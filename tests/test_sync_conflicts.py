import os
import pytest
import ptos
from ptos import (find_sync_conflicts, diff_records_conflict,
                  diff_todos_conflict, _strip_conflict_suffix,
                  _parse_conflict_meta, _classify_conflict)


class TestStripConflictSuffix:
    def test_syncthing(self):
        assert _strip_conflict_suffix(
            "2026.sync-conflict-20260911-113533-XAJ7GJU.log") == "2026.log"

    def test_syncthing_todo(self):
        assert _strip_conflict_suffix(
            "todo.sync-conflict-20260827-111614-K4BHCH2.txt") == "todo.txt"

    def test_nextcloud(self):
        assert _strip_conflict_suffix(
            "2026-07-03 (conflict 2026-07-03-14-36-49).md") == "2026-07-03.md"

    def test_rclone_conflict1(self):
        assert _strip_conflict_suffix("2026.log.conflict1") == "2026.log"

    def test_rclone_conflict2(self):
        assert _strip_conflict_suffix("todo.txt.conflict2") == "todo.txt"

    def test_no_conflict(self):
        assert _strip_conflict_suffix("2026.log") == "2026.log"


class TestParseConflictMeta:
    def test_syncthing(self):
        device, detected = _parse_conflict_meta(
            "2026.sync-conflict-20260911-113533-XAJ7GJU.log")
        assert device == "XAJ7GJU"
        assert detected == "2026-09-11 11:35:33"

    def test_nextcloud(self):
        device, detected = _parse_conflict_meta(
            "2026-07-03 (conflict 2026-07-03-14-36-49).md")
        assert device is None
        assert detected == "2026-07-03 14:36:49"

    def test_rclone(self):
        device, detected = _parse_conflict_meta("2026.log.conflict1")
        assert device is None
        assert detected is None


class TestClassifyConflict:
    def test_done_file(self):
        assert _classify_conflict("todo", "done.sync-conflict-20260827.txt") == "done"

    def test_todo_file(self):
        assert _classify_conflict("todo", "todo.sync-conflict-20260827.txt") == "todo"

    def test_records(self):
        assert _classify_conflict("records", "2026.sync-conflict-20260911.log") == "records"


