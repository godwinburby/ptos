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
    def test_area_page_lands_under_areas_with_shared_template(self):
        from ptos_web import app
        import ptos
        app.config["TESTING"] = True
        with app.test_client() as client:
            resp = client.post("/notes/new-folder",
                               json={"path": "", "name": "ignored", "area": "work"})
            assert resp.status_code == 200
            data = resp.get_json()
            assert data["ok"] is True
            assert data["rel_path"] == "Areas/work/Home.md"
            assert not os.path.exists(os.path.join(ptos.NOTES_DIR, "work"))
            folder = os.path.join(ptos.NOTES_DIR, "Areas", "work")
            assert not os.path.isfile(os.path.join(folder, "template.md"))
            home_path = os.path.join(folder, "Home.md")
            assert os.path.isfile(home_path)
            with open(home_path, encoding="utf-8") as f:
                home = f.read()
            assert "{{AREA}}" not in home
            assert "{{AREA_TITLE}}" not in home
            assert "Work" in home
            shared = os.path.join(ptos.NOTES_DIR, "Areas", "template.md")
            assert os.path.isfile(shared)
            with open(shared, encoding="utf-8") as f:
                tpl = f.read()
            assert "{{AREA}}" in tpl
            assert "{{AREA_TITLE}}" in tpl

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
            assert not os.path.isfile(os.path.join(folder_path, "Home.md"))

    def test_template_inheritance_and_placeholder_fill(self):
        from ptos_web import app
        import ptos
        app.config["TESTING"] = True
        with app.test_client() as client:
            client.post("/notes/new-folder",
                        json={"path": "", "name": "work", "area": "work"})
            tpl = client.post("/notes/template-check",
                              json={"path": "Areas/work"}).get_json()
            assert tpl["ok"] is True
            assert tpl["source"] == "choice"
            assert tpl["parent"]["rel_path"] == "Areas"
            content = tpl["parent"]["content"]
            assert "{{AREA}}" in content
            resp = client.post("/notes/new-file", json={
                "path": "Areas/work", "name": "mypage", "content": content})
            assert resp.status_code == 200
            assert resp.get_json()["ok"] is True
            edit_path = os.path.join(ptos.NOTES_DIR, "Areas", "work", "mypage.md")
            assert os.path.isfile(edit_path)
            with open(edit_path, encoding="utf-8") as f:
                filled = f.read()
            assert "{{AREA}}" not in filled
            assert "{{AREA_TITLE}}" not in filled
            assert "Work" in filled

    def test_nested_folder_uses_area_slug(self):
        import ptos
        import ptos_service as svc
        svc.svc_create_area_page("work")
        svc.svc_create_folder("Areas/work", "clients")
        svc.svc_create_file("Areas/work/clients", "acme", "{{AREA_TITLE}}")
        path = os.path.join(ptos.NOTES_DIR, "Areas", "work", "clients", "acme.md")
        with open(path, encoding="utf-8") as f:
            assert f.read() == "Work"

    def test_local_template_overrides_shared(self):
        import ptos
        import ptos_service as svc
        svc.svc_create_area_page("work")
        local = os.path.join(ptos.NOTES_DIR, "Areas", "work", "template.md")
        with open(local, "w", encoding="utf-8") as f:
            f.write("local {{AREA_TITLE}}")
        resolved = svc.svc_resolve_template("Areas/work")
        assert resolved["source"] == "local"
        svc.svc_create_file("Areas/work", "page", resolved["content"])
        with open(os.path.join(ptos.NOTES_DIR, "Areas", "work", "page.md"),
                  encoding="utf-8") as f:
            assert f.read() == "local Work"
        svc.svc_create_folder("Areas/work", "tpls")
        svc.svc_create_file("Areas/work/tpls", "template", "{{AREA_TITLE}}")
        with open(os.path.join(ptos.NOTES_DIR, "Areas", "work", "tpls",
                               "template.md"), encoding="utf-8") as f:
            assert f.read() == "{{AREA_TITLE}}"
        with open(local, encoding="utf-8") as f:
            assert f.read() == "local {{AREA_TITLE}}"

    def test_plain_folder_does_not_get_placeholders_filled(self):
        import ptos
        import ptos_service as svc
        svc.svc_create_folder("", "plain")
        svc.svc_create_file("plain", "note", "{{AREA_TITLE}}")
        with open(os.path.join(ptos.NOTES_DIR, "plain", "note.md"),
                  encoding="utf-8") as f:
            assert f.read() == "{{AREA_TITLE}}"


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
            assert '"ga"' in html
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
            assert "/notes/edit/Areas/work/Home.md" in html
            assert "Open area page" in html
            assert "/notes/browse/Areas/work" in html
            assert "Create area page" in html
            assert "No page yet" not in html

    def test_page_fields_reflect_home_file_not_folder(self):
        import os
        import ptos
        import ptos_service as svc
        work = next(a for a in svc.get_areas_with_counts() if a["slug"] == "work")
        assert work["has_folder"] is False
        assert work["has_page"] is False
        assert work["page_path"] == ""
        assert work["todo_linkable"] is True
        os.makedirs(os.path.join(ptos.NOTES_DIR, "Areas", "work"), exist_ok=True)
        work = next(a for a in svc.get_areas_with_counts() if a["slug"] == "work")
        assert work["has_folder"] is True
        assert work["has_page"] is False
        with open(os.path.join(ptos.NOTES_DIR, "Areas", "work", "Home.md"),
                  "w", encoding="utf-8") as f:
            f.write("Home")
        work = next(a for a in svc.get_areas_with_counts() if a["slug"] == "work")
        assert work["has_page"] is True
        assert work["page_path"] == "Areas/work/Home.md"
        assert work["page_url"] == "/notes/edit/Areas/work/Home.md"
        assert work["folder_url"] == "/notes/browse/Areas/work"

    def test_legacy_home_is_still_recognized(self):
        import os
        import ptos
        import ptos_service as svc
        os.makedirs(os.path.join(ptos.NOTES_DIR, "work"), exist_ok=True)
        with open(os.path.join(ptos.NOTES_DIR, "work", "Home.md"),
                  "w", encoding="utf-8") as f:
            f.write("Legacy")
        work = next(a for a in svc.get_areas_with_counts() if a["slug"] == "work")
        assert work["has_folder"] is True
        assert work["has_page"] is True
        assert work["page_path"] == "work/Home.md"
        assert work["page_url"] == "/notes/edit/work/Home.md"
        assert work["folder_url"] == "/notes/browse/work"
        assert svc.svc_create_area_page("work")["rel_path"] == "Areas/work/Home.md"
        assert os.path.isfile(os.path.join(ptos.NOTES_DIR, "Areas", "work",
                                           "Home.md"))
        assert not os.path.isdir(os.path.join(ptos.NOTES_DIR, "work"))

    def test_stat_tiles_are_links(self):
        import datetime as dt
        import ptos
        from ptos_web import app
        today = ptos.today()
        yesterday = (today - dt.timedelta(days=1)).isoformat()
        os.makedirs(os.path.dirname(ptos.TODO_PATH) or ".", exist_ok=True)
        with open(ptos.TODO_PATH, "w", encoding="utf-8") as f:
            f.write(f"Overdue task area:work due:{yesterday}\n")
            f.write(f"Today task area:work due:{today.isoformat()}\n")
        app.config["TESTING"] = True
        with app.test_client() as client:
            html = client.get("/areas").get_data(as_text=True)
        assert 'href="/todo?area=work"' in html
        assert 'href="/todo?area=work&due=overdue"' in html
        assert 'href="/todo?area=work&due=today"' in html
        assert 'href="/entity?field=area&value=work&time=tm"' in html
        card = html.split('data-area-card="work"')[1].split("</div>\n  </div>")[0]
        assert card.count('<a class="stat stat-link"') == 4
        assert '<div class="stat">\n        <div class="stat-label">Done</div>' in card

    def test_non_slug_area_gets_no_todo_links(self, monkeypatch):
        import ptos_service as svc
        from ptos_web import app
        monkeypatch.setattr(svc, "get_areas_with_counts", lambda: [{
            "area": "Business Development",
            "slug": "Business Development",
            "title": "Business Development",
            "open": 1,
            "done": 0,
            "overdue": 0,
            "due_today": 0,
            "records_this_month": 2,
            "has_folder": False,
            "has_page": False,
            "todo_linkable": False,
            "page_path": "",
            "page_url": "",
            "folder_url": "",
        }])
        app.config["TESTING"] = True
        with app.test_client() as client:
            html = client.get("/areas").get_data(as_text=True)
        assert 'data-area-card="Business Development"' in html
        assert 'href="/todo?area=Business Development"' not in html
        assert 'value=Business%20Development&time=tm' in html
        assert "Create area page" not in html
        assert "No page yet" in html

    def test_renders_no_inline_style_or_hex_colour(self):
        import re
        from ptos_web import app
        app.config["TESTING"] = True
        with app.test_client() as client:
            html = client.get("/areas").get_data(as_text=True)
            cards = html.split('<div class="area-card"')[1:]
            assert cards
            for card in cards:
                head = card.split('<div class="area-links">')[0]
                assert "style=" not in head
                assert not re.search(r"#[0-9a-fA-F]{3,8}\b", head)
                assert '<a class="stat stat-link"' in head

    def test_cards_are_not_link_wrappers(self):
        from ptos_web import app
        app.config["TESTING"] = True
        with app.test_client() as client:
            html = client.get("/areas").get_data(as_text=True)
            assert '<div class="area-card"' in html
            assert '<a class="area-card"' not in html


