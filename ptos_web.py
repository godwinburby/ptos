"""
ptos_web.py  —  Flask web UI for PTOS  (mobile-first, responsive)
Place in the same folder as ptos.py.
Run:  python ptos_web.py
Open: http://localhost:5000
"""

import sys, os, io, datetime as dt, json, csv, tempfile

# ── patch sys.exit so ptos never kills the Flask process ─────────────────────
class PTOSError(Exception): pass
def _safe_exit(msg=""): raise PTOSError(str(msg))
sys.exit = _safe_exit
# ─────────────────────────────────────────────────────────────────────────────

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ptos

from flask import Flask, render_template, request, redirect, url_for, jsonify, send_file
app = Flask(__name__, template_folder="web_templates")
app.secret_key = "ptos-local-only"

TIME_OPTIONS = [
    ("Today","td"),("Yesterday","yd"),("This week","tw"),("Last week","lw"),
    ("This month","tm"),("Last month","lm"),("This quarter","tq"),
    ("Last quarter","lq"),("This year","ty"),("Last year","ly"),("All time","all"),
]
_TIME_DICT = dict(TIME_OPTIONS)

def _cycles():
    return ptos.get_config().get("cycles", {})

def _now_str():
    return dt.datetime.now().strftime("%a %d %b")

def _greeting():
    h = dt.datetime.now().hour
    return "morning" if h < 12 else "afternoon" if h < 17 else "evening"

def _capture(fn, *args, **kwargs):
    buf = io.StringIO(); old = sys.stdout; sys.stdout = buf
    try:    fn(*args, **kwargs)
    except (PTOSError, Exception): pass
    finally: sys.stdout = old
    return buf.getvalue()

def _resolve_time(code):
    try:    return ptos.resolve_time(code or "tm", _cycles())
    except: return dt.date.min, dt.date.max

def _build_field_defs(schema, rtype, current_record=None):
    if not rtype: return []
    type_schema = schema.get("type", {}).get(rtype, {})
    required    = type_schema.get("required", [])
    all_fields  = list(required)
    for f in type_schema.get("fields", {}):
        if f not in all_fields: all_fields.append(f)
    for f in type_schema.get("conditions", {}):
        if f not in all_fields: all_fields.append(f)
    defs   = []
    record = current_record or {}
    for fname in all_fields:
        if fname == "tag": continue
        field_meta = schema.get("fields", {}).get(fname, {})
        is_int  = isinstance(field_meta, dict) and field_meta.get("type") == "int"
        unit    = field_meta.get("unit", "") if isinstance(field_meta, dict) else ""
        field_def = type_schema.get("fields", {}).get(fname, {})
        parent  = field_def.get("parent")
        if parent:
            options = ptos.resolve_options_for_value(type_schema, fname, record.get(parent,""))
        else:
            options = ptos.resolve_options(schema, type_schema, fname) or []
        defs.append({"name":fname,"required":fname in required,
                     "options":options,"is_int":is_int,"unit":unit,"parent":parent or ""})
    return defs

def _due_rows(days_override=None):
    """Return list of due row dicts for home and due pages."""
    try:
        queries = ptos.get_queries()
        due_cfg = queries.get("due")
        if not due_cfg: return []
        rtype    = due_cfg.get("type")
        key_fld  = due_cfg.get("key")
        days     = days_override if days_override is not None else int(due_cfg.get("days", 7))
        sort_fld = due_cfg.get("sort_by")
        exclude  = due_cfg.get("exclude_results", [])
        if not rtype or not key_fld: return []

        priority = {}
        if sort_fld:
            schema    = ptos.get_schema()
            type_meta = schema.get("type", {}).get(rtype, {})
            options   = type_meta.get("fields", {}).get(sort_fld, {}).get("options", [])
            if isinstance(options, list):
                priority = {v: i for i, v in enumerate(options)}

        results, _ = ptos.scan_records(dt.date.min, dt.date.max, [f"type={rtype}"], None)
        latest = {}
        for line in results:
            parsed = ptos.safe_parse_line(line)
            if not parsed: continue
            d, kv, note = parsed
            k = kv.get(key_fld)
            if not k: continue
            if k not in latest or d > latest[k]["date"]:
                latest[k] = {"date": d, "kv": kv, "note": note}
        if exclude:
            latest = {k: r for k, r in latest.items()
                      if r["kv"].get("result") not in exclude}
        cutoff  = ptos.today() - dt.timedelta(days=days)
        overdue = [r for r in latest.values() if r["date"] <= cutoff]
        overdue.sort(key=lambda r: (
            priority.get(r["kv"].get(sort_fld,""), 999) if sort_fld else 0,
            r["date"]
        ))
        rows = []
        for rec in overdue:
            kv  = rec["kv"]
            gap = (ptos.today() - rec["date"]).days
            heat = "hot" if gap >= 7 else "warm" if gap >= 3 else "cool"
            rows.append({
                "days":   gap,
                "name":   kv.get("name", kv.get(key_fld, "-")),
                "status": kv.get(sort_fld, "") if sort_fld else "",
                "note":   rec["note"] or "",
                "heat":   heat,
            })
        return rows
    except Exception:
        return []


