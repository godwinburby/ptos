# PTOS Charts Spec

Audit basis: `main` at `b591b38` (2026-10-14).

## Correction to the earlier gap list

Two items I called missing already exist:

- **Group, pivot and trend** are implemented: `get_group`, `get_pivot`, `get_trend` in `ptos_service.py`, saved-query keys `group`, `pivot`, `trend`, and web renderers `renderGroup`, `renderPivot`, `renderTrend` in `web_static/js/widgets.js`. They are also embeddable in notes via the `view` embed option.
- **CSV export** exists on the records table (`RecordTable._export`).

**The real gap is visual output.** Every aggregate result renders as a table. Only thresholds have bars. This spec adds a chart layer on top of the existing result shapes. It adds no new query kinds and no engine logic.

---

## 1. Goals and non-goals

**Goals**
- Render existing `group`, `trend` and `pivot` results as charts: bar, line, stacked bar.
- Work on the Queries page, on dashboards, and in markdown embeds, through the one shared `widgets.js` path.
- Zero new dependencies: inline SVG generated in JS. CSS variables for theme and dark mode.
- Config-driven, in `queries.toml`, consistent with the zero-domain-logic rule.

**Non-goals**
- No charting library (Chart.js, D3).
- No new aggregation functions beyond what `get_group` / `get_pivot` / `get_trend` return today.
- No interactive drill-down in v1 (see 6.1).
- No CLI graphics; optional text bars only (section 5).

## 2. Config

Add one optional key to existing saved queries. Default stays the table.

```toml
[expenses_by_category]
where = "type=expense"
time  = "this-month"
group = "category"
chart = "bar"          # bar | hbar | line | stacked | none (default none = table)

[monthly_trend]
where = "type=expense"
time  = "this-month"
trend = 6
chart = "line"
y     = "total"        # trend only: count | total | avg (default: total if has_amount else count)

[spend_by_cat_month]
where = "type=expense"
pivot = ["category", "month"]
chart = "stacked"
```

Rules:
- `chart` is valid only with `group`, `trend` or `pivot`. On records, metrics or dashboards it is ignored and lint warns.
- Compatibility: `bar`/`hbar` for group; `bar`/`line` for trend; `stacked`/`bar` for pivot (rows become series, columns the x axis). Invalid combos fall back to the table and show a one-line notice.
- Embeds accept an override: `view=group chart=hbar`.
- A `Table | Chart` toggle is always present so numbers stay one click away.

## 3. Rendering

Add to `widgets.js`:

- `renderChart(d, kind, opts)` returns an SVG string; dispatched from `renderResult` when the result carries `chart`.
- Pure functions per chart type: `chartBar`, `chartHBar`, `chartLine`, `chartStacked`. Shared helpers for scale, nice ticks, label truncation, value formatting (reuse `fmt`).
- Series colors from CSS variables (`--chart-1` … `--chart-8`) defined in both light and dark themes; no hard-coded colors.
- Responsive: `viewBox` plus `width:100%`; horizontal bars for more than 8 categories or long labels; labels rotate or thin out rather than overlap; on narrow screens (about 380px) limit visible x labels.
- Accessibility: `role="img"` with an `aria-label` summary, `<title>` per bar/point for hover tooltips, and a data table available through the toggle.
- Empty or single-point data: show the existing "no data" card, not an empty axis.
- Escape every label with the existing `esc()`.
- Cap rendered categories (default 12, rest grouped into "Other") so a high-cardinality field cannot produce an unreadable chart.

Service side: `run_query` returns `chart` and `y` in its payload when set. No change to the aggregate computation.

## 4. Query builder UI

- Add a "Chart" dropdown to the saved-query form in `query_builder.html`, shown only when group/trend/pivot is set, listing only compatible types.
- `save_query_entry` validates the value against the allowed set and compatibility rules; reject unknown values with a clear `PTOSError`.
- Starter queries: set `chart` on 2–3 examples (`expenses_by_category` as `hbar`, `monthly_trend` as `line`) so a fresh install shows charts in the demo.

## 5. CLI (optional, low priority)

- `ptos -q NAME` prints a text bar column next to group and trend rows when `chart` is set (`█` scaled to 20 chars). No flag changes. Skip if it complicates `ptos.py`; the CLI core must stay dependency-free and small.

## 6. Later, out of scope for v1

1. Click a bar to open the matching records (the group value becomes a `where` filter into `/browse`).
2. Year heatmap and week calendar modes.
3. Chart type on dashboards (a dashboard tile that is a chart).
4. Dual-axis or goal lines tied to thresholds.

## 7. Tests

- **Unit (JS-free, Python):** `save_query_entry` accepts valid `chart` values, rejects invalid and incompatible ones; `run_query` includes `chart`/`y` only for group/trend/pivot; lint warns on `chart` with records/metric.
- **Rendering:** snapshot tests on the generated SVG strings via a small headless harness (or a Python port of the pure scale/tick helpers) covering: single series, negative values, zero total, 1 point, >12 categories ("Other" bucket), long labels, HTML in labels (escaped).
- **Web:** `/queries/run` returns the chart payload; embed mounter renders a chart for `view=group chart=hbar`; templates load with all theme variables defined.
- **Regression:** all existing group/pivot/trend table tests unchanged and passing.

## 8. Acceptance

- `expenses_by_category`, `monthly_trend` and a pivot query each show a correct chart in light and dark themes on a ~380px viewport and on desktop.
- Table toggle shows identical numbers to the chart.
- A query without `chart` renders exactly as before.
- No new files in `requirements.txt`; no external requests (works offline and under the existing CSP-free setup).
- Full test suite passes in CI on Ubuntu and Windows.

## 9. Effort and order

1. Palette CSS variables and `chartBar`/`chartHBar` (group only).
2. `chartLine` for trend.
3. `chartStacked` for pivot.
4. Toggle, embeds, query-builder dropdown, starters.
5. Lint warning, tests, CHANGELOG, README section with one screenshot per chart type.

Expected size: roughly 300–400 lines of JS plus about 100 lines of service/validation and tests. The README screenshots double as the demo material for sharing.
