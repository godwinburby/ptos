"""Post-save redirect behaviour for record add / edit / convert.

Browse used to be the landing spot after every save: it was the fallback in
both POST handlers *and* the Referer for edits started from a record table
there, because those links pass return_to explicitly. It now resolves to
home, while every other origin is honoured.
"""
import os
from urllib.parse import quote

import pytest

import ptos
import ptos_service as svc


_RECORD = "2026-09-05 type=capture tag=inbox | bought coffee"


@pytest.fixture(autouse=True)
def _service_paths(monkeypatch):
    """ptos_service snapshots its path constants at import time; conftest only
    redirects ptos itself, so realign them or the filepath guard in
    edit_post compares against the real data dir."""
    base = ptos.BASE_DIR
    for attr, sub in [("RECORDS_DIR", "records"), ("JOURNAL_DIR", "journal"),
                      ("TODO_DIR", "todo"), ("TODO_PATH", "todo/todo.txt"),
                      ("DONE_PATH", "todo/done.txt")]:
        if hasattr(svc, attr):
            monkeypatch.setattr(svc, attr, os.path.join(base, sub))


def _client():
    from ptos_web import app
    return app.test_client()


def _location(resp):
    return resp.headers.get("Location", "")


def _write_record(line=_RECORD, subdir=""):
    d = ptos.RECORDS_DIR
    if subdir:
        d = os.path.join(d, subdir)
    os.makedirs(d, exist_ok=True)
    path = os.path.join(d, f"{ptos.today().year}.log")
    with open(path, "a", encoding="utf-8") as f:
        f.write(line + "\n")
    return path


def _records_text():
    out = ""
    for f in sorted(os.listdir(ptos.RECORDS_DIR)):
        if f.endswith(".log"):
            with open(os.path.join(ptos.RECORDS_DIR, f), encoding="utf-8") as fh:
                out += fh.read()
    return out


def _add(client, **extra):
    data = {"type": "capture", "date": "2026-09-05", "note": "test note"}
    data.update(extra)
    return client.post("/add", data=data)


def _edit(client, path, line=_RECORD, lineno="0", **extra):
    data = {"filepath": path, "old_line": line, "lineno": lineno}
    data.update(extra)
    return client.post("/edit", data=data)


def _convert(client, path, return_to, **extra):
    """A convert that clears every required field of the target type."""
    data = {"convert": "1", "type": "expense", "domain": "self",
            "category": "food", "amount": "5", "note": "",
            "remove_original": "1", "return_to": return_to}
    data.update(extra)
    return _edit(client, path, **data)


_BROWSEISH = ["/browse", "/browse?time=ty&where=type%3Dcapture", "/browse/"]
_UNSAFE = ["//evil.com/x", "https://evil.com/x", "evil.com", ""]
_KEEP = ["/", "/board?board=job_search", "/entity?field=category&value=food",
         "/edit?filepath=x&lineno=0&line=y&convert=1"]


class TestAfterSaveTarget:
    def test_browse_resolves_to_home(self):
        from ptos_web import app, _after_save_target
        with app.test_request_context("/"):
            for raw in _BROWSEISH:
                assert _after_save_target(raw) == "/"

    def test_unsafe_resolves_to_home(self):
        from ptos_web import app, _after_save_target
        with app.test_request_context("/"):
            for raw in _UNSAFE:
                assert _after_save_target(raw) == "/"

    def test_other_origins_pass_through(self):
        from ptos_web import app, _after_save_target
        with app.test_request_context("/"):
            for raw in _KEEP:
                assert _after_save_target(raw) == raw


class TestAddRedirect:
    @pytest.mark.parametrize("raw", _BROWSEISH)
    def test_from_browse_lands_home(self, raw):
        assert _location(_add(_client(), return_to=raw)) == "/"

    def test_absent_return_to_lands_home(self):
        assert _location(_add(_client())) == "/"

    @pytest.mark.parametrize("raw", _UNSAFE)
    def test_unsafe_lands_home(self, raw):
        assert _location(_add(_client(), return_to=raw)) == "/"

    @pytest.mark.parametrize("raw", _KEEP)
    def test_other_origins_preserved(self, raw):
        assert _location(_add(_client(), return_to=raw)) == raw

    def test_record_is_still_written(self):
        r = _add(_client(), return_to="/browse")
        assert r.status_code == 302
        assert "test note" in _records_text()