class TestFindSyncConflicts:
    def test_no_conflicts(self, tmp_path):
        records_dir = ptos.RECORDS_DIR
        os.makedirs(records_dir, exist_ok=True)
        with open(os.path.join(records_dir, "2026.log"), "w") as f:
            f.write("2026-01-01 type=expense amount=10\n")
        assert find_sync_conflicts() == []

    def test_detects_records_conflict(self):
        records_dir = ptos.RECORDS_DIR
        os.makedirs(records_dir, exist_ok=True)
        with open(os.path.join(records_dir, "2026.log"), "w") as f:
            f.write("2026-01-01 type=expense amount=10\n")
        with open(os.path.join(records_dir,
                 "2026.sync-conflict-20260911-113533-XAJ7GJU.log"), "w") as f:
            f.write("2026-01-02 type=income amount=20\n")
        conflicts = find_sync_conflicts()
        assert len(conflicts) == 1
        assert conflicts[0]["file_type"] == "records"
        assert conflicts[0]["device"] == "XAJ7GJU"
        assert "2026.log" in conflicts[0]["original_path"]

    def test_detects_todo_conflict(self):
        todo_dir = ptos.TODO_DIR
        os.makedirs(todo_dir, exist_ok=True)
        with open(os.path.join(todo_dir, "todo.txt"), "w") as f:
            f.write("(A) Buy milk\n")
        with open(os.path.join(todo_dir,
                 "todo.sync-conflict-20260827-111614-K4BHCH2.txt"), "w") as f:
            f.write("(B) Buy eggs\n")
        conflicts = find_sync_conflicts()
        assert len(conflicts) == 1
        assert conflicts[0]["file_type"] == "todo"

    def test_detects_done_conflict(self):
        todo_dir = ptos.TODO_DIR
        os.makedirs(todo_dir, exist_ok=True)
        with open(os.path.join(todo_dir, "done.txt"), "w") as f:
            f.write("x 2026-01-01 Finished task\n")
        with open(os.path.join(todo_dir,
                 "done.sync-conflict-20260827-111614-K4BHCH2.txt"), "w") as f:
            f.write("x 2026-01-02 Another done\n")
        conflicts = find_sync_conflicts()
        assert len(conflicts) == 1
        assert conflicts[0]["file_type"] == "done"

    def test_excludes_trashed_files(self):
        records_dir = ptos.RECORDS_DIR
        os.makedirs(records_dir, exist_ok=True)
        with open(os.path.join(records_dir,
                 ".trashed-1789295643-2026.sync-conflict-20260810.log"), "w") as f:
            f.write("")
        assert find_sync_conflicts() == []

    def test_excludes_stversions(self):
        records_dir = ptos.RECORDS_DIR
        stversions = os.path.join(records_dir, ".stversions")
        os.makedirs(stversions, exist_ok=True)
        with open(os.path.join(stversions,
                 "2026.sync-conflict-20260810.log"), "w") as f:
            f.write("")
        assert find_sync_conflicts() == []

    def test_multiple_conflicts(self):
        records_dir = ptos.RECORDS_DIR
        todo_dir = ptos.TODO_DIR
        os.makedirs(records_dir, exist_ok=True)
        os.makedirs(todo_dir, exist_ok=True)
        with open(os.path.join(records_dir,
                 "2026.sync-conflict-20260911-113533-XAJ7GJU.log"), "w") as f:
            f.write("")
        with open(os.path.join(todo_dir,
                 "todo.sync-conflict-20260827-111614-K4BHCH2.txt"), "w") as f:
            f.write("")
        with open(os.path.join(todo_dir,
                 "done.sync-conflict-20260827-111614-K4BHCH2.txt"), "w") as f:
            f.write("")
        conflicts = find_sync_conflicts()
        assert len(conflicts) == 3
        types = {c["file_type"] for c in conflicts}
        assert types == {"records", "todo", "done"}

    def test_notes_conflict(self):
        notes_dir = ptos.NOTES_DIR
        os.makedirs(notes_dir, exist_ok=True)
        with open(os.path.join(notes_dir, "meeting.md"), "w") as f:
            f.write("# Meeting\nOriginal content\n")
        with open(os.path.join(notes_dir,
                 "meeting.sync-conflict-20260911-113533-XAJ7GJU.md"), "w") as f:
            f.write("# Meeting\nConflicting content\n")
        conflicts = find_sync_conflicts()
        assert len(conflicts) == 1
        assert conflicts[0]["file_type"] == "notes"


