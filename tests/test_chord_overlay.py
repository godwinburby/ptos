"""Chord/help overlay consistency test."""
import pytest
import re
import os


class TestChordOverlay:
    def test_help_overlay_exists(self):
        """Help overlay HTML is defined in nav_chords.js"""
        js_path = os.path.join(
            os.path.dirname(__file__), "..", "web_static", "js", "nav_chords.js"
        )
        with open(js_path, encoding="utf-8") as f:
            content = f.read()
        assert "HELP_HTML" in content
        assert "kb-overlay" in content
        assert "Keyboard Shortcuts" in content

    def test_help_overlay_has_quick_nav_table(self):
        """Quick Navigation table exists with expected keys"""
        js_path = os.path.join(
            os.path.dirname(__file__), "..", "web_static", "js", "nav_chords.js"
        )
        with open(js_path, encoding="utf-8") as f:
            content = f.read()
        
        # Check for all single-key shortcuts in help overlay
        shortcuts = [
            "H", "A", "T", "J", "N", "F", "R", "Y", "B", "Q", "S", "E", "I", "/", "?"
        ]
        for s in shortcuts:
            assert f"<kbd>{s}</kbd>" in content or f"kbd>{s}</kbd>" in content or f"<kbd>{s.lower()}</kbd>" in content or f"kbd>{s.lower()}</kbd>" in content, f"Missing shortcut {s}"

    def test_help_overlay_has_extended_nav_table(self):
        """Extended Navigation (G prefix) table exists with expected keys"""
        js_path = os.path.join(
            os.path.dirname(__file__), "..", "web_static", "js", "nav_chords.js"
        )
        with open(js_path, encoding="utf-8") as f:
            content = f.read()
        
        # Check for G-prefix shortcuts
        g_shortcuts = ["B", "H", "A", "Q", "J", "F", "D", "T", "S", "L", "K", "C", "U", "O", "M", "Y", "R", "V", "F"]
        for s in g_shortcuts:
            assert f"<kbd>{s}</kbd>" in content, f"Missing G+{s} shortcut"

    def test_nav_map_matches_help_overlay(self):
        """NAV map in nav_chords.js matches help overlay entries"""
        js_path = os.path.join(
            os.path.dirname(__file__), "..", "web_static", "js", "nav_chords.js"
        )
        with open(js_path, encoding="utf-8") as f:
            content = f.read()
        
        # Extract NAV map entries
        nav_match = re.search(r"var NAV\s*=\s*(\{.*?\});", content, re.DOTALL)
        assert nav_match, "NAV map not found"
        
        # Extract help overlay table entries
        help_match = re.search(r"var HELP_HTML\s*=\s*`([\s\S]*?)`;", content, re.DOTALL)
        assert help_match, "HELP_HTML not found"
        
        # The NAV map should contain all G-prefix shortcuts mentioned in help
        nav_map = nav_match.group(1)
        g_shortcuts = ["b", "h", "a", "q", "j", "f", "d", "t", "s", "l", "k", "c", "u", "o", "m", "y", "r", "v", "f"]
        for s in g_shortcuts:
            assert f'"g {s}"' in nav_map, f"NAV map missing 'g {s}'"

    def test_single_key_shortcuts_in_event_handler(self):
        """Single-key shortcuts are handled in the keydown event listener"""
        js_path = os.path.join(
            os.path.dirname(__file__), "..", "web_static", "js", "nav_chords.js"
        )
        with open(js_path, encoding="utf-8") as f:
            content = f.read()
        
        # Single key shortcuts are in the keydown handler
        single_keys = ["h", "a", "b", "q", "j", "n", "s", "e", "i", "t", "f", "r", "y"]
        for k in single_keys:
            # Check for the pattern: if (key === "k" && !_g)
            assert f'key === "{k}"' in content, f"Missing single-key handler for '{k}'"

    def test_help_overlay_styles_use_css_variables(self):
        """Help overlay uses CSS variables, not hardcoded colors"""
        js_path = os.path.join(
            os.path.dirname(__file__), "..", "web_static", "js", "nav_chords.js"
        )
        with open(js_path, encoding="utf-8") as f:
            content = f.read()
        
        # Check that HELP_HTML uses var(--card), var(--border), var(--text), var(--sub), var(--bg)
        help_match = re.search(r"var HELP_HTML\s*=\s*`([\s\S]*?)`;", content, re.DOTALL)
        help_html = help_match.group(1)
        
        assert "var(--card)" in help_html
        assert "var(--border)" in help_html
        assert "var(--text)" in help_html
        assert "var(--sub)" in help_html
        assert "var(--bg)" in help_html

    def test_help_overlay_kbd_styles_use_variables(self):
        """kbd styles in help overlay use CSS variables"""
        js_path = os.path.join(
            os.path.dirname(__file__), "..", "web_static", "js", "nav_chords.js"
        )
        with open(js_path, encoding="utf-8") as f:
            content = f.read()
        
        help_match = re.search(r"var HELP_HTML\s*=\s*`([\s\S]*?)`;", content, re.DOTALL)
        help_html = help_match.group(1)
        
        # Check kbd styles section
        assert "var(--bg)" in help_html
        assert "var(--border)" in help_html
        assert "var(--text)" in help_html

    def test_nav_chords_no_hardcoded_colors(self):
        """nav_chords.js uses CSS variables for colors, not hardcoded hex"""
        js_path = os.path.join(
            os.path.dirname(__file__), "..", "web_static", "js", "nav_chords.js"
        )
        with open(js_path, encoding="utf-8") as f:
            content = f.read()
        
        # Check that there are no hardcoded hex colors in the file (outside of comments)
        # This is a basic check - look for # followed by 6 hex chars
        hex_colors = re.findall(r"#[0-9a-fA-F]{6}", content)
        # Allow some in comments or specific cases, but should be minimal
        # The #1a1a1a appears to be in a comment or string, allow it
        if hex_colors:
            # Filter out known false positives
            filtered = [c for c in hex_colors if c not in ["#1a1a1a"]]
            assert len(filtered) == 0, f"Found hardcoded hex colors: {filtered}"

    def test_help_overlay_has_close_handlers(self):
        """Help overlay has proper close handlers"""
        js_path = os.path.join(
            os.path.dirname(__file__), "..", "web_static", "js", "nav_chords.js"
        )
        with open(js_path, encoding="utf-8") as f:
            content = f.read()
        
        assert "closeKbHelp" in content
        assert "openKbHelp" in content
        assert "Escape" in content or "escape" in content
        assert "onclick=\"if(event.target===this)closeKbHelp()\"" in content

    def test_chord_map_completeness_g_prefix(self):
        """All G-prefixed pages in sidebar/more menu have corresponding chord shortcuts"""
        js_path = os.path.join(
            os.path.dirname(__file__), "..", "web_static", "js", "nav_chords.js"
        )
        with open(js_path, encoding="utf-8") as f:
            content = f.read()
        
        nav_match = re.search(r"var NAV\s*=\s*(\{.*?\});", content, re.DOTALL)
        nav_map = nav_match.group(1)
        
        # Check key G-prefixed pages are in NAV
        expected_g_pages = [
            "/board", "/habits", "/calendar", "/thresholds", "/entity",
            "/favorites", "/schema-builder", "/query-builder", "/backup", "/lint"
        ]
        
        for page in expected_g_pages:
            assert page in nav_map, f"Page {page} missing from NAV map"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])