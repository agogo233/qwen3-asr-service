"""app/api/maintenance_routes.py 测试（存储统计与运行时缓存清理）。

验证：统计准确性、活跃任务排除（file_path/chunk 目录）、四类清理动作、
认证 401、未知 target 400、task_store 未启用时 unavailable。
"""
import logging
import os
import time

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import config as cfg
from app.api import maintenance_routes as mr


@pytest.fixture
def maint_env(tmp_path, monkeypatch, tm_factory):
    """装配 maintenance 路由 + 重定向全部缓存路径到临时目录。

    返回 (client_factory, uploads_dir, chunks_dir, log_file)；
    client_factory(task_manager, task_store=None) 构建 TestClient。
    """
    uploads = tmp_path / "uploads"
    chunks = tmp_path / "audio_chunks"
    log_file = tmp_path / "asr.log"
    uploads.mkdir()
    chunks.mkdir()
    monkeypatch.setattr(cfg, "UPLOADS_DIR", str(uploads))
    monkeypatch.setattr(cfg, "AUDIO_CHUNKS_DIR", str(chunks))
    monkeypatch.setattr(cfg, "LOG_FILE", str(log_file))
    monkeypatch.setattr(cfg, "API_KEY", "")

    def _make(tm, task_store=None):
        mr.init_maintenance(tm, task_store)
        app = FastAPI()
        app.include_router(mr.build_maintenance_router("/v2"))
        return TestClient(app)

    return _make, uploads, chunks, log_file


def _age(path: str, seconds: float):
    """把文件/目录树 mtime 拨回过去（超过 MIN_AGE_SEC 视为可清理）"""
    old = time.time() - seconds
    if os.path.isdir(path):
        for root, _dirs, names in os.walk(path):
            os.utime(root, (old, old))
            for name in names:
                os.utime(os.path.join(root, name), (old, old))
    else:
        os.utime(path, (old, old))


def _submit_task(tm, file_path):
    """提交 pending 任务（不 start worker，仅注册内存记录供活跃集合判定）"""
    tm.submit(file_path=file_path)


# ─── storage 统计 ───

def test_storage_stats_counts_orphans_and_chunks(maint_env, tm_factory):
    make, uploads, chunks, _log = maint_env
    tm = tm_factory()

    old_orphan = uploads / "old.wav"
    old_orphan.write_bytes(b"x" * 100)
    _age(str(old_orphan), mr.MIN_AGE_SEC + 60)
    fresh = uploads / "fresh.wav"
    fresh.write_bytes(b"x" * 50)          # 新文件：不计入
    active_src = uploads / "active-src.wav"
    active_src.write_bytes(b"x" * 10)
    _age(str(active_src), mr.MIN_AGE_SEC + 60)
    _submit_task(tm, str(active_src))     # 活跃任务上传源：不计入

    stale_chunk = chunks / "dead-task"
    stale_chunk.mkdir()
    (stale_chunk / "c.wav").write_bytes(b"x" * 30)
    _age(str(stale_chunk), mr.MIN_AGE_SEC + 60)
    live_chunk = chunks / "live-task"
    live_chunk.mkdir()                    # 属于活跃任务 ID 的同名目录不存在 → 可清理？
    # live-task 不是任何活跃任务 ID（活跃任务 ID 是 submit 生成的 uuid），也算残留：
    # 用 mtime 阈值区分——刚创建的不计入
    (live_chunk / "c.wav").write_bytes(b"x" * 20)

    resp = make(tm).get("/v2/maintenance/storage")
    assert resp.status_code == 200
    items = {i["key"]: i for i in resp.json()["items"]}
    assert items["orphan_uploads"]["bytes"] == 100
    assert items["orphan_uploads"]["files"] == 1
    assert items["stale_chunks"]["bytes"] == 30
    assert items["stale_chunks"]["files"] == 1
    assert items["logs"]["available"] is True   # 日志文件未创建时 available 但 0 字节


def test_storage_active_processing_excluded(maint_env, tm_factory):
    """processing 状态任务的 file_path 与 chunk 目录均被排除"""
    make, uploads, chunks, _log = maint_env
    tm = tm_factory()
    src = uploads / "proc.wav"
    src.write_bytes(b"x")
    _age(str(src), mr.MIN_AGE_SEC + 60)
    task_id = tm.submit(file_path=str(src))
    tm.get_task(task_id)["status"] = "processing"

    chunk_dir = chunks / task_id
    chunk_dir.mkdir()
    (chunk_dir / "c.wav").write_bytes(b"x")
    _age(str(chunk_dir), mr.MIN_AGE_SEC + 60)

    items = {i["key"]: i for i in make(tm).get("/v2/maintenance/storage").json()["items"]}
    assert items["orphan_uploads"]["files"] == 0
    assert items["stale_chunks"]["files"] == 0