class TestDiffRecordsConflict:
    def test_append_only(self):
        records_dir = ptos.RECORDS_DIR
        os.makedirs(records_dir, exist_ok=True)
        orig = os.path.join(records_dir, "2026.log")
        conf = os.path.join(records_dir,
                "2026.sync-conflict-20260911-113533-XAJ7GJU.log")
        with open(orig, "w") as f:
            f.write("2026-01-01 type=expense amount=10\n")
            f.write("2026-01-02 type=expense amount=20\n")
        with open(conf, "w") as f:
            f.write("2026-01-01 type=expense amount=10\n")
            f.write("2026-01-03 type=income amount=30\n")
        orig_rel = os.path.relpath(orig, ptos.BASE_DIR).replace("\\", "/")
        conf_rel = os.path.relpath(conf, ptos.BASE_DIR).replace("\\", "/")
        result = diff_records_conflict(orig_rel, conf_rel)
        assert len(result["lines_only_in_conflict"]) == 1
        assert "income" in result["lines_only_in_conflict"][0]
        assert len(result["lines_only_in_original"]) == 1
        assert "2026-01-02" in result["lines_only_in_original"][0]
        assert len(result["edit_conflicts"]) == 0

    def test_same_date_type_is_a_hint_not_an_edit(self):
        records_dir = ptos.RECORDS_DIR
        os.makedirs(records_dir, exist_ok=True)
        orig = os.path.join(records_dir, "2026.log")
        conf = os.path.join(records_dir,
                "2026.sync-conflict-20260911-113533-XAJ7GJU.log")
        with open(orig, "w") as f:
            f.write("2026-01-01 type=expense amount=10\n")
        with open(conf, "w") as f:
            f.write("2026-01-01 type=expense amount=20\n")
        orig_rel = os.path.relpath(orig, ptos.BASE_DIR).replace("\\", "/")
        conf_rel = os.path.relpath(conf, ptos.BASE_DIR).replace("\\", "/")
        result = diff_records_conflict(orig_rel, conf_rel)
        assert result["edit_conflicts"] == []
        assert len(result["hints"]) == 1
        assert "amount=10" in result["hints"][0][0]
        assert "amount=20" in result["hints"][0][1]
        assert result["lines_only_in_conflict"] == [
            "2026-01-01 type=expense amount=20"]

    def test_same_id_is_an_edit_candidate(self):
        records_dir = ptos.RECORDS_DIR
        os.makedirs(records_dir, exist_ok=True)
        orig = os.path.join(records_dir, "2026.log")
        conf = os.path.join(records_dir,
                 "2026.sync-conflict-20260911-113533-XAJ7GJU.log")
        with open(orig, "w") as f:
            f.write("2026-01-01 type=expense id=abc amount=10\n")
        with open(conf, "w") as f:
            f.write("2026-01-01 type=expense id=abc amount=20\n")
        orig_rel = os.path.relpath(orig, ptos.BASE_DIR).replace("\\", "/")
        conf_rel = os.path.relpath(conf, ptos.BASE_DIR).replace("\\", "/")
        result = diff_records_conflict(orig_rel, conf_rel)
        assert len(result["edit_conflicts"]) == 1
        assert "amount=10" in result["edit_conflicts"][0][0]
        assert "amount=20" in result["edit_conflicts"][0][1]

    def test_identical_files(self):
        records_dir = ptos.RECORDS_DIR
        os.makedirs(records_dir, exist_ok=True)
        orig = os.path.join(records_dir, "2026.log")
        conf = os.path.join(records_dir,
                "2026.sync-conflict-20260911-113533-XAJ7GJU.log")
        content = "2026-01-01 type=expense amount=10\n"
        with open(orig, "w") as f:
            f.write(content)
        with open(conf, "w") as f:
            f.write(content)
        orig_rel = os.path.relpath(orig, ptos.BASE_DIR).replace("\\", "/")
        conf_rel = os.path.relpath(conf, ptos.BASE_DIR).replace("\\", "/")
        result = diff_records_conflict(orig_rel, conf_rel)
        assert len(result["lines_only_in_conflict"]) == 0
        assert len(result["lines_only_in_original"]) == 0
        assert len(result["edit_conflicts"]) == 0


