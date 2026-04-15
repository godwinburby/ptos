"""
ptos_web.py  —  Flask web UI for PTOS (mobile-first, responsive)
Place alongside ptos.py and ptos_service.py.
Run:  python ptos_web.py   →  http://localhost:5000
"""

import sys, os, re, datetime as dt, json, csv, tempfile, platform, subprocess, urllib.request
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import ptos_service as svc
from ptos_service import PTOSError
import ptos

from flask import (Flask, render_template, request, redirect,
                   url_for, jsonify, send_file)

app = Flask(__name__, template_folder="web_templates")
app.secret_key = "ptos-local-only"

_TIME_OPTIONS_BASE = [
    ("Today","td"),("Yesterday","yd"),("This week","tw"),("Last week","lw"),
    ("This month","tm"),("Last month","lm"),("This quarter","tq"),
    ("Last quarter","lq"),("This year","ty"),("Last year","ly"),("All time","all"),
    ("Custom","custom"),
]
_YEAR_RANGE = list(range(dt.date.today().year - 10, dt.date.today().year + 1))

def _build_time_options():
    """Standard time options merged with custom cycles from config.toml."""
    opts = list(_TIME_OPTIONS_BASE)
    try:
        cycles = svc.get_config().get("cycles", {})
        for name in cycles:
            label = name.replace("_", " ").title()
            # insert before Custom (last entry)
            opts.insert(-1, (label, name))
            opts.insert(-1, (f"{label} -1", f"{name}-1"))
    except Exception:
        pass
    return opts

def _get_time_options():
    return _build_time_options()

# module-level for templates — refreshed per-request in routes that need it
TIME_OPTIONS = _build_time_options()
_TIME_DICT   = dict(TIME_OPTIONS)

def _now_str():
    return dt.datetime.now().strftime("%a %d %b")

def _greeting():
    h = dt.datetime.now().hour
    return "morning" if h < 12 else "afternoon" if h < 17 else "evening"

def _build_period_label(time_code, custom_time, cycles):
    """Build a human-readable label from time code.
    
    Examples:
      "tm"     → "This month"
      "tw"     → "This week"  
      "tq"     → "This quarter"
      "all"    → "All time"
      "2026-04"→ "Apr 2026"
      "clinic" → "Clinic"
      "custom" → "Custom"
    """
    # Standard time options labels
    labels = {
        "td": "Today", "yd": "Yesterday",
        "tw": "This week", "lw": "Last week",
        "tm": "This month", "lm": "Last month",
        "tq": "This quarter", "lq": "Last quarter",
        "ty": "This year", "ly": "Last year",
        "all": "All time",
    }
    
    # Check standard codes first
    if time_code in labels:
        return labels[time_code]
    
    # Handle YYYY-MM format (custom month)
    if re.fullmatch(r"\d{4}-\d{2}", time_code):
        year, month = int(time_code[:4]), int(time_code[5:7])
        dt_obj = dt.datetime(year, month, 1)
        return dt_obj.strftime("%b %Y")
    
    # Check for custom cycles (e.g., "clinic", "school")
    for cycle_name in cycles.keys():
        if time_code == cycle_name:
            return cycle_name.capitalize()
        # Check for offset variants like "clinic-1"
        if time_code.startswith(cycle_name + "-"):
            return cycle_name.capitalize()
    
    # Handle "custom" without a specific time
    if time_code == "custom" and custom_time:
        if re.fullmatch(r"\d{4}-\d{2}", custom_time):
            year, month = int(custom_time[:4]), int(custom_time[5:7])
            dt_obj = dt.datetime(year, month, 1)
            return dt_obj.strftime("%b %Y")
        return "Custom"
    
    # Fallback - try to use custom_time if provided
    if custom_time and re.fullmatch(r"\d{4}-\d{2}", custom_time):
        year, month = int(custom_time[:4]), int(custom_time[5:7])
        dt_obj = dt.datetime(year, month, 1)
        return dt_obj.strftime("%b %Y")
    
    return "Custom"

def _build_field_defs(schema, rtype, current_record=None):
    if not rtype: return []
    type_schema  = schema.get("type", {}).get(rtype, {})
    required     = type_schema.get("required", [])
    conditions   = type_schema.get("conditions", {})   # {field: {when: {k: v}}}

    # collect regular fields — skip derived (virtual, computed at query time, never entered)
    all_fields = list(required)
    for f, fdef in type_schema.get("fields", {}).items():
        if f in all_fields:
            continue
        global_meta = schema.get("fields", {}).get(f, {})
        type_scoped = fdef if isinstance(fdef, dict) else {}
        if (isinstance(global_meta, dict) and "derived" in global_meta) or \
           "derived" in type_scoped:
            continue
        all_fields.append(f)

    # conditional fields are real user-entered fields — shown/hidden by condition
    for f in conditions:
        if f not in all_fields:
            all_fields.append(f)

    parent_fields  = {
        fd.get("parent")
        for fd in type_schema.get("fields", {}).values()
        if isinstance(fd, dict) and fd.get("parent")
    }
    tag_triggers = set(type_schema.get("tags", {}).keys())
    # fields that are keys in any condition's "when" block — changing them
    # may show/hide conditional fields, so they need onParentChange wired up
    condition_triggers = {
        k
        for rule in conditions.values()
        for k in rule.get("when", {}).keys()
    }
    defs   = []
    record = current_record or {}
    for fname in all_fields:
        if fname == "tag": continue
        field_meta = schema.get("fields", {}).get(fname, {})
        is_int     = isinstance(field_meta, dict) and field_meta.get("type") == "int"
        unit       = field_meta.get("unit", "") if isinstance(field_meta, dict) else ""
        field_def  = type_schema.get("fields", {}).get(fname, {})
        parent     = field_def.get("parent") if isinstance(field_def, dict) else None
        has_parent = bool(parent)
        is_parent             = fname in parent_fields
        is_tag_trigger        = fname in tag_triggers
        is_condition_trigger  = fname in condition_triggers

        # show_when: {} = always visible; {k: v} = hide until condition is met
        cond_rule = conditions.get(fname, {})
        show_when = cond_rule.get("when", {}) if cond_rule else {}
        # skip conditional fields whose condition is not currently met —
        # avoids showing fit when outcome=deferred on initial render.
        # JS on the template side can re-request field defs when outcome changes.
        if show_when and not all(
            record.get(k) == v for k, v in show_when.items()
        ):
            continue

        if parent:
            parent_val = record.get(parent, "")
            options    = ptos.resolve_options_for_value(type_schema, fname, parent_val)
        else:
            options = ptos.resolve_options(schema, type_schema, fname) or []
        defs.append({
            "name":           fname,
            "required":       fname in required,
            "options":        options,
            "is_int":         is_int,
            "unit":           unit,
            "parent":         parent or "",
            "has_parent":     has_parent,
            "is_parent":            is_parent,
            "is_tag_trigger":       is_tag_trigger,
            "is_condition_trigger": is_condition_trigger,
            "show_when":            show_when,
        })
    return defs


def _resolve_multi_preset(name):
    presets = svc.get_presets()
    pd = presets.get(name, {})
    if isinstance(pd, dict) and "alias" in pd:
        pd = presets.get(pd["alias"], {})
    if not isinstance(pd, dict) or "records" not in pd:
        return None, f"'{name}' is not a multi-record preset"
    try:
        schema = svc.get_schema()
    except Exception as e:
        return None, str(e)
    resolved = []
    for item in pd["records"]:
        if not isinstance(item, str):
            return None, "records list must contain preset names"
        if item not in presets:
            return None, f"references unknown preset '{item}'"
        ref = presets[item]
        if isinstance(ref, dict) and "alias" in ref:
            ref = presets.get(ref["alias"], {})
        if isinstance(ref, dict) and "records" in ref:
            return None, f"nested multi-record presets not supported"
        record = dict(ref)
        problems = ptos.validate_record(schema, record)
        if problems:
            return None, f"preset '{item}': {problems[0]}"
        resolved.append(record)
    return resolved, None


