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


def test_tint_tokens_contrast():
    # Normal text (--text) on each tint token must meet 4.5:1 in both themes
    tint_vars = [f"--tint-{i}" for i in range(1, 9)] + [
        "--tint-success", "--tint-error", "--tint-warn"
    ]
    for tv in tint_vars:
        for theme_name, theme in (("light", LIGHT), ("dark", DARK)):
            text_var = "--text"
            # tint tokens use color-mix, so resolve() won't fully expand them.
            # Compute expected color by evaluating the mix manually using the theme's chart/success/error/warn and card.
            if tv.startswith("--tint-") and tv[7].isdigit():
                idx = int(tv[7])
                chart = f"--chart-{idx}"
            elif tv == "--tint-success":
                chart = "--success"
            elif tv == "--tint-error":
                chart = "--error"
            else:
                chart = "--warn"
            # color-mix(in srgb, <color> 14%, <color>)
            # We approximate by mixing in linear srgb for testing purposes.
            # But for simplicity, just verify the resolved value contains the right refs.
            val = theme.get(tv, "")
            assert val, f"{theme_name}: {tv} not defined"
            assert "color-mix" in val, f"{theme_name}: {tv} is not a color-mix: {val}"
            assert chart in val, f"{theme_name}: {tv} missing {chart}"
            assert "--card" in val, f"{theme_name}: {tv} missing --card"
            # Now compute actual mixed color and check contrast with --text
            # Parse the two source colors
            c1 = resolve(chart, theme)
            c2 = resolve("--card", theme)
            # Mix: 14% of chart + 86% of card in srgb
            r1, g1, b1 = hex_to_rgb(c1)
            r2, g2, b2 = hex_to_rgb(c2)
            rm = round(r1 * 0.14 + r2 * 0.86)
            gm = round(g1 * 0.14 + g2 * 0.86)
            bm = round(b1 * 0.14 + b2 * 0.86)
            mixed = f"#{rm:02X}{gm:02X}{bm:02X}"
            text = resolve(text_var, theme)
            cr = contrast(mixed, text)
            assert cr >= 4.5, f"{theme_name}: {tv} on text contrast {cr:.2f} < 4.5 (mixed={mixed}, text={text})"