class TestDiffTodosConflict:
    def _write_todo(self, path, lines):
        with open(path, "w") as f:
            f.write("\n".join(lines) + "\n" if lines else "")

    def test_identical_todos(self):
        todo_dir = ptos.TODO_DIR
        os.makedirs(todo_dir, exist_ok=True)
        orig = os.path.join(todo_dir, "todo.txt")
        conf = os.path.join(todo_dir,
                "todo.sync-conflict-20260827-111614-K4BHCH2.txt")
        self._write_todo(orig, ["(A) Buy milk", "(B) Buy eggs"])
        self._write_todo(conf, ["(A) Buy milk", "(B) Buy eggs"])
        orig_rel = os.path.relpath(orig, ptos.BASE_DIR).replace("\\", "/")
        conf_rel = os.path.relpath(conf, ptos.BASE_DIR).replace("\\", "/")
        result = diff_todos_conflict(orig_rel, conf_rel)
        assert len(result["identical"]) == 2
        assert len(result["edit_conflicts"]) == 0
        assert len(result["only_in_conflict"]) == 0
        assert len(result["only_in_original"]) == 0

    def test_edit_conflicts(self):
        todo_dir = ptos.TODO_DIR
        os.makedirs(todo_dir, exist_ok=True)
        orig = os.path.join(todo_dir, "todo.txt")
        conf = os.path.join(todo_dir,
                "todo.sync-conflict-20260827-111614-K4BHCH2.txt")
        self._write_todo(orig, ["(A) Buy milk due:2026-09-01"])
        self._write_todo(conf, ["(B) Buy milk due:2026-08-15"])
        orig_rel = os.path.relpath(orig, ptos.BASE_DIR).replace("\\", "/")
        conf_rel = os.path.relpath(conf, ptos.BASE_DIR).replace("\\", "/")
        result = diff_todos_conflict(orig_rel, conf_rel)
        assert len(result["edit_conflicts"]) == 1
        orig_t, conf_t = result["edit_conflicts"][0]
        assert orig_t.priority == "A"
        assert conf_t.priority == "B"

    def test_unique_in_conflict(self):
        todo_dir = ptos.TODO_DIR
        os.makedirs(todo_dir, exist_ok=True)
        orig = os.path.join(todo_dir, "todo.txt")
        conf = os.path.join(todo_dir,
                "todo.sync-conflict-20260827-111614-K4BHCH2.txt")
        self._write_todo(orig, ["(A) Buy milk"])
        self._write_todo(conf, ["(A) Buy milk", "(B) Buy eggs"])
        orig_rel = os.path.relpath(orig, ptos.BASE_DIR).replace("\\", "/")
        conf_rel = os.path.relpath(conf, ptos.BASE_DIR).replace("\\", "/")
        result = diff_todos_conflict(orig_rel, conf_rel)
        assert len(result["only_in_conflict"]) == 1
        assert result["only_in_conflict"][0].priority == "B"

    def test_superset(self):
        todo_dir = ptos.TODO_DIR
        os.makedirs(todo_dir, exist_ok=True)
        orig = os.path.join(todo_dir, "done.txt")
        conf = os.path.join(todo_dir,
                "done.sync-conflict-20260827-111614-K4BHCH2.txt")
        self._write_todo(orig, [
            "x 2026-01-01 Task one",
            "x 2026-01-02 Task two",
            "x 2026-01-03 Task three",
        ])
        self._write_todo(conf, [
            "x 2026-01-01 Task one",
            "x 2026-01-02 Task two",
        ])
        orig_rel = os.path.relpath(orig, ptos.BASE_DIR).replace("\\", "/")
        conf_rel = os.path.relpath(conf, ptos.BASE_DIR).replace("\\", "/")
        result = diff_todos_conflict(orig_rel, conf_rel)
        assert len(result["only_in_original"]) == 1
        assert len(result["only_in_conflict"]) == 0
        assert len(result["edit_conflicts"]) == 0


class TestDoctorReportsConflicts:
    def test_conflict_warning(self):
        records_dir = ptos.RECORDS_DIR
        os.makedirs(records_dir, exist_ok=True)
        with open(os.path.join(records_dir,
                 "2026.sync-conflict-20260911-113533-XAJ7GJU.log"), "w") as f:
            f.write("")
        errors, warnings, messages, fixes = ptos.doctor_check()
        conflict_warnings = [w for w in warnings if "sync conflict" in w.lower()]
        assert len(conflict_warnings) >= 1


