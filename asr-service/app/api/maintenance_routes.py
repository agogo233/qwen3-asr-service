"""维护路由：存储占用统计与运行时缓存清理（WebUI 存储清理面板后端）。

清理范围仅限运行时缓存四类，绝不触碰 models/venv/声纹库等资产目录：
- orphan_uploads：uploads 内孤儿上传/转码残留（崩溃或停机期间滞留）
- stale_chunks：audio_chunks 下崩溃残留的任务切片目录（pipeline finally 仅覆盖正常路径）
- task_history：tasks.db 终态历史记录 + 内存终态任务（任务持久化未启用时不可用）
- logs：logs/asr.log 截断清空（保留文件句柄，跨平台安全）

安全边界：
- 删除目标一律来自对 config 白名单目录的 os.listdir 枚举，不接受任何请求传入的路径；
- orphan/chunks 均要求 mtime 早于 MIN_AGE_SEC（> TASK_TIMEOUT 最坏运行期），避免误删
  不经 TaskManager 队列的同步临时文件（声纹登记 spk_*、URL 下载 dsdl_* 等）；
- 写操作需 Bearer API Key（与业务接口同一 verify_api_key）。
"""
import logging
import os
import shutil
import time

from fastapi import APIRouter, Depends, HTTPException

from app import config as cfg
from app.api.schemas import (
    MaintenanceCleanupRequest,
    MaintenanceCleanupResponse,
    MaintenanceCleanupResult,
    MaintenanceItem,
    MaintenanceStorageResponse,
)
from app.api.routes import verify_api_key

logger = logging.getLogger(__name__)

# 手动清理的最小文件年龄（秒）：须大于 TASK_TIMEOUT（30min）的最坏任务运行期，
# 兜底排除进行中任务的同步临时文件（声纹登记/URL 下载不经 TaskManager，无法按集合排除）
MIN_AGE_SEC = 3600

CLEANUP_KEYS = ("orphan_uploads", "stale_chunks", "task_history", "logs")

_task_manager = None
_task_store = None


def init_maintenance(task_manager, task_store=None):
    """注入运行时依赖（task_store 可选：未启用时 task_history 项标记不可用）"""
    global _task_manager, _task_store
    _task_manager = task_manager
    _task_store = task_store


def _dir_stats(path: str) -> tuple[int, int]:
    """目录树累计 (bytes, files)；不存在返回 (0, 0)"""
    total = files = 0
    for root, _dirs, names in os.walk(path):
        for name in names:
            try:
                total += os.path.getsize(os.path.join(root, name))
                files += 1
            except OSError:
                continue
    return total, files


def _newest_mtime(path: str) -> float:
    """目录树内最大 mtime（含目录自身），用于判断是否仍在活跃写入"""
    newest = 0.0
    for root, _dirs, names in os.walk(path):
        try:
            newest = max(newest, os.path.getmtime(root))
        except OSError:
            continue
        for name in names:
            try:
                newest = max(newest, os.path.getmtime(os.path.join(root, name)))
            except OSError:
                continue
    return newest


def _scan_orphan_uploads() -> tuple[list[str], int]:
    """枚举 uploads 内可清理孤儿文件：(绝对路径列表, 总字节)。"""
    if not os.path.isdir(cfg.UPLOADS_DIR):
        return [], 0
    cutoff = time.time() - MIN_AGE_SEC
    active_paths = _task_manager.active_file_paths()
    paths: list[str] = []
    total = 0
    for name in os.listdir(cfg.UPLOADS_DIR):
        path = os.path.abspath(os.path.join(cfg.UPLOADS_DIR, name))
        if not os.path.isfile(path) or path in active_paths:
            continue
        try:
            if os.path.getmtime(path) >= cutoff:
                continue
            paths.append(path)
            total += os.path.getsize(path)
        except OSError:
            continue
    return paths, total


def _scan_stale_chunks() -> tuple[list[str], int]:
    """枚举 audio_chunks 下可清理残留任务目录：(绝对路径列表, 总字节)。"""
    if not os.path.isdir(cfg.AUDIO_CHUNKS_DIR):
        return [], 0
    cutoff = time.time() - MIN_AGE_SEC
    active_ids = _task_manager.active_task_ids()
    dirs: list[str] = []
    total = 0
    for name in os.listdir(cfg.AUDIO_CHUNKS_DIR):
        path = os.path.abspath(os.path.join(cfg.AUDIO_CHUNKS_DIR, name))
        if not os.path.isdir(path) or name in active_ids:
            continue
        if _newest_mtime(path) >= cutoff:
            continue
        size, _files = _dir_stats(path)
        dirs.append(path)
        total += size
    return dirs, total


def _db_files_size(db_path: str) -> int:
    """SQLite 主库 + WAL/SHM 伴生文件总字节数"""
    total = 0
    for suffix in ("", "-wal", "-shm"):
        try:
            total += os.path.getsize(db_path + suffix)
        except OSError:
            continue
    return total


