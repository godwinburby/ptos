"""
ptos_service.py  —  Service layer for PTOS
==========================================
This layer orchestrates between web (HTTP) and engine (file I/O).
Returns dicts/lists instead of printing. Zero UI knowledge.

API CONTRACT:
-------------
Public functions should accept/return business objects, not file concepts.
DO NOT expose in public API: filepath, lineno, raw_line, old_line

Public API:
- get_schema() → dict
- get_records(filters, time, search) → List[dict]
- edit_record(context, changes, note) → result  
- append_record(record) → result
- get_dashboard(), get_metric(), get_due() → business objects

Used by ptos_web.py (Flask).
ptos.py CLI is unchanged and does not use this file.
"""

import sys
import os
import re
import glob
import datetime as dt
import dataclasses

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# ── patch sys.exit BEFORE importing ptos so it never kills the process ────────

def _disp(s):
    """Convert underscore-separated value to space-separated for display only."""
    return str(s).replace("_", " ") if s is not None else ""


def _safe_exit(msg=""):
    raise PTOSError(str(msg))

# _safe_exit is installed per-request in ptos_web.py via before_request/teardown_request
# ─────────────────────────────────────────────────────────────────────────────

import ptos

PTOSError = ptos.PTOSError


# ══════════════════════════════════════════════════════════════════════
# Path constants (read-only aliases to engine paths)
# ══════════════════════════════════════════════════════════════════════

JOURNAL_DIR = ptos.JOURNAL_DIR
RECORDS_DIR = ptos.RECORDS_DIR
BACKUP_DIR = ptos.BACKUP_DIR
BASE_DIR = ptos.BASE_DIR
SCHEMA_PATH = ptos.SCHEMA_PATH
QUERIES_PATH = ptos.QUERIES_PATH


# ══════════════════════════════════════════════════════════════════════════════
# Internal wrappers for engine file operations
# Centralizes file I/O for easier future changes
# ══════════════════════════════════════════════════════════════════════════════

def _update_record_in_file(filepath, old_line, new_line, lineno):
    """Update record in file - wraps engine file operations.
    
    Args:
        filepath: Path to the record file
        old_line: Original record line
        new_line: New record line (or None to delete)
        lineno: Line number for precise targeting
    """
    ptos.rewrite_line_in_file(filepath, old_line, new_line, lineno=lineno)


# ── Cache manager ────────────────────────────────────────────────────────────
# Each resource maps to its cache key + dependent keys invalidated together.

_CACHE_MAP = {
    "schema":   ["schema", "derived_fields", "numeric_fields", "datetime_fields"],
    "queries":  ["queries"],
    "config":   ["config"],
    "presets":  ["presets"],
}


def invalidate(resource):
    """Invalidate cache for a resource and all its dependents.
    
    Args:
        resource: One of "schema", "queries", "config", "presets",
                  or a list/tuple of such keys.
    """
    if isinstance(resource, str):
        resource = [resource]
    keys = set()
    for r in resource:
        keys.update(_CACHE_MAP.get(r, [r]))
    for key in keys:
        ptos._CACHE.pop(key, None)


def invalidate_all():
    """Invalidate every cached resource (e.g. after restore)."""
    for key in list(ptos._CACHE.keys()):
        ptos._CACHE.pop(key, None)


def invalidate_cache(keys):
    """Backwards-compatible wrapper. Prefer invalidate() for new code."""
    invalidate(keys)


def _invalidate_history_cache():
    """Invalidate every history/conditional-suggestion/habit/calendar cache key.

    Called after any record write (or schema change) regardless of which
    rtype changed — correctness over precision: writes are rare compared
    to cascade reads, and selectively invalidating individual condsug keys
    risks missing one and serving stale suggestions."""
    for key in list(ptos._CACHE.keys()):
        if (key.startswith("history:") or key.startswith("condsug:")
                or key.startswith("habit:") or key.startswith("calendar:")):
            ptos._CACHE.pop(key, None)


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
    _dt_fields = set(ptos.datetime_fields())
    for k, v in kv.items():
        raw = ", ".join(v) if isinstance(v, list) else str(v)
        if k in _dt_fields and raw:
            try:
                import datetime as _dt_mod
                parsed_dt = _dt_mod.datetime.fromisoformat(raw)
                row[k] = parsed_dt.strftime("%d-%b-%Y %H:%M")
            except (ValueError, TypeError):
                row[k] = _disp(raw)
        else:
            row[k] = _disp(raw)
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


def save_config(config_dict):
    """Save PTOS configuration atomically with backup.
    
    Args:
        config_dict: Configuration dict to save to config.toml.
    
    Returns:
        dict: Result with ok and message.
    """
    try:
        import tomli_w
        os.makedirs(os.path.dirname(ptos.CONFIG_PATH), exist_ok=True)
        with ptos.AtomicWrite(ptos.CONFIG_PATH, "config") as w:
            tomli_w.dump(config_dict, w.stream)
        return {"ok": True, "message": "Settings saved"}
    except Exception as e:
        return {"ok": False, "message": str(e)}


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
        result = ptos.append_record(line)
        _invalidate_history_cache()
        return result
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

def _build_history_suggestions(rtype):
    """Scan all records of the given type and aggregate suggestion data.
    Expensive part (full file scan) — cached by get_history_suggestions.
    Returns a dict with the scan-derived aggregates; filtered_tags is
    computed per-call by _apply_context_filter since it depends on the
    per-request context_record."""
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
        return {"tags": [], "field_values": {}, "field_defaults": {}, "tags_by_field_value": {}}

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

    return {
        "tags":                sorted(tag_set),
        "field_values":        field_values,
        "field_defaults":      field_defaults,
        "tags_by_field_value": tags_by_field_value,
    }


def _apply_context_filter(tags_by_field_value, rtype, context_record):
    """Compute filtered_tags for one context_record from cached aggregates.
    Cheap per-call step (schema is itself cached) — run fresh on every
    call so the context-specific result is never shared across requests."""
    try:
        schema      = ptos.get_schema()
        type_schema = schema.get("type", {}).get(rtype, {})
    except Exception:
        schema = {}
        type_schema = {}

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

    return filtered_tags


def get_history_suggestions(rtype, context_record=None):
    """Scan all records of the given type and return:
      tags: sorted list of all tags ever used for this type
      filtered_tags: tags filtered by context_record's field cascade (schema + history based)
      field_values: {fieldname: [values by freq]} for free-text fields
      field_defaults: {fieldname: most_common_value} for schema option fields
                      (used to pre-select the most likely value on type selection)

    If context_record is provided, filtered_tags includes:
    1. Schema-defined tags from resolve_tags() based on context field values
    2. Historical tags that appeared in past records with matching field values

    The expensive full-file scan is cached per rtype (key history:{rtype});
    the context-dependent filter is re-run cheaply on every call since
    context_record varies per request and the aggregates are already built.
    """
    cache_key = f"history:{rtype}"
    cached = ptos._CACHE.get(cache_key)
    if cached is None:
        cached = _build_history_suggestions(rtype)
        ptos._CACHE[cache_key] = cached

    filtered_tags = _apply_context_filter(cached["tags_by_field_value"], rtype, context_record)

    return {
        "tags":           cached["tags"],
        "filtered_tags":  sorted(filtered_tags),
        "field_values":   cached["field_values"],
        "field_defaults": cached["field_defaults"],
    }


def get_conditional_suggestions(rtype, field, value):
    """Given a known field=value, return the most common value for every
    other schema-option field across matching history records.
    Used for cascade pre-fill: user picks source=mgm → suggest booked_by=cso.
    Returns: {fieldname: most_common_value}
    Fully cacheable per (rtype, field, value) — invalidated on any record
    write via _invalidate_history_cache.
    """
    cache_key = f"condsug:{rtype}:{field}:{value}"
    cached = ptos._CACHE.get(cache_key)
    if cached is not None:
        return cached

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

    result = {
        k: counter.most_common(1)[0][0]
        for k, counter in field_counts.items()
        if counter
    }
    ptos._CACHE[cache_key] = result
    return result