class TestConflictsPageRenders:
    @staticmethod
    def _client():
        from ptos_web import app
        return app.test_client()

    def test_records_conflict_renders_actions(self):
        records_dir = ptos.RECORDS_DIR
        os.makedirs(records_dir, exist_ok=True)
        with open(os.path.join(records_dir, "2026.log"), "w") as f:
            f.write("2026-01-01 type=expense id=abc amount=10\n")
        with open(os.path.join(records_dir,
                 "2026.sync-conflict-20260911-113533-XAJ7GJU.log"), "w") as f:
            f.write("2026-01-01 type=expense id=abc amount=99\n")
        resp = self._client().get("/conflicts")
        assert resp.status_code == 200
        html = resp.get_data(as_text=True)
        assert "Add" in html
        assert "Replace" in html
        assert "Skip" in html
        assert "loop.parent" not in html
        assert 'data-filetype="records"' in html
        assert "conflict-row" in html

    def test_todo_edit_conflict_renders(self):
        todo_dir = ptos.TODO_DIR
        os.makedirs(todo_dir, exist_ok=True)
        with open(os.path.join(todo_dir, "todo.txt"), "w") as f:
            f.write("(A) Buy milk due:2026-01-05\n")
        with open(os.path.join(todo_dir,
                 "todo.sync-conflict-20260827-111614-K4BHCH2.txt"), "w") as f:
            f.write("(B) Buy milk due:2026-01-06\n")
        resp = self._client().get("/conflicts")
        assert resp.status_code == 200
        assert "resolveTodoChoice" in resp.get_data(as_text=True)


class TestConflictFilterRecords:
    def test_get_log_files_excludes_conflict(self):
        records_dir = ptos.RECORDS_DIR
        os.makedirs(records_dir, exist_ok=True)
        with open(os.path.join(records_dir, "2026.log"), "w") as f:
            f.write("data\n")
        with open(os.path.join(records_dir,
                 "2026.sync-conflict-20260911.log"), "w") as f:
            f.write("conflict data\n")
        files = ptos.get_log_files()
        assert "2026.log" in files
        assert all("conflict" not in f.lower() for f in files)

    def test_list_dir_excludes_conflict(self):
        notes_dir = ptos.NOTES_DIR
        os.makedirs(notes_dir, exist_ok=True)
        with open(os.path.join(notes_dir, "meeting.md"), "w") as f:
            f.write("# Meeting\n")
        with open(os.path.join(notes_dir,
                 "meeting.sync-conflict-20260911.md"), "w") as f:
            f.write("# Conflict\n")
        result = ptos.list_dir("")
        names = [f["name"] for f in result["files"]]
        assert "meeting.md" in names
        assert not any("conflict" in n.lower() for n in names)


def _write(rel_or_dir, name, content):
    os.makedirs(rel_or_dir, exist_ok=True)
    with open(os.path.join(rel_or_dir, name), "w", encoding="utf-8") as f:
        f.write(content)


def _records_conflict():
    """A records conflict with one edit conflict and one unique line."""
    _write(ptos.RECORDS_DIR, "2026.log",
           "2026-01-01 type=expense amount=10\n"
           "2026-01-05 type=income amount=50\n")
    _write(ptos.RECORDS_DIR, "2026.sync-conflict-20260911-113533-XAJ7GJU.log",
           "2026-01-01 type=expense amount=99\n"
           "2026-01-08 type=expense amount=7\n")
    orig = "records/2026.log"
    conf = "records/2026.sync-conflict-20260911-113533-XAJ7GJU.log"
    return orig, conf


def _todo_conflict():
    _write(ptos.TODO_DIR, "todo.txt",
           "(A) Buy milk due:2026-01-05\nCall bob\n")
    _write(ptos.TODO_DIR, "todo.sync-conflict-20260827-111614-K4BHCH2.txt",
           "(B) Buy milk due:2026-01-06\nEmail alice\n")
    orig = "todo/todo.txt"
    conf = "todo/todo.sync-conflict-20260827-111614-K4BHCH2.txt"
    return orig, conf


def _read(rel):
    with open(os.path.join(ptos.BASE_DIR, rel), encoding="utf-8") as f:
        return f.read()


