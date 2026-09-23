"""
tests/test_routines.py  —  Tests for the routines view (checkbox cards over +routine todos)
"""

import datetime as dt, os, pytest
import ptos
import ptos_todo
import ptos_service as svc
import ptos_web
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

    def test_unknown_context_dropped_from_cards(self, tmp_path, monkeypatch):
        todo_path = tmp_path / "todo" / "todo.txt"
        monkeypatch.setattr(ptos, "TODO_PATH", str(todo_path))
        monkeypatch.setattr(ptos_todo, "TODO_PATH", str(todo_path))
        monkeypatch.setattr(svc, "TODO_PATH", str(todo_path))
        _write_todo(todo_path, [
            f"(A) {TODAY_S} Custom ctx +routine @workout due:{TODAY_S}",
        ])
        client = app.test_client()
        resp = client.get("/routines")
        html = resp.get_data(as_text=True)
        cards_html = html.split('id="view-cards"')[1].split('id="view-day"')[0]
        assert "workout" not in cards_html.lower()

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


class TestRoutinesTimeView:
    def test_now_time_passed_to_template(self, tmp_path, monkeypatch):
        todo_path = tmp_path / "todo" / "todo.txt"
        monkeypatch.setattr(ptos, "TODO_PATH", str(todo_path))
        monkeypatch.setattr(ptos_todo, "TODO_PATH", str(todo_path))
        monkeypatch.setattr(svc, "TODO_PATH", str(todo_path))
        _write_todo(todo_path, [
            f"(A) {TODAY_S} Wake up +routine @morning due:{TODAY_S} due_time:06:00",
        ])
        client = app.test_client()
        resp = client.get("/routines")
        html = resp.get_data(as_text=True)
        assert resp.status_code == 200
        assert "_nowTime" in html

    def test_due_time_shown_in_row(self, tmp_path, monkeypatch):
        todo_path = tmp_path / "todo" / "todo.txt"
        monkeypatch.setattr(ptos, "TODO_PATH", str(todo_path))
        monkeypatch.setattr(ptos_todo, "TODO_PATH", str(todo_path))
        monkeypatch.setattr(svc, "TODO_PATH", str(todo_path))
        _write_todo(todo_path, [
            f"(A) {TODAY_S} Wake up +routine @morning due:{TODAY_S} due_time:06:00",
            f"(B) {TODAY_S} Check mail +routine @morning due:{TODAY_S} due_time:09:00",
        ])
        client = app.test_client()
        resp = client.get("/routines")
        html = resp.get_data(as_text=True)
        assert "06:00" in html
        assert "09:00" in html
        assert "routine-time" in html

    def test_no_due_time_no_time_badge(self, tmp_path, monkeypatch):
        todo_path = tmp_path / "todo" / "todo.txt"
        monkeypatch.setattr(ptos, "TODO_PATH", str(todo_path))
        monkeypatch.setattr(ptos_todo, "TODO_PATH", str(todo_path))
        monkeypatch.setattr(svc, "TODO_PATH", str(todo_path))
        _write_todo(todo_path, [
            f"(A) {TODAY_S} Unsorted +routine @morning due:{TODAY_S}",
        ])
        client = app.test_client()
        resp = client.get("/routines")
        html = resp.get_data(as_text=True)
        assert '<span class="routine-time"' not in html

    def test_time_first_sort_order(self, tmp_path, monkeypatch):
        todo_path = tmp_path / "todo" / "todo.txt"
        monkeypatch.setattr(ptos, "TODO_PATH", str(todo_path))
        monkeypatch.setattr(ptos_todo, "TODO_PATH", str(todo_path))
        monkeypatch.setattr(svc, "TODO_PATH", str(todo_path))
        _write_todo(todo_path, [
            f"(A) {TODAY_S} Late task +routine @morning due:{TODAY_S} due_time:14:00",
            f"(B) {TODAY_S} Early task +routine @morning due:{TODAY_S} due_time:06:00",
            f"(C) {TODAY_S} Mid task +routine @morning due:{TODAY_S} due_time:09:00",
        ])
        client = app.test_client()
        resp = client.get("/routines")
        html = resp.get_data(as_text=True)
        early_pos = html.index("Early task")
        mid_pos = html.index("Mid task")
        late_pos = html.index("Late task")
        assert early_pos < mid_pos < late_pos

    def test_no_time_todos_after_timed(self, tmp_path, monkeypatch):
        todo_path = tmp_path / "todo" / "todo.txt"
        monkeypatch.setattr(ptos, "TODO_PATH", str(todo_path))
        monkeypatch.setattr(ptos_todo, "TODO_PATH", str(todo_path))
        monkeypatch.setattr(svc, "TODO_PATH", str(todo_path))
        _write_todo(todo_path, [
            f"(A) {TODAY_S} Timed task +routine @morning due:{TODAY_S} due_time:09:00",
            f"(B) {TODAY_S} Untimed task +routine @morning due:{TODAY_S}",
        ])
        client = app.test_client()
        resp = client.get("/routines")
        html = resp.get_data(as_text=True)
        timed_pos = html.index("Timed task")
        untimed_pos = html.index("Untimed task")
        assert timed_pos < untimed_pos

    def test_data_time_attribute_on_rows(self, tmp_path, monkeypatch):
        todo_path = tmp_path / "todo" / "todo.txt"
        monkeypatch.setattr(ptos, "TODO_PATH", str(todo_path))
        monkeypatch.setattr(ptos_todo, "TODO_PATH", str(todo_path))
        monkeypatch.setattr(svc, "TODO_PATH", str(todo_path))
        _write_todo(todo_path, [
            f"(A) {TODAY_S} Wake up +routine @morning due:{TODAY_S} due_time:06:00",
        ])
        client = app.test_client()
        resp = client.get("/routines")
        html = resp.get_data(as_text=True)
        assert 'data-time="06:00"' in html

    def test_now_line_js_present(self, tmp_path, monkeypatch):
        todo_path = tmp_path / "todo" / "todo.txt"
        monkeypatch.setattr(ptos, "TODO_PATH", str(todo_path))
        monkeypatch.setattr(ptos_todo, "TODO_PATH", str(todo_path))
        monkeypatch.setattr(svc, "TODO_PATH", str(todo_path))
        _write_todo(todo_path, [
            f"(A) {TODAY_S} Wake up +routine @morning due:{TODAY_S} due_time:06:00",
        ])
        client = app.test_client()
        resp = client.get("/routines")
        html = resp.get_data(as_text=True)
        assert "_insertNowLines" in html
        assert "routine-now" in html


