import os
import re

import pytest


def _write(path, text):
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def _append(path, text):
    with open(path, "a", encoding="utf-8") as f:
        f.write(text)


class TestGenerateId:
    def test_length_and_alphabet(self):
        import ptos
        alphabet = set("abcdefghjkmnpqrstuvwxyz23456789")
        for _ in range(50):
            g = ptos.generate_id()
            assert len(g) == 6
            assert set(g) <= alphabet

    def test_no_confusable_chars(self):
        import ptos
        g = ptos.generate_id(200)
        assert "0" not in g and "o" not in g and "1" not in g and "l" not in g

    def test_ida_unique_in_practice(self):
        import ptos
        ids = {ptos.generate_id() for _ in range(200)}
        assert len(ids) == 200


class TestSplitLinkTarget:
    def test_valid(self):
        import ptos
        assert ptos.split_link_target("expense:k3f9a1") == ("expense", "k3f9a1")

    def test_journal(self):
        import ptos
        assert ptos.split_link_target("journal:2026-08-17") == ("journal", "2026-08-17")

    def test_case_insensitive_type(self):
        import ptos
        assert ptos.split_link_target("Expense:ABC") == ("expense", "ABC")

    def test_malformed(self):
        import ptos
        assert ptos.split_link_target("no-colon") is None
        assert ptos.split_link_target(":") is None
        assert ptos.split_link_target("expense:") is None
        assert ptos.split_link_target("") is None


class TestResolveLink:
    def test_record(self, tmp_path, monkeypatch):
        import ptos
        monkeypatch.setattr(ptos, "RECORDS_DIR", str(tmp_path / "records"))
        (tmp_path / "records").mkdir(exist_ok=True)
        _write(tmp_path / "records" / "2026.log",
               "2026-08-17 type=expense amount=450 category=food domain=self id=k3f9a1\n"
               "2026-08-17 type=income amount=450 source=salary id=ins9x\n")
        hit = ptos.resolve_link("expense:k3f9a1")
        assert hit is not None
        assert hit["kind"] == "record"
        assert hit["type"] == "expense"
        assert hit["id"] == "k3f9a1"
        assert hit["lineno"] == 0

    def test_record_missing(self, tmp_path, monkeypatch):
        import ptos
        monkeypatch.setattr(ptos, "RECORDS_DIR", str(tmp_path / "records"))
        (tmp_path / "records").mkdir(exist_ok=True)
        _write(tmp_path / "records" / "2026.log",
               "2026-08-17 type=expense amount=450 category=food domain=self id=k3f9a1\n")
        assert ptos.resolve_link("expense:nope") is None

    def test_todo_open(self, tmp_path, monkeypatch):
        import ptos
        monkeypatch.setattr(ptos, "TODO_PATH", str(tmp_path / "todo.txt"))
        monkeypatch.setattr(ptos, "DONE_PATH", str(tmp_path / "done.txt"))
        _write(tmp_path / "todo.txt", "(A) Call supplier id:t7c2b8 links:expense:k3f9a1\n")
        _write(tmp_path / "done.txt", "")
        hit = ptos.resolve_link("todo:t7c2b8")
        assert hit is not None
        assert hit["kind"] == "todo"
        assert hit["id"] == "t7c2b8"
        assert hit["lineno"] == 1

    def test_todo_done(self, tmp_path, monkeypatch):
        import ptos
        monkeypatch.setattr(ptos, "TODO_PATH", str(tmp_path / "todo.txt"))
        monkeypatch.setattr(ptos, "DONE_PATH", str(tmp_path / "done.txt"))
        _write(tmp_path / "todo.txt", "")
        _write(tmp_path / "done.txt", "x 2026-08-18 2026-08-17 Call supplier id:t7c2b8\n")
        hit = ptos.resolve_link("todo:t7c2b8")
        assert hit is not None
        assert hit["kind"] == "todo"
        assert hit["filepath"].endswith("done.txt")

    def test_todo_missing(self, tmp_path, monkeypatch):
        import ptos
        monkeypatch.setattr(ptos, "TODO_PATH", str(tmp_path / "todo.txt"))
        monkeypatch.setattr(ptos, "DONE_PATH", str(tmp_path / "done.txt"))
        _write(tmp_path / "todo.txt", "")
        _write(tmp_path / "done.txt", "")
        assert ptos.resolve_link("todo:nope") is None

    def test_journal_by_date(self, tmp_path, monkeypatch):
        import ptos
        monkeypatch.setattr(ptos, "JOURNAL_DIR", str(tmp_path / "journal"))
        jdir = tmp_path / "journal" / "2026" / "08"
        jdir.mkdir(parents=True, exist_ok=True)
        _write(jdir / "2026-08-17.md", "# 2026-08-17\n")
        hit = ptos.resolve_link("journal:2026-08-17")
        assert hit is not None
        assert hit["kind"] == "journal"
        assert hit["filepath"].endswith("2026-08-17.md")

    def test_journal_missing(self, tmp_path, monkeypatch):
        import ptos
        monkeypatch.setattr(ptos, "JOURNAL_DIR", str(tmp_path / "journal"))
        assert ptos.resolve_link("journal:1999-01-01") is None

    def test_id_must_be_whole_token(self, tmp_path, monkeypatch):
        import ptos
        monkeypatch.setattr(ptos, "TODO_PATH", str(tmp_path / "todo.txt"))
        monkeypatch.setattr(ptos, "DONE_PATH", str(tmp_path / "done.txt"))
        _write(tmp_path / "todo.txt", "Call about id:t7c2b8xtra\n")
        _write(tmp_path / "done.txt", "")
        assert ptos.resolve_link("todo:t7c2b8") is None


