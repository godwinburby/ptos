"""Journal date validation, path containment, and (later) rev-conflict saves."""
import ast
import datetime as dt
import os

import pytest

import ptos

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_TODAY = dt.date.today().isoformat()


@pytest.fixture
def client():
    import ptos_web
    return ptos_web.app.test_client()


class TestParseJournalDate:
    def test_accepts_today(self):
        assert ptos.parse_journal_date(_TODAY).isoformat() == _TODAY

    @pytest.mark.parametrize("value", ["2024-02-29", "2000-02-29", "1999-01-01"])
    def test_accepts_valid_dates(self, value):
        assert ptos.parse_journal_date(value).isoformat() == value

    @pytest.mark.parametrize("value", [
        "2026-02-30",
        "2026-13-01",
        "2026-00-10",
        "2026-10-00",
        "2026-10-16 ",
        " 2026-10-16",
        "2026-10-16x",
        "2026-10-16\n",
        "2026-10-16\x00",
        "20261016",
        "2026-W41-4",
        "2026-10-16T00:00:00",
        "2026-10-16/../../../../escaped",
        "/etc/x",
        "..",
        "C:\\x",
        "C:/x",
        "",
        "a" * 4096,
        123,
        None,
        b"2026-10-16",
        [],
        {},
    ])
    def test_rejects_everything_else(self, value):
        with pytest.raises(ptos.PTOSError):
            ptos.parse_journal_date(value)


class TestJournalPathBuilders:
    def test_journal_path_shape(self):
        path = ptos.journal_path(_TODAY)
        assert path == os.path.join(
            ptos.JOURNAL_DIR, _TODAY[:4], _TODAY[5:7], f"{_TODAY}.md")

    def test_journal_path_rejects_traversal(self):
        with pytest.raises(ptos.PTOSError):
            ptos.journal_path("2026-10-16/../../../../escaped")

    def test_get_journal_path_rejects_traversal_without_creating(self):
        with pytest.raises(ptos.PTOSError):
            ptos.get_journal_path("2026-10-16/../../../escaped")
        assert not os.path.exists(os.path.join(ptos.BASE_DIR, "escaped.md"))
        assert not os.path.isdir(os.path.join(ptos.JOURNAL_DIR, "2026", "10",
                                              "2026-10-16"))

    def test_get_journal_path_writes_inside_journal_dir(self):
        path = ptos.get_journal_path("2026-07-15")
        assert ptos._path_within(path, ptos.JOURNAL_DIR)
        assert os.path.isfile(path)

    def test_delete_journal_rejects_traversal_and_keeps_victim(self):
        victim = os.path.join(ptos.BASE_DIR, "victim.md")
        with open(victim, "w", encoding="utf-8") as f:
            f.write("keep me")
        with pytest.raises(ptos.PTOSError):
            ptos.delete_journal("2026-10-16/../../../victim")
        assert os.path.isfile(victim)
        with open(victim, encoding="utf-8") as f:
            assert f.read() == "keep me"

    def test_resolve_link_malformed_journal_target_is_none(self):
        assert ptos.resolve_link("journal:2026-..-xx") is None
        assert ptos.resolve_link("journal:../x") is None

    def test_resolve_link_valid_date_missing_file_is_none(self):
        assert not os.path.exists(ptos.journal_path(_TODAY))
        assert ptos.resolve_link(f"journal:{_TODAY}") is None

    def test_get_journal_template_content_rejects_traversal(self):
        with pytest.raises(ptos.PTOSError):
            ptos.get_journal_template_content("2026-10-16/../x")


class TestJournalServiceSafety:
    def test_save_journal_traversal_never_writes_outside(self):
        import ptos_service as svc
        with pytest.raises(ptos.PTOSError):
            svc.save_journal("2026-10-16/../../../escaped", "content")
        assert not os.path.exists(os.path.join(ptos.BASE_DIR, "escaped.md"))
        assert not os.path.exists(os.path.join(ptos.BASE_DIR, "escaped.md.lock"))
        assert not os.path.exists(os.path.join(ptos.BASE_DIR, "escaped.md.bak"))

    def test_save_journal_valid_date_writes_inside_journal_dir(self):
        import ptos_service as svc
        svc.save_journal(_TODAY, "hello")
        path = os.path.join(
            ptos.JOURNAL_DIR, _TODAY[:4], _TODAY[5:7], f"{_TODAY}.md")
        assert os.path.isfile(path)
        with open(path, encoding="utf-8") as f:
            assert f.read() == "hello"

    def test_delete_journal_service_rejects_traversal(self):
        import ptos_service as svc
        victim = os.path.join(ptos.BASE_DIR, "victim2.md")
        with open(victim, "w", encoding="utf-8") as f:
            f.write("keep")
        with pytest.raises(ptos.PTOSError):
            svc.delete_journal("2026-10-16/../../../victim2")
        assert os.path.isfile(victim)


