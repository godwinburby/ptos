"""
ptos_service.py  —  Structured data layer for PTOS
Returns dicts/lists instead of printing.  Zero UI knowledge.
Used by ptos_web.py (Flask) and ptos_gui.pyw (Tkinter).
ptos.py CLI is unchanged and does not use this file.
"""

import sys
import os
import datetime as dt

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# ── patch sys.exit BEFORE importing ptos so it never kills the process ────────
class PTOSError(Exception):
    """Raised instead of sys.exit() so callers can handle gracefully."""
    pass

def _safe_exit(msg=""):
    raise PTOSError(str(msg))

sys.exit = _safe_exit
# ─────────────────────────────────────────────────────────────────────────────

import ptos


def _cycles():
    return ptos.get_config().get("cycles", {})


def _resolve_time(code):
    try:
        return ptos.resolve_time(code or "tm", _cycles())
    except Exception as e:
        raise PTOSError(f"Invalid time '{code}': {e}")


def _parse_record(line):
    """Parse a raw log line into a flat dict suitable for UI rendering."""
    parsed = ptos.safe_parse_line(line)
    if not parsed:
        return None
    d, kv, note = parsed
    row = {"date": str(d)}
    for k, v in kv.items():
        row[k] = ", ".join(v) if isinstance(v, list) else str(v)
    if note:
        row["note"] = note
    return row


# ══════════════════════════════════════════════════════════════════════════════
# Records
# ══════════════════════════════════════════════════════════════════════════════

def get_records(filters, time="tm", search=None, sort=None,
                from_file=None, sum_field=None, select=None):
    """
    Returns:
      { records: [{date, type, ...fields, note}],
        columns: [col_name, ...],        # ordered, for table headers
        count: int,
        total: int,                      # 0 if no numeric field
        total_fmt: str,
        avg_fmt: str,
        start: str, end: str,
        time_label: str,
        filters: [str] }
    """
    try:
        start, end = _resolve_time(time)
        raw, total = ptos.scan_records(
            start, end, filters, search,
            from_file=from_file, sum_field=sum_field)
    except PTOSError:
        raise
    except Exception as e:
        raise PTOSError(str(e))

    if sort:
        def _sk(line):
            p = ptos.safe_parse_line(line)
            if not p: return (1, 0, "")
            v = p[1].get(sort, "")
            if isinstance(v, list): v = v[0] if v else ""
            try:    return (0, int(v), "")
            except: return (1, 0, str(v).lower())
        raw = sorted(raw, key=_sk)

    records = []
    col_seen = []
    col_set  = set()

    for line in raw:
        row = _parse_record(line)
        if not row:
            continue
        records.append(row)
        for k in row:
            if k not in col_set:
                col_seen.append(k)
                col_set.add(k)

    # apply --select column filter
    if select:
        want = set(select) | {"date", "type"}
        col_seen = [c for c in col_seen if c in want]
        records  = [{k: v for k, v in r.items() if k in want} for r in records]

    time_label = ptos._TIME_ALIASES.get(time, time)
    count = len(records)

    return {
        "records":    records,
        "columns":    col_seen,
        "count":      count,
        "total":      total,
        "total_fmt":  ptos.fmt(total) if total else "",
        "avg_fmt":    ptos.fmt_avg(total / count) if count and total else "",
        "start":      str(start),
        "end":        str(end),
        "time_label": time_label,
        "filters":    filters,
    }


# ══════════════════════════════════════════════════════════════════════════════
# Group
# ══════════════════════════════════════════════════════════════════════════════

def get_group(filters, time="tm", group_fields=None,
              sum_field=None, from_file=None):
    """
    Returns:
      { rows: [{key: str, count: int, total: int, total_fmt: str}],
        fields: [str],
        has_amount: bool,
        grand_count: int,
        grand_total: int,
        grand_total_fmt: str,
        time_label: str,
        start: str, end: str }
    """
    group_fields = group_fields or ["type"]
    try:
        start, end = _resolve_time(time)
        raw, total = ptos.scan_records(start, end, filters, None,
                                       from_file=from_file, sum_field=sum_field)
    except PTOSError:
        raise
    except Exception as e:
        raise PTOSError(str(e))

    counts, sums, has_amount = ptos.group_results(raw, group_fields, sum_field=sum_field)

    rows = []
    grand_count = 0
    grand_total = 0
    for key in sorted(counts):
        label = "  ".join(key) if isinstance(key, tuple) else key
        cnt   = counts[key]
        s     = sums.get(key, 0)
        grand_count += cnt
        grand_total += s
        rows.append({
            "key":       label,
            "count":     cnt,
            "total":     s,
            "total_fmt": ptos.fmt(s) if has_amount else "",
        })

    return {
        "rows":            rows,
        "fields":          group_fields,
        "has_amount":      has_amount,
        "grand_count":     grand_count,
        "grand_total":     grand_total,
        "grand_total_fmt": ptos.fmt(grand_total) if has_amount else "",
        "time_label":      ptos._TIME_ALIASES.get(time, time),
        "start":           str(start),
        "end":             str(end),
    }


