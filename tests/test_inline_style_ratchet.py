"""Inline style ratchet for templates and JS.

Counts `style="..."` occurrences per file. Counts may only go down.
Baseline stored in tests/inline_style_baseline.json.
"""

import json
import os
import pathlib

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
TEMPLATE_DIR = pathlib.Path('web_templates')
JS_DIR = pathlib.Path('web_static/js')
BASELINE_FILE = pathlib.Path(__file__).resolve().parents[1] / "tests" / "inline_style_baseline.json"


def scan_all():
    """Scan all template and JS files, return dict of counts."""
    counts = {}
    repo_root = pathlib.Path.cwd()
    for f in sorted(pathlib.Path('web_templates').rglob('*.html')):
        text = f.read_text(encoding='utf-8')
        counts[os.path.relpath(f, pathlib.Path.cwd())] = text.count('style="')
    for f in sorted(pathlib.Path('web_static/js').rglob('*.js')):
        text = f.read_text(encoding='utf-8')
        counts[os.path.relpath(f, pathlib.Path.cwd())] = text.count('style="')
    return counts


def load_baseline():
    if BASELINE_FILE.exists():
        return json.loads(BASELINE_FILE.read_text(encoding='utf-8'))
    return {}


def save_baseline(data):
    BASELINE_FILE.write_text(json.dumps(data, indent=2, sort_keys=True) + '\n', encoding='utf-8')


def test_inline_style_ratchet():
    counts = scan_all()
    baseline = load_baseline()

    if not baseline:
        # First run: establish baseline
        save_baseline(counts)
        print("Baseline established:", json.dumps(counts, indent=2))
        import pytest
        pytest.fail("Baseline created at tests/inline_style_baseline.json; re-run test to verify")

    # Compare with baseline
    errors = []
    for fname, count in sorted(counts.items()):
        base = baseline.get(fname, 0)
        if count > base:
            errors.append(f"{fname}: count {count} > baseline {base} (style regression)")
        elif count < base:
            errors.append(f"{fname}: count {count} < baseline {base} (baseline must be updated)")

    if errors:
        print("\n".join(errors))
        import pytest
        pytest.fail("Inline style ratchet failed:\n" + "\n".join(errors))


if __name__ == "__main__":
    test_inline_style_ratchet()