# ══════════════════════════════════════════════════════════════════════════════
# Home
# ══════════════════════════════════════════════════════════════════════════════

@app.route("/")
def home():
    try: schema = ptos.get_schema()
    except: schema = {}
    presets = {k: v for k, v in ptos.get_presets().items()
               if not (isinstance(v, dict) and ("alias" in v or "records" in v))}

    due_rows = _due_rows()
    due_count = len(due_rows)

    # build stat cards from saved queries in queries.toml [dashboards.home] or first dashboard
    stats = []
    try:
        queries    = ptos.get_queries()
        dashboards = queries.get("dashboards", {})
        # pick first dashboard or one named "home"/"monthly"
        db_name = next((n for n in ("home","monthly","clinic") if n in dashboards),
                       next(iter(dashboards), None))
        if db_name:
            cycles = _cycles()
            start, end = _resolve_time("tm")
            for item in dashboards[db_name].get("metrics", [])[:3]:
                metrics = queries.get("metrics", {})
                if item in metrics:
                    m = metrics[item]
                    if "ratio" in m:
                        c1,_ = _run_base(m["ratio"][0], queries, start, end)
                        c2,_ = _run_base(m["ratio"][1], queries, start, end)
                        val = f"{(c1/c2)*100:.0f}%" if c2 else "—"
                    elif "avg" in m:
                        cnt,tot = _run_base(m["avg"], queries, start, end)
                        val = ptos.fmt_avg(tot/cnt) if cnt else "—"
                    elif "sum" in m:
                        _,tot = _run_base(m["sum"], queries, start, end)
                        val = ptos.fmt(tot)
                    else: val = "—"
                    stats.append({"label": item.replace("_"," "), "value": val, "sub": "this month"})
                elif item in queries:
                    cnt, tot = _run_base(item, queries, start, end)
                    val = str(cnt)
                    sub = ptos.fmt(tot) if tot > 0 else "this month"
                    stats.append({"label": item.replace("_"," "), "value": val, "sub": sub})
    except Exception:
        pass

    # recent records (last 5 lines of current year log)
    recent = ""
    try:
        path = os.path.join(ptos.RECORDS_DIR, f"{ptos.today().year}.log")
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                lines = [l.rstrip() for l in f if l.strip()]
            recent = "\n".join(lines[-5:])
    except Exception:
        pass

    return render_template("home.html",
        tab="home", title="Home", now=_now_str(),
        greeting=_greeting(),
        presets=sorted(presets.keys())[:8],
        due_count=due_count,
        due_rows=due_rows[:5],
        stats=stats,
        recent=recent)

def _run_base(name, queries, start, end):
    q = queries.get(name, {})
    f = q.get("where","").split() if isinstance(q, dict) else []
    try:
        if isinstance(q, dict) and "time" in q:
            s, e = _resolve_time(q["time"])
        else:
            s, e = start, end
        results, total = ptos.scan_records(s, e, f, None)
        return len(results), total
    except Exception:
        return 0, 0


# ══════════════════════════════════════════════════════════════════════════════
# Due List
# ══════════════════════════════════════════════════════════════════════════════