# ══════════════════════════════════════════════════════════════════════════════
# Pivot
# ══════════════════════════════════════════════════════════════════════════════

def get_pivot(filters, time="tm", row_field="type", col_field="month",
              count_mode=False, sort_col=None, sum_field=None):
    """
    Returns:
      { cols: [str],
        rows: [{label: str, <col>: int, ..., total: int}],
        col_totals: {col: int},
        grand: int,
        row_field: str,
        col_field: str,
        time_label: str }
    """
    try:
        start, end = _resolve_time(time)
        raw, _ = ptos.scan_records(start, end, filters, None)
    except PTOSError:
        raise
    except Exception as e:
        raise PTOSError(str(e))

    table, cols, row_order = ptos.pivot_results(
        raw, row_field, col_field, count_mode, sort_col, sum_field=sum_field)

    col_totals = {c: 0 for c in cols}
    grand      = 0
    rows       = []
    for row_label in row_order:
        row_total = 0
        r = {"label": row_label}
        for c in cols:
            val = table[row_label].get(c, 0)
            r[c]           = val
            row_total      += val
            col_totals[c]  += val
        r["total"] = row_total
        grand     += row_total
        rows.append(r)

    return {
        "cols":        cols,
        "rows":        rows,
        "col_totals":  col_totals,
        "grand":       grand,
        "row_field":   row_field,
        "col_field":   col_field,
        "time_label":  ptos._TIME_ALIASES.get(time, time),
        "start":       str(start),
        "end":         str(end),
    }


# ══════════════════════════════════════════════════════════════════════════════
# Trend
# ══════════════════════════════════════════════════════════════════════════════

def get_trend(filters, time="tm", n=6):
    """
    Returns:
      { periods: [{label, count, total, total_fmt, avg_fmt}],
        has_amount: bool,
        filter_str: str }
    """
    try:
        periods = ptos._prior_periods(time, n, _cycles())
    except Exception as e:
        raise PTOSError(str(e))

    if not periods:
        raise PTOSError(
            f"--trend not supported for time window: {time}\n"
            f"Use: this-month, this-week, this-quarter, YYYY-MM, or a named cycle")

    rows       = []
    has_amount = False
    for label, start, end in periods:
        raw, total = ptos.scan_records(start, end, filters, None)
        count = len(raw)
        if total > 0:
            has_amount = True
        rows.append({
            "label":     label,
            "count":     count,
            "total":     total,
            "total_fmt": ptos.fmt(total) if total else "",
            "avg_fmt":   ptos.fmt_avg(total / count) if count and total else "",
        })

    return {
        "periods":    rows,
        "has_amount": has_amount,
        "filter_str": " ".join(filters) if filters else "all",
        "n":          n,
    }


# ══════════════════════════════════════════════════════════════════════════════
# Due list
# ══════════════════════════════════════════════════════════════════════════════