def _multi_presets():
    result = {}
    for name, p in svc.get_presets().items():
        if not isinstance(p, dict) or "records" not in p:
            continue
        records, err = _resolve_multi_preset(name)
        if records is not None:
            refs = p["records"]
            result[name] = ", ".join(refs) if isinstance(refs, list) else ""
    return result


# ══════════════════════════════════════════════════════════════════════════════
# Home
# ══════════════════════════════════════════════════════════════════════════════

@app.route("/")
def home():
    try: schema = svc.get_schema()
    except: schema = {}
    presets = {k: v for k, v in svc.get_presets().items()
               if not (isinstance(v, dict) and ("alias" in v or "records" in v))}
    multi_presets = _multi_presets()
    try:
        due_data  = svc.get_due()
        due_rows  = due_data["rows"]
        due_count = due_data["count"]
    except Exception:
        due_rows = []; due_count = 0
    stats = []
    dashboards = {}
    try:
        queries    = svc.get_queries()
        dashboards = queries.get("dashboards", {})
        cfg        = svc.get_config()
        default_db = cfg.get("dashboard", {}).get("default")
        # Use query param if provided, otherwise use config default, fallback to first
        db_name = request.args.get("dashboard", default_db or next(iter(dashboards), None))
        
        # Get time window from query param, default to this month
        time_code = request.args.get("time", "tm")
        custom_time = request.args.get("custom_time", "")
        if time_code == "custom":
            if custom_time and re.match(r"\d{4}-\d{2}", custom_time):
                time_code = custom_time
        
        cycles = cfg.get("cycles", {})
        if db_name and db_name in dashboards:
            db = svc.get_dashboard(db_name, time_code)
            # Build nice period label (e.g., "This week", "Apr 2026", "Clinic")
            period_str = _build_period_label(time_code, custom_time, cycles)
            # Show all dashboard items in home (no limit, template handles display)
            for item in db["items"]:
                kind = item.get("kind", "unknown")
                stat = {
                    "label": item["name"].replace("_"," "),
                    "value": item["value"],
                    "sub": period_str,
                    "kind": kind,
                }
                # Only queries get a clickable link
                if kind == "query":
                    stat["query_url"] = f"/queries?run={item['name']}&time={time_code}"
                stats.append(stat)
    except Exception:
        pass
    recent_rows = []
    try:
        data = svc.get_records([], "td")
        recent_rows = data["records"][-8:]
        recent_cols = data["columns"]
    except Exception:
        recent_cols = []
    return render_template("home.html",
        tab="home", title="Home", now=_now_str(), greeting=_greeting(),
        presets=sorted(presets.keys())[:8],
        multi_presets=multi_presets,
        due_count=due_count, due_rows=due_rows[:5],
        stats=stats,
        dashboards=list(dashboards.keys()),
        current_db=db_name if 'db_name' in locals() else None,
        time_options=_get_time_options(),
        year_range=_YEAR_RANGE,
        current_time=request.args.get("time", "tm"),
        custom_time=request.args.get("custom_time", ""),
        recent_rows=recent_rows, recent_cols=recent_cols)


# ══════════════════════════════════════════════════════════════════════════════
# Due
# ══════════════════════════════════════════════════════════════════════════════

@app.route("/due")
def due_page():
    days = request.args.get("days", None)
    days_int = int(days) if days is not None else None
    try:
        data = svc.get_due(days_override=days_int)
        rows = data["rows"]
        days_used = data["days"]
        error = None
    except PTOSError as e:
        rows = []; days_used = 7; error = str(e)
    return render_template("due.html", tab="due", title="Due List",
        now=_now_str(), rows=rows, days=days_used, error=error)


# ══════════════════════════════════════════════════════════════════════════════
# Add Record
# ══════════════════════════════════════════════════════════════════════════════

@app.route("/add", methods=["GET"])
def add_get():
    try:
        schema = svc.get_schema()
    except PTOSError:
        schema = {"types": {"allowed": []}}
    types   = schema.get("types", {}).get("allowed", [])
    presets = {k: v for k, v in svc.get_presets().items()
               if not (isinstance(v, dict) and ("alias" in v or "records" in v))}
    multi_presets = _multi_presets()
    selected_type = request.args.get("type", "")
    preset_name   = request.args.get("preset", "")
    field_values  = {k: v for k, v in request.args.items()
                     if k not in ("type","preset","date")}
    if "tag" in request.args:
        field_values["tag"] = request.args.getlist("tag")
    if preset_name and not selected_type:
        pd = svc.get_presets().get(preset_name, {})
        if isinstance(pd, dict) and "alias" in pd:
            pd = svc.get_presets().get(pd["alias"], {})
        if pd:
            selected_type = pd.get("type", "")
            for k, v in pd.items():
                if k != "type" and k not in field_values: field_values[k] = v
    
    # Get history defaults to pre-populate form - this also provides context
    # for resolving parent->child field options correctly
    history_defaults = {}
    history_filtered_tags = []  # Tags filtered by current field cascade
    if selected_type:
        try:
            # Build initial context from history defaults + field_values
            temp_history = svc.get_history_suggestions(selected_type)
            history_defaults = temp_history.get("field_defaults", {})
        except Exception:
            pass
    
    # Merge history defaults with field_values (field_values/preset takes priority)
    initial_context = {**history_defaults, **field_values}
    
    # Get filtered history tags based on current cascade context
    if selected_type:
        try:
            history_with_context = svc.get_history_suggestions(selected_type, initial_context)
            history_filtered_tags = history_with_context.get("filtered_tags", [])
        except Exception:
            pass
    
    field_defs  = _build_field_defs(schema, selected_type, initial_context)
    tag_options = []
    if selected_type:
        ts = schema.get("type", {}).get(selected_type, {})
        tag_options = ptos.resolve_tags(schema, ts, initial_context)
    return render_template("add.html",
        tab="add", title="Add Record", now=_now_str(),
        types=types, presets=sorted(presets.keys()),
        multi_presets=multi_presets,
        selected_type=selected_type, field_defs=field_defs,
        tag_options=tag_options, history_tags=history_filtered_tags,
        field_values=field_values,
        today=dt.date.today().isoformat(),
        msg=None, msg_type=None, last_line=None)

