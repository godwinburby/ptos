"""
ptos_web.py  —  Flask web UI for PTOS
Place in the same folder as ptos.py.
Run:  python ptos_web.py
Then open: http://localhost:5000
"""

import sys
import os
import io
import datetime as dt

# ── patch sys.exit so ptos never kills the Flask process ─────────────────────
class PTOSError(Exception):
    pass

_real_exit = sys.exit
def _safe_exit(msg=""):
    raise PTOSError(str(msg))
sys.exit = _safe_exit
# ─────────────────────────────────────────────────────────────────────────────

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ptos

from flask import (Flask, render_template, request, redirect,
                   url_for, jsonify, send_file)

app = Flask(__name__, template_folder="web_templates")
app.secret_key = "ptos-local-only"

# ── helpers ───────────────────────────────────────────────────────────────────

TIME_OPTIONS = [
    ("Today",        "td"),
    ("Yesterday",    "yd"),
    ("This week",    "tw"),
    ("Last week",    "lw"),
    ("This month",   "tm"),
    ("Last month",   "lm"),
    ("This quarter", "tq"),
    ("Last quarter", "lq"),
    ("This year",    "ty"),
    ("Last year",    "ly"),
    ("All time",     "all"),
]

def _cycles():
    return ptos.get_config().get("cycles", {})

def _capture(fn, *args, **kwargs):
    """Call a ptos print-based function, capture its stdout as a string."""
    buf = io.StringIO()
    old = sys.stdout
    sys.stdout = buf
    try:
        fn(*args, **kwargs)
    except PTOSError as e:
        sys.stdout = old
        return f"Error: {e}"
    except Exception as e:
        sys.stdout = old
        return f"Error: {e}"
    finally:
        sys.stdout = old
    return buf.getvalue()

def _resolve_time(code):
    """Resolve a time code to (start, end), returning (date.min, date.max) on error."""
    try:
        return ptos.resolve_time(code or "tm", _cycles())
    except Exception:
        return dt.date.min, dt.date.max

def _build_field_defs(schema, rtype, current_record=None):
    """
    Return a list of field definition dicts for the Add Record form.
    Each dict: {name, required, options, is_int, unit, parent}
    Handles flat options, parent-dependent options, shared refs, int fields.
    """
    if not rtype:
        return []
    type_schema = schema.get("type", {}).get(rtype, {})
    required    = type_schema.get("required", [])
    all_fields  = list(required)
    # add optional fields defined in type schema
    for f in type_schema.get("fields", {}):
        if f not in all_fields:
            all_fields.append(f)
    # add condition fields
    for f in type_schema.get("conditions", {}):
        if f not in all_fields:
            all_fields.append(f)

    defs = []
    record = current_record or {}

    for fname in all_fields:
        if fname == "tag":
            continue
        field_meta = schema.get("fields", {}).get(fname, {})
        is_int     = isinstance(field_meta, dict) and field_meta.get("type") == "int"
        unit       = field_meta.get("unit", "") if isinstance(field_meta, dict) else ""
        field_def  = type_schema.get("fields", {}).get(fname, {})
        parent     = field_def.get("parent")

        # resolve options
        if parent:
            parent_val = record.get(parent, "")
            options    = ptos.resolve_options_for_value(type_schema, fname, parent_val)
        else:
            options = ptos.resolve_options(schema, type_schema, fname) or []

        defs.append({
            "name":     fname,
            "required": fname in required,
            "options":  options,
            "is_int":   is_int,
            "unit":     unit,
            "parent":   parent or "",
        })
    return defs


def _check_conditions(schema, rtype, record):
    """Return list of condition fields that are currently active."""
    type_schema = schema.get("type", {}).get(rtype, {})
    active = []
    for field, rule in type_schema.get("conditions", {}).items():
        condition = rule.get("when", {})
        if all(record.get(k) == v for k, v in condition.items()):
            active.append(field)
    return active


# ── redirect root ─────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return redirect(url_for("add_get"))


