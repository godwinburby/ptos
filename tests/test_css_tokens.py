import json, os, re, pathlib

CSS_DIR = pathlib.Path(__file__).resolve().parents[1] / "web_static" / "css"
BASELINE = pathlib.Path(__file__).resolve().parent / "css_token_baseline.json"

HEX_RE = re.compile(r"#[0-9a-fA-F]{3,8}\b")
RADIUS_RE = re.compile(r"border-radius\s*:\s*([^;]+);", re.I)
SHADOW_RE = re.compile(r"box-shadow\s*:\s*([^;]+);", re.I)
FONTSIZE_RE = re.compile(r"font-size\s*:\s*([^;]+);", re.I)

ROOT_BLOCK_RE = re.compile(r":root(?:\[[^\]]*\])?(?::not\([^)]*\))?\s*\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}", re.S)


def strip_comments(css):
    return re.sub(r"/\*.*?\*/", "", css, flags=re.S)


def strip_root_blocks(css):
    # remove :root and :root[...] blocks (balanced, one level deep is enough for tokens)
    return ROOT_BLOCK_RE.sub("", css)


def is_allowed_radius(val):
    v = val.strip()
    if v in ("0", "50%", "999px"):
        return True
    if v.startswith("var(--radius-"):
        return True
    parts = v.split()
    if len(parts) > 1:
        return all(p == "0" or p.startswith("var(--radius-") for p in parts)
    return False


def is_allowed_shadow(val):
    v = val.strip()
    if v == "none":
        return True
    if v.startswith("var(--shadow-"):
        return True
    if v.startswith("inset 3px 0 0 var(--"):
        return True
    if v.startswith("0 0 0 2px var(--focus-ring-color") or v.startswith("0 0 0 2px var(--accent"):
        return True
    return False


def is_allowed_fontsize(val):
    v = val.strip()
    if "var(--fs-" in v:
        return True
    return False


def count_file(path):
    raw = path.read_text(encoding="utf-8")
    css = strip_comments(raw)
    css = strip_root_blocks(css)
    hex_count = len(HEX_RE.findall(css))
    radius_count = sum(1 for m in RADIUS_RE.finditer(css) if not is_allowed_radius(m.group(1)))
    shadow_count = sum(1 for m in SHADOW_RE.finditer(css) if not is_allowed_shadow(m.group(1)))
    fontsize_count = 0
    for m in FONTSIZE_RE.finditer(css):
        val = m.group(1).strip()
        if "px" in val and not is_allowed_fontsize(val):
            fontsize_count += 1
    return {
        "hex": hex_count,
        "radius": radius_count,
        "shadow": shadow_count,
        "fontsize": fontsize_count,
    }


def total_counts():
    totals = {"hex": 0, "radius": 0, "shadow": 0, "fontsize": 0}
    for f in sorted(CSS_DIR.glob("*.css")):
        c = count_file(f)
        for k in totals:
            totals[k] += c[k]
    return totals


def test_ratchet():
    actual = total_counts()
    if not BASELINE.exists():
        BASELINE.write_text(json.dumps(actual, indent=2) + "\n")
        return
    baseline = json.loads(BASELINE.read_text())
    # fail if any count increased
    over = []
    for k in actual:
        if actual[k] > baseline.get(k, 0):
            over.append(f"{k}: {actual[k]} > baseline {baseline.get(k,0)}")
    assert not over, "counts rose:\\n" + "\\n".join(over)
    # fail if decreased but baseline not updated
    under = []
    for k in actual:
        if actual[k] < baseline.get(k, 0):
            under.append(f"{k}: {actual[k]} < baseline {baseline.get(k,0)}")
    assert not under, "counts fell but baseline not updated:\\n" + "\\n".join(under)
