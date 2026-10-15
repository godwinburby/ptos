import os
import tomllib

import pytest

import ptos
import ptos_service as svc


# ── helpers ───────────────────────────────────────────────────────────────────

def _read_config_text():
    with open(ptos.CONFIG_PATH, "r", encoding="utf-8", newline="") as f:
        return f.read()


def _write_config_text(text):
    with open(ptos.CONFIG_PATH, "w", encoding="utf-8", newline="") as f:
        f.write(text)
    ptos._invalidate_all()


def _load_config():
    with open(ptos.CONFIG_PATH, "rb") as f:
        return tomllib.load(f)


def _fav(name, url):
    return {"name": name, "url": url}


# ── engine: surgical block writer ─────────────────────────────────────────────

class TestSaveFavoritesWriter:
    def test_adds_section_when_missing(self):
        _write_config_text("[user]\nname = \"Test\"\n")
        ptos.save_favorites([_fav("A", "/a")])
        cfg = _load_config()
        assert cfg["favorites"]["items"] == [{"name": "A", "url": "/a"}]
        assert cfg["user"]["name"] == "Test"

    def test_replaces_existing_section_only(self):
        _write_config_text(
            "# top comment\n[user]\nname = \"T\"\n\n[favorites]\nitems = []\n\n[demo]\nshow = \"auto\"\n"
        )
        ptos.save_favorites([_fav("A", "/a"), _fav("B", "/b")])
        text = _read_config_text()
        assert "# top comment" in text
        assert 'name = "T"' in text
        assert 'show = "auto"' in text
        cfg = _load_config()
        assert len(cfg["favorites"]["items"]) == 2

    def test_comments_outside_block_survive(self):
        _write_config_text(
            "# keep me\n[home]\nquick_presets = 10  # inline\n\n"
            "[favorites]\nitems = []\n\n# after block\n[server]\nport = 5000\n"
        )
        ptos.save_favorites([_fav("A", "/a")])
        text = _read_config_text()
        assert "# keep me" in text
        assert "# inline" in text
        assert "# after block" in text

    def test_quoted_header_is_matched(self):
        _write_config_text('["favorites"]\nitems = []\n')
        ptos.save_favorites([_fav("A", "/a")])
        cfg = _load_config()
        assert cfg["favorites"]["items"][0]["name"] == "A"
        assert _read_config_text().count("[favorites]") + _read_config_text().count('["favorites"]') == 1

    def test_empty_list_writes_empty_items(self):
        _write_config_text("[favorites]\nitems = [{ name = \"A\", url = \"/a\" },]\n")
        ptos.save_favorites([])
        cfg = _load_config()
        assert cfg["favorites"]["items"] == []

    def test_preserves_crlf(self):
        _write_config_text("[user]\r\nname = \"T\"\r\n")
        ptos.save_favorites([_fav("A", "/a")])
        text = _read_config_text()
        assert "\r\n" in text
        cfg = _load_config()
        assert cfg["favorites"]["items"][0]["url"] == "/a"

    def test_preserves_lf(self):
        _write_config_text("[user]\nname = \"T\"\n")
        ptos.save_favorites([_fav("A", "/a")])
        assert "\r" not in _read_config_text()

    def test_file_without_trailing_newline(self):
        _write_config_text("[user]\nname = \"T\"")
        ptos.save_favorites([_fav("A", "/a")])
        cfg = _load_config()
        assert cfg["favorites"]["items"][0]["name"] == "A"

    def test_roundtrip_special_chars(self):
        ptos.save_favorites([_fav('Quote " and \\ back', "/a?x=1&y=2")])
        cfg = _load_config()
        assert cfg["favorites"]["items"][0]["name"] == 'Quote " and \\ back'
        assert cfg["favorites"]["items"][0]["url"] == "/a?x=1&y=2"

    def test_one_favourite_per_line(self):
        ptos.save_favorites([_fav("A", "/a"), _fav("B", "/b")])
        text = _read_config_text()
        assert '{ name = "A", url = "/a" },' in text
        assert '{ name = "B", url = "/b" },' in text

    def test_repeated_saves_stay_stable(self):
        ptos.save_favorites([_fav("A", "/a")])
        first = _read_config_text()
        ptos.save_favorites([_fav("A", "/a")])
        assert _read_config_text() == first


