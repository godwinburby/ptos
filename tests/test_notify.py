import os
import json
import queue
import threading
import time
import subprocess
import pytest
import ptos_web
import ptos
import ptos_todo as todo_mod


class TestSseBroadcast:
    def test_broadcast_to_no_clients(self):
        with ptos_web._sse_lock:
            ptos_web._sse_clients.clear()
        ptos_web._sse_broadcast("test-event", {"key": "val"})

    def test_broadcast_delivers_to_connected_client(self):
        q = queue.Queue()
        with ptos_web._sse_lock:
            ptos_web._sse_clients.append(q)
        try:
            ptos_web._sse_broadcast("todo-due", [{"description": "test"}])
            msg = json.loads(q.get_nowait())
            assert msg["type"] == "todo-due"
            assert msg["data"][0]["description"] == "test"
        finally:
            with ptos_web._sse_lock:
                ptos_web._sse_clients.remove(q)

    def test_broadcast_does_not_block_on_full_queue(self):
        q = queue.Queue(maxsize=1)
        q.put("old")
        with ptos_web._sse_lock:
            ptos_web._sse_clients.append(q)
        try:
            ptos_web._sse_broadcast("test", "data")
            assert q.get_nowait() == "old"
        finally:
            with ptos_web._sse_lock:
                ptos_web._sse_clients.remove(q)

    def test_broadcast_multiple_clients(self):
        q1 = queue.Queue()
        q2 = queue.Queue()
        with ptos_web._sse_lock:
            ptos_web._sse_clients.extend([q1, q2])
        try:
            ptos_web._sse_broadcast("shutdown")
            assert json.loads(q1.get_nowait())["type"] == "shutdown"
            assert json.loads(q2.get_nowait())["type"] == "shutdown"
        finally:
            with ptos_web._sse_lock:
                ptos_web._sse_clients.clear()


class TestPendingNotifications:
    def setup_method(self):
        with ptos_web._sse_lock:
            ptos_web._pending_notifications.clear()

    def test_cache_is_populated_when_new_todos_found(self):
        tasks = [{"description": "task1", "due": "2026-07-17"}]
        with ptos_web._sse_lock:
            ptos_web._pending_notifications.clear()
            ptos_web._pending_notifications.append(tasks)
        with ptos_web._sse_lock:
            assert len(ptos_web._pending_notifications) == 1
            assert ptos_web._pending_notifications[0][0]["description"] == "task1"

    def test_cache_cleared_after_sse_replay(self):
        tasks = [{"description": "task1", "due": "2026-07-17"}]
        with ptos_web._sse_lock:
            ptos_web._pending_notifications.clear()
            ptos_web._pending_notifications.append(tasks)
        q = queue.Queue()
        with ptos_web._sse_lock:
            ptos_web._sse_clients.append(q)
        try:
            with ptos_web._sse_lock:
                pending = list(ptos_web._pending_notifications)
                ptos_web._pending_notifications.clear()
            for t in pending:
                ptos_web._sse_broadcast("todo-due", t)
            msg = json.loads(q.get_nowait())
            assert msg["type"] == "todo-due"
            with ptos_web._sse_lock:
                assert len(ptos_web._pending_notifications) == 0
        finally:
            with ptos_web._sse_lock:
                ptos_web._sse_clients.remove(q)

    def test_new_client_receives_pending_and_cache_cleared(self):
        tasks = [{"description": "startup task", "due": "2026-07-17"}]
        with ptos_web._sse_lock:
            ptos_web._pending_notifications.clear()
            ptos_web._pending_notifications.append(tasks)
        q = queue.Queue()
        with ptos_web._sse_lock:
            ptos_web._sse_clients.append(q)
        try:
            with ptos_web._sse_lock:
                pending = list(ptos_web._pending_notifications)
                ptos_web._pending_notifications.clear()
            for t in pending:
                payload = json.dumps({"type": "todo-due", "data": t})
                q.put_nowait(payload)
            msg = json.loads(q.get_nowait())
            assert msg["type"] == "todo-due"
            assert msg["data"][0]["description"] == "startup task"
            with ptos_web._sse_lock:
                assert len(ptos_web._pending_notifications) == 0
        finally:
            with ptos_web._sse_lock:
                ptos_web._sse_clients.remove(q)


