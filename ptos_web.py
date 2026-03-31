"""
ptos_web.py  —  Flask web UI for PTOS (mobile-first, responsive)
Place alongside ptos.py and ptos_service.py.
Run:  python ptos_web.py   →  http://localhost:5000
"""

import sys, os, re, datetime as dt, json, csv, tempfile
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import ptos_service as svc
from ptos_service import PTOSError
import ptos

from flask import (Flask, render_template, request, redirect,
                   url_for, jsonify, send_file)

app = Flask(__name__, template_folder="web_templates")
app.secret_key = "ptos-local-only"

TIME_OPTIONS = [
    ("Today","td"),("Yesterday","yd"),("This week","tw"),("Last week","lw"),
    ("This month","tm"),("Last month","lm"),("This quarter","tq"),
    ("Last quarter","lq"),("This year","ty"),("Last year","ly"),("All time","all"),
]
_TIME_DICT = dict(TIME_OPTIONS)

def _now_str():
    return dt.datetime.now().strftime("%a %d %b")

def _greeting():
    h = dt.datetime.now().hour
    return "morning" if h < 12 else "afternoon" if h < 17 else "evening"

def _build_field_defs(schema, rtype, current_record=None):
    if not rtype: return []
    type_schema = schema.get("type", {}).get(rtype, {})
    required    = type_schema.get("required", [])
    all_fields  = list(required)
    for f in type_schema.get("fields", {}):
        if f not in all_fields: all_fields.append(f)
    for f in type_schema.get("conditions", {}):
        if f not in all_fields: all_fields.append(f)

    # collect which fields trigger tags and which are parents of other fields
    parent_fields  = {
        fd.get("parent")
        for fd in type_schema.get("fields", {}).values()
        if isinstance(fd, dict) and fd.get("parent")
    }
    tag_triggers = set(type_schema.get("tags", {}).keys())

    defs   = []
    record = current_record or {}
    for fname in all_fields:
        if fname == "tag": continue
        field_meta = schema.get("fields", {}).get(fname, {})
        is_int     = isinstance(field_meta, dict) and field_meta.get("type") == "int"
        unit       = field_meta.get("unit", "") if isinstance(field_meta, dict) else ""
        field_def  = type_schema.get("fields", {}).get(fname, {})
        parent     = field_def.get("parent")
        has_parent = bool(parent)
        is_parent      = fname in parent_fields
        is_tag_trigger = fname in tag_triggers

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
            "is_parent":      is_parent,
            "is_tag_trigger": is_tag_trigger,
        })
    return defs

def _resolve_multi_preset(name):
    """Resolve a multi-record preset to a list of record dicts.
    Returns (records, error_str) — error_str is None if all records are complete.
    A preset is considered complete if all its fields are specified
    (no schema-required fields missing).
    """
    presets = ptos.get_presets()
    pd = presets.get(name, {})
    if isinstance(pd, dict) and "alias" in pd:
        pd = presets.get(pd["alias"], {})
    if not isinstance(pd, dict) or "records" not in pd:
        return None, f"'{name}' is not a multi-record preset"
    try:
        schema = ptos.get_schema()
    except Exception as e:
        return None, str(e)
    resolved = []
    for item in pd["records"]:
        if not isinstance(item, str):
            return None, f"records list must contain preset names"
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
    """Return dict of multi-record presets that are fully specified (no missing fields)."""
    result = {}
    for name, p in ptos.get_presets().items():
        if not isinstance(p, dict) or "records" not in p:
            continue
        records, err = _resolve_multi_preset(name)
        if records is not None:
            refs = p["records"]
            result[name] = ", ".join(refs) if isinstance(refs, list) else ""
    return result




