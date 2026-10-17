"""desktop_app.py must parse and import: it shipped with an IndentationError
(mis-indented import inside _Api.close_app) that nothing compiled, so the
Windows desktop wrapper could not start (pre-modularization spec A1)."""
import os
import py_compile

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DESKTOP = os.path.join(REPO, "desktop_app.py")


def test_desktop_app_compiles():
    py_compile.compile(DESKTOP, doraise=True)


def test_desktop_app_imports_without_optional_deps():
    import desktop_app
    assert hasattr(desktop_app, "_Api")
    assert desktop_app._has_webview() in (True, False)


def test_close_app_runs(monkeypatch):
    import desktop_app
    monkeypatch.setattr(desktop_app, "_destroy_window", lambda: None)
    api = desktop_app._Api(5000)
    api.close_app()
    assert desktop_app._stopping is True
    monkeypatch.setattr(desktop_app, "_stopping", False)