class TestPathWithinHelper:
    def test_inside_and_equal(self):
        root = ptos.JOURNAL_DIR
        inside = os.path.join(root, "2026", "10", "x.md")
        assert ptos._path_within(inside, root)
        assert ptos._path_within(root, root)

    def test_escape_forms(self):
        root = ptos.JOURNAL_DIR
        assert not ptos._path_within(os.path.join(root, "..", "x"), root)
        assert not ptos._path_within(os.path.join(root, "2026", "..", "..", "x"), root)
        assert not ptos._path_within("/etc/passwd", root)

    def test_sibling_prefix_is_outside(self):
        root = ptos.RECORDS_DIR
        sibling = str(root) + "_evil"
        assert not ptos._path_within(os.path.join(sibling, "x.log"), root)

    def test_realpath_key_strips_extended_prefix(self, monkeypatch):
        monkeypatch.setattr(os.path, "realpath", lambda p: p)
        assert ptos._realpath_key(r"\\?\C:\data\journal\x.md") == \
            os.path.normcase(r"C:\data\journal\x.md")
        assert ptos._realpath_key(r"\\?\UNC\srv\share\x") == \
            os.path.normcase(r"\\srv\share\x")
        assert ptos._realpath_key("/data/x") == os.path.normcase("/data/x")

    def test_mixed_extended_prefix_forms_still_contain(self, monkeypatch):
        root = os.path.join(os.sep + "data", "journal")
        inside = os.path.join(root, "2026", "10", "x.md")

        def fake_realpath(p):
            return "\\\\?\\" + p if p == inside else p

        monkeypatch.setattr(os.path, "realpath", fake_realpath)
        assert ptos._path_within(inside, root)
        assert ptos._path_within(root, root)

    def test_prefixed_escape_is_still_outside(self, monkeypatch):
        root = os.path.join(os.sep + "data", "journal")
        outside = os.path.join(os.sep + "data", "journal_evil", "x.md")

        def fake_realpath(p):
            return "\\\\?\\" + p if p == outside else p

        monkeypatch.setattr(os.path, "realpath", fake_realpath)
        assert not ptos._path_within(outside, root)


class TestBackupNameValidator:
    @pytest.mark.parametrize("name", [
        "ptos-backup-full-20261016_120000.zip",
        "ptos-backup-config-20261016_120000.zip",
    ])
    def test_accepts_real_names(self, name):
        assert ptos._valid_backup_name(name)

    @pytest.mark.parametrize("name", [
        "../x.zip",
        "..",
        ".",
        "x.zip",
        "ptos-backup-full-20261016_120000.zip/../x.zip",
        "C:\\x.zip",
        "/etc/x.zip",
        "",
        None,
        123,
    ])
    def test_rejects_everything_else(self, name):
        assert not ptos._valid_backup_name(name)


class TestJournalRoutes:
    def test_save_non_json_is_400(self, client):
        r = client.post("/journal/save", data="x", content_type="text/plain")
        assert r.status_code == 400

    def test_save_traversal_date_is_400_and_writes_nothing(self, client):
        r = client.post("/journal/save", json={
            "date": "2026-10-16/../../../escaped", "content": "hi"})
        assert r.status_code == 400
        assert r.get_json()["ok"] is False
        assert not os.path.exists(os.path.join(ptos.BASE_DIR, "escaped.md"))

    def test_save_valid_date_still_works(self, client):
        r = client.post("/journal/save", json={"date": _TODAY, "content": "hi"})
        assert r.status_code == 200
        assert r.get_json()["ok"] is True

    def test_delete_non_json_is_400(self, client):
        r = client.post("/journal/delete", data="x", content_type="text/plain")
        assert r.status_code == 400

    def test_delete_traversal_is_400_and_keeps_victim(self, client):
        victim = os.path.join(ptos.BASE_DIR, "victim3.md")
        with open(victim, "w", encoding="utf-8") as f:
            f.write("keep")
        r = client.post("/journal/delete", json={
            "date": "2026-10-16/../../../victim3"})
        assert r.status_code == 400
        assert os.path.isfile(victim)

    def test_get_page_rejects_garbage_date_by_falling_back(self, client):
        r = client.get("/journal?date=2026-10-16/../../../x")
        assert r.status_code == 200
        assert _TODAY in r.get_data(as_text=True)


