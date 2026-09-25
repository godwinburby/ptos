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


class TestHousekeepingCheck:
    def _write_todo(self, lines):
        todo_dir = os.path.dirname(ptos.TODO_PATH)
        os.makedirs(todo_dir, exist_ok=True)
        with open(ptos.TODO_PATH, "w", encoding="utf-8") as f:
            f.write(lines)
        return ptos.TODO_PATH

    def _check(self, monkeypatch, **kwargs):
        monkeypatch.setattr(ptos_web.svc, "TODO_PATH", ptos.TODO_PATH)
        return ptos_web._housekeeping_check(set(), **kwargs)

    def test_excludes_routines_by_default(self, monkeypatch):
        today = dt.date.today().isoformat()
        self._write_todo(
            "task A due:%s\n"
            "water plants +routine rec:1w due:%s\n" % (today, today)
        )
        current, tasks, body = self._check(monkeypatch)
        assert tasks is not None
        assert len(tasks) == 1
        assert tasks[0]["description"] == "task A"
        assert current == {(1, today, None)}

    def test_includes_routines_when_enabled(self, monkeypatch):
        today = dt.date.today().isoformat()
        self._write_todo(
            "task A due:%s\n"
            "water plants +routine rec:1w due:%s\n" % (today, today)
        )
        current, tasks, body = self._check(monkeypatch, notify_routines=True)
        assert tasks is not None
        assert len(tasks) == 2
        assert {t["description"] for t in tasks} == {"task A", "water plants"}

    def test_no_new_tasks_returns_none(self, monkeypatch):
        today = dt.date.today().isoformat()
        self._write_todo("task A due:%s\n" % today)
        first = self._check(monkeypatch)
        monkeypatch.setattr(ptos_web.svc, "TODO_PATH", ptos.TODO_PATH)
        current, tasks, body = ptos_web._housekeeping_check(first[0])
        assert tasks is None


class TestDueSoonFiltered:
    def _write_todo(self, lines):
        todo_dir = os.path.dirname(ptos.TODO_PATH)
        os.makedirs(todo_dir, exist_ok=True)
        with open(ptos.TODO_PATH, "w", encoding="utf-8") as f:
            f.write(lines)
        return ptos.TODO_PATH

    def _load(self):
        todos, _ = todo_mod.load_todos(ptos.TODO_PATH)
        return todos

    def test_excludes_routines_by_default(self):
        self._write_todo(
            "task A due:2099-12-31 due_time:14:30\n"
            "water plants +routine rec:1w due:2099-12-31 due_time:14:30\n"
        )
        todos = self._load()
        now = dt.datetime(2099, 12, 31, 14, 20)
        due_soon = ptos_web._due_soon_filtered(todos, now, remind_before=15)
        assert len(due_soon) == 1
        assert due_soon[0][0].description == "task A"

    def test_includes_routines_when_enabled(self):
        self._write_todo(
            "task A due:2099-12-31 due_time:14:30\n"
            "water plants +routine rec:1w due:2099-12-31 due_time:14:30\n"
        )
        todos = self._load()
        now = dt.datetime(2099, 12, 31, 14, 20)
        due_soon = ptos_web._due_soon_filtered(todos, now, remind_before=15, notify_routines=True)
        assert len(due_soon) == 2


class TestStartHousekeepingThread:
    def test_thread_not_started_when_interval_zero(self, monkeypatch):
        started = []
        class FakeThread:
            def __init__(self, *a, **kw):
                self.target = kw.get("target")
                self.args = kw.get("args")
            def start(self):
                started.append(self)
        monkeypatch.setattr(ptos_web.threading, "Thread", FakeThread)
        monkeypatch.setattr(ptos_web.svc, "get_config",
                            lambda: {"todo": {"notify_interval": 0}})
        result = ptos_web._start_housekeeping_thread()
        assert result is None
        assert len(started) == 0

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
                            lambda: {"todo": {"notify_interval": 5}})
        result = ptos_web._start_housekeeping_thread()
        assert result is not None
        assert len(started) == 1
        assert started[0].target == ptos_web._housekeeping_loop
        assert started[0].args == (5, False)

    def test_once_on_startup_starts_no_thread(self, monkeypatch):
        started = []
        class FakeThread:
            def __init__(self, *a, **kw):
                self.target = kw.get("target")
                self.args = kw.get("args")
            def start(self):
                started.append(self)
        monkeypatch.setattr(ptos_web.threading, "Thread", FakeThread)
        monkeypatch.setattr(ptos_web.svc, "get_config",
                            lambda: {"todo": {"notify_interval": 60,
                                              "notify_once_on_startup": True}})
        result = ptos_web._start_housekeeping_thread()
        assert result is None
        assert len(started) == 0

    def test_thread_not_started_when_config_missing(self, monkeypatch):
        started = []
        class FakeThread:
            def start(self):
                started.append(self)
        monkeypatch.setattr(ptos_web.threading, "Thread", FakeThread)
        monkeypatch.setattr(ptos_web.svc, "get_config", lambda: {})
        result = ptos_web._start_housekeeping_thread()
        assert result is None
        assert len(started) == 0


class TestSettingsSaveNotifier:
    def _save(self, data):
        from ptos_web import app
        client = app.test_client()
        return client.post("/settings/save", json=data)

    def test_notify_interval_zero_saved(self):
        resp = self._save({"notify_interval": "0"})
        assert resp.status_code == 200
        assert resp.get_json()["ok"] is True
        assert ptos.get_config()["todo"]["notify_interval"] == 0

    def test_notify_interval_negative_clamped_to_zero(self):
        resp = self._save({"notify_interval": "-5"})
        assert resp.get_json()["ok"] is True
        assert ptos.get_config()["todo"]["notify_interval"] == 0

    def test_routine_and_once_flags_saved(self):
        resp = self._save({"notify_routines": True, "notify_once_on_startup": True})
        assert resp.get_json()["ok"] is True
        cfg = ptos.get_config()["todo"]
        assert cfg["notify_routines"] is True
        assert cfg["notify_once_on_startup"] is True


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
