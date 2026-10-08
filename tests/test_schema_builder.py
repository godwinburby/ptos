import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


class TestSchemaBuilderCollapsible:
    def test_type_editor_cards_collapsible(self):
        from ptos_web import app
        client = app.test_client()
        resp = client.get("/schema-builder")
        assert resp.status_code == 200
        html = resp.get_data(as_text=True)

        sections = re.findall(r'class="chip-section([^"]*)" style="border-top', html)
        assert len(sections) == 7

        assert sections.count("") == 4
        assert sections.count(" collapsed") == 3

        assert re.search(r'class="chip-section" style="border-top:3px solid var\(--success\);"', html)
        assert re.search(r'class="chip-section collapsed" style="border-top:3px solid var\(--warn\);"', html)
        assert re.search(r'class="chip-section collapsed" style="border-top:3px solid var\(--success\);"', html)

        assert html.count('onclick="toggleSection(this)"') == 7
        assert "function toggleSection(el)" in html

        for lid in ("fields-list", "tags-list",
                    "derived-fields-list", "conditions-list",
                    "global-fields-list", "shared-defs-list",
                    "global-derived-list"):
            assert f'id="{lid}"' in html


class TestSchemaBuilderSharedField:
    def test_add_field_offers_shared_conversion(self):
        from ptos_web import app
        client = app.test_client()
        html = client.get("/schema-builder").get_data(as_text=True)
        assert "convertToSharedField" in html
        assert "shared." in html

    def test_save_round_trip_use_field(self):
        import ptos
        from ptos_web import app
        client = app.test_client()
        payload = {
            "types": ["expense", "income"],
            "type_schemas": {
                "expense": {
                    "required": ["domain", "category", "amount"],
                    "fields": {
                        "domain": {"is_int": False, "options": ["self", "work"]},
                        "category": {"is_int": False, "options": ["food", "transport"]},
                        "amount": {"is_int": True},
                    },
                },
                "income": {
                    "required": ["source", "amount"],
                    "fields": {
                        "source": {"is_int": False, "options": [], "use": "shared.source"},
                        "amount": {"is_int": True},
                    },
                },
            },
            "global_fields": {},
            "shared_defs": {
                "source": {"is_int": False, "options": ["salary", "freelance"]},
            },
            "field_meta": {"amount": {"type": "int", "aggregatable": True,
                                      "dimension": True, "unit": "", "linkable": False}},
        }
        resp = client.post("/schema-builder/save", json=payload)
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["ok"] is True, data.get("error")
        schema = ptos.get_schema()
        assert schema["type"]["income"]["fields"]["source"]["use"] == "shared.source"
        assert schema["shared"]["source"]["options"] == ["salary", "freelance"]
        assert ptos.validate_schema_structure(schema) == []


class TestSchemaBuilderRawOptions:
    """Option values are stored as typed (trimmed), not lowercased/underscored."""

    def test_save_preserves_spaced_option_values(self):
        import ptos
        from ptos_web import app
        client = app.test_client()
        payload = {
            "types": ["expense"],
            "type_schemas": {
                "expense": {
                    "required": ["category"],
                    "fields": {
                        "category": {"is_int": False,
                                     "options": ["Big Bazaar", "corner shop"]},
                    },
                },
            },
            "global_fields": {
                "project": {"is_int": False, "options": ["Building B"]},
            },
            "shared_defs": {
                "method": {"is_int": False, "options": ["credit card"]},
            },
            "field_meta": {},
        }
        resp = client.post("/schema-builder/save", json=payload)
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["ok"] is True, data.get("error")
        schema = ptos.get_schema()
        assert schema["type"]["expense"]["fields"]["category"]["options"] == \
            ["Big Bazaar", "corner shop"]
        assert schema["global_fields"]["project"]["options"] == ["Building B"]
        assert schema["shared"]["method"]["options"] == ["credit card"]


class TestOptionAddersStoreRawValues:
    """Static guards: option-add handlers must not lowercase/underscore values."""

    _NORMALIZED = ("web_templates/schema_builder.html",
                   "web_templates/types.html",
                   "web_static/js/nav_chords.js")
    _ADDERS = {
        "web_templates/schema_builder.html": [
            "addOption", "addParentOpt", "addParentValue",
            "addGlobalOption", "addSharedOption",
        ],
        "web_templates/types.html": ["addOpt"],
        "web_static/js/nav_chords.js": ["addGlobalFieldOption", "addNewOption"],
    }

    def _body(self, rel, fn):
        src = (REPO_ROOT / rel).read_text(encoding="utf-8")
        m = re.search(r"function\s+" + re.escape(fn) + r"\s*\([^)]*\)\s*\{.*?\n\}",
                      src, re.DOTALL)
        assert m, f"{fn} not found in {rel}"
        return m.group(0)

    def test_adders_do_not_normalize(self):
        for rel, fns in self._ADDERS.items():
            for fn in fns:
                body = self._body(rel, fn)
                assert ".toLowerCase()" not in body, f"{fn} still lowercases in {rel}"
                assert ".replace(/\\s+/g" not in body, f"{fn} still underscores in {rel}"

    def test_tag_values_still_normalized(self):
        body = self._body("web_templates/schema_builder.html", "addTag")
        assert '.replace(/\\s+/g,"_")' in body
