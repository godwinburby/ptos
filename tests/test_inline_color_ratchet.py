"""Inline colour ratchet for templates and JS.

Counts per file: hex colours (#rgb, #rrggbb, #rrggbbaa), rgb/rgba with
literal numbers, and bare white/black used as color/background values.
Counts may only go down. Baseline stored in tests/inline_color_baseline.json.
"""

import json
import pathlib
import re

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
TEMPLATE_DIR = REPO_ROOT / "web_templates"
JS_DIR = REPO_ROOT / "web_static" / "js"
BASELINE_FILE = REPO_ROOT / "tests" / "inline_color_baseline.json"

HEX_RE = re.compile(r"#[0-9a-fA-F]{3,8}\b")
RGB_RE = re.compile(r"rgba?\([^)]*\b\d+\b[^)]*\)")
WHITE_BLACK_RE = re.compile(r"\b(white|black)\b")

ALLOW_LINE_RE = re.compile(r"/\*\s*allow-color:\s*.*?\*/")
SCRIM_RE = re.compile(r"rgba?\(\s*(0|255)\s*,\s*(0|255)\s*,\s*(0|255)\s*(?:,\s*[\d.]+)?\s*\)")
META_THEME_COLOR_RE = re.compile(r'<meta\s+name="theme-color"')
DATA_URI_RE = re.compile(r"data:[^\"']*")


def count_inline_colours(text: str, fname: str) -> int:
    """Count disallowed inline colour occurrences in text."""
    count = 0
    lines = text.splitlines()
    for i, line in enumerate(lines):
        # Skip lines with allow-color comment
        if ALLOW_LINE_RE.search(line):
            continue
        # Skip meta theme-color lines
        if META_THEME_COLOR_RE.search(line):
            continue
        # Remove data: URIs from the line for counting
        clean_line = DATA_URI_RE.sub("", line)

        # Hex colours
        for m in HEX_RE.finditer(clean_line):
            # Skip if part of a data URI (already removed) or CSS variable
            start = m.start()
            if start > 0 and clean_line[start - 1] == "(":
                # Could be var(--chart-1) etc - but hex won't be in var()
                pass
            count += 1

        # rgb/rgba with literal numbers
        for m in RGB_RE.finditer(clean_line):
            val = m.group(0)
            # Allow scrims: rgba(0,0,0,...) or rgba(255,255,255,...)
            if SCRIM_RE.fullmatch(val.replace(" ", "")):
                continue
            count += 1

        # Bare white/black as color/background value
        # Heuristic: white/black preceded by color: or background: or background-color:
        # and not inside a comment or string (approximate)
        for m in WHITE_BLACK_RE.finditer(clean_line):
            start = m.start()
            # Look back for color: or background:
            preceding = clean_line[:start]
            if re.search(r"(?:^|[;\s{])(?:color|background(?:-color)?)\s*:\s*$", preceding):
                count += 1
            elif re.search(r"(?:^|[;\s{])(?:color|background(?:-color)?)\s*:\s*[^;]*$", preceding):
                # The value might continue after white/black
                if re.search(r"(?:^|[;\s{])(?:color|background(?:-color)?)\s*:\s*[^;]*\b(white|black)\b", clean_line):
                    count += 1

    return count


def scan_all():
    """Scan all template and JS files, return dict of counts."""
    counts = {}
    for f in sorted(TEMPLATE_DIR.rglob("*.html")):
        rel = f.relative_to(REPO_ROOT)
        text = f.read_text(encoding="utf-8")
        counts[rel.as_posix()] = count_inline_colours(text, str(f))
    for f in sorted(JS_DIR.rglob("*.js")):
        rel = f.relative_to(REPO_ROOT)
        text = f.read_text(encoding="utf-8")
        counts[rel.as_posix()] = count_inline_colours(text, str(f))
    return counts


def load_baseline():
    if BASELINE_FILE.exists():
        return json.loads(BASELINE_FILE.read_text(encoding="utf-8"))
    return {}


def save_baseline(data):
    BASELINE_FILE.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def test_inline_colour_ratchet():
    baseline = load_baseline()
    counts = scan_all()

    if not baseline:
        # First run: establish baseline
        save_baseline(counts)
        print("Baseline established:", json.dumps(counts, indent=2))
        # Fail so the test signals baseline creation; user re-runs
        import pytest
        pytest.fail("Baseline created at tests/inline_color_baseline.json; re-run test to verify")

    # Compare with baseline
    errors = []
    for fname, count in sorted(counts.items()):
        base = baseline.get(fname, 0)
        if count > base:
            errors.append(f"{fname}: count {count} > baseline {base} (colour regression)")
        elif count < base:
            errors.append(f"{fname}: count {count} < baseline {base} (baseline must be updated)")

    if errors:
        print("\n".join(errors))
        import pytest
        pytest.fail("Inline colour ratchet failed:\n" + "\n".join(errors))


if __name__ == "__main__":
    test_inline_colour_ratchet()