class TestCreateAreaPage:
    def test_creates_shared_template_and_area_home(self):
        import ptos
        import ptos_service as svc
        result = svc.svc_create_area_page("work")
        assert result["created"] is True
        assert result["rel_path"] == "Areas/work/Home.md"
        folder = os.path.join(ptos.NOTES_DIR, "Areas", "work")
        assert not os.path.isfile(os.path.join(folder, "template.md"))
        home = os.path.join(folder, "Home.md")
        assert os.path.isfile(home)
        with open(home, encoding="utf-8") as f:
            content = f.read()
        assert "{{AREA}}" not in content
        assert "{{AREA_TITLE}}" not in content
        assert "Work" in content
        with open(os.path.join(ptos.NOTES_DIR, "Areas", "template.md"),
                  encoding="utf-8") as f:
            shared = f.read()
        assert "{{AREA}}" in shared
        assert "{{AREA_TITLE}}" in shared

    def test_second_call_is_idempotent_and_never_overwrites(self):
        import ptos
        import ptos_service as svc
        svc.svc_create_area_page("work")
        home = os.path.join(ptos.NOTES_DIR, "Areas", "work", "Home.md")
        with open(home, "w", encoding="utf-8") as f:
            f.write("my own page")
        result = svc.svc_create_area_page("work")
        assert result["created"] is False
        with open(home, encoding="utf-8") as f:
            assert f.read() == "my own page"

    def test_shared_template_edit_is_never_overwritten(self):
        import ptos
        import ptos_service as svc
        svc.svc_create_area_page("work")
        shared = os.path.join(ptos.NOTES_DIR, "Areas", "template.md")
        with open(shared, "w", encoding="utf-8") as f:
            f.write("custom shared")
        svc.svc_create_area_page("home")
        with open(shared, encoding="utf-8") as f:
            assert f.read() == "custom shared"

    def test_rejects_invalid_slug(self):
        import ptos_service as svc
        with pytest.raises(svc.PTOSError):
            svc.svc_create_area_page("Work")
        with pytest.raises(svc.PTOSError):
            svc.svc_create_area_page("")

    def test_route_creates_page_and_reports_errors(self):
        import os
        import ptos
        from ptos_web import app
        app.config["TESTING"] = True
        with app.test_client() as client:
            resp = client.post("/api/areas/create-page", json={"area": "work"})
            assert resp.status_code == 200
            data = resp.get_json()
            assert data["ok"] is True
            assert data["rel_path"] == "Areas/work/Home.md"
            assert data["created"] is True
            assert os.path.isfile(os.path.join(ptos.NOTES_DIR, "Areas", "work",
                                               "Home.md"))
            resp = client.post("/api/areas/create-page", json={"area": "Work"})
            assert resp.status_code == 400
            assert resp.get_json()["ok"] is False
            resp = client.post("/api/areas/create-page", data="nope",
                               content_type="text/plain")
            assert resp.status_code == 400
            assert resp.get_json()["error"] == "JSON body required"