class TestLineScopedResolution:
    def test_keep_original_keeps_unique_lines(self):
        orig, conf = _records_conflict()
        key = "2026-01-01 type=expense amount=99"
        resolved = ptos.resolve_edit_conflict(orig, conf, key, None, "records")
        assert resolved is False
        assert os.path.exists(os.path.join(ptos.BASE_DIR, conf))
        orig_text = _read(orig)
        assert "2026-01-01 type=expense amount=10" in orig_text
        assert "amount=99" not in orig_text
        assert "2026-01-08 type=expense amount=7" in _read(conf)

    def test_replace_replaces_not_duplicates(self):
        orig, conf = _records_conflict()
        ptos.replace_conflict_line(
            orig, conf, "2026-01-01 type=expense amount=99",
            "2026-01-01 type=expense amount=10", "records")
        text = open(os.path.join(ptos.BASE_DIR, orig), encoding="utf-8").read()
        assert "amount=99" in text
        assert "amount=10" not in text
        assert text.count("2026-01-01 type=expense amount=99") == 1

    def test_import_selected_finalizes_when_all_resolved(self):
        orig, conf = _records_conflict()
        ptos.resolve_edit_conflict(
            orig, conf, "2026-01-01 type=expense amount=99", None, "records")
        resolved = ptos.import_conflict_lines(
            orig, conf, ["2026-01-08 type=expense amount=7"], "records")
        assert resolved is True
        assert not os.path.exists(os.path.join(ptos.BASE_DIR, conf))
        text = open(os.path.join(ptos.BASE_DIR, orig), encoding="utf-8").read()
        assert "2026-01-08 type=expense amount=7" in text
        assert "amount=10" in text

    def test_import_selected_keeps_file_when_edits_remain(self):
        orig, conf = _records_conflict()
        resolved = ptos.import_conflict_lines(
            orig, conf, ["2026-01-08 type=expense amount=7"], "records")
        assert resolved is False
        assert os.path.exists(os.path.join(ptos.BASE_DIR, conf))
        assert "2026-01-01 type=expense amount=99" in open(
            os.path.join(ptos.BASE_DIR, conf), encoding="utf-8").read()

    def test_import_all_appends_and_never_replaces(self):
        orig, conf = _records_conflict()
        ptos.import_all_conflict(orig, conf, "records")
        assert not os.path.exists(os.path.join(ptos.BASE_DIR, conf))
        text = open(os.path.join(ptos.BASE_DIR, orig), encoding="utf-8").read()
        assert "amount=99" in text
        assert "amount=10" in text  # the original line is never removed
        assert "2026-01-08 type=expense amount=7" in text
        assert text.count("amount=99") == 1

    def test_todo_edit_conflict_line_scoped(self):
        orig, conf = _todo_conflict()
        resolved = ptos.resolve_todo_edit_conflict(
            orig, conf, "Buy milk", "original", "todo")
        assert resolved is False
        assert os.path.exists(os.path.join(ptos.BASE_DIR, conf))
        assert "Buy milk due:2026-01-06" not in open(
            os.path.join(ptos.BASE_DIR, conf), encoding="utf-8").read()
        ptos.import_conflict_lines(orig, conf, ["Email alice"], "todo")
        assert not os.path.exists(os.path.join(ptos.BASE_DIR, conf))
        text = open(os.path.join(ptos.BASE_DIR, orig), encoding="utf-8").read()
        assert "Buy milk due:2026-01-05" in text
        assert "Email alice" in text


class TestConflictApiLineScoped:
    def _client(self):
        from ptos_web import app
        return app.test_client()

    def _post(self, payload):
        return self._client().post("/api/conflict/resolve", json=payload)

    def test_edit_record_keep_original_preserves_unique(self):
        orig, conf = _records_conflict()
        d = self._post({
            "action": "edit_record",
            "conflict_path": conf,
            "original_path": orig,
            "file_type": "records",
            "line": "2026-01-01 type=expense amount=99",
            "choice": "original",
        })
        data = d.get_json()
        assert data["ok"] is True
        assert data["resolved"] is False
        assert os.path.exists(os.path.join(ptos.BASE_DIR, conf))
        text = open(os.path.join(ptos.BASE_DIR, orig), encoding="utf-8").read()
        assert "amount=10" in text and "amount=99" not in text

    def test_replace_record_then_import_finalizes(self):
        orig, conf = _records_conflict()
        d = self._post({
            "action": "replace_record",
            "conflict_path": conf,
            "original_path": orig,
            "file_type": "records",
            "line": "2026-01-01 type=expense amount=99",
            "target": "2026-01-01 type=expense amount=10",
        })
        assert d.get_json()["resolved"] is False
        text = open(os.path.join(ptos.BASE_DIR, orig), encoding="utf-8").read()
        assert text.count("amount=99") == 1 and "amount=10" not in text
        d = self._post({
            "action": "import_records",
            "conflict_path": conf,
            "original_path": orig,
            "file_type": "records",
            "lines": ["2026-01-08 type=expense amount=7"],
        })
        assert d.get_json()["resolved"] is True
        assert not os.path.exists(os.path.join(ptos.BASE_DIR, conf))

    def test_skip_record_removes_without_import(self):
        orig, conf = _records_conflict()
        d = self._post({
            "action": "skip_record",
            "conflict_path": conf,
            "original_path": orig,
            "file_type": "records",
            "line": "2026-01-01 type=expense amount=99",
        })
        assert d.get_json()["resolved"] is False
        text = open(os.path.join(ptos.BASE_DIR, orig), encoding="utf-8").read()
        assert "amount=99" not in text and "amount=10" in text