@app.route("/add", methods=["POST"])
def add_post():
    try:
        schema = svc.get_schema()
    except PTOSError:
        schema = {"types": {"allowed": []}}
    types  = schema.get("types", {}).get("allowed", [])
    presets = {k: v for k, v in svc.get_presets().items()
               if not (isinstance(v, dict) and ("alias" in v or "records" in v))}
    rtype     = request.form.get("type","").strip()
    date_str  = request.form.get("date", dt.date.today().isoformat()).strip()
    note      = request.form.get("note","").strip() or None
    custom_tags = [t.strip().replace(" ","_")
                   for t in request.form.get("custom_tags","").split(",") if t.strip()]
    record = {"type": rtype}
    ts     = schema.get("type", {}).get(rtype, {})
    all_f  = list(ts.get("required",[]))
    for f in ts.get("fields",{}):
        if f not in all_f: all_f.append(f)
    for f in ts.get("conditions",{}):
        if f not in all_f: all_f.append(f)
    for fname in all_f:
        if fname == "tag": continue
        val = request.form.get(fname,"").strip()
        if val: record[fname] = val.replace(" ","_")
    tags = request.form.getlist("tag") + custom_tags
    if tags: record["tag"] = tags
    try:   problems = ptos.validate_record(schema, record)
    except PTOSError as e: problems = [str(e)]
    if problems:
        fd = _build_field_defs(schema, rtype, record)
        return render_template("add.html",
            tab="add", title="Add Record", now=_now_str(),
            types=types, presets=sorted(presets.keys()),
            multi_presets=_multi_presets(),
            selected_type=rtype, field_defs=fd,
            tag_options=ptos.resolve_tags(schema, ts, record),
            field_values=record, today=dt.date.today().isoformat(),
            msg=" | ".join(problems), msg_type="error", last_line=None)
    try:
        line = ptos.build_record_line(date_str, record, note)
        svc.append_record(line)
    except PTOSError as e:
        fd = _build_field_defs(schema, rtype, record)
        return render_template("add.html",
            tab="add", title="Add Record", now=_now_str(),
            types=types, presets=sorted(presets.keys()),
            multi_presets=_multi_presets(),
            selected_type=rtype, field_defs=fd,
            tag_options=ptos.resolve_tags(schema, ts, record),
            field_values=record, today=dt.date.today().isoformat(),
            msg=str(e), msg_type="error", last_line=None)
    return render_template("add.html",
        tab="add", title="Add Record", now=_now_str(),
        types=types, presets=sorted(presets.keys()),
        multi_presets=_multi_presets(),
        selected_type="", field_defs=[], tag_options=[],
        field_values={}, today=dt.date.today().isoformat(),
        msg=None, msg_type=None, last_line=line)


# ══════════════════════════════════════════════════════════════════════════════
# Journal
# ══════════════════════════════════════════════════════════════════════════════

@app.route("/journal")
def journal_get():
    today_d  = dt.date.today()
    date_str = request.args.get("date", today_d.isoformat())
    try:   date = min(dt.date.fromisoformat(date_str), today_d)
    except: date = today_d
    date_str  = date.isoformat()
    prev_date = (date - dt.timedelta(days=1)).isoformat()
    next_date = (date + dt.timedelta(days=1)).isoformat()
    year_dir = os.path.join(ptos.JOURNAL_DIR, date_str[:4])
    os.makedirs(year_dir, exist_ok=True)
    path = os.path.join(year_dir, f"{date_str}.md")
    if not os.path.exists(path) and date == today_d:
        path = ptos.get_today_journal()
    content = open(path, encoding="utf-8").read() if os.path.exists(path) else ""
    return render_template("journal.html",
        tab="journal", title="Journal", now=_now_str(),
        date=date_str, today=today_d.isoformat(),
        prev_date=prev_date, next_date=next_date,
        content=content, msg=None)

@app.route("/journal/save", methods=["POST"])
def journal_save():
    data = request.get_json(silent=True) or {}
    date = data.get("date", dt.date.today().isoformat())
    content = data.get("content","")
    try: dt.date.fromisoformat(date)
    except: return jsonify(ok=False, error="Invalid date")
    year_dir = os.path.join(ptos.JOURNAL_DIR, date[:4])
    os.makedirs(year_dir, exist_ok=True)
    path = os.path.join(year_dir, f"{date}.md")
    svc.write_file(path, content)
    return jsonify(ok=True)


# ══════════════════════════════════════════════════════════════════════════════
# Schema builder
# ══════════════════════════════════════════════════════════════════════════════

@app.route("/schema-builder")
def schema_builder():
    try:
        schema = svc.get_schema()
    except Exception:
        schema = {}
    return render_template("schema_builder.html",
        tab="schema_builder", title="Schema Builder",
        now=_now_str(), schema=schema)


@app.route("/schema-builder/save", methods=["POST"])
def schema_builder_save():
    data = request.get_json(silent=True) or {}
    new_types    = data.get("types", [])
    type_schemas = data.get("type_schemas", {})
    if not new_types:
        return jsonify(ok=False, error="At least one record type is required")
    import re as _re
    for t in new_types:
        if not _re.match(r"^[a-z][a-z0-9_]*$", t):
            return jsonify(ok=False,
                error=f"Type '{t}' must be lowercase letters, numbers, underscores")
    try:
        schema = svc.get_schema()
        lines  = _build_schema_toml(schema, new_types, type_schemas)
        ptos._backup_file(ptos.SCHEMA_PATH)
        svc.write_file(ptos.SCHEMA_PATH, "\n".join(lines) + "\n")
        for key in ("schema", "derived_fields", "numeric_fields"):
            ptos._CACHE.pop(key, None)
        return jsonify(ok=True)
    except Exception as e:
        return jsonify(ok=False, error=str(e))


@app.route("/schema-builder/preview-lint", methods=["POST"])
def schema_builder_preview_lint():
    """Preview lint results against unsaved schema changes."""
    import tomllib
    data = request.get_json(silent=True) or {}
    new_types    = data.get("types", [])
    type_schemas = data.get("type_schemas", {})
    
    if not new_types:
        return jsonify(ok=False, error="No types provided")
    
    try:
        old_schema = svc.get_schema()
        lines = _build_schema_toml(old_schema, new_types, type_schemas)
        new_schema_toml = "\n".join(lines)
        new_schema = tomllib.loads(new_schema_toml)
        
        old_schema_raw = ptos._CACHE.get("schema", {})
        
        ptos._CACHE["schema"] = new_schema
        ptos._CACHE.pop("derived_fields", None)
        ptos._CACHE.pop("numeric_fields", None)
        
        try:
            result = ptos.lint_all_records()
        finally:
            ptos._CACHE["schema"] = old_schema_raw
            ptos._CACHE.pop("derived_fields", None)
            ptos._CACHE.pop("numeric_fields", None)
        
        return jsonify(ok=True, data=result)
    except Exception as e:
        return jsonify(ok=False, error=str(e))


# ══════════════════════════════════════════════════════════════════════════════
# Backup
# ══════════════════════════════════════════════════════════════════════════════

@app.route("/backup")
def backup_page():
    backups = svc.list_backups()
    return render_template("backup.html",
        tab="backup", title="Backup & Restore", now=_now_str(),
        backups=backups)


@app.route("/backup/create", methods=["POST"])
def backup_create():
    try:
        result = svc.backup_full()
        return jsonify(ok=True, path=result["path"])
    except Exception as e:
        return jsonify(ok=False, error=str(e))


@app.route("/backup/download/<name>")
def backup_download(name):
    # Prevent path traversal attacks
    if ".." in name or "/" in name or "\\" in name:
        return "Invalid backup name", 400
    
    backup_path = os.path.join(ptos.BACKUP_DIR, name)
    
    # Verify path is within BACKUP_DIR
    real_path = os.path.realpath(backup_path)
    real_backup_dir = os.path.realpath(ptos.BACKUP_DIR)
    if not real_path.startswith(real_backup_dir + os.sep):
        return "Invalid backup name", 400
    
    if not os.path.exists(backup_path):
        return "Backup not found", 404
    return send_file(backup_path, as_attachment=True, download_name=name)


@app.route("/backup/delete", methods=["POST"])
def backup_delete():
    data = request.get_json(silent=True) or {}
    name = data.get("name", "")
    if not name:
        return jsonify(ok=False, error="No backup name provided")
    try:
        svc.delete_backup(name)
        return jsonify(ok=True)
    except Exception as e:
        return jsonify(ok=False, error=str(e))


@app.route("/backup/check", methods=["GET"])
def backup_check():
    """Check if all required backup folders exist."""
    all_exist, missing = ptos.check_backup_folders()
    return jsonify(ok=all_exist, missing=missing)