# ══════════════════════════════════════════════════════════════════════════════
# Add Record
# ══════════════════════════════════════════════════════════════════════════════

@app.route("/add", methods=["GET"])
def add_get():
    schema  = ptos.get_schema()
    types   = schema.get("types", {}).get("allowed", [])
    presets = {k: v for k, v in ptos.get_presets().items()
               if not (isinstance(v, dict) and ("alias" in v or "records" in v))}

    # resolve type from query param or preset
    selected_type = request.args.get("type", "")
    preset_name   = request.args.get("preset", "")

    # collect any field values already in the query string (from parent-change reload)
    field_values = {k: v for k, v in request.args.items()
                    if k not in ("type", "preset", "date")}
    if field_values.get("tag"):
        tags = request.args.getlist("tag")
        field_values["tag"] = tags

    # if preset selected, seed field values from it
    if preset_name and not selected_type:
        preset_data = ptos.get_presets().get(preset_name, {})
        if isinstance(preset_data, dict) and "alias" in preset_data:
            preset_data = ptos.get_presets().get(preset_data["alias"], {})
        if preset_data:
            selected_type = preset_data.get("type", "")
            for k, v in preset_data.items():
                if k != "type" and k not in field_values:
                    field_values[k] = v

    field_defs  = _build_field_defs(schema, selected_type, field_values)
    tag_options = []
    if selected_type:
        type_schema = schema.get("type", {}).get(selected_type, {})
        tag_options = ptos.resolve_tags(schema, type_schema, field_values)

    return render_template("add.html",
        tab="add", title="Add Record",
        types=types, presets=sorted(presets.keys()),
        selected_type=selected_type,
        field_defs=field_defs,
        tag_options=tag_options,
        field_values=field_values,
        today=dt.date.today().isoformat(),
        msg=None, last_line=None)


@app.route("/add", methods=["POST"])
def add_post():
    schema = ptos.get_schema()
    types  = schema.get("types", {}).get("allowed", [])
    presets = {k: v for k, v in ptos.get_presets().items()
               if not (isinstance(v, dict) and ("alias" in v or "records" in v))}

    rtype      = request.form.get("type", "").strip()
    date_str   = request.form.get("date", dt.date.today().isoformat()).strip()
    note       = request.form.get("note", "").strip() or None
    custom_tags = [t.strip().replace(" ", "_")
                   for t in request.form.get("custom_tags", "").split(",")
                   if t.strip()]

    # build record dict from form
    record = {"type": rtype}
    type_schema = schema.get("type", {}).get(rtype, {})
    all_fields  = list(type_schema.get("required", []))
    for f in type_schema.get("fields", {}):
        if f not in all_fields:
            all_fields.append(f)
    for f in type_schema.get("conditions", {}):
        if f not in all_fields:
            all_fields.append(f)

    for fname in all_fields:
        if fname == "tag":
            continue
        val = request.form.get(fname, "").strip()
        if val:
            record[fname] = val.replace(" ", "_")

    tags = request.form.getlist("tag") + custom_tags
    if tags:
        record["tag"] = tags

    # validate
    try:
        problems = ptos.validate_record(schema, record)
    except PTOSError as e:
        problems = [str(e)]

    if problems:
        field_defs  = _build_field_defs(schema, rtype, record)
        tag_options = ptos.resolve_tags(schema, type_schema, record)
        return render_template("add.html",
            tab="add", title="Add Record",
            types=types, presets=sorted(presets.keys()),
            selected_type=rtype,
            field_defs=field_defs,
            tag_options=tag_options,
            field_values=record,
            today=dt.date.today().isoformat(),
            msg=" | ".join(problems), msg_type="error",
            last_line=None)

    # save
    try:
        line = ptos.build_record_line(date_str, record, note)
        ptos.append_record(line)
    except PTOSError as e:
        return render_template("add.html",
            tab="add", title="Add Record",
            types=types, presets=sorted(presets.keys()),
            selected_type=rtype,
            field_defs=_build_field_defs(schema, rtype, record),
            tag_options=ptos.resolve_tags(schema, type_schema, record),
            field_values=record,
            today=dt.date.today().isoformat(),
            msg=str(e), msg_type="error", last_line=None)

    return render_template("add.html",
        tab="add", title="Add Record",
        types=types, presets=sorted(presets.keys()),
        selected_type="", field_defs=[], tag_options=[],
        field_values={},
        today=dt.date.today().isoformat(),
        msg="✔ Record saved.", msg_type="success",
        last_line=line)


