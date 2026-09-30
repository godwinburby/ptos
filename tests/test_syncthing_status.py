import json
import os
import urllib.error
import urllib.request
import datetime as dt
from urllib.parse import urlsplit

import ptos_service
import ptos_cli


CONFIG_XML = """<?xml version="1.0" encoding="UTF-8"?>
<configuration version="38">
  <gui enabled="true" tls="false" debugging="false">
    <address>127.0.0.1:8384</address>
    <apikey>abc123secret</apikey>
    <user></user>
    <password></password>
  </gui>
  <folder id="abcd-1234" label="ptos-data" path="{folder_path}" type="sendreceive">
    <filesystemType>basic</filesystemType>
  </folder>
</configuration>
"""

DB_STATUS = {"state": "idle", "stateChanged": "2026-09-30T12:45:03+05:30",
             "globalBytes": 1000, "inSyncBytes": 1000, "needBytes": 0}

MY_ID = "ABCDEFGH-JKLMNPQR-STUVWXYZ-23456789-ABCDEFGH-JKLMNPQR-STUVWXYZ-RDHAXAX"

SYSTEM_STATUS = {"myID": MY_ID, "myName": "test-pc"}

EVENTS = [{"type": "FolderCompletion", "time": "2026-09-30T11:00:00Z",
           "data": {"folder": "abcd-1234", "completion": 1.0}}]

DEVICES = [
    {"name": "android", "deviceID": "K4BHCH2-ABCDEFGH-QRSTUVWX-YZABCDEF-12345678-ABCDEFGH-QRSTUVWX-RDHAXAX",
     "lastSeen": "2026-09-28T10:00:00Z"},
    {"name": "", "deviceID": "XAJ7GJU-AAAAAAAA-BBBBBBBB-CCCCCCCC-DDDDDDDD-EEEEEEEE-FFFFFFFF-00000000",
     "lastSeen": "0001-01-01T00:00:00Z"},
]

CONNECTIONS = {"connections": {
    "K4BHCH2-ABCDEFGH-QRSTUVWX-YZABCDEF-12345678-ABCDEFGH-QRSTUVWX-RDHAXAX":
        {"connected": True, "at": "2026-09-30T12:00:00Z"},
    "XAJ7GJU-AAAAAAAA-BBBBBBBB-CCCCCCCC-DDDDDDDD-EEEEEEEE-FFFFFFFF-00000000":
        {"connected": False, "at": "0001-01-01T00:00:00Z"},
}}


class FakeResponse:
    def __init__(self, payload):
        self._payload = payload.encode("utf-8")

    def read(self):
        return self._payload

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class FakeUrlopen:
    def __init__(self, routes):
        self.routes = routes
        self.calls = []

    def __call__(self, req, timeout=None):
        url = req.full_url
        path = urlsplit(url).path
        self.calls.append((url, timeout))
        for key, payload in self.routes.items():
            if path == key:
                return FakeResponse(payload)
        raise urllib.error.URLError("Unreachable " + url)


def _patch_config(tmp_path, monkeypatch, folder_path="", xml=None):
    cfg_path = tmp_path / "config.xml"
    if xml is None:
        xml = CONFIG_XML.format(folder_path=folder_path)
    cfg_path.write_text(xml, encoding="utf-8")
    monkeypatch.setattr(ptos_service, "_syncthing_config_candidates",
                        lambda: [str(cfg_path)])
    return cfg_path


def _default_routes(events=None):
    routes = {
        "/rest/system/version": json.dumps({"version": "v2.1.5"}),
        "/rest/system/status": json.dumps(SYSTEM_STATUS),
        "/rest/db/status": json.dumps(DB_STATUS),
        "/rest/events": json.dumps(events if events is not None else EVENTS),
        "/rest/config/devices": json.dumps(DEVICES),
        "/rest/system/connections": json.dumps(CONNECTIONS),
    }
    return routes