class TestListLinkIds:
    def test_dedupe_and_sort(self, tmp_path, monkeypatch):
        import ptos
        monkeypatch.setattr(ptos, "RECORDS_DIR", str(tmp_path / "records"))
        monkeypatch.setattr(ptos, "TODO_PATH", str(tmp_path / "todo.txt"))
        monkeypatch.setattr(ptos, "DONE_PATH", str(tmp_path / "done.txt"))
        (tmp_path / "records").mkdir(exist_ok=True)
        _write(tmp_path / "records" / "2026.log",
               "2026-08-17 type=expense amount=1 category=food domain=self id=b2\n"
               "2026-08-17 type=income amount=1 source=salary id=a1\n")
        _write(tmp_path / "todo.txt", "Call x id:t1\n")
        _write(tmp_path / "done.txt", "")
        targets = [i["target"] for i in ptos.list_link_ids()]
        assert targets == ["expense:b2", "income:a1", "todo:t1"]

    def test_no_ids_empty(self, tmp_path, monkeypatch):
        import ptos
        monkeypatch.setattr(ptos, "RECORDS_DIR", str(tmp_path / "records"))
        monkeypatch.setattr(ptos, "TODO_PATH", str(tmp_path / "todo.txt"))
        monkeypatch.setattr(ptos, "DONE_PATH", str(tmp_path / "done.txt"))
        (tmp_path / "records").mkdir(exist_ok=True)
        _write(tmp_path / "records" / "2026.log",
               "2026-08-17 type=expense amount=1 category=food domain=self\n")
        _write(tmp_path / "todo.txt", "Call x\n")
        _write(tmp_path / "done.txt", "")
        assert ptos.list_link_ids() == []


class TestCheckDanglingLinks:
    def test_dangling_record_link(self, tmp_path, monkeypatch):
        import ptos
        monkeypatch.setattr(ptos, "RECORDS_DIR", str(tmp_path / "records"))
        monkeypatch.setattr(ptos, "TODO_PATH", str(tmp_path / "todo.txt"))
        monkeypatch.setattr(ptos, "DONE_PATH", str(tmp_path / "done.txt"))
        (tmp_path / "records").mkdir(exist_ok=True)
        _write(tmp_path / "records" / "2026.log",
               "2026-08-17 type=expense amount=1 category=food domain=self "
               "id=k3f9a1 links=expense:zz99\n")
        _write(tmp_path / "todo.txt", "")
        _write(tmp_path / "done.txt", "")
        problems = ptos.check_dangling_links()
        assert len(problems) == 1
        assert problems[0]["error"] == "dangling link"
        assert problems[0]["target"] == "expense:zz99"
        assert problems[0]["kind"] == "record"

    def test_dangling_todo_link(self, tmp_path, monkeypatch):
        import ptos
        monkeypatch.setattr(ptos, "RECORDS_DIR", str(tmp_path / "records"))
        monkeypatch.setattr(ptos, "TODO_PATH", str(tmp_path / "todo.txt"))
        monkeypatch.setattr(ptos, "DONE_PATH", str(tmp_path / "done.txt"))
        (tmp_path / "records").mkdir(exist_ok=True)
        _write(tmp_path / "records" / "2026.log",
               "2026-08-17 type=expense amount=1 category=food domain=self id=k3f9a1\n")
        _write(tmp_path / "todo.txt", "Call supplier links:expense:zz99\n")
        _write(tmp_path / "done.txt", "")
        problems = ptos.check_dangling_links()
        assert len(problems) == 1
        assert problems[0]["target"] == "expense:zz99"
        assert problems[0]["kind"] == "todo"

    def test_duplicate_record_id(self, tmp_path, monkeypatch):
        import ptos
        monkeypatch.setattr(ptos, "RECORDS_DIR", str(tmp_path / "records"))
        monkeypatch.setattr(ptos, "TODO_PATH", str(tmp_path / "todo.txt"))
        monkeypatch.setattr(ptos, "DONE_PATH", str(tmp_path / "done.txt"))
        (tmp_path / "records").mkdir(exist_ok=True)
        _write(tmp_path / "records" / "2026.log",
               "2026-08-17 type=expense amount=1 category=food domain=self id=k3f9a1\n"
               "2026-08-18 type=expense amount=2 category=food domain=self id=k3f9a1\n")
        _write(tmp_path / "todo.txt", "")
        _write(tmp_path / "done.txt", "")
        dupes = [p for p in ptos.check_dangling_links() if p["error"] == "duplicate id"]
        assert len(dupes) == 1
        assert dupes[0]["target"] == "expense:k3f9a1"

    def test_duplicate_todo_id(self, tmp_path, monkeypatch):
        import ptos
        monkeypatch.setattr(ptos, "RECORDS_DIR", str(tmp_path / "records"))
        monkeypatch.setattr(ptos, "TODO_PATH", str(tmp_path / "todo.txt"))
        monkeypatch.setattr(ptos, "DONE_PATH", str(tmp_path / "done.txt"))
        (tmp_path / "records").mkdir(exist_ok=True)
        _write(tmp_path / "records" / "2026.log", "")
        _write(tmp_path / "todo.txt", "A id:t1\nB id:t1\n")
        _write(tmp_path / "done.txt", "")
        dupes = [p for p in ptos.check_dangling_links() if p["error"] == "duplicate id"]
        assert len(dupes) == 1
        assert dupes[0]["target"] == "todo:t1"

    def test_clean(self, tmp_path, monkeypatch):
        import ptos
        monkeypatch.setattr(ptos, "RECORDS_DIR", str(tmp_path / "records"))
        monkeypatch.setattr(ptos, "TODO_PATH", str(tmp_path / "todo.txt"))
        monkeypatch.setattr(ptos, "DONE_PATH", str(tmp_path / "done.txt"))
        (tmp_path / "records").mkdir(exist_ok=True)
        _write(tmp_path / "records" / "2026.log",
               "2026-08-17 type=expense amount=1 category=food domain=self id=k3f9a1\n")
        _write(tmp_path / "todo.txt", "Call supplier links:expense:k3f9a1\n")
        _write(tmp_path / "done.txt", "")
        assert ptos.check_dangling_links() == []