# ══════════════════════════════════════════════════════════════════════════════
# Journal
# ══════════════════════════════════════════════════════════════════════════════

@app.route("/journal")
def journal_get():
    date_str = request.args.get("date", dt.date.today().isoformat())
    try:
        date = dt.date.fromisoformat(date_str)
    except ValueError:
        date = dt.date.today()

    today     = dt.date.today()
    date      = min(date, today)
    date_str  = date.isoformat()
    prev_date = (date - dt.timedelta(days=1)).isoformat()
    next_date = (date + dt.timedelta(days=1)).isoformat()

    year_dir = os.path.join(ptos.JOURNAL_DIR, date_str[:4])
    os.makedirs(year_dir, exist_ok=True)
    path = os.path.join(year_dir, f"{date_str}.md")

    if not os.path.exists(path):
        if date == today:
            path = ptos.get_today_journal()
        content = ""
    else:
        with open(path, encoding="utf-8") as f:
            content = f.read()

    return render_template("journal.html",
        tab="journal", title="Journal",
        date=date_str, today=today.isoformat(),
        prev_date=prev_date, next_date=next_date,
        content=content, msg=None)


@app.route("/journal/save", methods=["POST"])
def journal_save():
    data    = request.get_json(silent=True) or {}
    date    = data.get("date", dt.date.today().isoformat())
    content = data.get("content", "")

    try:
        dt.date.fromisoformat(date)
    except ValueError:
        return jsonify(ok=False, error="Invalid date")

    year_dir = os.path.join(ptos.JOURNAL_DIR, date[:4])
    os.makedirs(year_dir, exist_ok=True)
    path = os.path.join(year_dir, f"{date}.md")
    ptos._backup_file(path)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    return jsonify(ok=True)


# ══════════════════════════════════════════════════════════════════════════════
# Queries
# ══════════════════════════════════════════════════════════════════════════════

@app.route("/queries")
def queries_get():
    try:
        all_q = ptos.get_queries()
    except PTOSError as e:
        all_q = {}

    named      = [k for k in all_q
                  if k not in ("metrics", "dashboards", "due")
                  and not (isinstance(all_q[k], dict) and "alias" in all_q[k])]
    metrics    = list(all_q.get("metrics", {}).keys())
    dashboards = list(all_q.get("dashboards", {}).keys())

    return render_template("queries.html",
        tab="queries", title="Queries",
        queries=named, metrics=metrics, dashboards=dashboards,
        time_options=TIME_OPTIONS)