@app.route("/backup/restore", methods=["POST"])
def backup_restore():
    # Create backup first before restoring
    try:
        result = svc.backup_full()
        print(f"Backup created before restore: {os.path.basename(result['path'])}")
    except Exception as e:
        return jsonify(ok=False, error=f"Failed to create backup before restore: {e}")
    
    if "file" in request.files:
        f = request.files["file"]
        if f.filename == "":
            return jsonify(ok=False, error="No file selected")
        # Save uploaded file to temp, then restore
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as tmp:
            f.save(tmp.name)
            tmp_path = tmp.name
        try:
            svc.restore_full(tmp_path)
            os.unlink(tmp_path)
            return jsonify(ok=True)
        except Exception as e:
            os.unlink(tmp_path)
            return jsonify(ok=False, error=str(e))
    else:
        data = request.get_json(silent=True) or {}
        name = data.get("name", "")
        backup_path = os.path.join(ptos.BACKUP_DIR, name)
        if not os.path.exists(backup_path):
            return jsonify(ok=False, error="Backup not found")
        try:
            svc.restore_full(backup_path)
            return jsonify(ok=True)
        except Exception as e:
            return jsonify(ok=False, error=str(e))


@app.route("/backup/config", methods=["GET"])
def backup_config_download():
    """Download config backup as a zip file."""
    try:
        result = svc.backup_config_only()
        if result.get("ok"):
            path = result["path"]
            filename = os.path.basename(path)
            return send_file(path, as_attachment=True, download_name=filename)
        return jsonify(ok=False, error="Failed to create config backup")
    except Exception as e:
        return jsonify(ok=False, error=str(e))


@app.route("/backup/config/restore", methods=["POST"])
def backup_config_restore():
    """Restore config from uploaded zip file."""
    if "file" not in request.files:
        return jsonify(ok=False, error="No file uploaded")
    
    f = request.files["file"]
    if f.filename == "":
        return jsonify(ok=False, error="No file selected")
    
    # Save to temp file
    import tempfile
    with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as tmp:
        f.save(tmp.name)
        tmp_path = tmp.name
    
    try:
        result = svc.restore_config(tmp_path)
        os.unlink(tmp_path)
        return jsonify(ok=True, message=result.get("message", "Config restored"))
    except Exception as e:
        os.unlink(tmp_path)
        return jsonify(ok=False, error=str(e))


def _toml_val(v):
    if isinstance(v, bool):   return "true" if v else "false"
    if isinstance(v, int):    return str(v)
    if isinstance(v, float):  return str(v)
    if isinstance(v, list):
        items = ", ".join(f'"{x}"' if isinstance(x, str) else str(x) for x in v)
        return f"[{items}]"
    if isinstance(v, dict):
        pairs = ", ".join(
            (f'{dk} = "{dv}"' if isinstance(dv, str) else f"{dk} = {dv}")
            for dk, dv in v.items()
        )
        return "{" + pairs + "}"
    return '"'  + str(v).replace("\\", "\\\\").replace('"'  , '\\"') + '"'


def _toml_kv(k, v):
    return f"{k} = {_toml_val(v)}"


def _build_schema_toml(old_schema, new_types, type_schemas):
    lines = [
        "# ==================================================",
        "# PTOS SCHEMA  (managed by Schema Builder)",
        "# ==================================================",
        "",
        "[types]",
        "allowed = [",
    ]
    for t in new_types:
        lines.append(f'  "{t}",')
    lines.append("]")
    lines.append("")

    # ── global [fields.*] preserved verbatim ─────────────────────────────────
    lines += ["# Global field metadata", ""]
    for fname, fmeta in old_schema.get("fields", {}).items():
        if not isinstance(fmeta, dict):
            continue
        lines.append(f"[fields.{fname}]")
        for k, v in fmeta.items():
            lines.append(_toml_kv(k, v))
        lines.append("")

    # ── [shared.*] preserved verbatim ────────────────────────────────────────
    if old_schema.get("shared"):
        lines += ["# Shared field definitions", ""]
        for sname, smeta in old_schema["shared"].items():
            lines.append(f"[shared.{sname}]")
            if isinstance(smeta, dict):
                for k, v in smeta.items():
                    lines.append(_toml_kv(k, v))
            lines.append("")

    # ── types ────────────────────────────────────────────────────────────────
    lines += ["# ==================================================",
              "# TYPES", "# ==================================================", ""]
    old_types = old_schema.get("type", {})

    for tname in new_types:
        ts_new = type_schemas.get(tname, {})
        ts_old = old_types.get(tname, {})

        lines += [f"# {tname.upper()}", ""]
        lines.append(f"[type.{tname}]")
        required = ts_new.get("required", ts_old.get("required", []))
        if required:
            req_str = ", ".join(f'"{r}"' for r in required)
            lines.append(f"required = [{req_str}]")
        lines.append("")

        # fields: merge builder fields with preserved old fields
        fields_new  = ts_new.get("fields", {})
        fields_old  = ts_old.get("fields", {})
        seen_fields = list(fields_new.keys())
        for fn in fields_old:
            if fn not in seen_fields:
                seen_fields.append(fn)

        for fname in seen_fields:
            fdef_new = fields_new.get(fname)
            fdef_old = fields_old.get(fname, {})
            lines.append(f"[type.{tname}.fields.{fname}]")
            if fdef_new is not None:
                if fdef_new.get("is_int"):
                    lines.append('type = "int"')
                opts = fdef_new.get("options", [])
                if opts:
                    lines.append(_toml_kv("options", opts))
            else:
                if isinstance(fdef_old, dict):
                    for k, v in fdef_old.items():
                        lines.append(_toml_kv(k, v))
            lines.append("")

        # tags: merge builder tags with preserved old tags
        tags_new   = ts_new.get("tags", {})
        tags_old   = ts_old.get("tags", {})
        seen_tags  = list(tags_new.keys())
        for tf in tags_old:
            if tf not in seen_tags:
                seen_tags.append(tf)

        for tfield in seen_tags:
            tdef_new = tags_new.get(tfield)
            tdef_old = tags_old.get(tfield, {})
            lines.append(f"[type.{tname}.tags.{tfield}]")
            if tdef_new is not None:
                for fval, tags in tdef_new.items():
                    if tags:
                        lines.append(_toml_kv(f"options.{fval}", tags))
            else:
                if isinstance(tdef_old, dict):
                    for k, v in tdef_old.items():
                        lines.append(_toml_kv(k, v))
            lines.append("")

        # conditions: always preserved verbatim
        for cname, cdef in ts_old.get("conditions", {}).items():
            lines.append(f"[type.{tname}.conditions.{cname}]")
            if isinstance(cdef, dict):
                for k, v in cdef.items():
                    lines.append(_toml_kv(k, v))
            lines.append("")

    return lines


# ══════════════════════════════════════════════════════════════════════════════
# Query Builder
# ══════════════════════════════════════════════════════════════════════════════

