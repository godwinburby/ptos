import os
import datetime as dt
import tomli_w
import ptos
import ptos_cli
import ptos_service as svc
import pytest


def _set_config(log_sessions):
    cfg = ptos.get_config()
    cfg.setdefault("pomodoro", {})["log_sessions"] = bool(log_sessions)
    with open(ptos.CONFIG_PATH, "wb") as f:
        tomli_w.dump(cfg, f)
    ptos._invalidate_all()


def _without_type(tname):
    schema = ptos.get_schema()
    allowed = [t for t in schema.get("types", {}).get("allowed", [])
               if t != tname]
    schema["types"]["allowed"] = allowed
    with open(ptos.SCHEMA_PATH, "wb") as f:
        tomli_w.dump(schema, f)
    ptos._invalidate_all()


def _clean_cache():
    ptos._CACHE.clear()


class TestPomodoroLogService:
    def test_log_appends_record(self):
        _clean_cache()
        result = svc.pomodoro_log("Write tests", 25)
        assert result["ok"] is True
        assert result["line"].startswith(dt.date.today().isoformat())
        assert "type=pomodoro" in result["line"]
        assert "task=Write tests" in result["line"]
        assert "minutes=25" in result["line"]

    def test_log_with_date(self):
        _clean_cache()
        svc.pomodoro_log("work", 50, date="2026-03-02")
        filepath = os.path.join(ptos.RECORDS_DIR, "2026.log")
        with open(filepath, encoding="utf-8") as f:
            content = f.read()
        assert "2026-03-02 type=pomodoro task=work minutes=50" in content

    def test_log_skips_when_disabled(self):
        _clean_cache()
        _set_config(False)
        result = svc.pomodoro_log("work", 25)
        assert result["ok"] is False
        assert "log_sessions" in result.get("skipped", "")

    def test_log_skips_when_type_missing(self):
        _clean_cache()
        _without_type("pomodoro")
        result = svc.pomodoro_log("work", 25)
        assert result["ok"] is False
        assert "pomodoro" in result.get("skipped", "")

    def test_log_bad_minutes_raises(self):
        _clean_cache()
        with pytest.raises(svc.PTOSError):
            svc.pomodoro_log("work", "abc")

    def test_log_minutes_zero_raises(self):
        _clean_cache()
        with pytest.raises(svc.PTOSError):
            svc.pomodoro_log("work", 0)

    def test_log_empty_task_raises(self):
        _clean_cache()
        with pytest.raises(svc.PTOSError):
            svc.pomodoro_log("   ", 25)

    def test_log_invalidates_habit_cache(self):
        _clean_cache()
        svc.get_habit_data("pomodoro")
        assert any(k.startswith("habit:") for k in ptos._CACHE)
        svc.pomodoro_log("work", 1)
        assert not any(k.startswith("habit:") for k in ptos._CACHE)


class TestPomodoroLogCli:
    def test_run_pomodoro_log_prints_line(self, capsys):
        _clean_cache()
        ptos_cli.run_pomodoro_log("CLI session", 30)
        out = capsys.readouterr().out
        assert "Logged:" in out
        assert "type=pomodoro" in out

    def test_run_pomodoro_log_disabled_skips(self, capsys):
        _clean_cache()
        _set_config(False)
        ptos_cli.run_pomodoro_log("CLI session", 30)
        out = capsys.readouterr().out
        assert "Skipped:" in out

    def test_run_pomodoro_log_bad_minutes_exits(self):
        _clean_cache()
        with pytest.raises(SystemExit):
            ptos_cli.run_pomodoro_log("CLI session", "x")


class TestPomodoroLogWeb:
    def test_api_pomo_log_ok(self):
        _clean_cache()
        from ptos_web import app
        client = app.test_client()
        resp = client.post("/api/pomo-log", json={"task": "web session", "minutes": 25})
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["ok"] is True
        assert "type=pomodoro" in data["line"]
        assert "minutes=25" in data["line"]

    def test_api_pomo_log_missing_task_error(self):
        _clean_cache()
        from ptos_web import app
        client = app.test_client()
        resp = client.post("/api/pomo-log", json={"task": "", "minutes": 25})
        data = resp.get_json()
        assert data["ok"] is False

    def test_api_pomo_log_missing_minutes_error(self):
        _clean_cache()
        from ptos_web import app
        client = app.test_client()
        resp = client.post("/api/pomo-log", json={"task": "work"})
        data = resp.get_json()
        assert data["ok"] is False