@app.route("/queries/run", methods=["POST"])
def queries_run():
    data = request.get_json(silent=True) or {}
    kind = data.get("kind", "q")   # q / m / d
    name = data.get("name", "")
    time = data.get("time", "")

    try:
        queries = ptos.get_queries()
        cycles  = _cycles()
        start, end = _resolve_time(time) if time else (None, None)

        if kind == "d":
            if start is None:
                db  = queries.get("dashboards", {}).get(name, {})
                t   = db.get("time", "tm") if isinstance(db, dict) else "tm"
                start, end = _resolve_time(t)
            result = _capture(ptos.run_dashboard, name, queries, start, end, cycles)

        elif kind == "m":
            if start is None:
                start, end = _resolve_time("tm")
            result = _capture(ptos.run_metric, name, queries, start, end, cycles)

        else:  # saved query
            q_def = queries.get(name, {})
            if not isinstance(q_def, dict):
                return jsonify(result=f"Query '{name}' not found.")
            if start is None:
                t = q_def.get("time", "tm")
                start, end = _resolve_time(t)
            filters = q_def.get("where", "").split()

            results, total = ptos.scan_records(start, end, filters, None)
            if not results:
                return jsonify(result="No records found.")

            out = io.StringIO()
            old = sys.stdout
            sys.stdout = out

            # honour group/pivot/trend from saved query
            if "group" in q_def:
                ptos.render_summary(results, start, end,
                                    time or q_def.get("time","tm"),
                                    filters, total)
                counts, sums, has_amt = ptos.group_results(results, q_def["group"])
                ptos.render_group(counts, sums, has_amt, q_def["group"])
            elif "pivot" in q_def and len(q_def["pivot"]) >= 2:
                row, col = q_def["pivot"][:2]
                ptos.render_summary(results, start, end,
                                    time or q_def.get("time","tm"),
                                    filters, total)
                table, cols, rows = ptos.pivot_results(
                    results, row, col, q_def.get("count", False))
                ptos.render_pivot(table, cols, rows, row)
            elif q_def.get("trend"):
                sys.stdout = old
                result = _capture(ptos.run_trend, filters,
                                   q_def.get("time", "tm"),
                                   int(q_def["trend"]), cycles)
                return jsonify(result=result)
            else:
                ptos.render_summary(results, start, end,
                                    time or q_def.get("time","tm"),
                                    filters, total)
                for line in results:
                    print(line)

            sys.stdout = old
            result = out.getvalue()

    except PTOSError as e:
        result = f"Error: {e}"
    except Exception as e:
        result = f"Error: {e}"

    return jsonify(result=result)


# ══════════════════════════════════════════════════════════════════════════════
# Browse
# ══════════════════════════════════════════════════════════════════════════════

@app.route("/browse")
def browse_get():
    schema    = ptos.get_schema()
    types     = schema.get("types", {}).get("allowed", [])
    log_files = sorted(
        f for f in os.listdir(ptos.RECORDS_DIR) if f.endswith(".log")
    ) if os.path.exists(ptos.RECORDS_DIR) else []

    return render_template("browse.html",
        tab="browse", title="Browse",
        types=types, log_files=log_files,
        time_options=TIME_OPTIONS)


@app.route("/browse/run", methods=["POST"])
def browse_run():
    data    = request.get_json(silent=True) or {}
    where   = data.get("where", [])
    time    = data.get("time", "tm")
    search  = data.get("search", "") or None
    group   = data.get("group", "")
    sort    = data.get("sort", "") or None
    file    = data.get("file", "") or None

    try:
        start, end = _resolve_time(time)
        results, total = ptos.scan_records(
            start, end, where, search, from_file=file)

        if not results:
            return jsonify(result="No records found.")

        out = io.StringIO()
        old = sys.stdout
        sys.stdout = out

        time_label = dict(TIME_OPTIONS).get(time, time)

        if group:
            ptos.render_summary(results, start, end, time_label, where, total)
            counts, sums, has_amt = ptos.group_results(results, [group])
            print(f"\nGrouped by: {group}\n")
            ptos.render_group(counts, sums, has_amt, [group])
        else:
            if sort:
                def sort_key(line):
                    parsed = ptos.safe_parse_line(line)
                    if not parsed: return (1, 0, "")
                    _, kv, _ = parsed
                    val = kv.get(sort, "")
                    if isinstance(val, list): val = val[0] if val else ""
                    try:    return (0, int(val), "")
                    except: return (1, 0, str(val).lower())
                results = sorted(results, key=sort_key)
            for line in results:
                print(line)
            ptos.render_summary(results, start, end, time_label, where, total)

        sys.stdout = old
        result = out.getvalue()

    except PTOSError as e:
        result = f"Error: {e}"
    except Exception as e:
        result = f"Error: {e}"

    return jsonify(result=result)


@app.route("/browse/due", methods=["POST"])
def browse_due():
    try:
        result = _capture(ptos.run_due, "__DEFAULT__")
    except Exception as e:
        result = f"Error: {e}"
    return jsonify(result=result)


