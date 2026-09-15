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


def _clean_cache():
    ptos._CACHE.clear()


# ── §1: Classification ──

class TestClassifyPaste:
    def test_empty_exits(self):
        with pytest.raises(SystemExit):
            ptos.classify_paste("")

    def test_multiline_exits(self):
        with pytest.raises(SystemExit, match="multi-line"):
            ptos.classify_paste("line1\nline2")

    def test_valid_line_is_kind_a(self):
        _clean_cache()
        kind, detail = ptos.classify_paste(
            f"{dt.date.today()} type=expense amount=100 tag=food | lunch")
        assert kind == "line"
        d, kv, note = detail
        assert kv["type"] == "expense"
        assert kv["amount"] == "100"

    def test_free_text_is_kind_b(self):
        kind, detail = ptos.classify_paste("lunch at cafe rs200")
        assert kind == "freeform"
        assert detail == "lunch at cafe rs200"

    def test_line_shaped_with_date_is_kind_a(self):
        kind, detail = ptos.classify_paste(
            f"{dt.date.today()} type=expense amount=abc")
        assert kind == "line"
        d, kv, note = detail
        assert kv["type"] == "expense"

    def test_freeform_no_date_is_kind_b(self):
        kind, detail = ptos.classify_paste("type=expense amount=abc")
        assert kind == "freeform"

    def test_type_with_date_is_kind_a(self):
        kind, detail = ptos.classify_paste(
            f"{dt.date.today()} type=capture | quick note")
        assert kind == "line"

    def test_type_without_date_is_kind_b(self):
        kind, detail = ptos.classify_paste("type=capture | quick note")
        assert kind == "freeform"


# ── §2: Kind A — validate and append ──

class TestValidateAndAppendLine:
    def test_valid_line_appends(self):
        _clean_cache()
        result = ptos.validate_and_append_line(
            _raw=f"{dt.date.today()} type=expense domain=self category=food amount=50 tag=food | tea")
        assert result["ok"] is True
        assert "type=expense" in result["line"]
        assert result["filepath"].endswith(".log")

    def test_valid_line_with_custom_date(self):
        _clean_cache()
        result = ptos.validate_and_append_line(
            date_override="2025-01-15",
            _raw=f"{dt.date.today()} type=expense domain=self category=food amount=50 | tea")
        assert result["ok"] is True
        assert result["line"].startswith("2025-01-15")

    def test_missing_required_field_rejects(self):
        _clean_cache()
        result = ptos.validate_and_append_line(
            _raw=f"{dt.date.today()} type=expense domain=self amount=50")
        assert result["ok"] is False
        assert any("Missing required field" in p for p in result["problems"])

    def test_invalid_type_rejects(self):
        _clean_cache()
        result = ptos.validate_and_append_line(
            _raw=f"{dt.date.today()} type=nonexistent foo=bar")
        assert result["ok"] is False
        assert any("Invalid type" in p for p in result["problems"])

    def test_dry_run_does_not_write(self):
        _clean_cache()
        result = ptos.validate_and_append_line(
            dry_run=True,
            _raw=f"{dt.date.today()} type=expense domain=self category=food amount=50 | tea")
        assert result["ok"] is True
        assert result.get("dry_run") is True
        assert "type=expense" in result["line"]
        log_path = os.path.join(ptos.RECORDS_DIR, f"{dt.date.today().year}.log")
        assert not os.path.exists(log_path)


# ── §4: capture() validates ──

class TestCaptureValidation:
    def test_capture_validates(self):
        _clean_cache()
        result = svc.capture("text")
        assert result["ok"] is True
        assert "type=capture" in result["line"]

    def test_capture_empty_exits(self):
        with pytest.raises(Exception):
            svc.capture("")

    def test_capture_missing_type_exits(self):
        _clean_cache()
        schema = ptos.get_schema()
        allowed = [t for t in schema.get("types", {}).get("allowed", [])
                   if t != "capture"]
        schema["types"]["allowed"] = allowed
        with open(ptos.SCHEMA_PATH, "wb") as f:
            tomli_w.dump(schema, f)
        ptos._invalidate_all()
        with pytest.raises(Exception, match="capture"):
            svc.capture("some text")


# ── §3: Kind B — paste_to_record capture + suggestions ──

class TestPasteToRecordKindB:
    def test_free_text_writes_capture(self):
        _clean_cache()
        result = svc.paste_to_record("lunch at cafe rs200")
        assert result["kind"] == "capture"
        assert result["ok"] is True
        assert result["filepath"].endswith(".log")
        with open(result["filepath"], encoding="utf-8") as f:
            lines = f.readlines()
        assert result["lineno"] < len(lines)
        assert "type=capture" in lines[result["lineno"]]

    def test_free_text_no_structured_record(self):
        _clean_cache()
        result = svc.paste_to_record("some random text here")
        assert result["kind"] == "capture"
        with open(result["filepath"], encoding="utf-8") as f:
            lines = f.readlines()
        assert "type=capture" in lines[result["lineno"]]

    def test_suggestions_match_independent_output(self):
        _clean_cache()
        independent = svc.suggest_convert_type("lunch at cafe rs200")
        result = svc.paste_to_record("lunch at cafe rs200")
        if independent:
            assert result["suggested_type"] == independent[0]["type"]
        else:
            assert result["suggested_type"] is None

    def test_dry_run_does_not_write(self):
        _clean_cache()
        result = svc.paste_to_record("lunch at cafe rs200", dry_run=True)
        assert result["dry_run"] is True
        assert result["kind"] == "freeform"
        log_path = os.path.join(ptos.RECORDS_DIR, f"{dt.date.today().year}.log")
        assert not os.path.exists(log_path)

    def test_review_url_present(self):
        _clean_cache()
        result = svc.paste_to_record("rs200 auto to clinic")
        if result.get("suggested_type"):
            assert "review_url" in result
            assert "convert=1" in result["review_url"]