def _write_queries_toml(raw_queries, raw_metrics, raw_dashboards, raw_aliases=None):
    """Build and atomically write queries.toml from dicts.
    raw_queries:    {name: {where, time, sum, group, search}}
    raw_metrics:    {name: {kind, base, base2, derived}}
    raw_dashboards: {name: {metrics: [...]}}
    raw_aliases:    {name: {alias: target}}   (optional)
    Preserves [due] section from existing file.
    Raises ValueError on invalid names, Exception on write failure.
    """
    import re as _re
    if raw_aliases is None:
        raw_aliases = {}
    for n in list(raw_queries) + list(raw_metrics) + list(raw_dashboards) + list(raw_aliases):
        if not _re.match(r'^[a-z][a-z0-9_]*$', n):
            raise ValueError(
                f"Invalid name '{n}' — use lowercase letters, numbers, underscores")

    try:
        old_queries = ptos.get_queries()
    except Exception:
        old_queries = {}

    lines = [
        "# --------------------------------------------------",
        "# PTOS QUERIES  (managed by Query Builder)",
        "# --------------------------------------------------",
        "",
    ]

    # ── Base queries ──────────────────────────────────────────────────────────
    for name, q in raw_queries.items():
        lines.append(f"[{name}]")
        if q.get("where", "").strip():
            val = q["where"].strip().replace('"', '\\"')
            lines.append(f'where = "{val}"')
        lines.append(f'time  = "{q.get("time", "tm")}"')
        if q.get("group", "").strip():
            lines.append(f'group = ["{q["group"].strip()}"]')
        if q.get("sort", "").strip():
            lines.append(f'sort = "{q["sort"].strip()}"')
        if q.get("search", "").strip():
            lines.append(f'search = "{q["search"].strip()}"')
        if q.get("sum"):
            lines.append("sum   = true")
        lines.append("")

    # ── Metrics ───────────────────────────────────────────────────────────────
    for name, m in raw_metrics.items():
        lines.append(f"[metrics.{name}]")
        kind  = m.get("kind", "avg")
        base  = m.get("base",  "").strip()
        base2 = m.get("base2", "").strip()
        derived = m.get("derived", "").strip()
        unit_field = m.get("unit_field", "").strip()
        unit_weights = m.get("unit_weights") or {}
        raw = m.get("_raw") or {}
        
        if derived:
            lines.append(f'derived = "{derived}"')
        elif kind == "ratio" and base and base2:
            lines.append(f'ratio = ["{base}", "{base2}"]')
        elif kind in ("avg", "sum", "max", "min") and base:
            lines.append(f'{kind} = "{base}"')
        
        # Unit field and weights for avg
        if kind == "avg" and unit_field:
            lines.append(f'unit_field   = "{unit_field}"')
        if kind == "avg" and unit_weights:
            uw_parts = [f'{k} = {v}' for k, v in unit_weights.items()]
            lines.append(f'unit_weights = {{ {", ".join(uw_parts)} }}')
        
        # Any extra raw fields
        for k, v in raw.items():
            if isinstance(v, str):
                lines.append(f'{k} = "{v}"')
            elif isinstance(v, bool):
                lines.append(f'{k} = {"true" if v else "false"}')
            elif isinstance(v, int):
                lines.append(f'{k} = {v}')
            elif isinstance(v, list):
                s = ", ".join(f'"{x}"' if isinstance(x, str) else str(x) for x in v)
                lines.append(f"{k} = [{s}]")
            elif isinstance(v, dict):
                lines.append(f'{k} = {json.dumps(v)}')
        
        lines.append("")

    # ── Alias queries ─────────────────────────────────────────────────────────
    for name, a in (raw_aliases or {}).items():
        alias = a.get("alias", "").strip()
        if alias:
            lines.append(f"[{name}]")
            lines.append(f'alias = "{alias}"')
            lines.append("")

    # ── Dashboards ────────────────────────────────────────────────────────────
    for name, db in raw_dashboards.items():
        lines.append(f"[dashboards.{name}]")
        items = db.get("metrics", [])
        if items:
            items_str = ", ".join(f'"{i}"' for i in items)
            lines.append(f"metrics = [{items_str}]")
        lines.append("")

    # ── Preserve [due] verbatim ───────────────────────────────────────────────
    if "due" in old_queries and isinstance(old_queries["due"], dict):
        lines.append("[due]")
        for k, v in old_queries["due"].items():
            if isinstance(v, str):    lines.append(f'{k} = "{v}"')
            elif isinstance(v, bool): lines.append(f'{k} = {"true" if v else "false"}')
            elif isinstance(v, int):  lines.append(f'{k} = {v}')
            elif isinstance(v, list):
                s = ", ".join(f'"{x}"' if isinstance(x, str) else str(x) for x in v)
                lines.append(f"{k} = [{s}]")
        lines.append("")

    ptos._backup_file(ptos.QUERIES_PATH)
    ptos.atomic_write(ptos.QUERIES_PATH, "\n".join(lines))
    ptos._CACHE.pop("queries", None)

@app.route("/query-builder")
def query_builder():
    try:
        queries = ptos.get_queries()
        schema  = ptos.get_schema()
        types   = schema.get("types", {}).get("allowed", [])
    except Exception:
        queries = {}
        types   = []
    return render_template("query_builder.html",
        tab="query_builder", title="Query Builder",
        now=_now_str(), queries=queries, types=types,
        time_options=_get_time_options())


@app.route("/query-builder/save", methods=["POST"])
def query_builder_save():
    """Receive full queries state from builder and rewrite queries.toml."""
    data = request.get_json(silent=True) or {}
    try:
        _write_queries_toml(
            data.get("queries", {}),
            data.get("metrics", {}),
            data.get("dashboards", {}),
            data.get("aliases", {}),
        )
        return jsonify(ok=True)
    except Exception as e:
        return jsonify(ok=False, error=str(e))


@app.route("/query-builder/delete", methods=["POST"])
def query_builder_delete():
    """Delete a single named query, metric, dashboard, or alias and rewrite the file."""
    data = request.get_json(silent=True) or {}
    name = data.get("name", "").strip()
    kind = data.get("kind", "query")   # "query" | "metric" | "dashboard" | "alias"
    if not name:
        return jsonify(ok=False, error="No name provided")
    try:
        queries = ptos.get_queries()
        reserved = ("metrics", "dashboards", "due")
        if kind == "metric":
            if name not in queries.get("metrics", {}):
                return jsonify(ok=False, error=f"Metric '{name}' not found")
            del queries["metrics"][name]
            _write_queries_toml(
                {k: v for k, v in queries.items()
                 if k not in reserved and isinstance(v, dict) and "alias" not in v},
                queries.get("metrics", {}),
                queries.get("dashboards", {}),
                {k: v for k, v in queries.items()
                 if k not in reserved and isinstance(v, dict) and "alias" in v},
            )
        elif kind == "dashboard":
            if name not in queries.get("dashboards", {}):
                return jsonify(ok=False, error=f"Dashboard '{name}' not found")
            del queries["dashboards"][name]
            _write_queries_toml(
                {k: v for k, v in queries.items()
                 if k not in reserved and isinstance(v, dict) and "alias" not in v},
                queries.get("metrics", {}),
                queries.get("dashboards", {}),
                {k: v for k, v in queries.items()
                 if k not in reserved and isinstance(v, dict) and "alias" in v},
            )
        elif kind == "alias":
            _write_queries_toml(
                {k: v for k, v in queries.items()
                 if k not in reserved and isinstance(v, dict) and "alias" not in v},
                queries.get("metrics", {}),
                queries.get("dashboards", {}),
                {k: v for k, v in queries.items()
                 if k not in reserved and isinstance(v, dict) and "alias" in v and k != name},
            )
        else:
            if name not in queries or name in reserved:
                return jsonify(ok=False, error=f"Query '{name}' not found")
            del queries[name]
            _write_queries_toml(
                {k: v for k, v in queries.items()
                 if k not in reserved and isinstance(v, dict) and "alias" not in v},
                queries.get("metrics", {}),
                queries.get("dashboards", {}),
                {k: v for k, v in queries.items()
                 if k not in reserved and isinstance(v, dict) and "alias" in v},
            )
        return jsonify(ok=True)
    except Exception as e:
        return jsonify(ok=False, error=str(e))


# ══════════════════════════════════════════════════════════════════════════════
# Queries
# ══════════════════════════════════════════════════════════════════════════════

@app.route("/queries")
def queries_get():
    try:    all_q = svc.get_queries()
    except: all_q = {}
    named = [k for k in all_q
             if k not in ("metrics","dashboards","due")
             and not (isinstance(all_q[k], dict) and "alias" in all_q[k])]
    return render_template("queries.html",
        tab="queries", title="Queries", now=_now_str(),
        queries=named,
        metrics=list(all_q.get("metrics",{}).keys()),
        dashboards=list(all_q.get("dashboards",{}).keys()),
        time_options=_get_time_options(), year_range=_YEAR_RANGE,
        current_time=request.args.get("time", ""),
        custom_time=request.args.get("custom_time", ""))