class TestAppendLinks:
    def test_record_merge_dedupe(self):
        import ptos
        line = "2026-08-17 type=expense amount=1 category=food domain=self links=expense:k3f9a1"
        out = ptos.append_links_to_line(line, ["income:ins9x", "expense:k3f9a1"])
        assert "links=expense:k3f9a1,income:ins9x" in out
        assert out.count("links=") == 1

    def test_record_append_new(self):
        import ptos
        line = "2026-08-17 type=expense amount=1 category=food domain=self"
        out = ptos.append_links_to_line(line, ["expense:k3f9a1"])
        assert out.endswith("links=expense:k3f9a1")

    def test_todo_merge(self):
        import ptos
        line = "(A) Call supplier links:expense:k3f9a1"
        out = ptos.append_links_to_todo_line(line, ["todo:t7c2b8"])
        assert "links:expense:k3f9a1,todo:t7c2b8" in out

    def test_todo_append_new(self):
        import ptos
        line = "(A) Call supplier"
        out = ptos.append_links_to_todo_line(line, ["expense:k3f9a1"])
        assert out == "(A) Call supplier links:expense:k3f9a1"


class TestAppendIds:
    def test_record_id_rewrites_in_place(self, tmp_path, monkeypatch):
        import ptos
        monkeypatch.setattr(ptos, "RECORDS_DIR", str(tmp_path / "records"))
        (tmp_path / "records").mkdir(exist_ok=True)
        p = tmp_path / "records" / "2026.log"
        raw = "2026-08-17 type=expense amount=1 category=food domain=self"
        _write(p, raw + "\n")
        new_id = ptos.append_record_id(str(p), 0, raw)
        assert len(new_id) == 6
        content = open(p, encoding="utf-8").read()
        assert f"id={new_id}" in content

    def test_record_id_raises_if_exists(self, tmp_path, monkeypatch):
        import ptos
        monkeypatch.setattr(ptos, "RECORDS_DIR", str(tmp_path / "records"))
        (tmp_path / "records").mkdir(exist_ok=True)
        p = tmp_path / "records" / "2026.log"
        raw = "2026-08-17 type=expense amount=1 category=food domain=self id=k3f9a1"
        _write(p, raw + "\n")
        with pytest.raises(ValueError):
            ptos.append_record_id(str(p), 0, raw)

    def test_todo_id_line(self):
        import ptos
        line, new_id = ptos.append_todo_id("(A) Call supplier")
        assert len(new_id) == 6
        assert line == f"(A) Call supplier id:{new_id}"

    def test_todo_id_raises_if_exists(self):
        import ptos
        with pytest.raises(ValueError):
            ptos.append_todo_id("(A) Call supplier id:t7c2b8")

    def test_todo_custom_id(self):
        import ptos
        line, new_id = ptos.append_todo_id("(A) Call supplier", "custom1")
        assert new_id == "custom1"
        assert line == "(A) Call supplier id:custom1"


