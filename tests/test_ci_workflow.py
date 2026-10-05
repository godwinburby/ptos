"""The CI workflow must exist, stay in sync with the pre-commit hook, and
actually cover the platforms PTOS ships launchers for."""
import os
import re

import pytest
import yaml

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORKFLOW = os.path.join(REPO, ".github", "workflows", "tests.yml")
HOOK = os.path.join(REPO, "scripts", "pre-commit")
TESTS = os.path.join(REPO, "tests")

# Import name -> distribution name, where they differ.
_PACKAGE_OF = {"tomli_w": "tomli-w", "yaml": "pyyaml"}


def _third_party_imports():
    """Every non-stdlib, non-PTOS module imported anywhere in the suite."""
    import sys

    stdlib = set(sys.stdlib_module_names) | {"ptos", "ptos_cli", "ptos_service",
                                             "ptos_todo", "ptos_web"}
    local = {name[:-3] for name in os.listdir(REPO) if name.endswith(".py")}
    found = set()
    for name in os.listdir(TESTS):
        if not name.endswith(".py"):
            continue
        text = open(os.path.join(TESTS, name), encoding="utf-8").read()
        for m in re.finditer(r"^\s*(?:import|from)\s+([A-Za-z_][\w.]*)",
                             text, re.M):
            root = m.group(1).split(".")[0]
            if root not in stdlib and root not in local:
                found.add(root)
    return found

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

    def test_installs_every_third_party_import(self, wf):
        """A new dependency must be added to the workflow too.

        Derived from the suite's actual imports rather than hardcoded, so
        forgetting this fails here instead of as an ImportError mid-job.
        """
        declared = " ".join(_run_lines(wf)).lower()
        needed = _third_party_imports()
        assert needed, "scan found no third-party imports; the scan is broken"
        for mod in sorted(needed):
            assert _PACKAGE_OF.get(mod, mod).lower() in declared, mod

    def test_declares_nothing_the_suite_does_not_use(self, wf):
        """Also the other direction: no unused pins to keep current."""
        declared = " ".join(_run_lines(wf)).lower()
        used = {_PACKAGE_OF.get(m, m).lower() for m in _third_party_imports()}
        for pkg in ("flask", "tomli-w", "pytest", "pyyaml"):
            if pkg not in used:
                assert pkg not in declared, pkg

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