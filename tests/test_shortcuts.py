"""Tests for keyboard shortcuts single source of truth.

Ensures nav_sections is the canonical source and JS map is derived from it.
"""
import re
import json


def test_nav_sections_shortcuts_format(_isolated_ptos_paths):
    """Every shortcut in nav_sections matches ^[A-Z]$ or ^G [A-Z]$."""
    from ptos_web import app
    app.config["TESTING"] = True
    with app.test_client() as client:
        resp = client.get("/todo")
        html = resp.get_data(as_text=True)

    # Extract nav_sections from page_state
    match = re.search(r"window\.PTOS_PAGE = (\{.*\});", html)
    assert match, "PTOS_PAGE not found"
    page_state = json.loads(match.group(1))

    nav_sections = page_state.get("nav_sections", [])
    for sec_id, sec_name, items in nav_sections:
        for url_path, tab_name, icon_name, label, shortcut in items:
            if shortcut:
                # Must be single uppercase letter or "G X"
                assert re.match(r"^[A-Z]$", shortcut) or re.match(r"^G [A-Z]$", shortcut), \
                    f"Invalid shortcut format: {shortcut!r} for {label}"


def test_nav_sections_no_duplicate_shortcuts(_isolated_ptos_paths):
    """No shortcut appears twice in nav_sections."""
    from ptos_web import app
    app.config["TESTING"] = True
    with app.test_client() as client:
        resp = client.get("/todo")
        html = resp.get_data(as_text=True)

    match = re.search(r"window\.PTOS_PAGE = (\{.*\});", html)
    assert match
    page_state = json.loads(match.group(1))

    nav_sections = page_state.get("nav_sections", [])
    seen = {}
    for sec_id, sec_name, items in nav_sections:
        for url_path, tab_name, icon_name, label, shortcut in items:
            if shortcut:
                if shortcut in seen:
                    raise AssertionError(f"Duplicate shortcut {shortcut!r}: {seen[shortcut]} and {label}")
                seen[shortcut] = label


def _extract_json_object(text, start_idx):
    """Extract a JSON object from text starting at start_idx (where text[start_idx] == '{').
    Returns the extracted JSON string and the index after the closing brace."""
    depth = 0
    in_string = False
    escape = False
    for i in range(start_idx, len(text)):
        ch = text[i]
        if escape:
            escape = False
            continue
        if ch == '\\':
            escape = True
            continue
        if ch == '"' and not escape:
            in_string = not in_string
            continue
        if not in_string:
            if ch == '{':
                depth += 1
            elif ch == '}':
                depth -= 1
                if depth == 0:
                    return text[start_idx:i+1], i+1
    return None, None


# Expected nav_sections from ptos_web.py (single source of truth)
_EXPECTED_NAV_SECTIONS = [
    ("log", "Log", [
        ("",            "home",    "home",      "Home",        "H"),
        ("add",         "add",     "add",       "Add Record",  "A"),
        ("todo",        "todo",    "todo",      "Todos",       "T"),
        ("journal",     "journal", "journal",   "Journal",     "J"),
        ("notes",       "notes",   "notes",     "Pages",       "P"),
        ("types",       "types",   "types",     "Types",       "G Y"),
        ("routines",    "routines","routines",  "Routines",    "R"),
        ("favorites",   "favorites","favorites", "Favorites",   "G F"),
    ]),
    ("find", "Find", [
        ("search",      "search",  "search",    "Search",      "F"),
        ("due",         "due",     "due",       "Due List",    "D"),
        ("browse",      "browse",  "browse",    "Browse",      "B"),
        ("entity",      "entity",  "entity",    "Entity",      "G J"),
    ]),
    ("track", "Track", [
        ("queries",     "queries", "query",     "Queries",     "Q"),
        ("board",       "board",   "board",     "Board",       "G B"),
        ("habits",      "habits",  "habits",    "Habits",      "G H"),
        ("calendar",    "calendar","calendar",  "Calendar",    "G C"),
        ("thresholds",  "thresholds","thresholds","Thresholds","G T"),
        ("projects",    "projects","projects",  "Projects",    "G P"),
        ("areas",       "areas",   "areas",     "Areas",       "G V"),
    ]),
    ("setup", "Setup", [
        ("query-builder",  "query_builder",   "query_builder",   "Query Builder",  "G Q"),
        ("schema-builder", "schema_builder",  "schema_builder",  "Schema Builder", "G S"),
        ("editor",         "editor",          "editor",          "Log Editor",     "G L"),
        ("lint",           "lint",            "lint",            "Lint",           "G I"),
        ("backup",         "backup",          "backup",          "Backup",         "G U"),
        ("settings",       "settings",        "settings",        "Settings",       "S"),
    ]),
]

# Static non-nav keys added by _build_shortcut_map
_STATIC_KEYS = {
    "e": "/add?type=expense",
    "i": "/add?type=income",
    "/": "focus_search",
    "?": "show_help",
    "escape": "close_overlay",
}


def test_js_shortcut_map_derived_from_nav_sections(_isolated_ptos_paths):
    """The JS shortcut map (window.PTOS.keys) is built from nav_sections and has one entry per nav item with a shortcut."""
    from ptos_web import app
    app.config["TESTING"] = True
    with app.test_client() as client:
        resp = client.get("/todo")
        html = resp.get_data(as_text=True)

    # Extract shortcut_map from window.PTOS.keys (valid JSON via tojson filter)
    keys_idx = html.find('keys:{')
    assert keys_idx >= 0, "keys:{ not found in page"
    keys_json, _ = _extract_json_object(html, keys_idx + 5)  # skip "keys:"
    assert keys_json is not None, "Failed to extract keys JSON"
    ptos_keys = json.loads(keys_json)

    # Build expected keys from the canonical nav_sections definition + static keys
    expected_keys = {}
    for sec_id, sec_name, items in _EXPECTED_NAV_SECTIONS:
        for url_path, tab_name, icon_name, label, shortcut in items:
            if shortcut:
                norm = shortcut.lower().replace(" ", "")
                path = "/" + url_path if url_path else "/"
                expected_keys[norm] = path
    expected_keys.update(_STATIC_KEYS)

    assert len(ptos_keys) == len(expected_keys), \
        f"PTOS.keys has {len(ptos_keys)} entries, expected {len(expected_keys)}"

    for key, path in ptos_keys.items():
        assert key in expected_keys, f"Unexpected key in PTOS.keys: {key}"
        assert path == expected_keys[key], f"Path mismatch for {key}: got {path}, expected {expected_keys[key]}"


def test_nav_chords_js_no_hardcoded_nav():
    """nav_chords.js contains no hardcoded 'g x': '/path' entries."""
    content = open("web_static/js/nav_chords.js", encoding="utf-8").read()
    # Should not have NAV object with hardcoded paths
    # It should read from window.PTOS_KEYS instead
    assert "NAV = {" not in content, "nav_chords.js still has hardcoded NAV object"
    assert '"/board"' not in content or "PTOS_KEYS" in content, "Hardcoded paths in nav_chords.js"


def test_nav_chords_js_no_hardcoded_help_table():
    """nav_chords.js contains no hardcoded help table rows."""
    content = open("web_static/js/nav_chords.js", encoding="utf-8").read()
    # HELP_HTML should not exist as a big template string
    assert "HELP_HTML" not in content, "nav_chords.js still has hardcoded HELP_HTML"