@app.route("/due")
def due_page():
    days = request.args.get("days", None)
    days_int = int(days) if days is not None else None
    try:
        queries = ptos.get_queries()
        due_cfg = queries.get("due")
        if not due_cfg:
            return render_template("due.html", tab="due", title="Due List",
                now=_now_str(), rows=[], days=7,
                error="No [due] config in queries.toml")
        default_days = int(due_cfg.get("days", 7))
        days_used = days_int if days_int is not None else default_days
        rows = _due_rows(days_override=days_used)
    except Exception as e:
        rows = []
        days_used = 7
    return render_template("due.html", tab="due", title="Due List",
        now=_now_str(), rows=rows, days=days_used, error=None)


# ══════════════════════════════════════════════════════════════════════════════
# Add Record
# ══════════════════════════════════════════════════════════════════════════════

@app.route("/add", methods=["GET"])
def add_get():
    schema  = ptos.get_schema()
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
                if k != "type" and k not in field_values:
                    field_values[k] = v

    field_defs  = _build_field_defs(schema, selected_type, field_values)
    tag_options = []
    if selected_type:
        ts = schema.get("type", {}).get(selected_type, {})
        tag_options = ptos.resolve_tags(schema, ts, field_values)

    return render_template("add.html",
        tab="add", title="Add Record", now=_now_str(),
        types=types, presets=sorted(presets.keys()),
        selected_type=selected_type,
        field_defs=field_defs, tag_options=tag_options,
        field_values=field_values,
        today=dt.date.today().isoformat(),
        msg=None, msg_type=None, last_line=None)


