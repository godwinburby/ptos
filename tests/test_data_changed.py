"""Phase 2 — data-changed emission and scoped refresh (spec section 3.4).

Server: every service write path broadcasts one SSE ``data-changed`` event
with a scope ("records" | "todo" | "notes" | "config"); failed writes stay
silent; the external sweep picks up foreign todo/notes edits the engine does
not watch (records/config come from the engine's own change detection, which
already re-baselines around PTOS's own writes).

Client side is static-pinned (no JS runner): sse.js relays the event as
``ptos:data-changed``, widget_host.js debounces a scoped refresh (500 ms,
visibilitychange/pageshow, no polling), and todo.html reloads guarded against
typing focus.
"""

import os

import pytest

import ptos
import ptos_service as svc
import ptos_web
import ptos_todo

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@pytest.fixture
def client():
    ptos_web.app.config["TESTING"] = True
    return ptos_web.app.test_client()


@pytest.fixture
def broadcasts(monkeypatch):
    """Capture (event_type, data) tuples instead of queuing SSE payloads."""
    events = []
    monkeypatch.setattr(ptos_web, "_sse_broadcast",
                        lambda t, d="": events.append((t, d)))
    return events


def _scopes(events):
    return [d.get("scope") for t, d in events if t == "data-changed"]


@pytest.fixture
def scopes(monkeypatch):
    """Capture scopes emitted through the service hook (service-level tests)."""
    out = []
    monkeypatch.setattr(svc, "_DATA_CHANGED_HOOK", lambda s: out.append(s))
    return out


@pytest.fixture
def watch(monkeypatch):
    """Fresh emission-watch state + stubbed engine change detection."""
    monkeypatch.setattr(ptos_web, "_DATA_WATCH", {"sig": None, "dirty": False})
    state = {"files": []}
    monkeypatch.setattr(
        ptos, "check_external_changes",
        lambda force=False: {"checked": True,
                             "changed": bool(state["files"]),
                             "files": list(state["files"]),
                             "invalidated": 0})
    return state


class TestServiceEmission:
    def test_hook_installed_at_import(self):
        assert svc._DATA_CHANGED_HOOK is ptos_web._emit_data_changed

    def test_append_record_emits_records(self, scopes):
        line = ptos.build_record_line(ptos.today(), {"type": "capture"},
                                      note="phase two")
        svc.append_record(line)
        assert scopes == ["records"]

    def test_add_todo_emits_todo(self, scopes):
        svc.add_todo_line("data changed test task")
        assert scopes == ["todo"]

    def test_complete_and_undo_emit_todo(self, scopes):
        svc.add_todo_line("complete me for sweep test")
        todos, _ = ptos_todo.load_todos(ptos.TODO_PATH)
        svc.complete_todo_by_line(todos[0].line_no)
        done, _ = ptos_todo.load_todos(ptos.DONE_PATH)
        svc.undo_todo_by_line(done[-1].line_no)
        assert scopes == ["todo", "todo", "todo"]

    def test_delete_todo_emits_todo(self, scopes):
        svc.add_todo_line("delete me")
        scopes.clear()             # the add's own event is not the subject
        todos, _ = ptos_todo.load_todos(ptos.TODO_PATH)
        svc.delete_todo_by_line(todos[0].line_no)
        assert scopes == ["todo"]

    def test_save_config_emits_config(self, scopes):
        result = svc.save_config({"server": {"port": 5000}})
        assert result["ok"]
        assert scopes == ["config"]

    def test_queries_writer_emits_config(self, scopes):
        svc.save_query_entry("dc_phase_two", {"where": "type=capture",
                                              "time": "all"})
        assert scopes == ["config"]

    def test_capture_emits_records(self, scopes):
        svc.capture("phase two capture")
        assert scopes == ["records"]

    def test_failed_write_emits_nothing(self, scopes):
        with pytest.raises(Exception):
            svc.complete_todo_by_line(999999)
        assert scopes == []

    def test_broken_listener_never_fails_the_write(self, monkeypatch):
        def boom(scope):
            raise RuntimeError("listener exploded")
        monkeypatch.setattr(svc, "_DATA_CHANGED_HOOK", boom)
        line = ptos.build_record_line(ptos.today(), {"type": "capture"},
                                      note="still lands")
        svc.append_record(line)
        svc.add_todo_line("write survives broken listener")