class TestRoutinesDayView:
    def test_view_toggle_in_html(self, tmp_path, monkeypatch):
        todo_path = tmp_path / "todo" / "todo.txt"
        monkeypatch.setattr(ptos, "TODO_PATH", str(todo_path))
        monkeypatch.setattr(ptos_todo, "TODO_PATH", str(todo_path))
        monkeypatch.setattr(svc, "TODO_PATH", str(todo_path))
        client = app.test_client()
        resp = client.get("/routines")
        html = resp.get_data(as_text=True)
        assert 'id="view-cards"' in html
        assert 'id="view-day"' in html

    def test_view_toggle_buttons(self, tmp_path, monkeypatch):
        todo_path = tmp_path / "todo" / "todo.txt"
        monkeypatch.setattr(ptos, "TODO_PATH", str(todo_path))
        monkeypatch.setattr(ptos_todo, "TODO_PATH", str(todo_path))
        monkeypatch.setattr(svc, "TODO_PATH", str(todo_path))
        client = app.test_client()
        resp = client.get("/routines")
        html = resp.get_data(as_text=True)
        assert 'id="rv-cards"' in html
        assert 'id="rv-day"' in html
        assert "Cards" in html and "Day" in html

    def test_timed_blocks_in_timeline(self, tmp_path, monkeypatch):
        todo_path = tmp_path / "todo" / "todo.txt"
        monkeypatch.setattr(ptos, "TODO_PATH", str(todo_path))
        monkeypatch.setattr(ptos_todo, "TODO_PATH", str(todo_path))
        monkeypatch.setattr(svc, "TODO_PATH", str(todo_path))
        _write_todo(todo_path, [
            f"(A) {TODAY_S} Wake up +routine @morning due:{TODAY_S} due_time:06:00",
            f"(B) {TODAY_S} Check mail +routine @morning due:{TODAY_S} due_time:09:00",
        ])
        client = app.test_client()
        resp = client.get("/routines")
        html = resp.get_data(as_text=True)
        assert "rv-block" in html
        assert 'data-time="06:00"' in html
        assert 'data-time="09:00"' in html

    def test_untimed_in_anytime_section(self, tmp_path, monkeypatch):
        todo_path = tmp_path / "todo" / "todo.txt"
        monkeypatch.setattr(ptos, "TODO_PATH", str(todo_path))
        monkeypatch.setattr(ptos_todo, "TODO_PATH", str(todo_path))
        monkeypatch.setattr(svc, "TODO_PATH", str(todo_path))
        _write_todo(todo_path, [
            f"(A) {TODAY_S} Timed task +routine @morning due:{TODAY_S} due_time:09:00",
            f"(B) {TODAY_S} Untimed task +routine @morning due:{TODAY_S}",
        ])
        client = app.test_client()
        resp = client.get("/routines")
        html = resp.get_data(as_text=True)
        assert "rv-anytime" in html
        assert "Untimed task" in html

    def test_project_color_classes(self, tmp_path, monkeypatch):
        todo_path = tmp_path / "todo" / "todo.txt"
        monkeypatch.setattr(ptos, "TODO_PATH", str(todo_path))
        monkeypatch.setattr(ptos_todo, "TODO_PATH", str(todo_path))
        monkeypatch.setattr(svc, "TODO_PATH", str(todo_path))
        _write_todo(todo_path, [
            f"(A) {TODAY_S} Wake up +routine +gym @morning due:{TODAY_S} due_time:06:00",
            f"(B) {TODAY_S} Tidy up +routine +gym @evening due:{TODAY_S} due_time:20:00",
        ])
        client = app.test_client()
        resp = client.get("/routines")
        html = resp.get_data(as_text=True)
        assert "ctx-blue" in html or "ctx-orange" in html or "ctx-green" in html

    def test_same_project_same_color(self, tmp_path, monkeypatch):
        todo_path = tmp_path / "todo" / "todo.txt"
        monkeypatch.setattr(ptos, "TODO_PATH", str(todo_path))
        monkeypatch.setattr(ptos_todo, "TODO_PATH", str(todo_path))
        monkeypatch.setattr(svc, "TODO_PATH", str(todo_path))
        _write_todo(todo_path, [
            f"(A) {TODAY_S} Wake up +routine +gym @morning due:{TODAY_S} due_time:06:00",
            f"(B) {TODAY_S} Evening gym +routine +gym @night due:{TODAY_S} due_time:20:00",
        ])
        client = app.test_client()
        resp = client.get("/routines")
        html = resp.get_data(as_text=True)
        import re
        block_classes = re.findall(r'class="rv-block ([^"]+)"', html)
        assert block_classes
        colors = [c.split()[0] for c in block_classes]
        assert colors[0] == colors[1] != "ctx-other"

    def test_different_projects_different_colors(self, tmp_path, monkeypatch):
        todo_path = tmp_path / "todo" / "todo.txt"
        monkeypatch.setattr(ptos, "TODO_PATH", str(todo_path))
        monkeypatch.setattr(ptos_todo, "TODO_PATH", str(todo_path))
        monkeypatch.setattr(svc, "TODO_PATH", str(todo_path))
        _write_todo(todo_path, [
            f"(A) {TODAY_S} Morning gym +routine +gym @morning due:{TODAY_S} due_time:06:00",
            f"(B) {TODAY_S} Morning meal +routine +meal @morning due:{TODAY_S} due_time:08:00",
        ])
        client = app.test_client()
        resp = client.get("/routines")
        html = resp.get_data(as_text=True)
        import re
        block_classes = re.findall(r'class="rv-block ([^"]+)"', html)
        assert block_classes
        colors = [c.split()[0] for c in block_classes]
        assert colors[0] != colors[1]

    def test_no_extra_project_is_ctx_other(self, tmp_path, monkeypatch):
        todo_path = tmp_path / "todo" / "todo.txt"
        monkeypatch.setattr(ptos, "TODO_PATH", str(todo_path))
        monkeypatch.setattr(ptos_todo, "TODO_PATH", str(todo_path))
        monkeypatch.setattr(svc, "TODO_PATH", str(todo_path))
        _write_todo(todo_path, [
            f"(A) {TODAY_S} Wake up +routine @morning due:{TODAY_S} due_time:06:00",
        ])
        client = app.test_client()
        resp = client.get("/routines")
        html = resp.get_data(as_text=True)
        assert 'class="rv-block ctx-other' in html

    def test_day_view_legend(self, tmp_path, monkeypatch):
        todo_path = tmp_path / "todo" / "todo.txt"
        monkeypatch.setattr(ptos, "TODO_PATH", str(todo_path))
        monkeypatch.setattr(ptos_todo, "TODO_PATH", str(todo_path))
        monkeypatch.setattr(svc, "TODO_PATH", str(todo_path))
        _write_todo(todo_path, [
            f"(A) {TODAY_S} Morning gym +routine +gym @morning due:{TODAY_S} due_time:06:00",
            f"(B) {TODAY_S} Morning meal +routine +meal @morning due:{TODAY_S} due_time:08:00",
        ])
        client = app.test_client()
        resp = client.get("/routines")
        html = resp.get_data(as_text=True)
        assert 'class="rv-legend"' in html
        assert "gym" in html
        assert "meal" in html
        assert "other" in html

    def test_block_heights_nonzero(self, tmp_path, monkeypatch):
        todo_path = tmp_path / "todo" / "todo.txt"
        monkeypatch.setattr(ptos, "TODO_PATH", str(todo_path))
        monkeypatch.setattr(ptos_todo, "TODO_PATH", str(todo_path))
        monkeypatch.setattr(svc, "TODO_PATH", str(todo_path))
        _write_todo(todo_path, [
            f"(A) {TODAY_S} Early +routine @morning due:{TODAY_S} due_time:06:00",
            f"(B) {TODAY_S} Late +routine @morning due:{TODAY_S} due_time:09:00",
        ])
        client = app.test_client()
        resp = client.get("/routines")
        html = resp.get_data(as_text=True)
        import re
        heights = re.findall(r'height:(\d+)px', html)
        assert any(int(h) > 0 for h in heights)

    def test_now_line_in_day_view(self, tmp_path, monkeypatch):
        todo_path = tmp_path / "todo" / "todo.txt"
        monkeypatch.setattr(ptos, "TODO_PATH", str(todo_path))
        monkeypatch.setattr(ptos_todo, "TODO_PATH", str(todo_path))
        monkeypatch.setattr(svc, "TODO_PATH", str(todo_path))
        monkeypatch.setattr(ptos_web, "_now_time_str", lambda: "06:30")
        _write_todo(todo_path, [
            f"(A) {TODAY_S} Task +routine @morning due:{TODAY_S} due_time:06:00",
        ])
        client = app.test_client()
        resp = client.get("/routines")
        html = resp.get_data(as_text=True)
        assert 'id="rv-now"' in html
        assert "rv-now-label" in html

    def test_past_blocks_marked(self, tmp_path, monkeypatch):
        todo_path = tmp_path / "todo" / "todo.txt"
        monkeypatch.setattr(ptos, "TODO_PATH", str(todo_path))
        monkeypatch.setattr(ptos_todo, "TODO_PATH", str(todo_path))
        monkeypatch.setattr(svc, "TODO_PATH", str(todo_path))
        _write_todo(todo_path, [
            f"(A) {TODAY_S} Task +routine @morning due:{TODAY_S} due_time:00:01",
        ])
        client = app.test_client()
        resp = client.get("/routines")
        html = resp.get_data(as_text=True)
        assert "past" in html

    def test_hour_labels_present(self, tmp_path, monkeypatch):
        todo_path = tmp_path / "todo" / "todo.txt"
        monkeypatch.setattr(ptos, "TODO_PATH", str(todo_path))
        monkeypatch.setattr(ptos_todo, "TODO_PATH", str(todo_path))
        monkeypatch.setattr(svc, "TODO_PATH", str(todo_path))
        _write_todo(todo_path, [
            f"(A) {TODAY_S} Task +routine @morning due:{TODAY_S} due_time:09:00",
        ])
        client = app.test_client()
        resp = client.get("/routines")
        html = resp.get_data(as_text=True)
        assert "rv-hour-label" in html
        assert "9:00" in html

    def test_empty_day_view_message(self, tmp_path, monkeypatch):
        todo_path = tmp_path / "todo" / "todo.txt"
        monkeypatch.setattr(ptos, "TODO_PATH", str(todo_path))
        monkeypatch.setattr(ptos_todo, "TODO_PATH", str(todo_path))
        monkeypatch.setattr(svc, "TODO_PATH", str(todo_path))
        _write_todo(todo_path, [
            f"(A) {TODAY_S} Untimed +routine @morning due:{TODAY_S}",
        ])
        client = app.test_client()
        resp = client.get("/routines")
        html = resp.get_data(as_text=True)
        assert "No timed routines to show in day view" in html

    def test_total_height_computed(self, tmp_path, monkeypatch):
        todo_path = tmp_path / "todo" / "todo.txt"
        monkeypatch.setattr(ptos, "TODO_PATH", str(todo_path))
        monkeypatch.setattr(ptos_todo, "TODO_PATH", str(todo_path))
        monkeypatch.setattr(svc, "TODO_PATH", str(todo_path))
        _write_todo(todo_path, [
            f"(A) {TODAY_S} Task +routine @morning due:{TODAY_S} due_time:06:00",
        ])
        client = app.test_client()
        resp = client.get("/routines")
        html = resp.get_data(as_text=True)
        assert "rv-blocks" in html
        import re
        heights = re.findall(r'height:(\d+)px', html)
        assert any(int(h) >= 60 for h in heights)

    def test_timeline_trimmed_to_routine_span(self, tmp_path, monkeypatch):
        todo_path = tmp_path / "todo" / "todo.txt"
        monkeypatch.setattr(ptos, "TODO_PATH", str(todo_path))
        monkeypatch.setattr(ptos_todo, "TODO_PATH", str(todo_path))
        monkeypatch.setattr(svc, "TODO_PATH", str(todo_path))
        _write_todo(todo_path, [
            f"(A) {TODAY_S} Early +routine @morning due:{TODAY_S} due_time:06:45",
            f"(B) {TODAY_S} Late +routine @evening due:{TODAY_S} due_time:20:15",
        ])
        client = app.test_client()
        resp = client.get("/routines")
        html = resp.get_data(as_text=True)
        assert ">6:00</span>" in html
        assert ">21:00</span>" in html
        assert ">0:00</span>" not in html
        assert ">23:00</span>" not in html

    def test_now_line_hidden_out_of_range(self, tmp_path, monkeypatch):
        todo_path = tmp_path / "todo" / "todo.txt"
        monkeypatch.setattr(ptos, "TODO_PATH", str(todo_path))
        monkeypatch.setattr(ptos_todo, "TODO_PATH", str(todo_path))
        monkeypatch.setattr(svc, "TODO_PATH", str(todo_path))
        monkeypatch.setattr(ptos_web, "_now_time_str", lambda: "14:00")
        _write_todo(todo_path, [
            f"(A) {TODAY_S} Early +routine @morning due:{TODAY_S} due_time:06:00",
        ])
        client = app.test_client()
        resp = client.get("/routines")
        html = resp.get_data(as_text=True)
        assert 'id="rv-now"' not in html

    def test_single_line_is_past_without_line_through(self, tmp_path, monkeypatch):
        todo_path = tmp_path / "todo" / "todo.txt"
        monkeypatch.setattr(ptos, "TODO_PATH", str(todo_path))
        monkeypatch.setattr(ptos_todo, "TODO_PATH", str(todo_path))
        monkeypatch.setattr(svc, "TODO_PATH", str(todo_path))
        _write_todo(todo_path, [
            f"(A) {TODAY_S} Early +routine @morning due:{TODAY_S} due_time:00:01",
        ])
        client = app.test_client()
        resp = client.get("/routines")
        html = resp.get_data(as_text=True)
        assert "past" in html
        assert ".routine-item.past .routine-desc { text-decoration:line-through; }" not in html
        assert ".rv-block.past .rv-block-desc { text-decoration:line-through; }" not in html

    def test_delete_button_on_rows(self, tmp_path, monkeypatch):
        todo_path = tmp_path / "todo" / "todo.txt"
        monkeypatch.setattr(ptos, "TODO_PATH", str(todo_path))
        monkeypatch.setattr(ptos_todo, "TODO_PATH", str(todo_path))
        monkeypatch.setattr(svc, "TODO_PATH", str(todo_path))
        _write_todo(todo_path, [
            f"(A) {TODAY_S} Timed +routine @morning due:{TODAY_S} due_time:09:00",
            f"(B) {TODAY_S} Untimed +routine @morning due:{TODAY_S}",
        ])
        client = app.test_client()
        resp = client.get("/routines")
        html = resp.get_data(as_text=True)
        assert "routine-del" in html
        assert "deleteTodo(" in html

    def test_modal_delete_button_present_on_routines(self, tmp_path, monkeypatch):
        todo_path = tmp_path / "todo" / "todo.txt"
        monkeypatch.setattr(ptos, "TODO_PATH", str(todo_path))
        monkeypatch.setattr(ptos_todo, "TODO_PATH", str(todo_path))
        monkeypatch.setattr(svc, "TODO_PATH", str(todo_path))
        _write_todo(todo_path, [
            f"(A) {TODAY_S} Task +routine @morning due:{TODAY_S}",
        ])
        client = app.test_client()
        resp = client.get("/routines")
        html = resp.get_data(as_text=True)
        assert 'id="todo-modal-delete"' in html

    def test_modal_delete_button_absent_on_todo_page(self, tmp_path, monkeypatch):
        todo_path = tmp_path / "todo" / "todo.txt"
        monkeypatch.setattr(ptos, "TODO_PATH", str(todo_path))
        monkeypatch.setattr(ptos_todo, "TODO_PATH", str(todo_path))
        monkeypatch.setattr(svc, "TODO_PATH", str(todo_path))
        _write_todo(todo_path, [
            f"(A) {TODAY_S} Task +routine @morning due:{TODAY_S}",
        ])
        client = app.test_client()
        resp = client.get("/todo")
        html = resp.get_data(as_text=True)
        assert 'id="todo-modal-delete"' not in html

    def test_card_rows_colored_by_project(self, tmp_path, monkeypatch):
        todo_path = tmp_path / "todo" / "todo.txt"
        monkeypatch.setattr(ptos, "TODO_PATH", str(todo_path))
        monkeypatch.setattr(ptos_todo, "TODO_PATH", str(todo_path))
        monkeypatch.setattr(svc, "TODO_PATH", str(todo_path))
        _write_todo(todo_path, [
            f"(A) {TODAY_S} Wake up +routine +gym @morning due:{TODAY_S} due_time:06:00",
            f"(B) {TODAY_S} Evening gym +routine +gym @night due:{TODAY_S} due_time:20:00",
        ])
        client = app.test_client()
        resp = client.get("/routines")
        html = resp.get_data(as_text=True)
        import re
        row_classes = re.findall(r'class="routine-item (ctx-\w+)"', html)
        assert row_classes
        assert row_classes[0] == row_classes[1] != "ctx-other"

    def test_card_rows_different_projects_different_colors(self, tmp_path, monkeypatch):
        todo_path = tmp_path / "todo" / "todo.txt"
        monkeypatch.setattr(ptos, "TODO_PATH", str(todo_path))
        monkeypatch.setattr(ptos_todo, "TODO_PATH", str(todo_path))
        monkeypatch.setattr(svc, "TODO_PATH", str(todo_path))
        _write_todo(todo_path, [
            f"(A) {TODAY_S} Morning gym +routine +gym @morning due:{TODAY_S} due_time:06:00",
            f"(B) {TODAY_S} Morning meal +routine +meal @morning due:{TODAY_S} due_time:08:00",
        ])
        client = app.test_client()
        resp = client.get("/routines")
        html = resp.get_data(as_text=True)
        import re
        row_classes = re.findall(r'class="routine-item (ctx-\w+)"', html)
        assert row_classes
        assert row_classes[0] != row_classes[1]

    def test_anytime_rows_colored(self, tmp_path, monkeypatch):
        todo_path = tmp_path / "todo" / "todo.txt"
        monkeypatch.setattr(ptos, "TODO_PATH", str(todo_path))
        monkeypatch.setattr(ptos_todo, "TODO_PATH", str(todo_path))
        monkeypatch.setattr(svc, "TODO_PATH", str(todo_path))
        _write_todo(todo_path, [
            f"(A) {TODAY_S} Untimed gym +routine +gym @morning due:{TODAY_S}",
            f"(B) {TODAY_S} Plain untimed +routine @morning due:{TODAY_S}",
        ])
        client = app.test_client()
        resp = client.get("/routines")
        html = resp.get_data(as_text=True)
        assert 'class="routine-item ctx-blue' in html or 'class="routine-item ctx-orange' in html
        assert 'class="routine-item ctx-other' in html

    def test_done_rows_neutral(self, tmp_path, monkeypatch):
        done_path = tmp_path / "todo" / "done.txt"
        monkeypatch.setattr(ptos, "DONE_PATH", str(done_path))
        monkeypatch.setattr(ptos_todo, "DONE_PATH", str(done_path))
        monkeypatch.setattr(svc, "DONE_PATH", str(done_path))
        _write_todo(done_path, [
            f"x {TODAY_S} Completed gym +routine @morning",
        ])
        todo_path = tmp_path / "todo" / "todo.txt"
        monkeypatch.setattr(ptos, "TODO_PATH", str(todo_path))
        monkeypatch.setattr(ptos_todo, "TODO_PATH", str(todo_path))
        monkeypatch.setattr(svc, "TODO_PATH", str(todo_path))
        _write_todo(todo_path, [
            f"(A) {TODAY_S} Wake up +routine +gym @morning due:{TODAY_S} due_time:06:00",
        ])
        client = app.test_client()
        resp = client.get("/routines")
        html = resp.get_data(as_text=True)
        assert "routine-done" in html
        assert 'class="routine-item completed"' in html
        assert 'class="routine-item completed ctx-' not in html

    def test_legend_visible_in_cards_view(self, tmp_path, monkeypatch):
        todo_path = tmp_path / "todo" / "todo.txt"
        monkeypatch.setattr(ptos, "TODO_PATH", str(todo_path))
        monkeypatch.setattr(ptos_todo, "TODO_PATH", str(todo_path))
        monkeypatch.setattr(svc, "TODO_PATH", str(todo_path))
        _write_todo(todo_path, [
            f"(A) {TODAY_S} Untimed gym +routine +gym @morning due:{TODAY_S}",
        ])
        client = app.test_client()
        resp = client.get("/routines")
        html = resp.get_data(as_text=True)
        assert 'class="rv-legend"' in html
        assert "gym" in html

    def test_legend_hidden_when_no_routines(self, tmp_path, monkeypatch):
        todo_path = tmp_path / "todo" / "todo.txt"
        monkeypatch.setattr(ptos, "TODO_PATH", str(todo_path))
        monkeypatch.setattr(ptos_todo, "TODO_PATH", str(todo_path))
        monkeypatch.setattr(svc, "TODO_PATH", str(todo_path))
        _write_todo(todo_path, [
            f"(B) {TODAY_S} Non-routine todo @morning due:{TODAY_S}",
        ])
        client = app.test_client()
        resp = client.get("/routines")
        html = resp.get_data(as_text=True)
        assert "No routine todos found." in html
        assert 'class="rv-legend"' not in html
