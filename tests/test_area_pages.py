"""
Tests for area schema field, folder template, and nav entry.
"""
import os
import tempfile
import shutil
import pytest


class TestAreaSchemaField:
    def test_schema_loads_area_field(self, _isolated_ptos_paths):
        import ptos
        schema = ptos.get_schema()
        gf = schema.get("global_fields", {})
        assert "area" in gf, "global_fields.area should exist"
        area_field = gf["area"]
        assert area_field.get("type") == "string"
        assert area_field.get("linkable") is True
        assert "work" in area_field.get("options", [])
        assert "finance" in area_field.get("options", [])
        assert "relationship" in area_field.get("options", [])
        assert "health" in area_field.get("options", [])
        assert "spirituality" in area_field.get("options", [])
        assert "career" in area_field.get("options", [])
        assert "business" in area_field.get("options", [])
        assert "family" in area_field.get("options", [])

    def test_area_field_is_global(self):
        import ptos
        schema = ptos.get_schema()
        gf = schema.get("global_fields", {})
        assert "area" in gf
        for tname, tdef in schema.get("type", {}).items():
            fields = tdef.get("fields", {})
            assert "area" not in fields, f"area should not be in type {tname} fields (global field)"

    def test_area_field_linkable(self):
        import ptos
        schema = ptos.get_schema()
        area_field = schema.get("global_fields", {}).get("area", {})
        assert area_field.get("linkable") is True, "area field should be linkable=True for bracket autocomplete"

    def test_area_field_queryable(self):
        from ptos_web import app
        import ptos_service as svc
        app.config["TESTING"] = True
        with app.test_client() as client:
            resp = client.post("/api/capture", json={"text": "test area work", "area": "work"})
            assert resp.status_code == 200
            result = svc.get_records(["area=work"])
            assert result["count"] >= 1
            for rec in svc.get_records(["area=work"])["records"]:
                assert rec.get("area") == "work"

    def test_area_matches_two_record_types(self):
        import ptos
        import ptos_service as svc
        today = ptos.today().isoformat()
        for rtype, note in (("capture", "area capture"), ("pomodoro", "area pomodoro")):
            line = ptos.build_record_line(
                today, {"type": rtype, "area": "work"}, note=note)
            ptos.append_record(line)
        result = svc.get_records(["area=work"], time="all")
        assert result["count"] >= 2
        types = {rec.get("type") for rec in result["records"]}
        assert {"capture", "pomodoro"} <= types


class TestAreaFolderTemplate:
    def test_folder_creation_seeds_template(self):
        from ptos_web import app
        import ptos_service as svc
        import ptos
        app.config["TESTING"] = True
        with app.test_client() as client:
            resp = client.post("/notes/new-folder", json={"path": "", "name": "work", "area": "work"})
            assert resp.status_code == 200
            data = resp.get_json()
            assert data["ok"] is True
            folder_path = os.path.join(ptos.NOTES_DIR, "work")
            tpl_path = os.path.join(folder_path, "template.md")
            assert os.path.isfile(tpl_path)
            with open(tpl_path, encoding="utf-8") as f:
                content = f.read()
            assert "{{AREA}}" not in content
            assert "{{AREA_TITLE}}" not in content
            assert "work" in content.lower()
            assert "Work" in content

    def test_folder_without_area_creates_no_template(self):
        from ptos_web import app
        import ptos
        app.config["TESTING"] = True
        with app.test_client() as client:
            resp = client.post("/notes/new-folder", json={"path": "", "name": "noarea"})
            assert resp.status_code == 200
            data = resp.get_json()
            assert data["ok"] is True
            folder_path = os.path.join(ptos.NOTES_DIR, "noarea")
            tpl_path = os.path.join(folder_path, "template.md")
            assert not os.path.isfile(tpl_path)

    def test_template_inheritance_works(self):
        from ptos_web import app
        import ptos
        app.config["TESTING"] = True
        with app.test_client() as client:
            client.post("/notes/new-folder", json={"path": "", "name": "work", "area": "work"})
            tpl = client.post("/notes/template-check", json={"path": "work"}).get_json()
            assert tpl["ok"] is True
            assert tpl["source"] == "local"
            resp = client.post("/notes/new-file", json={
                "path": "work", "name": "mypage", "content": tpl["content"]})
            assert resp.status_code == 200
            data = resp.get_json()
            assert data["ok"] is True
            edit_path = os.path.join(ptos.NOTES_DIR, "work", "mypage.md")
            assert os.path.isfile(edit_path)
            with open(edit_path, encoding="utf-8") as f:
                content = f.read()
            assert "work" in content.lower()


