import os
import datetime as dt
from urllib.parse import quote
import ptos
import ptos_cli
import ptos_service as svc
import pytest


def _write_records(lines, year=None):
    os.makedirs(ptos.RECORDS_DIR, exist_ok=True)
    if year is None:
        year = dt.date.today().year
    with open(os.path.join(ptos.RECORDS_DIR, f"{year}.log"),
              "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def _clean_cache():
    ptos._CACHE.clear()


def _records_content():
    path = os.path.join(ptos.RECORDS_DIR, f"{dt.date.today().year}.log")
    with open(path, encoding="utf-8") as f:
        return f.read()


def _convert(argv, monkeypatch, answer="y"):
    items = ["ptos"] + list(argv)
    monkeypatch.setattr("sys.argv", items)
    monkeypatch.setattr("builtins.input", lambda _: answer)
    ptos_cli.main()


class TestConvertDraft:
    def _draft(self, line, target, **kw):
        _clean_cache()
        return svc.convert_draft(line, 0, target, **kw)

    def test_missing_required_listed(self):
        draft = self._draft("2026-09-05 type=capture tag=inbox | walked 30 min",
                            "exercise")
        assert draft["source_type"] == "capture"
        assert draft["target_type"] == "exercise"
        assert draft["date"] == "2026-09-05"
        assert draft["note"] == "walked 30 min"
        assert sorted(draft["missing_required"]) == ["activity", "duration"]
        assert "tag = inbox" in draft["new_line"] or "tag=inbox" in draft["new_line"]
        assert "type=exercise" in draft["new_line"]

    def test_overrides_fill_required(self):
        draft = self._draft("2026-09-05 type=capture | walked",
                            "exercise",
                            kv_overrides={"activity": "walk", "duration": "30"})
        assert draft["missing_required"] == []
        assert "activity=walk" in draft["new_line"]
        assert "duration=30" in draft["new_line"]

    def test_same_type_raises(self):
        with pytest.raises(svc.PTOSError):
            self._draft("2026-09-05 type=capture | x", "capture")

    def test_unknown_type_raises(self):
        with pytest.raises(svc.PTOSError):
            self._draft("2026-09-05 type=capture | x", "bogus_type")

    def test_tag_carry_add_del(self):
        draft = self._draft("2026-09-05 type=capture tag=inbox,work | x",
                            "exercise",
                            tag_add=["later"], tag_del=["work"])
        tags = [t.strip() for t in draft["draft"]["tag"]]
        assert tags == ["inbox", "later"]
        assert "tag=inbox" in draft["new_line"]
        assert "tag=later" in draft["new_line"]

    def test_id_links_never_copy(self):
        draft = self._draft("2026-09-05 type=capture id=ab12 links=expense:cd34 | x",
                            "exercise",
                            kv_overrides={"activity": "walk", "duration": "30"})
        assert "id=" not in draft["new_line"]
        assert "links=" not in draft["new_line"]

    def test_shared_fields_copied(self):
        draft = self._draft("2026-09-05 type=expense domain=self category=food "
                            "amount=50 pay_method=card | groceries",
                            "income")
        assert draft["draft"].get("amount") == "50"
        assert "domain" not in draft["draft"]
        assert "pay_method" not in draft["draft"]
        assert "income" in draft["missing_required"] or "source" in draft["missing_required"]

    def test_date_note_overrides(self):
        draft = self._draft("2026-09-05 type=capture | walked",
                            "exercise",
                            kv_overrides={"date": "2026-01-01", "note": "custom"})
        assert draft["new_line"].startswith("2026-01-01 ")
        assert draft["new_line"].endswith("| custom")

    def test_blank_override_removes_field(self):
        draft = self._draft("2026-09-05 type=expense domain=self category=food "
                            "amount=50 | groceries",
                            "income", kv_overrides={"amount": ""})
        assert "amount=" not in draft["new_line"]


class TestConvertRecord:
    def _source(self):
        _clean_cache()
        _write_records(["2026-09-05 type=capture tag=inbox | walked 30 min"])
        path = os.path.join(ptos.RECORDS_DIR, f"{dt.date.today().year}.log")
        return path, "2026-09-05 type=capture tag=inbox | walked 30 min", 0

    def test_appends_and_deletes_source(self):
        path, line, lineno = self._source()
        res = svc.convert_record(path, line, lineno, "exercise",
                                 kv_overrides={"activity": "walk", "duration": "30"})
        assert res["ok"] is True
        assert res["source_deleted"] is True
        content = _records_content()
        assert "type=exercise" in content
        assert "activity=walk" in content
        assert "type=capture" not in content

    def test_keep_true_keeps_source(self):
        path, line, lineno = self._source()
        res = svc.convert_record(path, line, lineno, "exercise", keep=True,
                                 kv_overrides={"activity": "walk", "duration": "30"})
        assert res["source_deleted"] is False
        content = _records_content()
        assert content.count("\n") == 2  # two lines
        assert "type=exercise" in content
        assert "type=capture" in content

    def test_blocked_missing_required_no_write(self):
        path, line, lineno = self._source()
        with pytest.raises(svc.PTOSError):
            svc.convert_record(path, line, lineno, "exercise")
        content = _records_content()
        assert "type=exercise" not in content
        assert content.count("\n") == 1

    def test_same_type_blocked(self):
        path, line, lineno = self._source()
        with pytest.raises(svc.PTOSError):
            svc.convert_record(path, line, lineno, "capture")

    def test_invalid_filepath_rejected(self):
        _clean_cache()
        _write_records(["2026-09-05 type=capture | x"])
        with pytest.raises(svc.PTOSError):
            svc.convert_record(r"C:\outside\tmp.log", "2026-09-05 type=capture | x", 0,
                               "exercise",
                               kv_overrides={"activity": "walk", "duration": "30"})

    def test_invalidates_history_cache(self):
        path, line, lineno = self._source()
        _clean_cache()
        svc.get_history_suggestions("exercise")
        assert any(k.startswith("history:") for k in ptos._CACHE)
        svc.convert_record(path, line, lineno, "exercise",
                           kv_overrides={"activity": "walk", "duration": "30"})
        assert not any(k.startswith("history:") for k in ptos._CACHE)


class TestSuggestConvertType:
    def test_coffee_suggests_expense(self):
        _clean_cache()
        res = svc.suggest_convert_type("bought coffee $45")
        assert res and res[0]["type"] == "expense"
        assert res[0]["pct"] == 100

    def test_salary_monthly_bonus_suggests_income(self):
        _clean_cache()
        res = svc.suggest_convert_type("salary monthly bonus")
        assert res and res[0]["type"] == "income"

    def test_gibberish_empty(self):
        _clean_cache()
        assert svc.suggest_convert_type("asdf qwerty zxcv") == []

    def test_empty_text_empty(self):
        _clean_cache()
        assert svc.suggest_convert_type("") == []

    def test_sorted_by_score_desc(self):
        _clean_cache()
        res = svc.suggest_convert_type("coffee salary monthly bonus snacks")
        scores = [r["score"] for r in res]
        assert scores == sorted(scores, reverse=True)

    def test_deterministic(self):
        _clean_cache()
        a = svc.suggest_convert_type("coffee salary monthly bonus snacks")
        b = svc.suggest_convert_type("coffee salary monthly bonus snacks")
        assert a == b


class TestScrapeConvertFields:
    def test_amount_extraction(self):
        _clean_cache()
        res = svc.scrape_convert_fields("bought coffee $45 @work", "expense")
        assert res["fields"]["amount"] == "45"

    def test_option_value_fills_field(self):
        _clean_cache()
        res = svc.scrape_convert_fields("paid self for food", "expense")
        assert res["fields"]["domain"] == "self"

    def test_tag_tokens_collected(self):
        _clean_cache()
        res = svc.scrape_convert_fields("+groceries #urgent", "expense")
        assert res["fields"]["tag"] == ["groceries", "urgent"]

    def test_fields_only_filled_when_found(self):
        _clean_cache()
        res = svc.scrape_convert_fields("totally unrelated words", "expense")
        assert "amount" not in res["fields"]
        assert "domain" not in res["fields"]
        assert res["history_defaults"] == {}

    def test_history_defaults_only_valid_options(self):
        _clean_cache()
        _write_records([
            "2026-09-01 type=expense domain=work category=food amount=10 | a",
            "2026-09-02 type=expense domain=work category=food amount=20 | b",
            "2026-09-03 type=expense domain=self category=food amount=30 | c",
        ])
        _clean_cache()
        res = svc.scrape_convert_fields("grabbed lunch", "expense")
        assert res["history_defaults"].get("domain") == "work"

    def test_history_default_skipped_when_field_mentioned(self):
        _clean_cache()
        _write_records([
            "2026-09-01 type=expense domain=work category=food amount=10 | a",
            "2026-09-02 type=expense domain=work category=food amount=20 | b",
        ])
        _clean_cache()
        res = svc.scrape_convert_fields("grabbed lunch self", "expense")
        assert "domain" not in res["history_defaults"]
        assert res["fields"]["domain"] == "self"


class TestConvertCli:
    def test_suggestion_mode_auto_pick_and_convert(self, monkeypatch, capsys):
        _clean_cache()
        _write_records(["2026-09-05 type=capture tag=inbox | bought coffee $45"])
        _convert(["--convert", "type=capture",
                  "--set", "domain=work", "category=food", "amount=45"],
                 monkeypatch)
        out = capsys.readouterr().out
        assert "expense (" in out or "expense" in out
        assert "Converted:" in out
        content = _records_content()
        assert "type=expense" in content
        assert "domain=work" in content and "category=food" in content and "amount=45" in content
        assert "type=capture" not in content

    def test_explicit_target_and_keep(self, monkeypatch, capsys):
        _clean_cache()
        _write_records(["2026-09-05 type=capture tag=inbox | walked"])
        _convert(["--convert", "type=capture", "exercise",
                  "--set", "activity=walk", "duration=30",
                  "--keep"],
                 monkeypatch)
        out = capsys.readouterr().out
        assert "(source record will be deleted)" not in out
        content = _records_content()
        assert content.count("\n") == 2
        assert "type=exercise" in content
        assert "type=capture" in content

    def test_missing_required_blocks_before_write(self, monkeypatch, capsys):
        _clean_cache()
        _write_records(["2026-09-05 type=capture | walked"])
        _convert(["--convert", "type=capture", "exercise"], monkeypatch)
        out = capsys.readouterr().out
        assert "[blocked]" in out
        assert "Converted:" not in out
        assert "type=exercise" not in _records_content()

    def test_conversion_confirmation_denied(self, monkeypatch, capsys):
        _clean_cache()
        _write_records(["2026-09-05 type=capture | walked"])
        _convert(["--convert", "type=capture", "exercise",
                  "--set", "activity=walk", "duration=30"],
                 monkeypatch, answer="n")
        out = capsys.readouterr().out
        assert "Cancelled." in out
        assert "type=exercise" not in _records_content()

    def test_requires_a_filter(self, monkeypatch):
        _clean_cache()
        monkeypatch.setattr("sys.argv", ["ptos", "--convert", "expense"])
        with pytest.raises(SystemExit) as exc:
            ptos_cli.main()
        assert "filter" in str(exc.value.code)

    def test_target_without_filter_rejected(self, monkeypatch):
        _clean_cache()
        monkeypatch.setattr("sys.argv", ["ptos", "--convert", "exercise"])
        with pytest.raises(SystemExit) as exc:
            ptos_cli.main()
        assert "filter" in str(exc.value.code).lower()

    def test_no_matches(self, monkeypatch, capsys):
        _clean_cache()
        _write_records(["2026-09-05 type=capture | walked"])
        _convert(["--convert", "tag=never", "exercise"], monkeypatch, answer="y")
        out = capsys.readouterr().out
        assert "No records found" in out

    def test_backlink_warning_on_delete(self, monkeypatch, capsys):
        _clean_cache()
        _write_records([
            "2026-09-05 type=capture id=ab12 | walked",
            "2026-09-05 type=expense domain=work category=food amount=20 "
            "links=capture:ab12 | pays for it",
        ])
        _convert(["--convert", "type=capture", "exercise",
                  "--set", "activity=walk", "duration=30"], monkeypatch)
        out = capsys.readouterr().out
        assert "link to capture:ab12" in out
        assert "will become dangling" in out


class TestConvertWeb:
    def test_edit_convert_get(self):
        _clean_cache()
        _write_records(["2026-09-05 type=capture tag=inbox | bought coffee $45"])
        path = os.path.join(ptos.RECORDS_DIR, f"{dt.date.today().year}.log")
        line = "2026-09-05 type=capture tag=inbox | bought coffee $45"
        from ptos_web import app
        client = app.test_client()
        resp = client.get("/edit?convert=1&filepath=" + quote(path)
                          + "&lineno=0&line=" + quote(line) + "&return_to=/")
        assert resp.status_code == 200
        data = resp.get_data(as_text=True)
        assert "Convert Record" in data
        assert "CONVERTING CAPTURE" in data
        assert 'value="expense"' in data
        assert 'name="convert"' in data and 'value="1"' in data
        assert 'name="remove_original"' in data

    def test_edit_convert_post_default_removes_source(self):
        _clean_cache()
        _write_records(["2026-09-05 type=capture tag=inbox | walked"])
        path = os.path.join(ptos.RECORDS_DIR, f"{dt.date.today().year}.log")
        old_line = "2026-09-05 type=capture tag=inbox | walked"
        from ptos_web import app
        client = app.test_client()
        resp = client.post("/edit", data={
            "convert": "1", "filepath": path, "old_line": old_line,
            "lineno": "0", "return_to": "/browse",
            "type": "exercise", "activity": "walk", "duration": "30",
        }, follow_redirects=True)
        assert resp.status_code == 200
        content = _records_content()
        assert "type=exercise" in content
        assert "type=capture" not in content

    def test_edit_convert_post_keep_original(self):
        _clean_cache()
        _write_records(["2026-09-05 type=capture tag=inbox | walked"])
        path = os.path.join(ptos.RECORDS_DIR, f"{dt.date.today().year}.log")
        old_line = "2026-09-05 type=capture tag=inbox | walked"
        from ptos_web import app
        client = app.test_client()
        resp = client.post("/edit", data={
            "convert": "1", "filepath": path, "old_line": old_line,
            "lineno": "0", "return_to": "/browse",
            "type": "exercise", "activity": "walk", "duration": "30",
            "remove_original": "",
        }, follow_redirects=True)
        assert resp.status_code == 200
        content = _records_content()
        assert "type=exercise" in content
        assert "type=capture" in content

    def test_edit_convert_post_missing_required_rerenders_error(self):
        _clean_cache()
        _write_records(["2026-09-05 type=capture tag=inbox | walked"])
        path = os.path.join(ptos.RECORDS_DIR, f"{dt.date.today().year}.log")
        old_line = "2026-09-05 type=capture tag=inbox | walked"
        from ptos_web import app
        client = app.test_client()
        resp = client.post("/edit", data={
            "convert": "1", "filepath": path, "old_line": old_line,
            "lineno": "0", "return_to": "/browse",
            "type": "exercise",
        }, follow_redirects=True)
        assert resp.status_code == 200
        data = resp.get_data(as_text=True)
        assert "blocked" in data.lower() or "requires" in data.lower()
        assert "type=exercise" not in _records_content()

    def test_edit_convert_get_prefill_amount_from_source(self):
        _clean_cache()
        _write_records(["2026-09-05 type=capture | bought coffee $45"])
        path = os.path.join(ptos.RECORDS_DIR, f"{dt.date.today().year}.log")
        line = "2026-09-05 type=capture | bought coffee $45"
        from ptos_web import app
        client = app.test_client()
        resp = client.get("/edit?convert=1&filepath=" + quote(path)
                          + "&lineno=0&line=" + quote(line) + "&return_to=/")
        assert resp.status_code == 200
        data = resp.get_data(as_text=True)
        assert 'value="45"' in data

    def test_edit_convert_post_empty_note_clears(self):
        _clean_cache()
        _write_records(["2026-09-05 type=capture | walked 30 min"])
        path = os.path.join(ptos.RECORDS_DIR, f"{dt.date.today().year}.log")
        old_line = "2026-09-05 type=capture | walked 30 min"
        from ptos_web import app
        client = app.test_client()
        resp = client.post("/edit", data={
            "convert": "1", "filepath": path, "old_line": old_line,
            "lineno": "0", "return_to": "/browse",
            "type": "exercise", "activity": "walk", "duration": "30",
            "note": "",
        }, follow_redirects=True)
        assert resp.status_code == 200
        content = _records_content()
        assert "type=exercise" in content
        assert "walked 30 min" not in content


class TestStripScrapedNote:
    def test_basic_strip(self):
        scrape = {"strip_spans": [(14, 17)]}
        result = svc.strip_scraped_note("bought coffee $45", scrape)
        assert result == "bought coffee"

    def test_connector_both_sides_dropped(self):
        scrape = {"strip_spans": [(15, 18)]}
        result = svc.strip_scraped_note("had dinner for $45 with friends", scrape)
        assert result == "had dinner friends"

    def test_connector_single_side_kept(self):
        scrape = {"strip_spans": [(19, 22)]}
        result = svc.strip_scraped_note("bought coffee with $45", scrape)
        assert result == "bought coffee with"

    def test_empty_after_strip_returns_none(self):
        scrape = {"strip_spans": [(0, 14)]}
        result = svc.strip_scraped_note("bought coffee", scrape)
        assert result is None

    def test_no_spans_returns_note(self):
        scrape = {"strip_spans": []}
        result = svc.strip_scraped_note("unchanged text", scrape)
        assert result == "unchanged text"

    def test_none_note_returns_none(self):
        result = svc.strip_scraped_note(None, {"strip_spans": [(0, 5)]})
        assert result is None

    def test_currency_rs(self):
        _clean_cache()
        res = svc.scrape_convert_fields("lunch rs 69", "expense")
        assert res["fields"]["amount"] == "69"
        assert len(res["strip_spans"]) == 1

    def test_duplicate_number_only_matched_once(self):
        _clean_cache()
        res = svc.scrape_convert_fields("bought 45 items for $45", "expense")
        assert res["fields"]["amount"] == "45"
        spans = res["strip_spans"]
        assert len(spans) == 1
        matched_text = "bought 45 items for $45"[spans[0][0]:spans[0][1]]
        assert matched_text == "$45"


class TestConvertDraftStrip:
    def test_strip_by_default(self):
        _clean_cache()
        draft = svc.convert_draft("2026-09-05 type=capture tag=inbox | bought coffee $45",
                                  0, "expense",
                                  kv_overrides={"domain": "self", "category": "food",
                                                "amount": "45"})
        assert draft["note"] == "bought coffee"
        assert "$45" not in draft["note"]

    def test_strip_false_keeps_note(self):
        _clean_cache()
        draft = svc.convert_draft("2026-09-05 type=capture tag=inbox | bought coffee $45",
                                  0, "expense",
                                  kv_overrides={"domain": "self", "category": "food",
                                                "amount": "45"},
                                  strip_note=False)
        assert draft["note"] == "bought coffee $45"

    def test_explicit_note_override_wins(self):
        _clean_cache()
        draft = svc.convert_draft("2026-09-05 type=capture | bought coffee $45",
                                  0, "expense",
                                  kv_overrides={"domain": "self", "category": "food",
                                                "amount": "45", "note": "my custom note"})
        assert draft["note"] == "my custom note"

    def test_blank_note_override_clears(self):
        _clean_cache()
        draft = svc.convert_draft("2026-09-05 type=capture | bought coffee $45",
                                  0, "expense",
                                  kv_overrides={"domain": "self", "category": "food",
                                                "amount": "45", "note": ""})
        assert draft["note"] == ""

    def test_empty_note_no_strip(self):
        _clean_cache()
        draft = svc.convert_draft("2026-09-05 type=capture | ", 0, "expense",
                                  kv_overrides={"domain": "self"})
        assert draft["note"] == ""

    def test_connector_rule_strips_both_sides(self):
        _clean_cache()
        draft = svc.convert_draft("2026-09-05 type=capture | had coffee for $45 with snacks",
                                  0, "expense",
                                  kv_overrides={"amount": "45"})
        assert "for" not in draft["note"]
        assert "with" not in draft["note"]
        assert draft["note"] == "had coffee snacks"

    def test_connector_single_side_kept(self):
        _clean_cache()
        draft = svc.convert_draft("2026-09-05 type=capture | bought coffee $45 with snacks",
                                  0, "expense",
                                  kv_overrides={"amount": "45"})
        assert "with" in draft["note"]
        assert draft["note"] == "bought coffee with snacks"

    def test_option_field_stripped(self):
        _clean_cache()
        draft = svc.convert_draft("2026-09-05 type=capture | food meeting rs 69",
                                  0, "expense",
                                  kv_overrides={"domain": "work", "category": "food",
                                                "amount": "69"})
        assert "food" not in draft["note"]
        assert draft["note"] == "meeting"

    def test_idempotent_strip(self):
        _clean_cache()
        draft1 = svc.convert_draft("2026-09-05 type=capture | bought coffee $45",
                                   0, "expense",
                                   kv_overrides={"amount": "45"})
        draft2 = svc.convert_draft("2026-09-05 type=capture | bought coffee",
                                   0, "expense",
                                   kv_overrides={"amount": ""})
        assert draft1["note"] == draft2["note"]

    def test_real_world_example(self):
        _clean_cache()
        draft = svc.convert_draft(
            "2026-09-05 type=capture | had coffee and tea with food megha for rs 69 with snacks appam and kozhukatta",
            0, "expense",
            kv_overrides={"domain": "work", "category": "food", "amount": "69"})
        assert "food" not in draft["note"]
        assert "rs" not in draft["note"]
        assert draft["note"] == "had coffee and tea with megha snacks appam and kozhukatta"