@app.route("/add", methods=["POST"])
def add_post():
    schema = ptos.get_schema()
    types  = schema.get("types", {}).get("allowed", [])
    presets = {k: v for k, v in ptos.get_presets().items()
               if not (isinstance(v, dict) and ("alias" in v or "records" in v))}

    rtype      = request.form.get("type","").strip()
    date_str   = request.form.get("date", dt.date.today().isoformat()).strip()
    note       = request.form.get("note","").strip() or None
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
        fd  = _build_field_defs(schema, rtype, record)
        tag_opts = ptos.resolve_tags(schema, ts, record)
        return render_template("add.html",
            tab="add", title="Add Record", now=_now_str(),
            types=types, presets=sorted(presets.keys()),
            selected_type=rtype, field_defs=fd, tag_options=tag_opts,
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
    data    = request.get_json(silent=True) or {}
    date    = data.get("date", dt.date.today().isoformat())
    content = data.get("content","")
    try:    dt.date.fromisoformat(date)
    except: return jsonify(ok=False, error="Invalid date")
    year_dir = os.path.join(ptos.JOURNAL_DIR, date[:4])
    os.makedirs(year_dir, exist_ok=True)
    path = os.path.join(year_dir, f"{date}.md")
    ptos._backup_file(path)
    with open(path, "w", encoding="utf-8") as f: f.write(content)
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
    data  = request.get_json(silent=True) or {}
    kind  = data.get("kind","q")
    name  = data.get("name","")
    time  = data.get("time","")
    try:
        queries = ptos.get_queries()
        cycles  = _cycles()
        start, end = _resolve_time(time) if time else _resolve_time("tm")

        if kind == "d":
            if not time:
                db  = queries.get("dashboards",{}).get(name,{})
                start, end = _resolve_time(db.get("time","tm") if isinstance(db,dict) else "tm")
            result = _capture(ptos.run_dashboard, name, queries, start, end, cycles)
        elif kind == "m":
            result = _capture(ptos.run_metric, name, queries, start, end, cycles)
        else:
            q_def   = queries.get(name, {})
            if not isinstance(q_def, dict):
                return jsonify(result=f"Query '{name}' not found.")
            if not time:
                start, end = _resolve_time(q_def.get("time","tm"))
            filters = q_def.get("where","").split()
            results, total = ptos.scan_records(start, end, filters, None)
            if not results:
                return jsonify(result="No records found.")
            out = io.StringIO(); old = sys.stdout; sys.stdout = out
            if "group" in q_def:
                ptos.render_summary(results,start,end,time or q_def.get("time","tm"),filters,total)
                c,s,h = ptos.group_results(results, q_def["group"])
                ptos.render_group(c,s,h,q_def["group"])
            elif "pivot" in q_def and len(q_def["pivot"]) >= 2:
                row,col = q_def["pivot"][:2]
                ptos.render_summary(results,start,end,time or q_def.get("time","tm"),filters,total)
                t2,cols2,rows2 = ptos.pivot_results(results,row,col,q_def.get("count",False))
                ptos.render_pivot(t2,cols2,rows2,row)
            elif q_def.get("trend"):
                sys.stdout = old
                return jsonify(result=_capture(ptos.run_trend,filters,
                               q_def.get("time","tm"),int(q_def["trend"]),cycles))
            else:
                ptos.render_summary(results,start,end,time or q_def.get("time","tm"),filters,total)
                for line in results: print(line)
            sys.stdout = old
            result = out.getvalue()
    except (PTOSError, Exception) as e:
        result = f"Error: {e}"
    return jsonify(result=result)


# ══════════════════════════════════════════════════════════════════════════════
# Browse
# ══════════════════════════════════════════════════════════════════════════════

@app.route("/browse")
def browse_get():
    schema    = ptos.get_schema()
    types     = schema.get("types",{}).get("allowed",[])
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
    group  = data.get("group","")
    sort   = data.get("sort","") or None
    file   = data.get("file","") or None
    try:
        start, end = _resolve_time(time)
        results, total = ptos.scan_records(start, end, where, search, from_file=file)
        if not results: return jsonify(result="No records found.")
        out = io.StringIO(); old = sys.stdout; sys.stdout = out
        tl  = _TIME_DICT.get(time, time)
        if group:
            ptos.render_summary(results,start,end,tl,where,total)
            c,s,h = ptos.group_results(results,[group])
            print(f"\nGrouped by: {group}\n")
            ptos.render_group(c,s,h,[group])
        else:
            if sort:
                def sk(line):
                    p = ptos.safe_parse_line(line)
                    if not p: return (1,0,"")
                    v = p[1].get(sort,"")
                    if isinstance(v,list): v = v[0] if v else ""
                    try:    return (0,int(v),"")
                    except: return (1,0,str(v).lower())
                results = sorted(results, key=sk)
            for line in results: print(line)
            ptos.render_summary(results,start,end,tl,where,total)
        sys.stdout = old
        result = out.getvalue()
    except (PTOSError, Exception) as e:
        result = f"Error: {e}"
    return jsonify(result=result)

@app.route("/browse/export", methods=["POST"])
def browse_export():
    params = json.loads(request.form.get("params","{}"))
    where  = params.get("where",[])
    time   = params.get("time","tm")
    search = params.get("search","") or None
    file   = params.get("file","") or None
    try:
        start, end = _resolve_time(time)
        results, _ = ptos.scan_records(start, end, where, search, from_file=file)
        tl = _TIME_DICT.get(time, time)
        tmp = tempfile.NamedTemporaryFile(mode="w",suffix=".csv",delete=False,
                                          encoding="utf-8",newline="")
        type_part = next((f.split("=")[1] for f in where if f.startswith("type=")),"records")
        filename  = f"{type_part}_{tl}.csv"
        cols = ["date"]; seen = {"date"}
        for line in results:
            p = ptos.safe_parse_line(line)
            if p:
                for k in p[1]:
                    if k not in seen: cols.append(k); seen.add(k)
        has_note = any(ptos.safe_parse_line(l) and ptos.safe_parse_line(l)[2] for l in results)
        if has_note: cols.append("note")
        writer = csv.DictWriter(tmp, fieldnames=cols)
        writer.writeheader()
        for line in results:
            p = ptos.safe_parse_line(line)
            if not p: continue
            d,kv,note = p
            row = {"date":str(d)}
            for k,v in kv.items(): row[k] = ",".join(v) if isinstance(v,list) else str(v)
            if has_note: row["note"] = note or ""
            writer.writerow(row)
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
    current   = request.args.get("file","")
    if not current and log_files: current = log_files[-1]
    content = ""
    if current:
        path = os.path.join(ptos.RECORDS_DIR, current)
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f: content = f.read()
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
    print("\nPTOS Web UI  —  mobile-first, responsive")
    print("Open: http://localhost:5000\n")
    app.run(debug=False, host="127.0.0.1", port=5000)
