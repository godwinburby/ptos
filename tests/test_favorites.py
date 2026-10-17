import os
import re
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


def _fav_header_count(text):
    return len(re.findall(r'(?m)^\s*\[\s*"?favorites"?\s*\]', text))


_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


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

    def test_header_with_trailing_comment(self):
        # A commented header is legal TOML; missing it used to append a
        # second [favorites] table and brick the whole config file.
        _write_config_text("[user]\nname = \"T\"\n\n[favorites]  # my links\nitems = []\n\n[server]\nport = 5000\n")
        ptos.save_favorites([_fav("A", "/a")])
        cfg = _load_config()
        assert cfg["favorites"]["items"] == [_fav("A", "/a")]
        assert _fav_header_count(_read_config_text()) == 1

    def test_header_with_inner_spaces(self):
        _write_config_text("[ favorites ]\nitems = []\n")
        ptos.save_favorites([_fav("A", "/a")])
        assert _load_config()["favorites"]["items"] == [_fav("A", "/a")]
        assert _fav_header_count(_read_config_text()) == 1

    def test_header_quoted_with_spaces(self):
        _write_config_text('[ "favorites" ]\nitems = []\n')
        ptos.save_favorites([_fav("A", "/a")])
        assert _load_config()["favorites"]["items"] == [_fav("A", "/a")]
        assert _fav_header_count(_read_config_text()) == 1

    def test_header_trailing_comment_crlf(self):
        _write_config_text(
            "[user]\r\nname = \"T\"\r\n\r\n[favorites] # links\r\nitems = []\r\n\r\n[server]\r\nport = 5000\r\n"
        )
        ptos.save_favorites([_fav("A", "/a")])
        text = _read_config_text()
        assert "\r\n" in text
        assert _load_config()["favorites"]["items"] == [_fav("A", "/a")]
        assert _fav_header_count(text) == 1

    def test_favorites_as_last_section(self):
        _write_config_text("[user]\nname = \"T\"\n\n[favorites] # last\nitems = []\n")
        ptos.save_favorites([_fav("A", "/a")])
        assert _load_config()["favorites"]["items"] == [_fav("A", "/a")]
        assert _fav_header_count(_read_config_text()) == 1

    def test_favorites_before_comment_block_then_table(self):
        _write_config_text(
            "[favorites]\nitems = []\n\n"
            "# a comment block\n# between sections\n\n"
            "[server]\nport = 5000\n"
        )
        ptos.save_favorites([_fav("A", "/a")])
        text = _read_config_text()
        assert "# a comment block" in text
        assert 'port = 5000' in text
        assert _fav_header_count(text) == 1

    def test_every_header_variant_leaves_parseable_single_table(self):
        for header in ("[favorites]", "[favorites] # c", "[ favorites ]",
                       '["favorites"]', '[ "favorites" ]', "[favorites ]"):
            _write_config_text(header + "\nitems = []\n\n[server]\nport = 5000\n")
            ptos.save_favorites([_fav("A", "/a")])
            cfg = tomllib.loads(_read_config_text())
            assert cfg["favorites"]["items"] == [_fav("A", "/a")]
            assert _fav_header_count(_read_config_text()) == 1


class TestSaveFavoritesGuard:
    def test_pre_corrupted_double_table_refused(self, tmp_path):
        # A file that already has two [favorites] tables cannot be parsed;
        # the guard must refuse and leave the bytes untouched.
        bad = ("[favorites]\nitems = []\n\n[favorites]\nitems = []\n"
               "[server]\nport = 5000\n")
        _write_config_text(bad)
        with pytest.raises(svc.PTOSError):
            ptos.save_favorites([_fav("A", "/a")])
        assert _read_config_text() == bad

    def test_unmatchable_header_refused(self, monkeypatch):
        # Simulate a header form the regex cannot see: the section is
        # present in the file, the matcher misses it, so the rewrite would
        # append a duplicate table — the parse-before-write net catches it.
        text = "[favorites]\nitems = []\n\n[server]\nport = 5000\n"
        _write_config_text(text)
        monkeypatch.setattr(ptos, "_FAVORITES_HEADER_RE",
                            re.compile(r"^\s*\[never_matches\]\s*$"))
        with pytest.raises(svc.PTOSError):
            ptos.save_favorites([_fav("A", "/a")])
        assert _read_config_text() == text

    def test_error_message_says_unchanged(self, monkeypatch):
        _write_config_text("[favorites]\nitems = []\n")
        monkeypatch.setattr(ptos, "_FAVORITES_HEADER_RE",
                            re.compile(r"^\s*\[never_matches\]\s*$"))
        with pytest.raises(svc.PTOSError, match="favorites unchanged"):
            ptos.save_favorites([_fav("A", "/a")])


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