def get_due(config_name=None, days_override=None):
    """
    Returns:
      { rows: [{name, days, status, note, heat, key_val}],
        count: int,
        rec_type: str,
        days: int,
        key_field: str,
        sort_field: str }
    heat values: 'hot' (>=7d), 'warm' (3-6d), 'cool' (<3d)
    """
    try:
        queries = ptos.get_queries()
    except PTOSError:
        raise
    except Exception as e:
        raise PTOSError(str(e))

    # resolve config block
    if config_name and config_name not in ("__DEFAULT__",):
        named = queries.get("due", {})
        due_cfg = named.get(config_name) if isinstance(named, dict) else None
        if not due_cfg:
            raise PTOSError(f"Due config '{config_name}' not found in queries.toml")
    else:
        due_cfg = queries.get("due")
        if not due_cfg:
            raise PTOSError("No [due] section in queries.toml")

    rec_type  = due_cfg.get("type")
    key_field = due_cfg.get("key")
    sort_field = due_cfg.get("sort_by")
    exclude   = due_cfg.get("exclude_results", [])
    days      = days_override if days_override is not None else int(due_cfg.get("days", 7))

    if not rec_type or not key_field:
        raise PTOSError("[due] config missing 'type' or 'key'")

    # priority from schema
    priority = {}
    if sort_field:
        try:
            schema    = ptos.get_schema()
            type_meta = schema.get("type", {}).get(rec_type, {})
            options   = type_meta.get("fields", {}).get(sort_field, {}).get("options", [])
            if isinstance(options, list):
                priority = {v: i for i, v in enumerate(options)}
            elif isinstance(options, dict):
                idx = 0
                for vals in options.values():
                    for v in vals:
                        if v not in priority:
                            priority[v] = idx; idx += 1
        except Exception:
            pass

    try:
        raw, _ = ptos.scan_records(dt.date.min, dt.date.max, [f"type={rec_type}"], None)
    except Exception as e:
        raise PTOSError(str(e))

    latest = {}
    for line in raw:
        p = ptos.safe_parse_line(line)
        if not p: continue
        d, kv, note = p
        k = kv.get(key_field)
        if not k: continue
        if k not in latest or d > latest[k]["date"]:
            latest[k] = {"date": d, "kv": kv, "note": note}

    if exclude:
        latest = {k: r for k, r in latest.items()
                  if r["kv"].get("result") not in exclude}

    cutoff  = ptos.today() - dt.timedelta(days=days)
    overdue = [r for r in latest.values() if r["date"] <= cutoff]
    overdue.sort(key=lambda r: (
        priority.get(r["kv"].get(sort_field, ""), 999) if sort_field else 0,
        r["date"]
    ))

    rows = []
    for rec in overdue:
        kv  = rec["kv"]
        gap = (ptos.today() - rec["date"]).days
        rows.append({
            "name":      kv.get("name", kv.get(key_field, "-")),
            "key_val":   kv.get(key_field, "-"),
            "days":      gap,
            "status":    kv.get(sort_field, "") if sort_field else "",
            "note":      rec["note"] or "",
            "heat":      "hot" if gap >= 7 else "warm" if gap >= 3 else "cool",
        })

    return {
        "rows":       rows,
        "count":      len(rows),
        "rec_type":   rec_type,
        "days":       days,
        "key_field":  key_field,
        "sort_field": sort_field or "",
    }


# ══════════════════════════════════════════════════════════════════════════════
# Metric
# ══════════════════════════════════════════════════════════════════════════════

def get_metric(name, time="tm"):
    """
    Returns:
      { name: str, value: str, raw: float|int|None }
    """
    try:
        queries = ptos.get_queries()
        cycles  = _cycles()
        start, end = _resolve_time(time)
        metrics = queries.get("metrics", {})
    except PTOSError:
        raise
    except Exception as e:
        raise PTOSError(str(e))

    if name not in metrics:
        raise PTOSError(f"Metric '{name}' not found")

    m = metrics[name]

    try:
        if "ratio" in m:
            q1, q2 = m["ratio"]
            c1, _  = ptos._run_base_query(q1, queries, start, end, cycles)
            c2, _  = ptos._run_base_query(q2, queries, start, end, cycles)
            if c2 == 0:
                return {"name": name, "value": "no data", "raw": None}
            raw = (c1 / c2) * 100
            return {"name": name, "value": f"{raw:.1f}%  ({c1}/{c2})", "raw": raw}

        if "avg" in m:
            uf = m.get("unit_field")
            uw = m.get("unit_weights")
            if uf and uw:
                lines, total = ptos._run_base_query_lines(m["avg"], queries, start, end, cycles)
                if not lines:
                    return {"name": name, "value": "no data", "raw": None}
                units = sum(uw.get(
                    (ptos.safe_parse_line(l) or (None,{},None))[1].get(uf,""), 1)
                    for l in lines)
                raw = total / units if units else 0
            else:
                cnt, total = ptos._run_base_query(m["avg"], queries, start, end, cycles)
                if cnt == 0:
                    return {"name": name, "value": "no data", "raw": None}
                raw = total / cnt
            return {"name": name, "value": ptos.fmt_avg(raw), "raw": raw}

        if "sum" in m:
            _, total = ptos._run_base_query(m["sum"], queries, start, end, cycles)
            return {"name": name, "value": ptos.fmt(total), "raw": total}

        if "max" in m or "min" in m:
            key = "max" if "max" in m else "min"
            lines, _ = ptos._run_base_query_lines(m[key], queries, start, end, cycles)
            values = [ptos.numeric_value(
                (ptos.safe_parse_line(l) or (None,{},None))[1])
                for l in lines]
            values = [v for v in values if v is not None]
            if not values:
                return {"name": name, "value": "no data", "raw": None}
            raw = max(values) if key == "max" else min(values)
            return {"name": name, "value": ptos.fmt(raw), "raw": raw}

    except Exception as e:
        return {"name": name, "value": f"error: {e}", "raw": None}

    return {"name": name, "value": "?", "raw": None}


# ══════════════════════════════════════════════════════════════════════════════
# Dashboard
# ══════════════════════════════════════════════════════════════════════════════