class TestHousekeepingLogic:
    def _write_todo(self, line):
        todo_dir = os.path.dirname(ptos.TODO_PATH)
        os.makedirs(todo_dir, exist_ok=True)
        with open(ptos.TODO_PATH, "w") as f:
            f.write(line + "\n")
        return ptos.TODO_PATH

    def test_detects_due_todos(self):
        todo_path = self._write_todo("test task due:2026-07-17")
        todos, _ = todo_mod.load_todos(todo_path)
        due = todo_mod.get_due_todos(todos, lookahead_days=1)
        assert len(due) == 1
        assert due[0].description == "test task"

    def test_same_todos_not_repeated(self):
        todo_path = self._write_todo("task A due:2026-07-17")
        todos, _ = todo_mod.load_todos(todo_path)
        due = todo_mod.get_due_todos(todos, lookahead_days=1)
        notified = {(t.line_no, str(t.due), t.due_time) for t in due}
        new = [t for t in due if (t.line_no, str(t.due), t.due_time) not in notified]
        assert len(new) == 0

    def test_done_todo_not_in_due(self):
        self._write_todo("x 2026-07-17 2026-07-17 done task")
        todos, _ = todo_mod.load_todos(ptos.TODO_PATH)
        due = todo_mod.get_due_todos(todos, lookahead_days=1)
        assert len(due) == 0

    def test_threshold_todo_hidden(self):
        self._write_todo("future task due:2026-07-20 t:2026-12-01")
        todos, _ = todo_mod.load_todos(ptos.TODO_PATH)
        due = todo_mod.get_due_todos(todos, lookahead_days=1)
        assert len(due) == 0

    def test_no_due_todos_empty(self):
        self._write_todo("someday task")
        todos, _ = todo_mod.load_todos(ptos.TODO_PATH)
        due = todo_mod.get_due_todos(todos, lookahead_days=1)
        assert len(due) == 0

    def test_multiple_due_todos_detected(self):
        import datetime as _dt
        today = _dt.date.today()
        future = today + _dt.timedelta(days=2)
        self._write_todo(
            f"task A due:{today}\n"
            f"task B due:{today}\n"
            f"task C due:{future}"
        )
        todos, _ = todo_mod.load_todos(ptos.TODO_PATH)
        due = todo_mod.get_due_todos(todos, lookahead_days=1)
        assert len(due) == 2

    def test_new_vs_notified_dedup(self):
        self._write_todo(
            "task A due:2026-07-17\n"
            "task B due:2026-07-17"
        )
        todos, _ = todo_mod.load_todos(ptos.TODO_PATH)
        due = todo_mod.get_due_todos(todos, lookahead_days=1)
        notified = {(t.line_no, str(t.due), t.due_time) for t in due}
        assert len(notified) == 2
        new = [t for t in due if (t.line_no, str(t.due), t.due_time) not in notified]
        assert len(new) == 0


class TestDetectNotifyPlatform:
    def test_windows_detection(self, monkeypatch):
        monkeypatch.setattr("os.environ", {})
        monkeypatch.setattr("os.path.exists", lambda p: False)
        import platform as _platform
        monkeypatch.setattr(_platform, "system", lambda: "Windows")
        assert ptos_web._detect_notify_platform() == "windows"

    def test_linux_detection(self, monkeypatch):
        monkeypatch.setattr("os.environ", {})
        monkeypatch.setattr("os.path.exists", lambda p: False)
        import platform as _platform
        monkeypatch.setattr(_platform, "system", lambda: "Linux")
        assert ptos_web._detect_notify_platform() == "linux"

    def test_macos_detection(self, monkeypatch):
        monkeypatch.setattr("os.environ", {})
        monkeypatch.setattr("os.path.exists", lambda p: False)
        import platform as _platform
        monkeypatch.setattr(_platform, "system", lambda: "Darwin")
        assert ptos_web._detect_notify_platform() == "macos"

    def test_termux_detection_via_prefix(self, monkeypatch):
        monkeypatch.setattr("os.environ", {"PREFIX": "/data/data/com.termux/files/usr"})
        monkeypatch.setattr("os.path.exists", lambda p: False)
        assert ptos_web._detect_notify_platform() == "termux"

    def test_termux_detection_via_path(self, monkeypatch):
        monkeypatch.setattr("os.environ", {})
        monkeypatch.setattr("os.path.exists", lambda p: p == "/data/data/com.termux")
        assert ptos_web._detect_notify_platform() == "termux"

    def test_unknown_platform_returns_none(self, monkeypatch):
        monkeypatch.setattr("os.environ", {})
        monkeypatch.setattr("os.path.exists", lambda p: False)
        import platform as _platform
        monkeypatch.setattr(_platform, "system", lambda: "FreeBSD")
        assert ptos_web._detect_notify_platform() is None


class TestSystemNotify:
    def test_noop_on_unknown_platform(self, monkeypatch):
        monkeypatch.setattr(ptos_web, "_notify_platform", None)
        ptos_web._system_notify("title", "body")

    def test_calls_subprocess_on_linux(self, monkeypatch):
        called = []
        def fake_run(cmd, **kw):
            called.append(cmd)
            return type("R", (), {"returncode": 0})()
        monkeypatch.setattr(ptos_web, "_notify_platform", "linux")
        monkeypatch.setattr(ptos_web.subprocess, "run", fake_run)
        ptos_web._system_notify("title", "body")
        assert called[0] == ["notify-send", "title", "body"]

    def test_exception_does_not_propagate(self, monkeypatch):
        def boom(*a, **kw):
            raise OSError("no notify")
        monkeypatch.setattr(ptos_web, "_notify_platform", "linux")
        monkeypatch.setattr(ptos_web.subprocess, "run", boom)
        ptos_web._system_notify("title", "body")

    def test_windows_tries_modern_toast(self, monkeypatch):
        calls = []
        def fake_run(cmd, **kw):
            calls.append(cmd)
            return type("R", (), {"returncode": 0, "stdout": "", "stderr": ""})()
        monkeypatch.setattr(ptos_web, "_notify_platform", "windows")
        monkeypatch.setattr(ptos_web.subprocess, "run", fake_run)
        ptos_web._system_notify("title", "body")
        assert len(calls) >= 1
        assert calls[0][0] == "powershell"


