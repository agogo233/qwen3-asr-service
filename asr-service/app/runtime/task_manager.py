import os
import queue
import threading
import uuid
import logging
import time
from datetime import datetime
from app.config import (
    TASK_TIMEOUT,
    TASK_RESULT_TTL,
    TASK_CLEANUP_INTERVAL,
    TASK_ORPHAN_TTL,
    UPLOADS_DIR,
)

logger = logging.getLogger(__name__)


class TaskManager:
    def __init__(self, max_queue_size=100, store=None):
        self._queue = queue.Queue(maxsize=max_queue_size)
        self._tasks = {}  # task_id -> task_dict
        self._cancel_events: dict[str, threading.Event] = {}  # task_id -> cancel event
        self._done_events: dict[str, threading.Event] = {}    # task_id -> 终态通知（同步等待用）
        self._lock = threading.Lock()
        self._worker_thread = None
        self._cleanup_thread = None
        self._process_fn = None
        self._stop_event = threading.Event()
        # 可选持久化（app.runtime.task_store.TaskStore）：write-through，
        # store 内部自吞库异常，钩子调用一律放在 self._lock 之外（锁内不做 I/O）
        self._store = store

    @property
    def is_stopping(self) -> bool:
        return self._stop_event.is_set()

    def set_processor(self, fn):
        """注入任务处理函数: fn(task_dict) -> result"""
        self._process_fn = fn

    def start(self):
        """启动工作线程和清理线程"""
        self._worker_thread = threading.Thread(target=self._worker, daemon=True)
        self._worker_thread.start()
        self._cleanup_thread = threading.Thread(target=self._cleanup_loop, daemon=True)
        self._cleanup_thread.start()
        logger.info("任务工作线程和清理线程已启动")

    def submit(self, file_path: str, language: str | None = None,
               wav_name: str | None = None, identify_speakers: bool = False,
               options: dict | None = None) -> str:
        """提交任务，返回 task_id。options=按请求覆盖项（仅内存，不落库）。"""
        task_id = str(uuid.uuid4())
        task = {
            "task_id": task_id,
            "status": "pending",
            "progress": 0.0,
            "file_path": file_path,
            "language": language,
            "wav_name": wav_name,
            "identify_speakers": identify_speakers,
            "options": options or {},
            "result": None,
            "error": None,
            "created_at": datetime.now().isoformat(),
            "finished_at": None,
        }

        with self._lock:
            self._tasks[task_id] = task
            self._cancel_events[task_id] = threading.Event()
            self._done_events[task_id] = threading.Event()

        self._queue.put_nowait(task_id)  # 队列满时抛出 queue.Full
        if self._store:
            self._store.insert_task(task)
        logger.info(f"任务已提交: {task_id}")
        return task_id

    def get_task(self, task_id: str) -> dict | None:
        """查询任务状态"""
        with self._lock:
            return self._tasks.get(task_id)

    def list_tasks(self, status: str | None = None) -> list[dict]:
        """列出任务，可按状态筛选，返回不含 result 的摘要（按创建时间倒序）"""
        with self._lock:
            tasks = list(self._tasks.values())

        if status:
            tasks = [t for t in tasks if t["status"] == status]

        tasks.sort(key=lambda t: t.get("created_at", ""), reverse=True)

        return [
            {
                "task_id": t["task_id"],
                "status": t["status"],
                "progress": t["progress"],
                "language": t.get("language"),
                "wav_name": t.get("wav_name"),
                "created_at": t["created_at"],
                "finished_at": t.get("finished_at"),
                "error": t.get("error"),
            }
            for t in tasks
        ]

    def update_progress(self, task_id: str, progress: float):
        """更新任务进度"""
        with self._lock:
            if task_id not in self._tasks:
                return
            self._tasks[task_id]["progress"] = progress
        if self._store:
            self._store.save_progress(task_id, progress)  # store 内部 1s 节流

    def cancel_task(self, task_id: str) -> str | None:
        """请求取消任务。返回取消前的状态，或 None 表示任务不存在。"""
        with self._lock:
            task = self._tasks.get(task_id)
            if not task:
                return None
            status = task["status"]
            if status in ("completed", "failed", "cancelled"):
                return status  # 已终结，不操作

            # 设置 per-task 取消事件
            cancel_event = self._cancel_events.get(task_id)
            if cancel_event:
                cancel_event.set()

            if status == "pending":
                # 尚未开始处理，立即标记为取消
                task["status"] = "cancelled"
                task["error"] = "任务已取消"
                task["finished_at"] = datetime.now().isoformat()
                self._signal_done(task_id)   # pending 直接终态，唤醒同步等待方
                logger.info(f"任务已取消 (pending): {task_id}")
            else:
                # processing 中，pipeline 将在下一个 chunk 边界检测到取消
                logger.info(f"任务取消请求已发送 (processing): {task_id}")

        if status == "pending":
            self._remove_upload_file(task)   # 锁外 I/O：未处理任务直接清理上传文件
            if self._store:
                self._store.finalize_task(task)
        return status

    def is_cancelled(self, task_id: str) -> bool:
        """检查指定任务是否已被请求取消（依赖 CPython GIL 保证 dict 读取安全）"""
        event = self._cancel_events.get(task_id)
        return event.is_set() if event else False

    def _remove_upload_file(self, task: dict) -> None:
        """删除任务上传文件（pending 取消/跳过时兜底清理；幂等，缺失静默）。

        仅删除 UPLOADS_DIR 内的文件（服务端 uuid 保存路径），防御外部路径混入。
        """
        path = task.get("file_path")
        if not path:
            return
        uploads = os.path.abspath(UPLOADS_DIR)
        try:
            if os.path.commonpath([os.path.abspath(path), uploads]) != uploads:
                return
        except ValueError:
            return  # 路径无法比较（不同盘符）→ 非上传目录文件，跳过
        try:
            if os.path.exists(path):
                os.remove(path)
        except FileNotFoundError:
            pass  # 并发双删（cancel_task 与 worker 跳过分支）→ 幂等静默
        except OSError as e:
            logger.warning(f"清理任务上传文件失败: {task['task_id']}: {e}")

    def _signal_done(self, task_id: str):
        """标记任务已达终态，唤醒所有 wait_done 等待方（幂等）。"""
        event = self._done_events.get(task_id)
        if event is not None:
            event.set()

    def wait_done(self, task_id: str, timeout: float) -> dict | None:
        """阻塞等待任务终态（completed/failed/cancelled），返回任务快照。

        超时返回 None；任务不存在（已被 TTL 清理）时回退到 get_task 当前快照。
        供兼容层同步端点经 asyncio.to_thread 调用，不阻塞事件循环。
        """
        event = self._done_events.get(task_id)
        if event is None:
            return self.get_task(task_id)
        if not event.wait(timeout):
            return None
        return self.get_task(task_id)

    def _worker(self):
        """工作线程：串行消费队列，每任务独立 daemon 线程 + join 超时实现协作取消。

        超时语义：join(timeout) 超时后协作取消（set cancel_event）+ 立即标记 failed 并放行
        后续任务。残留线程为 daemon，pipeline 在下一个 chunk/batch 边界自停后退出；期间
        新任务与残留线程瞬时并发（有意取舍：恢复队列优先于严格串行，见 audit 1-9）。
        """
        while not self._stop_event.is_set():
            try:
                task_id = self._queue.get(timeout=1)
            except queue.Empty:
                continue

            skip = False
            with self._lock:
                task = self._tasks.get(task_id)
                if not task:
                    self._queue.task_done()
                    continue
                # pending 时已被取消的任务，跳过处理（文件清理在锁外）
                if task.get("status") == "cancelled":
                    skip = True
                else:
                    task["status"] = "processing"

            if skip:
                self._remove_upload_file(task)
                self._queue.task_done()
                continue

            if self._store:
                self._store.update_status(task_id, "processing")  # 状态跃迁立即落库

            cancel_event = self._cancel_events.get(task_id)
            start_time = time.time()

            box = {"result": None, "error": None}

            def _run():
                try:
                    box["result"] = self._process_fn(task)
                except BaseException as e:
                    box["error"] = e

            worker = threading.Thread(target=_run, daemon=True)
            worker.start()
            worker.join(timeout=TASK_TIMEOUT)
            elapsed = time.time() - start_time

            if worker.is_alive():
                # 超时：协作取消让 pipeline 尽快自停，同时不等待残留线程
                if cancel_event:
                    cancel_event.set()
                with self._lock:
                    task["status"] = "failed"
                    task["error"] = f"处理超时（>{TASK_TIMEOUT}s）"
                    task["finished_at"] = datetime.now().isoformat()
                if self._store:
                    self._store.finalize_task(task)
                logger.error(f"任务超时: {task_id} ({elapsed:.0f}s)")
            elif box["error"] is not None:
                if self._stop_event.is_set():
                    self._signal_done(task_id)
                    self._queue.task_done()
                    break
                with self._lock:
                    task["status"] = "failed"
                    task["error"] = "内部处理错误，请检查服务日志"
                    task["finished_at"] = datetime.now().isoformat()
                if self._store:
                    self._store.finalize_task(task)
                logger.error(
                    f"任务失败: {task_id}, 错误: {box['error']}",
                    exc_info=(type(box["error"]), box["error"], box["error"].__traceback__),
                )
            else:
                result = box["result"]
                with self._lock:
                    if cancel_event and cancel_event.is_set():
                        task["status"] = "cancelled"
                        task["result"] = result
                        task["error"] = "任务已取消，返回部分结果"
                        task["finished_at"] = datetime.now().isoformat()
                        logger.info(f"任务已取消 (processing, partial): {task_id}")
                    else:
                        task["status"] = "completed"
                        task["progress"] = 1.0
                        task["result"] = result
                        task["finished_at"] = datetime.now().isoformat()
                        logger.info(f"任务完成: {task_id} ({elapsed:.1f}s)")
                if self._store:
                    self._store.finalize_task(task)

            self._signal_done(task_id)   # 所有终态分支统一唤醒同步等待方
            self._queue.task_done()

    def shutdown(self) -> bool:
        """安全终止：停止工作线程并关闭线程池。

        返回工作线程是否已退出；False 表示仍有任务在收尾（finalize 可能尚未完成），
        调用方不应在此时关闭 task_store 连接（避免与 finalize 落库竞态）。
        """
        logger.info("正在终止任务管理器...")
        self._stop_event.set()
        if self._worker_thread and self._worker_thread.is_alive():
            self._worker_thread.join(timeout=5)
        if self._cleanup_thread and self._cleanup_thread.is_alive():
            self._cleanup_thread.join(timeout=2)
        worker_exited = not (self._worker_thread and self._worker_thread.is_alive())
        logger.info("任务管理器已终止")
        return worker_exited

    def _cleanup_loop(self):
        """定期清理已完成/失败的过期任务 + 上传目录孤儿文件"""
        while not self._stop_event.is_set():
            self._stop_event.wait(timeout=TASK_CLEANUP_INTERVAL)
            if not self._stop_event.is_set():
                self._cleanup_expired_tasks()
                self._cleanup_orphan_uploads()

    def _cleanup_expired_tasks(self):
        """清理超过 TTL 的已终结任务"""
        now = time.time()
        expired = []

        with self._lock:
            for task_id, task in self._tasks.items():
                if task["status"] in ("completed", "failed", "cancelled") and task.get("finished_at"):
                    finished_ts = datetime.fromisoformat(task["finished_at"]).timestamp()
                    if now - finished_ts > TASK_RESULT_TTL:
                        expired.append(task_id)
            for task_id in expired:
                del self._tasks[task_id]
                self._cancel_events.pop(task_id, None)
                self._done_events.pop(task_id, None)

        if expired:
            logger.info(f"已清理 {len(expired)} 个过期任务")

    def _cleanup_orphan_uploads(self):
        """清扫上传目录孤儿文件：mtime 超 TASK_ORPHAN_TTL 且不属于任何活跃任务。

        兜底覆盖 pending 取消漏删 / 进程崩溃等一切残留路径。活跃任务（pending/
        processing）的 file_path 一律排除，避免误删排队中尚未处理的上传文件。
        """
        try:
            uploads = os.path.abspath(UPLOADS_DIR)
            if not os.path.isdir(uploads):
                return
            with self._lock:
                active_paths = {
                    os.path.abspath(t["file_path"])
                    for t in self._tasks.values()
                    if t.get("file_path") and t["status"] in ("pending", "processing")
                }
            cutoff = time.time() - TASK_ORPHAN_TTL
            removed = 0
            for name in os.listdir(uploads):
                path = os.path.join(uploads, name)
                if not os.path.isfile(path):
                    continue
                if os.path.abspath(path) in active_paths:
                    continue
                try:
                    if os.path.getmtime(path) < cutoff:
                        os.remove(path)
                        removed += 1
                except OSError:
                    continue
            if removed:
                logger.info(f"已清扫 {removed} 个孤儿上传文件")
        except OSError as e:
            logger.warning(f"孤儿上传文件清扫失败: {e}")
