"""The CI workflow must exist, stay in sync with the pre-commit hook and the
requirements files, and actually cover the platforms PTOS ships launchers for."""
import ast
import os
import re
import subprocess
import sys

import pytest
import yaml

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORKFLOW = os.path.join(REPO, ".github", "workflows", "tests.yml")
HOOK = os.path.join(REPO, "scripts", "pre-commit")
TESTS = os.path.join(REPO, "tests")
SCRIPTS = os.path.join(REPO, "scripts")
REQ = os.path.join(REPO, "requirements.txt")
REQ_DEV = os.path.join(REPO, "requirements-dev.txt")
README = os.path.join(REPO, "README.md")

# Import name -> distribution name, where they differ.
_PACKAGE_OF = {"tomli_w": "tomli-w", "yaml": "pyyaml"}

# Imports deliberately absent from requirements files:
# - pystray/PIL: desktop_app.py's tray icon degrades gracefully without them
#   (logged, tray disabled)
# - tomli: only reached on Python < 3.11 (the `except ImportError` fallback
#   after `import tomllib`); the supported floor is 3.11, which ships tomllib
_OPTIONAL = {"pystray", "PIL", "tomli", "webview"}

_STDLIB = set(sys.stdlib_module_names) | {
    "ptos", "ptos_cli", "ptos_service", "ptos_todo", "ptos_web", "desktop_app"}

_LOCAL = {name[:-3] for name in os.listdir(REPO) if name.endswith(".py")}


def _py_files(*dirs):
    for d in dirs:
        if not os.path.isdir(d):
            continue
        for name in sorted(os.listdir(d)):
            if name.endswith(".py"):
                yield os.path.join(d, name)


def _imports_in(files):
    """Non-stdlib, non-local module roots imported by the given files.

    Parsed with ast so docstring lines like "from the files list" can never
    be mistaken for an import statement.
    """
    found = set()
    for path in files:
        try:
            tree = ast.parse(open(path, encoding="utf-8").read())
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    found.add(alias.name.split(".")[0])
            elif isinstance(node, ast.ImportFrom):
                if node.module and node.level == 0:
                    found.add(node.module.split(".")[0])
    return (found - _STDLIB) - _LOCAL


def _product_imports():
    return _imports_in(_py_files(REPO, SCRIPTS))


def _suite_imports():
    return _imports_in(_py_files(TESTS))


def _req_dists(path):
    """Distribution names declared in a requirements file (ignores -r lines)."""
    d = set()
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or line.startswith("-"):
                continue
            name = re.split(r"[<>=!\[; ]", line)[0].strip().lower()
            if name:
                d.add(name)
    return d


def _dist_of(mod):
    return _PACKAGE_OF.get(mod, mod).lower()


pytestmark = pytest.mark.skipif(
    not os.path.exists(WORKFLOW), reason="no CI workflow configured")


@pytest.fixture(scope="module")
def wf():
    with open(WORKFLOW, encoding="utf-8") as f:
        return yaml.safe_load(f)


def _run_lines(wf):
    out = []
    for job in wf["jobs"].values():
        for step in job.get("steps", []):
            if "run" in step:
                out.append(step["run"])
    return out


def _within(child, parent):
    """True when `child` is inside `parent` (different drives: never)."""
    try:
        return os.path.commonpath([child, parent]) == parent
    except ValueError:
        return False


class TestSuiteDoesNotDirtyTheCheckout:
    """Backup output must land outside the repo, or CI leaves a dirty tree."""

    def test_backup_dir_is_outside_the_repo(self):
        import ptos
        repo = os.path.normcase(os.path.abspath(REPO))
        backup = os.path.normcase(os.path.abspath(ptos.BACKUP_DIR))
        assert not _within(backup, repo), backup

    def test_data_dir_is_outside_the_repo(self):
        import ptos
        repo = os.path.normcase(os.path.abspath(REPO))
        base = os.path.normcase(os.path.abspath(ptos.BASE_DIR))
        assert not _within(base, repo), base