@app.route("/browse/export", methods=["POST"])
def browse_export():
    import json, csv, tempfile
    params = json.loads(request.form.get("params", "{}"))
    where  = params.get("where", [])
    time   = params.get("time", "tm")
    search = params.get("search", "") or None
    file   = params.get("file", "") or None

    try:
        start, end = _resolve_time(time)
        results, _ = ptos.scan_records(start, end, where, search, from_file=file)
        time_label = dict(TIME_OPTIONS).get(time, time)

        # write to temp file then send
        tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".csv",
                                          delete=False, encoding="utf-8",
                                          newline="")
        type_part = next((f.split("=")[1] for f in where
                          if f.startswith("type=")), "records")
        filename  = f"{type_part}_{time_label}.csv"

        cols = ["date"]
        seen = {"date"}
        for line in results:
            parsed = ptos.safe_parse_line(line)
            if parsed:
                for k in parsed[1]:
                    if k not in seen:
                        cols.append(k)
                        seen.add(k)
        has_note = any(ptos.safe_parse_line(l) and ptos.safe_parse_line(l)[2]
                       for l in results)
        if has_note:
            cols.append("note")

        writer = csv.DictWriter(tmp, fieldnames=cols)
        writer.writeheader()
        for line in results:
            parsed = ptos.safe_parse_line(line)
            if not parsed: continue
            d, kv, note = parsed
            row = {"date": str(d)}
            for k, v in kv.items():
                row[k] = ",".join(v) if isinstance(v, list) else str(v)
            if has_note:
                row["note"] = note or ""
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
    log_files = sorted(
        f for f in os.listdir(ptos.RECORDS_DIR) if f.endswith(".log")
    ) if os.path.exists(ptos.RECORDS_DIR) else []

    current_file = request.args.get("file", "")
    if not current_file and log_files:
        current_file = log_files[-1]   # default: most recent year

    content = ""
    if current_file:
        path = os.path.join(ptos.RECORDS_DIR, current_file)
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                content = f.read()

    return render_template("editor.html",
        tab="editor", title="Log Editor",
        log_files=log_files,
        current_file=current_file,
        content=content, msg=None)


@app.route("/editor/save", methods=["POST"])
def editor_save():
    data    = request.get_json(silent=True) or {}
    file    = data.get("file", "")
    content = data.get("content", "")

    if not file or "/" in file or "\\" in file:
        return jsonify(ok=False, error="Invalid filename")

    path = os.path.join(ptos.RECORDS_DIR, file)
    if not os.path.exists(path):
        return jsonify(ok=False, error=f"File not found: {file}")

    ptos._backup_file(path)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    return jsonify(ok=True)


# ══════════════════════════════════════════════════════════════════════════════
# API endpoints (used by browse.html JS)
# ══════════════════════════════════════════════════════════════════════════════

@app.route("/api/type_fields/<rtype>")
def api_type_fields(rtype):
    """Return field definitions and dimension list for a given type."""
    try:
        schema      = ptos.get_schema()
        type_schema = schema.get("type", {}).get(rtype, {})
        bad         = ptos.non_dimension_fields()
        defs        = _build_field_defs(schema, rtype)
        dimensions  = [f["name"] for f in defs
                       if f["name"] not in bad and f["options"]]
        return jsonify(fields=defs, dimensions=dimensions)
    except Exception as e:
        return jsonify(fields=[], dimensions=[], error=str(e))


@app.route("/api/preset/<name>")
def api_preset(name):
    """Return preset field values as JSON."""
    try:
        presets = ptos.get_presets()
        data    = presets.get(name, {})
        if isinstance(data, dict) and "alias" in data:
            data = presets.get(data["alias"], {})
        return jsonify(data)
    except Exception as e:
        return jsonify(error=str(e))


# ══════════════════════════════════════════════════════════════════════════════
# Run
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("\nPTOS Web UI")
    print("Open: http://localhost:5000\n")
    app.run(debug=False, host="127.0.0.1", port=5000)
