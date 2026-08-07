import os
import datetime as dt
import threading
import pytest
import ptos
import ptos_web
import ptos_todo as todo_mod


class TestDueSoon:
    def _write_todo(self, lines):
        todo_dir = os.path.dirname(ptos.TODO_PATH)
        os.makedirs(todo_dir, exist_ok=True)
        with open(ptos.TODO_PATH, "w", encoding="utf-8") as f:
            f.write(lines)
        return ptos.TODO_PATH

    def _load(self):
        todos, _ = todo_mod.load_todos(ptos.TODO_PATH)
        return todos

    def test_fires_within_window(self):
        self._write_todo("task A due:2099-12-31 due_time:14:30\n")
        todos = self._load()
        now = dt.datetime(2099, 12, 31, 14, 20)
        due_soon = ptos_web._due_soon(todos, now, remind_before=15)
        assert len(due_soon) == 1
        assert due_soon[0][0].description == "task A"

    def test_not_fired_too_early(self):
        self._write_todo("task A due:2099-12-31 due_time:14:30\n")
        todos = self._load()
        now = dt.datetime(2099, 12, 31, 14, 0)
        due_soon = ptos_web._due_soon(todos, now, remind_before=15)
        assert len(due_soon) == 0

    def test_past_due_time_skipped(self):
        self._write_todo("task A due:2099-12-31 due_time:14:30\n")
        todos = self._load()
        now = dt.datetime(2099, 12, 31, 14, 31)
        due_soon = ptos_web._due_soon(todos, now, remind_before=15)
        assert len(due_soon) == 0

    def test_no_due_time_skipped(self):
        self._write_todo("task A due:2099-12-31\n")
        todos = self._load()
        now = dt.datetime(2099, 12, 31, 14, 20)
        due_soon = ptos_web._due_soon(todos, now, remind_before=15)
        assert len(due_soon) == 0

    def test_done_task_skipped(self):
        self._write_todo("x 2099-12-30 2099-12-31 task A due:2099-12-31 due_time:14:30\n")
        todos = self._load()
        now = dt.datetime(2099, 12, 31, 14, 20)
        due_soon = ptos_web._due_soon(todos, now, remind_before=15)
        assert len(due_soon) == 0

    def test_tomorrow_due_time_caught(self):
        self._write_todo("task B due:2100-01-01 due_time:00:10\n")
        todos = self._load()
        now = dt.datetime(2099, 12, 31, 23, 58)
        due_soon = ptos_web._due_soon(todos, now, remind_before=15)
        assert len(due_soon) == 1

    def test_edited_due_time_new_key(self):
        self._write_todo("task A due:2099-12-31 due_time:14:30\n")
        todos = self._load()
        t = todos[0]
        key1 = ptos_web._reminder_key(t)
        t.due_time = "15:30"
        key2 = ptos_web._reminder_key(t)
        assert key1 != key2


class TestReminderKey:
    def test_key_uses_line_due_due_time(self):
        class Fake:
            line_no = 7
            due = dt.date(2099, 12, 31)
            due_time = "14:30"
        assert ptos_web._reminder_key(Fake()) == (7, "2099-12-31", "14:30")


class TestReminderSsePayload:
    def test_broadcast_shape(self):
        import json
        import queue
        q = queue.Queue()
        with ptos_web._sse_lock:
            ptos_web._sse_clients.append(q)
        try:
            task = {"line_no": 3, "description": "call", "priority": "A",
                    "due": "2099-12-31", "due_time": "14:30", "mins_until": 12}
            ptos_web._sse_broadcast("todo-reminder", [task])
            msg = json.loads(q.get_nowait())
            assert msg["type"] == "todo-reminder"
            assert msg["data"][0] == task
            assert msg["data"][0]["mins_until"] == 12
        finally:
            with ptos_web._sse_lock:
                ptos_web._sse_clients.remove(q)

    def test_fire_task_payload_matches_shape(self):
        todo_dir = os.path.dirname(ptos.TODO_PATH)
        os.makedirs(todo_dir, exist_ok=True)
        with open(ptos.TODO_PATH, "w", encoding="utf-8") as f:
            f.write("call client due:2099-12-31 due_time:14:30\n")
        todos, _ = todo_mod.load_todos(ptos.TODO_PATH)
        now = dt.datetime(2099, 12, 31, 14, 20)
        due_soon = ptos_web._due_soon(todos, now, remind_before=15)
        t, mins_until = due_soon[0]
        task = {"line_no": t.line_no, "description": t.description, "priority": t.priority,
                "due": str(t.due), "due_time": t.due_time, "mins_until": round(mins_until)}
        assert task["line_no"] == t.line_no
        assert task["description"] == "call client"
        assert task["due_time"] == "14:30"
        assert task["mins_until"] == 10


class TestSettingsClamp:
    def test_reminder_check_interval_clamped_to_window(self):
        data = {"remind_before_minutes": "10", "reminder_check_interval": "30"}
        cfg = {}
        rb = max(0, min(120, int(data["remind_before_minutes"])))
        cfg["remind_before_minutes"] = rb
        rci = max(1, int(data["reminder_check_interval"]))
        rci = min(rci, rb)
        assert rci == 10

    def test_check_interval_smaller_window_untouched(self):
        data = {"remind_before_minutes": "15", "reminder_check_interval": "2"}
        cfg = {}
        rb = max(0, min(120, int(data["remind_before_minutes"])))
        cfg["remind_before_minutes"] = rb
        rci = max(1, int(data["reminder_check_interval"]))
        rci = min(rci, rb)
        assert rci == 2

    def test_disabled_remind_before_allows_any_interval(self):
        data = {"remind_before_minutes": "0", "reminder_check_interval": "30"}
        cfg = {}
        rb = max(0, min(120, int(data["remind_before_minutes"])))
        cfg["remind_before_minutes"] = rb
        rci = max(1, int(data["reminder_check_interval"]))
        assert rci == 30


class TestStartReminderThread:
    def test_thread_not_started_when_disabled(self, monkeypatch):
        calls = []
        def fake_thread(*a, **kw):
            calls.append(a)
            return type("T", (), {"start": lambda self: None})()
        monkeypatch.setattr(ptos_web.threading, "Thread", fake_thread)
        monkeypatch.setattr(ptos_web.svc, "get_config",
                            lambda: {"todo": {"remind_before_minutes": 0}})
        result = ptos_web._start_reminder_thread()
        assert result is None
        assert len(calls) == 0

    def test_thread_started_when_enabled(self, monkeypatch):
        started = []
        class FakeThread:
            def __init__(self, *a, **kw):
                self.target = kw.get("target")
                self.args = kw.get("args")
            def start(self):
                started.append(self)
        monkeypatch.setattr(ptos_web.threading, "Thread", FakeThread)
        monkeypatch.setattr(ptos_web.svc, "get_config",
                            lambda: {"todo": {"remind_before_minutes": 15,
                                              "reminder_check_interval": 2}})
        result = ptos_web._start_reminder_thread()
        assert result is not None
        assert len(started) == 1
        assert started[0].target == ptos_web._reminder_loop

    def test_thread_not_started_when_config_missing(self, monkeypatch):
        calls = []
        def fake_thread(*a, **kw):
            calls.append(a)
            return type("T", (), {"start": lambda self: None})()
        monkeypatch.setattr(ptos_web.threading, "Thread", fake_thread)
        monkeypatch.setattr(ptos_web.svc, "get_config", lambda: {})
        result = ptos_web._start_reminder_thread()
        assert result is None
        assert len(calls) == 0