class TestTodoRoundTrip:
    def test_parse_format_round_trip(self):
        import ptos_todo
        line = "(A) Call Mr Nair @phone +HearingAid due:2026-08-20 id:t7c2b8 links:project:p91a,expense:k3f9a1"
        t = ptos_todo.parse_todo_line(line, line_no=1)
        assert t.id == "t7c2b8"
        assert t.links == ["project:p91a", "expense:k3f9a1"]
        assert t.description == "Call Mr Nair"
        t2 = ptos_todo.parse_todo_line(ptos_todo.format_line(t), line_no=1)
        assert t2.id == t.id
        assert t2.links == t.links
        assert t2.description == t.description
        assert t2.priority == t.priority
        assert t2.projects == t.projects
        assert t2.contexts == t.contexts
        assert t2.due == t.due

    def test_parse_no_id_links(self):
        import ptos_todo
        t = ptos_todo.parse_todo_line("(A) Call Mr Nair", line_no=1)
        assert t.id is None
        assert t.links == []
        assert ptos_todo.format_line(t) == "(A) Call Mr Nair"

    def test_edit_todo_id_links(self, tmp_path, monkeypatch):
        import ptos
        import ptos_todo
        monkeypatch.setattr(ptos, "TODO_PATH", str(tmp_path / "todo.txt"))
        monkeypatch.setattr(ptos_todo, "TODO_PATH", str(tmp_path / "todo.txt"))
        p = tmp_path / "todo.txt"
        _write(p, "(A) Call supplier\n")
        t = ptos_todo.edit_todo(str(p), 1, {"id": "t7c2b8", "links": ["expense:k3f9a1"]})
        assert t.id == "t7c2b8"
        assert t.links == ["expense:k3f9a1"]
        content = open(p, encoding="utf-8").read()
        assert "id:t7c2b8" in content and "links:expense:k3f9a1" in content

    def test_batch_edit_todo_id(self, tmp_path, monkeypatch):
        import ptos
        import ptos_todo
        monkeypatch.setattr(ptos, "TODO_PATH", str(tmp_path / "todo.txt"))
        monkeypatch.setattr(ptos_todo, "TODO_PATH", str(tmp_path / "todo.txt"))
        p = tmp_path / "todo.txt"
        _write(p, "(A) Call supplier\n(B) Email client\n")
        ptos_todo.batch_edit_todos(str(p), [1, 2], {"id": "shared1"})
        content = open(p, encoding="utf-8").read()
        assert content.count("id:shared1") == 2

    def test_filter_linked_to(self, tmp_path, monkeypatch):
        import ptos
        import ptos_todo
        monkeypatch.setattr(ptos, "TODO_PATH", str(tmp_path / "todo.txt"))
        monkeypatch.setattr(ptos_todo, "TODO_PATH", str(tmp_path / "todo.txt"))
        p = tmp_path / "todo.txt"
        _write(p, "(A) One links:expense:k3f9a1\n(B) Two links:income:ins9x\n(C) Three\n")
        todos, _ = ptos_todo.load_todos(str(p))
        hits = ptos_todo.filter_todos(todos, linked_to="expense:k3f9a1")
        assert [t.line_no for t in hits] == [1]
        hits = ptos_todo.filter_todos(todos, linked_to=["expense:k3f9a1", "income:ins9x"])
        assert [t.line_no for t in hits] == [1, 2]

    def test_rewrite_line_by_number(self, tmp_path, monkeypatch):
        import ptos
        import ptos_todo
        monkeypatch.setattr(ptos, "TODO_PATH", str(tmp_path / "todo.txt"))
        monkeypatch.setattr(ptos_todo, "TODO_PATH", str(tmp_path / "todo.txt"))
        p = tmp_path / "todo.txt"
        _write(p, "(A) One\n(B) Two\n(C) Three\n")
        assert ptos_todo.rewrite_line_by_number(str(p), 2, "(B) Two id:t2") is True
        content = open(p, encoding="utf-8").read()
        assert "(B) Two id:t2" in content
        assert "(A) One" in content and "(C) Three" in content
        assert ptos_todo.rewrite_line_by_number(str(p), 2, "(B) Two id:t2") is False


class TestValidateAllowsIdLinks:
    def test_id_links_accepted(self, sample_schema):
        import ptos
        record = {"type": "expense", "domain": "self", "category": "food",
                  "amount": "50", "id": "k3f9a1", "links": "income:ins9x"}
        assert ptos.validate_record(sample_schema, record) == []


class TestBacklinksIncludeLinks:
    def test_record_links_backlink(self, tmp_path, monkeypatch):
        import ptos
        monkeypatch.setattr(ptos, "RECORDS_DIR", str(tmp_path / "records"))
        monkeypatch.setattr(ptos, "TODO_DIR", str(tmp_path / "todo"))
        monkeypatch.setattr(ptos, "TODO_PATH", str(tmp_path / "todo" / "todo.txt"))
        monkeypatch.setattr(ptos, "DONE_PATH", str(tmp_path / "todo" / "done.txt"))
        monkeypatch.setattr(ptos, "NOTES_DIR", str(tmp_path / "notes"))
        monkeypatch.setattr(ptos, "JOURNAL_DIR", str(tmp_path / "journal"))
        (tmp_path / "records").mkdir(exist_ok=True)
        (tmp_path / "todo").mkdir(exist_ok=True)
        (tmp_path / "notes").mkdir(exist_ok=True)
        (tmp_path / "journal").mkdir(exist_ok=True)
        _write(tmp_path / "records" / "2026.log",
               "2026-08-17 type=income amount=450 source=salary id=ins9x links=expense:k3f9a1\n")
        _write(tmp_path / "todo" / "todo.txt", "Call x id:t1 links:expense:k3f9a1\n")
        _write(tmp_path / "todo" / "done.txt", "")
        from ptos_service import get_backlinks
        bl = get_backlinks("expense:k3f9a1")
        assert len(bl["records"]) == 1
        assert bl["records"][0]["field"] == "links"
        assert len(bl["todo"]) == 1