class TestAreaNavEntry:
    def test_areas_nav_entry_exists(self):
        from ptos_web import app
        app.config["TESTING"] = True
        with app.test_client() as client:
            resp = client.get("/")
            html = resp.get_data(as_text=True)
            assert "/areas" in html
            assert "Areas" in html

    def test_areas_nav_shortcut_works(self):
        from ptos_web import app
        app.config["TESTING"] = True
        with app.test_client() as client:
            resp = client.get("/")
            html = resp.get_data(as_text=True)
            assert '"gv"' in html
            assert '"/areas"' in html

    def test_areas_page_accessible(self):
        from ptos_web import app
        app.config["TESTING"] = True
        with app.test_client() as client:
            resp = client.get("/areas")
            assert resp.status_code == 200
            html = resp.get_data(as_text=True)
            assert "Areas" in html

    def test_areas_page_accessible_with_data(self):
        from ptos_web import app
        app.config["TESTING"] = True
        with app.test_client() as client:
            client.post("/notes/new-folder", json={"path": "", "name": "finance", "area": "finance"})
            resp = client.get("/areas")
            assert resp.status_code == 200
            html = resp.get_data(as_text=True)
            assert "Finance" in html
            assert "finance" in html.lower()


class TestAreasIndex:
    @staticmethod
    def _area(areas, slug):
        return next((a for a in areas if a["slug"] == slug), None)

    def test_schema_areas_render_with_zero_counts(self):
        import ptos_service as svc
        from ptos_web import app
        app.config["TESTING"] = True
        areas = svc.get_areas_with_counts()
        work = self._area(areas, "work")
        assert work is not None
        assert work["open"] == 0
        assert work["done"] == 0
        assert work["overdue"] == 0
        assert work["due_today"] == 0
        assert work["records_this_month"] == 0
        with app.test_client() as client:
            html = client.get("/areas").get_data(as_text=True)
            assert "Work" in html
            assert "Finance" in html

    def test_in_use_area_not_in_schema_renders(self):
        import os
        import ptos
        import ptos_service as svc
        os.makedirs(os.path.dirname(ptos.TODO_PATH) or ".", exist_ok=True)
        with open(ptos.TODO_PATH, "w", encoding="utf-8") as f:
            f.write("Mow the lawn area:garden\n")
        areas = svc.get_areas_with_counts()
        garden = self._area(areas, "garden")
        assert garden is not None
        assert garden["open"] == 1
        from ptos_web import app
        app.config["TESTING"] = True
        with app.test_client() as client:
            html = client.get("/areas").get_data(as_text=True)
            assert "Garden" in html

    def test_records_this_month_counts_area_records(self):
        import datetime as dt
        import ptos
        import ptos_service as svc
        today = ptos.today()
        last_month_day = today.replace(day=1) - dt.timedelta(days=1)
        for when, note in ((today, "this month"),
                           (last_month_day, "last month")):
            line = ptos.build_record_line(
                when.isoformat(), {"type": "capture", "area": "work"},
                note=note)
            ptos.append_record(line)
        work = self._area(svc.get_areas_with_counts(), "work")
        assert work["records_this_month"] == 1

    def test_has_page_link_branches(self):
        from ptos_web import app
        app.config["TESTING"] = True
        with app.test_client() as client:
            client.post("/notes/new-folder",
                        json={"path": "", "name": "work", "area": "work"})
            html = client.get("/areas").get_data(as_text=True)
            assert "/notes/browse/work" in html
            assert "View notes" in html
            assert "No page yet" in html

    def test_renders_no_inline_style_or_hex_colour(self):
        import re
        from ptos_web import app
        app.config["TESTING"] = True
        with app.test_client() as client:
            html = client.get("/areas").get_data(as_text=True)
            cards = html.split('<div class="area-card">')[1:]
            assert cards
            for card in cards:
                head = card.split('<div class="area-links">')[0]
                assert "style=" not in head
                assert not re.search(r"#[0-9a-fA-F]{3,8}\b", head)
                assert head.count("<a ") == 1

    def test_cards_are_not_link_wrappers(self):
        from ptos_web import app
        app.config["TESTING"] = True
        with app.test_client() as client:
            html = client.get("/areas").get_data(as_text=True)
            assert '<div class="area-card">' in html
            assert '<a class="area-card"' not in html


class TestAreaPagesIntegration:
    def test_area_page_roundtrip(self):
        from ptos_web import app
        app.config["TESTING"] = True
        with app.test_client() as client:
            client.post("/notes/new-folder", json={"path": "", "name": "finance", "area": "finance"})
            resp = client.post("/api/capture", json={"text": "Test finance record", "area": "finance"})
            assert resp.status_code == 200
            resp = client.get("/areas")
            assert resp.status_code == 200
            html = resp.get_data(as_text=True)
            assert "Finance" in html
            assert "finance" in resp.get_data(as_text=True).lower()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])