class TestAreaMigration:
    def test_moves_legacy_folder_and_keeps_local_template(self):
        import ptos
        import ptos_service as svc
        legacy = os.path.join(ptos.NOTES_DIR, "work")
        os.makedirs(os.path.join(legacy, "clients"), exist_ok=True)
        with open(os.path.join(legacy, "Home.md"), "w", encoding="utf-8") as f:
            f.write("legacy home")
        with open(os.path.join(legacy, "template.md"), "w", encoding="utf-8") as f:
            f.write("custom template")
        with open(os.path.join(legacy, "clients", "acme.md"), "w",
                  encoding="utf-8") as f:
            f.write("client")
        moved = svc.svc_migrate_area_folders(["work"])
        assert moved == ["Areas/work"]
        assert not os.path.isdir(legacy)
        new_folder = os.path.join(ptos.NOTES_DIR, "Areas", "work")
        with open(os.path.join(new_folder, "Home.md"), encoding="utf-8") as f:
            assert f.read() == "legacy home"
        with open(os.path.join(new_folder, "template.md"), encoding="utf-8") as f:
            assert f.read() == "custom template"
        assert os.path.isfile(os.path.join(new_folder, "clients", "acme.md"))
        assert os.path.isfile(os.path.join(ptos.NOTES_DIR, "Areas",
                                           "template.md"))
        assert svc.svc_resolve_template("Areas/work")["source"] == "local"

    def test_skips_folders_without_home(self):
        import ptos
        import ptos_service as svc
        folder = os.path.join(ptos.NOTES_DIR, "archive")
        os.makedirs(folder, exist_ok=True)
        with open(os.path.join(folder, "note.md"), "w", encoding="utf-8") as f:
            f.write("note")
        assert svc.svc_migrate_area_folders(["archive"]) == []
        assert os.path.isdir(folder)
        assert not os.path.isdir(os.path.join(ptos.NOTES_DIR, "Areas", "archive"))

    def test_skips_when_destination_exists(self):
        import ptos
        import ptos_service as svc
        legacy = os.path.join(ptos.NOTES_DIR, "work")
        os.makedirs(legacy, exist_ok=True)
        with open(os.path.join(legacy, "Home.md"), "w", encoding="utf-8") as f:
            f.write("legacy")
        dest = os.path.join(ptos.NOTES_DIR, "Areas", "work")
        os.makedirs(dest, exist_ok=True)
        with open(os.path.join(dest, "Home.md"), "w", encoding="utf-8") as f:
            f.write("new")
        assert svc.svc_migrate_area_folders(["work"]) == []
        with open(os.path.join(dest, "Home.md"), encoding="utf-8") as f:
            assert f.read() == "new"
        assert os.path.isfile(os.path.join(legacy, "Home.md"))

    def test_idempotent(self):
        import ptos
        import ptos_service as svc
        legacy = os.path.join(ptos.NOTES_DIR, "work")
        os.makedirs(legacy, exist_ok=True)
        with open(os.path.join(legacy, "Home.md"), "w", encoding="utf-8") as f:
            f.write("legacy")
        assert svc.svc_migrate_area_folders(["work"]) == ["Areas/work"]
        assert svc.svc_migrate_area_folders(["work"]) == []

    def test_repairs_home_page_and_favorites(self):
        import ptos
        import ptos_service as svc
        legacy = os.path.join(ptos.NOTES_DIR, "work")
        os.makedirs(legacy, exist_ok=True)
        with open(os.path.join(legacy, "Home.md"), "w", encoding="utf-8") as f:
            f.write("legacy")
        svc.set_home_page("work/Home.md")
        svc.add_favorite("Work", "/notes/edit/work/Home.md")
        svc.svc_migrate_area_folders(["work"])
        assert svc.get_home_page() == "Areas/work/Home.md"
        urls = [f["url"] for f in svc.get_favorites()]
        assert "/notes/edit/Areas/work/Home.md" in urls

    def test_default_discovery_includes_areas_in_use(self):
        import ptos
        import ptos_service as svc
        os.makedirs(os.path.dirname(ptos.TODO_PATH) or ".", exist_ok=True)
        with open(ptos.TODO_PATH, "w", encoding="utf-8") as f:
            f.write("Mow area:garden\n")
        folder = os.path.join(ptos.NOTES_DIR, "garden")
        os.makedirs(folder, exist_ok=True)
        with open(os.path.join(folder, "Home.md"), "w", encoding="utf-8") as f:
            f.write("garden")
        moved = svc.svc_migrate_area_folders()
        assert "Areas/garden" in moved


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