class TestSyncthingConfig:
    def test_parse_windows_shaped_config(self, tmp_path, monkeypatch):
        _patch_config(tmp_path, monkeypatch, folder_path=str(tmp_path))
        cfg = ptos_service._syncthing_config()
        assert cfg["ok"] is True
        assert cfg["apikey"] == "abc123secret"
        assert cfg["address"] == "http://127.0.0.1:8384"
        assert cfg["folders"][0]["id"] == "abcd-1234"
        assert cfg["folders"][0]["path"] == str(tmp_path)

    def test_address_without_scheme_gets_http(self, tmp_path, monkeypatch):
        _patch_config(tmp_path, monkeypatch,
                      xml="<configuration><gui enabled=\"true\"><apikey>k</apikey>"
                          "<address>:8384</address></gui></configuration>")
        assert ptos_service._syncthing_config()["address"] == "http://:8384"

    def test_address_defaults_to_8384(self, tmp_path, monkeypatch):
        _patch_config(tmp_path, monkeypatch,
                      xml="<configuration><gui enabled=\"true\"><apikey>k</apikey>"
                          "</gui></configuration>")
        assert ptos_service._syncthing_config()["address"] == "http://127.0.0.1:8384"

    def test_gui_disabled_is_error(self, tmp_path, monkeypatch):
        _patch_config(tmp_path, monkeypatch,
                      xml="<configuration><gui enabled=\"false\"><apikey>k</apikey>"
                          "</gui></configuration>")
        cfg = ptos_service._syncthing_config()
        assert cfg["ok"] is False
        assert "disabled" in cfg["error"]

    def test_missing_apikey_is_error(self, tmp_path, monkeypatch):
        _patch_config(tmp_path, monkeypatch,
                      xml="<configuration><gui enabled=\"true\"></gui></configuration>")
        cfg = ptos_service._syncthing_config()
        assert cfg["ok"] is False
        assert "API key" in cfg["error"]

    def test_missing_config_all_candidates(self, tmp_path, monkeypatch):
        monkeypatch.setattr(ptos_service, "_syncthing_config_candidates",
                            lambda: [str(tmp_path / "nope.xml")])
        cfg = ptos_service._syncthing_config()
        assert cfg["ok"] is False
        assert "config.xml not found" in cfg["error"]

    def test_folder_path_expands_home(self, tmp_path, monkeypatch):
        _patch_config(tmp_path, monkeypatch, folder_path="~/ptos-data")
        path = ptos_service._syncthing_config()["folders"][0]["path"]
        assert os.path.isabs(path)
        assert "~" not in path
        assert path.endswith("ptos-data")

    def test_folder_label_falls_back_to_id(self, tmp_path, monkeypatch):
        _patch_config(tmp_path, monkeypatch,
                      xml=CONFIG_XML.format(folder_path=str(tmp_path)).replace(
                          ' label="ptos-data"', ""))
        assert ptos_service._syncthing_config()["folders"][0]["label"] == "abcd-1234"


class TestMatchFolder:
    def test_exact_match(self):
        f = [{"id": "x", "label": "x", "path": os.path.abspath("C:/data")}]
        assert ptos_service._match_syncthing_folder(f, "C:/data") is f[0]

    def test_no_match(self, tmp_path):
        f = [{"id": "x", "label": "x", "path": str(tmp_path / "elsewhere")}]
        assert ptos_service._match_syncthing_folder(f, str(tmp_path)) is None

    def test_case_insensitive_on_windows(self, monkeypatch, tmp_path):
        monkeypatch.setattr(ptos_service.sys, "platform", "win32")
        f = [{"id": "x", "label": "x", "path": str(tmp_path).upper()}]
        assert ptos_service._match_syncthing_folder(f, str(tmp_path)) is f[0]


class TestLastSyncFromLog:
    LOG = "[INF] 2026-09-30 09:12:44 Folder \"ptos-data\" (abcd-1234) synced in 1.42s\n" \
          "2026-09-30 10:00:00 another line\n" \
          "[INF] 2026-09-30 08:00:00 Folder \"ptos-data\" synced in 0.5s\n"

    def test_returns_last_synced_timestamp(self, tmp_path, monkeypatch):
        log = tmp_path / "syncthing.log"
        log.write_text(self.LOG, encoding="utf-8")
        monkeypatch.setattr(ptos_service, "_syncthing_log_candidates", lambda: [str(log)])
        assert ptos_service._last_sync_from_log() == "2026-09-30 08:00:00"

    def test_returns_none_when_log_missing(self, tmp_path, monkeypatch):
        monkeypatch.setattr(ptos_service, "_syncthing_log_candidates",
                            lambda: [str(tmp_path / "nope.log")])
        assert ptos_service._last_sync_from_log() is None

    def test_returns_none_when_no_sync_lines(self, tmp_path, monkeypatch):
        log = tmp_path / "syncthing.log"
        log.write_text("2026-09-30 09:12:44 unrelated message\n", encoding="utf-8")
        monkeypatch.setattr(ptos_service, "_syncthing_log_candidates", lambda: [str(log)])
        assert ptos_service._last_sync_from_log() is None