def test_storage_task_history_unavailable_without_store(maint_env, tm_factory):
    make, *_ = maint_env
    items = {i["key"]: i for i in make(tm_factory()).get("/v2/maintenance/storage").json()["items"]}
    assert items["task_history"]["available"] is False


def test_storage_task_history_with_store(maint_env, tm_factory, tmp_path):
    from app.runtime.task_store import TaskStore
    make, *_ = maint_env
    store = TaskStore(str(tmp_path / "tasks.db"), retention_days=7)
    try:
        done = {"task_id": "t1", "status": "completed", "progress": 1.0,
                "created_at": "2026-01-01T00:00:00",
                "finished_at": "2026-01-01T00:01:00"}
        running = {"task_id": "t2", "status": "processing", "progress": 0.5,
                   "created_at": "2026-01-01T00:00:00"}
        for t in (done, running):
            store.insert_task(t)
        store.finalize_task(done)

        items = {i["key"]: i for i in make(tm_factory(), store).get("/v2/maintenance/storage").json()["items"]}
        assert items["task_history"]["available"] is True
        assert items["task_history"]["files"] == 1      # 仅终态计数
        assert items["task_history"]["bytes"] > 0
    finally:
        store.close()


# ─── cleanup ───

def test_cleanup_orphan_uploads_keeps_fresh_and_active(maint_env, tm_factory):
    make, uploads, _chunks, _log = maint_env
    tm = tm_factory()
    orphan = uploads / "old.wav"
    orphan.write_bytes(b"x" * 100)
    _age(str(orphan), mr.MIN_AGE_SEC + 60)
    fresh = uploads / "fresh.wav"
    fresh.write_bytes(b"x")
    active_src = uploads / "src.wav"
    active_src.write_bytes(b"x")
    _submit_task(tm, str(active_src))

    body = {"targets": ["orphan_uploads"]}
    resp = make(tm).post("/v2/maintenance/cleanup", json=body)
    assert resp.status_code == 200
    r = resp.json()["results"][0]
    assert r["status"] == "cleaned"
    assert r["removed_files"] == 1
    assert r["freed_bytes"] == 100
    assert not orphan.exists()
    assert fresh.exists() and active_src.exists()


def test_cleanup_stale_chunks_removes_dir_tree(maint_env, tm_factory):
    make, _uploads, chunks, _log = maint_env
    stale = chunks / "dead-task"
    stale.mkdir()
    (stale / "sub").mkdir()
    (stale / "sub" / "c.wav").write_bytes(b"x" * 40)
    _age(str(stale), mr.MIN_AGE_SEC + 60)
    fresh_dir = chunks / "fresh-task"
    fresh_dir.mkdir()
    (fresh_dir / "c.wav").write_bytes(b"x")

    resp = make(tm_factory()).post("/v2/maintenance/cleanup",
                                   json={"targets": ["stale_chunks"]})
    r = resp.json()["results"][0]
    assert r["removed_files"] == 1 and r["freed_bytes"] == 40
    assert not stale.exists()
    assert fresh_dir.exists()


def test_cleanup_logs_truncates(maint_env, tm_factory):
    make, _u, _c, log_file = maint_env
    log_file.write_text("hello log\n" * 100)
    resp = make(tm_factory()).post("/v2/maintenance/cleanup", json={"targets": ["logs"]})
    r = resp.json()["results"][0]
    assert r["status"] == "cleaned"
    assert r["freed_bytes"] == 1000
    assert log_file.exists() and log_file.stat().st_size == 0


def test_cleanup_logs_via_file_handler(maint_env, tm_factory):
    """已挂载 FileHandler 时走句柄截断分支，且句柄仍可继续写入"""
    make, _u, _c, log_file = maint_env
    root = logging.getLogger()
    old_level = root.level
    root.setLevel(logging.INFO)
    handler = logging.FileHandler(str(log_file), encoding="utf-8")
    root.addHandler(handler)
    try:
        logging.getLogger().info("payload")
        handler.flush()
        size_before = log_file.stat().st_size
        assert size_before > 0

        root.setLevel(logging.CRITICAL)   # 静默 TestClient/httpx 请求日志对文件的追加写入
        resp = make(tm_factory()).post("/v2/maintenance/cleanup", json={"targets": ["logs"]})
        r = resp.json()["results"][0]
        assert r["freed_bytes"] == size_before
        assert log_file.stat().st_size == 0
        assert handler.stream.tell() == 0       # 写入位置已重置，后续日志从头部追加
    finally:
        root.removeHandler(handler)
        handler.close()
        root.setLevel(old_level)