class TestSiblingPathFixes:
    def test_conflict_resolver_rejects_escaping_conflict_path(self, client):
        r = client.post("/api/conflict/resolve", json={
            "action": "import_records",
            "conflict_path": "../evil.sync-conflict.log",
            "original_path": "records/x.log",
            "file_type": "records",
            "lines": [],
        })
        assert r.status_code == 400
        assert "conflict_path" in r.get_json()["error"]

    def test_conflict_resolver_rejects_escaping_original_path(self, client):
        r = client.post("/api/conflict/resolve", json={
            "action": "import_records",
            "conflict_path": "records/x.sync-conflict.log",
            "original_path": "../evil.log",
            "file_type": "records",
            "lines": [],
        })
        assert r.status_code == 400
        assert "original_path" in r.get_json()["error"]

    def test_backup_restore_rejects_escaping_name(self, client):
        r = client.post("/backup/restore", json={"name": "../x.zip"})
        assert r.status_code == 400
        r2 = client.post("/backup/restore", json={"name": ".."})
        assert r2.status_code == 400

    def test_records_delete_rejects_sibling_prefix(self, client):
        evil = os.path.join(str(ptos.RECORDS_DIR) + "_evil", "x.log")
        r = client.post("/api/records/delete", json={
            "filepath": evil, "old_line": "x"})
        assert r.get_json()["ok"] is False
        assert "Invalid filepath" in r.get_json()["error"]

    def test_records_edit_rejects_sibling_prefix(self, client):
        evil = os.path.join(str(ptos.RECORDS_DIR) + "_evil", "x.log")
        r = client.post("/api/records/edit", json={
            "filepath": evil, "old_line": "x", "set": []})
        assert r.get_json()["ok"] is False
        assert "Invalid filepath" in r.get_json()["error"]

    def test_bulk_delete_rejects_sibling_prefix(self, client):
        evil = os.path.join(str(ptos.RECORDS_DIR) + "_evil", "x.log")
        r = client.post("/api/records/bulk_delete", json={
            "records": [{"filepath": evil, "line": "x", "lineno": 0}]})
        assert r.get_json()["ok"] is False
        assert "Invalid filepath" in r.get_json()["error"]

    def test_bulk_set_rejects_sibling_prefix(self, client):
        evil = os.path.join(str(ptos.RECORDS_DIR) + "_evil", "x.log")
        r = client.post("/api/records/bulk_set", json={
            "records": [{"filepath": evil, "line": "x", "lineno": 0}],
            "set_args": ["tag=x"]})
        assert r.get_json()["ok"] is False
        assert "Invalid filepath" in r.get_json()["error"]

    def test_editor_get_rejects_traversal(self, client):
        secret = os.path.join(ptos.BASE_DIR, "config", "secret.toml")
        os.makedirs(os.path.dirname(secret), exist_ok=True)
        with open(secret, "w", encoding="utf-8") as f:
            f.write("password = hunter2")
        r = client.get("/editor?file=../config/secret.toml")
        assert r.status_code == 400
        assert "hunter2" not in r.get_data(as_text=True)

    def test_editor_content_rejects_dotdot(self, client):
        r = client.get("/editor/content?file=..")
        assert r.status_code == 400

    def test_editor_save_rejects_dotdot(self, client):
        r = client.post("/editor/save", json={"file": "..", "content": "x"})
        assert r.get_json()["ok"] is False
        assert "Invalid filename" in r.get_json()["error"]