# ── service: CRUD ─────────────────────────────────────────────────────────────

class TestFavoritesService:
    def test_get_favorites_empty_by_default(self):
        assert svc.get_favorites() == []

    def test_add_and_get(self):
        items = svc.add_favorite("A", "/a")
        assert items == [_fav("A", "/a")]
        assert svc.get_favorites() == [_fav("A", "/a")]

    def test_add_upserts_by_url(self):
        svc.add_favorite("Old", "/a")
        items = svc.add_favorite("New", "/a")
        assert items == [_fav("New", "/a")]

    def test_add_preserves_other_config(self):
        _write_config_text("# hi\n[home]\nquick_presets = 10\n")
        svc.add_favorite("A", "/a")
        text = _read_config_text()
        assert "# hi" in text
        assert _load_config()["home"]["quick_presets"] == 10

    def test_remove(self):
        svc.add_favorite("A", "/a")
        svc.add_favorite("B", "/b")
        items = svc.remove_favorite("/a")
        assert items == [_fav("B", "/b")]

    def test_remove_missing_is_noop(self):
        svc.add_favorite("A", "/a")
        assert svc.remove_favorite("/nope") == [_fav("A", "/a")]

    def test_rename(self):
        svc.add_favorite("A", "/a")
        items = svc.rename_favorite("/a", "Z")
        assert items == [_fav("Z", "/a")]

    def test_rename_missing_raises(self):
        with pytest.raises(svc.PTOSError):
            svc.rename_favorite("/nope", "Z")

    def test_move_up_down(self):
        svc.add_favorite("A", "/a")
        svc.add_favorite("B", "/b")
        svc.add_favorite("C", "/c")
        items = svc.move_favorite("/c", "up")
        assert [i["name"] for i in items] == ["A", "C", "B"]
        items = svc.move_favorite("/a", "down")
        assert [i["name"] for i in items] == ["C", "A", "B"]

    def test_move_at_edge_stays(self):
        svc.add_favorite("A", "/a")
        svc.add_favorite("B", "/b")
        items = svc.move_favorite("/a", "up")
        assert [i["name"] for i in items] == ["A", "B"]
        items = svc.move_favorite("/b", "down")
        assert [i["name"] for i in items] == ["A", "B"]

    def test_move_missing_raises(self):
        with pytest.raises(svc.PTOSError):
            svc.move_favorite("/nope", "up")

    def test_move_bad_direction_raises(self):
        svc.add_favorite("A", "/a")
        with pytest.raises(svc.PTOSError):
            svc.move_favorite("/a", "sideways")


# ── service: validation ───────────────────────────────────────────────────────

class TestFavoritesValidation:
    def test_rejects_blank_name(self):
        with pytest.raises(svc.PTOSError):
            svc.add_favorite("   ", "/a")

    def test_rejects_javascript_url(self):
        with pytest.raises(svc.PTOSError):
            svc.add_favorite("A", "javascript:alert(1)")

    def test_rejects_protocol_relative(self):
        with pytest.raises(svc.PTOSError):
            svc.add_favorite("A", "//evil.example")

    def test_rejects_missing_slash(self):
        with pytest.raises(svc.PTOSError):
            svc.add_favorite("A", "notes/edit/x.md")

    def test_rejects_empty_url(self):
        with pytest.raises(svc.PTOSError):
            svc.add_favorite("A", "")

    def test_accepts_query_string(self):
        items = svc.add_favorite("A", "/browse?type=expense&time=tm")
        assert items[0]["url"] == "/browse?type=expense&time=tm"

    def test_max_items(self):
        for i in range(svc._FAV_MAX):
            svc.add_favorite(f"N{i}", f"/p{i}")
        with pytest.raises(svc.PTOSError):
            svc.add_favorite("One too many", "/overflow")

    def test_get_skips_hand_edited_garbage(self):
        _write_config_text(
            "[favorites]\nitems = [\n"
            "  { name = \"Good\", url = \"/good\" },\n"
            "  { name = \"\", url = \"/blank\" },\n"
            "  { name = \"Bad\", url = \"http://evil\" },\n"
            "  \"not a dict\",\n"
            "]\n"
        )
        assert svc.get_favorites() == [_fav("Good", "/good")]