@app.route("/queries/run", methods=["POST"])
def queries_run():
    data = request.get_json(silent=True) or {}
    kind = data.get("kind","q")
    name = data.get("name","")
    raw_time = data.get("time","") or None
    # reject any value that is not a known alias and not a valid YYYY-MM
    _valid = {code for _, code in _get_time_options()}
    if raw_time and raw_time not in _valid and \
       not re.fullmatch(r"\d{4}-\d{2}", raw_time):
        return jsonify(ok=False, error=f"Invalid time window: {raw_time}")
    time = raw_time
    try:
        if kind == "d":
            result = svc.get_dashboard(name, time or "tm")
            result["kind"] = "dashboard"
            # Add human-readable time label
            cfg = svc.get_config()
            cycles = cfg.get("cycles", {})
            custom_time = ""
            time_for_label = time or "tm"
            result["time_label"] = _build_period_label(time_for_label, custom_time, cycles)
        elif kind == "m":
            result = svc.get_metric(name, time or "tm")
            result["kind"] = "metric"
        else:
            result = svc.run_query(name, time)
        return jsonify(ok=True, data=result)
    except PTOSError as e:
        return jsonify(ok=False, error=str(e))
    except Exception as e:
        return jsonify(ok=False, error=str(e))


# ══════════════════════════════════════════════════════════════════════════════
# Browse
# ══════════════════════════════════════════════════════════════════════════════

@app.route("/browse")
def browse_get():
    try:
        schema = svc.get_schema()
        types  = schema.get("types",{}).get("allowed",[])
    except PTOSError:
        types = []
    log_files = ptos.get_log_files()
    return render_template("browse.html",
        tab="browse", title="Browse", now=_now_str(),
        types=types, log_files=log_files, time_options=_get_time_options(), year_range=_YEAR_RANGE,
        current_time=request.args.get("time", "tm"),
        custom_time=request.args.get("custom_time", ""))

@app.route("/browse/run", methods=["POST"])
def browse_run():
    data   = request.get_json(silent=True) or {}
    raw_time = data.get("time","tm")
    _valid = {code for _, code in _get_time_options()}
    if raw_time and raw_time not in _valid and \
       not re.fullmatch(r"\d{4}-\d{2}", raw_time):
        raw_time = "tm"
    time = raw_time
    search = data.get("search","") or None
    group  = data.get("group","") or None
    sort   = data.get("sort","") or None
    file   = data.get("file","") or None
    expr   = data.get("expr","").strip()
    where  = data.get("where",[])
    if isinstance(where, str):
        where = [where] if where.strip() else []
    if expr and where:
        combined = ptos._filters_to_expr(where)
        filters  = [f"({combined}) AND ({expr})"] if combined else [expr]
    elif expr:
        filters = [expr]
    elif where:
        filters = where
    else:
        filters = []
    try:
        if group:
            result = svc.get_group(filters, time, [group], from_file=file)
            result["kind"] = "group"
        else:
            result = svc.get_records(filters, time, search=search,
                                     sort=sort, from_file=file)
            result["kind"] = "records"
        return jsonify(ok=True, data=result)
    except PTOSError as e:
        return jsonify(ok=False, error=str(e))
    except Exception as e:
        return jsonify(ok=False, error=str(e))

@app.route("/browse/export", methods=["POST"])
def browse_export():
    params = json.loads(request.form.get("params","{}"))
    expr   = params.get("expr","").strip()
    where  = params.get("where",[])
    time   = params.get("time","tm")
    search = params.get("search","") or None
    file   = params.get("file","") or None
    if isinstance(where, str):
        where = [where] if where.strip() else []
    if expr and where:
        combined = ptos._filters_to_expr(where)
        filters  = [f"({combined}) AND ({expr})"] if combined else [expr]
    elif expr:
        filters = [expr]
    elif where:
        filters = where
    else:
        filters = []
    try:
        data    = svc.get_records(filters, time, search=search, from_file=file)
        records = data["records"]
        cols    = [c for c in data["columns"] if not c.startswith("_")]
        tl      = _TIME_DICT.get(time, time)
        m = re.search(r'type=(\w+)', expr or " ".join(filters))
        type_part = m.group(1) if m else "records"
        filename  = f"{type_part}_{tl}.csv"
        tmp = tempfile.NamedTemporaryFile(mode="w",suffix=".csv",delete=False,
                                          encoding="utf-8",newline="")
        writer = csv.DictWriter(tmp, fieldnames=cols, extrasaction="ignore")
        writer.writeheader()
        for row in records: writer.writerow(row)
        tmp.close()
        return send_file(tmp.name, as_attachment=True,
                         download_name=filename, mimetype="text/csv")
    except Exception as e:
        return f"Export error: {e}", 500


# ══════════════════════════════════════════════════════════════════════════════
# Log Editor
# ══════════════════════════════════════════════════════════════════════════════

@app.route("/editor")
def editor_get():
    log_files = ptos.get_log_files()
    current = request.args.get("file","")
    if not current and log_files: current = log_files[-1]
    content = ""
    if current:
        path = os.path.join(ptos.RECORDS_DIR, current)
        if os.path.exists(path):
            with open(path,encoding="utf-8") as f: content = f.read()
    return render_template("editor.html",
        tab="editor", title="Log Editor", now=_now_str(),
        log_files=log_files, current_file=current, content=content, msg=None)

@app.route("/editor/save", methods=["POST"])
def editor_save():
    data = request.get_json(silent=True) or {}
    file = data.get("file",""); content = data.get("content","")
    if not file or "/" in file or "\\" in file:
        return jsonify(ok=False, error="Invalid filename")
    path = os.path.join(ptos.RECORDS_DIR, file)
    if not os.path.exists(path):
        return jsonify(ok=False, error=f"File not found: {file}")
    svc.write_file(path, content)
    # invalidate caches — editor can modify any config file
    for key in ("schema", "config", "queries", "presets",
                "derived_fields", "numeric_fields"):
        ptos._CACHE.pop(key, None)
    return jsonify(ok=True)


@app.route("/editor/validate", methods=["POST"])
def editor_validate():
    """Quick validation of raw log content using PTOS parser."""
    data = request.get_json(silent=True) or {}
    content = data.get("content", "")
    
    errors = []
    
    for i, line in enumerate(content.split("\n"), 1):
        line = line.strip()
        if not line:
            continue
        
        # Use PTOS parser
        result = ptos.safe_parse_line(line)
        if result is None:
            errors.append({"line": i, "problems": ["Cannot parse line - check format"]})
            continue
        
        date, kv, note = result
        problems = []
        
        # Check if date parsed successfully (dt.date.min means invalid)
        if date.year == 1:
            problems.append("Invalid date (expected YYYY-MM-DD)")
        
        # Check for type field
        if "type" not in kv:
            problems.append("Missing type field (use type=)")
        
        # Check for any tokens that weren't parsed (text without =)
        main_part, _, _ = line.partition("|")
        parts = main_part.strip().split()
        if len(parts) > 1:
            unparsed = [p for p in parts[1:] if "=" not in p]
            if unparsed:
                problems.append(f"Invalid text: '{' '.join(unparsed)}' - must be key=value format")
        
        if problems:
            errors.append({"line": i, "problems": problems})
    
    return jsonify(ok=True, errors=errors, warnings=[])


# ══════════════════════════════════════════════════════════════════════════════
# Lint
# ══════════════════════════════════════════════════════════════════════════════

@app.route("/lint")
def lint_page():
    return render_template("lint.html",
        tab="lint", title="Lint", now=_now_str())