class TestFmtSyncTime:
    def test_none(self):
        assert ptos_service._fmt_sync_time(None) is None

    def test_naive_log_timestamp_passes_through(self):
        assert ptos_service._fmt_sync_time("2026-09-30 09:12:44") == "2026-09-30 09:12 AM"

    def test_z_suffix_converts_to_local(self):
        ref = (dt.datetime.fromisoformat("2026-09-30T11:00:00+00:00")
               .astimezone().strftime("%Y-%m-%d %I:%M %p"))
        assert ptos_service._fmt_sync_time("2026-09-30T11:00:00Z") == ref

    def test_offset_converts_to_local(self):
        ref = (dt.datetime.fromisoformat("2026-09-30T12:45:03+05:30")
               .astimezone().strftime("%Y-%m-%d %I:%M %p"))
        assert ptos_service._fmt_sync_time("2026-09-30T12:45:03+05:30") == ref

    def test_datetime_instance(self):
        assert ptos_service._fmt_sync_time(dt.datetime(2026, 9, 30, 9, 12, 44)) == "2026-09-30 09:12 AM"

    def test_unparsable_returns_raw(self):
        assert ptos_service._fmt_sync_time("garbage") == "garbage"


class TestGetSyncthingStatus:
    def _install_routes(self, monkeypatch, routes):
        fake = FakeUrlopen(routes)
        monkeypatch.setattr(urllib.request, "urlopen", fake)
        return fake

    def test_full_pipeline(self, tmp_path, monkeypatch):
        _patch_config(tmp_path, monkeypatch, folder_path=str(tmp_path))
        monkeypatch.setattr(ptos_service, "BASE_DIR", str(tmp_path))
        routes = _default_routes()
        fake = self._install_routes(monkeypatch, routes)
        s = ptos_service.get_syncthing_status()
        assert s["ok"] is True
        assert s["reachable"] is True
        assert s["version"] == "v2.1.5"
        assert s["my_id"] == MY_ID
        assert s["my_name"] == "test-pc"
        assert s["folder"]["id"] == "abcd-1234"
        assert s["state"] == "idle"
        assert s["completion_pct"] == 100.0
        assert s["last_sync"] == "2026-09-30T11:00:00Z"
        assert s["last_sync_source"] == "api"
        assert s["last_sync_fmt"].endswith("T11:00:00Z") is False
        assert ptos_service._fmt_sync_time(s["last_sync"]) == s["last_sync_fmt"]
        assert s["devices_connected"] == 1
        assert len(s["devices"]) == 2
        assert s["devices"][0]["connected"] is True
        assert s["devices"][0]["last_seen"] == "2026-09-28T10:00:00Z"
        assert s["devices"][0]["last_seen_fmt"] == ptos_service._fmt_sync_time("2026-09-28T10:00:00Z")
        assert s["devices"][1]["connected"] is False
        assert s["devices"][1]["last_seen"] is None
        assert s["devices"][1]["last_seen_fmt"] is None
        assert any("timeout=0" in url for url, _ in fake.calls)

    def test_events_empty_falls_back_to_log(self, tmp_path, monkeypatch):
        _patch_config(tmp_path, monkeypatch, folder_path=str(tmp_path))
        monkeypatch.setattr(ptos_service, "BASE_DIR", str(tmp_path))
        monkeypatch.setattr(ptos_service, "_syncthing_log_candidates", lambda: [])
        self._install_routes(monkeypatch, _default_routes(events=[]))
        s = ptos_service.get_syncthing_status()
        assert s["last_sync"] is None
        log = tmp_path / "syncthing.log"
        log.write_text("[x] 2026-09-30 09:12:44 synced in 2.00s\n", encoding="utf-8")
        monkeypatch.setattr(ptos_service, "_syncthing_log_candidates", lambda: [str(log)])
        fake = self._install_routes(monkeypatch, {"/rest/system/version": json.dumps({"version": "v1.0"})})
        s = ptos_service.get_syncthing_status()
        assert s["last_sync"] == "2026-09-30 09:12:44"
        assert s["last_sync_source"] == "log"

    def test_incomplete_event_is_ignored(self, tmp_path, monkeypatch):
        _patch_config(tmp_path, monkeypatch, folder_path=str(tmp_path))
        monkeypatch.setattr(ptos_service, "BASE_DIR", str(tmp_path))
        ev = [{"type": "FolderCompletion", "time": "2026-09-30T10:00:00Z",
               "data": {"folder": "abcd-1234", "completion": 0.5}}]
        self._install_routes(monkeypatch, _default_routes(events=ev))
        s = ptos_service.get_syncthing_status()
        assert s["last_sync"] is None

    def test_event_for_other_folder_is_ignored(self, tmp_path, monkeypatch):
        _patch_config(tmp_path, monkeypatch, folder_path=str(tmp_path))
        monkeypatch.setattr(ptos_service, "BASE_DIR", str(tmp_path))
        ev = [{"type": "FolderCompletion", "time": "2026-09-30T10:00:00Z",
               "data": {"folder": "other-folder", "completion": 1.0}}]
        self._install_routes(monkeypatch, _default_routes(events=ev))
        s = ptos_service.get_syncthing_status()
        assert s["last_sync"] is None

    def test_unreachable_daemon(self, tmp_path, monkeypatch):
        _patch_config(tmp_path, monkeypatch, folder_path=str(tmp_path))
        monkeypatch.setattr(ptos_service, "BASE_DIR", str(tmp_path))
        fake = self._install_routes(monkeypatch, {})
        s = ptos_service.get_syncthing_status()
        assert s["ok"] is True
        assert s["reachable"] is False
        assert "not reachable" in s["error"]
        assert s["folder"]["id"] == "abcd-1234"

    def test_config_missing(self, tmp_path, monkeypatch):
        monkeypatch.setattr(ptos_service, "_syncthing_config_candidates",
                            lambda: [str(tmp_path / "nope.xml")])
        s = ptos_service.get_syncthing_status()
        assert s["ok"] is False
        assert s["reachable"] is False
        assert "config.xml" in s["error"]

    def test_folder_unmatched(self, tmp_path, monkeypatch):
        _patch_config(tmp_path, monkeypatch, folder_path=str(tmp_path / "other"))
        monkeypatch.setattr(ptos_service, "BASE_DIR", str(tmp_path))
        self._install_routes(monkeypatch, _default_routes())
        s = ptos_service.get_syncthing_status()
        assert s["folder"] is None

    def test_full_sync_idle_as_of(self, tmp_path, monkeypatch):
        _patch_config(tmp_path, monkeypatch, folder_path=str(tmp_path))
        monkeypatch.setattr(ptos_service, "BASE_DIR", str(tmp_path))
        self._install_routes(monkeypatch, _default_routes(events=[]))
        s = ptos_service.get_syncthing_status()
        assert s["fully_in_sync_as_of"] == "2026-09-30T12:45:03+05:30"

    def test_missing_system_status_is_not_fatal(self, tmp_path, monkeypatch):
        _patch_config(tmp_path, monkeypatch, folder_path=str(tmp_path))
        monkeypatch.setattr(ptos_service, "BASE_DIR", str(tmp_path))
        self._install_routes(monkeypatch, {"/rest/system/version": json.dumps({"version": "v2.1.5"})})
        s = ptos_service.get_syncthing_status()
        assert s["ok"] is True
        assert s["my_id"] is None


