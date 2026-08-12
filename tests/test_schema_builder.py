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
