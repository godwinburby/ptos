import gzip
import os
import re

import pytest
from flask import Response

import ptos

TEMPLATE_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "web_templates")
STARTER_CONFIG = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "starters", "starter_config.toml")

GZIP = {"Accept-Encoding": "gzip"}
# gzip is skipped for loopback clients, so compression assertions must come
# from a non-loopback address.
REMOTE = {"REMOTE_ADDR": "203.0.113.7"}


class TestGzip:
    def test_html_page_is_compressed(self):
        from ptos_web import app
        resp = app.test_client().get("/", headers=GZIP, environ_base=REMOTE)
        assert resp.status_code == 200
        assert resp.headers.get("Content-Encoding") == "gzip"
        assert int(resp.headers["Content-Length"]) == len(resp.get_data())
        body = gzip.decompress(resp.get_data()).decode("utf-8")
        assert "<!DOCTYPE html>" in body

    def test_compressed_is_smaller_than_identity(self):
        from ptos_web import app
        client = app.test_client()
        zipped = client.get("/", headers=GZIP, environ_base=REMOTE)
        plain = client.get("/", headers={"Accept-Encoding": "identity"},
                           environ_base=REMOTE)
        assert plain.headers.get("Content-Encoding") is None
        assert len(zipped.get_data()) < len(plain.get_data())

    def test_vary_header_includes_accept_encoding(self):
        from ptos_web import app
        resp = app.test_client().get("/", headers=GZIP, environ_base=REMOTE)
        assert "Accept-Encoding" in resp.headers.get("Vary", "")

    def test_loopback_client_not_compressed(self):
        from ptos_web import app
        resp = app.test_client().get("/", headers=GZIP)
        assert resp.headers.get("Content-Encoding") is None

    def test_not_compressed_without_accept_encoding(self):
        from ptos_web import app
        resp = app.test_client().get("/", headers={"Accept-Encoding": "identity"},
                                     environ_base=REMOTE)
        assert resp.headers.get("Content-Encoding") is None

    def test_small_body_left_alone(self):
        import ptos_web
        with ptos_web.app.test_request_context("/", headers=GZIP):
            resp = Response("tiny", mimetype="text/plain")
            out = ptos_web._gzip_response(resp)
        assert "Content-Encoding" not in out.headers

    def test_binary_type_not_compressed(self):
        import ptos_web
        with ptos_web.app.test_request_context("/", headers=GZIP):
            resp = Response(b"\x89PNG" + b"0" * 4000, mimetype="image/png")
            out = ptos_web._gzip_response(resp)
        assert "Content-Encoding" not in out.headers

    def test_streamed_sse_never_compressed(self):
        import ptos_web

        def gen():
            yield "data: ping\n\n"

        with ptos_web.app.test_request_context("/", headers=GZIP):
            resp = Response(gen(), mimetype="text/event-stream")
            out = ptos_web._gzip_response(resp)
        assert "Content-Encoding" not in out.headers

    def test_already_encoded_left_alone(self):
        import ptos_web
        with ptos_web.app.test_request_context("/", headers=GZIP):
            resp = Response(b"x" * 4000, mimetype="text/plain",
                            headers={"Content-Encoding": "br"})
            out = ptos_web._gzip_response(resp)
        assert out.headers["Content-Encoding"] == "br"

    def test_error_status_not_compressed(self):
        import ptos_web
        with ptos_web.app.test_request_context("/", headers=GZIP):
            resp = Response("x" * 4000, mimetype="text/plain", status=404)
            out = ptos_web._gzip_response(resp)
        assert "Content-Encoding" not in out.headers


class TestStaticCacheControl:
    def test_versioned_asset_is_immutable(self):
        import ptos_web
        resp = ptos_web.app.test_client().get(
            f"/static/css/components.css?v={ptos_web.ASSET_VERSION}")
        assert "immutable" in resp.headers.get("Cache-Control", "")

    def test_unversioned_asset_revalidates(self):
        import ptos_web
        resp = ptos_web.app.test_client().get("/static/css/components.css")
        assert resp.headers.get("Cache-Control") == "no-cache"

    def test_manifest_never_cached(self):
        import ptos_web
        resp = ptos_web.app.test_client().get("/static/manifest.json?v=99")
        assert resp.headers.get("Cache-Control") == "no-cache"

    def test_sw_js_never_cached(self):
        import ptos_web
        resp = ptos_web.app.test_client().get("/static/sw.js?v=99")
        assert resp.headers.get("Cache-Control") == "no-cache"


class TestServiceWorkerRetired:
    def _read(self, name):
        return open(os.path.join(TEMPLATE_DIR, name), encoding="utf-8").read()

    def _read_static(self, name):
        root = os.path.dirname(TEMPLATE_DIR)
        return open(os.path.join(root, "web_static", name), encoding="utf-8").read()

    def test_sw_js_does_not_precache_or_intercept(self):
        text = self._read_static("sw.js")
        assert "addEventListener('fetch'" not in text
        assert 'addEventListener("fetch"' not in text
        assert "addAll" not in text
        assert "cache.put" not in text

    def test_sw_js_self_destructs(self):
        text = self._read_static("sw.js")
        assert '"activate"' in text
        assert "caches.delete" in text
        assert "registration.unregister" in text

    def test_base_no_longer_registers_a_worker(self):
        text = self._read("base.html")
        assert "serviceWorker.register" not in text

    def test_base_unregisters_and_clears_caches(self):
        text = self._read("base.html")
        assert "getRegistrations" in text
        assert "unregister" in text
        assert "caches.keys" in text