def _storage_items() -> list[MaintenanceItem]:
    items: list[MaintenanceItem] = []

    orphan_paths, orphan_bytes = _scan_orphan_uploads()
    chunk_dirs, chunk_bytes = _scan_stale_chunks()
    items.append(MaintenanceItem(
        key="orphan_uploads", available=True, bytes=orphan_bytes, files=len(orphan_paths)))
    items.append(MaintenanceItem(
        key="stale_chunks", available=True, bytes=chunk_bytes, files=len(chunk_dirs)))

    if _task_store is None:
        items.append(MaintenanceItem(key="task_history", available=False))
    else:
        size = _db_files_size(_task_store.db_path)
        count = _task_store.count_finished()
        count = count if count is not None else 0
        items.append(MaintenanceItem(key="task_history", available=True,
                                     bytes=size, files=count))

    try:
        log_size = os.path.getsize(cfg.LOG_FILE)
        items.append(MaintenanceItem(key="logs", available=True,
                                     bytes=log_size, files=1 if log_size else 0))
    except OSError:
        items.append(MaintenanceItem(key="logs", available=True))
    return items


def _truncate_log() -> int:
    """截断服务日志，返回释放字节数。优先复用已打开的 FileHandler 句柄。"""
    freed = 0
    try:
        freed = os.path.getsize(cfg.LOG_FILE)
    except OSError:
        return 0
    target = os.path.abspath(cfg.LOG_FILE)
    for handler in logging.getLogger().handlers:
        base = getattr(handler, "baseFilename", None)
        stream = getattr(handler, "stream", None)
        if base and stream and os.path.abspath(base) == target:
            try:
                stream.seek(0)
                stream.truncate(0)
                return freed
            except (OSError, ValueError):
                continue
    # 未找到匹配 handler（如日志模块未初始化）：直接重开截断
    try:
        with open(cfg.LOG_FILE, "w"):
            pass
    except OSError as e:
        logger.warning(f"日志截断失败: {e}")
        return 0
    return freed


def _clean_orphan_uploads() -> MaintenanceCleanupResult:
    paths, total = _scan_orphan_uploads()
    removed = 0
    for path in paths:
        try:
            os.remove(path)
            removed += 1
        except OSError:
            continue
    return MaintenanceCleanupResult(
        key="orphan_uploads", status="cleaned",
        removed_files=removed, freed_bytes=total if removed else 0)


def _clean_stale_chunks() -> MaintenanceCleanupResult:
    dirs, total = _scan_stale_chunks()
    removed = 0
    for path in dirs:
        shutil.rmtree(path, ignore_errors=True)
        if not os.path.exists(path):
            removed += 1
    return MaintenanceCleanupResult(
        key="stale_chunks", status="cleaned",
        removed_files=removed, freed_bytes=total if removed else 0)


def _clean_task_history() -> MaintenanceCleanupResult:
    result = MaintenanceCleanupResult(key="task_history", status="cleaned")
    memory_removed = _task_manager.purge_finished()
    if _task_store is not None:
        deleted = _task_store.purge_finished()
        if deleted < 0:
            result.status = "error"
            result.removed_files = memory_removed
            return result
        result.removed_files = memory_removed + deleted
        result.freed_bytes = _db_files_size(_task_store.db_path) if deleted else 0
    else:
        result.removed_files = memory_removed
    return result


def _clean_logs() -> MaintenanceCleanupResult:
    freed = _truncate_log()
    return MaintenanceCleanupResult(
        key="logs", status="cleaned" if freed >= 0 else "error", freed_bytes=freed)


_CLEANERS = {
    "orphan_uploads": _clean_orphan_uploads,
    "stale_chunks": _clean_stale_chunks,
    "task_history": _clean_task_history,
    "logs": _clean_logs,
}


def build_maintenance_router(prefix: str = "/v2") -> APIRouter:
    r = APIRouter()

    @r.get(prefix + "/maintenance/storage",
           response_model=MaintenanceStorageResponse, dependencies=[Depends(verify_api_key)])
    async def storage_stats():
        """各运行时缓存项占用统计（活跃任务文件自动排除，不计入可清理量）"""
        return MaintenanceStorageResponse(items=_storage_items())

    @r.post(prefix + "/maintenance/cleanup",
            response_model=MaintenanceCleanupResponse, dependencies=[Depends(verify_api_key)])
    async def cleanup(body: MaintenanceCleanupRequest):
        """按 targets 执行清理；未知 target 返回 400，功能未启用项返回 unavailable"""
        unknown = [k for k in body.targets if k not in CLEANUP_KEYS]
        if unknown:
            raise HTTPException(status_code=400,
                                detail=f"未知清理项: {', '.join(sorted(set(unknown)))}")
        results = []
        for key in body.targets:
            if key == "task_history" and _task_store is None:
                results.append(MaintenanceCleanupResult(key=key, status="unavailable"))
                continue
            results.append(_CLEANERS[key]())
        return MaintenanceCleanupResponse(results=results)

    return r