class TestScopeForDataPath:
    @pytest.mark.parametrize("path,scope", [
        ("records/2026.log", "records"),
        ("records/group/2026.log", "records"),
        ("todo/todo.txt", "todo"),
        ("todo/done.2025.txt", "todo"),
        ("notes/deep/x.md", "notes"),
        ("config/queries.toml", "config"),
        ("journal/2026/01/x.md", None),
        ("x.md", None),
        ("notes/config/x.md", "notes"),
    ])
    def test_paths(self, path, scope):
        assert svc.scope_for_data_path(path) == scope

    def test_absolute_path(self):
        assert svc.scope_for_data_path(
            os.path.join("C:\\", "data", "ptos-data", "todo",
                         "todo.txt").replace("\\", "/")) == "todo"


class TestWebBroadcasts:
    def test_capture_route_broadcasts_records(self, client, broadcasts):
        resp = client.post("/api/capture", json={"text": "web scope test"})
        assert resp.status_code == 200 and resp.get_json().get("ok")
        assert _scopes(broadcasts) == ["records"]

    def test_add_and_complete_broadcast_todo(self, client, broadcasts):
        resp = client.post("/todo/add", json={"text": "web todo scope"})
        assert resp.get_json()["ok"]
        todos, _ = ptos_todo.load_todos(ptos.TODO_PATH)
        resp = client.post("/todo/complete",
                           json={"line_no": todos[0].line_no})
        assert resp.get_json()["ok"]
        assert _scopes(broadcasts) == ["todo", "todo"]

    def test_failed_todo_action_broadcasts_nothing(self, client, broadcasts):
        resp = client.post("/todo/complete", json={"line_no": 999999})
        assert resp.get_json()["ok"] is False
        assert _scopes(broadcasts) == []

    def test_note_create_broadcasts_notes(self, client, broadcasts):
        resp = client.post("/notes/new-file",
                           json={"path": "", "name": "data_changed_probe"})
        assert resp.status_code == 200 and resp.get_json().get("ok")
        assert _scopes(broadcasts) == ["notes"]

    def test_payload_shape(self, client, broadcasts):
        client.post("/api/capture", json={"text": "shape check"})
        assert broadcasts == [("data-changed", {"scope": "records"})]

    def test_stale_expect_action_broadcasts_nothing(self, client, broadcasts):
        client.post("/todo/add", json={"text": "stale guard broadcast"})
        todos, _ = ptos_todo.load_todos(ptos.TODO_PATH)
        broadcasts.clear()          # drop the add's own event
        resp = client.post("/todo/complete",
                           json={"line_no": todos[0].line_no,
                                 "expect": "not the real line"})
        assert resp.status_code in (400, 423) or resp.get_json().get("ok") is False
        assert "todo" not in _scopes(broadcasts)


