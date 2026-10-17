"""Static-analysis gates run as part of the suite (pre-modularization spec A3):
every root module must compile, stay pyflakes-clean on the error classes that
break a code move (undefined names, redefinitions, unused imports), and not
grow its lower-severity warning count (unused locals, placeholder-less
f-strings)."""
import ast
import os
import subprocess
import sys

from pyflakes.checker import Checker

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

ROOT_FILES = sorted(
    os.path.join(REPO, n) for n in os.listdir(REPO) if n.endswith(".py"))
_SCRIPTS = os.path.join(REPO, "scripts")
SCRIPT_FILES = (
    sorted(os.path.join(_SCRIPTS, n) for n in os.listdir(_SCRIPTS)
           if n.endswith(".py"))
    if os.path.isdir(_SCRIPTS) else [])
ALL_FILES = ROOT_FILES + SCRIPT_FILES

# pyflakes message classes that fail outright — exactly what a broken
# function move produces.
STRICT = {"UndefinedName", "RedefinedWhileUnused", "UnusedImport"}

# Lower-severity classes allowed only at-or-below the per-file baseline
# (ratchet: the count may fall, never rise; lowering it is a one-line edit
# here).
RATCHET = {"UnusedVariable", "FStringMissingPlaceholders"}
_BASELINE = {
    "ptos.py": {"UnusedVariable": 1, "FStringMissingPlaceholders": 8},
    "ptos_service.py": {"UnusedVariable": 10},
    "ptos_web.py": {"UnusedVariable": 8, "FStringMissingPlaceholders": 1},
    "ptos_cli.py": {"UnusedVariable": 3, "FStringMissingPlaceholders": 6},
    "ptos_todo.py": {},
    "desktop_app.py": {},
    "notify_todo.py": {},
}


def _messages(path):
    with open(path, encoding="utf-8") as f:
        source = f.read()
    tree = ast.parse(source, filename=path)
    return list(Checker(tree, path).messages)


def _counts(path):
    counts = {}
    for msg in _messages(path):
        name = type(msg).__name__
        if name in RATCHET:
            counts[name] = counts.get(name, 0) + 1
    return counts


class TestCompileGate:
    def test_every_module_compiles(self):
        r = subprocess.run(
            [sys.executable, "-m", "compileall", "-q", *ALL_FILES],
            capture_output=True, text=True, timeout=120)
        assert r.returncode == 0, r.stdout + r.stderr


class TestPyflakesGate:
    def test_scanned_every_expected_file(self):
        names = {os.path.basename(p) for p in ALL_FILES}
        assert {"ptos.py", "ptos_service.py", "ptos_web.py", "ptos_cli.py",
                "ptos_todo.py", "desktop_app.py", "notify_todo.py"} <= names

    def test_no_strict_findings(self):
        bad = []
        for path in ALL_FILES:
            for msg in _messages(path):
                if type(msg).__name__ in STRICT:
                    bad.append(str(msg))
        assert not bad, "\n".join(bad)

    def test_ratchet_counts_do_not_rise(self):
        over = []
        for path in ALL_FILES:
            name = os.path.basename(path)
            allowed = _BASELINE.get(name, {})
            for kind, n in sorted(_counts(path).items()):
                limit = allowed.get(kind, 0)
                if n > limit:
                    over.append(f"{name}: {kind} {n} > baseline {limit}")
        assert not over, "\n".join(over)
