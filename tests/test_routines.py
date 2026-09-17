"""
tests/test_routines.py  —  Tests for the routines view (checkbox cards over +routine todos)
"""

import datetime as dt, os, pytest
import ptos
import ptos_todo
import ptos_service as svc
from ptos_web import app


def _write_todo(path, lines):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


TODAY = dt.date.today()
TODAY_S = TODAY.isoformat()
YESTERDAY = (TODAY - dt.timedelta(days=1)).isoformat()
TOMORROW = (TODAY + dt.timedelta(days=1)).isoformat()


class TestRoutinesPage:
    def test_empty_shows_empty_state(self, tmp_path, monkeypatch):
        monkeypatch.setattr(ptos, "TODO_PATH", str(tmp_path / "todo" / "todo.txt"))
        monkeypatch.setattr(ptos_todo, "TODO_PATH", str(tmp_path / "todo" / "todo.txt"))
        monkeypatch.setattr(svc, "TODO_PATH", str(tmp_path / "todo" / "todo.txt"))
        client = app.test_client()
        resp = client.get("/routines")
        assert resp.status_code == 200
        html = resp.get_data(as_text=True)
        assert "No routine todos found" in html

    def test_cards_grouped_by_context(self, tmp_path, monkeypatch):
        todo_path = tmp_path / "todo" / "todo.txt"
        monkeypatch.setattr(ptos, "TODO_PATH", str(todo_path))
        monkeypatch.setattr(ptos_todo, "TODO_PATH", str(todo_path))
        monkeypatch.setattr(svc, "TODO_PATH", str(todo_path))
        _write_todo(todo_path, [
            f"(A) {TODAY_S} Check mail +routine @morning due:{TODAY_S}",
            f"(B) {TODAY_S} Call clients +routine @morning due:{TODAY_S}",
            f"(A) {TODAY_S} Tally cash card +routine @evening due:{TODAY_S}",
        ])
        client = app.test_client()
        resp = client.get("/routines")
        html = resp.get_data(as_text=True)
        assert resp.status_code == 200
        assert "morning" in html.lower()
        assert "evening" in html.lower()
        assert "Check mail" in html
        assert "Call clients" in html
        assert "Tally cash card" in html

    def test_no_context_goes_to_other(self, tmp_path, monkeypatch):
        todo_path = tmp_path / "todo" / "todo.txt"
        monkeypatch.setattr(ptos, "TODO_PATH", str(todo_path))
        monkeypatch.setattr(ptos_todo, "TODO_PATH", str(todo_path))
        monkeypatch.setattr(svc, "TODO_PATH", str(todo_path))
        _write_todo(todo_path, [
            f"{TODAY_S} Unsorted routine +routine due:{TODAY_S}",
        ])
        client = app.test_client()
        resp = client.get("/routines")
        html = resp.get_data(as_text=True)
        assert resp.status_code == 200
        assert "other" in html.lower()

    def test_only_routine_todos_shown(self, tmp_path, monkeypatch):
        todo_path = tmp_path / "todo" / "todo.txt"
        monkeypatch.setattr(ptos, "TODO_PATH", str(todo_path))
        monkeypatch.setattr(ptos_todo, "TODO_PATH", str(todo_path))
        monkeypatch.setattr(svc, "TODO_PATH", str(todo_path))
        _write_todo(todo_path, [
            f"{TODAY_S} Buy groceries +Home @errand due:{TODAY_S}",
            f"{TODAY_S} Check mail +routine @morning due:{TODAY_S}",
        ])
        client = app.test_client()
        resp = client.get("/routines")
        html = resp.get_data(as_text=True)
        assert "Check mail" in html
        assert "Buy groceries" not in html

    def test_overdue_todos_appear(self, tmp_path, monkeypatch):
        todo_path = tmp_path / "todo" / "todo.txt"
        monkeypatch.setattr(ptos, "TODO_PATH", str(todo_path))
        monkeypatch.setattr(ptos_todo, "TODO_PATH", str(todo_path))
        monkeypatch.setattr(svc, "TODO_PATH", str(todo_path))
        _write_todo(todo_path, [
            f"(A) {YESTERDAY} Overdue task +routine @morning due:{YESTERDAY}",
        ])
        client = app.test_client()
        resp = client.get("/routines")
        html = resp.get_data(as_text=True)
        assert resp.status_code == 200
        assert "Overdue task" in html

    def test_progress_bar_count(self, tmp_path, monkeypatch):
        todo_path = tmp_path / "todo.txt"
        monkeypatch.setattr(ptos, "TODO_PATH", str(todo_path))
        monkeypatch.setattr(ptos_todo, "TODO_PATH", str(todo_path))
        monkeypatch.setattr(svc, "TODO_PATH", str(todo_path))
        done_path = tmp_path / "done.txt"
        monkeypatch.setattr(ptos, "DONE_PATH", str(done_path))
        monkeypatch.setattr(ptos_todo, "DONE_PATH", str(done_path))
        monkeypatch.setattr(svc, "DONE_PATH", str(done_path))
        _write_todo(todo_path, [
            f"(A) {TODAY_S} Check mail +routine @morning due:{TODAY_S}",
            f"(B) {TODAY_S} Call clients +routine @morning due:{TODAY_S}",
        ])
        client = app.test_client()
        resp = client.get("/routines")
        html = resp.get_data(as_text=True)
        assert "2" in html

    def test_nav_entry_present(self, tmp_path, monkeypatch):
        monkeypatch.setattr(ptos, "TODO_PATH", str(tmp_path / "todo" / "todo.txt"))
        monkeypatch.setattr(ptos_todo, "TODO_PATH", str(tmp_path / "todo" / "todo.txt"))
        monkeypatch.setattr(svc, "TODO_PATH", str(tmp_path / "todo" / "todo.txt"))
        client = app.test_client()
        resp = client.get("/routines")
        html = resp.get_data(as_text=True)
        assert "/routines" in html
        assert "Routines" in html


