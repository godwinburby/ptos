"""Behaviour that must stay safe rather than change: DEBUG, and host exposure.

A security posture with no test is a posture that decays, so these pin the
settings that are already correct.
"""
import os
import re

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _src(name):
    return open(os.path.join(REPO, name), encoding="utf-8").read()


class TestDebugStaysOff:
    def test_debug_is_off(self):
        import ptos_web
        assert ptos_web.app.config["DEBUG"] is False
        assert ptos_web.app.debug is False

    def test_debug_is_pinned_at_import(self):
        # The single assignment lives at module scope, immediately after the
        # Flask() construction — nothing reads an env var or config to change it.
        src = _src("ptos_web.py")
        assert src.count("DEBUG") == 1, "more than one DEBUG reference"
        assert 'app.config["DEBUG"] = False' in src

    def test_no_launcher_enables_debug(self):
        # app.run(debug=...) and the reloader both expose tracebacks.
        for name in ("ptos_web.py", "desktop_app.py"):
            for call in re.findall(r"\.run\(([^)]*)\)", _src(name)):
                assert not re.search(r"debug\s*=", call), (name, call)
                assert not re.search(r"use_reloader\s*=\s*True", call), (name, call)

    def test_no_template_exposes_debug(self):
        tdir = os.path.join(REPO, "web_templates")
        for name in os.listdir(tdir):
            if name.endswith(".html"):
                text = open(os.path.join(tdir, name), encoding="utf-8").read()
                assert "config.DEBUG" not in text, name
                assert "app.debug" not in text, name


class TestLoopbackDefault:
    def test_starter_binds_loopback(self):
        starter = os.path.join(REPO, "starters", "starter_config.toml")
        text = open(starter, encoding="utf-8").read()
        assert re.search(r'^host\s*=\s*"127\.0\.0\.1"', text, re.M)

    def test_desktop_app_never_binds_all_interfaces(self):
        src = _src("desktop_app.py")
        assert '"0.0.0.0"' not in src
        assert 'host="127.0.0.1"' in src


class TestExposedWithoutAuthWarning:
    """Binding beyond loopback with auth off is the one dangerous misconfig."""

    def test_warns_for_a_public_bind_without_auth(self, capsys):
        import ptos_web
        assert ptos_web._warn_if_exposed("0.0.0.0", {"enabled": False}) is True
        out = capsys.readouterr().out
        assert "WARNING" in out and "0.0.0.0" in out
        assert "Enable auth" in out

    def test_warns_when_auth_section_is_absent(self, capsys):
        import ptos_web
        assert ptos_web._warn_if_exposed("192.168.1.5", None) is True
        assert "WARNING" in capsys.readouterr().out

    def test_quiet_on_loopback(self, capsys):
        import ptos_web
        for host in ("127.0.0.1", "localhost"):
            assert ptos_web._warn_if_exposed(host, {"enabled": False}) is False
        assert capsys.readouterr().out == ""

    def test_quiet_when_auth_is_enabled(self, capsys):
        import ptos_web
        assert ptos_web._warn_if_exposed(
            "0.0.0.0", {"enabled": True, "username": "u"}) is False
        assert capsys.readouterr().out == ""


class TestHttpExceptionsKeepTheirStatus:
    """@app.errorhandler(Exception) also matches every HTTPException.

    Left unguarded it reported a missing page as a 500 and logged a full
    traceback, so ordinary 404/405 traffic looked like a server fault and
    filled the log.
    """

    @staticmethod
    def _client(monkeypatch):
        import ptos_web
        monkeypatch.setattr(ptos_web, "_check_auth", lambda u, p: True)
        return ptos_web.app.test_client()

    def test_unknown_route_is_404_not_500(self, monkeypatch):
        c = self._client(monkeypatch)
        assert c.get("/definitely-not-a-route-xyz").status_code == 404

    def test_unknown_api_route_is_404(self, monkeypatch):
        c = self._client(monkeypatch)
        assert c.get("/api/nope").status_code == 404

    def test_missing_static_file_is_404(self, monkeypatch):
        c = self._client(monkeypatch)
        assert c.get("/static/definitely-not-here.js").status_code == 404

    def test_wrong_method_is_405(self, monkeypatch):
        c = self._client(monkeypatch)
        assert c.post("/").status_code == 405

    def test_http_exception_is_returned_untouched(self):
        import ptos_web
        from werkzeug.exceptions import NotFound
        with ptos_web.app.test_request_context("/some/missing/page"):
            result = ptos_web.handle_unexpected_error(NotFound())
        assert isinstance(result, NotFound)

    def test_http_exception_is_not_logged_as_an_error(self, caplog):
        import logging
        import ptos_web
        from werkzeug.exceptions import NotFound
        with ptos_web.app.test_request_context("/some/missing/page"):
            with caplog.at_level(logging.ERROR, logger="ptos_web"):
                ptos_web.handle_unexpected_error(NotFound())
        assert not [r for r in caplog.records if r.levelno >= logging.ERROR]

    def test_a_genuine_error_is_still_a_500(self):
        import ptos_web
        with ptos_web.app.test_request_context("/some/page"):
            body, code = ptos_web.handle_unexpected_error(
                RuntimeError("boom"))
        assert code == 500