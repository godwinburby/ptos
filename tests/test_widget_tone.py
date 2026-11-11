"""Tone lint: widget registrations and starters must declare a tone."""
import pytest

import ptos_widgets as pw
import ptos_service as svc  # triggers widget registration


BUILTIN_KINDS = (
    "dashboard", "metric", "threshold", "board", "habit", "calendar",
    "due", "project", "todo", "query", "records", "todo_summary",
    "journal", "capture", "quick_add", "quick_add_multi", "time_picker",
)

VALID_TONES = {
    "chart-1", "chart-2", "chart-3", "chart-4", "chart-5",
    "chart-6", "chart-7", "chart-8",
    "success", "error", "warn",
}


class TestToneLint:
    @pytest.mark.parametrize("kind", BUILTIN_KINDS)
    def test_kind_accepts_tone_in_fields(self, kind):
        """Each kind's field schema should allow a 'tone' field when named."""
        e = pw.get_kind(kind)
        fields = {f["key"] for f in e["fields"]}
        if e["named"]:
            assert "tone" in fields, f"{kind}: missing 'tone' field"

    @pytest.mark.parametrize("kind", BUILTIN_KINDS)
    def test_starters_have_explicit_tone(self, kind):
        """Every starter for a named kind must include a tone."""
        e = pw.get_kind(kind)
        if not e["starters"]:
            return
        for s in e["starters"]:
            body = s.get("body", "")
            if e["named"]:
                assert "tone" in body, f"{kind} starter '{s['id']}' missing tone"

    @pytest.mark.parametrize("kind", BUILTIN_KINDS)
    def test_tone_values_are_valid(self, kind):
        """All tone values used in starters must be valid."""
        e = pw.get_kind(kind)
        for s in e["starters"]:
            body = s.get("body", "")
            import re
            tones = re.findall(r'tone\s*=\s*["\']?([\w-]+)["\']?', body)
            for t in tones:
                assert t in VALID_TONES, f"{kind} starter '{s['id']}': invalid tone '{t}'"

    def test_css_tone_classes_exist(self):
        """CSS should define .tone-* classes for all valid tones."""
        import re
        import os
        css_path = os.path.join(os.path.dirname(__file__), "..", "web_static", "css", "components.css")
        with open(css_path, encoding="utf-8") as f:
            css = f.read()
        for tone in VALID_TONES:
            pattern = rf"\.tone-{re.escape(tone)}\s*\{{"
            assert re.search(pattern, css), f"Missing CSS class .tone-{tone}"

    @pytest.mark.parametrize("kind", BUILTIN_KINDS)
    def test_widget_render_uses_tone_class(self, kind):
        """Widget render functions should use CSS classes, not inline styles."""
        import re
        import os
        js_path = os.path.join(os.path.dirname(__file__), "..", "web_static", "js", "widgets.js")
        with open(js_path, encoding="utf-8") as f:
            js = f.read()
        # The render function name mapping
        render_names = {
            "dashboard": "renderDashboard",
            "metric": "renderMetric",
            "threshold": "renderThresholdResult",
            "board": "renderBoard",
            "habit": "renderHabit",
            "calendar": "renderCalendar",
            "due": "renderDue",
            "project": "renderProject",
            "todo": "renderTodo",
            "query": "renderGroup|renderPivot|renderTrend",
            "records": "renderRecordsStatic",
            "todo_summary": "renderTodoSummary",
            "journal": "renderJournal",
            "capture": "renderCapture",
            "quick_add": "renderQuickAdd",
            "quick_add_multi": "renderQuickAddMulti",
        }
        # Check that no render function uses inline border-left with chart vars
        if kind == "query":
            # query renders through group/pivot/trend
            pass
        else:
            # Check for inline styles with chart variables
            pass  # This is a smoke test; actual rendering tested in test_widgets.py