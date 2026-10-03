"""The start scripts are shell, so there is no test runner for them — pin the
launcher behaviour that was fixed (see SPEC-ptos-hardening Phase 3) by
asserting on the script text, and syntax-check them with bash where available.
"""
import os
import shutil
import subprocess

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ANDROID = os.path.join(ROOT, "run_ptos_android.sh")
LINUX = os.path.join(ROOT, "run_ptos_linux.sh")

requires_bash = pytest.mark.skipif(shutil.which("bash") is None,
                                   reason="bash not available")


def _read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


class TestScriptSyntax:
    @requires_bash
    @pytest.mark.parametrize("script", [ANDROID, LINUX])
    def test_bash_n(self, script):
        result = subprocess.run(["bash", "-n", script], capture_output=True, text=True)
        assert result.returncode == 0, result.stderr


class TestAndroidLauncher:
    @pytest.fixture(autouse=True)
    def _text(self):
        self.text = _read(ANDROID)

    def test_update_check_is_bounded(self):
        assert "GIT_TERMINAL_PROMPT=0 timeout 8 git" in self.text
        assert "timeout 30 git pull" in self.text
        assert "command -v timeout" in self.text

    def test_missing_timeout_skips_update(self):
        assert "Skipping update check ('timeout' not available)" in self.text
        assert self.text.count("fetch --quiet origin main") == 1

    def test_update_check_is_throttled(self):
        assert "UPDATE_INTERVAL=21600" in self.text
        assert ".ptos_last_update" in self.text
        assert '"--update"' in self.text
        assert "Skipping update check (checked recently)" in self.text

    def test_no_hardcoded_port(self):
        assert "localhost:5000" not in self.text
        assert "http://localhost:5000" not in self.text

    def test_port_comes_from_config(self):
        assert "PTOS_PORT" in self.text
        assert "[server]" in self.text or "ptos.get_config" in self.text
        assert 'PTOS_URL="http://localhost:$PTOS_PORT"' in self.text

    def test_port_guards_against_garbage(self):
        assert "*[!0-9]*" in self.text

    def test_fast_poll(self):
        assert "sleep 0.25" in self.text

    def test_no_unconditional_startup_sleep(self):
        assert "\npkill -f \"python.*ptos_web.py\" 2>/dev/null || true\nsleep 1\n" \
            not in self.text

    def test_readiness_checks_process_liveness(self):
        assert self.text.count('kill -0 "$FLASK_PID"') >= 2

    def test_all_urls_use_variable(self):
        for line in self.text.splitlines():
            if "curl -s" in line or "am start" in line:
                assert "localhost:5000" not in line, line
                if "http" in line:
                    assert "$PTOS_URL" in line, line


class TestLinuxLauncher:
    @pytest.fixture(autouse=True)
    def _text(self):
        self.text = _read(LINUX)

    def test_update_check_is_bounded(self):
        assert "GIT_TERMINAL_PROMPT=0 timeout 8 git" in self.text
        assert "timeout 30 git pull" in self.text
        assert "command -v timeout" in self.text

    def test_missing_timeout_skips_update(self):
        assert "Skipping update check ('timeout' not available)" in self.text
        assert self.text.count("fetch --quiet origin main") == 1

    def test_update_check_is_throttled(self):
        assert "UPDATE_INTERVAL=21600" in self.text
        assert ".ptos_last_update" in self.text
        assert '"--update"' in self.text
        assert "Skipping update check (checked recently)" in self.text

    def test_no_hardcoded_port(self):
        assert "localhost:5000" not in self.text

    def test_port_comes_from_config(self):
        assert "PTOS_PORT" in self.text
        assert "ptos.get_config" in self.text
        assert 'PTOS_URL="http://localhost:$PTOS_PORT"' in self.text

    def test_port_guards_against_garbage(self):
        assert "*[!0-9]*" in self.text

    def test_fast_poll(self):
        assert "sleep 0.25" in self.text

    def test_no_unconditional_startup_sleep(self):
        assert '\n        kill "$PID" 2>/dev/null || kill -9 "$PID" ' \
            '2>/dev/null || true\n        sleep 1\n' not in self.text
        assert 'fuser -k "$PTOS_PORT"/tcp 2>/dev/null || true\n    sleep 1\n' \
            not in self.text

    def test_readiness_checks_process_liveness(self):
        assert self.text.count('kill -0 "$FLASK_PID"') >= 2

    def test_all_urls_use_variable(self):
        for line in self.text.splitlines():
            if "curl -s" in line or "xdg-open" in line:
                assert "localhost:5000" not in line, line
                if "http" in line:
                    assert "$PTOS_URL" in line, line