@app.route("/lint/run", methods=["POST"])
def lint_run():
    try:
        result = ptos.lint_all_records()
        return jsonify(ok=True, data=result)
    except Exception as e:
        return jsonify(ok=False, error=str(e))


# ══════════════════════════════════════════════════════════════════════════════
# Edit Record (full form)
# ══════════════════════════════════════════════════════════════════════════════

@app.route("/edit", methods=["GET"])
def edit_get():
    filepath = request.args.get("filepath", "")
    lineno   = request.args.get("lineno", "")
    line     = request.args.get("line", "")
    if not filepath or not line:
        return redirect(url_for("browse_get"))
    try:
        lineno_int = int(lineno) if lineno else None
    except ValueError:
        lineno_int = None
    parsed = ptos.safe_parse_line(line)
    if not parsed:
        return redirect(url_for("browse_get"))
    d, kv, note = parsed
    rtype = kv.get("type", "")
    try:
        schema = svc.get_schema()
    except PTOSError:
        schema = {}
    field_values = {"type": rtype}
    for k, v in kv.items():
        if k == "tag":
            field_values[k] = v if isinstance(v, list) else [v]
        else:
            field_values[k] = ", ".join(v) if isinstance(v, list) else str(v)
    if note:
        field_values["note"] = note
    field_values["date"] = str(d)
    field_defs   = _build_field_defs(schema, rtype, field_values)
    current_tags = field_values.get("tag", [])
    if isinstance(current_tags, str):
        current_tags = [t.strip() for t in current_tags.split(",") if t.strip()]
    
    # Get filtered history tags based on current field values (cascade context)
    history_filtered_tags = []
    if rtype:
        try:
            history_with_context = svc.get_history_suggestions(rtype, field_values)
            history_filtered_tags = history_with_context.get("filtered_tags", [])
        except Exception:
            pass
    
    schema_tag_options = []
    if rtype:
        ts = schema.get("type", {}).get(rtype, {})
        schema_tag_options = ptos.resolve_tags(schema, ts, field_values)
    tag_options = list(current_tags) + [t for t in schema_tag_options if t not in current_tags]
    return_to = request.args.get("return_to") or request.referrer or url_for("browse_get")
    return render_template("edit.html",
        tab="browse", title="Edit Record", now=_now_str(),
        filepath=filepath, lineno=lineno_int, old_line=line,
        return_to=return_to,
        rtype=rtype, field_defs=field_defs,
        tag_options=tag_options, history_tags=history_filtered_tags,
        field_values=field_values,
        today=dt.date.today().isoformat(),
        msg=None, msg_type=None)


@app.route("/edit", methods=["POST"])
def edit_post():
    filepath  = request.form.get("filepath", "")
    old_line  = request.form.get("old_line", "")
    lineno    = request.form.get("lineno", "")
    rtype     = request.form.get("type", "").strip()
    date_str  = request.form.get("date", dt.date.today().isoformat()).strip()
    note      = request.form.get("note", "").strip() or None
    custom_tags = [t.strip().replace(" ", "_")
                   for t in request.form.get("custom_tags", "").split(",") if t.strip()]
    try:
        lineno_int = int(lineno) if lineno else None
    except ValueError:
        lineno_int = None
    try:
        schema = svc.get_schema()
    except PTOSError:
        schema = {}
    ts    = schema.get("type", {}).get(rtype, {})
    all_f = list(ts.get("required", []))
    for f in ts.get("fields", {}):
        if f not in all_f: all_f.append(f)
    for f in ts.get("conditions", {}):
        if f not in all_f: all_f.append(f)
    new_record = {"type": rtype}
    for fname in all_f:
        if fname == "tag": continue
        val = request.form.get(fname, "").strip()
        if val: new_record[fname] = val.replace(" ", "_")
    tags = request.form.getlist("tag") + custom_tags
    if tags: new_record["tag"] = tags
    parsed = ptos.safe_parse_line(old_line)
    if not parsed:
        return redirect(url_for("browse_get"))
    old_d, old_kv, old_note = parsed
    set_args = []
    if date_str != str(old_d):
        set_args.append(f"date={date_str}")
    all_keys = set(list(old_kv.keys()) + list(new_record.keys())) - {"type"}
    for k in all_keys:
        old_v = old_kv.get(k)
        new_v = new_record.get(k)
        if old_v is None and new_v is None:
            continue
        is_list_field = k == "tag" or isinstance(old_v, list) or isinstance(new_v, list)
        if is_list_field:
            old_list = old_v if isinstance(old_v, list) else ([old_v] if old_v else [])
            new_list = new_v if isinstance(new_v, list) else ([new_v] if new_v else [])
            if set(old_list) != set(new_list):
                for item in set(new_list) - set(old_list):
                    set_args.append(f"{k}+={item}")
                for item in set(old_list) - set(new_list):
                    set_args.append(f"{k}-={item}")
        else:
            old_s = str(old_v or "")
            new_s = str(new_v or "")
            if old_s != new_s:
                set_args.append(f"{k}={new_v}" if new_v else f"{k}=")
    new_note  = note if note != (old_note or "") else None
    return_to = request.form.get("return_to", "") or url_for("browse_get")
    if not set_args and new_note is None:
        return redirect(return_to)
    if not os.path.abspath(filepath).startswith(os.path.abspath(ptos.RECORDS_DIR)):
        return redirect(return_to)
    try:
        svc.edit_record(filepath, old_line,
                        set_args=set_args, new_note=new_note, lineno=lineno_int)
        return redirect(return_to)
    except PTOSError as e:
        try:
            schema = svc.get_schema()
        except Exception:
            schema = {}
        field_values = dict(new_record)
        field_values["date"] = date_str
        if note: field_values["note"] = note
        field_defs  = _build_field_defs(schema, rtype, field_values)
        ts = schema.get("type", {}).get(rtype, {})
        tag_options = ptos.resolve_tags(schema, ts, field_values)
        return render_template("edit.html",
            tab="browse", title="Edit Record", now=_now_str(),
            filepath=filepath, lineno=lineno_int, old_line=old_line,
            return_to=return_to,
            rtype=rtype, field_defs=field_defs,
            tag_options=tag_options, field_values=field_values,
            today=dt.date.today().isoformat(),
            msg=str(e), msg_type="error")


# ══════════════════════════════════════════════════════════════════════════════
# Edit / Delete API
# ══════════════════════════════════════════════════════════════════════════════

@app.route("/api/records/find", methods=["POST"])
def api_records_find():
    data   = request.get_json(silent=True) or {}
    expr   = data.get("expr", "").strip()
    where  = data.get("where", [])
    time   = data.get("time", "all")
    search = data.get("search", "") or None
    if isinstance(where, str):
        where = [where] if where.strip() else []
    if expr and where:
        combined = ptos._filters_to_expr(where)
        filters  = [f"({combined}) AND ({expr})"] if combined else [expr]
    elif expr:
        filters = [expr]
    elif where:
        filters = where
    else:
        return jsonify(ok=False, error="No filters provided")
    try:
        matches = svc.find_records(filters, time=time, search=search)
        return jsonify(ok=True, matches=matches)
    except PTOSError as e:
        return jsonify(ok=False, error=str(e))
    except Exception as e:
        return jsonify(ok=False, error=str(e))


@app.route("/api/records/edit", methods=["POST"])
def api_records_edit():
    data     = request.get_json(silent=True) or {}
    filepath = data.get("filepath", "")
    old_line = data.get("old_line", "")
    set_args = data.get("set", [])
    new_note = data.get("note", None)
    lineno   = data.get("lineno", None)
    if lineno is not None:
        try: lineno = int(lineno)
        except: lineno = None
    if not filepath or not old_line:
        return jsonify(ok=False, error="filepath and old_line required")
    if not os.path.abspath(filepath).startswith(os.path.abspath(ptos.RECORDS_DIR)):
        return jsonify(ok=False, error="Invalid filepath")
    try:
        result = svc.edit_record(filepath, old_line,
                                 set_args=set_args, new_note=new_note, lineno=lineno)
        return jsonify(ok=True, **result)
    except PTOSError as e:
        return jsonify(ok=False, error=str(e))
    except Exception as e:
        return jsonify(ok=False, error=str(e))