# ── shared internal-URL validator ─────────────────────────────────────────────

_ACCEPT_URLS = ["/", "/browse", "/browse?q=a&b=c", "/notes/My%20Note"]
_REJECT_URLS = [
    "//evil.com",
    "/\\evil.com",
    "/\\\\evil.com",
    "/\t/evil.com",
    "/\n/evil.com",
    "/\r/evil.com",
    "/\x00/evil.com",
    "javascript:alert(1)",
    "http://evil.com",
    "https://evil.com",
    "",
    "   ",
    None,
    123,
    ["x"],
    "x" * 2049,
]


class TestInternalUrlValidator:
    @pytest.mark.parametrize("url", _ACCEPT_URLS)
    def test_fav_url_accepts(self, url):
        assert svc._valid_fav_url(url) is True

    @pytest.mark.parametrize("url", _REJECT_URLS)
    def test_fav_url_rejects(self, url):
        assert svc._valid_fav_url(url) is False

    @pytest.mark.parametrize("url", _ACCEPT_URLS)
    def test_return_to_accepts(self, url):
        from ptos_web import _safe_return_to
        assert _safe_return_to(url) == url.strip()

    @pytest.mark.parametrize("url", _REJECT_URLS)
    def test_return_to_rejects(self, url):
        from ptos_web import _safe_return_to
        assert _safe_return_to(url, default="/fallback") == "/fallback"

    def test_backslash_favorites_dropped_on_load(self):
        _write_config_text(
            "[favorites]\nitems = [\n"
            "  { name = \"Good\", url = \"/good\" },\n"
            "  { name = \"Evil\", url = \"/\\\\evil.com\" },\n"
            "  { name = \"Tab\", url = \"/\\t/evil.com\" },\n"
            "]\n"
        )
        assert svc.get_favorites() == [_fav("Good", "/good")]


# ── JSON Content-Type hardening ───────────────────────────────────────────────

class TestJsonContentType:
    FAV_ENDPOINTS = ["/api/favorites/add", "/api/favorites/remove",
                     "/api/favorites/rename", "/api/favorites/move"]

    @pytest.fixture()
    def client(self):
        from ptos_web import app
        app.config["TESTING"] = True
        return app.test_client()

    @pytest.mark.parametrize("path", FAV_ENDPOINTS + ["/api/conflict/resolve"])
    def test_plain_text_post_rejected(self, client, path):
        # force=True used to accept text/plain, which needs no CORS
        # preflight — a cross-site form post with cached Basic auth.
        before = svc.get_favorites()
        resp = client.post(path, data='{"name":"A","url":"/a"}',
                           content_type="text/plain")
        assert resp.status_code == 400
        assert resp.get_json()["ok"] is False
        assert svc.get_favorites() == before

    def test_json_add_still_works(self, client):
        resp = client.post("/api/favorites/add",
                           json={"name": "A", "url": "/a"})
        assert resp.status_code == 200
        assert resp.get_json()["ok"] is True
        assert svc.get_favorites() == [_fav("A", "/a")]

    def test_json_remove_still_works(self, client):
        svc.add_favorite("A", "/a")
        resp = client.post("/api/favorites/remove", json={"url": "/a"})
        assert resp.get_json()["ok"] is True
        assert svc.get_favorites() == []

    def test_no_force_true_in_web_module(self):
        path = os.path.join(_REPO_ROOT, "ptos_web.py")
        with open(path, encoding="utf-8") as f:
            text = f.read()
        assert "force=True" not in text


# ── cross-origin write guard ──────────────────────────────────────────────────