class TestCli:
    def test_run_sync_status_prints_full_report(self, tmp_path, monkeypatch, capsys):
        status = {
            "ok": True, "reachable": True, "version": "v2.1.5",
            "address": "http://127.0.0.1:8384",
            "my_id": MY_ID, "my_name": "test-pc",
            "folder": {"id": "abcd", "label": "ptos-data", "path": str(tmp_path)},
            "state": "idle", "completion_pct": 100.0, "need_bytes": 0,
            "last_sync": "2026-09-30T11:00:00Z", "last_sync_source": "api",
            "last_sync_fmt": "2026-09-30 04:30 PM", "fully_in_sync_as_of_fmt": None,
            "devices": [{"name": "android", "id": "K4B...", "connected": True,
                         "last_seen": "2026-09-28T10:00:00Z", "last_seen_fmt": "2026-09-28 10:00 AM"}],
            "devices_connected": 1, "error": None,
        }
        monkeypatch.setattr(ptos_service, "get_syncthing_status", lambda: status)
        ptos_cli.run_sync_status()
        out = capsys.readouterr().out
        assert "v2.1.5" in out
        assert "ptos-data" in out
        assert "This dev:" in out
        assert MY_ID in out
        assert "2026-09-30 04:30 PM" in out
        assert "2026-09-30T11:00:00Z" not in out
        assert "Syncthing event log" in out
        assert "Sync setup" not in out

    def test_run_sync_status_prints_setup_guide_when_unpaired(self, tmp_path, monkeypatch, capsys):
        status = {
            "ok": True, "reachable": True, "version": "v2.1.5",
            "address": "http://127.0.0.1:8384",
            "my_id": MY_ID, "my_name": "test-pc",
            "folder": {"id": "abcd-1234", "label": "ptos-data", "path": str(tmp_path)},
            "state": "idle", "completion_pct": 100.0, "need_bytes": 0,
            "last_sync": None, "last_sync_source": None,
            "fully_in_sync_as_of": "2026-09-30T12:45:03+05:30",
            "fully_in_sync_as_of_fmt": "2026-09-30 12:45 PM",
            "devices": [], "devices_connected": 0, "error": None,
        }
        monkeypatch.setattr(ptos_service, "get_syncthing_status", lambda: status)
        ptos_cli.run_sync_status()
        out = capsys.readouterr().out
        assert "This dev:" in out
        assert MY_ID in out
        assert "Sync setup (one-time" in out
        assert "Add Remote Device" in out
        assert "Send & Receive" in out
        assert "abcd-1234" in out
        assert str(tmp_path) in out
        assert "--set-config syncthing.serve false" in out

    def test_run_sync_status_fully_in_sync_fallback(self, tmp_path, monkeypatch, capsys):
        status = {
            "ok": True, "reachable": True, "version": None,
            "address": "http://127.0.0.1:8384",
            "folder": {"id": "abcd", "label": "ptos-data", "path": str(tmp_path)},
            "state": "idle", "completion_pct": 100.0, "need_bytes": 0,
            "last_sync": None, "last_sync_source": None,
            "fully_in_sync_as_of": "2026-09-30T12:45:03+05:30",
            "fully_in_sync_as_of_fmt": "2026-09-30 12:45 PM",
            "devices": [], "devices_connected": 0, "error": None,
        }
        monkeypatch.setattr(ptos_service, "get_syncthing_status", lambda: status)
        ptos_cli.run_sync_status()
        out = capsys.readouterr().out
        assert "fully in sync as of 2026-09-30 12:45 PM" in out
        assert "2026-09-30T12:45:03" not in out

    def test_run_sync_status_config_missing(self, monkeypatch, capsys):
        status = {"ok": False, "error": "Syncthing config.xml not found — install and configure Syncthing first"}
        monkeypatch.setattr(ptos_service, "get_syncthing_status", lambda: status)
        ptos_cli.run_sync_status()
        out = capsys.readouterr().out
        assert "config.xml not found" in out
        assert "does not sync anything itself" in out

    def test_no_folder_match_hint(self, tmp_path, monkeypatch, capsys):
        status = {
            "ok": True, "reachable": True, "version": "v2.1.5",
            "address": "http://127.0.0.1:8384", "folder": None,
            "state": None, "completion_pct": None, "need_bytes": None,
            "last_sync": None, "last_sync_source": None, "fully_in_sync_as_of": None,
            "devices": [], "devices_connected": 0, "error": None,
        }
        monkeypatch.setattr(ptos_service, "get_syncthing_status", lambda: status)
        ptos_cli.run_sync_status()
        out = capsys.readouterr().out
        assert "no configured Syncthing folder matches" in out

    def test_main_dispatch_sync_status(self, tmp_path, monkeypatch, capsys):
        monkeypatch.setattr(ptos_service, "get_syncthing_status",
                            lambda: {"ok": False,
                                     "error": "Syncthing config.xml not found — install and configure Syncthing first"})
        monkeypatch.setattr("sys.argv", ["ptos", "--sync-status"])
        ptos_cli.main()
        assert "config.xml not found" in capsys.readouterr().out


