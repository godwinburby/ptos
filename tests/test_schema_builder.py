import re


class TestSchemaBuilderCollapsible:
    def test_type_editor_cards_collapsible(self):
        from ptos_web import app
        client = app.test_client()
        resp = client.get("/schema-builder")
        assert resp.status_code == 200
        html = resp.get_data(as_text=True)

        sections = re.findall(r'class="chip-section([^"]*)" style="border-top', html)
        assert len(sections) == 8

        assert sections.count("") == 2
        assert sections.count(" collapsed") == 6

        assert re.search(r'class="chip-section" style="border-top:3px solid var\(--accent\);"', html)
        assert re.search(r'class="chip-section" style="border-top:3px solid var\(--success\);"', html)
        assert re.search(r'class="chip-section collapsed" style="border-top:3px solid var\(--warn\);"', html)
        assert re.search(r'class="chip-section collapsed" style="border-top:3px solid var\(--accent\);"', html)
        assert re.search(r'class="chip-section collapsed" style="border-top:3px solid var\(--success\);"', html)

        assert html.count('onclick="toggleSection(this)"') == 8
        assert "function toggleSection(el)" in html

        for lid in ("required-chips", "fields-list", "tags-list",
                    "derived-fields-list", "conditions-list",
                    "global-fields-list", "shared-defs-list", "field-meta-list"):
            assert f'id="{lid}"' in html


class TestSchemaBuilderSharedField:
    def test_add_field_offers_shared_prompt(self):
        from ptos_web import app
        client = app.test_client()
        html = client.get("/schema-builder").get_data(as_text=True)
        assert "Use options from a shared definition" in html
        assert 'ts().fields[name] = { is_int: false, options: [], use: "shared." + sname, linkable: false }' in html

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
