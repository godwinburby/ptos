import os
import datetime as dt
import tomli_w
from types import SimpleNamespace
import ptos
import ptos_cli
import ptos_service as svc
import pytest


def _write_records(lines):
    os.makedirs(ptos.RECORDS_DIR, exist_ok=True)
    with open(os.path.join(ptos.RECORDS_DIR, f"{dt.date.today().year}.log"),
              "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def _without_type(tname):
    schema = ptos.get_schema()
    allowed = [t for t in schema.get("types", {}).get("allowed", [])
               if t != tname]
    schema["types"]["allowed"] = allowed
    with open(ptos.SCHEMA_PATH, "wb") as f:
        tomli_w.dump(schema, f)
    ptos._invalidate_all()


def _clean_cache():
    ptos._CACHE.clear()


class TestCaptureService:
    def test_capture_appends_record_with_note(self):
        _clean_cache()
        result = svc.capture("Buy more domes")
        assert result["ok"] is True
        assert result["line"].startswith(dt.date.today().isoformat())
        assert "type=capture" in result["line"]
        assert result["line"].endswith("| Buy more domes")
        filepath = os.path.join(ptos.RECORDS_DIR, f"{dt.date.today().year}.log")
        assert result["filepath"] == filepath
        with open(filepath, encoding="utf-8") as f:
            content = f.read()
        assert result["line"] in content

    def test_capture_with_tag_and_links(self):
        _clean_cache()
        result = svc.capture("Follow up", tag=["inbox"], links="expense:abc123")
        assert "tag=inbox" in result["line"]
        assert "links=expense:abc123" in result["line"]

    def test_capture_with_date(self):
        _clean_cache()
        result = svc.capture("Dated capture", date="2026-01-15")
        assert result["line"].startswith("2026-01-15 ")
        assert os.path.exists(os.path.join(ptos.RECORDS_DIR, "2026.log"))

    def test_capture_empty_text_raises(self):
        _clean_cache()
        with pytest.raises(svc.PTOSError):
            svc.capture("   ")

    def test_capture_missing_type_raises(self):
        _clean_cache()
        _without_type("capture")
        with pytest.raises(svc.PTOSError):
            svc.capture("hello")

    def test_capture_invalidates_habit_cache(self):
        _clean_cache()
        svc.get_habit_data("pomodoro")
        assert any(k.startswith("habit:") for k in ptos._CACHE)
        svc.capture("hello")
        assert not any(k.startswith("habit:") for k in ptos._CACHE)


class TestCaptureCli:
    def test_run_capture_prints_line(self, capsys):
        _clean_cache()
        args = SimpleNamespace(cap=["test", "cli"], date=None, tag=None, link=None)
        ptos_cli.run_capture(args)
        out = capsys.readouterr().out
        assert "Captured:" in out
        assert "type=capture" in out
        assert "test cli" in out

    def test_run_capture_empty_exits(self):
        _clean_cache()
        args = SimpleNamespace(cap=[""], date=None, tag=None, link=None)
        with pytest.raises(SystemExit):
            ptos_cli.run_capture(args)

    def test_run_capture_date_and_link(self):
        _clean_cache()
        args = SimpleNamespace(cap=["note"], date="2026-02-01",
                               tag=["x"], link=["expense:k1"])
        ptos_cli.run_capture(args)
        filepath = os.path.join(ptos.RECORDS_DIR, "2026.log")
        with open(filepath, encoding="utf-8") as f:
            content = f.read()
        assert "2026-02-01 type=capture tag=x links=expense:k1 | note" in content

    def test_run_capture_multiple_links_exits(self):
        _clean_cache()
        args = SimpleNamespace(cap=["note"], date=None, tag=None,
                               link=["a:1", "b:2"])
        with pytest.raises(SystemExit):
            ptos_cli.run_capture(args)


class TestCaptureWeb:
    def test_api_capture_ok(self):
        _clean_cache()
        from ptos_web import app
        client = app.test_client()
        resp = client.post("/api/capture", json={"text": "web capture"})
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["ok"] is True
        assert "type=capture" in data["line"]

    def test_api_capture_empty_text_error(self):
        _clean_cache()
        from ptos_web import app
        client = app.test_client()
        resp = client.post("/api/capture", json={"text": "  "})
        data = resp.get_json()
        assert data["ok"] is False
        assert "required" in data.get("error", "").lower() or \
               "empty" in data.get("error", "").lower()