class TestWeb:
    def test_api_route(self, tmp_path, monkeypatch):
        from ptos_web import app
        status = {"ok": True, "reachable": True, "folder": None, "error": None}
        monkeypatch.setattr(ptos_service, "get_syncthing_status", lambda: status)
        client = app.test_client()
        resp = client.get("/api/syncthing/status")
        assert resp.status_code == 200
        assert resp.get_json()["ok"] is True

    def test_settings_page_renders_card(self, tmp_path, monkeypatch):
        from ptos_web import app
        status = {
            "ok": True, "reachable": True, "version": "v2.1.5",
            "address": "http://127.0.0.1:8384",
            "my_id": MY_ID, "my_name": "test-pc",
            "folder": {"id": "abcd", "label": "ptos-data", "path": str(tmp_path)},
            "state": "idle", "completion_pct": 100.0, "need_bytes": 0,
            "last_sync": "2026-09-30T11:00:00Z", "last_sync_source": "api",
            "last_sync_fmt": "2026-09-30 04:30 PM", "fully_in_sync_as_of_fmt": None,
            "devices": [{"name": "android", "id": "K4B...", "connected": True,
                         "last_seen": "2026-09-28T10:00:00Z", "last_seen_fmt": "2026-09-28 10:00 AM"}],
            "devices_connected": 1, "error": None,
        }
        monkeypatch.setattr(ptos_service, "get_syncthing_status", lambda: status)
        client = app.test_client()
        resp = client.get("/settings")
        html = resp.get_data(as_text=True)
        assert resp.status_code == 200
        assert 'id="sec-syncthing"' in html
        assert 'href="#sec-syncthing"' in html
        assert "v2.1.5" in html
        assert "This device" in html
        assert MY_ID in html
        assert "copyStId()" in html
        assert "2026-09-30 04:30 PM" in html
        assert "2026-09-30T11:00:00Z" not in html
        assert "refreshSyncthing()" in html
        assert "/api/syncthing/status" in html
        assert "syncthing-status-body" in html
        assert 'id="sync-setup-guide"' in html
        assert "Set up sync between two devices" in html
        assert "Add Remote Device" in html
        assert 'id="sync-setup-guide" open' not in html

    def test_settings_page_no_config(self, tmp_path, monkeypatch):
        from ptos_web import app
        monkeypatch.setattr(
            ptos_service, "get_syncthing_status",
            lambda: {"ok": False, "reachable": False, "error": "Syncthing config.xml not found — install and configure Syncthing first"})
        client = app.test_client()
        resp = client.get("/settings")
        html = resp.get_data(as_text=True)
        assert "config.xml not found" in html

    def test_settings_page_fully_in_sync_branch(self, tmp_path, monkeypatch):
        from ptos_web import app
        status = {
            "ok": True, "reachable": True, "version": None,
            "address": "http://127.0.0.1:8384",
            "folder": {"id": "abcd", "label": "ptos-data", "path": str(tmp_path)},
            "state": "idle", "completion_pct": 100.0, "need_bytes": 0,
            "last_sync": None, "last_sync_source": None,
            "fully_in_sync_as_of": "2026-09-30T12:45:03+05:30",
            "fully_in_sync_as_of_fmt": "2026-09-30 12:45 PM",
            "devices": [], "devices_connected": 0, "error": None,
        }
        monkeypatch.setattr(ptos_service, "get_syncthing_status", lambda: status)
        client = app.test_client()
        html = client.get("/settings").get_data(as_text=True)
        assert "fully in sync" in html
        assert "2026-09-30 12:45 PM" in html
        assert "2026-09-30T12:45:03" not in html
        assert 'id="sync-setup-guide" open' in html

    def test_settings_page_unmatched_folder_branch(self, tmp_path, monkeypatch):
        from ptos_web import app
        status = {
            "ok": True, "reachable": True, "version": "v2.1.5",
            "address": "http://127.0.0.1:8384", "folder": None,
            "state": None, "completion_pct": None, "need_bytes": None,
            "last_sync": None, "last_sync_source": None, "fully_in_sync_as_of": None,
            "devices": [], "devices_connected": 0, "error": None,
        }
        monkeypatch.setattr(ptos_service, "get_syncthing_status", lambda: status)
        client = app.test_client()
        html = client.get("/settings").get_data(as_text=True)
        assert "No configured Syncthing folder matches this data folder" in html