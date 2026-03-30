"""
ptos_web.py  —  Flask web UI for PTOS (mobile-first, responsive)
Place alongside ptos.py and ptos_service.py.
Run:  python ptos_web.py   →  http://localhost:5000
"""

import sys, os, datetime as dt, json, csv, tempfile
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


# ══════════════════════════════════════════════════════════════════════════════
# Home
# ══════════════════════════════════════════════════════════════════════════════

@app.route("/")
def home():
    try: schema = ptos.get_schema()
    except: schema = {}
    presets = {k: v for k, v in ptos.get_presets().items()
               if not (isinstance(v, dict) and ("alias" in v or "records" in v))}

    # due list
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
    where  = data.get("where",[])
    time   = data.get("time","tm")
    search = data.get("search","") or None
    group  = data.get("group","") or None
    sort   = data.get("sort","") or None
    file   = data.get("file","") or None
    try:
        if group:
            result = svc.get_group(where, time, [group], from_file=file)
            result["kind"] = "group"
        else:
            result = svc.get_records(where, time, search=search,
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
    where  = params.get("where",[])
    time   = params.get("time","tm")
    search = params.get("search","") or None
    file   = params.get("file","") or None
    try:
        data = svc.get_records(where, time, search=search, from_file=file)
        records = data["records"]
        cols    = data["columns"]
        tl      = _TIME_DICT.get(time, time)
        type_part = next((f.split("=")[1] for f in where if f.startswith("type=")),"records")
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


# ══════════════════════════════════════════════════════════════════════════════
# Run
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("\nPTOS Web UI")
    print("Open: http://localhost:5000\n")
    app.run(debug=False, host="127.0.0.1", port=5000)