class TestServiceLinks:
    def test_retro_id_record(self, tmp_path, monkeypatch):
        import ptos
        import ptos_service
        monkeypatch.setattr(ptos, "RECORDS_DIR", str(tmp_path / "records"))
        monkeypatch.setattr(ptos_service.ptos, "RECORDS_DIR", str(tmp_path / "records"))
        (tmp_path / "records").mkdir(exist_ok=True)
        p = tmp_path / "records" / "2026.log"
        _write(p, "2026-08-17 type=expense amount=1 category=food domain=self\n")
        res = ptos_service.retro_id_record(str(p), 0)
        assert res["ok"] is True
        assert res["target"] == "expense:" + res["id"]
        content = open(p, encoding="utf-8").read()
        assert f"id={res['id']}" in content
        with pytest.raises(ptos_service.PTOSError):
            ptos_service.retro_id_record(str(p), 0)

    def test_retro_id_todo(self, tmp_path, monkeypatch):
        import ptos
        import ptos_todo
        import ptos_service
        monkeypatch.setattr(ptos, "TODO_PATH", str(tmp_path / "todo.txt"))
        monkeypatch.setattr(ptos, "DONE_PATH", str(tmp_path / "done.txt"))
        monkeypatch.setattr(ptos_todo, "TODO_PATH", str(tmp_path / "todo.txt"))
        monkeypatch.setattr(ptos_todo, "DONE_PATH", str(tmp_path / "done.txt"))
        monkeypatch.setattr(ptos_service.ptos_todo, "TODO_PATH", str(tmp_path / "todo.txt"))
        monkeypatch.setattr(ptos_service, "TODO_PATH", str(tmp_path / "todo.txt"))
        monkeypatch.setattr(ptos_service, "DONE_PATH", str(tmp_path / "done.txt"))
        p = tmp_path / "todo.txt"
        _write(p, "(A) Call supplier\n")
        _write(tmp_path / "done.txt", "")
        res = ptos_service.retro_id_todo(1)
        assert res["target"] == "todo:" + res["id"]
        content = open(p, encoding="utf-8").read()
        assert f"id:{res['id']}" in content
        with pytest.raises(ptos_service.PTOSError):
            ptos_service.retro_id_todo(1)

    def test_link_entries_record_source(self, tmp_path, monkeypatch):
        import ptos
        import ptos_service
        monkeypatch.setattr(ptos, "RECORDS_DIR", str(tmp_path / "records"))
        monkeypatch.setattr(ptos_service.ptos, "RECORDS_DIR", str(tmp_path / "records"))
        monkeypatch.setattr(ptos, "TODO_PATH", str(tmp_path / "todo.txt"))
        monkeypatch.setattr(ptos_service.ptos, "TODO_PATH", str(tmp_path / "todo.txt"))
        monkeypatch.setattr(ptos, "DONE_PATH", str(tmp_path / "done.txt"))
        monkeypatch.setattr(ptos_service.ptos, "DONE_PATH", str(tmp_path / "done.txt"))
        (tmp_path / "records").mkdir(exist_ok=True)
        _write(tmp_path / "records" / "2026.log",
               "2026-08-17 type=income amount=450 source=salary id=ins9x\n"
               "2026-08-17 type=expense amount=450 category=food domain=self id=k3f9a1\n")
        _write(tmp_path / "todo.txt", "")
        _write(tmp_path / "done.txt", "")
        res = ptos_service.link_entries("income:ins9x", "expense:k3f9a1")
        assert res["ok"] is True
        assert res["resolves"] is True
        assert res["links"] == ["expense:k3f9a1"]
        content = open(tmp_path / "records" / "2026.log", encoding="utf-8").read()
        assert "links=expense:k3f9a1" in content

    def test_link_entries_todo_source(self, tmp_path, monkeypatch):
        import ptos
        import ptos_todo
        import ptos_service
        monkeypatch.setattr(ptos, "RECORDS_DIR", str(tmp_path / "records"))
        monkeypatch.setattr(ptos_service.ptos, "RECORDS_DIR", str(tmp_path / "records"))
        monkeypatch.setattr(ptos, "TODO_PATH", str(tmp_path / "todo.txt"))
        monkeypatch.setattr(ptos_service.ptos, "TODO_PATH", str(tmp_path / "todo.txt"))
        monkeypatch.setattr(ptos, "DONE_PATH", str(tmp_path / "done.txt"))
        monkeypatch.setattr(ptos_service.ptos, "DONE_PATH", str(tmp_path / "done.txt"))
        monkeypatch.setattr(ptos_service.ptos_todo, "TODO_PATH", str(tmp_path / "todo.txt"))
        (tmp_path / "records").mkdir(exist_ok=True)
        _write(tmp_path / "records" / "2026.log",
               "2026-08-17 type=expense amount=450 category=food domain=self id=k3f9a1\n")
        _write(tmp_path / "todo.txt", "(A) Call supplier id:t7c2b8\n")
        _write(tmp_path / "done.txt", "")
        res = ptos_service.link_entries("todo:t7c2b8", "expense:k3f9a1")
        assert res["ok"] is True
        content = open(tmp_path / "todo.txt", encoding="utf-8").read()
        assert "links:expense:k3f9a1" in content

    def test_link_entries_missing_source(self, tmp_path, monkeypatch):
        import ptos
        import ptos_service
        monkeypatch.setattr(ptos, "RECORDS_DIR", str(tmp_path / "records"))
        monkeypatch.setattr(ptos_service.ptos, "RECORDS_DIR", str(tmp_path / "records"))
        monkeypatch.setattr(ptos, "TODO_PATH", str(tmp_path / "todo.txt"))
        monkeypatch.setattr(ptos_service.ptos, "TODO_PATH", str(tmp_path / "todo.txt"))
        monkeypatch.setattr(ptos, "DONE_PATH", str(tmp_path / "done.txt"))
        monkeypatch.setattr(ptos_service.ptos, "DONE_PATH", str(tmp_path / "done.txt"))
        (tmp_path / "records").mkdir(exist_ok=True)
        _write(tmp_path / "records" / "2026.log", "")
        _write(tmp_path / "todo.txt", "")
        _write(tmp_path / "done.txt", "")
        with pytest.raises(ptos_service.PTOSError):
            ptos_service.link_entries("expense:nope", "expense:k3f9a1")

    def test_link_entries_unknown_target(self, tmp_path, monkeypatch):
        import ptos
        import ptos_service
        monkeypatch.setattr(ptos, "RECORDS_DIR", str(tmp_path / "records"))
        monkeypatch.setattr(ptos_service.ptos, "RECORDS_DIR", str(tmp_path / "records"))
        monkeypatch.setattr(ptos, "TODO_PATH", str(tmp_path / "todo.txt"))
        monkeypatch.setattr(ptos_service.ptos, "TODO_PATH", str(tmp_path / "todo.txt"))
        monkeypatch.setattr(ptos, "DONE_PATH", str(tmp_path / "done.txt"))
        monkeypatch.setattr(ptos_service.ptos, "DONE_PATH", str(tmp_path / "done.txt"))
        (tmp_path / "records").mkdir(exist_ok=True)
        _write(tmp_path / "records" / "2026.log",
               "2026-08-17 type=income amount=450 source=salary id=ins9x\n")
        _write(tmp_path / "todo.txt", "")
        _write(tmp_path / "done.txt", "")
        res = ptos_service.link_entries("income:ins9x", "expense:zz99")
        assert res["ok"] is True
        assert res["resolves"] is False