# ── cache invalidation ────────────────────────────────────────────────────────

class TestFavoritesCache:
    def test_add_visible_to_next_get(self):
        svc.add_favorite("A", "/a")
        assert svc.get_favorites() == [_fav("A", "/a")]
        svc.add_favorite("B", "/b")
        assert len(svc.get_favorites()) == 2

    def test_config_cache_reloaded(self):
        svc.add_favorite("A", "/a")
        assert ptos.get_config()["favorites"]["items"][0]["name"] == "A"


# ── web routes ────────────────────────────────────────────────────────────────

class TestFavoritesWeb:
    @pytest.fixture()
    def client(self):
        from ptos_web import app
        app.config["TESTING"] = True
        return app.test_client()

    def test_page_renders(self, client):
        resp = client.get("/favorites")
        assert resp.status_code == 200
        assert b"Favorites" in resp.data

    def test_page_lists_favourite(self, client):
        svc.add_favorite("My Note", "/notes/edit/x.md")
        html = client.get("/favorites").get_data(as_text=True)
        assert "My Note" in html
        assert "/notes/edit/x.md" in html

    def test_add_route(self, client):
        resp = client.post("/api/favorites/add",
                           json={"name": "A", "url": "/a"})
        data = resp.get_json()
        assert data["ok"] is True
        assert data["favorites"] == [_fav("A", "/a")]

    def test_add_route_validation(self, client):
        resp = client.post("/api/favorites/add",
                           json={"name": "A", "url": "javascript:x"})
        data = resp.get_json()
        assert data["ok"] is False
        assert "error" in data

    def test_remove_route(self, client):
        svc.add_favorite("A", "/a")
        resp = client.post("/api/favorites/remove", json={"url": "/a"})
        assert resp.get_json()["favorites"] == []

    def test_rename_route(self, client):
        svc.add_favorite("A", "/a")
        resp = client.post("/api/favorites/rename",
                           json={"url": "/a", "name": "Z"})
        assert resp.get_json()["favorites"] == [_fav("Z", "/a")]

    def test_move_route(self, client):
        svc.add_favorite("A", "/a")
        svc.add_favorite("B", "/b")
        resp = client.post("/api/favorites/move",
                           json={"url": "/b", "direction": "up"})
        data = resp.get_json()
        assert [f["name"] for f in data["favorites"]] == ["B", "A"]


# ── shell (sidebar / more menu / star) ────────────────────────────────────────

class TestFavoritesShell:
    @pytest.fixture()
    def client(self):
        from ptos_web import app
        app.config["TESTING"] = True
        return app.test_client()

    def _home(self, client):
        return client.get("/").get_data(as_text=True)

    def test_sidebar_group_renders(self, client):
        html = self._home(client)
        assert 'data-group="favorites"' in html
        assert "Manage favorites" in html

    def test_sidebar_lists_favourite(self, client):
        svc.add_favorite("Buried note", "/notes/edit/deep/x.md")
        html = self._home(client)
        assert "Buried note" in html
        assert "/notes/edit/deep/x.md" in html

    def test_sidebar_empty_hint(self, client):
        html = self._home(client)
        assert "Star any page" in html

    def test_star_buttons_present(self, client):
        html = self._home(client)
        assert 'id="fav-star-top"' in html
        assert 'id="fav-star-side"' in html

    def test_more_menu_section(self, client):
        svc.add_favorite("A", "/a")
        html = self._home(client)
        assert 'class="more-menu-item fav-more-item"' in html

    def test_fav_urls_shim(self, client):
        svc.add_favorite("A", "/a")
        html = self._home(client)
        assert "favUrls" in html
        assert '"/a"' in html

    def test_fav_urls_shim_escapes_script_breakout(self, client):
        # |tojson escapes <, >, & as \u003c etc, so a synced-in URL
        # containing "</script>" cannot end the shim's <script> element.
        svc.add_favorite("Sneaky", "/x?</script><script>alert(1)</script>")
        html = self._home(client)
        assert "</script><script>alert(1)" not in html
        assert "\\u003c" in html

    def test_favorites_js_loaded(self, client):
        html = self._home(client)
        assert "favorites.js" in html

    def test_icon_exists(self):
        path = os.path.join(os.path.dirname(os.path.dirname(__file__)),
                            "web_templates", "icons", "favorites.html")
        assert os.path.exists(path)


