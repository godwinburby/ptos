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
    ("Custom","custom"),
]
_TIME_DICT = dict(TIME_OPTIONS)
_VALID_TIME = {code for _, code in TIME_OPTIONS}
_YEAR_RANGE = list(range(dt.date.today().year - 10, dt.date.today().year + 1))

def _now_str():
    return dt.datetime.now().strftime("%a %d %b")

def _greeting():
    h = dt.datetime.now().hour
    return "morning" if h < 12 else "afternoon" if h < 17 else "evening"

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
    for name, p in ptos.get_presets().items():
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
    stats = []
    try:
        queries    = ptos.get_queries()
        dashboards = queries.get("dashboards", {})
        cfg        = ptos.get_config()
        default_db = cfg.get("dashboard", {}).get("default")
        # Use query param if provided, otherwise use config default, fallback to first
        db_name = request.args.get("dashboard", default_db or next(iter(dashboards), None))
        
        # Get time window from query param, default to this month
        time_code = request.args.get("time", "tm")
        if time_code == "custom":
            custom_time = request.args.get("custom_time", "")
            if custom_time and re.match(r"\d{4}-\d{2}", custom_time):
                time_code = custom_time
        
        cycles = cfg.get("cycles", {})
        if db_name and db_name in dashboards:
            db = svc.get_dashboard(db_name, time_code)
            # Show all dashboard items in home (no limit, template handles display)
            for item in db["items"]:
                stats.append({"label": item["name"].replace("_"," "),
                               "value": item["value"], "sub": "this month"})
    except Exception:
        pass
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
        time_options=TIME_OPTIONS,
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
            multi_presets=_multi_presets(),
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
        time_options=TIME_OPTIONS, year_range=_YEAR_RANGE,
        current_time=request.args.get("time", ""),
        custom_time=request.args.get("custom_time", ""))

@app.route("/queries/run", methods=["POST"])
def queries_run():
    data = request.get_json(silent=True) or {}
    kind = data.get("kind","q")
    name = data.get("name","")
    raw_time = data.get("time","") or None
    # reject any value that is not a known alias and not a valid YYYY-MM
    if raw_time and raw_time not in _VALID_TIME and \
       not re.fullmatch(r"\d{4}-\d{2}", raw_time):
        return jsonify(ok=False, error=f"Invalid time window: {raw_time}")
    time = raw_time
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
    except PTOSError:
        types = []
    log_files = sorted(f for f in os.listdir(ptos.RECORDS_DIR)
                       if f.endswith(".log")) if os.path.exists(ptos.RECORDS_DIR) else []
    return render_template("browse.html",
        tab="browse", title="Browse", now=_now_str(),
        types=types, log_files=log_files, time_options=TIME_OPTIONS, year_range=_YEAR_RANGE,
        current_time=request.args.get("time", "tm"),
        custom_time=request.args.get("custom_time", ""))

@app.route("/browse/run", methods=["POST"])
def browse_run():
    data   = request.get_json(silent=True) or {}
    raw_time = data.get("time","tm")
    if raw_time and raw_time not in _VALID_TIME and \
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
        schema = ptos.get_schema()
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
        schema = ptos.get_schema()
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
            schema = ptos.get_schema()
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
        defs       = _build_field_defs(schema, rtype)
        dimensions = [f["name"] for f in defs if f["name"] not in bad and f["options"]]
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
            ptos.append_record(line)
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


@app.route("/api/save_query", methods=["POST"])
def api_save_query():
    data    = request.get_json(silent=True) or {}
    name    = data.get("name","").strip().replace(" ","_").lower()
    expr    = data.get("expr","").strip()
    where   = data.get("where", [])
    time    = data.get("time", "tm")
    group   = data.get("group", "") or None
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
        result = svc.save_query(name, where_expr, time=time, group=group, search=search)
        return jsonify(ok=True, name=result["name"])
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