class TestLintIncludesLinks:
    def test_lint_records_flags_dangling(self, tmp_path, monkeypatch, capsys):
        import ptos
        monkeypatch.setattr(ptos, "RECORDS_DIR", str(tmp_path / "records"))
        monkeypatch.setattr(ptos, "TODO_PATH", str(tmp_path / "todo.txt"))
        monkeypatch.setattr(ptos, "DONE_PATH", str(tmp_path / "done.txt"))
        (tmp_path / "records").mkdir(exist_ok=True)
        _write(tmp_path / "records" / "2026.log",
               "2026-08-17 type=expense amount=1 category=food domain=self "
               "id=k3f9a1 links=expense:zz99\n")
        _write(tmp_path / "todo.txt", "")
        _write(tmp_path / "done.txt", "")
        results, _ = ptos.scan_records(ptos.dt.date.min, ptos.dt.date.max, [], None)
        schema = ptos.get_schema()
        error_files = ptos.lint_records(results, schema)
        out = capsys.readouterr().out
        assert "dangling link" in out
        assert any("2026.log" in f for f in error_files)

    def test_lint_all_records_includes_links(self, tmp_path, monkeypatch):
        import ptos
        monkeypatch.setattr(ptos, "RECORDS_DIR", str(tmp_path / "records"))
        monkeypatch.setattr(ptos, "TODO_PATH", str(tmp_path / "todo.txt"))
        monkeypatch.setattr(ptos, "DONE_PATH", str(tmp_path / "done.txt"))
        (tmp_path / "records").mkdir(exist_ok=True)
        _write(tmp_path / "records" / "2026.log",
               "2026-08-17 type=expense amount=1 category=food domain=self "
               "id=k3f9a1 links=expense:zz99\n")
        _write(tmp_path / "todo.txt", "")
        _write(tmp_path / "done.txt", "")
        res = ptos.lint_all_records()
        assert res["error_count"] >= 1
        link_errs = [e for e in res["errors"] if "dangling link" in " ".join(e["problems"])]
        assert len(link_errs) == 1


class TestTodoParserStarter:
    def test_id_links_tokens(self):
        import ptos_todo
        t = ptos_todo.parse_todo_line("Buy milk id:m1 links:expense:k3f9a1", line_no=3)
        assert t.id == "m1"
        assert t.links == ["expense:k3f9a1"]
        assert t.line_no == 3


def _link_env(tmp_path, monkeypatch, records="", todo="", done=""):
    import ptos
    monkeypatch.setattr(ptos, "RECORDS_DIR", str(tmp_path / "records"))
    monkeypatch.setattr(ptos, "TODO_PATH", str(tmp_path / "todo.txt"))
    monkeypatch.setattr(ptos, "DONE_PATH", str(tmp_path / "done.txt"))
    (tmp_path / "records").mkdir(exist_ok=True)
    (tmp_path / "todo").mkdir(exist_ok=True)
    _write(tmp_path / "records" / "2026.log", records)
    _write(tmp_path / "todo.txt", todo)
    _write(tmp_path / "done.txt", done)
    return ptos


class TestGenerateUniqueId:
    def test_avoids_existing_ids(self, tmp_path, monkeypatch):
        ptos = _link_env(tmp_path, monkeypatch,
                         records="2026-08-17 type=expense amount=1 category=food "
                                 "domain=self id=abc123\n",
                         todo="Call x id:t1\n")
        calls = {"n": 0}

        def fake(length=6):
            calls["n"] += 1
            return "abc123" if calls["n"] == 1 else "zzzz99"

        monkeypatch.setattr(ptos, "generate_id", fake)
        assert ptos.generate_unique_id() == "zzzz99"
        assert calls["n"] == 2

    def test_retries_then_sys_exit(self, tmp_path, monkeypatch):
        ptos = _link_env(tmp_path, monkeypatch,
                         records="2026-08-17 type=expense amount=1 category=food "
                                 "domain=self id=abc123\n")
        monkeypatch.setattr(ptos, "generate_id", lambda length=6: "abc123")
        with pytest.raises(SystemExit):
            ptos.generate_unique_id(max_attempts=3)

    def test_generates_when_clean(self, tmp_path, monkeypatch):
        ptos = _link_env(tmp_path, monkeypatch)
        assert len(ptos.generate_unique_id()) == 6