def get_dashboard(name, time="tm"):
    """
    Returns:
      { name: str,
        period: str,
        items: [{name, value, raw}] }
    """
    try:
        queries    = ptos.get_queries()
        cycles     = _cycles()
        start, end = _resolve_time(time)
        dashboards = queries.get("dashboards", {})
    except PTOSError:
        raise
    except Exception as e:
        raise PTOSError(str(e))

    if name not in dashboards:
        raise PTOSError(f"Dashboard '{name}' not found")

    items = []
    for item_name in dashboards[name].get("metrics", []):
        metrics = queries.get("metrics", {})
        if item_name in metrics:
            items.append(get_metric(item_name, time))
        elif item_name in queries:
            try:
                cnt, total = ptos._run_base_query(item_name, queries, start, end, cycles)
                value = str(cnt)
                if total > 0:
                    value += f"  ({ptos.fmt(total)})"
                items.append({"name": item_name, "value": value, "raw": cnt})
            except Exception as e:
                items.append({"name": item_name, "value": f"error: {e}", "raw": None})
        else:
            items.append({"name": item_name, "value": "not found", "raw": None})

    return {
        "name":   name,
        "period": f"{start} to {end}",
        "items":  items,
    }


# ══════════════════════════════════════════════════════════════════════════════
# Lint
# ══════════════════════════════════════════════════════════════════════════════

def run_lint():
    """
    Returns:
      { clean: bool,
        checked: int,
        type_counts: {type: count},
        errors: [{line, problems: [str]}],
        warnings: [{line, problems: [str]}],
        error_count: int,
        warning_count: int }
    """
    try:
        schema  = ptos.get_schema()
        raw, _  = ptos.scan_records(dt.date.min, dt.date.max, [], None)
    except PTOSError:
        raise
    except Exception as e:
        raise PTOSError(str(e))

    errors       = []
    warnings     = []
    type_counts  = {}
    total_checked = 0

    for line in raw:
        if not line.strip():
            continue
        total_checked += 1
        p = ptos.safe_parse_line(line)
        if not p:
            errors.append({"line": line, "problems": ["Malformed line — cannot parse"]})
            continue
        d, kv, note = p
        rtype = kv.get("type", "unknown")
        type_counts[rtype] = type_counts.get(rtype, 0) + 1

        hard = []
        soft = []
        if d == dt.date.min:
            hard.append("Missing or malformed date")
        if "type" not in kv:
            hard.append("Missing type field")
        if "tag" not in kv:
            soft.append("No tag")
        if not note:
            soft.append("No note")

        schema_problems = ptos.validate_record(schema, kv)
        hard.extend(schema_problems)

        if hard:
            errors.append({"line": line, "problems": hard})
        if soft:
            warnings.append({"line": line, "problems": soft})

    return {
        "clean":         len(errors) == 0 and len(warnings) == 0,
        "checked":       total_checked,
        "type_counts":   type_counts,
        "errors":        errors,
        "warnings":      warnings,
        "error_count":   len(errors),
        "warning_count": len(warnings),
    }


# ══════════════════════════════════════════════════════════════════════════════
# Query runner (resolves saved query to correct call)
# ══════════════════════════════════════════════════════════════════════════════

def run_query(name, time=None):
    """
    Resolves a named query and returns structured data.
    Returns a dict with a 'kind' key indicating the result type:
      kind='records'   → get_records() result
      kind='group'     → get_group() result
      kind='pivot'     → get_pivot() result
      kind='trend'     → get_trend() result
      kind='metric'    → get_metric() result
      kind='dashboard' → get_dashboard() result
    """
    try:
        queries    = ptos.get_queries()
        metrics    = queries.get("metrics", {})
        dashboards = queries.get("dashboards", {})
    except PTOSError:
        raise
    except Exception as e:
        raise PTOSError(str(e))

    if name in dashboards:
        result = get_dashboard(name, time or "tm")
        result["kind"] = "dashboard"
        return result

    if name in metrics:
        result = get_metric(name, time or "tm")
        result["kind"] = "metric"
        return result

    q = queries.get(name)
    if not q or not isinstance(q, dict):
        raise PTOSError(f"Query '{name}' not found")

    effective_time = time or q.get("time", "tm")
    filters = q.get("where", "").split()

    if "group" in q:
        result = get_group(filters, effective_time, q["group"],
                           sum_field=q.get("sum_field"))
        result["kind"] = "group"
        return result

    if "pivot" in q and len(q["pivot"]) >= 2:
        result = get_pivot(filters, effective_time,
                           q["pivot"][0], q["pivot"][1],
                           count_mode=q.get("count", False),
                           sort_col=q.get("sort"))
        result["kind"] = "pivot"
        return result

    if "trend" in q:
        result = get_trend(filters, effective_time, int(q["trend"]))
        result["kind"] = "trend"
        return result

    result = get_records(filters, effective_time)
    result["kind"] = "records"
    return result