# ── sidebar CSS ───────────────────────────────────────────────────────────────

class TestFavoritesSidebarCss:
    def test_sidebar_group_never_shrinks(self):
        # #fav-group is the only overflow:hidden direct child of the
        # fixed-height .sidebar flex column. nav.sidebar-nav has flex:1
        # (basis 0%) but min-height:auto → its min-content (1095px) exceeds
        # any normal viewport, so the flex algorithm freezes nav at
        # min-content and redistributes the deficit to the other children;
        # fav-group's automatic minimum (overflow:hidden → 0) then absorbs
        # it and crushes the group to height 0 — rows laid out, clipped
        # invisible ("Favorites heading only, open but empty"). flex-shrink:0
        # pins it at its basis so the excess falls on the sidebar's
        # overflow-y scroll instead.
        path = os.path.join(os.path.dirname(os.path.dirname(__file__)),
                            "web_static", "css", "base.css")
        with open(path, encoding="utf-8") as f:
            text = f.read()
        marker = ".sidebar-nav-group {"
        i = text.index(marker)
        rule = text[i:text.index("}", i)]
        assert "flex-shrink: 0" in rule
        assert "overflow: hidden" in rule


# ── favorites.js static pins ──────────────────────────────────────────────────

class TestFavoritesJsStatic:
    def test_more_menu_rows_insert_into_content(self):
        # .fav-more-manage lives inside #more-menu > .more-menu-content, and
        # insertBefore only accepts a direct child as the reference node —
        # inserting into #more-menu itself threw "Child to insert before is
        # not a child of this node" on every star/unstar (the sidebar rows
        # updated, then the More-menu insert aborted setStars/expandFavGroup
        # and surfaced an alert). Rows must be inserted into the content
        # container that actually holds the manage link.
        path = os.path.join(os.path.dirname(os.path.dirname(__file__)),
                            "web_static", "js", "favorites.js")
        with open(path, encoding="utf-8") as f:
            text = f.read()
        assert "content.insertBefore(a, manageM)" in text
        assert "menu.insertBefore(a, manageM)" not in text


# ── keyboard chord ────────────────────────────────────────────────────────────

class TestFavoritesChord:
    def test_g_f_in_nav_map(self):
        path = os.path.join(os.path.dirname(os.path.dirname(__file__)),
                            "web_static", "js", "nav_chords.js")
        with open(path, encoding="utf-8") as f:
            text = f.read()
        assert '"g f": "/favorites"' in text
        assert "Favorites" in text


# ── starter parity ────────────────────────────────────────────────────────────

class TestStarterFavorites:
    def test_starter_config_has_section(self):
        path = os.path.join(os.path.dirname(os.path.dirname(__file__)),
                            "starters", "starter_config.toml")
        with open(path, "rb") as f:
            cfg = tomllib.load(f)
        assert "favorites" in cfg
        assert cfg["favorites"]["items"] == []

    def test_starter_comment_mentioned(self):
        path = os.path.join(os.path.dirname(os.path.dirname(__file__)),
                            "starters", "starter_config.toml")
        with open(path, encoding="utf-8") as f:
            text = f.read()
        assert "# Star any page" in text