class TestRoutinesComplete:
    def test_complete_via_existing_endpoint(self, tmp_path, monkeypatch):
        todo_path = tmp_path / "todo" / "todo.txt"
        monkeypatch.setattr(ptos, "TODO_PATH", str(todo_path))
        monkeypatch.setattr(ptos_todo, "TODO_PATH", str(todo_path))
        monkeypatch.setattr(svc, "TODO_PATH", str(todo_path))
        done_path = tmp_path / "todo" / "done.txt"
        monkeypatch.setattr(ptos, "DONE_PATH", str(done_path))
        monkeypatch.setattr(ptos_todo, "DONE_PATH", str(done_path))
        monkeypatch.setattr(svc, "DONE_PATH", str(done_path))
        _write_todo(todo_path, [
            f"(A) {TODAY_S} Check mail +routine @morning due:{TODAY_S}",
        ])
        client = app.test_client()
        resp = client.post("/todo/complete", json={"line_no": 1})
        data = resp.get_json()
        assert data["ok"] is True
        with open(todo_path) as f:
            remaining = f.read().strip()
        assert remaining == ""
        with open(done_path) as f:
            done = f.read()
        assert "Check mail" in done

    def test_undo_via_existing_endpoint(self, tmp_path, monkeypatch):
        todo_path = tmp_path / "todo" / "todo.txt"
        done_path = tmp_path / "todo" / "done.txt"
        monkeypatch.setattr(ptos, "TODO_PATH", str(todo_path))
        monkeypatch.setattr(ptos_todo, "TODO_PATH", str(todo_path))
        monkeypatch.setattr(svc, "TODO_PATH", str(todo_path))
        monkeypatch.setattr(ptos, "DONE_PATH", str(done_path))
        monkeypatch.setattr(ptos_todo, "DONE_PATH", str(done_path))
        monkeypatch.setattr(svc, "DONE_PATH", str(done_path))
        _write_todo(todo_path, [
            f"(A) {TODAY_S} Check mail +routine @morning due:{TODAY_S}",
        ])
        client = app.test_client()
        client.post("/todo/complete", json={"line_no": 1})
        resp = client.post("/todo/undo", json={"line_no": 1})
        data = resp.get_json()
        assert data["ok"] is True
        with open(todo_path) as f:
            restored = f.read()
        assert "Check mail" in restored


class TestRoutinesRecurrence:
    def test_rec1d_creates_next_day(self, tmp_path, monkeypatch):
        todo_path = tmp_path / "todo" / "todo.txt"
        done_path = tmp_path / "todo" / "done.txt"
        monkeypatch.setattr(ptos, "TODO_PATH", str(todo_path))
        monkeypatch.setattr(ptos_todo, "TODO_PATH", str(todo_path))
        monkeypatch.setattr(svc, "TODO_PATH", str(todo_path))
        monkeypatch.setattr(ptos, "DONE_PATH", str(done_path))
        monkeypatch.setattr(ptos_todo, "DONE_PATH", str(done_path))
        monkeypatch.setattr(svc, "DONE_PATH", str(done_path))
        _write_todo(todo_path, [
            f"(A) {TODAY_S} Check mail +routine @morning rec:1d due:{TODAY_S}",
        ])
        client = app.test_client()
        client.post("/todo/complete", json={"line_no": 1})
        with open(todo_path) as f:
            new_todo = f.read()
        assert "Check mail" in new_todo
        assert TOMORROW in new_todo