class TestOriginGuard:
    @pytest.fixture()
    def client(self):
        from ptos_web import app
        app.config["TESTING"] = True
        return app.test_client()

    def test_cross_origin_write_rejected(self, client):
        resp = client.post("/api/favorites/add",
                           json={"name": "A", "url": "/a"},
                           headers={"Origin": "http://evil.example"})
        assert resp.status_code == 403
        assert resp.get_json()["ok"] is False
        assert svc.get_favorites() == []

    def test_same_origin_write_allowed(self, client):
        resp = client.post("/api/favorites/add",
                           json={"name": "A", "url": "/a"},
                           headers={"Origin": "http://localhost"})
        assert resp.status_code == 200
        assert resp.get_json()["ok"] is True

    def test_no_origin_allowed(self, client):
        resp = client.post("/api/favorites/add",
                           json={"name": "A", "url": "/a"})
        assert resp.status_code == 200
        assert resp.get_json()["ok"] is True

    def test_null_origin_rejected(self, client):
        resp = client.post("/api/favorites/add",
                           json={"name": "A", "url": "/a"},
                           headers={"Origin": "null"})
        assert resp.status_code == 403
        assert svc.get_favorites() == []

    def test_get_with_foreign_origin_untouched(self, client):
        resp = client.get("/favorites",
                          headers={"Origin": "http://evil.example"})
        assert resp.status_code == 200


# ── rename-aware favorites (note display names spec, section 2) ──────────────

class TestRetargetNotesUrl:
    def test_file_edit_favorite(self):
        got = svc._retarget_notes_url("/notes/edit/a.md", "a.md", "b.md", False)
        assert got == "/notes/edit/b.md"

    def test_file_edit_encoded_spaces_and_unicode(self):
        url = "/notes/edit/caf%C3%A9%20notes/clinic.md"
        got = svc._retarget_notes_url(url, "caf\u00e9 notes/clinic.md",
                                      "caf\u00e9 notes/dinner.md", False)
        assert got == "/notes/edit/caf%C3%A9%20notes/dinner.md"

    def test_query_and_fragment_preserved(self):
        got = svc._retarget_notes_url("/notes/edit/a.md?run=x#sec",
                                      "a.md", "b.md", False)
        assert got == "/notes/edit/b.md?run=x#sec"

    def test_folder_prefix_exact_and_nested(self):
        assert svc._retarget_notes_url("/notes/browse/Old", "Old",
                                       "New", True) == "/notes/browse/New"
        assert svc._retarget_notes_url("/notes/edit/Old/inner.md",
                                       "Old", "New", True) == \
            "/notes/edit/New/inner.md"

    def test_folder_prefix_is_segment_aware(self):
        assert svc._retarget_notes_url("/notes/edit/Projects/Job2/x.md",
                                       "Projects/Job", "Projects/Role",
                                       True) is None

    def test_unrelated_urls_pass_through(self):
        for url in ("/browse?type=expense", "/notes/edit/other.md",
                    "/habits", "https://example.com/notes/edit/a.md"):
            assert svc._retarget_notes_url(url, "a.md", "b.md", False) is None

    def test_rewritten_url_passes_validation(self):
        got = svc._retarget_notes_url("/notes/edit/a.md?q=1#f",
                                      "a.md", "b c/d.md", False)
        assert svc._valid_fav_url(got)


