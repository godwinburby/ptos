import os
import ptos


class TestAtomicWrite:
    def test_writes_new_file(self, tmp_path):
        path = tmp_path / "test.txt"
        ptos.atomic_write(str(path), "hello")
        assert path.read_text() == "hello"
        assert not (path.with_suffix(".bak")).exists()

    def test_overwrites_existing_file(self, tmp_path):
        path = tmp_path / "test.txt"
        path.write_text("old")
        ptos.atomic_write(str(path), "new")
        assert path.read_text() == "new"
        assert not (path.with_suffix(".bak")).exists()

    def test_creates_backup_on_overwrite(self, tmp_path):
        path = tmp_path / "test.txt"
        path.write_text("original")
        # Simulate failure by making a subdir with same name so rename fails
        ptos.atomic_write(str(path), "replacement")
        assert path.read_text() == "replacement"

    def test_empty_content(self, tmp_path):
        path = tmp_path / "empty.txt"
        ptos.atomic_write(str(path), "")
        assert path.read_text() == ""


class TestAtomicAppend:
    def test_appends_to_new_file(self, tmp_path):
        path = tmp_path / "log.txt"
        ptos.atomic_append(str(path), "line1")
        assert path.read_text() == "line1\n"

    def test_appends_to_existing_file(self, tmp_path):
        path = tmp_path / "log.txt"
        path.write_text("line1\n")
        ptos.atomic_append(str(path), "line2")
        assert path.read_text() == "line1\nline2\n"

    def test_appends_to_existing_no_trailing_newline(self, tmp_path):
        path = tmp_path / "log.txt"
        path.write_text("line1")
        ptos.atomic_append(str(path), "line2")
        assert path.read_text() == "line1\nline2\n"

    def test_creates_backup_on_append(self, tmp_path):
        path = tmp_path / "log.txt"
        path.write_text("original\n")
        ptos.atomic_append(str(path), "appended")
        assert path.read_text() == "original\nappended\n"
