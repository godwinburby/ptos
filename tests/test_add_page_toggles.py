import re
from html.parser import HTMLParser
from pathlib import Path

import ptos

TEMPLATE = Path(__file__).resolve().parents[1] / "web_templates" / "add.html"
VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input",
        "link", "meta", "param", "source", "track", "wbr"}


class _Tree(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.nodes = []
        self.stack = []
        self.tok = 0

    def handle_starttag(self, tag, attrs):
        self.tok += 1
        node = {"tag": tag, "attrs": dict(attrs), "start": self.tok,
                "end": None, "text": []}
        self.nodes.append(node)
        if tag not in VOID:
            self.stack.append(node)

    def handle_endtag(self, tag):
        self.tok += 1
        for i in range(len(self.stack) - 1, -1, -1):
            if self.stack[i]["tag"] == tag:
                while len(self.stack) > i:
                    node = self.stack.pop()
                    node["end"] = self.tok
                    if self.stack:
                        self.stack[-1]["text"].extend(node["text"])
                break

    def handle_data(self, data):
        if self.stack:
            self.stack[-1]["text"].append(data)

    def close(self):
        super().close()
        while self.stack:
            node = self.stack.pop()
            node["end"] = self.tok
            if self.stack:
                self.stack[-1]["text"].extend(node["text"])

    def by_id(self, element_id):
        matches = [n for n in self.nodes if n["attrs"].get("id") == element_id]
        assert len(matches) == 1, f"expected one #{element_id}, got {len(matches)}"
        return matches[0]

    def by_data_name(self, name):
        return [n for n in self.nodes
                if n["tag"] == "button" and n["attrs"].get("data-name") == name]

    def text_of(self, node):
        return " ".join("".join(node["text"]).split())

    def has_class(self, node, cls):
        return cls in (node["attrs"].get("class") or "").split()


def _write_presets(multi=True):
    presets_path = Path(ptos.PRESETS_PATH)
    presets_path.parent.mkdir(parents=True, exist_ok=True)
    body = (
        '[presets.exercise]\n'
        'type = "habit"\n'
        'name = "exercise"\n'
        'instant = true\n'
    )
    if multi:
        body += (
            '\n[presets.commute]\n'
            'records = ["auto", "bus"]\n'
            '\n[presets.auto]\n'
            'type = "expense"\n'
            'domain = "self"\n'
            'category = "transport"\n'
            'amount = 60\n'
            '\n[presets.bus]\n'
            'type = "expense"\n'
            'domain = "self"\n'
            'category = "transport"\n'
            'amount = 30\n'
        )
    presets_path.write_text(body, encoding="utf-8")
    ptos._invalidate("presets")


def _add_html():
    from ptos_web import app
    client = app.test_client()
    resp = client.get("/add")
    assert resp.status_code == 200
    return resp.get_data(as_text=True)


class TestTemplateToggles:
    def test_no_style_display_toggles(self):
        src = TEMPLATE.read_text(encoding="utf-8")
        assert "style.display" not in src

    def test_toggle_targets_hidden_then_revealed_by_class(self):
        src = TEMPLATE.read_text(encoding="utf-8")
        for element_id in ("paste-result", "threshold-match-area", "preset-msg",
                           "preset-dialog", "multi-msg-add"):
            tag = re.search(rf'<[^>]*id="{element_id}"[^>]*>', src)
            assert tag, f"#{element_id} markup missing"
            assert "d-none" in tag.group(0)
        assert src.count('id="multi-msg-add"') == 1
        assert "box.classList.remove('d-none')" in src
        assert 'area.classList.remove("d-none")' in src
        assert 'area.classList.add("d-none")' in src
        assert 'dlg.classList.remove("d-none")' in src
        assert 'document.getElementById("preset-dialog").classList.add("d-none")' in src
        assert 'msg.classList.remove("d-none")' in src
        assert 'msg.classList.add("d-none")' in src
        assert 'document.getElementById("preset-msg").classList.add("d-none")' in src

    def test_preset_dialog_is_flex_when_shown(self):
        src = TEMPLATE.read_text(encoding="utf-8")
        tag = re.search(r'<[^>]*id="preset-dialog"[^>]*>', src).group(0)
        assert "d-flex" in tag


class TestPresetsCard:
    def test_presets_are_in_their_own_card_above_the_type_card(self, tmp_path, monkeypatch):
        _write_presets(multi=True)
        tree = _Tree()
        tree.feed(_add_html())
        tree.close()

        presets = tree.by_id("presets-card")
        assert tree.has_class(presets, "card")
        assert "QUICK PRESETS" in tree.text_of(presets)
        assert "MULTI PRESETS" in tree.text_of(presets)

        frequent = tree.by_id("frequent-presets")
        assert presets["start"] < frequent["start"]
        assert frequent["end"] < presets["end"]

        multi = tree.by_data_name("commute")
        assert len(multi) == 1
        assert presets["start"] < multi[0]["start"] < presets["end"]

        type_card = [n for n in tree.nodes
                     if tree.has_class(n, "card")
                     and "Select Record Type" in tree.text_of(n)]
        assert len(type_card) == 1
        type_card = type_card[0]
        assert presets["end"] < type_card["start"]
        for node in (frequent, multi[0], tree.by_id("multi-msg-add")):
            assert not (type_card["start"] < node["start"] < type_card["end"])

    def test_no_presets_renders_no_presets_card(self, tmp_path, monkeypatch):
        presets_path = Path(ptos.PRESETS_PATH)
        presets_path.parent.mkdir(parents=True, exist_ok=True)
        presets_path.write_text("", encoding="utf-8")
        ptos._invalidate("presets")
        html = _add_html()
        assert 'id="presets-card"' not in html
        assert 'id="frequent-presets"' not in html

    def test_instant_only_preset_still_defines_add_multi_preset(self, tmp_path, monkeypatch):
        _write_presets(multi=False)
        html = _add_html()
        assert 'data-name="exercise"' in html
        assert "function addMultiPreset(" in html
        assert 'id="presets-card"' in html
