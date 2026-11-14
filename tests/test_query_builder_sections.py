import re
from pathlib import Path

TEMPLATE = Path(__file__).resolve().parents[1] / "web_templates" / "query_builder.html"

SECTIONS = ["queries", "metrics", "dashboards", "aliases", "due", "boards",
            "habits", "calendars", "thresholds"]


def _render():
    from ptos_web import app
    client = app.test_client()
    resp = client.get("/query-builder")
    assert resp.status_code == 200
    return resp.get_data(as_text=True)


def _tag(html, element_id):
    m = re.search(rf'<div id="{element_id}"[^>]*>', html)
    assert m, f"#{element_id} markup missing"
    return m.group(0)


def _switch_body(src):
    m = re.search(r"function switchSection\(sec\)\s*\{(.*?)\n\}", src, re.S)
    assert m, "switchSection not found"
    return m.group(1)


class TestSectionStripsHiddenByClass:
    def test_non_query_strips_hide_with_d_none(self):
        html = _render()
        for sec in SECTIONS:
            if sec == "queries":
                continue
            tag = _tag(html, f"tabs-{sec}")
            assert "d-none" in tag, tag
            assert "display:none" not in tag, tag

    def test_queries_strip_starts_visible(self):
        tag = _tag(_render(), "tabs-queries")
        assert "d-none" not in tag
        assert "display:none" not in tag

    def test_switch_section_toggles_the_class(self):
        body = _switch_body(TEMPLATE.read_text(encoding="utf-8"))
        assert 'classList.toggle("d-none"' in body
        assert "style.display" not in body

    def test_every_tab_has_a_strip_and_is_switched(self):
        src = TEMPLATE.read_text(encoding="utf-8")
        tabs = set(re.findall(r'data-sec="([a-z]+)"', src))
        assert tabs == set(SECTIONS)
        strips = set(re.findall(r'<div id="tabs-([a-z]+)"', src))
        assert strips == tabs
        arr = re.search(r"\[([^\]]*)\]\.forEach", _switch_body(src))
        assert arr, "switchSection section list not found"
        switched = set(re.findall(r'"([a-z]+)"', arr.group(1)))
        assert switched == tabs


class TestDynamicVisibilityUsesClass:
    def test_board_overlap_area_hides_with_d_none(self):
        src = TEMPLATE.read_text(encoding="utf-8")
        m = re.search(r'<div id="board-overlap-area"[^>]*>', src)
        assert m, "#board-overlap-area markup missing"
        assert "d-none" in m.group(0)
        assert "display:none" not in m.group(0)
        assert 'area.classList.remove("d-none")' in src
        assert 'area.classList.add("d-none")' in src

    def test_threshold_numeric_input_hides_with_d_none(self):
        src = TEMPLATE.read_text(encoding="utf-8")
        assert 'id="thr-value-num" class="\'+(isNum?\'\':\'d-none\')+\'"' in src
        assert 'num.classList.remove("d-none")' in src
        assert 'num.classList.add("d-none")' in src

    def test_no_inline_display_none_left(self):
        src = TEMPLATE.read_text(encoding="utf-8")
        src = src.replace(".qb-section-bar::-webkit-scrollbar { display:none; }", "")
        assert "display:none" not in src
        assert "display: none" not in src
