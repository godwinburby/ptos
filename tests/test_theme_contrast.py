import re, pathlib

CSS = pathlib.Path(__file__).resolve().parents[1] / "web_static" / "css" / "base.css"
TEXT = CSS.read_text(encoding="utf-8")

def block_for(selector_pattern):
    # find the first {...} block whose header matches selector_pattern
    for m in re.finditer(r"(:root[^{]*|@media[^{]*)\{", TEXT):
        header = m.group(0)
        if not re.search(selector_pattern, header):
            continue
        # find matching closing brace
        depth = 0
        i = m.end() - 1
        while i < len(TEXT):
            if TEXT[i] == "{":
                depth += 1
            elif TEXT[i] == "}":
                depth -= 1
                if depth == 0:
                    return TEXT[m.end():i]
            i += 1
    return ""

LIGHT_BLOCK = block_for(r"^:root\s*\{")
DARK_BLOCK = block_for(r':root\[data-theme="dark"\]')


def parse_vars(block):
    out = {}
    for m in re.finditer(r"--([a-zA-Z0-9-]+)\s*:\s*([^;]+);", block):
        out["--" + m.group(1)] = m.group(2).strip()
    return out


LIGHT = parse_vars(LIGHT_BLOCK)
DARK = parse_vars(DARK_BLOCK)


def hex_to_rgb(h):
    h = h.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    if len(h) == 8:
        h = h[:6]
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return r, g, b


def luminance(h):
    r, g, b = hex_to_rgb(h)
    def chan(c):
        c = c / 255.0
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    return 0.2126 * chan(r) + 0.7152 * chan(g) + 0.0722 * chan(b)


def contrast(c1, c2):
    l1, l2 = luminance(c1), luminance(c2)
    hi, lo = max(l1, l2), min(l1, l2)
    return (hi + 0.05) / (lo + 0.05)


def resolve(varname, theme):
    # resolve a var() reference one level
    v = theme.get(varname, "")
    if v.startswith("var("):
        inner = v[4:].rstrip(")").strip()
        return theme.get(inner, v)
    return v


def test_light_contrast():
    pairs = [
        ("--text", "--card"), ("--text", "--bg"), ("--sub", "--card"),
        ("--sub", "--bg"), ("--success", "--card"), ("--error", "--card"),
        ("--warn-text", "--card"), ("--warn-text", "--warn-lt"),
    ]
    for a, b in pairs:
        ca, cb = resolve(a, LIGHT), resolve(b, LIGHT)
        assert contrast(ca, cb) >= 4.5, f"light {a}/{b}: {contrast(ca,cb):.2f}"


def test_dark_contrast():
    pairs = [
        ("--text", "--card"), ("--text", "--bg"), ("--sub", "--card"),
        ("--sub", "--bg"), ("--success", "--card"), ("--error", "--card"),
        ("--warn-text", "--card"), ("--warn-text", "--warn-lt"),
        ("--accent-d", "--accent-lt"),
    ]
    for a, b in pairs:
        ca, cb = resolve(a, DARK), resolve(b, DARK)
        assert contrast(ca, cb) >= 4.5, f"dark {a}/{b}: {contrast(ca,cb):.2f}"


def test_button_text_contrast():
    # light: white on --accent ; dark: --bg on --accent
    assert contrast("#FFFFFF", resolve("--accent", LIGHT)) >= 4.5
    assert contrast(resolve("--bg", DARK), resolve("--accent", DARK)) >= 4.5


def test_focus_fields_use_theme_background():
    m = re.search(r"input:focus[^{]*\{([^}]*)\}", TEXT)
    assert m, "focus rule not found"
    body = m.group(1)
    assert "white" not in body
    assert not re.search(r"background:\s*#[0-9A-Fa-f]{3,8}", body)
    assert "var(--" in body


def test_variable_parity():
    missing = set(LIGHT.keys()) - set(DARK.keys())
    assert not missing, f"missing in dark: {sorted(missing)}"


def test_accent_d_on_accent_lt():
    assert contrast(resolve("--accent-d", LIGHT), resolve("--accent-lt", LIGHT)) >= 4.5