class TestWorkflowShape:
    def test_parses_and_declares_a_test_job(self, wf):
        assert "pytest" in wf["jobs"]

    def test_runs_the_same_command_as_the_pre_commit_hook(self, wf):
        hook = open(HOOK, encoding="utf-8").read()
        expected = re.search(r"python -m pytest[^\s|;&]*", hook).group(0)
        assert any(expected in r for r in _run_lines(wf)), expected

    def test_covers_both_shipped_platforms(self, wf):
        matrix = wf["jobs"]["pytest"]["strategy"]["matrix"]
        assert "ubuntu-latest" in matrix["os"]
        assert "windows-latest" in matrix["os"]

    def test_covers_supported_pythons(self, wf):
        # AGENTS.md states Python 3.11+, and tomllib (used for all config
        # parsing) is stdlib from 3.11.
        versions = [str(v) for v in wf["jobs"]["pytest"]["strategy"]["matrix"]["python-version"]]
        assert "3.11" in versions
        assert any(v.startswith("3.1") and int(v.split(".")[1]) > 11 for v in versions)

    def test_installs_from_the_requirements_file(self, wf):
        """CI must install from requirements-dev.txt, not an inline package list."""
        assert any("requirements-dev.txt" in r for r in _run_lines(wf))

    def test_covers_every_third_party_import(self, wf):
        """Product imports need requirements.txt; suite imports need the dev
        file. Derived from the actual imports, so a new dependency fails here
        instead of as an ImportError mid-job."""
        declared = " ".join(_run_lines(wf)).lower()
        assert "requirements-dev.txt" in declared
        runtime = _req_dists(REQ)
        dev = _req_dists(REQ_DEV)
        needed = (_product_imports() | _suite_imports()) - _OPTIONAL
        assert needed, "scan found no third-party imports; the scan is broken"
        for mod in sorted(needed):
            assert _dist_of(mod) in runtime | dev, mod

    def test_one_failure_does_not_hide_the_rest(self, wf):
        assert wf["jobs"]["pytest"]["strategy"]["fail-fast"] is False

    def test_no_linter_step_silently_breaking_the_build(self, wf):
        for run in _run_lines(wf):
            assert "ruff" not in run and "flake8" not in run and "black" not in run
            assert "shellcheck" not in run

    def test_read_only_permissions(self, wf):
        assert wf.get("permissions") == {"contents": "read"}

    def test_uses_immutable_action_pins(self, wf):
        for job in wf["jobs"].values():
            for step in job.get("steps", []):
                uses = step.get("uses", "")
                if uses.startswith("actions/"):
                    assert re.search(r"@v\d+$", uses), uses


class TestRequirementsFiles:
    """requirements.txt is the single source of truth for dependencies."""

    def test_both_files_exist(self):
        assert os.path.exists(REQ), "requirements.txt missing"
        assert os.path.exists(REQ_DEV), "requirements-dev.txt missing"

    def test_dev_file_includes_runtime(self):
        text = open(REQ_DEV, encoding="utf-8").read()
        assert "-r requirements.txt" in text

    def test_every_product_import_is_in_runtime(self):
        runtime = _req_dists(REQ)
        product = _product_imports() - _OPTIONAL
        assert product, "scan found no product imports; the scan is broken"
        for mod in sorted(product):
            assert _dist_of(mod) in runtime, mod

    def test_every_suite_import_is_declared(self):
        runtime = _req_dists(REQ)
        dev = _req_dists(REQ_DEV)
        for mod in sorted(_suite_imports() - _OPTIONAL):
            assert _dist_of(mod) in runtime | dev, mod

    def test_no_unused_runtime_pin(self):
        used = {_dist_of(m) for m in _product_imports()}
        for dist in sorted(_req_dists(REQ)):
            assert dist in used, dist

    def test_no_unused_dev_pin(self):
        used = {_dist_of(m) for m in _product_imports() | _suite_imports()}
        for dist in sorted(_req_dists(REQ_DEV)):
            assert dist in used, dist

    def test_tomli_fallbacks_stay_guarded(self):
        """tomli (the pre-3.11 backport) must only be imported as the
        except-ImportError fallback after `import tomllib`, so it is never
        needed on the supported floor."""
        for rel in ("ptos.py", "ptos_service.py", "ptos_cli.py"):
            path = os.path.join(REPO, rel)
            if not os.path.exists(path):
                continue
            lines = open(path, encoding="utf-8").readlines()
            for i, line in enumerate(lines):
                if re.match(r"\s*import tomli\b", line):
                    prev = lines[i - 1] if i else ""
                    assert "except ImportError" in prev, f"{rel}:{i + 1}"

    def test_readme_install_uses_the_file(self):
        text = open(README, encoding="utf-8").read()
        assert "-r requirements.txt" in text

    def test_readme_requires_python_311(self):
        text = open(README, encoding="utf-8").read()
        assert "Python 3.11+" in text


_BLOCK_TOMLI_W = """\
import sys


class _Block:
    def find_spec(self, name, path=None, target=None):
        if name == "tomli_w":
            raise ImportError("blocked for test")
        return None


sys.meta_path.insert(0, _Block())
import runpy

sys.argv = ["ptos_cli.py"] + sys.argv[1:]
runpy.run_path({cli!r}, run_name="__main__")
"""


class TestTomliWMissing:
    """No command may print a raw traceback when tomli-w is absent."""

    def _run(self, tmp_path, *args):
        cli = os.path.join(REPO, "ptos_cli.py")
        blocker = tmp_path / "block_tomli_w.py"
        blocker.write_text(_BLOCK_TOMLI_W.format(cli=cli), encoding="utf-8")
        env = dict(os.environ, PTOS_HOME=str(tmp_path))
        return subprocess.run(
            [sys.executable, str(blocker), *args],
            capture_output=True, text=True, env=env, cwd=REPO, timeout=60)

    def test_set_name_without_tomli_w(self, tmp_path):
        r = self._run(tmp_path, "--set-name", "Ada")
        out = r.stdout + r.stderr
        assert r.returncode != 0
        assert "tomli-w not installed" in out
        assert "Traceback" not in out

    def test_set_config_without_tomli_w(self, tmp_path):
        r = self._run(tmp_path, "--set-config", "user.name", "Ada")
        out = r.stdout + r.stderr
        assert r.returncode != 0
        assert "tomli-w not installed" in out
        assert "Traceback" not in out