# ── §6: Kind A in paste_to_record ──

class TestPasteToRecordKindA:
    def test_valid_line_appends_directly(self):
        _clean_cache()
        result = svc.paste_to_record(
            f"{dt.date.today()} type=expense domain=self category=food amount=100 tag=food | lunch")
        assert result["kind"] == "line"
        assert result["ok"] is True
        assert "type=expense" in result["line"]

    def test_invalid_line_rejects(self):
        _clean_cache()
        result = svc.paste_to_record(
            f"{dt.date.today()} type=nonexistent foo=bar")
        assert result["kind"] == "line"
        assert result["ok"] is False
        assert len(result["problems"]) > 0

    def test_dry_run_line_no_write(self):
        _clean_cache()
        result = svc.paste_to_record(
            f"{dt.date.today()} type=expense domain=self category=food amount=50 | tea", dry_run=True)
        assert result["kind"] == "line"
        assert result["ok"] is True
        assert result.get("dry_run") is True
        log_path = os.path.join(ptos.RECORDS_DIR, f"{dt.date.today().year}.log")
        assert not os.path.exists(log_path)


# ── §7: Multi-line rejection ──

class TestPasteMultiLine:
    def test_multiline_exits(self):
        with pytest.raises(SystemExit):
            ptos.classify_paste("line1\nline2\nline3")


# ── CLI tests ──

class TestPasteCli:
    def test_paste_kind_a_valid(self, capsys):
        _clean_cache()
        args = SimpleNamespace(
            paste=f"{dt.date.today()} type=expense domain=self category=food amount=50 tag=food | tea",
            date=None, dry_run=False)
        ptos_cli.run_paste(args)
        out = capsys.readouterr().out
        assert "Added:" in out

    def test_paste_kind_a_invalid(self, capsys):
        _clean_cache()
        args = SimpleNamespace(
            paste=f"{dt.date.today()} type=nonexistent foo=bar",
            date=None, dry_run=False)
        with pytest.raises(SystemExit):
            ptos_cli.run_paste(args)

    def test_paste_kind_b_writes_capture(self, capsys):
        _clean_cache()
        args = SimpleNamespace(
            paste="lunch at cafe rs200",
            date=None, dry_run=False)
        ptos_cli.run_paste(args)
        out = capsys.readouterr().out
        assert "Captured:" in out

    def test_paste_dry_run_kind_a(self, capsys):
        _clean_cache()
        args = SimpleNamespace(
            paste=f"{dt.date.today()} type=expense domain=self category=food amount=50 | tea",
            date=None, dry_run=True)
        ptos_cli.run_paste(args)
        out = capsys.readouterr().out
        assert "dry-run" in out
        log_path = os.path.join(ptos.RECORDS_DIR, f"{dt.date.today().year}.log")
        assert not os.path.exists(log_path)

    def test_paste_dry_run_kind_b(self, capsys):
        _clean_cache()
        args = SimpleNamespace(
            paste="lunch at cafe",
            date=None, dry_run=True)
        ptos_cli.run_paste(args)
        out = capsys.readouterr().out
        assert "dry-run" in out
        log_path = os.path.join(ptos.RECORDS_DIR, f"{dt.date.today().year}.log")
        assert not os.path.exists(log_path)

    def test_paste_no_input_exits(self):
        args = SimpleNamespace(paste=None, date=None, dry_run=False)
        with pytest.raises(SystemExit):
            ptos_cli.run_paste(args)


# ── Web API tests ──

class TestPasteWeb:
    def test_api_paste_kind_a_valid(self):
        _clean_cache()
        from ptos_web import app
        client = app.test_client()
        resp = client.post("/api/paste",
                           json={"text": f"{dt.date.today()} type=expense domain=self category=food amount=50 | tea"})
        data = resp.get_json()
        assert data["kind"] == "line"
        assert data["ok"] is True
        assert "type=expense" in data["line"]

    def test_api_paste_kind_a_invalid(self):
        _clean_cache()
        from ptos_web import app
        client = app.test_client()
        resp = client.post("/api/paste",
                           json={"text": f"{dt.date.today()} type=nonexistent foo=bar"})
        data = resp.get_json()
        assert data["kind"] == "line"
        assert data["ok"] is False
        assert len(data["problems"]) > 0

    def test_api_paste_kind_b(self):
        _clean_cache()
        from ptos_web import app
        client = app.test_client()
        resp = client.post("/api/paste", json={"text": "lunch at cafe rs200"})
        data = resp.get_json()
        assert data["kind"] == "capture"
        assert data["ok"] is True
        assert "review_url" in data

    def test_api_paste_empty_text(self):
        from ptos_web import app
        client = app.test_client()
        resp = client.post("/api/paste", json={"text": ""})
        data = resp.get_json()
        assert data["ok"] is False

    def test_api_paste_text_plain(self):
        _clean_cache()
        from ptos_web import app
        client = app.test_client()
        resp = client.post("/api/paste",
                           data=f"{dt.date.today()} type=expense domain=self category=food amount=50 | tea",
                           content_type="text/plain")
        data = resp.get_json()
        assert data["kind"] == "line"
        assert data["ok"] is True
