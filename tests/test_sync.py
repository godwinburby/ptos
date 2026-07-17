import os
import time
import subprocess
import pytest
import ptos


class TestPidIsRunning:
    def test_current_pid_is_running(self):
        assert ptos._pid_is_running(os.getpid()) is True

    def test_invalid_pid_not_running(self):
        assert ptos._pid_is_running(9999999) is False


class TestSyncLock:
    def test_acquire_and_release(self):
        assert ptos._acquire_sync_lock() is True
        lock_path = os.path.join(ptos.BASE_DIR, ".sync.lock")
        assert os.path.isfile(lock_path)
        with open(lock_path) as f:
            assert f.read().strip() == str(os.getpid())
        ptos._release_sync_lock()
        assert not os.path.isfile(lock_path)

    def test_release_nonexistent_lock_is_safe(self):
        ptos._release_sync_lock()

    def test_stale_lock_is_reclaimed(self):
        lock_path = os.path.join(ptos.BASE_DIR, ".sync.lock")
        with open(lock_path, "w") as f:
            f.write("9999999")
        assert ptos._acquire_sync_lock() is True
        with open(lock_path) as f:
            assert f.read().strip() == str(os.getpid())
        ptos._release_sync_lock()

    def test_second_acquire_fails_while_first_holds(self):
        assert ptos._acquire_sync_lock() is True
        assert ptos._acquire_sync_lock() is False
        ptos._release_sync_lock()

    def test_lock_released_on_exception(self):
        assert ptos._acquire_sync_lock() is True
        lock_path = os.path.join(ptos.BASE_DIR, ".sync.lock")
        assert os.path.isfile(lock_path)
        try:
            raise RuntimeError("boom")
        except RuntimeError:
            pass
        ptos._release_sync_lock()
        assert not os.path.isfile(lock_path)


class TestRunSyncLock:
    def test_run_sync_acquires_and_releases_lock(self, monkeypatch):
        monkeypatch.setattr(ptos, "get_config", lambda: {
            "sync": {"remote_name": "test", "remote_path": "data"}
        })
        monkeypatch.setattr(ptos, "_detect_corruption", lambda *a: [])
        monkeypatch.setattr(ptos, "_record_sizes", lambda *a: None)
        monkeypatch.setattr(ptos, "_invalidate_all", lambda: None)
        monkeypatch.setattr(ptos, "_clear_rclone_bisync_locks", lambda: None)
        def capture_run(cmd, **kw):
            if "listremotes" in cmd:
                return subprocess.CompletedProcess(
                    args=cmd, returncode=0, stdout="test:\n", stderr="")
            return subprocess.CompletedProcess(
                args=cmd, returncode=0, stdout="", stderr="")
        monkeypatch.setattr(subprocess, "run", capture_run)
        def fake_popen(cmd, **kw):
            proc = subprocess.CompletedProcess(args=cmd, returncode=0, stdout="", stderr="")
            proc.stdout = iter([])
            return proc
        monkeypatch.setattr(subprocess, "Popen", fake_popen)
        ptos.run_sync("bisync")
        assert not os.path.isfile(os.path.join(ptos.BASE_DIR, ".sync.lock"))

    def test_run_sync_rejects_when_lock_held(self, monkeypatch):
        monkeypatch.setattr(ptos, "get_config", lambda: {
            "sync": {"remote_name": "test", "remote_path": "data"}
        })
        assert ptos._acquire_sync_lock() is True
        result = ptos.run_sync("bisync")
        assert result["ok"] is False
        assert "already running" in result["error"]
        ptos._release_sync_lock()

    def test_run_sync_releases_lock_on_exception(self, monkeypatch):
        monkeypatch.setattr(ptos, "get_config", lambda: {
            "sync": {"remote_name": "test", "remote_path": "data"}
        })
        monkeypatch.setattr(ptos, "_detect_corruption", lambda *a: [])
        monkeypatch.setattr(ptos, "_clear_rclone_bisync_locks", lambda: None)
        def capture_run(cmd, **kw):
            if "listremotes" in cmd:
                return subprocess.CompletedProcess(
                    args=cmd, returncode=0, stdout="test:\n", stderr="")
            return subprocess.CompletedProcess(
                args=cmd, returncode=0, stdout="", stderr="")
        monkeypatch.setattr(subprocess, "run", capture_run)
        def boom(*a, **kw):
            raise RuntimeError("rclone crashed")
        monkeypatch.setattr(subprocess, "Popen", boom)
        try:
            ptos.run_sync("bisync")
        except RuntimeError:
            pass
        assert not os.path.isfile(os.path.join(ptos.BASE_DIR, ".sync.lock"))

    def test_run_sync_exclude_list_includes_lock_files(self, monkeypatch):
        captured_cmd = []
        def capture_run(cmd, **kw):
            if "listremotes" in cmd:
                return subprocess.CompletedProcess(
                    args=cmd, returncode=0, stdout="test:\n", stderr="")
            return subprocess.CompletedProcess(
                args=cmd, returncode=0, stdout="", stderr="")
        def capture_popen(cmd, **kw):
            captured_cmd.extend(cmd)
            proc = subprocess.CompletedProcess(
                args=cmd, returncode=0, stdout="", stderr="")
            proc.stdout = iter([])
            return proc
        monkeypatch.setattr(ptos, "get_config", lambda: {
            "sync": {"remote_name": "test", "remote_path": "data"}
        })
        monkeypatch.setattr(ptos, "_detect_corruption", lambda *a: [])
        monkeypatch.setattr(ptos, "_record_sizes", lambda *a: None)
        monkeypatch.setattr(ptos, "_invalidate_all", lambda: None)
        monkeypatch.setattr(ptos, "_clear_rclone_bisync_locks", lambda: None)
        monkeypatch.setattr(subprocess, "run", capture_run)
        monkeypatch.setattr(subprocess, "Popen", capture_popen)
        ptos.run_sync("bisync")
        assert ".sync.lock" in captured_cmd
        assert ".sync_scheduled.log" in captured_cmd
