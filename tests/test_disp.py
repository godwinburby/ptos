import os
import datetime as dt
import tomli_w
import ptos
import ptos_service as svc
from ptos_web import app

SCHEMA = {
    "types": {"allowed": ["disp_test"]},
    "type": {
        "disp_test": {
            "required": ["merchant"],
            "fields": {
                "merchant": {"options": ["Big_Bazaar", "Corner_Shop"]},
                "detail": {},
                "kind": {"options": ["food", "transport"]},
            },
            "tags": {
                "kind": {"options": {"transport": ["water_metro", "supermarket"]}},
            },
        }
    },
}


def _client():
    app.config["TESTING"] = True
    return app.test_client()


def _write_schema():
    with open(ptos.SCHEMA_PATH, "wb") as f:
        tomli_w.dump(SCHEMA, f)
    ptos._invalidate_all()


def _record_content():
    path = os.path.join(ptos.RECORDS_DIR, f"{dt.date.today().year}.log")
    if not os.path.exists(path):
        return ""
    with open(path, encoding="utf-8") as f:
        return f.read()


class TestDispFilterRegistered:
    def test_filter_still_converts_identifiers(self):
        assert app.jinja_env.filters["disp"]("Big_Bazaar") == "Big Bazaar"
        assert app.jinja_env.filters["disp"]("") == ""
        assert app.jinja_env.filters["disp"](None) == ""


class TestAddFormDisplay:
    def test_option_label_raw(self):
        _write_schema()
        html = _client().get("/add?type=disp_test").get_data(as_text=True)
        assert 'value="Big_Bazaar"' in html
        assert 'value="Corner_Shop"' in html
        assert "Big Bazaar" not in html
        assert "Corner Shop" not in html

    def test_free_text_input_spaced(self):
        _write_schema()
        html = _client().get("/add?type=disp_test&detail=Big%20Bazaar").get_data(as_text=True)
        assert 'name="detail"' in html
        assert 'value="Big Bazaar"' in html

    def test_id_and_links_stay_raw(self):
        _write_schema()
        html = _client().get(
            "/add?type=disp_test&id=abc_def&links=expense:xyz_123").get_data(as_text=True)
        assert 'value="abc_def"' in html
        assert 'value="expense:xyz_123"' in html
        assert 'value="abc def"' not in html

    def test_tag_label_raw(self):
        _write_schema()
        html = _client().get(
            "/add?type=disp_test&kind=transport").get_data(as_text=True)
        assert 'value="water_metro"' in html
        assert "water_metro" in html
        assert "water metro" not in html
        assert 'value="supermarket"' in html


class TestEditFormDisplay:
    def test_option_label_raw(self):
        _write_schema()
        line = "2026-01-02 type=disp_test merchant=Big_Bazaar detail=Big_Bazaar"
        html = _client().get(
            "/edit?filepath=x&lineno=0&line=" + line).get_data(as_text=True)
        assert 'value="Big_Bazaar"' in html
        assert "Big Bazaar" not in html

    def test_free_text_input_spaced(self):
        _write_schema()
        line = '2026-01-02 type=disp_test merchant=Big_Bazaar detail="Corner Market"'
        html = _client().get(
            "/edit?filepath=x&lineno=0&line=" + line).get_data(as_text=True)
        assert 'value="Corner Market"' in html


class TestRoundTrip:
    def test_posted_spaced_value_stored_quoted(self):
        _write_schema()
        _client().post("/add", data={
            "type": "disp_test",
            "merchant": "Big_Bazaar",
            "detail": "Big Bazaar",
            "date": "2026-01-02",
            "return_to": "/",
        })
        content = _record_content()
        assert 'detail="Big Bazaar"' in content
        assert "detail=Big Bazaar" not in content


class TestRecordRowsRaw:
    """Record-table values are shown exactly as stored — no `_` -> space."""

    def _seed(self, line):
        path = os.path.join(ptos.RECORDS_DIR, "2026.log")
        with open(path, "a", encoding="utf-8") as f:
            f.write(line + "\n")
        ptos._invalidate_all()

    def test_row_values_raw(self):
        _write_schema()
        self._seed("2026-01-02 type=disp_test merchant=Big_Bazaar detail=Big_Bazaar")
        data = svc.get_records(["type=disp_test"], time="all")
        assert len(data["records"]) == 1
        row = data["records"][0]
        assert row["merchant"] == "Big_Bazaar"
        assert row["detail"] == "Big_Bazaar"

    def test_group_label_raw(self):
        _write_schema()
        self._seed("2026-01-02 type=disp_test merchant=Big_Bazaar detail=Corner_Shop")
        data = svc.get_group(["type=disp_test"], time="all", group_fields=["detail"])
        labels = [r["key"] for r in data["rows"]]
        assert "Corner_Shop" in labels
        assert "Corner Shop" not in labels


class TestFilterBuilderRawAndQuoted:
    """Chips show raw values; a value with spaces is quoted in the expression."""

    def _src(self):
        path = os.path.join(os.path.dirname(ptos.__file__),
                            "web_static", "js", "filter_builder.js")
        with open(path, encoding="utf-8") as f:
            return f.read()

    def test_no_disp_helper_and_raw_chip_text(self):
        src = self._src()
        assert "function disp(" not in src
        assert "b.textContent=opt;" in src
        assert "b.textContent=v;" in src
        assert "b.textContent=tag;" in src

    def test_quotes_values_in_expression(self):
        src = self._src()
        assert "function _q(" in src
        assert "c.field+c.op+_q(c.value)" in src
        assert "_chipsToExpr" in src