class TestUpdateFavoritesAfterRename:
    def test_file_rename_updates_favorite(self):
        svc.add_favorite("Note", "/notes/edit/old.md")
        svc.add_favorite("Other", "/browse")
        n = svc.update_favorites_after_rename("old.md", "new.md", False)
        assert n == 1
        urls = [f["url"] for f in svc.get_favorites()]
        assert urls == ["/notes/edit/new.md", "/browse"]

    def test_no_match_means_no_write(self, monkeypatch):
        svc.add_favorite("Other", "/browse")
        def boom(items):
            raise AssertionError("save_favorites must not be called")
        monkeypatch.setattr(ptos, "save_favorites", boom)
        n = svc.update_favorites_after_rename("ghost.md", "x.md", False)
        assert n == 0

    def test_folder_rename_updates_browse_and_inside(self):
        svc.add_favorite("Folder", "/notes/browse/Old")
        svc.add_favorite("Inner", "/notes/edit/Old/deep/inner.md")
        svc.add_favorite("Sibling", "/notes/browse/Old2")
        n = svc.update_favorites_after_rename("Old", "New", True)
        assert n == 2
        urls = {f["name"]: f["url"] for f in svc.get_favorites()}
        assert urls["Folder"] == "/notes/browse/New"
        assert urls["Inner"] == "/notes/edit/New/deep/inner.md"
        assert urls["Sibling"] == "/notes/browse/Old2"

    def test_names_order_and_unrelated_untouched(self):
        text_before = _read_config_text()
        svc.add_favorite("A", "/notes/edit/a.md")
        svc.add_favorite("B", "/browse")
        svc.add_favorite("C", "/habits")
        svc.update_favorites_after_rename("a.md", "z.md", False)
        items = svc.get_favorites()
        assert [f["name"] for f in items] == ["A", "B", "C"]
        assert items[1]["url"] == "/browse"
        assert items[2]["url"] == "/habits"

    def test_duplicate_url_collapses_keeping_first(self):
        svc.add_favorite("First", "/notes/edit/a.md")
        svc.add_favorite("Second", "/notes/edit/z.md")
        svc.update_favorites_after_rename("z.md", "a.md", False)
        items = svc.get_favorites()
        assert items == [_fav("First", "/notes/edit/a.md")]

    def test_failure_keeps_rename_and_warns(self, monkeypatch):
        with open(os.path.join(ptos.NOTES_DIR, "keep.md"), "w") as f:
            f.write("x")
        def boom(old_rel, new_rel, is_folder):
            raise RuntimeError("config exploded")
        monkeypatch.setattr(svc, "update_favorites_after_rename", boom)
        result = svc.svc_rename("keep.md", "kept")
        assert result["rel_path"] == "kept.md"
        assert result["warning"] == "Renamed, but favorites could not be updated"
        assert os.path.isfile(os.path.join(ptos.NOTES_DIR, "kept.md"))

    def test_project_notes_path_updated_for_folder(self):
        ptos.create_folder("", "Old")
        ptos.create_folder("Old", "sub")
        svc._write_queries_toml_key(
            "project.ptest", {"label": "PT", "notes_path": "Old"})
        svc._write_queries_toml_key(
            "project.ptest2", {"label": "PT2", "notes_path": "Old/sub"})
        svc._write_queries_toml_key(
            "project.ptest3", {"label": "PT3", "notes_path": "Other"})
        svc.svc_rename("Old", "New")
        data = ptos.get_queries()
        assert data["project.ptest"]["notes_path"] == "New"
        assert data["project.ptest2"]["notes_path"] == "New/sub"
        assert data["project.ptest3"]["notes_path"] == "Other"

    def test_notes_path_untouched_for_file_rename(self):
        svc._write_queries_toml_key(
            "project.ptest", {"label": "PT", "notes_path": "Folder"})
        svc.update_favorites_after_rename("a.md", "b.md", False)
        data = ptos.get_queries()
        assert data["project.ptest"]["notes_path"] == "Folder"


class TestRenameRouteAndPage:
    @pytest.fixture()
    def client(self):
        from ptos_web import app
        app.config["TESTING"] = True
        return app.test_client()

    def test_rename_route_returns_rel_path_and_count(self, client):
        ptos.create_file("", "star", "body")
        svc.add_favorite("Star", "/notes/edit/star.md")
        resp = client.post("/notes/rename",
                           json={"path": "star.md", "new_name": "nova"})
        data = resp.get_json()
        assert data["ok"] is True
        assert data["rel_path"] == "nova.md"
        assert data["favorites_updated"] == 1
        assert data["warning"] is None

    def test_rename_api_ignores_new_url(self, client):
        svc.add_favorite("A", "/notes/edit/a.md")
        resp = client.post("/api/favorites/rename",
                           json={"url": "/notes/edit/a.md", "name": "Z",
                                 "new_url": "/hacked", "path": "/hacked"})
        assert resp.get_json()["ok"] is True
        assert svc.get_favorites() == [_fav("Z", "/notes/edit/a.md")]

    def test_page_has_no_path_input_and_inline_editor(self):
        html = open(os.path.join(_REPO_ROOT, "web_templates",
                                 "favorites.html"),
                    encoding="utf-8").read()
        assert "prompt(" not in html
        assert 'input.type = "text"' in html
        rows = re.findall(r'fav-row-url[^>]*>', html)
        assert all("<input" not in r for r in rows)
        assert 'class="fav-row-url"' in html
