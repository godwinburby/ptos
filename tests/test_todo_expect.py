"""
tests/test_todo_expect.py  -  Stale-line guard (expect) for todo actions, spec 4.4
"""

import json, os, pytest
import ptos
import ptos_todo
import ptos_service as svc
from ptos_web import app


def _write_todo(lines, done=None):
    todo_path = os.path.join(ptos.TODO_DIR, "todo.txt")
    os.makedirs(ptos.TODO_DIR, exist_ok=True)
    with open(todo_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    done_path = os.path.join(ptos.TODO_DIR, "done.txt")
    if done is not None:
        with open(done_path, "w", encoding="utf-8") as f:
            f.write("\n".join(done) + "\n")
    return todo_path, done_path


def _paths(tmp_path, monkeypatch):
    todo_dir = str(tmp_path / "todo")
    monkeypatch.setattr(ptos, "TODO_DIR", todo_dir)
    monkeypatch.setattr(ptos, "TODO_PATH", str(tmp_path / "todo" / "todo.txt"))
    monkeypatch.setattr(ptos, "DONE_PATH", str(tmp_path / "todo" / "done.txt"))
    monkeypatch.setattr(ptos_todo, "TODO_PATH", str(tmp_path / "todo" / "todo.txt"))
    monkeypatch.setattr(ptos_todo, "DONE_PATH", str(tmp_path / "todo" / "done.txt"))


L1 = "(A) 2026-01-05 alpha +p1"
L2 = "(B) 2026-01-06 beta +p2"


class TestExpectGuardService:
    def test_complete_with_matching_expect(self, tmp_path, monkeypatch):
        _paths(tmp_path, monkeypatch)
        _write_todo([L1, L2])
        resp = svc.complete_todo_by_line(1, expect=L1)
        assert resp["ok"] is True
        assert resp["done_line_no"] >= 1
        assert resp["done_raw"] in (L1, L1 + " x:") or "alpha" in resp["done_raw"]

    def test_complete_with_stale_expect_refused(self, tmp_path, monkeypatch):
        _paths(tmp_path, monkeypatch)
        _write_todo([L1, L2])
        with pytest.raises(svc.PTOSError, match="refresh"):
            svc.complete_todo_by_line(1, expect="(A) 2026-01-05 something else")
        todos, _ = ptos_todo.load_todos(ptos.TODO_PATH)
        assert len(todos) == 2
        done, _ = ptos_todo.load_todos(ptos.DONE_PATH)
        assert done == []

    def test_complete_without_expect_backward_compatible(self, tmp_path, monkeypatch):
        _paths(tmp_path, monkeypatch)
        _write_todo([L1, L2])
        resp = svc.complete_todo_by_line(1)
        assert resp["ok"] is True
        todos, _ = ptos_todo.load_todos(ptos.TODO_PATH)
        assert len(todos) == 1

    def test_shifted_line_numbers_detected(self, tmp_path, monkeypatch):
        _paths(tmp_path, monkeypatch)
        _write_todo([L1, L2])
        first = svc.complete_todo_by_line(1, expect=L1)
        assert first["ok"] is True
        with pytest.raises(svc.PTOSError, match="refresh"):
            svc.complete_todo_by_line(1, expect=L1)

    def test_undo_round_trip_with_done_expect(self, tmp_path, monkeypatch):
        _paths(tmp_path, monkeypatch)
        _write_todo([L1])
        resp = svc.complete_todo_by_line(1, expect=L1)
        svc.undo_todo_by_line(resp["done_line_no"], expect=resp["done_raw"])
        todos, _ = ptos_todo.load_todos(ptos.TODO_PATH)
        assert len(todos) == 1

    def test_undo_with_stale_expect_refused(self, tmp_path, monkeypatch):
        _paths(tmp_path, monkeypatch)
        _write_todo([L1], done=["x 2026-01-06 2026-01-05 alpha +p1"])
        done, _ = ptos_todo.load_todos(ptos.DONE_PATH)
        with pytest.raises(svc.PTOSError, match="refresh"):
            svc.undo_todo_by_line(done[0].line_no, expect="x 2026-01-06 2026-01-05 beta +p2")

    def test_delete_with_stale_expect_refused(self, tmp_path, monkeypatch):
        _paths(tmp_path, monkeypatch)
        _write_todo([L1, L2])
        with pytest.raises(svc.PTOSError, match="refresh"):
            svc.delete_todo_by_line(2, expect=L1)
        todos, _ = ptos_todo.load_todos(ptos.TODO_PATH)
        assert len(todos) == 2

    def test_delete_with_matching_expect(self, tmp_path, monkeypatch):
        _paths(tmp_path, monkeypatch)
        _write_todo([L1, L2])
        svc.delete_todo_by_line(2, expect=L2)
        todos, _ = ptos_todo.load_todos(ptos.TODO_PATH)
        assert [t.raw_line for t in todos] == [L1]

    def test_edit_with_stale_expect_refused(self, tmp_path, monkeypatch):
        _paths(tmp_path, monkeypatch)
        _write_todo([L1, L2])
        with pytest.raises(svc.PTOSError, match="refresh"):
            svc.edit_todo_by_line(1, {"description": "changed"}, expect=L2)
        todos, _ = ptos_todo.load_todos(ptos.TODO_PATH)
        assert todos[0].description == "alpha"

    def test_bulk_with_string_keyed_expects(self, tmp_path, monkeypatch):
        _paths(tmp_path, monkeypatch)
        _write_todo([L1, L2])
        svc.bulk_edit_todos([1, 2], {"priority": "C"},
                            expects={"1": L1, "2": L2})
        todos, _ = ptos_todo.load_todos(ptos.TODO_PATH)
        assert all(t.priority == "C" for t in todos)

    def test_bulk_one_stale_refuses_whole_batch(self, tmp_path, monkeypatch):
        _paths(tmp_path, monkeypatch)
        _write_todo([L1, L2])
        with pytest.raises(svc.PTOSError, match="refresh"):
            svc.bulk_edit_todos([1, 2], {"priority": "C"},
                                expects={"1": L1, "2": "stale line"})
        todos, _ = ptos_todo.load_todos(ptos.TODO_PATH)
        assert all(t.priority in ("A", "B", None) for t in todos)

    def test_done_edit_with_expect(self, tmp_path, monkeypatch):
        _paths(tmp_path, monkeypatch)
        done_raw = "x 2026-01-06 2026-01-05 alpha +p1"
        _write_todo([], done=[done_raw])
        with pytest.raises(svc.PTOSError, match="refresh"):
            svc.edit_done_todo_by_line(1, {"description": "nope"}, expect="stale")
        svc.edit_done_todo_by_line(1, {"description": "yes"}, expect=done_raw)
        done, _ = ptos_todo.load_todos(ptos.DONE_PATH)
        assert done[0].description == "yes"

    def test_done_delete_with_expect(self, tmp_path, monkeypatch):
        _paths(tmp_path, monkeypatch)
        done_raw = "x 2026-01-06 2026-01-05 alpha +p1"
        _write_todo([], done=[done_raw])
        with pytest.raises(svc.PTOSError, match="refresh"):
            svc.delete_done_todo_by_line(1, expect="stale")
        svc.delete_done_todo_by_line(1, expect=done_raw)
        done, _ = ptos_todo.load_todos(ptos.DONE_PATH)
        assert done == []


class TestExpectGuardEndpoints:
    def _client(self, tmp_path, monkeypatch):
        _paths(tmp_path, monkeypatch)
        _write_todo([L1, L2])
        return app.test_client()

    def test_complete_endpoint_sends_stale_error(self, tmp_path, monkeypatch):
        c = self._client(tmp_path, monkeypatch)
        resp = c.post("/todo/complete", json={"line_no": 1, "expect": "stale"})
        d = resp.get_json()
        assert d["ok"] is False
        assert "refresh" in d["error"]

    def test_complete_endpoint_without_expect_still_works(self, tmp_path, monkeypatch):
        c = self._client(tmp_path, monkeypatch)
        resp = c.post("/todo/complete", json={"line_no": 1})
        assert resp.get_json()["ok"] is True

    def test_complete_endpoint_returns_done_identity(self, tmp_path, monkeypatch):
        c = self._client(tmp_path, monkeypatch)
        resp = c.post("/todo/complete", json={"line_no": 1, "expect": L1})
        d = resp.get_json()
        assert d["ok"] is True
        assert d["done_line_no"] >= 1 and d["done_raw"]

    def test_edit_endpoint_stale(self, tmp_path, monkeypatch):
        c = self._client(tmp_path, monkeypatch)
        d = c.post("/todo/edit", json={
            "line_no": 1, "updates": {"description": "x"}, "expect": L2
        }).get_json()
        assert d["ok"] is False and "refresh" in d["error"]

    def test_delete_endpoint_stale_keeps_file(self, tmp_path, monkeypatch):
        c = self._client(tmp_path, monkeypatch)
        d = c.post("/todo/delete", json={"line_no": 1, "expect": L2}).get_json()
        assert d["ok"] is False
        todos, _ = ptos_todo.load_todos(ptos.TODO_PATH)
        assert len(todos) == 2

    def test_bulk_endpoint_expects(self, tmp_path, monkeypatch):
        c = self._client(tmp_path, monkeypatch)
        d = c.post("/todo/bulk-edit", json={
            "line_nos": [1, 2], "updates": {"priority": "D"},
            "expects": {"1": L1, "2": L2},
        }).get_json()
        assert d["ok"] is True
        d2 = c.post("/todo/bulk-edit", json={
            "line_nos": [1, 2], "updates": {"priority": "D"},
            "expects": {"1": L1, "2": "stale"},
        }).get_json()
        assert d2["ok"] is False

    def test_undo_endpoint_stale(self, tmp_path, monkeypatch):
        c = self._client(tmp_path, monkeypatch)
        c.post("/todo/complete", json={"line_no": 1, "expect": L1})
        d = c.post("/todo/undo", json={"line_no": 1, "expect": "stale"}).get_json()
        assert d["ok"] is False and "refresh" in d["error"]

    def test_done_endpoints_stale(self, tmp_path, monkeypatch):
        c = self._client(tmp_path, monkeypatch)
        c.post("/todo/complete", json={"line_no": 1, "expect": L1})
        d = c.post("/todo/delete-done", json={"line_no": 1, "expect": "stale"}).get_json()
        assert d["ok"] is False
        d2 = c.post("/todo/edit-done", json={
            "line_no": 1, "updates": {"description": "z"}, "expect": "stale",
        }).get_json()
        assert d2["ok"] is False