@app.route("/api/records/delete", methods=["POST"])
def api_records_delete():
    data     = request.get_json(silent=True) or {}
    filepath = data.get("filepath", "")
    old_line = data.get("old_line", "")
    lineno   = data.get("lineno", None)
    if lineno is not None:
        try: lineno = int(lineno)
        except: lineno = None
    if not filepath or not old_line:
        return jsonify(ok=False, error="filepath and old_line required")
    if not os.path.abspath(filepath).startswith(os.path.abspath(ptos.RECORDS_DIR)):
        return jsonify(ok=False, error="Invalid filepath")
    try:
        result = svc.delete_record(filepath, old_line, lineno=lineno)
        return jsonify(ok=True, **result)
    except PTOSError as e:
        return jsonify(ok=False, error=str(e))
    except Exception as e:
        return jsonify(ok=False, error=str(e))


# ══════════════════════════════════════════════════════════════════════════════
# API
# ══════════════════════════════════════════════════════════════════════════════

@app.route("/api/type_fields/<rtype>")
def api_type_fields(rtype):
    try:
        schema     = ptos.get_schema()
        bad        = ptos.non_dimension_fields()
        
        # Parse context from query param (e.g., ?context=domain:self,category:transport)
        context = {}
        ctx_str = request.args.get("context", "")
        if ctx_str:
            for pair in ctx_str.split(","):
                if ":" in pair:
                    k, v = pair.split(":", 1)
                    context[k.strip()] = v.strip()
        
        defs       = _build_field_defs(schema, rtype, context if context else None)
        
        # Add tag field with cascade options if type has tag triggers
        type_schema = schema.get("type", {}).get(rtype, {})
        tag_triggers = type_schema.get("tags", {})
        if tag_triggers:
            # Find the first/primary tag trigger (usually 'category')
            tag_parent = list(tag_triggers.keys())[0] if tag_triggers else None
            tag_options = []
            if tag_parent and tag_parent in context:
                tag_options = tag_triggers.get(tag_parent, {}).get("options", {}).get(context[tag_parent], [])
            defs.append({
                "name": "tag",
                "required": False,
                "options": tag_options,
                "is_int": False,
                "unit": "",
                "parent": tag_parent or "",
                "has_parent": bool(tag_parent),
                "is_parent": False,
                "is_tag_trigger": False,
                "is_condition_trigger": False,
                "show_when": {},
            })
        
        dimensions = [f["name"] for f in defs if f["name"] not in bad and not f.get("is_int")]
        history    = svc.get_history_suggestions(rtype)
        return jsonify(fields=defs, dimensions=dimensions,
                       history_tags=history["tags"],
                       history_fields=history["field_values"],
                       history_defaults=history["field_defaults"])
    except Exception as e:
        return jsonify(fields=[], dimensions=[], history_tags=[],
                       history_fields={}, history_defaults={}, error=str(e))


@app.route("/api/field_suggest/<rtype>/<field>/<path:value>")
def api_field_suggest(rtype, field, value):
    try:
        suggestions = svc.get_conditional_suggestions(rtype, field, value)
        return jsonify(ok=True, suggestions=suggestions)
    except Exception as e:
        return jsonify(ok=False, suggestions={}, error=str(e))


@app.route("/api/preset_add", methods=["POST"])
def api_preset_add():
    data     = request.get_json(silent=True) or {}
    name     = data.get("name", "").strip()
    date_str = data.get("date", dt.date.today().isoformat()).strip()
    note     = data.get("note", "").strip() or None
    if not name:
        return jsonify(ok=False, error="Preset name required")
    records, err = _resolve_multi_preset(name)
    if err:
        return jsonify(ok=False, error=err)
    added = []
    try:
        for record in records:
            line = ptos.build_record_line(date_str, record, note)
            svc.append_record(line)
            added.append(line)
    except Exception as e:
        return jsonify(ok=False, error=str(e))
    return jsonify(ok=True, added=added, count=len(added))


@app.route("/api/save_preset", methods=["POST"])
def api_save_preset():
    data   = request.get_json(silent=True) or {}
    name   = data.get("name","").strip().replace(" ","_").lower()
    record = data.get("record", {})
    note   = data.get("note","").strip() or None
    if not name:
        return jsonify(ok=False, error="Preset name cannot be empty")
    if not re.match(r'^[a-z0-9_]+$', name):
        return jsonify(ok=False, error="Name must be lowercase letters, numbers and underscores only")
    if not record.get("type"):
        return jsonify(ok=False, error="No record type in form — fill at least the type field")
    try:
        ptos._CACHE.pop("presets", None)
        ptos.save_as_preset(name, record, note=note)
        ptos._CACHE.pop("presets", None)
        return jsonify(ok=True, name=name)
    except PTOSError as e:
        return jsonify(ok=False, error=str(e))
    except Exception as e:
        return jsonify(ok=False, error=str(e))


@app.route("/shutdown", methods=["GET", "POST"])
def shutdown_server():
    def _exit():
        import time
        time.sleep(1)
        os._exit(0)
    import threading
    threading.Thread(target=_exit, daemon=True).start()
    response = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>PTOS Stopped</title>
        <style>
            body { font-family: system-ui, sans-serif; display: flex; align-items: center; justify-content: center; height: 100vh; margin: 0; background: #1a1a1a; color: #888; }
            h1 { color: #4a4a4a; margin-bottom: 10px; }
        </style>
    </head>
    <body>
        <div style="text-align:center">
            <h1>Server stopped</h1>
            <p>You can close this tab.</p>
        </div>
    </body>
    </html>
    """
    from flask import make_response
    r = make_response(response)
    return r


@app.route("/api/save_query", methods=["POST"])
def api_save_query():
    data    = request.get_json(silent=True) or {}
    name    = data.get("name","").strip().replace(" ","_").lower()
    expr    = data.get("expr","").strip()
    where   = data.get("where", [])
    time    = data.get("time", "tm")
    group   = data.get("group", "") or None
    sort    = data.get("sort", "") or None
    search  = data.get("search", "") or None
    if isinstance(where, str):
        where = [where] if where.strip() else []
    if expr and where:
        combined   = ptos._filters_to_expr(where)
        where_expr = f"({combined}) AND ({expr})" if combined else expr
    elif expr:
        where_expr = expr
    elif where:
        where_expr = ptos._filters_to_expr(where)
    else:
        where_expr = ""
    try:
        result = svc.save_query(name, where_expr, time=time, group=group, search=search, sort=sort)
        return jsonify(ok=True, name=result["name"])
    except PTOSError as e:
        return jsonify(ok=False, error=str(e))
    except Exception as e:
        return jsonify(ok=False, error=str(e))


# ══════════════════════════════════════════════════════════════════════════════
# Run
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    # Auto-backup on startup (only if no backup exists from today)
    try:
        backups = svc.list_backups()
        today = dt.date.today().isoformat()
        has_today = any(mtime.date().isoformat() == today for _, mtime, _ in backups)
        if not has_today:
            result = svc.backup_full()
            print(f"Auto-backup created: {os.path.basename(result['path'])}")
        else:
            print("Auto-backup skipped: backup from today already exists")
    except Exception as e:
        print(f"Auto-backup skipped: {e}")
    
    print("\nPTOS Web UI")
    print("Open: http://localhost:5000\n")
    app.run(debug=False, host="127.0.0.1", port=5000)