@app.route("/")
def home():
    try: schema = ptos.get_schema()
    except: schema = {}
    presets = {k: v for k, v in ptos.get_presets().items()
               if not (isinstance(v, dict) and ("alias" in v or "records" in v))}
    multi_presets = _multi_presets()
    try:
        due_data  = svc.get_due()
        due_rows  = due_data["rows"]
        due_count = due_data["count"]
    except Exception:
        due_rows = []; due_count = 0

    # dashboard stats
    stats = []
    try:
        queries    = ptos.get_queries()
        dashboards = queries.get("dashboards", {})
        db_name    = next((n for n in ("home","monthly","clinic") if n in dashboards),
                          next(iter(dashboards), None))
        if db_name:
            db = svc.get_dashboard(db_name, "tm")
            for item in db["items"][:4]:
                stats.append({"label": item["name"].replace("_"," "),
                               "value": item["value"], "sub": "this month"})
    except Exception:
        pass

    # recent records
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
        schema = ptos.get_schema()
    except PTOSError:
        schema = {"types": {"allowed": []}}
    types   = schema.get("types", {}).get("allowed", [])
    presets = {k: v for k, v in ptos.get_presets().items()
               if not (isinstance(v, dict) and ("alias" in v or "records" in v))}
    multi_presets = _multi_presets()
    selected_type = request.args.get("type", "")
    preset_name   = request.args.get("preset", "")
    field_values  = {k: v for k, v in request.args.items()
                     if k not in ("type","preset","date")}
    if "tag" in request.args:
        field_values["tag"] = request.args.getlist("tag")
    if preset_name and not selected_type:
        pd = ptos.get_presets().get(preset_name, {})
        if isinstance(pd, dict) and "alias" in pd:
            pd = ptos.get_presets().get(pd["alias"], {})
        if pd:
            selected_type = pd.get("type", "")
            for k, v in pd.items():
                if k != "type" and k not in field_values: field_values[k] = v
    field_defs  = _build_field_defs(schema, selected_type, field_values)
    tag_options = []
    if selected_type:
        ts = schema.get("type", {}).get(selected_type, {})
        tag_options = ptos.resolve_tags(schema, ts, field_values)
    return render_template("add.html",
        tab="add", title="Add Record", now=_now_str(),
        types=types, presets=sorted(presets.keys()),
        multi_presets=multi_presets,
        selected_type=selected_type, field_defs=field_defs,
        tag_options=tag_options, field_values=field_values,
        today=dt.date.today().isoformat(),
        msg=None, msg_type=None, last_line=None)