class TestCliAddLinkWarning:
    def _run_add(self, monkeypatch, *argv):
        import ptos_cli
        monkeypatch.setattr("sys.argv", ["ptos"] + list(argv))
        ptos_cli.main()

    def test_warns_on_unresolvable(self, tmp_path, monkeypatch, capsys):
        ptos = _link_env(tmp_path, monkeypatch,
                         records="2026-08-17 type=expense amount=1 category=food "
                                 "domain=self id=abc123\n")
        self._run_add(monkeypatch, "--add", "type=expense", "domain=self",
                      "category=food", "amount=50", "--link", "expense:zz99")
        out = capsys.readouterr().out
        assert "does not resolve" in out
        content = open(tmp_path / "records" / "2026.log", encoding="utf-8").read()
        assert "links=expense:zz99" in content

    def test_no_warning_when_resolves(self, tmp_path, monkeypatch, capsys):
        ptos = _link_env(tmp_path, monkeypatch,
                         records="2026-08-17 type=expense amount=1 category=food "
                                 "domain=self id=abc123\n")
        self._run_add(monkeypatch, "--add", "type=expense", "domain=self",
                      "category=food", "amount=50", "--link", "expense:abc123")
        out = capsys.readouterr().out
        assert "does not resolve" not in out
        content = open(tmp_path / "records" / "2026.log", encoding="utf-8").read()
        assert "links=expense:abc123" in content


class TestCliAddExplicitIdUniqueness:
    def test_duplicate_id_rejected(self, tmp_path, monkeypatch, capsys):
        import ptos_cli
        _link_env(tmp_path, monkeypatch,
                  records="2026-08-17 type=expense amount=1 category=food "
                          "domain=self id=abc123\n")
        monkeypatch.setattr("sys.argv", ["ptos", "--add", "type=income",
                                         "source=salary", "amount=100", "id=abc123"])
        with pytest.raises(SystemExit) as exc:
            ptos_cli.main()
        assert "already in use" in str(exc.value.code)
        content = open(tmp_path / "records" / "2026.log", encoding="utf-8").read()
        assert "source=salary" not in content


class TestSetIdLinksValidation:
    def test_set_id_duplicate_rejected(self, tmp_path, monkeypatch):
        ptos = _link_env(tmp_path, monkeypatch,
                         records="2026-08-17 type=expense amount=1 category=food "
                                 "domain=self id=abc123\n")
        line = "2026-08-18 type=income amount=100 source=salary"
        with pytest.raises(SystemExit):
            ptos.apply_set(line, ["id=abc123"], None)

    def test_set_own_id_allowed(self, tmp_path, monkeypatch):
        ptos = _link_env(tmp_path, monkeypatch,
                         records="2026-08-17 type=expense amount=1 category=food "
                                 "domain=self id=abc123\n")
        line = "2026-08-17 type=expense amount=1 category=food domain=self id=abc123"
        new_line, _ = ptos.apply_set(line, ["amount=2"], None)
        assert "id=abc123" in new_line
        new_line, _ = ptos.apply_set(line, ["id=abc123"], None)
        assert "id=abc123" in new_line

    def test_set_links_dangling_warns(self, tmp_path, monkeypatch, capsys):
        ptos = _link_env(tmp_path, monkeypatch)
        line = "2026-08-18 type=income amount=100 source=salary"
        new_line, _ = ptos.apply_set(line, ["links=expense:zz99"], None)
        assert "does not resolve" in capsys.readouterr().out
        assert "links=expense:zz99" in new_line

    def test_set_links_resolving_no_warning(self, tmp_path, monkeypatch, capsys):
        ptos = _link_env(tmp_path, monkeypatch,
                         records="2026-08-17 type=expense amount=1 category=food "
                                 "domain=self id=abc123\n")
        line = "2026-08-18 type=income amount=100 source=salary"
        new_line, _ = ptos.apply_set(line, ["links=expense:abc123"], None)
        assert "does not resolve" not in capsys.readouterr().out
        assert "links=expense:abc123" in new_line


class TestBacklinkRefs:
    def test_finds_record_and_todo(self, tmp_path, monkeypatch):
        ptos = _link_env(tmp_path, monkeypatch,
                         records="2026-08-17 type=expense amount=1 category=food "
                                 "domain=self id=abc123\n"
                                 "2026-08-18 type=income amount=100 source=salary "
                                 "links=expense:abc123\n",
                         todo="Call x links:expense:abc123\n")
        refs = ptos.backlink_refs("expense:abc123")
        assert len(refs) == 2
        assert {r["kind"] for r in refs} == {"record", "todo"}

    def test_empty(self, tmp_path, monkeypatch):
        ptos = _link_env(tmp_path, monkeypatch,
                         records="2026-08-17 type=expense amount=1 category=food "
                                 "domain=self id=abc123\n")
        assert ptos.backlink_refs("expense:abc123") == []

    def test_ignores_unrelated_links(self, tmp_path, monkeypatch):
        ptos = _link_env(tmp_path, monkeypatch,
                         records="2026-08-17 type=expense amount=1 category=food "
                                 "domain=self id=abc123\n"
                                 "2026-08-18 type=income amount=100 source=salary "
                                 "links=expense:other1\n")
        assert ptos.backlink_refs("expense:abc123") == []