class TestCliResolveRecordConflict:
    def _conflict(self, orig_lines, conf_lines):
        _write(ptos.RECORDS_DIR, "2026.log", "".join(l + "\n" for l in orig_lines))
        _write(ptos.RECORDS_DIR,
               "2026.sync-conflict-20260911-113533-XAJ7GJU.log",
               "".join(l + "\n" for l in conf_lines))
        return "records/2026.log", "records/2026.sync-conflict-20260911-113533-XAJ7GJU.log"

    def test_replace_is_explicit_and_finalizes(self, monkeypatch):
        import ptos_cli
        orig, conf = self._conflict(
            ["2026-01-01 type=expense id=abc amount=10"],
            ["2026-01-01 type=expense id=abc amount=99"])
        c = {"original_path": orig, "conflict_path": conf, "file_type": "records"}
        orig_full = os.path.join(ptos.BASE_DIR, orig)
        conf_full = os.path.join(ptos.BASE_DIR, conf)
        monkeypatch.setattr("builtins.input", lambda *a: "r")
        imported, skipped = ptos_cli._resolve_record_conflict(c, orig_full, conf_full)
        text = open(orig_full, encoding="utf-8").read()
        assert text.count("amount=99") == 1
        assert "amount=10" not in text
        assert imported == 1 and skipped == 0
        assert not os.path.exists(conf_full)

    def test_plain_conflict_defaults_to_add(self, monkeypatch):
        import ptos_cli
        orig, conf = self._conflict(
            ["2026-01-01 type=expense amount=10"],
            ["2026-01-08 type=expense amount=7"])
        c = {"original_path": orig, "conflict_path": conf, "file_type": "records"}
        orig_full = os.path.join(ptos.BASE_DIR, orig)
        conf_full = os.path.join(ptos.BASE_DIR, conf)
        monkeypatch.setattr("builtins.input", lambda *a: "")
        imported, skipped = ptos_cli._resolve_record_conflict(c, orig_full, conf_full)
        text = open(orig_full, encoding="utf-8").read()
        assert "2026-01-08 type=expense amount=7" in text
        assert "amount=10" in text
        assert imported == 1 and skipped == 0
        assert not os.path.exists(conf_full)

    def test_same_id_add_keeps_both(self, monkeypatch):
        import ptos_cli
        orig, conf = self._conflict(
            ["2026-01-01 type=expense id=abc amount=10"],
            ["2026-01-01 type=expense id=abc amount=99"])
        c = {"original_path": orig, "conflict_path": conf, "file_type": "records"}
        orig_full = os.path.join(ptos.BASE_DIR, orig)
        conf_full = os.path.join(ptos.BASE_DIR, conf)
        monkeypatch.setattr("builtins.input", lambda *a: "a")
        imported, skipped = ptos_cli._resolve_record_conflict(c, orig_full, conf_full)
        text = open(orig_full, encoding="utf-8").read()
        assert "amount=10" in text and "amount=99" in text
        assert imported == 1
        assert not os.path.exists(conf_full)