@app.route("/add", methods=["POST"])
def add_post():
    try:
        schema = ptos.get_schema()
    except PTOSError:
        schema = {"types": {"allowed": []}}
    types  = schema.get("types", {}).get("allowed", [])
    presets = {k: v for k, v in ptos.get_presets().items()
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
            selected_type=rtype, field_defs=fd,
            tag_options=ptos.resolve_tags(schema, ts, record),
            field_values=record, today=dt.date.today().isoformat(),
            msg=" | ".join(problems), msg_type="error", last_line=None)
    try:
        line = ptos.build_record_line(date_str, record, note)
        ptos.append_record(line)
    except PTOSError as e:
        fd = _build_field_defs(schema, rtype, record)
        return render_template("add.html",
            tab="add", title="Add Record", now=_now_str(),
            types=types, presets=sorted(presets.keys()),
            selected_type=rtype, field_defs=fd,
            tag_options=ptos.resolve_tags(schema, ts, record),
            field_values=record, today=dt.date.today().isoformat(),
            msg=str(e), msg_type="error", last_line=None)
    return render_template("add.html",
        tab="add", title="Add Record", now=_now_str(),
        types=types, presets=sorted(presets.keys()),
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
    ptos._backup_file(path)
    with open(path,"w",encoding="utf-8") as f: f.write(content)
    return jsonify(ok=True)


# ══════════════════════════════════════════════════════════════════════════════
# Queries
# ══════════════════════════════════════════════════════════════════════════════

@app.route("/queries")
def queries_get():
    try:    all_q = ptos.get_queries()
    except: all_q = {}
    named = [k for k in all_q
             if k not in ("metrics","dashboards","due")
             and not (isinstance(all_q[k], dict) and "alias" in all_q[k])]
    return render_template("queries.html",
        tab="queries", title="Queries", now=_now_str(),
        queries=named,
        metrics=list(all_q.get("metrics",{}).keys()),
        dashboards=list(all_q.get("dashboards",{}).keys()),
        time_options=TIME_OPTIONS)

@app.route("/queries/run", methods=["POST"])
def queries_run():
    data = request.get_json(silent=True) or {}
    kind = data.get("kind","q")
    name = data.get("name","")
    time = data.get("time","") or None
    try:
        if kind == "d":
            result = svc.get_dashboard(name, time or "tm")
            result["kind"] = "dashboard"
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
        schema = ptos.get_schema()
        types  = schema.get("types",{}).get("allowed",[])
    except PTOSError as e:
        types = []
    log_files = sorted(f for f in os.listdir(ptos.RECORDS_DIR)
                       if f.endswith(".log")) if os.path.exists(ptos.RECORDS_DIR) else []
    return render_template("browse.html",
        tab="browse", title="Browse", now=_now_str(),
        types=types, log_files=log_files, time_options=TIME_OPTIONS)

@app.route("/browse/run", methods=["POST"])
def browse_run():
    data   = request.get_json(silent=True) or {}
    time   = data.get("time","tm")
    search = data.get("search","") or None
    group  = data.get("group","") or None
    sort   = data.get("sort","") or None
    file   = data.get("file","") or None

    # Accept both formats:
    #   expr  (string) — expression from expression input bar
    #   where (list)   — legacy field-level dropdown filters
    # Merge into a single filter list for the service layer.
    expr  = data.get("expr","").strip()
    where = data.get("where",[])
    if isinstance(where, str):
        where = [where] if where.strip() else []

    # Build unified filter list
    if expr and where:
        # combine: wrap existing conditions with AND
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
        cols    = data["columns"]
        tl      = _TIME_DICT.get(time, time)
        # derive type label from expression for filename
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
    log_files = sorted(f for f in os.listdir(ptos.RECORDS_DIR)
                       if f.endswith(".log")) if os.path.exists(ptos.RECORDS_DIR) else []
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
    ptos._backup_file(path)
    with open(path,"w",encoding="utf-8") as f: f.write(content)
    return jsonify(ok=True)


# ══════════════════════════════════════════════════════════════════════════════
# API
# ══════════════════════════════════════════════════════════════════════════════

@app.route("/api/type_fields/<rtype>")
def api_type_fields(rtype):
    try:
        schema     = ptos.get_schema()
        bad        = ptos.non_dimension_fields()
        defs       = _build_field_defs(schema, rtype)
        dimensions = [f["name"] for f in defs if f["name"] not in bad and f["options"]]
        return jsonify(fields=defs, dimensions=dimensions)
    except Exception as e:
        return jsonify(fields=[], dimensions=[], error=str(e))


@app.route("/api/preset_add", methods=["POST"])
def api_preset_add():
    """Add all records from a multi-record preset in one shot."""
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
            ptos.append_record(line)
            added.append(line)
    except Exception as e:
        return jsonify(ok=False, error=str(e))

    return jsonify(ok=True, added=added, count=len(added))



@app.route("/api/save_preset", methods=["POST"])
def api_save_preset():
    """Save current add-record form state as a preset."""
    data   = request.get_json(silent=True) or {}
    name   = data.get("name","").strip().replace(" ","_").lower()
    record = data.get("record", {})

    if not name:
        return jsonify(ok=False, error="Preset name cannot be empty")
    if not re.match(r'^[a-z0-9_]+$', name):
        return jsonify(ok=False, error="Name must be lowercase letters, numbers and underscores only")

    existing = ptos.get_presets()
    if name in existing:
        return jsonify(ok=False, error=f"Preset '{name}' already exists")
    if not record.get("type"):
        return jsonify(ok=False, error="No record type in form — fill at least the type field")

    try:
        ptos._CACHE.pop("presets", None)   # invalidate cache before write
        ptos.save_as_preset(name, record)
        ptos._CACHE.pop("presets", None)   # invalidate cache after write
        return jsonify(ok=True, name=name)
    except PTOSError as e:
        return jsonify(ok=False, error=str(e))
    except Exception as e:
        return jsonify(ok=False, error=str(e))


@app.route("/api/save_query", methods=["POST"])
def api_save_query():
    """Save current browse filter state as a named query in queries.toml."""
    data    = request.get_json(silent=True) or {}
    name    = data.get("name","").strip().replace(" ","_").lower()
    expr    = data.get("expr","").strip()      # expression string from expr bar
    where   = data.get("where", [])            # legacy list from dropdowns
    time    = data.get("time", "tm")
    group   = data.get("group", "") or None
    search  = data.get("search", "") or None

    if isinstance(where, str):
        where = [where] if where.strip() else []

    # Build unified expression string
    if expr and where:
        combined = ptos._filters_to_expr(where)
        where_expr = f"({combined}) AND ({expr})" if combined else expr
    elif expr:
        where_expr = expr
    elif where:
        where_expr = ptos._filters_to_expr(where)
    else:
        where_expr = ""

    try:
        result = svc.save_query(
            name, where_expr, time=time,
            group=group, search=search
        )
        return jsonify(ok=True, name=result["name"])
    except PTOSError as e:
        return jsonify(ok=False, error=str(e))
    except Exception as e:
        return jsonify(ok=False, error=str(e))


# ══════════════════════════════════════════════════════════════════════════════
# Edit / Delete
# ══════════════════════════════════════════════════════════════════════════════

@app.route("/api/records/find", methods=["POST"])
def api_records_find():
    """Find records matching filters for edit/delete UI.
    Body: {expr: str, where: [str], time: str, search: str}
    Returns: {ok, matches: [{filepath, filename, line, parsed}]}
    """
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
    """Edit one record in place.
    Body: {filepath, old_line, set: ["key=val", ...], note: str|null}
    Returns: {ok, old_line, new_line, changed_date}
    """
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
    """Delete one record.
    Body: {filepath, old_line}
    Returns: {ok, deleted_line}
    """
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
# Run
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("\nPTOS Web UI")
    print("Open: http://localhost:5000\n")
    app.run(debug=False, host="127.0.0.1", port=5000)