class TestRunSetDeleteWarning:
    def test_warns_before_delete(self, tmp_path, monkeypatch, capsys):
        import datetime as dt
        ptos = _link_env(tmp_path, monkeypatch,
                         records="2026-08-17 type=expense amount=1 category=food "
                                 "domain=self id=abc123\n"
                                 "2026-08-18 type=income amount=100 source=salary "
                                 "links=expense:abc123\n")
        monkeypatch.setattr("builtins.input", lambda *a: "y")
        ptos.run_set([], dt.date.min, dt.date.max, None, None,
                     do_delete=True, do_all=True)
        out = capsys.readouterr().out
        assert "1 entry link to expense:abc123" in out
        assert "will become dangling" in out
        content = open(tmp_path / "records" / "2026.log", encoding="utf-8").read()
        assert "type=expense" not in content

    def test_no_warning_when_no_backlinks(self, tmp_path, monkeypatch, capsys):
        import datetime as dt
        ptos = _link_env(tmp_path, monkeypatch,
                         records="2026-08-17 type=expense amount=1 category=food "
                                 "domain=self id=abc123\n")
        monkeypatch.setattr("builtins.input", lambda *a: "y")
        ptos.run_set([], dt.date.min, dt.date.max, None, None,
                     do_delete=True, do_all=True)
        assert "will become dangling" not in capsys.readouterr().out


class TestTodoDeleteWarnings:
    def test_todo_done_warns(self, tmp_path, monkeypatch, capsys):
        import ptos_todo
        import ptos_cli
        ptos = _link_env(tmp_path, monkeypatch,
                         records="2026-08-17 type=income amount=100 source=salary "
                                 "links=todo:t7c2b8\n",
                         todo="(A) Call supplier id:t7c2b8\n")
        monkeypatch.setattr(ptos_todo, "TODO_PATH", str(tmp_path / "todo.txt"))
        monkeypatch.setattr(ptos_todo, "DONE_PATH", str(tmp_path / "done.txt"))
        ptos_cli._handle_todo_done("1")
        out = capsys.readouterr().out
        assert "will become dangling" in out
        assert "todo:t7c2b8" in out

    def test_todo_delete_warns(self, tmp_path, monkeypatch, capsys):
        import ptos_todo
        import ptos_cli
        ptos = _link_env(tmp_path, monkeypatch,
                         records="2026-08-17 type=income amount=100 source=salary "
                                 "links=todo:t7c2b8\n",
                         todo="(A) Call supplier id:t7c2b8\n")
        monkeypatch.setattr(ptos_todo, "TODO_PATH", str(tmp_path / "todo.txt"))
        monkeypatch.setattr(ptos_todo, "DONE_PATH", str(tmp_path / "done.txt"))
        ptos_cli._handle_todo_delete("1")
        out = capsys.readouterr().out
        assert "will become dangling" in out
        assert open(tmp_path / "todo.txt", encoding="utf-8").read() == ""

    def test_todo_done_delete_warns(self, tmp_path, monkeypatch, capsys):
        import ptos_todo
        import ptos_cli
        ptos = _link_env(tmp_path, monkeypatch,
                         records="2026-08-17 type=income amount=100 source=salary "
                                 "links=todo:t7c2b8\n",
                         done="x 2026-08-18 2026-08-17 Call supplier id:t7c2b8\n")
        monkeypatch.setattr(ptos_todo, "TODO_PATH", str(tmp_path / "todo.txt"))
        monkeypatch.setattr(ptos_todo, "DONE_PATH", str(tmp_path / "done.txt"))
        ptos_cli._handle_todo_done_delete("1")
        out = capsys.readouterr().out
        assert "will become dangling" in out
        assert open(tmp_path / "done.txt", encoding="utf-8").read() == ""

    def test_todo_done_no_warning_when_clean(self, tmp_path, monkeypatch, capsys):
        import ptos_todo
        import ptos_cli
        ptos = _link_env(tmp_path, monkeypatch, todo="(A) Call supplier id:t7c2b8\n")
        monkeypatch.setattr(ptos_todo, "TODO_PATH", str(tmp_path / "todo.txt"))
        monkeypatch.setattr(ptos_todo, "DONE_PATH", str(tmp_path / "done.txt"))
        ptos_cli._handle_todo_done("1")
        assert "will become dangling" not in capsys.readouterr().out


class TestRemoveTypeAwareness:
    def test_awareness_message(self, tmp_path, monkeypatch, capsys):
        ptos = _link_env(tmp_path, monkeypatch,
                         records="2026-08-17 type=expense amount=1 category=food "
                                 "domain=self id=abc123\n"
                                 "2026-08-18 type=expense amount=2 category=food "
                                 "domain=self\n")
        ptos.remove_type("expense")
        out = capsys.readouterr().out
        assert "2 existing records use type 'expense'" in out
        assert "id set on 1 of them" in out

    def test_no_message_when_unused(self, tmp_path, monkeypatch, capsys):
        ptos = _link_env(tmp_path, monkeypatch)
        ptos.remove_type("expense")
        assert "existing records use type 'expense'" not in capsys.readouterr().out
