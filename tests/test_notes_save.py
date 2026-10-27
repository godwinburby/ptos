"""Note save safety — locked atomic writes, rev conflicts, id preservation."""
import inspect
import os
import subprocess
import sys
import threading
import zipfile

import pytest

import ptos
import ptos_service as svc

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

_SAVES = """\
import sys
import ptos_service as svc
rel, content, n = sys.argv[1], sys.argv[2], int(sys.argv[3])
for _ in range(n):
    svc.svc_save_file(rel, content)
print("done", flush=True)
"""

CONT_A = "A" * 4000 + "|END-A"
CONT_B = "B" * 4100 + "|END-B"


def _spawn(script, home, *args):
    env = dict(os.environ, PTOS_HOME=home)
    return subprocess.Popen(
        [sys.executable, "-c", script, *args],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, env=env, cwd=REPO)


def _raw(rel):
    with open(os.path.join(ptos.NOTES_DIR, rel), "rb") as f:
        return f.read()


def _write(rel, text):
    path = os.path.join(ptos.NOTES_DIR, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(text.encode("utf-8"))
    return path


def _leftovers():
    out = []
    for root, _dirs, files in os.walk(ptos.NOTES_DIR):
        for fname in files:
            if fname.endswith((".tmp", ".bak")):
                out.append(fname)
    return out


# ── 1. concurrent complete-content saves ─────────────────────────────────────

class TestConcurrentSaves:
    def test_two_threads_write_one_complete_content(self):
        errors = []

        def worker(content):
            try:
                for _ in range(200):
                    svc.svc_save_file("race.md", content)
            except Exception as e:  # noqa: BLE001 — surfaced below
                errors.append(repr(e))

        t1 = threading.Thread(target=worker, args=(CONT_A,))
        t2 = threading.Thread(target=worker, args=(CONT_B,))
        t1.start()
        t2.start()
        t1.join(120.0)
        t2.join(120.0)
        assert not t1.is_alive() and not t2.is_alive()
        assert not errors, errors
        raw = _raw("race.md")
        assert raw in (CONT_A.encode("utf-8"), CONT_B.encode("utf-8"))
        assert not _leftovers()

    def test_two_subprocesses_write_one_complete_content(self):
        base = ptos.BASE_DIR
        procs = [
            _spawn(_SAVES, base, "race2.md", CONT_A, "200"),
            _spawn(_SAVES, base, "race2.md", CONT_B, "200"),
        ]
        for p in procs:
            _out, err = p.communicate(timeout=240.0)
            assert p.returncode == 0, err
        raw = _raw("race2.md")
        assert raw in (CONT_A.encode("utf-8"), CONT_B.encode("utf-8"))
        assert not _leftovers()


# ── 2. crash safety ──────────────────────────────────────────────────────────

class TestCrashSafety:
    def test_failed_rename_leaves_original_unchanged(self, monkeypatch):
        _write("keep.md", "original content")
        before = _raw("keep.md")

        def boom(*_a, **_k):
            raise OSError("simulated crash")

        orig_replace = os.replace
        monkeypatch.setattr(os, "replace", boom)
        try:
            with pytest.raises(OSError):
                svc.svc_save_file("keep.md", "replacement content")
        finally:
            monkeypatch.setattr(os, "replace", orig_replace)

        assert _raw("keep.md") == before
        assert not _leftovers()


# ── 3. version check ─────────────────────────────────────────────────────────

class TestVersionCheck:
    def test_stale_rev_raises_and_file_unchanged(self):
        _write("v.md", "v1")
        r1 = svc.svc_read_file("v.md")["rev"]
        svc.svc_save_file("v.md", "v2", base_rev=r1)
        r2 = svc.svc_read_file("v.md")["rev"]
        before = _raw("v.md")
        with pytest.raises(svc.NoteConflictError) as e:
            svc.svc_save_file("v.md", "v3", base_rev=r1)
        assert e.value.rev == r2
        assert _raw("v.md") == before

    def test_fresh_rev_writes_and_returns_new_rev(self):
        _write("v2.md", "v1")
        r1 = svc.svc_read_file("v2.md")["rev"]
        out = svc.svc_save_file("v2.md", "v2", base_rev=r1)
        assert out["rev"] != r1
        assert out["rev"] == svc.svc_read_file("v2.md")["rev"]
        assert _raw("v2.md") == b"v2"

    def test_missing_base_rev_is_legacy_write(self):
        _write("v3.md", "old")
        out = svc.svc_save_file("v3.md", "legacy overwrite")
        assert out["rev"]
        assert _raw("v3.md") == b"legacy overwrite"

    def test_force_overwrites_despite_stale_rev(self):
        _write("v4.md", "current")
        out = svc.svc_save_file("v4.md", "forced",
                                base_rev="0" * 16, force=True)
        assert _raw("v4.md") == b"forced"
        assert out["rev"] == ptos.note_rev(b"forced")

    def test_identical_content_with_stale_rev_succeeds(self):
        _write("v5.md", "same bytes")
        out = svc.svc_save_file("v5.md", "same bytes", base_rev="f" * 16)
        assert out["rev"] == ptos.note_rev(b"same bytes")
        assert _raw("v5.md") == b"same bytes"

    def test_missing_parent_keeps_error_behavior(self):
        with pytest.raises(FileNotFoundError):
            svc.svc_save_file("ghost/lost.md", "x")


# ── 4–5. ensure_note_id vs saves ─────────────────────────────────────────────

class TestIdVsSaveRace:
    def test_stale_save_cannot_lose_new_id(self):
        _write("id1.md", "editor body")
        r0 = svc.svc_read_file("id1.md")["rev"]
        nid = ptos.ensure_note_id("id1.md")
        after_id = _raw("id1.md")
        r1 = ptos.note_rev(after_id)
        assert r1 != r0

        with pytest.raises(svc.NoteConflictError) as e:
            svc.svc_save_file("id1.md", "editor body v2", base_rev=r0)
        assert e.value.rev == r1
        assert _raw("id1.md") == after_id
        assert nid.encode("utf-8") in _raw("id1.md")

    def test_legacy_save_re_prepends_id_line(self):
        _write("id2.md", "plain body")
        nid = ptos.ensure_note_id("id2.md")
        svc.svc_save_file("id2.md", "content without id")
        raw = _raw("id2.md")
        assert raw == f"<!-- ptos-id: {nid} -->\ncontent without id".encode("utf-8")

    def test_existing_id_returned_without_rewrite(self):
        path = _write("id3.md", "has one already")
        nid1 = ptos.ensure_note_id("id3.md")
        stat1 = os.stat(path)
        raw1 = _raw("id3.md")
        nid2 = ptos.ensure_note_id("id3.md")
        stat2 = os.stat(path)
        raw2 = _raw("id3.md")
        assert nid1 and nid1 == nid2
        assert raw1 == raw2
        assert stat1.st_mtime_ns == stat2.st_mtime_ns

    def test_id_created_under_lock_and_atomic(self):
        _write("id4.md", "atomic path")
        src = inspect.getsource(ptos.ensure_note_id)
        assert "file_lock" in src
        assert "AtomicWrite" in src
        assert 'open(full, "w"' not in src


# ── 6. routes ────────────────────────────────────────────────────────────────

class TestRoutes:
    @pytest.fixture()
    def client(self):
        import ptos_web
        return ptos_web.app.test_client()

    def test_fresh_save_returns_rev(self, client):
        _write("rt.md", "base")
        r0 = svc.svc_read_file("rt.md")["rev"]
        resp = client.post("/notes/save",
                           json={"path": "rt.md", "content": "changed",
                                 "base_rev": r0})
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["ok"] is True
        assert data["rev"] != r0
        assert len(data["rev"]) == 16

    def test_stale_rev_is_409_with_body_shape(self, client):
        _write("cf.md", "one")
        resp = client.post("/notes/save",
                           json={"path": "cf.md", "content": "two",
                                 "base_rev": "0" * 16})
        assert resp.status_code == 409
        data = resp.get_json()
        assert data["ok"] is False
        assert data["conflict"] is True
        assert data["rev"] == ptos.note_rev(b"one")
        assert data["error"]
        assert _raw("cf.md") == b"one"

    def test_non_json_body_is_400(self, client):
        resp = client.post("/notes/save", data="plain",
                           content_type="text/plain")
        assert resp.status_code == 400
        data = resp.get_json()
        assert data["ok"] is False
        assert "JSON" in data["error"]

    def test_held_lock_is_423(self, client):
        full = _write("busy.md", "original")
        ready = threading.Event()
        release = threading.Event()

        def holder():
            with ptos.file_lock(full, timeout=10.0):
                ready.set()
                release.wait(15.0)

        t = threading.Thread(target=holder, daemon=True)
        t.start()
        assert ready.wait(5.0), "holder thread never acquired"
        gen = getattr(ptos.file_lock, "__wrapped__", None)
        assert gen is not None
        old_defaults = gen.__defaults__
        gen.__defaults__ = (0.3,)
        try:
            resp = client.post("/notes/save",
                               json={"path": "busy.md", "content": "new"})
        finally:
            gen.__defaults__ = old_defaults
            release.set()
            t.join(15.0)
        assert resp.status_code == 423
        data = resp.get_json()
        assert data["ok"] is False
        assert data["error"]
        assert _raw("busy.md") == b"original"

    def test_missing_parent_route_is_error_not_crash(self, client):
        resp = client.post("/notes/save",
                           json={"path": "ghost/lost.md", "content": "x"})
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["ok"] is False
        assert data["error"]

    def test_edit_page_carries_rev(self, client):
        _write("page.md", "page body")
        rev = svc.svc_read_file("page.md")["rev"]
        resp = client.get("/notes/edit/page.md")
        assert resp.status_code == 200
        assert f'"{rev}"' in resp.get_data(as_text=True)


# ── 7. round trip ────────────────────────────────────────────────────────────

class TestRoundTrip:
    @pytest.mark.parametrize("content", [
        "plain ascii\nsecond line",
        "héllo — ünïcode ✓\n第二行 нотатка",
        "crlf first\r\nsecond line\r\n",
        "mixed\nline\rline\rtail",
    ])
    def test_byte_exact_storage_and_stable_reload(self, content, tmp_path):
        rel = f"rt{abs(hash(content)) % 100000}.md"
        svc.svc_save_file(rel, content)
        raw = _raw(rel)
        assert raw == content.encode("utf-8")
        read = svc.svc_read_file(rel)
        assert read["rev"] == ptos.note_rev(raw)
        expected = content.replace("\r\n", "\n").replace("\r", "\n")
        assert read["content"] == expected
        out = svc.svc_save_file(rel, read["content"], base_rev=read["rev"])
        assert out["rev"]
        assert _raw(rel) == expected.encode("utf-8")


# ── 8. enumeration ignores writer files ──────────────────────────────────────

class TestEnumerationIgnoresWriterFiles:
    @pytest.fixture(autouse=True)
    def planted(self):
        _write("real.md", "queried realcontenttoken, see [[bl-real]]")
        path = os.path.join(ptos.NOTES_DIR, "planted.md.lock")
        with open(path, "w", encoding="utf-8") as f:
            f.write("queried lockcontenttoken [[bl-fake]]")
        return path

    def test_tree_excludes_lock(self, planted):
        listing = ptos.list_dir("")
        names = [f["name"] for f in listing["files"]]
        assert "real.md" in names
        assert "planted.md.lock" not in names
        assert not any(n.endswith(".lock") for n in names)

    def test_search_excludes_lock(self, client_factory, planted):
        client = client_factory()
        body = client.get("/search",
                          query_string={"q": "queried"}
                          ).get_data(as_text=True)
        assert "realcontenttoken" in body
        assert "lockcontenttoken" not in body

    def test_backlinks_exclude_lock(self, planted):
        assert not any(svc.get_backlinks("bl-fake").values())
        assert svc.get_backlinks("bl-real")["notes"]

    def test_backup_zip_excludes_lock(self, planted):
        zip_path = ptos.backup_data(force=True)
        with zipfile.ZipFile(zip_path) as z:
            names = z.namelist()
        assert names
        assert not any(n.endswith(".lock") for n in names)


@pytest.fixture()
def client_factory():
    def make():
        import ptos_web
        return ptos_web.app.test_client()
    return make


# ── 9. rename/delete leave no orphan locks ───────────────────────────────────

class TestNoOrphanLocks:
    def test_rename_removes_old_sidecar(self):
        _write("old.md", "content")
        open(os.path.join(ptos.NOTES_DIR, "old.md.lock"), "w").close()
        ptos.rename_note("old.md", "renamed.md")
        assert os.path.exists(os.path.join(ptos.NOTES_DIR, "renamed.md"))
        assert not os.path.exists(os.path.join(ptos.NOTES_DIR, "old.md"))
        assert not os.path.exists(os.path.join(ptos.NOTES_DIR, "old.md.lock"))

    def test_file_delete_removes_sidecar(self):
        ptos.create_file("", "victim.md", "bye")
        open(os.path.join(ptos.NOTES_DIR, "victim.md.lock"), "w").close()
        ptos.delete_note_entry("victim.md")
        assert not os.path.exists(os.path.join(ptos.NOTES_DIR, "victim.md"))
        assert not os.path.exists(os.path.join(ptos.NOTES_DIR, "victim.md.lock"))

    def test_folder_delete_removes_sidecar(self):
        folder = os.path.join(ptos.NOTES_DIR, "box")
        os.makedirs(folder)
        with open(os.path.join(folder, "in.md"), "w", encoding="utf-8") as f:
            f.write("x")
        open(folder + ".lock", "w").close()
        ptos.delete_note_entry("box")
        assert not os.path.exists(folder)
        assert not os.path.exists(folder + ".lock")


# ── 10. template / static pins ───────────────────────────────────────────────

class TestTemplatePins:
    def _read(self, *parts):
        with open(os.path.join(REPO, "web_templates", *parts),
                  encoding="utf-8") as f:
            return f.read()

    def test_editor_partial_handles_conflicts(self):
        html = self._read("_markdown_editor.html")
        for needle in ("md-conflict-banner", "md-conflict-reload",
                       "md-conflict-copy", "md-conflict-overwrite",
                       "md-save-status", "409", "423",
                       "_mdSaveFn", "_mdCopyFn"):
            assert needle in html, f"missing {needle!r}"

    def test_notes_edit_sends_base_rev(self):
        html = self._read("notes_edit.html")
        for needle in ("_baseRev", "base_rev", 'base_rev: "absent"',
                       "409", "423", "Promise", "_mdCopyFn"):
            assert needle in html, f"missing {needle!r}"

    def test_journal_save_is_promise_based(self):
        html = self._read("journal.html")
        assert "window._mdSaveFn = function(silent, opts)" in html
        assert "Promise.resolve" in html

    def test_no_direct_text_writes_in_note_writers(self):
        import ptos_web
        core_src = inspect.getsource(svc._save_text_locked)
        assert "AtomicWrite" in core_src
        save_src = inspect.getsource(svc.svc_save_file)
        assert "_save_text_locked" in save_src
        for fn in (svc.svc_save_file, ptos.ensure_note_id, ptos.create_file):
            src = inspect.getsource(fn)
            assert 'open(full, "w"' not in src, fn.__name__
        src = inspect.getsource(ptos_web.api_conflict_resolve)
        assert "shutil.copy2(conf_full" not in src
        assert 'open(orig_full, "w"' not in src
        import ptos_cli
        src = inspect.getsource(ptos_cli._resolve_notes_conflict)
        assert 'open(orig_full, "w"' not in src


# ── 11. note names render without .md ────────────────────────────────────────

class TestNoteDisplayNames:
    @pytest.fixture()
    def client(self):
        import ptos_web
        return ptos_web.app.test_client()

    def test_notes_list_shows_display_name(self, client):
        _write("Clinic Note.md", "body")
        html = client.get("/notes").get_data(as_text=True)
        assert "&#128196; Clinic Note</a>" in html
        assert "&#128196; Clinic Note.md</a>" not in html
        assert 'href="/notes/edit/Clinic Note.md"' in html
        assert 'data-name="Clinic Note"' in html
        assert 'data-name="Clinic Note.md"' not in html

    def test_edit_breadcrumb_shows_display_name(self, client):
        _write("sub/Clinic Note.md", "body")
        html = client.get("/notes/edit/sub/Clinic Note.md") \
            .get_data(as_text=True)
        assert ">Clinic Note</span>" in html
        assert ">Clinic Note.md</span>" not in html
        import ptos_web
        crumbs = ptos_web._notes_breadcrumbs("sub/Clinic Note.md")
        assert crumbs[-1]["label"] == "Clinic Note"

    def test_search_result_title_has_no_md(self, client):
        _write("findme.md", "uniquefindmebody")
        html = client.get("/search?q=findmebody").get_data(as_text=True)
        assert ";font-weight:600;\">findme</a>" in html
        assert ";font-weight:600;\">findme.md</a>" not in html
        assert "findme.md" in html

    def test_projects_notes_list_has_no_md(self, client):
        _write("job-hunt.md", "# Job Hunt\nMeeting [[PT Name]] next week\n")
        svc._write_queries_toml_key(
            "project.ptname", {"label": "PT Name", "todo_project": "ptname"})
        html = client.get("/projects?legacy=1").get_data(as_text=True)
        assert ">📝 job-hunt</a>" in html
        assert ">📝 job-hunt.md</a>" not in html
        assert 'href="/notes/edit/job-hunt.md"' in html

    def test_rename_dialog_prefills_display_name(self, client):
        _write("Prefill.md", "body")
        html = client.get("/notes").get_data(as_text=True)
        assert 'data-name="Prefill"' in html
        assert 'data-name="Prefill.md"' not in html
