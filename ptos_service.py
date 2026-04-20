"""
ptos_service.py  —  Service layer for PTOS
Returns dicts/lists instead of printing.  Zero UI knowledge.
Used by ptos_web.py (Flask).
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


# ══════════════════════════════════════════════════════════════════════
# Path constants (read-only aliases to engine paths)
# ══════════════════════════════════════════════════════════════════════

JOURNAL_DIR = ptos.JOURNAL_DIR
RECORDS_DIR = ptos.RECORDS_DIR
BACKUP_DIR = ptos.BACKUP_DIR
BASE_DIR = ptos.BASE_DIR
SCHEMA_PATH = ptos.SCHEMA_PATH
QUERIES_PATH = ptos.QUERIES_PATH


def _cycles():
    return ptos.get_config().get("cycles", {})


def _resolve_time(code):
    try:
        return ptos.resolve_time(code or "tm", _cycles())
    except Exception as e:
        raise PTOSError(f"Invalid time '{code}': {e}")


def _parse_record(line, format_date=True):
    """Parse a raw log line into a flat dict suitable for UI rendering.
    Derived fields from schema are computed and added as virtual columns.
    """
    parsed = ptos.safe_parse_line(line)
    if not parsed:
        return None
    d, kv, note = parsed
    row = {"date": fmt_date(d) if format_date else str(d)}
    for k, v in kv.items():
        row[k] = ", ".join(v) if isinstance(v, list) else str(v)
    # append derived fields — pass record date for date arithmetic
    computed = ptos.compute_derived(kv, record_date=d)
    for fname, val in computed.items():
        if val is not None:
            row[fname] = str(val) if not isinstance(val, str) else val
    if note:
        row["note"] = note
    return row


# ══════════════════════════════════════════════════════════════════════════════
# Configuration (service layer wrappers)
# ══════════════════════════════════════════════════════════════════════════════

def get_config():
    """Get PTOS configuration.
    
    Returns:
        dict: Configuration as dict loaded from config.toml.
    """
    return ptos.get_config()


def get_schema():
    """Get record schema definition.
    
    Returns:
        dict: Schema loaded from schema.toml with types, fields, and options.
    """
    return ptos.get_schema()


def get_presets():
    """Get saved presets.
    
    Returns:
        dict: Presets loaded from presets.toml.
    """
    return ptos.get_presets()


# ══════════════════════════════════════════════════════════════════════════════
# Write operations (atomic)
# ══════════════════════════════════════════════════════════════════════════════

def append_record(line):
    """Append a record line to the appropriate year log file.
    
    Args:
        line: Record line string to append.
    
    Returns:
        dict: Result with ok and message.
    """
    try:
        return ptos.append_record(line)
    except Exception as e:
        raise PTOSError(str(e))


def write_file(filepath, content):
    """Write content to a file atomically.
    
    Args:
        filepath: Path to file to write.
        content: String content to write.
    
    Returns:
        None
    """
    try:
        return ptos.atomic_write(filepath, content)
    except Exception as e:
        raise PTOSError(str(e))


# ══════════════════════════════════════════════════════════════════════════════
# Backup operations
# ══════════════════════════════════════════════════════════════════════════════

def backup_full():
    """Create a full backup of records/, config/, and templates/ folders.
    
    Returns:
        str: Path to the created backup ZIP file.
    """
    try:
        backup_path = ptos.backup_data()
        return {"ok": True, "path": backup_path}
    except Exception as e:
        raise PTOSError(str(e))


def backup_config_only():
    """Create a config-only backup ZIP.
    
    Returns:
        str: Path to the created backup ZIP file.
    """
    try:
        backup_path = ptos.backup_config()
        return {"ok": True, "path": backup_path}
    except Exception as e:
        raise PTOSError(str(e))


def get_backup_preview():
    """Get preview of what will be backed up.
    
    Returns:
        dict: Preview information about backup contents.
    """
    try:
        preview = ptos.get_backup_preview()
        return {"ok": True, "preview": preview}
    except Exception as e:
        raise PTOSError(str(e))


def get_restore_preview(filename):
    """Get preview of what will be restored from a backup file.
    
    Args:
        filename: Name of backup file to preview.
    
    Returns:
        dict: Preview information about backup contents.
    """
    try:
        backup_path = os.path.join(ptos.BACKUP_DIR, filename)
        preview = ptos.get_restore_preview(backup_path)
        return {"ok": True, "preview": preview}
    except Exception as e:
        raise PTOSError(str(e))


def list_backups():
    """List all backup files.
    
    Returns:
        list: List of tuples (filename, created_datetime, type).
              type is 'full' or 'config'.
    """
    return ptos.list_backups()


def delete_backup(filename):
    """Delete a backup file.
    
    Args:
        filename: Name of backup file to delete.
    
    Returns:
        bool: True on success.
    """
    try:
        return ptos.delete_backup(filename)
    except Exception as e:
        raise PTOSError(str(e))


def restore_full(zip_path):
    """Restore data from a full backup ZIP.
    
    Args:
        zip_path: Path to backup ZIP file.
    
    Returns:
        None
    """
    try:
        ptos.restore_data(zip_path)
        return {"ok": True}
    except Exception as e:
        raise PTOSError(str(e))


# ══════════════════════════════════════════════════════════════════════════════
# Records
# ══════════════════════════════════════════════════════════════════════════════
# History suggestions
# ══════════════════════════════════════════════════════════════════════════════

def get_history_suggestions(rtype, context_record=None):
    """Scan all records of the given type and return:
      tags:           sorted list of all tags ever used for this type
      filtered_tags:  tags filtered by context_record's field cascade (schema + history based)
      field_values:   {fieldname: [values by freq]} for free-text fields
      field_defaults: {fieldname: most_common_value} for schema option fields
                      — used to pre-select the most likely value on type selection

    If context_record is provided, filtered_tags includes:
    1. Schema-defined tags from resolve_tags() based on context field values
    2. Historical tags that appeared in past records with matching field values

    Single scan, results suitable for caching by the caller.
    """
    try:
        schema      = ptos.get_schema()
        type_schema = schema.get("type", {}).get(rtype, {})
    except Exception:
        schema = {}
        type_schema = {}

    # separate fields into: has schema options vs free-text vs numeric
    fields_with_options = set()
    numeric_fields      = set()
    for fname, fdef in type_schema.get("fields", {}).items():
        if isinstance(fdef, dict):
            if fdef.get("options") or fdef.get("use"):
                fields_with_options.add(fname)
    for fname, fdef in schema.get("fields", {}).items():
        if isinstance(fdef, dict) and fdef.get("type") == "int":
            numeric_fields.add(fname)

    try:
        raw, _ = ptos.scan_records(
            dt.date.min, dt.date.max,
            [f"type={rtype}"], None)
    except Exception:
        return {"tags": [], "filtered_tags": [], "field_values": {}, "field_defaults": {}}

    from collections import Counter
    tag_set      = set()
    field_counts = {}   # {fieldname: Counter} — all fields
    # Track tags per field value for cascade-aware filtering
    # {fieldname: {fieldvalue: {tags...}}}
    tags_by_field_value = {}

    for line in raw:
        parsed = ptos.safe_parse_line(line)
        if not parsed:
            continue
        _, kv, _ = parsed
        # tags
        tv = kv.get("tag")
        if tv:
            record_tags = set(tv if isinstance(tv, list) else [tv])
            tag_set.update(record_tags)
            # Track tags per field value for cascade filtering
            for f in fields_with_options:
                fv = kv.get(f)
                if fv:
                    fv_list = fv if isinstance(fv, list) else [fv]
                    for v in fv_list:
                        if f not in tags_by_field_value:
                            tags_by_field_value[f] = {}
                        if v not in tags_by_field_value[f]:
                            tags_by_field_value[f][v] = set()
                        tags_by_field_value[f][v].update(record_tags)
        # all non-type, non-numeric fields
        for k, v in kv.items():
            if k in ("type", "tag") or k in numeric_fields:
                continue
            vals = v if isinstance(v, list) else [v]
            if k not in field_counts:
                field_counts[k] = Counter()
            for val in vals:
                field_counts[k][val] += 1

    # free-text fields: top 20 values for datalist autocomplete
    field_values = {
        k: [v for v, _ in counter.most_common(20)]
        for k, counter in field_counts.items()
        if counter and k not in fields_with_options
    }

    # schema option fields: single most common value for pre-selection
    field_defaults = {}
    for k, counter in field_counts.items():
        if k in fields_with_options and counter:
            field_defaults[k] = counter.most_common(1)[0][0]

    # global_fields with options: most common value for pre-selection in panel
    for fname, fdef in schema.get("global_fields", {}).items():
        if isinstance(fdef, dict) and fdef.get("options") and fname in field_counts:
            counter = field_counts[fname]
            if counter:
                field_defaults[fname] = counter.most_common(1)[0][0]

    # Calculate filtered tags based on context_record
    filtered_tags = set()
    if context_record:
        # 1. Schema-defined tags from resolve_tags (based on context field values)
        schema_tags = ptos.resolve_tags(schema, type_schema, context_record)
        filtered_tags.update(schema_tags)
        
        # 2. Historical tags from records that match context field values
        for field, value in context_record.items():
            if field in tags_by_field_value and value:
                value_str = str(value)
                if value_str in tags_by_field_value[field]:
                    filtered_tags.update(tags_by_field_value[field][value_str])
                # Also check for list values
                if isinstance(value, list):
                    for v in value:
                        v_str = str(v)
                        if v_str in tags_by_field_value[field]:
                            filtered_tags.update(tags_by_field_value[field][v_str])

    return {
        "tags":           sorted(tag_set),
        "filtered_tags":  sorted(filtered_tags),
        "field_values":   field_values,
        "field_defaults": field_defaults,
    }


def get_conditional_suggestions(rtype, field, value):
    """Given a known field=value, return the most common value for every
    other schema-option field across matching history records.
    Used for cascade pre-fill: user picks source=mgm → suggest booked_by=cso.
    Returns: {fieldname: most_common_value}
    """
    from collections import Counter

    try:
        schema      = ptos.get_schema()
        type_schema = schema.get("type", {}).get(rtype, {})
    except Exception:
        return {}

    # only suggest for fields that have schema options
    fields_with_options = set()
    for fname, fdef in type_schema.get("fields", {}).items():
        if isinstance(fdef, dict) and (fdef.get("options") or fdef.get("use")):
            fields_with_options.add(fname)

    try:
        raw, _ = ptos.scan_records(
            dt.date.min, dt.date.max,
            [f"type={rtype}", f"{field}={value}"], None)
    except Exception:
        return {}

    if not raw:
        return {}

    field_counts = {}
    for line in raw:
        parsed = ptos.safe_parse_line(line)
        if not parsed:
            continue
        _, kv, _ = parsed
        for k, v in kv.items():
            if k in ("type", "tag", field):
                continue
            if k not in fields_with_options:
                continue
            vals = v if isinstance(v, list) else [v]
            if k not in field_counts:
                field_counts[k] = Counter()
            for val in vals:
                field_counts[k][val] += 1

    return {
        k: counter.most_common(1)[0][0]
        for k, counter in field_counts.items()
        if counter
    }


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

    # build line→filepath map for edit/delete support
    try:
        if filters or search:
            loc_matches = ptos.find_records_with_location(
                filters, search=search, start=start, end=end)
        else:
            loc_matches = ptos.find_records_with_location(
                [], search=None, start=start, end=end)
        line_to_filepath = {line: fp   for fp, idx, line in loc_matches}
        line_to_lineno   = {line: idx  for fp, idx, line in loc_matches}
    except Exception:
        line_to_filepath = {}
        line_to_lineno   = {}

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
        row["_line"]     = line
        row["_filepath"] = line_to_filepath.get(line, "")
        row["_lineno"]   = line_to_lineno.get(line, -1)
        records.append(row)
        for k in row:
            if k not in col_set and not k.startswith("_"):
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
    # Configs are stored as:
    # - queries["due"] with root keys = default config (type, key, sort_by, days)
    # - queries["due"]["followup"] etc = additional configs
    # - queries["due.followup"] = separate [due.followup] section (backup)
    if config_name and config_name not in ("__DEFAULT__",):
        due_cfg = None
        named = queries.get("due", {})
        if isinstance(named, dict):
            # Check if it's a nested config (e.g., due.followup, due.assessment)
            if config_name in named and isinstance(named[config_name], dict):
                due_cfg = named[config_name]
            # Otherwise check root-level keys
            elif named.get("type"):
                due_cfg = named
        # Check separate [due.config_name] section (backup)
        if not due_cfg:
            due_cfg = queries.get(f"due.{config_name}")
        if not due_cfg:
            raise PTOSError(f"Due config '{config_name}' not found in queries.toml")
    else:
        # Default - use "default" key from [due] section, or fall back to "followup"
        due_section = queries.get("due", {})
        if isinstance(due_section, dict):
            due_cfg = due_section.get("default") or due_section.get("followup")
        if not due_cfg:
            due_cfg = queries.get("due.followup")  # Backup check
        if not due_cfg:
            raise PTOSError("No [due] section in queries.toml")

    rec_type  = due_cfg.get("type")
    key_field = due_cfg.get("key") or "name"   # fall back to name if key omitted
    sort_field = due_cfg.get("sort_by")
    exclude   = due_cfg.get("exclude_results", [])
    days      = days_override if days_override is not None else int(due_cfg.get("days", 7))

    if not rec_type:
        raise PTOSError("[due] config missing 'type'")

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

        if "derived" in m:
            # Evaluate arithmetic expression referencing metric names or base query names.
            # e.g. derived = "income - (expense + investment)"
            # Metrics are resolved recursively; base queries yield their total.
            import re as _re
            expr   = m["derived"]
            tokens = _re.findall(r'[a-z][a-z0-9_]*', expr)
            resolved = {}
            for token in tokens:
                if token in resolved:
                    continue
                if token in metrics:
                    dep_m = metrics[token]
                    if "sum" in dep_m:
                        _, val = ptos._run_base_query(dep_m["sum"], queries, start, end, cycles)
                    elif "ratio" in dep_m:
                        c1, _ = ptos._run_base_query(dep_m["ratio"][0], queries, start, end, cycles)
                        c2, _ = ptos._run_base_query(dep_m["ratio"][1], queries, start, end, cycles)
                        val = (c1 / c2 * 100) if c2 else 0
                    elif "avg" in dep_m:
                        cnt, total = ptos._run_base_query(dep_m["avg"], queries, start, end, cycles)
                        val = (total / cnt) if cnt else 0
                    elif "max" in dep_m or "min" in dep_m:
                        key2 = "max" if "max" in dep_m else "min"
                        dep_lines, _ = ptos._run_base_query_lines(dep_m[key2], queries, start, end, cycles)
                        dep_vals = [ptos.numeric_value(
                            (ptos.safe_parse_line(l) or (None, {}, None))[1])
                            for l in dep_lines]
                        dep_vals = [v for v in dep_vals if v is not None]
                        val = (max(dep_vals) if key2 == "max" else min(dep_vals)) if dep_vals else 0
                    else:
                        val = 0
                    resolved[token] = val
                elif token in queries:
                    # resolve as base query — follow one alias level if needed
                    q_entry    = queries[token]
                    query_name = token
                    if isinstance(q_entry, dict) and "alias" in q_entry:
                        target = q_entry["alias"]
                        if target in queries:
                            query_name = target
                    q_resolved = queries.get(query_name, {})
                    if isinstance(q_resolved, dict) and "where" in q_resolved:
                        _, val = ptos._run_base_query(query_name, queries, start, end, cycles)
                    else:
                        val = 0
                    resolved[token] = val
            # substitute resolved names with numeric values
            eval_expr = expr
            for token, val in resolved.items():
                eval_expr = _re.sub(rf'\b{token}\b', str(val), eval_expr)
            # safe eval — only digits, spaces, and arithmetic operators (including scientific notation e)
            if not _re.match(r'^[\d\s\.\+\-\*\/\(\)e]+$', eval_expr):
                return {"name": name, "value": f"unsafe expression: {eval_expr}", "raw": None}
            try:
                raw = float(eval(eval_expr))  # noqa: S307
                formatted = ptos.fmt(int(raw)) if raw == int(raw) else ptos.fmt_avg(raw)
                return {"name": name, "value": formatted, "raw": raw}
            except Exception as e:
                return {"name": name, "value": f"eval error: {e}", "raw": None}

    except Exception as e:
        return {"name": name, "value": f"error: {e}", "raw": None}

    return {"name": name, "value": "?", "raw": None}


# ══════════════════════════════════════════════════════════════════════════════
# Dashboard
# ══════════════════════════════════════════════════════════════════════════════

def get_dashboard(name, time="tm", use_dashboard_time=False):
    """
    Returns:
      { name: str,
        period: str,
        items: [{name, value, raw}] }
    
    use_dashboard_time: if False (default), each metric/query uses its own time.
                      if True, all use the dashboard's time.
    """
    try:
        queries    = ptos.get_queries()
        cycles     = _cycles()
        dashboards = queries.get("dashboards", {})
    except PTOSError:
        raise
    except Exception as e:
        raise PTOSError(str(e))

    if name not in dashboards:
        raise PTOSError(f"Dashboard '{name}' not found")

    # Pre-resolve dashboard time for override case
    if use_dashboard_time:
        db_start, db_end = _resolve_time(time)
    
    items = []
    for item_name in dashboards[name].get("metrics", []):
        metrics = queries.get("metrics", {})
        queries_dict = queries.get("queries", queries)
        
        # Determine which time to use for this item
        if use_dashboard_time:
            # Override: use dashboard's time for all
            item_time = time
        else:
            # Use each item's own time from queries.toml, fallback to dashboard's time
            q = queries_dict.get(item_name, {})
            item_time = q.get("time", time)
        
        # Get start/end for this item
        item_start, item_end = _resolve_time(item_time)
        
        if item_name in metrics:
            item = get_metric(item_name, item_time)
            item["kind"] = "metric"
            items.append(item)
        elif item_name in queries_dict:
            try:
                cnt, total = ptos._run_base_query(item_name, queries, item_start, item_end, cycles)
                value = str(cnt)
                if total > 0:
                    value += f"  ({ptos.fmt(total)})"
                items.append({"name": item_name, "value": value, "raw": cnt,
                               "kind": "query"})
            except Exception as e:
                items.append({"name": item_name, "value": f"error: {e}", "raw": None,
                               "kind": "query"})
        else:
            items.append({"name": item_name, "value": "not found", "raw": None,
                           "kind": "unknown"})

    # Build period string based on dashboard's time
    period_start, period_end = _resolve_time(time) if use_dashboard_time else _resolve_time(item_time)
    
    return {
        "name":   name,
        "period": f"{period_start} to {period_end}",
        "items":  items,
    }


def get_dashboard_names():
    """Return list of all dashboard names."""
    try:
        queries = ptos.get_queries()
        return list(queries.get("dashboards", {}).keys())
    except Exception:
        return []


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

    # resolve alias — follow one level
    if "alias" in q:
        target = q["alias"]
        if target not in queries:
            raise PTOSError(f"Alias '{name}' points to '{target}' which does not exist")
        name = target
        q    = queries[target]
        if not isinstance(q, dict):
            raise PTOSError(f"Query '{name}' not found")

    effective_time = time or q.get("time", "tm")

    raw_where = q.get("where")
    if isinstance(raw_where, list):
        # old array format — convert to single expression
        expr = ptos._filters_to_expr(raw_where)
        filters = [expr] if expr else []
    elif isinstance(raw_where, str) and raw_where.strip():
        filters = [raw_where]
    else:
        filters = []

    effective_search = q.get("search") or None
    where_expr = filters[0] if filters else ""

    if "group" in q:
        result = get_group(filters, effective_time, q["group"],
                           sum_field=q.get("sum_field"))
        result["kind"]       = "group"
        result["query_name"] = name
        result["where_expr"] = where_expr
        result["query_time"] = q.get("time", "tm")
        result["query_group"] = q.get("group")
        result["query_sort"] = q.get("sort")
        result["query_sum"] = q.get("sum")
        result["query_search"] = q.get("search")
        return result

    if "pivot" in q and len(q["pivot"]) >= 2:
        result = get_pivot(filters, effective_time,
                           q["pivot"][0], q["pivot"][1],
                           count_mode=q.get("count", False),
                           sort_col=q.get("sort"))
        result["kind"]       = "pivot"
        result["query_name"] = name
        result["where_expr"] = where_expr
        result["query_time"] = q.get("time", "tm")
        result["query_pivot"] = q.get("pivot")
        result["query_sort"] = q.get("sort")
        result["query_sum"] = q.get("sum")
        result["query_search"] = q.get("search")
        return result

    if "trend" in q:
        result = get_trend(filters, effective_time, int(q["trend"]))
        result["kind"]       = "trend"
        result["query_name"] = name
        result["where_expr"] = where_expr
        result["query_time"] = q.get("time", "tm")
        result["query_trend"] = q.get("trend")
        result["query_sum"] = q.get("sum")
        return result

    result = get_records(filters, effective_time, search=effective_search)
    result["kind"]       = "records"
    result["query_name"] = name
    result["where_expr"] = where_expr
    result["query_time"] = q.get("time", "tm")
    result["query_sort"] = q.get("sort")
    result["query_sum"] = q.get("sum")
    result["query_search"] = q.get("search")
    return result


# ══════════════════════════════════════════════════════════════════════════════
# Save query
# ══════════════════════════════════════════════════════════════════════════════

def save_query(name, where_expr, time="tm", group=None, search=None,
               pivot=None, count=False, sort=None, trend=None, overwrite=False):
    """Save a named query to queries.toml in unified expression format.

    where_expr: a single expression string already in canonical form,
                e.g. "type=expense AND domain!=work"
                Callers should use ptos._filters_to_expr() to build this
                from a list of conditions if needed.

    Returns: {"ok": True, "name": name}
    Raises:  PTOSError on failure or name conflict (when overwrite=False).
    """
    import re as _re
    name = name.strip().replace(" ", "_").lower()
    if not name:
        raise PTOSError("Query name cannot be empty")
    if not _re.match(r'^[a-z0-9_]+$', name):
        raise PTOSError("Name must be lowercase letters, numbers and underscores only")

    try:
        queries = ptos.get_queries()
    except PTOSError:
        queries = {}

    if name in queries and not overwrite:
        raise PTOSError(f"Query '{name}' already exists in queries.toml")

    lines = [f"\n[{name}]"]

    if where_expr and where_expr.strip():
        val = where_expr.strip().replace('"', '\\"')
        lines.append(f'where = "{val}"')

    lines.append(f'time  = "{time}"')

    if group:
        items = ", ".join(f'"{g}"' for g in (group if isinstance(group, list) else [group]))
        lines.append(f"group = [{items}]")

    if sort:
        lines.append(f'sort = "{sort}"')

    if search:
        lines.append(f'search = "{search}"')

    if pivot and len(pivot) >= 2:
        items = ", ".join(f'"{p}"' for p in pivot)
        lines.append(f"pivot = [{items}]")
        if count:
            lines.append("count = true")

    if trend is not None:
        lines.append(f"trend = {trend}")

    ptos._backup_file(ptos.QUERIES_PATH)
    with open(ptos.QUERIES_PATH, "a", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    ptos._CACHE.pop("queries", None)   # invalidate cache

    return {"ok": True, "name": name}


# ══════════════════════════════════════════════════════════════════════════════
# Edit / Delete
# ══════════════════════════════════════════════════════════════════════════════

def find_records(filters, time="all", search=None):
    """Find records matching filters + time + search.
    Returns list of {filepath, filename, line, parsed} dicts.
    parsed is a flat dict of the record fields for display.
    """
    try:
        start, end = _resolve_time(time)
    except PTOSError:
        start, end = __import__("datetime").date.min, __import__("datetime").date.max

    matches = ptos.find_records_with_location(filters, search=search,
                                               start=start, end=end)
    results = []
    for filepath, _idx, line in matches:
        row = _parse_record(line)
        results.append({
            "filepath": filepath,
            "filename": os.path.basename(filepath),
            "line":     line,
            "parsed":   row or {},
        })
    return results


def edit_record(filepath, old_line, set_args=None, new_note=None, lineno=None):
    """Apply --set changes and/or note replacement to one record.
    lineno: 0-based file line index for precise targeting (handles duplicates).
    Returns {"old_line", "new_line", "changed_date"} or raises PTOSError.
    """
    try:
        new_line, changed_date = ptos.apply_set(old_line, set_args or [], new_note)
    except SystemExit as e:
        raise PTOSError(str(e))
    except Exception as e:
        raise PTOSError(str(e))

    if new_line == old_line:
        raise PTOSError("No changes — new record is identical to old.")

    try:
        if changed_date:
            import os as _os
            old_year = _os.path.basename(filepath)[:4]
            new_year = changed_date[:4]
            ptos.rewrite_line_in_file(filepath, old_line, None, lineno=lineno)
            new_path = _os.path.join(ptos.RECORDS_DIR, f"{new_year}.log")
            # Read existing and append atomically
            existing = ""
            if _os.path.exists(new_path):
                with open(new_path, "r", encoding="utf-8") as f:
                    existing = f.read()
            content = existing.rstrip() + "\n" + new_line + "\n"
            write_file(new_path, content)
        else:
            ptos.rewrite_line_in_file(filepath, old_line, new_line, lineno=lineno)
    except ValueError as e:
        raise PTOSError(str(e))
    except Exception as e:
        raise PTOSError(str(e))

    return {"old_line": old_line, "new_line": new_line,
            "changed_date": changed_date}


def delete_record(filepath, old_line, lineno=None):
    """Delete one record line from its log file.
    lineno: 0-based file line index for precise targeting (handles duplicates).
    Returns {"deleted_line"} or raises PTOSError.
    """
    try:
        ptos.rewrite_line_in_file(filepath, old_line, None, lineno=lineno)
    except ValueError as e:
        raise PTOSError(str(e))
    except Exception as e:
        raise PTOSError(str(e))
    return {"deleted_line": old_line}


def restore_config(zip_path):
    """Restore config from a backup zip file.
    Validates contents, backs up current config first, then restores atomically.
    """
    import zipfile
    import uuid
    import shutil
    
    if not os.path.exists(zip_path):
        raise PTOSError(f"Backup file not found: {zip_path}")
    
    # Validate zip contents and check for path traversal
    try:
        base_dir = os.path.abspath(ptos.BASE_DIR)
        with zipfile.ZipFile(zip_path, "r") as zf:
            names = zf.namelist()
            for name in names:
                # Check that only config folder files are present
                if not name.startswith("config/") or not name.endswith(".toml"):
                    raise PTOSError(f"Invalid config backup: '{name}' is not a valid config file")
                # Prevent zip slip (path traversal)
                resolved_path = os.path.abspath(os.path.join(base_dir, name))
                if not resolved_path.startswith(base_dir + os.sep):
                    raise PTOSError(f"Invalid path in backup: {name}")
    except zipfile.BadZipFile:
        raise PTOSError("Invalid zip file")
    
    # Backup current config first - abort if this fails
    try:
        current_backup = ptos.backup_config()
    except Exception as e:
        raise PTOSError(f"Failed to create backup before restore: {e}")
    
    # Restore config atomically using temp directory
    temp_dir = os.path.join(ptos.BACKUP_DIR, f".config-restore-{uuid.uuid4().hex[:8]}")
    config_path = os.path.join(ptos.BASE_DIR, "config")
    
    try:
        # Extract to temp directory
        os.makedirs(temp_dir)
        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extractall(temp_dir)
        
        # Verify extraction
        temp_config = os.path.join(temp_dir, "config")
        if not os.path.isdir(temp_config):
            raise PTOSError("Invalid backup: config folder not found after extraction")
        
        # Atomic swap with rollback: backup to config.bak, copy new, cleanup on success
        config_bak = config_path + ".bak"
        
        # Backup existing config to config.bak
        if os.path.exists(config_path):
            if os.path.exists(config_bak):
                shutil.rmtree(config_bak)
            os.rename(config_path, config_bak)
        
        # Copy new config
        try:
            shutil.copytree(temp_config, config_path)
        except Exception:
            # Rollback: restore config.bak
            if os.path.exists(config_bak):
                if os.path.exists(config_path):
                    shutil.rmtree(config_path)
                os.rename(config_bak, config_path)
            raise
        
        # Success: delete config.bak
        if os.path.exists(config_bak):
            shutil.rmtree(config_bak)
        
        # Cleanup temp
        shutil.rmtree(temp_dir)
        
    except Exception as e:
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir)
        raise PTOSError(f"Failed to restore config: {e}")
    
    # Invalidate caches
    for key in ("schema", "config", "queries", "presets", "derived_fields", "numeric_fields"):
        ptos._CACHE.pop(key, None)
    
    return {"ok": True, "message": "Config restored successfully"}


# ══════════════════════════════════════════════════════════════════════════════
# Display helpers
# ══════════════════════════════════════════════════════════════════════════════

def fmt_date(date_obj):
    """Format date object according to configured format.
    
    Supports presets: indian (dd/mm/yyyy), us (mm/dd/yyyy), 
    eu (dd.mm.yyyy), readable (15 Apr 2026), iso (yyyy-mm-dd),
    or custom strftime pattern.
    """
    import datetime as dt
    cfg = get_config()
    fmt = cfg.get("display", {}).get("date_format", "indian")
    
    if fmt == "indian":
        return date_obj.strftime("%d/%m/%Y")
    elif fmt == "us":
        return date_obj.strftime("%m/%d/%Y")
    elif fmt == "eu":
        return date_obj.strftime("%d.%m.%Y")
    elif fmt == "readable":
        return date_obj.strftime("%d %b %Y")
    elif fmt == "iso":
        if isinstance(date_obj, dt.date):
            return date_obj.isoformat()
        else:
            return date_obj.strftime("%Y-%m-%d")
    else:
        # Custom strftime format
        try:
            return date_obj.strftime(fmt)
        except (ValueError, AttributeError):
            # Fallback to ISO format on error
            if isinstance(date_obj, dt.date):
                return date_obj.isoformat()
            else:
                return date_obj.strftime("%Y-%m-%d")


def fmt_datetime(dt_obj):
    """Format datetime object: date part uses configured format, time stays HH:MM."""
    return f"{fmt_date(dt_obj)} {dt_obj.strftime('%H:%M')}"


# ══════════════════════════════════════════════════════════════════════════════
# Lint (service layer wrappers)
# ══════════════════════════════════════════════════════════════════════

def lint_all():
    """Lint all records and return structured data.
    
    Returns:
        dict: Lint results including errors, warnings, quality warnings, and counts.
    """
    return ptos.lint_all_records()


def validate_content(content):
    """Validate raw log file content.
    
    Args:
        content: String content of a log file.
    
    Returns:
        dict: Validation results with errors list.
    """
    errors = []
    for lineno, raw_line in enumerate(content.split("\n"), 1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        try:
            d, kv, note = ptos.parse_line(line)
        except Exception:
            errors.append({
                "line": line,
                "problems": ["cannot parse line"],
                "lineno": lineno
            })
            continue
        
        line_errors = []
        if d == dt.date.min:
            line_errors.append("missing or malformed date")
        if "type" not in kv:
            line_errors.append("missing type field")
        
        schema = ptos.get_schema()
        schema_problems = ptos.validate_record(schema, kv)
        line_errors.extend(schema_problems)
        
        if line_errors:
            errors.append({
                "line": line,
                "problems": line_errors,
                "lineno": lineno
            })
    
    return {
        "valid": len(errors) == 0,
        "error_count": len(errors),
        "errors": errors
    }


def lint_content_with_schema(content, schema_override=None):
    """Lint content against a specific schema (for schema builder preview).
    
    Args:
        content: String content to lint.
        schema_override: Optional schema dict to use instead of current schema.
    
    Returns:
        dict: Lint results with errors and quality warnings.
    """
    schema = schema_override if schema_override is not None else ptos.get_schema()
    errors = []
    warnings = []
    quality_warnings = []
    
    for lineno, raw_line in enumerate(content.split("\n"), 1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        try:
            d, kv, note = ptos.parse_line(line)
        except Exception:
            errors.append({
                "line": line,
                "problems": ["cannot parse line"],
                "lineno": lineno
            })
            continue
        
        line_errors = []
        line_quality = []
        
        if d == dt.date.min:
            line_errors.append("missing or malformed date")
        if "type" not in kv:
            line_errors.append("missing type field")
        if "tag" not in kv:
            line_quality.append("no tag")
        if not note or not note.strip():
            line_quality.append("no note")
        
        schema_problems = ptos.validate_record(schema, kv)
        line_errors.extend(schema_problems)
        
        if line_errors:
            errors.append({
                "line": line,
                "problems": line_errors,
                "lineno": lineno
            })
        
        if line_quality:
            quality_warnings.append({
                "line": line,
                "problems": line_quality,
                "lineno": lineno
            })
    
    return {
        "clean": len(errors) == 0 and len(quality_warnings) == 0,
        "error_count": len(errors),
        "quality_warning_count": len(quality_warnings),
        "errors": errors,
        "quality_warnings": quality_warnings,
    }


# ══════════════════════════════════════════════════════════════════════════════
# Engine wrapper functions (for web layer)
# ══════════════════════════════════════════════════════════════════════

def resolve_options(schema, type_schema, field):
    """Get options for a field from schema."""
    return ptos.resolve_options(schema, type_schema, field)


def resolve_options_for_value(type_schema, field, parent_value):
    """Get options for a field based on parent field value."""
    return ptos.resolve_options_for_value(type_schema, field, parent_value)


def resolve_tags(schema, type_schema, record):
    """Get available tags for a record based on current field values."""
    return ptos.resolve_tags(schema, type_schema, record)


def validate_record(schema, record):
    """Validate a record against schema. Returns list of problems."""
    try:
        return ptos.validate_record(schema, record)
    except Exception as e:
        raise PTOSError(str(e))


def build_record_line(date, record, note=None):
    """Build a record line string from date, record dict, and optional note."""
    try:
        return ptos.build_record_line(date, record, note)
    except Exception as e:
        raise PTOSError(str(e))


def _backup_file(path):
    """Backup a file before modification."""
    try:
        return ptos._backup_file(path)
    except Exception as e:
        raise PTOSError(str(e))


def get_global_fields(schema):
    """Get list of global optional field names."""
    return ptos.get_global_fields(schema)


def get_log_files():
    """Get list of record log files."""
    return ptos.get_log_files()


def safe_parse_line(line):
    """Safely parse a record line. Returns (date, kv_dict, note) or None."""
    return ptos.safe_parse_line(line)


def _filters_to_expr(filters):
    """Convert list of where clauses to expression string."""
    return ptos._filters_to_expr(filters)


def non_dimension_fields():
    """Get list of non-dimension field names."""
    return ptos.non_dimension_fields()


def get_today_journal():
    """Get path to today's journal template."""
    return ptos.get_today_journal()


def save_as_preset(name, record, note=None):
    """Save a record as a preset."""
    try:
        return ptos.save_as_preset(name, record, note)
    except Exception as e:
        raise PTOSError(str(e))


def get_backup_config():
    """Get backup configuration."""
    return ptos.get_backup_config()


def backup_if_needed():
    """Create backup if there are changes since last backup."""
    try:
        return ptos.backup_if_needed()
    except Exception as e:
        raise PTOSError(str(e))


def invalidate_cache(keys):
    """Invalidate internal cache entries.
    
    Args:
        keys: Single key string or list of keys to invalidate.
    """
    if isinstance(keys, str):
        keys = [keys]
    for key in keys:
        ptos._CACHE.pop(key, None)


def check_backup_folders():
    """Check if all required backup folders exist. Returns (all_exist, missing_list)."""
    return ptos.check_backup_folders()


def atomic_write(filepath, content):
    """Write content to file atomically."""
    try:
        return ptos.atomic_write(filepath, content)
    except Exception as e:
        raise PTOSError(str(e))


def get_queries():
    """Get queries configuration."""
    return ptos.get_queries()

