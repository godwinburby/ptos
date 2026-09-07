import os
import datetime as dt
import ptos
import ptos_cli
import ptos_service as svc


def _write_records(lines):
    os.makedirs(ptos.RECORDS_DIR, exist_ok=True)
    with open(os.path.join(ptos.RECORDS_DIR, f"{dt.date.today().year}.log"),
              "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def _write_todos(lines):
    os.makedirs(ptos.TODO_DIR, exist_ok=True)
    with open(ptos.TODO_PATH, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def _write_journal(date_obj, content):
    folder = os.path.join(ptos.JOURNAL_DIR, str(date_obj.year),
                          date_obj.strftime("%m"))
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, date_obj.strftime("%Y-%m-%d") + ".md")
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    return path


def _clean_cache():
    ptos._CACHE.clear()


class TestDigestBasics:
    def test_default_date_is_yesterday(self):
        _clean_cache()
        data = svc.daily_digest()
        assert data["date"] == (dt.date.today() - dt.timedelta(days=1)).isoformat()

    def test_explicit_date(self):
        _clean_cache()
        data = svc.daily_digest("2026-04-10")
        assert data["date"] == "2026-04-10"
        assert data["weekday"] == dt.date(2026, 4, 10).strftime("%A")

    def test_records_grouped_by_type(self):
        _clean_cache()
        yesterday = dt.date.today() - dt.timedelta(days=1)
        _write_records([
            f"{yesterday} type=expense amount=50 | lunch",
            f"{yesterday} type=expense amount=10 | coffee",
            f"{yesterday} type=capture | quick idea",
        ])
        data = svc.daily_digest()
        by = {r["type"]: r for r in data["records_by_type"]}
        assert by["expense"]["count"] == 2
        assert by["capture"]["count"] == 1
        sample_text = " ".join(by["capture"]["samples"])
        assert "quick idea" in sample_text

    def test_full_line_for_qualifying_day(self):
        _clean_cache()
        today = dt.date.today()
        _write_records([f"{today} type=capture | today idea"])
        data = svc.daily_digest(today.isoformat())
        assert data["date"] == today.isoformat()
        by = {r["type"]: r for r in data["records_by_type"]}
        assert by["capture"]["count"] == 1

    def test_no_records_empty(self):
        _clean_cache()
        data = svc.daily_digest()
        assert data["records_by_type"] == []


class TestDigestTodos:
    def test_overdue_and_due_sections(self):
        _clean_cache()
        yesterday = dt.date.today() - dt.timedelta(days=1)
        _write_todos([
            f"(A) 2026-01-01 Old task due:{yesterday - dt.timedelta(days=2)}",
            f"(B) 2026-01-01 Due task due:{yesterday}",
            f"(C) 2026-01-01 Future task due:{yesterday + dt.timedelta(days=3)}",
        ])
        data = svc.daily_digest()
        overdue_descs = [t["description"] for t in data["todos"]["overdue"]]
        due_descs = [t["description"] for t in data["todos"]["due"]]
        assert "Old task" in overdue_descs
        assert "Due task" in due_descs
        assert "Future task" not in overdue_descs
        assert "Future task" not in due_descs
        assert data["todos"]["overdue"][0]["priority"] == "A"

    def test_done_todos_excluded(self):
        _clean_cache()
        yesterday = dt.date.today() - dt.timedelta(days=1)
        _write_todos([
            f"x 2026-01-01 2026-01-01 Completed due:{yesterday}",
        ])
        data = svc.daily_digest()
        assert data["todos"]["overdue"] == []
        assert data["todos"]["due"] == []

    def test_threshold_hidden(self):
        _clean_cache()
        yesterday = dt.date.today() - dt.timedelta(days=1)
        _write_todos([
            f"(A) 2026-01-01 Hidden task due:{yesterday} t:{yesterday + dt.timedelta(days=1)}",
        ])
        data = svc.daily_digest()
        descs = ([t["description"] for t in data["todos"]["overdue"]] +
                 [t["description"] for t in data["todos"]["due"]])
        assert descs == []

    def test_no_todos_empty(self):
        _clean_cache()
        data = svc.daily_digest()
        assert data["todos"]["overdue"] == []
        assert data["todos"]["due"] == []


class TestDigestExtras:
    def test_captures_include_through_digest_date(self):
        _clean_cache()
        today = dt.date.today()
        yesterday = today - dt.timedelta(days=1)
        _write_records([
            f"{today} type=capture | today's note",
            f"{yesterday} type=capture | yesterday's note",
        ])
        data = svc.daily_digest(today.isoformat())
        notes = [c["note"] for c in data["captures"]]
        assert "yesterday's note" in notes
        assert "today's note" in notes
        assert "today's note" in data["captures"][0]["sample"]

    def test_capture_excluded_after_digest_date(self):
        _clean_cache()
        today = dt.date.today()
        yesterday = today - dt.timedelta(days=1)
        _write_records([
            f"{yesterday} type=capture | older",
            f"{today} type=capture | newer",
        ])
        data = svc.daily_digest()
        notes = [c["note"] for c in data["captures"]]
        assert "older" in notes
        assert "newer" not in notes

    def test_journal_present_when_file_exists(self):
        _clean_cache()
        yesterday = dt.date.today() - dt.timedelta(days=1)
        path = _write_journal(yesterday, "# Journal\n\nSome content here.\n")
        data = svc.daily_digest()
        assert data["journal"] is not None
        assert data["journal"]["exists"] is True
        assert data["journal"]["date"] == yesterday.isoformat()
        assert data["journal"]["path"] == path
        assert "Some content" in data["journal"]["preview"]

    def test_journal_none_when_missing(self):
        _clean_cache()
        data = svc.daily_digest()
        assert data["journal"] is None

    def test_habits_reported(self):
        _clean_cache()
        today = dt.date.today()
        _write_records([f"{today} type=pomodoro task=work minutes=25"])
        data = svc.daily_digest()
        names = [h["name"] for h in data["habits"]]
        assert "pomodoro" in names
        pomo = next(h for h in data["habits"] if h["name"] == "pomodoro")
        assert pomo["today"] is True

    def test_habits_today_false_without_record(self):
        _clean_cache()
        data = svc.daily_digest()
        pomo = next((h for h in data["habits"] if h["name"] == "pomodoro"), None)
        if pomo:
            assert pomo["today"] is False


class TestDigestCli:
    def test_run_daily_prints_sections(self, capsys):
        _clean_cache()
        yesterday = dt.date.today() - dt.timedelta(days=1)
        _write_records([f"{yesterday} type=expense amount=1 | tea"])
        ptos_cli.run_daily("yesterday")
        out = capsys.readouterr().out
        assert "Daily digest" in out
        assert "Records:" in out
        assert "Todos:" in out
        assert "Captures:" in out
        assert "Journal:" in out
        assert "Habits:" in out
        assert yesterday.isoformat() in out

    def test_run_daily_explicit_date(self, capsys):
        _clean_cache()
        ptos_cli.run_daily("2026-05-01")
        out = capsys.readouterr().out
        assert "2026-05-01" in out


class TestDigestWeb:
    def test_daily_page_renders(self):
        _clean_cache()
        from ptos_web import app
        client = app.test_client()
        resp = client.get("/daily")
        assert resp.status_code == 200
        html = resp.get_data(as_text=True)
        assert "Daily" in html
        assert "Records" in html

    def test_daily_page_with_data(self):
        _clean_cache()
        yesterday = dt.date.today() - dt.timedelta(days=1)
        _write_records([f"{yesterday} type=capture | web idea"])
        from ptos_web import app
        client = app.test_client()
        resp = client.get("/daily")
        assert resp.status_code == 200
        html = resp.get_data(as_text=True)
        assert "web idea" in html

    def test_daily_page_specific_date_nav(self):
        _clean_cache()
        from ptos_web import app
        client = app.test_client()
        resp = client.get("/daily/2026-06-15")
        assert resp.status_code == 200
        html = resp.get_data(as_text=True)
        assert "2026-06-15" in html