class TestEditRedirect:
    def test_from_browse_lands_home(self):
        p = _write_record()
        assert _location(_edit(_client(), p, note="changed",
                               return_to="/browse")) == "/"

    def test_browse_with_query_lands_home(self):
        p = _write_record()
        r = _edit(_client(), p, note="changed", return_to="/browse?time=ty")
        assert _location(r) == "/"

    def test_absent_return_to_lands_home(self):
        p = _write_record()
        assert _location(_edit(_client(), p, note="changed")) == "/"

    @pytest.mark.parametrize("raw", _UNSAFE)
    def test_unsafe_lands_home(self, raw):
        p = _write_record()
        assert _location(_edit(_client(), p, note="changed",
                               return_to=raw)) == "/"

    @pytest.mark.parametrize("raw", _KEEP)
    def test_other_origins_preserved(self, raw):
        p = _write_record()
        assert _location(_edit(_client(), p, note="changed",
                               return_to=raw)) == raw

    def test_no_changes_lands_home(self):
        # same note + no field changes -> handler bails out early
        p = _write_record()
        r = _edit(_client(), p, note="bought coffee", return_to="/browse")
        assert _location(r) == "/"

    def test_unparseable_line_lands_home(self):
        r = _edit(_client(), "/nope.log", line="total garbage !!",
                  note="x", return_to="/browse")
        assert _location(r) == "/"

    def test_filepath_outside_records_dir_lands_home(self):
        r = _edit(_client(), os.path.join(ptos.BASE_DIR, "elsewhere.log"),
                  note="changed", return_to="/browse")
        assert _location(r) == "/"

    def test_edit_actually_applies(self):
        p = _write_record()
        _edit(_client(), p, note="changed", return_to="/browse")
        with open(p, encoding="utf-8") as f:
            assert "changed" in f.read()


class TestConvertRedirect:
    def test_convert_from_browse_lands_home(self):
        p = _write_record()
        assert _location(_convert(_client(), p, "/browse")) == "/"

    def test_convert_to_entity_preserved(self):
        p = _write_record()
        target = "/entity?field=category&value=food"
        assert _location(_convert(_client(), p, target)) == target

    def test_convert_actually_applies(self):
        p = _write_record()
        _convert(_client(), p, "/browse")
        text = _records_text()
        assert "type=expense" in text
        assert "bought coffee" not in text

    def test_convert_blocked_keeps_raw_return_to(self):
        # missing required target fields must re-render the convert form
        # rather than bouncing to the normalized landing page
        p = _write_record()
        r = _edit(_client(), p, convert="1", type="expense", note="",
                  return_to="/browse")
        assert r.status_code == 200
        assert "bought coffee" in _records_text()
        assert 'value="/browse"' in r.get_data(as_text=True)


class TestReturnToValidation:
    """The form's own return_to (Back / Cancel links) is still validated."""

    def test_add_rejects_protocol_relative(self):
        html = _client().get(
            "/add?type=capture&return_to=//evil.com/x").get_data(as_text=True)
        assert "//evil.com" not in html
        assert 'value="/browse"' in html  # documented fallback

    def test_edit_rejects_protocol_relative(self):
        p = _write_record()
        q = ("?return_to=//evil.com/x&filepath=%s&lineno=0&line=%s"
             % (quote(p), quote(_RECORD)))
        html = _client().get("/edit" + q).get_data(as_text=True)
        assert "//evil.com" not in html
        assert 'value="/browse"' in html

    def test_browse_still_available_for_back_link(self):
        html = _client().get(
            "/add?type=capture&return_to=/browse").get_data(as_text=True)
        assert 'value="/browse"' in html
        assert 'href="/browse"' in html