# ══════════════════════════════════════════════════════════════════════════════
def get_records(filters, time="tm", search=None, sort=None,
                from_file=None, sum_field=None, select=None,
                from_date=None, to_date=None):
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
        if from_date:
            start = ptos.parse_from_to(from_date)
            end = ptos.parse_from_to(to_date, as_end=True) if to_date else dt.date.max
            time_label = "From " + (from_date or "…") + (" to " + to_date if to_date else "")
        else:
            start, end = _resolve_time(time)
            time_label = ptos._TIME_ALIASES.get(time, time)
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
            # date is in p[0], other fields in p[1]
            if sort == "date":
                return (0, p[0], "")
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
              sum_field=None, from_file=None,
              from_date=None, to_date=None):
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
        if from_date:
            start = ptos.parse_from_to(from_date)
            end = ptos.parse_from_to(to_date, as_end=True) if to_date else dt.date.max
            time_label = "From " + (from_date or "…") + (" to " + to_date if to_date else "")
        else:
            start, end = _resolve_time(time)
            time_label = ptos._TIME_ALIASES.get(time, time)
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
        label = "  ".join(_disp(k) for k in key) if isinstance(key, tuple) else _disp(key)
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
        "time_label":      time_label,
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
        r = {"label": _disp(row_label)}
        for c in cols:
            val = table[row_label].get(c, 0)
            r[_disp(c)]    = val
            row_total      += val
            col_totals[c]  += val
        r["total"] = row_total
        grand     += row_total
        rows.append(r)

    return {
        "cols":        [_disp(c) for c in cols],
        "rows":        rows,
        "col_totals":  {_disp(k): v for k, v in col_totals.items()},
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

def get_metric(name, time="tm", from_date=None, to_date=None):
    """
    Returns:
      { name: str, value: str, raw: float|int|None }
    """
    try:
        queries = ptos.get_queries()
        cycles  = _cycles()
        if from_date:
            start = ptos.parse_from_to(from_date)
            end = ptos.parse_from_to(to_date, as_end=True) if to_date else dt.date.max
        else:
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
            def _resolve(op):
                if op in metrics:
                    dep = metrics[op]
                    if "sum" in dep:
                        _, t = ptos._run_base_query(dep["sum"], queries, start, end, cycles,
                                                    sum_field=dep.get("field"))
                        return t
                    elif "avg" in dep:
                        cnt, total = ptos._run_base_query(dep["avg"], queries, start, end, cycles)
                        return (total / cnt) if cnt else 0
                    elif "ratio" in dep:
                        v1 = _resolve(dep["ratio"][0])
                        v2 = _resolve(dep["ratio"][1])
                        return (v1 / v2 * 100) if v2 else 0
                # base query — return count
                c, _ = ptos._run_base_query(op, queries, start, end, cycles)
                return c
            v1 = _resolve(q1 := m["ratio"][0])
            v2 = _resolve(q2 := m["ratio"][1])
            if v2 == 0:
                return {"name": _disp(name), "value": "no data", "raw": None}
            raw = (v1 / v2) * 100
            return {"name": _disp(name), "value": f"{raw:.1f}%  ({v1:.0f}/{v2:.0f})", "raw": raw}

        if "sum" in m:
            _, total = ptos._run_base_query(m["sum"], queries, start, end, cycles,
                                            sum_field=m.get("field"))
            return {"name": _disp(name), "value": ptos.fmt(total), "raw": total}

        if "avg" in m:
            unit_field = m.get("unit_field")
            unit_weights = m.get("unit_weights")
            if unit_field and unit_weights:
                lines, total = ptos._run_base_query_lines(m["avg"], queries, start, end, cycles)
                if not lines:
                    return {"name": _disp(name), "value": "no data", "raw": None}
                units = 0
                for line in lines:
                    kv = (ptos.safe_parse_line(line) or (None, {}, None))[1]
                    val = kv.get(unit_field, "")
                    if isinstance(val, list):
                        val = val[0]
                    units += unit_weights.get(val, 1)
                raw = total / units if units else 0
                return {"name": _disp(name), "value": ptos.fmt_avg(raw), "raw": raw}
            else:
                cnt, total = ptos._run_base_query(m["avg"], queries, start, end, cycles)
                if cnt == 0:
                    return {"name": _disp(name), "value": "no data", "raw": None}
                raw = total / cnt
                return {"name": _disp(name), "value": ptos.fmt_avg(raw), "raw": raw}

        if "max" in m or "min" in m:
            key = "max" if "max" in m else "min"
            lines, _ = ptos._run_base_query_lines(m[key], queries, start, end, cycles)
            values = [ptos.numeric_value(
                (ptos.safe_parse_line(l) or (None,{},None))[1])
                for l in lines]
            values = [v for v in values if v is not None]
            if not values:
                return {"name": _disp(name), "value": "no data", "raw": None}
            raw = max(values) if key == "max" else min(values)
            return {"name": _disp(name), "value": ptos.fmt(raw), "raw": raw}

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
                    # Use dependency metric's own time window
                    dep_time = dep_m.get("time", "tm")
                    dep_start, dep_end = ptos.resolve_time(dep_time, cycles)
                    if "sum" in dep_m:
                        _, val = ptos._run_base_query(dep_m["sum"], queries, dep_start, dep_end, cycles,
                                                      sum_field=dep_m.get("field"))
                    elif "ratio" in dep_m:
                        dq1, dq2 = dep_m["ratio"][0], dep_m["ratio"][1]
                        def _res(op):
                            if op in metrics:
                                dm = metrics[op]
                                # Use sub-metric's own time
                                dm_time = dm.get("time", "tm")
                                dm_start, dm_end = ptos.resolve_time(dm_time, cycles)
                                if "sum" in dm:
                                    _, t = ptos._run_base_query(dm["sum"], queries, dm_start, dm_end, cycles,
                                                               sum_field=dm.get("field"))
                                    return t
                            c, _ = ptos._run_base_query(op, queries, start, end, cycles)
                            return c
                        dc1, dc2 = _res(dq1), _res(dq2)
                        val = (dc1 / dc2 * 100) if dc2 else 0
                    elif "avg" in dep_m:
                        cnt, total = ptos._run_base_query(dep_m["avg"], queries, dep_start, dep_end, cycles)
                        val = (total / cnt) if cnt else 0
                    elif "max" in dep_m or "min" in dep_m:
                        key2 = "max" if "max" in dep_m else "min"
                        dep_lines, _ = ptos._run_base_query_lines(dep_m[key2], queries, dep_start, dep_end, cycles)
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
                    # Use query's own time window
                    q_time = q_resolved.get("time", "tm") if isinstance(q_resolved, dict) else "tm"
                    q_start, q_end = ptos.resolve_time(q_time, cycles)
                    if isinstance(q_resolved, dict) and "where" in q_resolved:
                        _, val = ptos._run_base_query(query_name, queries, q_start, q_end, cycles)
                    else:
                        val = 0
                    resolved[token] = val
            # substitute resolved names with numeric values
            # Handle special tokens for date/day arithmetic
            import calendar as _cal
            
            now = dt.date.today()
            
            # Default values (month-based)
            month_days = _cal.monthrange(now.year, now.month)[1]
            month_day = now.day
            
            # Try to use first configured cycle
            cycle_start_day = None
            for _name, day in cycles.items():
                cycle_start_day = day
                break  # Use first cycle defined
            
            if cycle_start_day:
                # Calculate cycle start date
                if now.day >= cycle_start_day:
                    cycle_start = dt.date(now.year, now.month, cycle_start_day)
                else:
                    prev = now.replace(day=1) - dt.timedelta(days=1)
                    cycle_start = dt.date(prev.year, prev.month, cycle_start_day)
                
                # Calculate cycle end (start of next cycle)
                next_month = cycle_start.replace(day=28) + dt.timedelta(days=4)
                next_cycle_start = next_month.replace(day=cycle_start_day)
                cycle_end = next_cycle_start - dt.timedelta(days=1)
                
                cycle_days = (cycle_end - cycle_start).days + 1
                cycle_day = (now - cycle_start).days + 1  # 1-indexed
            else:
                # No cycle defined, use month
                cycle_days = month_days
                cycle_day = month_day
            
            # Add special tokens to resolved dict
            resolved['cycle_day'] = cycle_day
            resolved['cycle_days'] = cycle_days
            resolved['month_day'] = month_day
            resolved['month_days'] = month_days
            
            eval_expr = expr
            for token, val in resolved.items():
                eval_expr = _re.sub(rf'\b{token}\b', str(val), eval_expr)
            
            # safe eval — only digits, spaces, and arithmetic operators (including scientific notation e)
            if not _re.match(r'^[\d\s\.+\-*/()e]+$', eval_expr):
                return {"name": _disp(name), "value": f"unsafe expression: {eval_expr}", "raw": None}
            try:
                raw = float(eval(eval_expr))  # noqa: S307
                formatted = ptos.fmt(int(raw)) if raw == int(raw) else ptos.fmt_avg(raw)
                return {"name": _disp(name), "value": formatted, "raw": raw}
            except Exception as e:
                return {"name": _disp(name), "value": f"eval error: {e}", "raw": None}
            
    except Exception as e:
        return {"name": _disp(name), "value": f"error: {e}", "raw": None}
    
    return {"name": _disp(name), "value": "?", "raw": None}


# ══════════════════════════════════════════════════════════════════════════════
# Thresholds
# ══════════════════════════════════════════════════════════════════════════════

def _resolve_value(ref_name, threshold_cfg, time="tm", from_date=None, to_date=None):
    """Resolve a metric or query name to a numeric value.
    Used by get_threshold_status() for both the metric and the target value."""
    queries = ptos.get_queries()
    metrics = queries.get("metrics", {})
    if ref_name in metrics:
        result = get_metric(ref_name, time=time, from_date=from_date, to_date=to_date)
        return result["raw"]
    reserved = {"metrics", "dashboards", "due"}
    q = None
    if ref_name in queries.get("queries", {}):
        q = queries["queries"][ref_name]
    elif ref_name in queries and isinstance(queries[ref_name], dict) and ref_name not in reserved:
        q = queries[ref_name]
    if q is not None:
        where = q.get("where", "") if isinstance(q, dict) else ""
        filters = [where] if where.strip() else []
        agg = threshold_cfg.get("agg", "sum")
        sum_field = threshold_cfg.get("sum_field") if agg == "sum" else None
        result = get_records(filters, time=time, from_date=from_date,
                             to_date=to_date, sum_field=sum_field)
        return result["count"] if agg == "count" else result["total"]
    raise PTOSError(f"'{ref_name}' is not a known metric or query")


def get_threshold_status(name, time=None, from_date=None, to_date=None):
    """Evaluate a single threshold and return its status.

    Returns:
      {name, raw, target, direction, pct, unit, status}
      status: ok | warning | over | met
    """
    thresholds = ptos.get_thresholds()
    t = thresholds.get(name)
    if not t:
        raise PTOSError(f"Threshold '{name}' not found")

    resolved_time = time or t.get("time", "tm")
    raw = _resolve_value(t["metric"], t, resolved_time, from_date, to_date)
    if raw is None:
        raw = 0

    target = t.get("value", 0)
    if isinstance(target, str):
        try:
            target = float(target)
        except (ValueError, TypeError):
            target = _resolve_value(target, t, resolved_time, from_date, to_date)
    if target is None:
        target = 0

    pct = (raw / target * 100) if target else 0
    direction = t.get("direction", "max")
    if direction == "max":
        status = "over" if pct >= 100 else ("warning" if pct >= 80 else "ok")
    else:
        status = "met" if pct >= 100 else ("warning" if pct < 50 else "ok")

    return {
        "name": name,
        "raw": raw,
        "target": target,
        "direction": direction,
        "pct": pct,
        "unit": t.get("unit", ""),
        "status": status,
        "agg": t.get("agg", "sum"),
        "sum_field": t.get("sum_field"),
    }


def get_all_threshold_status(time=None, from_date=None, to_date=None):
    """Return status for every configured threshold."""
    thresholds = ptos.get_thresholds()
    results = []
    for name in thresholds:
        try:
            results.append(get_threshold_status(name, time, from_date, to_date))
        except Exception:
            results.append({"name": name, "raw": 0, "target": 0,
                            "direction": "max", "pct": 0, "unit": "",
                            "status": "error"})
    return results


def get_matching_thresholds(record):
    """Return threshold names whose underlying query's where clause matches
    the given record dict. Used for live add-form feedback."""
    thresholds = ptos.get_thresholds()
    queries = ptos.get_queries()
    matches = []
    for name, t in thresholds.items():
        ref = t.get("metric", "")
        if ref in queries.get("metrics", {}):
            base = queries["metrics"][ref]
            query_name = None
            if isinstance(base, dict):
                query_name = base.get("sum") or base.get("count") or base.get("avg")
        else:
            query_name = ref
        if query_name:
            q_def = queries.get("queries", {}).get(query_name)
            if q_def is None:
                reserved = {"metrics", "dashboards", "due"}
                q_def = queries.get(query_name) if query_name not in reserved else None
            where_expr = q_def.get("where", "") if isinstance(q_def, dict) else ""
        else:
            where_expr = ""
        if where_expr and ptos.apply_where(record, [where_expr]):
            try:
                status = get_threshold_status(name)
            except Exception:
                status = {"name": name, "raw": 0, "target": 0, "direction": "max",
                          "pct": 0, "unit": "", "status": "error"}
            matches.append(status)
    return matches


# ══════════════════════════════════════════════════════════════════════════════
# Dashboard
# ══════════════════════════════════════════════════════════════════════════════

def get_dashboard(name, time="tm", use_dashboard_time=False,
                  from_date=None, to_date=None):
    """
    Returns:
      { name: str,
        period: str,
        items: [{name, value, raw}],
        groups: [{name, items}] | None }   # None when no groups configured
    
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
    if use_dashboard_time and from_date:
        db_start = ptos.parse_from_to(from_date)
        db_end = ptos.parse_from_to(to_date, as_end=True) if to_date else dt.date.max
        period_from, period_to = db_start, db_end
    elif use_dashboard_time:
        db_start, db_end = _resolve_time(time)
        period_from, period_to = db_start, db_end
    
    items = []
    group_map = {}
    group_order = []
    try:
        cfg = ptos.get_config()
        highlight_map = cfg.get("dashboard", {}).get("highlights", {}).get(name, {})
    except Exception:
        highlight_map = {}

    dashdef = dashboards[name]
    group_defs = dashdef.get("groups") or {}
    has_groups = bool(group_defs)
    ordered = []
    if has_groups:
        grouped = set()
        for gname, gitems in group_defs.items():
            if isinstance(gitems, str):
                gitems = [gitems]
            for item_name in gitems:
                ordered.append((gname, item_name))
                grouped.add(item_name)
        for item_name in dashdef.get("metrics", []):
            if item_name not in grouped:
                ordered.append((None, item_name))
    else:
        for item_name in dashdef.get("metrics", []):
            ordered.append((None, item_name))

    def _push(entry):
        items.append(entry)
        key = group_name if group_name is not None else ""
        if key not in group_map:
            group_map[key] = []
            group_order.append(key)
        group_map[key].append(entry)

    for group_name, item_name in ordered:
        metrics = queries.get("metrics", {})
        queries_dict = queries.get("queries", queries)
        
        # Determine which time to use for this item
        if use_dashboard_time:
            # Override: use dashboard's time for all
            item_start, item_end = db_start, db_end
            item_time = time
            if from_date:
                item_time = "range"
        else:
            # Use each item's own time from queries.toml, fallback to dashboard's time
            if item_name in metrics:
                # For metrics, read time from metrics section
                q = metrics.get(item_name, {})
            else:
                # For queries, read from queries section
                q = queries_dict.get(item_name, {})
            item_time = q.get("time", time)
            if from_date:
                item_start = ptos.parse_from_to(from_date)
                item_end = ptos.parse_from_to(to_date, as_end=True) if to_date else dt.date.max
                item_time = "range"
            else:
                try:
                    item_start, item_end = _resolve_time(item_time)
                except Exception:
                    item_time = "tm"
                    item_start, item_end = _resolve_time("tm")
        item_period = f"{item_start} to {item_end}"
        
        if item_name in metrics:
            item = get_metric(item_name, item_time, from_date=from_date, to_date=to_date)
            item["kind"] = "metric"
            item["item_time"] = item_time
            item["item_period"] = item_period
            if item_name in highlight_map:
                item["highlight"] = highlight_map[item_name]
            _push(item)
        elif item_name in queries_dict:
            try:
                cnt, total = ptos._run_base_query(item_name, queries, item_start, item_end, cycles)
                value = str(cnt)
                if total > 0:
                    value += f"  ({ptos.fmt(total)})"
                entry = {"name": _disp(item_name), "raw_name": item_name, "value": value, "raw": cnt,
                         "kind": "query", "item_time": item_time, "item_period": item_period}
                if item_name in highlight_map:
                    entry["highlight"] = highlight_map[item_name]
                _push(entry)
            except Exception as e:
                entry = {"name": _disp(item_name), "raw_name": item_name, "value": f"error: {e}", "raw": None,
                         "kind": "query", "item_time": item_time, "item_period": item_period}
                if item_name in highlight_map:
                    entry["highlight"] = highlight_map[item_name]
                _push(entry)
        else:
            _push({"name": _disp(item_name), "value": "not found", "raw": None,
                   "kind": "unknown", "item_time": item_time, "item_period": item_period})
    
    if from_date:
        period_from = ptos.parse_from_to(from_date)
        period_end = ptos.parse_from_to(to_date, as_end=True) if to_date else dt.date.max
    else:
        period_from, period_end = _resolve_time(time)

    groups = None
    if has_groups:
        groups = []
        if group_map.get(""):
            groups.append({"name": "", "items": group_map[""]})
        for g in group_order:
            if g != "":
                groups.append({"name": g, "items": group_map[g]})

    return {
        "name":   _disp(name),
        "period": f"{period_from} to {period_end}",
        "items":  items,
        "groups": groups,
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

def run_query(name, time=None, from_date=None, to_date=None):
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
        result = get_dashboard(name, time or "tm",
                               from_date=from_date, to_date=to_date)
        result["kind"] = "dashboard"
        return result

    if name in metrics:
        result = get_metric(name, time or "tm",
                            from_date=from_date, to_date=to_date)
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
                           sum_field=q.get("sum_field"),
                           from_date=from_date, to_date=to_date)
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

    result = get_records(filters, effective_time, search=effective_search,
                         from_date=from_date, to_date=to_date)
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
    """Save a named query to queries.toml using tomli-w.

    where_expr: a single expression string already in canonical form,
                e.g. "type=expense AND domain!=work"

    Returns: {"ok": True, "name": name}
    Raises:  PTOSError on failure or name conflict (when overwrite=False).
    """
    import re as _re
    import tomli_w
    name = name.strip().replace(" ", "_").lower()
    if not name:
        raise PTOSError("Query name cannot be empty")
    if not _re.match(r'^[a-z0-9_]+$', name):
        raise PTOSError("Name must be lowercase letters, numbers and underscores only")

    try:
        data = ptos._load("queries", ptos.QUERIES_PATH)
    except Exception:
        data = {}

    if name in data and name not in ("metrics", "dashboards", "due") and not overwrite:
        raise PTOSError(f"Query '{name}' already exists in queries.toml")

    entry = {}
    if where_expr and where_expr.strip():
        entry["where"] = where_expr.strip()
    entry["time"] = time
    if group:
        entry["group"] = group if isinstance(group, list) else [group]
    if sort:
        entry["sort"] = sort
    if search:
        entry["search"] = search
    if pivot and len(pivot) >= 2:
        entry["pivot"] = pivot
        if count:
            entry["count"] = True
    if trend is not None:
        entry["trend"] = trend

    data[name] = entry

    with ptos.AtomicWrite(ptos.QUERIES_PATH, "queries") as w:
        tomli_w.dump(data, w.stream)

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
            _update_record_in_file(filepath, old_line, None, lineno=lineno)
            new_path = _os.path.join(ptos.RECORDS_DIR, f"{new_year}.log")
            # Read existing and append atomically
            existing = ""
            if _os.path.exists(new_path):
                with open(new_path, "r", encoding="utf-8") as f:
                    existing = f.read()
            content = existing.rstrip() + "\n" + new_line + "\n"
            write_file(new_path, content)
        else:
            _update_record_in_file(filepath, old_line, new_line, lineno=lineno)
    except ValueError as e:
        raise PTOSError(str(e))
    except Exception as e:
        raise PTOSError(str(e))

    _invalidate_history_cache()
    return {"old_line": old_line, "new_line": new_line,
            "changed_date": changed_date}


def delete_record(filepath, old_line, lineno=None):
    """Delete one record line from its log file.
    lineno: 0-based file line index for precise targeting (handles duplicates).
    Returns {"deleted_line"} or raises PTOSError.
    """
    try:
        _update_record_in_file(filepath, old_line, None, lineno=lineno)
    except ValueError as e:
        raise PTOSError(str(e))
    except Exception as e:
        raise PTOSError(str(e))
    _invalidate_history_cache()
    return {"deleted_line": old_line}



def bulk_delete(records):
    """Delete multiple records.
    records: list of {filepath, line, lineno} dicts.
    Returns {deleted, errors} counts.
    """
    deleted = 0
    errors  = []
    # Group by filepath so we only backup each file once
    from collections import defaultdict
    by_file = defaultdict(list)
    for r in records:
        by_file[r["filepath"]].append(r)

    for filepath, recs in by_file.items():
        if not os.path.abspath(filepath).startswith(os.path.abspath(ptos.RECORDS_DIR)):
            errors.append(f"Invalid filepath: {filepath}")
            continue
        # Delete in reverse lineno order so indices stay valid
        sorted_recs = sorted(recs, key=lambda r: r.get("lineno", 0) or 0, reverse=True)
        for r in sorted_recs:
            try:
                _update_record_in_file(filepath, r["line"], None, lineno=r.get("lineno"))
                deleted += 1
            except Exception as e:
                errors.append(str(e))
    if deleted:
        _invalidate_history_cache()
    return {"deleted": deleted, "errors": errors}


def bulk_set(records, set_args):
    """Apply --set changes to multiple records.
    records: list of {filepath, line, lineno} dicts.
    set_args: list of "field=value" strings.
    Returns {updated, errors} counts.
    """
    updated = 0
    errors  = []
    from collections import defaultdict
    by_file = defaultdict(list)
    for r in records:
        by_file[r["filepath"]].append(r)

    for filepath, recs in by_file.items():
        if not os.path.abspath(filepath).startswith(os.path.abspath(ptos.RECORDS_DIR)):
            errors.append(f"Invalid filepath: {filepath}")
            continue
        for r in recs:
            try:
                new_line, changed_date = ptos.apply_set(r["line"], set_args, None)
                if new_line != r["line"]:
                    _update_record_in_file(filepath, r["line"], new_line,
                                           lineno=r.get("lineno"))
                    updated += 1
            except Exception as e:
                errors.append(str(e))
    if updated:
        _invalidate_history_cache()
    return {"updated": updated, "errors": errors}


def increment_preset_use(name):
    """Increment use_count for a named preset using tomllib/tomli_w.
    Adds the field if not present. Silent no-op on any error."""
    try:
        import tomli_w
        path = ptos.PRESETS_PATH
        if not os.path.exists(path):
            return
        with open(path, "rb") as f:
            try:
                import tomllib
            except ImportError:
                import tomli as tomllib
            data = tomllib.load(f)
        presets = data.get("presets", {})
        if name not in presets:
            return
        presets[name]["use_count"] = presets[name].get("use_count", 0) + 1
        data["presets"] = presets
        with ptos.AtomicWrite(path, "presets") as w:
            tomli_w.dump(data, w.stream)
    except Exception:
        pass


def get_frequent_presets(n=6):
    """Return top N single presets sorted by use_count descending.
    Remaining presets sorted alphabetically for fast scanning.
    Multi-record and alias presets excluded.
    Returns (frequent, remaining) tuple for home page display."""
    presets = ptos.get_presets()
    singles = {
        k: v for k, v in presets.items()
        if isinstance(v, dict)
        and not v.get("records")
        and not v.get("alias")
    }
    ranked = sorted(
        singles.keys(),
        key=lambda k: (-singles[k].get("use_count", 0), k)
    )
    return ranked[:n], sorted(ranked[n:])


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
    invalidate_all()

    return {"ok": True, "message": "Config restored successfully"}


# ══════════════════════════════════════════════════════════════════════════════
# Board / Kanban
# ══════════════════════════════════════════════════════════════════════════════

def get_boards():
    """Get all board configurations from queries.toml.
    Returns dict of {board_name: {columns: [...]}}."""
    try:
        queries = ptos.get_queries()
    except Exception as e:
        raise PTOSError(str(e))
    boards = {}
    for k, v in queries.items():
        if k.startswith("board.") and isinstance(v, dict):
            name = k[6:]
            cols = v.get("columns", [])
            if isinstance(cols, list) and cols:
                boards[name] = {"columns": cols}
    return boards


def get_habit_names():
    """List configured [habit.*] entries, for the /habits index page."""
    try:
        queries = ptos.get_queries()
    except Exception as e:
        raise PTOSError(str(e))
    return sorted(k.split(".", 1)[1] for k in queries if k.startswith("habit."))


def get_habit_data(habit_name):
    """Return streak + weekly presence grid for a configured habit.

    Cached per habit under key habit:{habit_name}; invalidated by
    _invalidate_history_cache() on any record write."""
    cache_key = f"habit:{habit_name}"
    cached = ptos._CACHE.get(cache_key)
    if cached is not None:
        return cached

    try:
        queries = ptos.get_queries()
    except Exception as e:
        raise PTOSError(str(e))
    cfg = queries.get(f"habit.{habit_name}")
    if not cfg or not isinstance(cfg, dict):
        raise PTOSError(f"Habit '{habit_name}' not found in queries.toml")

    filters = cfg.get("filters", [])
    if not filters:
        raise PTOSError(f"Habit '{habit_name}' has no filters defined")
    weeks = int(cfg.get("weeks", 12))

    today = dt.date.today()
    start = today - dt.timedelta(days=weeks * 7 - 1)
    matches = ptos.find_records_with_location(filters, start=start, end=today)

    days_present = set()
    for _, _, line in matches:
        try:
            d, _, _ = ptos.parse_line(line)
            days_present.add(d)
        except Exception:
            continue

    streak = 0
    cursor = today
    if today not in days_present:
        cursor = today - dt.timedelta(days=1)
    while cursor in days_present:
        streak += 1
        cursor -= dt.timedelta(days=1)

    grid = [
        {"date": str(start + dt.timedelta(days=i)),
         "present": (start + dt.timedelta(days=i)) in days_present}
        for i in range((today - start).days + 1)
    ]

    result = {
        "habit_name": habit_name,
        "streak": streak,
        "weeks": weeks,
        "grid": grid,
        "total_days": len(grid),
        "days_done": len(days_present),
    }
    ptos._CACHE[cache_key] = result
    return result


def get_calendar_names():
    """List configured [calendar.*] entries, for the /calendar index page."""
    try:
        queries = ptos.get_queries()
    except Exception as e:
        raise PTOSError(str(e))
    return sorted(k.split(".", 1)[1] for k in queries if k.startswith("calendar."))


def get_calendar_data(name, year=None, month=None):
    """Return a month grid of records for a calendar view.

    name == "__all__" renders the implicit global view (every record, no
    config entry needed); any other name must match a [calendar.*] table.
    year/month default to the initial month from the calendar's time_window
    (falling back to the current month); pass explicit values to navigate
    to a different month. Cached per (name, year, month) under key
    calendar:{name}:{year}:{month}; invalidated by _invalidate_history_cache()
    on any record write."""
    y = year
    m = month
    cache_key = f"calendar:{name}:{y}:{m}"
    cached = ptos._CACHE.get(cache_key)
    if cached is not None:
        return cached

    if name == "__all__":
        filters = []
        time_window = "this-month"
    else:
        try:
            queries = ptos.get_queries()
        except Exception as e:
            raise PTOSError(str(e))
        cfg = queries.get(f"calendar.{name}")
        if not cfg or not isinstance(cfg, dict):
            raise PTOSError(f"Calendar '{name}' not found in queries.toml")
        filters = cfg.get("filters", [])
        if not filters:
            raise PTOSError(f"Calendar '{name}' has no filters defined")
        time_window = cfg.get("time_window", "this-month")

    if y is None or m is None:
        try:
            initial = _resolve_time(time_window)[0]
        except Exception:
            initial = dt.date.today()
        y = y or initial.year
        m = m or initial.month

    import calendar as _cal
    first_weekday, days_in_month = _cal.monthrange(y, m)
    start = dt.date(y, m, 1)
    end = dt.date(y, m, days_in_month)

    matches = ptos.find_records_with_location(filters, start=start, end=end)

    by_day = {}
    for fp, idx, line in matches:
        try:
            d, kv, _ = ptos.parse_line(line)
        except Exception:
            continue
        row = _parse_record(line) or {}
        title = next((str(row[f]) for f in ("name", "client", "intent", "title", "subject")
                      if row.get(f)), "")
        if not title:
            t = kv.get("type", "")
            t = ", ".join(t) if isinstance(t, list) else str(t)
            title = f"({t})" if t else ""
        by_day.setdefault(d.day, []).append({
            "line": line,
            "title": title,
            "note": row.get("note", ""),
        })

    weeks = []
    week = [None] * first_weekday
    for day in range(1, days_in_month + 1):
        week.append({"day": day, "records": by_day.get(day, []),
                     "count": len(by_day.get(day, []))})
        if len(week) == 7:
            weeks.append(week)
            week = []
    if week:
        week += [None] * (7 - len(week))
        weeks.append(week)

    prev_m, prev_y = (12, y - 1) if m == 1 else (m - 1, y)
    next_m, next_y = (1, y + 1) if m == 12 else (m + 1, y)

    result = {
        "calendar_name": name,
        "filters": filters,
        "year": y, "month": m,
        "weeks": weeks,
        "total_records": len(matches),
        "prev": {"year": prev_y, "month": prev_m},
        "next": {"year": next_y, "month": next_m},
    }
    ptos._CACHE[cache_key] = result
    return result


def get_board_data(board_name):
    """Load record data for each column of a board.
    Returns dict mapping column type → list of parsed record dicts
    with _filepath, _lineno, _line for edit support."""
    try:
        queries = ptos.get_queries()
    except Exception as e:
        raise PTOSError(str(e))

    key = f"board.{board_name}"
    cfg = queries.get(key)
    if not cfg or not isinstance(cfg, dict):
        raise PTOSError(f"Board '{board_name}' not found in queries.toml")

    columns = cfg.get("columns", [])
    if not columns:
        raise PTOSError(f"Board '{board_name}' has no columns defined")

    schema = ptos.get_schema()
    allowed = set(schema.get("types", {}).get("allowed", []))
    for t in columns:
        if t not in allowed:
            raise PTOSError(f"Type '{t}' in board '{board_name}' is not in schema types")

    overlap = ptos.get_column_field_overlap(columns, schema)
    field_info = {}
    for t in columns:
        field_info[t] = ptos.filter_fields_for_type(t, schema)

    # Time window and limit from board config
    time_window = cfg.get("time_window", "this-month")
    if time_window == "last-3-months":
        today = dt.date.today()
        first = today.replace(day=1)
        end = today + dt.timedelta(days=365)
        start = (first - dt.timedelta(days=1)).replace(day=1)
        start = (start - dt.timedelta(days=1)).replace(day=1)
    else:
        start, end = _resolve_time(time_window)

    limit = cfg.get("limit", 0)  # 0 = no limit

    rollup_field = cfg.get("rollup_field")
    rollup_op = cfg.get("rollup_op", "count")

    result = {}
    total_by_type = {}
    truncated_by_type = {}
    rollup_by_type = {}

    for col_type in columns:
        filters = [f"type={col_type}"]
        try:
            loc_matches = ptos.find_records_with_location(filters, start=start, end=end)
        except Exception:
            loc_matches = []

        records = []
        for fp, idx, line in loc_matches:
            row = _parse_record(line)
            if not row:
                continue
            row["_filepath"] = fp
            row["_lineno"] = idx
            row["_line"] = line
            records.append(row)

        # Sort by date descending (newest first)
        records.sort(key=lambda r: r.get("date", ""), reverse=True)
        total = len(records)

        # Rollup over the full matched set, before limit truncation
        if rollup_field and rollup_field in field_info[col_type]:
            vals = []
            for r in records:
                raw = r.get(rollup_field)
                try:
                    vals.append(float(raw))
                except (TypeError, ValueError):
                    continue
            if rollup_op == "sum":
                rollup_by_type[col_type] = sum(vals)
            elif rollup_op == "avg":
                rollup_by_type[col_type] = (sum(vals) / len(vals)) if vals else None
            else:
                rollup_by_type[col_type] = len(vals)
        else:
            rollup_by_type[col_type] = None

        if limit and total > limit:
            records = records[:limit]
            truncated_by_type[col_type] = total
        result[col_type] = records
        total_by_type[col_type] = total

    card_title_fields = cfg.get("card_title_fields")
    if isinstance(card_title_fields, str):
        card_title_fields = [f.strip() for f in card_title_fields.split(",") if f.strip()]
    elif not isinstance(card_title_fields, list):
        card_title_fields = []

    return {
        "columns": columns,
        "data": result,
        "counts": total_by_type,
        "truncated": truncated_by_type,
        "time_window": time_window,
        "overlap": overlap,
        "field_info": field_info,
        "board_name": board_name,
        "card_title_fields": card_title_fields,
        "rollups": rollup_by_type,
        "rollup_op": rollup_op,
    }


def update_board_time_window(board_name, time_window):
    """Update the time_window config for a board in queries.toml.
    Validates the window before saving."""
    valid = {"td", "yd", "tw", "lw", "tm", "lm", "last-3-months", "tq", "lq", "ty", "ly", "all"}
    try:
        cycles = ptos.get_config().get("cycles", {})
    except Exception:
        cycles = {}
    for name in cycles:
        valid.add(name)
        valid.add(f"{name}-1")
    if time_window not in valid:
        raise PTOSError(f"Invalid time window '{time_window}'")
    try:
        queries = ptos.get_queries()
    except Exception as e:
        raise PTOSError(str(e))
    key = f"board.{board_name}"
    cfg = queries.get(key)
    if not cfg or not isinstance(cfg, dict):
        raise PTOSError(f"Board '{board_name}' not found in queries.toml")
    cfg["time_window"] = time_window
    import tomli_w
    with ptos.AtomicWrite(ptos.QUERIES_PATH, "queries") as w:
        tomli_w.dump(queries, w.stream)
    ptos._invalidate_all()
    return {"ok": True, "board": board_name, "time_window": time_window}


def advance_record(old_line, lineno, target_type, target_ctx_fields=None):
    """Move a record from one column/type to another.
    Creates a NEW record with today's date and target_type.
    Shared fields (common to both source and target types) are copied.
    Source record is kept unchanged.
    
    target_ctx_fields: optional dict of extra field values for the target type
                       (e.g. field values captured from the drag context).
    
    Returns dict with new record info or redirect info if fields need filling."""
    try:
        parsed = ptos.safe_parse_line(old_line)
        if not parsed:
            raise PTOSError("Could not parse source record")
        d, kv, note = parsed

        schema = ptos.get_schema()
        source_type = kv.get("type", "")
        allowed = set(schema.get("types", {}).get("allowed", []))
        if target_type not in allowed:
            raise PTOSError(f"Target type '{target_type}' is not in schema")

        # Find shared fields between source and target
        source_fields = set(ptos.filter_fields_for_type(source_type, schema))
        target_fields = set(ptos.filter_fields_for_type(target_type, schema))
        shared = source_fields & target_fields

        # Build new record
        new_kv = {"type": target_type}
        for f in shared:
            if f in ("date", "type", "note"):
                continue
            if f in kv:
                new_kv[f] = kv[f]

        # Apply any context-provided field values (override shared)
        if target_ctx_fields:
            for f, v in target_ctx_fields.items():
                new_kv[f] = v

        today_str = dt.date.today().isoformat()
        new_line = ptos.build_record_line(today_str, new_kv, note or None)

        # Check if target type has required fields not yet filled
        tdef = schema.get("type", {}).get(target_type, {})
        required = tdef.get("required", [])
        missing = [f for f in required if f not in new_kv]

        if missing:
            return {
                "ok": True,
                "target_type": target_type,
                "missing_required": missing,
                "draft": {k: v for k, v in new_kv.items() if k != "type"},
                "note": note or "",
            }

        new_filepath, new_lineno = ptos.append_record(new_line, return_position=True)
        _invalidate_history_cache()
        return {
            "ok": True,
            "new_line": new_line,
            "new_filepath": new_filepath,
            "new_lineno": new_lineno,
            "missing_required": [],
            "target_type": target_type,
        }
    except PTOSError:
        raise
    except Exception as e:
        raise PTOSError(str(e))


# ══════════════════════════════════════════════════════════════════════════════
# Query TOML management (full write)
# ══════════════════════════════════════════════════════════════════════════════

def save_queries_full(raw_queries, raw_metrics, raw_dashboards, raw_aliases=None, raw_due=None, raw_boards=None, raw_habits=None, raw_calendars=None, raw_thresholds=None):
    """Build and write queries.toml using tomli-w with atomic write.

    raw_queries:    {name: {where, time, group, search, sort, sum}}
    raw_metrics:    {name: {kind, base, base2, derived, unit_field, unit_weights, time, ...}}
    raw_dashboards: {name: {metrics: [...]}}
    raw_aliases:    {name: {alias: target}}   (optional)
    raw_due:        {config_name: {type, key, sort_by, days, exclude_results}} (optional)
    raw_boards:     {name: {columns, time_window, limit, card_title_fields, rollup_field, rollup_op}} (optional)
    raw_habits:     {name: {filters, weeks}}  (optional)
    raw_calendars:  {name: {filters, time_window}}  (optional)
    raw_thresholds: {name: {metric, agg, sum_field, value, direction, time, unit}}  (optional)

    Raises:
        PTOSError on invalid names or write failure.
    """
    import re
    import tomli_w

    if raw_aliases is None:
        raw_aliases = {}

    def _clean_bare_name(n):
        if n.startswith("board."):
            return n[6:]
        if n.startswith("calendar."):
            return n[9:]
        if n.startswith("threshold."):
            return n[10:]
        return n

    def _is_config_key(n):
        return any(n.startswith(p) for p in ("board.", "habit.", "calendar.", "due.", "threshold."))

    all_names = [n for n in (list(raw_queries) + list(raw_metrics)
                             + list(raw_dashboards) + list(raw_aliases))
                 if not _is_config_key(n)]
    board_names = list(raw_boards or {})
    calendar_names = list(raw_calendars or {})
    threshold_names = list(raw_thresholds or {})
    for n in all_names + board_names + calendar_names + threshold_names:
        bare = _clean_bare_name(n)
        if not re.match(r'^[a-z][a-z0-9_]*$', bare):
            raise PTOSError(
                f"Invalid name '{n}' — use lowercase letters, numbers, underscores")

    data = {}

    for name, q in raw_queries.items():
        if _is_config_key(name):
            continue
        entry = {}
        if q.get("where", "").strip():
            entry["where"] = q["where"].strip()
        entry["time"] = q.get("time", "tm")
        group = q.get("group")
        if group:
            entry["group"] = group if isinstance(group, list) else [group.strip()]
        if q.get("sort"):
            entry["sort"] = q["sort"] if isinstance(q["sort"], str) else str(q["sort"])
        if q.get("search"):
            entry["search"] = q["search"] if isinstance(q["search"], str) else str(q["search"])
        if q.get("sum"):
            entry["sum"] = True
        data[name] = entry

    # Metrics
    metrics = {}
    for name, m in raw_metrics.items():
        entry = {}
        kind = m.get("kind", "avg")
        base = m.get("base", "").strip()
        base2 = m.get("base2", "").strip()
        derived = m.get("derived", "").strip()
        unit_field = m.get("unit_field", "").strip()
        unit_weights = m.get("unit_weights") or {}

        if derived:
            entry["derived"] = derived
        elif kind == "ratio" and base and base2:
            entry["ratio"] = [base, base2]
        elif kind in ("avg", "sum", "max", "min") and base:
            entry[kind] = base

        if kind == "avg" and unit_field:
            entry["unit_field"] = unit_field
        if kind == "avg" and unit_weights:
            entry["unit_weights"] = unit_weights

        for k, v in (m.get("_raw") or {}).items():
            entry[k] = v

        if m.get("time"):
            entry["time"] = m["time"]

        metrics[name] = entry
    if metrics:
        data["metrics"] = metrics

    # Dashboards
    dashboards = {}
    for name, db in raw_dashboards.items():
        entry = {}
        items = db.get("metrics", [])
        if items:
            entry["metrics"] = items
        groups = db.get("groups")
        if isinstance(groups, dict) and groups:
            clean_groups = {}
            for gname, gitems in groups.items():
                if isinstance(gitems, str):
                    gitems = [gitems]
                items = [str(i) for i in gitems if str(i)]
                if gname.strip() and items:
                    clean_groups[gname.strip()] = items
            if clean_groups:
                entry["groups"] = clean_groups
        dashboards[name] = entry
    if dashboards:
        data["dashboards"] = dashboards

    # Aliases
    for name, a in (raw_aliases or {}).items():
        if _is_config_key(name):
            continue
        alias = a.get("alias", "").strip()
        if alias:
            data[name] = {"alias": alias}

    # Due configs
    all_due = raw_due if raw_due else {}
    if all_due and isinstance(all_due, dict):
        due = {}
        for due_name, due_cfg in all_due.items():
            if not due_cfg or not isinstance(due_cfg, dict):
                continue
            entry = {}
            if due_cfg.get("type"):
                entry["type"] = due_cfg["type"]
            if due_cfg.get("key"):
                entry["key"] = due_cfg["key"]
            if due_cfg.get("sort_by"):
                entry["sort_by"] = due_cfg["sort_by"]
            if due_cfg.get("days"):
                entry["days"] = due_cfg["days"]
            if due_cfg.get("exclude_results") and isinstance(due_cfg["exclude_results"], list):
                entry["exclude_results"] = due_cfg["exclude_results"]
            due[due_name] = entry
        if due:
            data["due"] = due

    # Boards
    for name, board_cfg in (raw_boards or {}).items():
        bare = _clean_bare_name(name)
        cols = board_cfg.get("columns", [])
        if not cols or not isinstance(cols, list):
            raise PTOSError(f"Board '{name}' must have a non-empty columns list")
        entry = {"columns": cols}
        if board_cfg.get("time_window"):
            entry["time_window"] = board_cfg["time_window"]
        if board_cfg.get("limit"):
            entry["limit"] = int(board_cfg["limit"])
        raw_ctf = board_cfg.get("card_title_fields")
        if raw_ctf:
            entry["card_title_fields"] = raw_ctf
        rollup_field = board_cfg.get("rollup_field")
        if rollup_field:
            schema = ptos.get_schema()
            fmeta = schema.get("fields", {}).get(rollup_field, {})
            if not fmeta.get("aggregatable"):
                raise PTOSError(
                    f"Board '{name}': rollup_field '{rollup_field}' is not aggregatable in schema")
            present = [t for t in cols if rollup_field in ptos.filter_fields_for_type(t, schema)]
            if not present:
                raise PTOSError(
                    f"Board '{name}': rollup_field '{rollup_field}' does not apply to any column type")
            entry["rollup_field"] = rollup_field
            entry["rollup_op"] = board_cfg.get("rollup_op", "count")
        data[f"board.{bare}"] = entry

    # Habits
    for name, habit_cfg in (raw_habits or {}).items():
        bare = _clean_bare_name(name)
        hfilters = habit_cfg.get("filters", [])
        if not hfilters or not isinstance(hfilters, list):
            raise PTOSError(f"Habit '{name}' must have a non-empty filters list")
        entry = {"filters": hfilters}
        if habit_cfg.get("weeks"):
            entry["weeks"] = int(habit_cfg["weeks"])
        data[f"habit.{bare}"] = entry

    # Calendars
    for name, cal_cfg in (raw_calendars or {}).items():
        bare = _clean_bare_name(name)
        cfilters = cal_cfg.get("filters", [])
        if not cfilters or not isinstance(cfilters, list):
            raise PTOSError(f"Calendar '{name}' must have a non-empty filters list")
        entry = {"filters": cfilters}
        if cal_cfg.get("time_window"):
            entry["time_window"] = cal_cfg["time_window"]
        data[f"calendar.{bare}"] = entry

    # Thresholds
    for name, thr_cfg in (raw_thresholds or {}).items():
        bare = _clean_bare_name(name)
        if not thr_cfg.get("metric", "").strip():
            raise PTOSError(f"Threshold '{name}' must have a metric")
        entry = {"metric": thr_cfg["metric"].strip()}
        if thr_cfg.get("agg", "").strip():
            entry["agg"] = thr_cfg["agg"].strip()
        if thr_cfg.get("sum_field", "").strip():
            entry["sum_field"] = thr_cfg["sum_field"].strip()
        raw_val = thr_cfg.get("value", "")
        if isinstance(raw_val, (int, float)):
            entry["value"] = raw_val
        elif isinstance(raw_val, str) and raw_val.strip():
            entry["value"] = raw_val.strip()
        entry["direction"] = thr_cfg.get("direction", "max")
        if thr_cfg.get("time", "").strip():
            entry["time"] = thr_cfg["time"].strip()
        if thr_cfg.get("unit", "").strip():
            entry["unit"] = thr_cfg["unit"].strip()
        data[f"threshold.{bare}"] = entry

    with ptos.AtomicWrite(ptos.QUERIES_PATH, "queries") as w:
        tomli_w.dump(data, w.stream)


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


def get_tag_context(rtype, record):
    """Get tag field names and their parent values for a record type.
    
    Returns a list of dicts with tag_field name and current parent_value.
    """
    try:
        schema = ptos.get_schema()
        type_schema = schema.get("type", {}).get(rtype, {})
        tag_section = type_schema.get("tags", {})
        
        result = []
        for tag_field, trigger in tag_section.items():
            parent_value = record.get(tag_field, "")
            if parent_value:
                result.append({
                    "tag_field": tag_field,
                    "parent_value": parent_value
                })
        
        return result
    except Exception as e:
        return []


def add_field_option(type_name, field_name, new_option, option_source,
                    parent_field="", parent_value="", shared_key=""):
    """Add a new option to schema.toml."""
    return ptos.add_field_option(type_name, field_name, new_option, option_source,
                                 parent_field, parent_value, shared_key)


def add_global_field_option(field_name, new_option):
    """Add a new option to a global field in schema.toml."""
    return ptos.add_global_field_option(field_name, new_option)


def add_tag_option(rtype, tag_field, parent_value, new_tag):
    """Add a new tag option to schema.toml.
    
    Args:
        rtype: Record type (e.g., 'expense', 'income')
        tag_field: The tag field name (e.g., 'category', 'source')
        parent_value: The parent value this tag belongs to (e.g., 'food', 'salary')
        new_tag: The new tag option to add
    
    Returns:
        dict: Result with success boolean and optional error message.
    """
    try:
        schema = ptos.get_schema()
        type_schema = schema.get("type", {}).get(rtype, {})
        tag_section = type_schema.get("tags", {})
        
        if tag_field not in tag_section:
            return {"success": False, "error": f"No tags section for {tag_field}"}
        
        tag_options = tag_section.get(tag_field, {}).get("options", {})
        if not isinstance(tag_options, dict):
            return {"success": False, "error": f"Tags for {tag_field} not parent-dependent"}
        
        if parent_value not in tag_options:
            return {"success": False, "error": f"Parent value '{parent_value}' not found in {tag_field} tags"}
        
        new_tag = new_tag.strip().replace(" ", "_")
        if not new_tag:
            return {"success": False, "error": "Empty tag"}
        
        if new_tag in tag_options.get(parent_value, []):
            return {"success": True, "message": f"Tag '{new_tag}' already exists"}
        
        tag_options[parent_value].append(new_tag)
        tag_options[parent_value] = sorted(tag_options[parent_value])

        # Save schema (handles backup + atomic write + cache invalidation)
        ptos._save_schema(schema)

        return {"success": True, "message": f"Added '{new_tag}' to {tag_field}.{parent_value}"}
    except Exception as e:
        raise PTOSError(str(e))


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


def save_journal(date_str, content):
    """Save journal content for a given date."""
    month_dir = os.path.join(JOURNAL_DIR, date_str[:4], date_str[5:7])
    os.makedirs(month_dir, exist_ok=True)
    write_file(os.path.join(month_dir, f"{date_str}.md"), content)


def delete_journal(date_str):
    """Delete a journal file. Cleans empty year/month dirs."""
    return ptos.delete_journal(date_str)


def svc_list_dir(rel_path=""):
    return ptos.list_dir(rel_path)


def svc_create_folder(rel_path, name):
    ptos.create_folder(rel_path, name)


def svc_create_file(rel_path, name, content):
    ptos.create_file(rel_path, name, content)


def svc_rename(rel_path, new_name):
    ptos.rename_note(rel_path, new_name)


def svc_delete(rel_path):
    ptos.delete_note_entry(rel_path)


def svc_ensure_note_id(rel_path):
    """Generate and persist an id for a note if it doesn't have one.
    Returns the id string."""
    return ptos.ensure_note_id(rel_path)


def check_note_delete_links(rel_path):
    """Check if a note (or folder of notes) has incoming backlinks.
    Returns a dict with ok=True if safe, or ok=False with warning details."""
    import fnmatch
    full = ptos._safe_path(rel_path)
    notes_to_check = []
    if os.path.isdir(full):
        for root, _, files in os.walk(full):
            for fname in files:
                if fname == "template.md" or not fname.endswith(".md"):
                    continue
                fpath = os.path.join(root, fname)
                nid = ptos._note_id_of(fpath)
                if nid:
                    bl = get_backlinks(f"note:{nid}")
                    if bl:
                        rel = os.path.relpath(fpath, ptos.NOTES_DIR).replace("\\", "/")
                        notes_to_check.append({"path": rel, "id": nid, "backlinks": bl})
    else:
        nid = ptos._note_id_of(full)
        if nid:
            bl = get_backlinks(f"note:{nid}")
            if bl:
                notes_to_check.append({"path": rel_path, "id": nid, "backlinks": bl})
    if notes_to_check:
        total = sum(len(n["backlinks"]) for n in notes_to_check)
        return {"ok": False, "warning": f"{total} incoming link(s) to {len(notes_to_check)} note(s)", "notes": notes_to_check}
    return {"ok": True}


def svc_read_file(rel_path):
    full = ptos._safe_path(rel_path)
    if not os.path.isfile(full):
        return None
    with open(full, encoding="utf-8") as f:
        return f.read()


def svc_save_file(rel_path, content):
    full = ptos._safe_path(rel_path)
    with open(full, "w", encoding="utf-8") as f:
        f.write(content)


def svc_resolve_template(rel_path):
    return ptos.resolve_new_file_template(rel_path)


def svc_parent_template(rel_path):
    return ptos.find_parent_template(rel_path)


def save_as_preset(name, record, note=None, instant=False):
    """Save a record as a preset."""
    try:
        return ptos.save_as_preset(name, record, note, instant=instant)
    except Exception as e:
        raise PTOSError(str(e))


def delete_preset(name):
    """Delete a preset by name."""
    try:
        ptos.delete_preset(name)
    except Exception as e:
        raise PTOSError(str(e))


def set_preset_instant(name, instant):
    """Set or clear the instant flag on a preset."""
    try:
        ptos.set_preset_instant(name, instant)
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


def check_backup_folders():
    """Check if all required backup folders exist. Returns (all_exist, missing_list)."""
    return ptos.check_backup_folders()


def atomic_write(filepath, content):
    """Write content to file atomically."""
    try:
        return ptos.atomic_write(filepath, content)
    except Exception as e:
        raise PTOSError(str(e))


def write_toml(filepath, data, resource=None):
    """Write a dict to a TOML file atomically, with cache invalidation.
    Wraps ptos.AtomicWrite so callers never need to import ptos directly.

    Args:
        filepath: Destination path (e.g. svc.QUERIES_PATH).
        data:     Dict to serialise as TOML.
        resource: Cache resource name to invalidate on success (e.g. "queries").
    """
    import tomli_w
    try:
        with ptos.AtomicWrite(filepath, resource) as w:
            tomli_w.dump(data, w.stream)
    except Exception as e:
        raise PTOSError(str(e))


def get_queries():
    """Get queries configuration."""
    return ptos.get_queries()


def save_schema(schema_dict):
    """Save schema dict to schema.toml atomically with backup and cache invalidation.
    
    Args:
        schema_dict: Complete schema dict to write.
    
    Raises:
        PTOSError on failure.
    """
    try:
        ptos._save_schema(schema_dict)
        _invalidate_history_cache()
    except Exception as e:
        raise PTOSError(str(e))


# ══════════════════════════════════════════════════════════════════════════════
# Todo module
# ══════════════════════════════════════════════════════════════════════════════

import ptos_todo


TODO_DIR  = ptos.TODO_DIR
TODO_PATH = ptos.TODO_PATH
DONE_PATH = ptos.DONE_PATH


def get_todos(include_done=False):
    """Load all todos from todo.txt. Returns list of Todo dataclass instances."""
    try:
        todos, errors = ptos_todo.load_todos(TODO_PATH)
        if include_done:
            done, _ = ptos_todo.load_todos(DONE_PATH)
            todos = todos + done
        return todos
    except Exception as e:
        raise PTOSError(str(e))


def get_todos_bucketed():
    """Load todos and return bucketed dict (overdue/today/upcoming/someday)."""
    try:
        todos, _ = ptos_todo.load_todos(TODO_PATH)
        return ptos_todo.bucket_todos(todos)
    except Exception as e:
        raise PTOSError(str(e))


def add_todo_line(text):
    """Add a raw todo.txt line. Preprocesses pri:/due:/t: shortcuts."""
    try:
        text = ptos_todo.preprocess_todo_text(text)
        t = ptos_todo.add_todo(TODO_PATH, text)
        return {"ok": True, "todo": dataclasses.asdict(t)}
    except Exception as e:
        raise PTOSError(str(e))


def complete_todo_by_line(line_no):
    """Mark a todo as complete (move to done.txt)."""
    try:
        todos, _ = ptos_todo.load_todos(TODO_PATH)
        target = [t for t in todos if t.line_no == line_no]
        if not target:
            raise PTOSError(f"Todo at line {line_no} not found")
        ptos_todo.complete_todo(target[0])
        return {"ok": True}
    except PTOSError:
        raise
    except Exception as e:
        raise PTOSError(str(e))


def undo_todo_by_line(line_no):
    """Undo a completed todo (move from done.txt back to todo.txt)."""
    try:
        ptos_todo.undo_todo(line_no)
        return {"ok": True}
    except PTOSError:
        raise
    except Exception as e:
        raise PTOSError(str(e))


def delete_todo_by_line(line_no):
    """Delete a todo by line number."""
    try:
        ptos_todo.delete_todo(TODO_PATH, line_no)
        return {"ok": True}
    except Exception as e:
        raise PTOSError(str(e))


def edit_todo_by_line(line_no, updates):
    """Edit fields on a todo by line number."""
    try:
        t = ptos_todo.edit_todo(TODO_PATH, line_no, updates)
        return {"ok": True, "todo": dataclasses.asdict(t)}
    except Exception as e:
        raise PTOSError(str(e))


def bulk_edit_todos(line_nos, updates):
    """Edit multiple open todos by line numbers."""
    try:
        results = ptos_todo.batch_edit_todos(TODO_PATH, line_nos, updates)
        return {"ok": True, "count": len(results)}
    except Exception as e:
        raise PTOSError(str(e))


def delete_done_todo_by_line(line_no):
    """Delete a done todo by line number."""
    try:
        ptos_todo.delete_todo(DONE_PATH, line_no)
        return {"ok": True}
    except Exception as e:
        raise PTOSError(str(e))


def edit_done_todo_by_line(line_no, updates):
    """Edit fields on a done todo by line number."""
    try:
        t = ptos_todo.edit_todo(DONE_PATH, line_no, updates)
        return {"ok": True, "todo": dataclasses.asdict(t)}
    except Exception as e:
        raise PTOSError(str(e))


def get_todo_projects():
    """Get all unique +Project tokens from open todos."""
    try:
        todos, _ = ptos_todo.load_todos(TODO_PATH)
        done, _ = ptos_todo.load_todos(DONE_PATH)
        return ptos_todo.get_projects(todos + done)
    except Exception as e:
        raise PTOSError(str(e))


def get_todo_contexts():
    """Get all unique @context tokens from open todos."""
    try:
        todos, _ = ptos_todo.load_todos(TODO_PATH)
        done, _ = ptos_todo.load_todos(DONE_PATH)
        return ptos_todo.get_contexts(todos + done)
    except Exception as e:
        raise PTOSError(str(e))


def archive_old_todos(threshold_months=6):
    """Archive old done tasks to year files. Returns count archived."""
    try:
        return ptos_todo.archive_done_todos(DONE_PATH, threshold_months)
    except Exception as e:
        raise PTOSError(str(e))


# ══════════════════════════════════════════════════════════════════════════════
# Backlinks / link candidates — shared scan helper
# ══════════════════════════════════════════════════════════════════════════════

_BRACKET_RE = re.compile(r'\[\[([^\]]+)\]\]')


def _snippet(text, start, span=60):
    """Short snippet (~span chars) centered around a match start."""
    s = max(0, start - span // 2)
    return text[s:s + span]


def _iter_link_matches(linkable_fields):
    """Walk notes/journal/todo/records and yield match dicts:
    {"source": "note"|"journal"|"todo"|"record",
     "value": matched text,
     "loc": {...per-source location dict...}}

    Uses ptos.* attribute access so test monkeypatching of engine paths works.
    """
    def _scan_brackets(path, source, make_loc):
        try:
            with open(path, encoding="utf-8") as f:
                content = f.read()
            for m in _BRACKET_RE.finditer(content):
                yield {"source": source, "value": m.group(1),
                       "loc": make_loc(m.start(), content)}
        except Exception:
            return

    def _read_lines(path):
        try:
            with open(path, encoding="utf-8") as f:
                return f.readlines()
        except Exception:
            return []

    def _note_loc(rel, title, path, start, content):
        return {"rel_path": rel, "title": title,
                "path": path, "snippet": _snippet(content, start)}

    try:
        for root, _, files in os.walk(ptos.NOTES_DIR):
            for fname in sorted(files):
                if fname == "template.md" or not fname.endswith(".md"):
                    continue
                fpath = os.path.join(root, fname)
                rel = os.path.relpath(fpath, ptos.NOTES_DIR)
                title = fname[:-3]
                try:
                    with open(fpath, encoding="utf-8") as f:
                        first_line = f.readline().strip()
                    if first_line.startswith("# "):
                        title = first_line[2:]
                except Exception:
                    pass
                yield from _scan_brackets(
                    fpath, "note",
                    lambda s, c, rel=rel, title=title, path=fpath:
                        _note_loc(rel, title, path, s, c))
    except Exception:
        pass

    try:
        for date_dir_path in sorted(glob.glob(os.path.join(ptos.JOURNAL_DIR, "*", "*", "*.md"))):
            date_str = os.path.splitext(os.path.basename(date_dir_path))[0]
            yield from _scan_brackets(
                date_dir_path, "journal",
                lambda s, c, date_str=date_str, path=date_dir_path:
                    {"date": date_str, "path": path,
                     "snippet": _snippet(c, s)})
    except Exception:
        pass

    for tpath_name in ["todo.txt", "done.txt"]:
        tpath = os.path.join(ptos.TODO_DIR, tpath_name)
        done = tpath_name == "done.txt"
        lines = _read_lines(tpath)
        for lineno, line in enumerate(lines, start=1):
            for m in _BRACKET_RE.finditer(line):
                yield {"source": "todo", "value": m.group(1),
                       "loc": _todo_loc(line, lineno, done, tpath)}
            if "project" in linkable_fields:
                for m in re.finditer(r'\+\S+', line):
                    yield {"source": "todo", "value": m.group(0)[1:],
                           "loc": _todo_loc(line, lineno, done, tpath)}
            if "context" in linkable_fields:
                for m in re.finditer(r'@\S+', line):
                    yield {"source": "todo", "value": m.group(0)[1:],
                           "loc": _todo_loc(line, lineno, done, tpath)}
            for m in re.finditer(r'\blinks:([\w:,\-]+)', line):
                for token in m.group(1).split(","):
                    token = token.strip()
                    if token:
                        yield {"source": "todo", "value": token,
                               "loc": _todo_loc(line, lineno, done, tpath)}

    try:
        for fname in ptos.get_log_files():
            path = os.path.join(ptos.RECORDS_DIR, fname)
            lines = _read_lines(path)
            _kv_re = None
            if linkable_fields:
                _kv_re = re.compile(r'\b(' + '|'.join(re.escape(f) for f in linkable_fields) + r')=(\S+)')
            for lineno, line in enumerate(lines, start=1):
                if _kv_re:
                    for m in _kv_re.finditer(line):
                        yield {"source": "record",
                               "value": m.group(2),
                               "loc": _record_loc(line, fname, m.group(1), lineno, m.start(2))}
                for m in re.finditer(r'\blinks=([\w:,\-]+)', line):
                    for token in m.group(1).split(","):
                        token = token.strip()
                        if token:
                            yield {"source": "record", "value": token,
                                   "loc": _record_loc(line, fname, "links", lineno, line.find(token))}
    except Exception:
        pass


def _todo_loc(line, lineno, done, path):
    return {"line": line.strip(), "lineno": lineno, "done": done, "path": path}


def _record_loc(line, fname, field, lineno, value_start):
    return {"date": line[:10], "type": _record_type(line),
            "field": field, "path": fname, "lineno": lineno,
            "snippet": _snippet(line, value_start)}


def _record_type(line):
    try:
        return line.split()[1].split("=", 1)[1]
    except Exception:
        return ""


def get_link_candidates(q):
    """Collect unique candidate strings (from brackets + linkable fields)
    filtered by q. Mirrors the old /api/link-candidates endpoint."""
    q = (q or "").lower()
    results = []
    seen = set()
    for m in _iter_link_matches(ptos.get_linkable_fields()):
        v = m["value"].strip()
        if not v or v.lower() in seen or q not in v.lower():
            continue
        seen.add(v.lower())
        results.append(v)
    return sorted(results)[:20]


def get_backlinks(subject):
    """Return every reference to subject across notes/journal/todo/records."""
    subject = (subject or "").strip().lower()
    out = {"notes": [], "journal": [], "todo": [], "records": []}
    if not subject:
        return out
    for m in _iter_link_matches(ptos.get_linkable_fields()):
        if m["value"].strip().lower() != subject:
            continue
        key = "notes" if m["source"] == "note" else \
              "records" if m["source"] == "record" else m["source"]
        out[key].append(m["loc"])
    return out


def get_link_ids():
    """All type:id targets currently present (for autocomplete / link picker)."""
    try:
        return ptos.list_link_ids()
    except Exception as e:
        raise PTOSError(str(e))


def retro_id_record(filepath, lineno):
    """Generate + append id=<id> to a record line in place.
    lineno is the 0-based file index (engine convention)."""
    try:
        with open(filepath, encoding="utf-8") as f:
            lines = f.readlines()
        if lineno < 0 or lineno >= len(lines):
            raise PTOSError(f"Line {lineno + 1} out of range in {filepath}")
        raw = lines[lineno].rstrip("\n")
        d, kv, _ = ptos.parse_line(raw)
        rtype = kv.get("type")
        if not rtype:
            raise PTOSError("Can't assign an id to a line without a type field")
        if kv.get("id"):
            raise PTOSError(f"Line already has id={kv['id']}")
        new_id = ptos.append_record_id(filepath, lineno, raw)
        _invalidate_history_cache()
        return {"ok": True, "id": new_id, "target": f"{rtype}:{new_id}"}
    except PTOSError:
        raise
    except Exception as e:
        raise PTOSError(str(e))


def retro_id_todo(line_no):
    """Generate + append id:<id> to a todo line in place."""
    try:
        todos, _ = ptos_todo.load_todos(TODO_PATH)
        target = [t for t in todos if t.line_no == line_no]
        if not target:
            raise PTOSError(f"Todo at line {line_no} not found")
        t = target[0]
        if t.id:
            raise PTOSError(f"Todo already has id:{t.id}")
        new_line, new_id = ptos.append_todo_id(t.raw_line)
        ptos_todo.rewrite_line_by_number(TODO_PATH, t.line_no, new_line)
        return {"ok": True, "id": new_id, "target": f"todo:{new_id}"}
    except PTOSError:
        raise
    except Exception as e:
        raise PTOSError(str(e))


def link_entries(src_target, dst_target):
    """Add dst_target to the source entry's links field. Returns the new target
    list. Raises PTOSError if the source can't carry links."""
    try:
        src = ptos.resolve_link(src_target)
        if src is None:
            raise PTOSError(f"Source '{src_target}' not found — give it an id first "
                            "(edit it and press Generate, or use --retro-id).")
        dst_resolves = ptos.resolve_link(dst_target) is not None
        if src["kind"] == "journal":
            raise PTOSError("Journal entries can't carry links= tokens — write [[...]] "
                            "in the prose instead.")
        if src["kind"] == "todo":
            new_line = ptos.append_links_to_todo_line(src["line"], [dst_target])
            updated = ptos_todo.rewrite_line_by_number(src["filepath"], src["lineno"], new_line)
        else:
            new_line = ptos.append_links_to_line(src["line"], [dst_target])
            ptos.rewrite_line_in_file(src["filepath"], src["line"], new_line, lineno=src["lineno"])
            updated = True
        _invalidate_history_cache()
        links = []
        for tok in re.findall(r'links[=:](\S+)', new_line):
            links.extend(x.strip() for x in tok.split(",") if x.strip())
        return {"ok": True, "source": src_target, "target": dst_target,
                "resolves": dst_resolves, "updated": updated, "links": links}
    except PTOSError:
        raise
    except Exception as e:
        raise PTOSError(str(e))