class TestArrivedField:
    def _write_todo(self, line):
        todo_dir = os.path.dirname(ptos.TODO_PATH)
        os.makedirs(todo_dir, exist_ok=True)
        with open(ptos.TODO_PATH, "w") as f:
            f.write(line + "\n")
        return ptos.TODO_PATH

    def test_arrived_true_for_past_due_time(self):
        self._write_todo("past task due:2026-07-18 due_time:09:00")
        todos, _ = todo_mod.load_todos(ptos.TODO_PATH)
        due = todo_mod.get_due_todos(todos, lookahead_days=1)
        assert len(due) == 1
        t = due[0]
        assert t.due_time is not None
        import datetime as _dt
        due_dt = _dt.datetime.combine(t.due, _dt.time.fromisoformat(t.due_time))
        arrived = due_dt <= _dt.datetime.now()
        assert arrived is True

    def test_arrived_false_for_future_due_time(self):
        self._write_todo("future task due:2099-12-31 due_time:23:59")
        todos, _ = todo_mod.load_todos(ptos.TODO_PATH)
        due = todo_mod.get_due_todos(todos, lookahead_days=36500)
        assert len(due) == 1
        t = due[0]
        assert t.due_time is not None
        import datetime as _dt
        due_dt = _dt.datetime.combine(t.due, _dt.time.fromisoformat(t.due_time))
        arrived = due_dt <= _dt.datetime.now()
        assert arrived is False

    def test_arrived_false_for_no_due_time(self):
        self._write_todo("date-only task due:2026-07-18")
        todos, _ = todo_mod.load_todos(ptos.TODO_PATH)
        due = todo_mod.get_due_todos(todos, lookahead_days=1)
        assert len(due) == 1
        t = due[0]
        assert t.due_time is None

    def test_arrived_field_in_sse_payload(self):
        import datetime as _dt
        today = _dt.date.today()
        tasks = [{"line_no": 1, "description": "task", "priority": "A",
                  "due": str(today), "due_time": "09:00", "arrived": True}]
        assert tasks[0]["arrived"] is True
        assert tasks[0]["due_time"] == "09:00"


class TestTodayOnlyFilter:
    def _write_todo(self, line):
        todo_dir = os.path.dirname(ptos.TODO_PATH)
        os.makedirs(todo_dir, exist_ok=True)
        with open(ptos.TODO_PATH, "w") as f:
            f.write(line + "\n")
        return ptos.TODO_PATH

    def test_tomorrow_excluded(self):
        import datetime as _dt
        tomorrow = _dt.date.today() + _dt.timedelta(days=1)
        self._write_todo(f"tomorrow task due:{tomorrow.isoformat()}")
        todos, _ = todo_mod.load_todos(ptos.TODO_PATH)
        due = todo_mod.get_due_todos(todos, lookahead_days=1)
        today = _dt.date.today()
        due_today = [t for t in due if t.due == today]
        assert len(due_today) == 0

    def test_today_included(self):
        import datetime as _dt
        today = _dt.date.today()
        self._write_todo(f"today task due:{today}")
        todos, _ = todo_mod.load_todos(ptos.TODO_PATH)
        due = todo_mod.get_due_todos(todos, lookahead_days=1)
        due_today = [t for t in due if t.due == today]
        assert len(due_today) == 1

    def test_time_based_today_still_surfaces(self):
        import datetime as _dt
        today = _dt.date.today()
        self._write_todo(f"timed task due:{today} 15:00")
        todos, _ = todo_mod.load_todos(ptos.TODO_PATH)
        due = todo_mod.get_due_todos(todos, lookahead_days=1)
        due_today = [t for t in due if t.due == today]
        assert len(due_today) == 1

    def test_nothing_today_only_tomorrow(self):
        import datetime as _dt
        tomorrow = _dt.date.today() + _dt.timedelta(days=1)
        self._write_todo(f"only tomorrow due:{tomorrow.isoformat()}")
        todos, _ = todo_mod.load_todos(ptos.TODO_PATH)
        due = todo_mod.get_due_todos(todos, lookahead_days=1)
        today = _dt.date.today()
        due_today = [t for t in due if t.due == today]
        assert len(due_today) == 0