class TestExternalSweep:
    def test_first_sweep_only_baselines(self, watch, monkeypatch, broadcasts):
        assert ptos_web._sweep_data_changed() == []
        assert ptos_web._DATA_WATCH["sig"] is not None

    def test_foreign_todo_file_emits_todo(self, watch, monkeypatch, broadcasts):
        ptos_web._sweep_data_changed()          # baseline
        todo_dir = os.path.join(ptos.BASE_DIR, "todo")
        os.makedirs(todo_dir, exist_ok=True)
        with open(os.path.join(todo_dir, "foreign.txt"), "w",
                  encoding="utf-8") as f:
            f.write("x 2026-01-01 synced task\n")
        assert ptos_web._sweep_data_changed() == ["todo"]
        assert _scopes(broadcasts) == ["todo"]

    def test_foreign_note_file_emits_notes(self, watch, monkeypatch, broadcasts):
        ptos_web._sweep_data_changed()
        notes_dir = os.path.join(ptos.BASE_DIR, "notes")
        os.makedirs(notes_dir, exist_ok=True)
        with open(os.path.join(notes_dir, "foreign.md"), "w",
                  encoding="utf-8") as f:
            f.write("# synced\n")
        assert ptos_web._sweep_data_changed() == ["notes"]

    def test_engine_record_change_emits_records(self, watch, monkeypatch,
                                                broadcasts):
        watch["files"] = ["records/2026.log"]
        assert ptos_web._sweep_data_changed() == ["records"]

    def test_engine_config_change_emits_config(self, watch, monkeypatch,
                                               broadcasts):
        watch["files"] = ["config/queries.toml"]
        assert ptos_web._sweep_data_changed() == ["config"]

    def test_scopes_deduplicated(self, watch, monkeypatch, broadcasts):
        watch["files"] = ["records/2025.log", "records/2026.log"]
        assert ptos_web._sweep_data_changed() == ["records"]

    def test_own_todo_write_rebaselines_silently(self, watch, monkeypatch,
                                                 broadcasts):
        svc.add_todo_line("own write before sweep")
        assert ptos_web._DATA_WATCH["dirty"] is True
        assert ptos_web._sweep_data_changed() == []
        assert _scopes(broadcasts) == ["todo"]   # only the hook's own event

    def test_journal_file_change_emits_nothing(self, watch, monkeypatch,
                                               broadcasts):
        ptos_web._sweep_data_changed()
        jdir = os.path.join(ptos.BASE_DIR, "journal")
        os.makedirs(jdir, exist_ok=True)
        with open(os.path.join(jdir, "silent.md"), "w", encoding="utf-8") as f:
            f.write("no journal scope yet\n")
        assert ptos_web._sweep_data_changed() == []
        assert _scopes(broadcasts) == []

    def test_changed_file_moved_out_of_scope_stays_silent(self, watch,
                                                           monkeypatch,
                                                           broadcasts):
        # An engine-reported path with no widget scope must not broadcast.
        watch["files"] = ["templates/x.tmpl"]
        assert ptos_web._sweep_data_changed() == []


class TestClientStaticPins:
    def _read(self, *parts):
        with open(os.path.join(REPO, *parts), encoding="utf-8") as f:
            return f.read()

    def test_sse_js_relays_data_changed(self):
        src = self._read("web_static", "js", "sse.js")
        assert '"data-changed"' in src
        assert "ptos:data-changed" in src
        assert "dispatchEvent" in src

    def test_widget_host_subscribes_and_debounces(self):
        src = self._read("web_static", "js", "widget_host.js")
        assert '"ptos:data-changed"' in src
        assert "_REFRESH_DEBOUNCE_MS = 500" in src
        assert '"visibilitychange"' in src
        assert '"pageshow"' in src
        assert '"config"' in src
        assert "_scopesForKind" in src

    def test_widget_host_never_polls(self):
        src = self._read("web_static", "js", "widget_host.js")
        assert "setInterval" not in src

    def test_widget_host_tracks_live_handles(self):
        src = self._read("web_static", "js", "widget_host.js")
        assert "_live.push(handle)" in src
        assert "_live.splice" in src
        assert "handle._phScopes" in src

    def test_todo_page_listens_for_changes(self):
        src = self._read("web_templates", "todo.html")
        assert "'ptos:data-changed'" in src
        assert "_todoScheduleReload" in src
        assert "_todoReloadArmed" in src

    def test_no_widget_script_uses_element_ids(self):
        src = self._read("web_static", "js", "widget_host.js")
        assert "getElementById" not in src