class TestAssetVersionHelper:
    def test_av_appends_version(self):
        import ptos_web
        assert ptos_web.av("/static/js/drag.js") == \
            f"/static/js/drag.js?v={ptos_web.ASSET_VERSION}"

    def test_av_preserves_existing_query(self):
        import ptos_web
        out = ptos_web.av("/static/x.js?a=1")
        assert out.startswith("/static/x.js?a=1&")
        assert f"v={ptos_web.ASSET_VERSION}" in out


class TestAssetVersionAuto:
    """The version is derived from web_static/ contents, so a changed asset
    gets a new URL with no manual bump."""

    def test_version_is_short_hex(self):
        import ptos_web
        assert re.fullmatch(r"[0-9a-f]{10}", ptos_web.ASSET_VERSION)

    def test_changing_a_static_file_changes_version(self, tmp_path, monkeypatch):
        import ptos_web
        static = tmp_path / "web_static"
        static.mkdir()
        (static / "a.css").write_text("body{}", encoding="utf-8")
        monkeypatch.setattr(ptos_web, "_basedir", str(tmp_path))
        first = ptos_web._compute_asset_version()
        (static / "a.css").write_text("body{color:red}", encoding="utf-8")
        assert ptos_web._compute_asset_version() != first

    def test_adding_a_static_file_changes_version(self, tmp_path, monkeypatch):
        import ptos_web
        static = tmp_path / "web_static"
        static.mkdir()
        (static / "a.css").write_text("body{}", encoding="utf-8")
        monkeypatch.setattr(ptos_web, "_basedir", str(tmp_path))
        first = ptos_web._compute_asset_version()
        (static / "b.js").write_text("x", encoding="utf-8")
        assert ptos_web._compute_asset_version() != first

    def test_dev_mode_recomputes_on_file_change(self, tmp_path, monkeypatch):
        import ptos_web
        static = tmp_path / "web_static"
        static.mkdir()
        (static / "a.css").write_text("body{}", encoding="utf-8")
        monkeypatch.setattr(ptos_web, "_basedir", str(tmp_path))
        monkeypatch.setattr(ptos_web, "ASSET_VERSION", "start00000")
        monkeypatch.setattr(ptos_web, "_ASSET_DEV", True)
        monkeypatch.setattr(ptos_web, "_ASSET_DEV_STATE",
                            {"checked": 0.0, "mtime": 0.0})
        ptos_web._refresh_asset_version_if_dev()
        first = ptos_web.ASSET_VERSION
        assert first != "start00000"
        (static / "a.css").write_text("body{color:red}", encoding="utf-8")
        monkeypatch.setattr(ptos_web, "_ASSET_DEV_STATE",
                            {"checked": 0.0, "mtime": 0.0})
        ptos_web._refresh_asset_version_if_dev()
        assert ptos_web.ASSET_VERSION != first


class TestTemplatesUseVersionedAssets:
    """Every web_static reference in a template must go through av() (or be on
    the never-cache allowlist), so one bump of ASSET_VERSION covers the app."""

    ALLOWED = ("/static/manifest.json", "/static/sw.js")

    def test_no_unversioned_static_refs(self):
        offenders = []
        for name in sorted(os.listdir(TEMPLATE_DIR)):
            if not name.endswith(".html"):
                continue
            text = open(os.path.join(TEMPLATE_DIR, name), encoding="utf-8").read()
            for ref in re.findall(r"/static/[A-Za-z0-9_./-]+", text):
                if any(ref.startswith(a) for a in self.ALLOWED):
                    continue
                if f"av('{ref}')" not in text:
                    offenders.append(f"{name}: {ref}")
        assert not offenders, "unversioned static refs: " + ", ".join(offenders)

    def test_never_cache_allowlist_matches_web(self):
        import ptos_web
        assert set(ptos_web._STATIC_NEVER_CACHE) == set(self.ALLOWED)


class TestTemplatesAutoReload:
    def test_default_off(self):
        import ptos_web
        assert ptos_web.app.config["TEMPLATES_AUTO_RELOAD"] is False

    def test_as_bool_coercions(self):
        import ptos_web
        for truthy in (True, "true", "TRUE", "1", "yes", "on"):
            assert ptos_web._as_bool(truthy) is True
        for falsy in (False, "false", "0", "no", "off", "", None):
            assert ptos_web._as_bool(falsy) is False

    def test_starter_ships_the_key(self):
        text = open(STARTER_CONFIG, encoding="utf-8").read()
        assert re.search(r"^templates_auto_reload\s*=\s*false", text, re.M)

    def test_starter_reads_true_when_configured(self, monkeypatch):
        import ptos_web
        monkeypatch.setattr(ptos, "get_config",
                            lambda: {"server": {"templates_auto_reload": True}})
        assert ptos_web._as_bool(ptos_web._cfg_server("templates_auto_reload", False)) is True

    def test_missing_config_defaults_false(self, monkeypatch):
        import ptos_web
        monkeypatch.setattr(ptos, "get_config", lambda: {})
        assert ptos_web._as_bool(ptos_web._cfg_server("templates_auto_reload", False)) is False