def test_cleanup_task_history_purges_finished_only(maint_env, tm_factory, tmp_path):
    from app.runtime.task_store import TaskStore
    make, _u, _c, _log = maint_env
    store = TaskStore(str(tmp_path / "tasks.db"), retention_days=7)
    tm = tm_factory()
    try:
        done = {"task_id": "t1", "status": "completed", "progress": 1.0,
                "created_at": "2026-01-01T00:00:00",
                "finished_at": "2026-01-01T00:01:00"}
        running = {"task_id": "t2", "status": "processing", "progress": 0.5,
                   "created_at": "2026-01-01T00:00:00"}
        for t in (done, running):
            store.insert_task(t)
        store.finalize_task(done)
        mem_done_id = tm.submit(file_path="x.wav")
        tm.get_task(mem_done_id)["status"] = "completed"
        mem_run_id = tm.submit(file_path="y.wav")   # pending 保持

        resp = make(tm, store).post("/v2/maintenance/cleanup",
                                    json={"targets": ["task_history"]})
        r = resp.json()["results"][0]
        assert r["status"] == "cleaned"
        assert r["removed_files"] == 2          # 1 条库记录 + 1 个内存终态任务
        assert store.count_finished() == 0
        assert store.get_task("t2")["status"] == "processing"   # 进行中不受影响
        assert tm.get_task(mem_run_id) is not None
        assert tm.get_task(mem_done_id) is None
    finally:
        store.close()


def test_cleanup_task_history_unavailable_without_store(maint_env, tm_factory):
    make, *_ = maint_env
    resp = make(tm_factory()).post("/v2/maintenance/cleanup",
                                   json={"targets": ["task_history"]})
    assert resp.json()["results"][0]["status"] == "unavailable"


def test_cleanup_unknown_target_400(maint_env, tm_factory):
    make, *_ = maint_env
    resp = make(tm_factory()).post("/v2/maintenance/cleanup",
                                   json={"targets": ["models_dir"]})
    assert resp.status_code == 400


def test_missing_cache_dirs_tolerated(maint_env, tm_factory):
    """uploads/chunks 目录不存在时统计与清理均为 no-op，不抛 500"""
    make, uploads, chunks, _log = maint_env
    uploads.rmdir()
    chunks.rmdir()
    client = make(tm_factory())
    items = {i["key"]: i for i in client.get("/v2/maintenance/storage").json()["items"]}
    assert items["orphan_uploads"]["files"] == 0
    assert items["stale_chunks"]["bytes"] == 0
    resp = client.post("/v2/maintenance/cleanup",
                       json={"targets": ["orphan_uploads", "stale_chunks"]})
    assert resp.status_code == 200
    assert all(r["status"] == "cleaned" and r["removed_files"] == 0
               for r in resp.json()["results"])


def test_cleanup_empty_targets_ok(maint_env, tm_factory):
    make, *_ = maint_env
    resp = make(tm_factory()).post("/v2/maintenance/cleanup", json={"targets": []})
    assert resp.status_code == 200
    assert resp.json()["results"] == []


def test_cleanup_requires_api_key(maint_env, tm_factory, monkeypatch):
    make, *_ = maint_env
    monkeypatch.setattr(cfg, "API_KEY", "secret")
    client = make(tm_factory())
    assert client.get("/v2/maintenance/storage").status_code == 401
    assert client.post("/v2/maintenance/cleanup",
                       json={"targets": ["logs"]}).status_code == 401
    ok = client.get("/v2/maintenance/storage",
                    headers={"Authorization": "Bearer secret"})
    assert ok.status_code == 200


def test_multiple_targets_in_order(maint_env, tm_factory):
    make, uploads, _c, log_file = maint_env
    orphan = uploads / "old.wav"
    orphan.write_bytes(b"x" * 10)
    _age(str(orphan), mr.MIN_AGE_SEC + 60)
    log_file.write_text("x" * 5)

    resp = make(tm_factory()).post("/v2/maintenance/cleanup",
                                   json={"targets": ["orphan_uploads", "logs"]})
    results = resp.json()["results"]
    assert [r["key"] for r in results] == ["orphan_uploads", "logs"]
    assert all(r["status"] == "cleaned" for r in results)