class TestJournalRevSaves:
    def _save(self, client, date, content, **extra):
        body = {"date": date, "content": content}
        body.update(extra)
        return client.post("/journal/save", json=body)

    def test_fresh_save_returns_rev(self, client):
        r = self._save(client, _TODAY, "v1")
        d = r.get_json()
        assert r.status_code == 200 and d["ok"] is True
        assert d["rev"] != "absent"

    def test_first_save_absent_matches_missing_file(self, client):
        r = self._save(client, _TODAY, "v1", base_rev="absent")
        assert r.status_code == 200 and r.get_json()["ok"] is True

    def test_second_create_with_absent_is_409(self, client):
        self._save(client, _TODAY, "v1")
        r = self._save(client, _TODAY, "v2", base_rev="absent")
        assert r.status_code == 409
        d = r.get_json()
        assert d["ok"] is False and d["conflict"] is True
        assert d["rev"] != "absent"

    def test_stale_rev_does_not_overwrite(self, client):
        first = self._save(client, _TODAY, "v1").get_json()
        r = self._save(client, _TODAY, "v2", base_rev="absent")
        assert r.status_code == 409
        path = ptos.journal_path(_TODAY)
        with open(path, encoding="utf-8") as f:
            assert f.read() == "v1"
        assert first["rev"] != "absent"

    def test_force_overwrites(self, client):
        self._save(client, _TODAY, "v1")
        r = self._save(client, _TODAY, "v2", base_rev="absent", force=True)
        assert r.status_code == 200 and r.get_json()["ok"] is True
        with open(ptos.journal_path(_TODAY), encoding="utf-8") as f:
            assert f.read() == "v2"

    def test_current_rev_succeeds_and_rotates(self, client):
        rev1 = self._save(client, _TODAY, "v1").get_json()["rev"]
        r = self._save(client, _TODAY, "v2", base_rev=rev1)
        d = r.get_json()
        assert r.status_code == 200 and d["ok"] is True
        assert d["rev"] != rev1

    def test_identical_stale_rev_succeeds(self, client):
        rev1 = self._save(client, _TODAY, "same").get_json()["rev"]
        r = self._save(client, _TODAY, "same", base_rev="absent")
        d = r.get_json()
        assert r.status_code == 200 and d["ok"] is True
        assert d["rev"] == rev1

    def test_legacy_save_without_base_rev_still_writes(self, client):
        self._save(client, _TODAY, "v1")
        r = self._save(client, _TODAY, "v2")
        assert r.status_code == 200 and r.get_json()["ok"] is True
        with open(ptos.journal_path(_TODAY), encoding="utf-8") as f:
            assert f.read() == "v2"

    def test_thread_race_has_exactly_one_winner(self):
        import ptos_service as svc
        import threading
        results = []

        def writer(content):
            try:
                svc.save_journal(_TODAY, content, base_rev="absent")
                results.append("ok")
            except svc.NoteConflictError:
                results.append("conflict")

        threads = [threading.Thread(target=writer, args=(f"body{i}",))
                   for i in range(2)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(10.0)
        assert sorted(results) == ["conflict", "ok"]

    def test_get_page_carries_rev(self, client):
        text = client.get(f"/journal?date={_TODAY}").get_data(as_text=True)
        assert "_baseRev" in text
        assert "base_rev" in text
        assert "_mdCopyFn" in text

    def test_get_page_carries_real_rev_after_save(self, client):
        self._save(client, _TODAY, "v1")
        rev = ptos_service_journal_rev()
        text = client.get(f"/journal?date={_TODAY}").get_data(as_text=True)
        assert rev in text


def ptos_service_journal_rev():
    import ptos_service as svc
    return svc.journal_rev(_TODAY)


class TestJournalCopy:
    def test_copy_writes_beside_entry(self, client):
        import re
        client.post("/journal/save", json={"date": _TODAY, "content": "orig"})
        r = client.post("/journal/copy", json={
            "date": _TODAY, "content": "my merged text"})
        d = r.get_json()
        assert r.status_code == 200 and d["ok"] is True
        assert re.fullmatch(
            rf"{re.escape(_TODAY)} \(my edits \d{{4}}\)\.md", d["filename"])
        month_dir = os.path.dirname(ptos.journal_path(_TODAY))
        copy_path = os.path.join(month_dir, d["filename"])
        assert os.path.isfile(copy_path)
        with open(copy_path, encoding="utf-8") as f:
            assert f.read() == "my merged text"
        with open(ptos.journal_path(_TODAY), encoding="utf-8") as f:
            assert f.read() == "orig"

    def test_copy_rejects_traversal_date(self, client):
        r = client.post("/journal/copy", json={
            "date": "2026-10-16/../../../x", "content": "c"})
        assert r.status_code == 400

    def test_copy_non_json_is_400(self, client):
        r = client.post("/journal/copy", data="x",
                        content_type="text/plain")
        assert r.status_code == 400


class TestJournalDeleteRev:
    def test_stale_rev_delete_is_409_and_keeps_file(self, client):
        client.post("/journal/save", json={"date": _TODAY, "content": "v1"})
        r = client.post("/journal/delete", json={
            "date": _TODAY, "base_rev": "absent"})
        assert r.status_code == 409
        assert r.get_json()["conflict"] is True
        assert os.path.isfile(ptos.journal_path(_TODAY))

    def test_current_rev_delete_succeeds(self, client):
        rev = client.post("/journal/save", json={
            "date": _TODAY, "content": "v1"}).get_json()["rev"]
        r = client.post("/journal/delete", json={
            "date": _TODAY, "base_rev": rev})
        assert r.status_code == 200 and r.get_json()["ok"] is True
        assert not os.path.isfile(ptos.journal_path(_TODAY))

    def test_delete_without_rev_still_works(self, client):
        client.post("/journal/save", json={"date": _TODAY, "content": "v1"})
        r = client.post("/journal/delete", json={"date": _TODAY})
        assert r.status_code == 200 and r.get_json()["ok"] is True


class TestLineEndings:
    def test_notes_read_normalizes_crlf(self):
        import ptos_service as svc
        svc.svc_save_file("crlf.md", "line one")
        path = ptos._safe_path("crlf.md")
        with open(path, "wb") as f:
            f.write(b"line one\r\nline two\r\n")
        loaded = svc.svc_read_file("crlf.md")
        assert loaded["content"] == "line one\nline two\n"

    def test_crlf_identical_stale_rev_succeeds(self):
        import ptos_service as svc
        rev = svc.svc_save_file("crlf2.md", "same")["rev"]
        path = ptos._safe_path("crlf2.md")
        with open(path, "wb") as f:
            f.write(b"same\r\n")
        result = svc.svc_save_file("crlf2.md", "same\n", base_rev="absent")
        assert result["rev"] != "absent"

    def test_first_save_writes_lf(self):
        import ptos_service as svc
        svc.svc_save_file("lf.md", "a\nb\n")
        with open(ptos._safe_path("lf.md"), "rb") as f:
            raw = f.read()
        assert b"\r" not in raw
        assert raw == b"a\nb\n"

    def test_journal_crlf_identical_stale_rev_succeeds(self):
        import ptos_service as svc
        svc.save_journal(_TODAY, "same")
        with open(ptos.journal_path(_TODAY), "wb") as f:
            f.write(b"same\r\n")
        result = svc.save_journal(_TODAY, "same\n", base_rev="absent")
        assert result["rev"] != "absent"

    """Static guard: a ptos_web route that joins a request-derived value
    into a filesystem path must also call a containment/validator helper."""

    _VALIDATORS = {
        "_path_within", "_safe_path", "parse_journal_date",
        "_valid_backup_name", "_valid_log_filename", "basename",
    }

    @staticmethod
    def _is_os_join(node):
        return (isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "join"
                and isinstance(node.func.value, ast.Attribute)
                and node.func.value.attr == "path"
                and isinstance(node.func.value.value, ast.Name)
                and node.func.value.value.id == "os")

    @staticmethod
    def _is_dict_get(node):
        return (isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "get")

    def _violations(self):
        path = os.path.join(_REPO_ROOT, "ptos_web.py")
        with open(path, encoding="utf-8") as f:
            tree = ast.parse(f.read())
        violations = []
        for fn in [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)]:
            user_names = set()
            for node in ast.walk(fn):
                if not isinstance(node, ast.Assign):
                    continue
                if not self._is_dict_get(node.value):
                    continue
                for tgt in node.targets:
                    if isinstance(tgt, ast.Name):
                        user_names.add(tgt.id)
            joins_user_value = False
            for node in ast.walk(fn):
                if not self._is_os_join(node):
                    continue
                for arg in node.args:
                    if isinstance(arg, ast.Name) and arg.id in user_names:
                        joins_user_value = True
                    if self._is_dict_get(arg):
                        joins_user_value = True
            if not joins_user_value:
                continue
            uses_validator = any(
                (isinstance(n, ast.Call)
                 and ((isinstance(n.func, ast.Attribute)
                       and n.func.attr in self._VALIDATORS)
                      or (isinstance(n.func, ast.Name)
                          and n.func.id in self._VALIDATORS)))
                for n in ast.walk(fn))
            if not uses_validator:
                violations.append(fn.name)
        return violations

    def test_every_user_value_join_is_validated(self):
        assert self._violations() == []
