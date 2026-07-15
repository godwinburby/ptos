"""
ptos_web.py  —  Flask web UI for PTOS (mobile-first, responsive)
Place alongside ptos.py and ptos_service.py.
Run:  python ptos_web.py   →  http://localhost:5000
"""

import sys, os, re, fnmatch, datetime as dt, json, csv, tempfile, platform, subprocess, urllib.request, atexit, queue, threading, time, logging, shutil
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import ptos_service as svc
import ptos
from ptos import _glob_match
from ptos_service import PTOSError

from flask import (Flask, render_template, request, redirect,
                   url_for, jsonify, send_file, Response)

_basedir = getattr(sys, '_MEIPASS', None) or os.path.dirname(os.path.abspath(__file__))
app = Flask(__name__,
    template_folder=os.path.join(_basedir, 'web_templates'),
    static_folder=os.path.join(_basedir, 'web_static'),
    static_url_path="/static")
app.secret_key = "ptos-local-only"
app.config['TEMPLATES_AUTO_RELOAD'] = True
app.config["DEBUG"] = False

log = logging.getLogger("ptos_web")

@app.context_processor
def _inject_globals():
    return {
        "frozen": bool(getattr(sys, "frozen", False)),
        "desktop_mode": os.environ.get("DESKTOP_MODE") == "1",
    }

def _wants_json():
    return (
        request.path.startswith("/api/")
        or request.headers.get("X-Requested-With") == "XMLHttpRequest"
        or request.accept_mimetypes.best == "application/json"
    )

@app.errorhandler(PTOSError)
def handle_ptos_error(e):
    app.logger.warning(f"PTOSError on {request.path}: {e}")
    if _wants_json():
        return jsonify({"success": False, "error": str(e)}), 500
    return render_template("error.html", message=str(e)), 500

@app.errorhandler(Exception)
def handle_unexpected_error(e):
    app.logger.error(f"Unhandled exception on {request.path}: {e}", exc_info=True)
    if _wants_json():
        return jsonify({"success": False, "error": "Something went wrong."}), 500
    return render_template("error.html",
        message="Something went wrong. Check the server log for details."), 500

from functools import wraps
from flask import request, Response

def _check_auth(username, password):
    try:
        cfg = svc.get_config()
        auth = cfg.get("auth")
        if auth is None:
            return True
        if not auth.get("enabled", True):
            return True
        return username == auth.get("username", "") and password == auth.get("password", "")
    except Exception:
        return False

_original_exit = sys.exit

@app.before_request
def require_auth():
    if request.path.startswith("/static/"):
        return None
    auth = request.authorization
    if not _check_auth(auth.username if auth else "", auth.password if auth else ""):
        return Response(
            'PTOS — Access denied',
            401,
            {'WWW-Authenticate': 'Basic realm="PTOS"'}
        )

@app.before_request
def _activate_error_trap():
    sys.exit = svc._safe_exit

@app.teardown_request
def _deactivate_error_trap(exc):
    sys.exit = _original_exit

_TIME_OPTIONS_BASE = [
    ("Today","td"),("Yesterday","yd"),("This week","tw"),("Last week","lw"),
    ("This month","tm"),("Last month","lm"),("This quarter","tq"),
    ("Last quarter","lq"),("This year","ty"),("Last year","ly"),("All time","all"),
    ("Specific year","year"),("Specific month","month"),("Specific date","date"),("Date range","range"),
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

def _build_period_label(time_code, custom_time, cycles, from_date=None, to_date=None):
    """Build a human-readable label from time code.
    
    Examples:
      "tm"     → "This month"
      "tw"     → "This week"  
      "tq"     → "This quarter"
      "all"    → "All time"
      "2026-04"→ "Apr 2026"
      "2026"   → "2026"
      "2026-04-15" → "15 Apr 2026"
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
    
    # Handle range
    if time_code == "range":
        if from_date or to_date:
            parts = []
            if from_date:
                d = dt.date.fromisoformat(from_date) if re.fullmatch(r"\d{4}-\d{2}-\d{2}", from_date) else None
                parts.append("From " + (f"{d.day} {d.strftime('%b %Y')}" if d else from_date))
            if to_date:
                d = dt.date.fromisoformat(to_date) if re.fullmatch(r"\d{4}-\d{2}-\d{2}", to_date) else None
                parts.append("to " + (f"{d.day} {d.strftime('%b %Y')}" if d else to_date))
            return " ".join(parts)
        return "Date range"
    
    # Handle YYYY (bare year)
    if re.fullmatch(r"\d{4}", time_code):
        return time_code
    
    # Handle YYYY-MM-DD (full date)
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", time_code):
        year, month, day = int(time_code[:4]), int(time_code[5:7]), int(time_code[8:10])
        return f"{day} {dt.date(year, month, 1).strftime('%b %Y')}"
    
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
    
    # Handle "custom", "year", "month", "date" with custom_time
    if time_code in ("custom","year","month","date") and custom_time:
        if re.fullmatch(r"\d{4}-\d{2}", custom_time):
            year, month = int(custom_time[:4]), int(custom_time[5:7])
            dt_obj = dt.datetime(year, month, 1)
            return dt_obj.strftime("%b %Y")
        if re.fullmatch(r"\d{4}", custom_time):
            return custom_time
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", custom_time):
            year, month, day = int(custom_time[:4]), int(custom_time[5:7]), int(custom_time[8:10])
            return f"{day} {dt.date(year, month, 1).strftime('%b %Y')}"
        return "Custom"
    
    # Fallback - try to use custom_time if provided
    if time_code in ("custom","year","month","date") and custom_time:
        if re.fullmatch(r"\d{4}-\d{2}", custom_time):
            year, month = int(custom_time[:4]), int(custom_time[5:7])
            dt_obj = dt.datetime(year, month, 1)
            return dt_obj.strftime("%b %Y")
        if re.fullmatch(r"\d{4}", custom_time):
            return custom_time
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", custom_time):
            year, month, day = int(custom_time[:4]), int(custom_time[5:7]), int(custom_time[8:10])
            return f"{day} {dt.date(year, month, 1).strftime('%b %Y')}"
        return "Custom"

    return "Custom"

def _build_field_types(schema):
    ft = {}
    def _set(fname, ftype):
        ft[fname] = {"is_int": ftype == "int", "is_date": ftype == "date",
                      "is_month": ftype == "month", "is_datetime": ftype == "datetime"}
    for fname, fmeta in schema.get("fields", {}).items():
        if isinstance(fmeta, dict):
            _set(fname, fmeta.get("type", ""))
    for tdef in schema.get("type", {}).values():
        for fname, fdef in tdef.get("fields", {}).items():
            if isinstance(fdef, dict) and fname not in ft:
                _set(fname, fdef.get("type", ""))
    _set("date", "date")
    return ft

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
        is_int      = isinstance(field_meta, dict) and field_meta.get("type") == "int"
        is_date     = isinstance(field_meta, dict) and field_meta.get("type") == "date"
        is_month    = isinstance(field_meta, dict) and field_meta.get("type") == "month"
        is_datetime = isinstance(field_meta, dict) and field_meta.get("type") == "datetime"
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
            options    = svc.resolve_options_for_value(type_schema, fname, parent_val)
            option_source = "parent_dependent"
            parent_options = list(field_def.get("options", {}).keys()) if isinstance(field_def.get("options"), dict) else []
            shared_key = ""
        else:
            options = svc.resolve_options(schema, type_schema, fname) or []
            if field_def.get("use"):
                option_source = "shared"
                shared_key = field_def["use"].split(".", 1)[1]
                parent_options = []
            elif isinstance(field_def.get("options"), list):
                option_source = "flat"
                shared_key = ""
                parent_options = []
            else:
                option_source = "none"
                shared_key = ""
                parent_options = []
        
        has_options = bool(options) or option_source in ("parent_dependent", "shared")
        
        defs.append({
            "name":           fname,
            "required":       fname in required,
            "options":        options,
            "has_options":    has_options,
            "option_source":  option_source,
            "shared_key":      shared_key,
            "parent_options": parent_options,
            "type_name":       rtype,
            "is_int":         is_int,
            "is_date":        is_date,
            "is_month":       is_month,
            "is_datetime":    is_datetime,
            "unit":           unit,
            "parent":         parent or "",
            "has_parent":     has_parent,
            "is_parent":            is_parent,
            "is_tag_trigger":       is_tag_trigger,
            "is_condition_trigger": is_condition_trigger,
            "show_when":            show_when,
        })
    return defs


def _build_global_field_defs(schema, current_record=None):
    """Build field def dicts for [global_fields] — rendered in collapsible panel."""
    record = current_record or {}
    defs = []
    for fname, fdef in schema.get("global_fields", {}).items():
        if not isinstance(fdef, dict):
            continue
        defs.append({
            "name":    fname,
            "options": fdef.get("options", []),
            "is_int":  fdef.get("type") == "int",
            "unit":    fdef.get("unit", ""),
            "value":   record.get(fname, ""),
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
        # Strip metadata fields (e.g. use_count) not in the record schema
        known = {"type", "tag", "note"}
        known.update(schema.get("fields", {}).keys())
        known.update(schema.get("global_fields", {}).keys())
        rtype = record.get("type")
        if rtype:
            ts = schema.get("type", {}).get(rtype, {})
            known.update(ts.get("required", []))
            known.update(ts.get("fields", {}).keys())
        record = {k: v for k, v in record.items() if k in known}
        problems = svc.validate_record(schema, record)
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
    try:
        schema = svc.get_schema()
        field_types = _build_field_types(schema)
    except Exception:
        log.exception("Failed to load schema for home page")
        schema = {}
        field_types = {}
    presets = {k: v for k, v in svc.get_presets().items()
               if not (isinstance(v, dict) and ("alias" in v or "records" in v))}
    multi_presets = _multi_presets()
    
    # Get selected due config from query param, default to first one
    selected_due = request.args.get("due", None)
    due_configs = {}  # {name: config}
    
    try:
        queries = svc.get_queries()
        due_section = queries.get("due", {})
        if not isinstance(due_section, dict):
            due_section = {}
        
        # Root-level keys = default config
        if due_section.get("type"):
            due_configs["default"] = {
                "type": due_section.get("type", "followup"),
                "key": due_section.get("key", "client"),
                "sort_by": due_section.get("sort_by", ""),
                "days": due_section.get("days", 7),
                "exclude_results": due_section.get("exclude_results", [])
            }
        
        # Read nested configs from [due] section
        for name, cfg in due_section.items():
            if isinstance(cfg, dict) and cfg.get("type"):
                due_configs[name] = cfg
        
        # Also check for separate [due.*] or [due_*] sections (backup)
        for k, v in queries.items():
            if not isinstance(v, dict):
                continue
            if k.startswith("due."):
                name = k[4:]
                if name not in due_configs:
                    due_configs[name] = v
            elif k.startswith("due_"):
                name = k[4:]
                if name not in due_configs:
                    due_configs[name] = v
    except Exception:
        log.exception("Failed to load queries for due configs on home page")
        queries = {}
    
    # Get due data for selected config
    try:
        due_data = svc.get_due(config_name=selected_due if selected_due and selected_due != "default" else None)
        due_rows = due_data["rows"]
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
        
        # time_param absent = Per query mode: each metric uses its own query time.
        # time_param present = user explicitly picked a window to override all metrics.
        time_param  = request.args.get("time", None)
        custom_time = request.args.get("custom_time", "")
        from_date   = request.args.get("from_date") or None
        to_date     = request.args.get("to_date") or None
        if from_date:
            time_code = "range"
            use_dashboard_time = True
        elif time_param in ("custom","year","month","date") and custom_time and re.fullmatch(r"\d{4}(?:-\d{2}(?:-\d{2})?)?", custom_time):
            time_code = custom_time
        else:
            time_code = time_param or "tm"
        use_dashboard_time = time_param is not None or from_date is not None

        cycles = cfg.get("cycles", {})
        if db_name and db_name in dashboards:
            db = svc.get_dashboard(db_name, time_code, use_dashboard_time,
                                   from_date=from_date, to_date=to_date)
            for item in db["items"]:
                kind = item.get("kind", "unknown")
                # Each card shows its own query's time window, not a global label
                item_time = item.get("item_time", time_code)
                sub = _build_period_label(item_time, custom_time, cycles, from_date=from_date, to_date=to_date)
                stat = {
                    "label": item["name"].replace("_"," "),
                    "value": item["value"],
                    "sub":   item.get("sub", sub),
                    "kind":  kind,
                }
                raw_name = item.get("raw_name", item["name"])
                if kind == "query":
                    stat["query_url"] = f"/queries?run={raw_name}"
                elif kind == "metric":
                    stat["query_url"] = f"/queries?run={raw_name}"
                stats.append(stat)
    except Exception:
        log.exception("Failed to load dashboard stats for home page")
    recent_rows = []
    try:
        data = svc.get_records([], "td")
        recent_rows = data["records"][-8:]
        recent_cols = data["columns"]
    except Exception:
        log.exception("Failed to load recent records for home page")
        recent_cols = []
    
    cfg = svc.get_config()
    username = cfg.get("user", {}).get("name", "User")
    freq, rem = svc.get_frequent_presets(6)

    return render_template("home.html",
        tab="home", title="Home", now=_now_str(), greeting=_greeting(),
        username=username,
        frequent_presets=freq,
        remaining_presets=rem,
        multi_presets=multi_presets,
        due_count=due_count, due_rows=due_rows[:5],
        due_configs=list(due_configs.keys()), selected_due=selected_due or "default",
        stats=stats,
        dashboards=list(dashboards.keys()),
        current_db=db_name if 'db_name' in locals() else None,
        time_options=_get_time_options(),
        year_range=_YEAR_RANGE,
        current_time=request.args.get("time", ""),   # "" selects Per query option
        custom_time=request.args.get("custom_time", ""),
        from_date=request.args.get("from_date", ""),
        to_date=request.args.get("to_date", ""),
        recent_rows=recent_rows, recent_cols=recent_cols,
        field_types=field_types)


# ══════════════════════════════════════════════════════════════════════════════
# Due
# ══════════════════════════════════════════════════════════════════════════════

@app.route("/due")
def due_page():
    due_name = request.args.get("due", None)  # Select which due config
    days = request.args.get("days", None)
    days_int = int(days) if days is not None else None
    
    # Get all due configs for the tabs
    due_configs = {}
    try:
        queries = svc.get_queries()
        due_section = queries.get("due", {})
        if isinstance(due_section, dict):
            for name in ["default", "followup", "assessment", "investment"]:
                if name in due_section and isinstance(due_section[name], dict):
                    due_configs[name] = due_section[name]
        for k, v in queries.items():
            if not isinstance(v, dict):
                continue
            if k == "due":
                if "default" not in due_configs:
                    due_configs["default"] = v
            elif k.startswith("due."):
                due_configs[k[4:]] = v
            elif k.startswith("due_"):
                due_configs[k[4:]] = v
    except Exception:
        log.exception("Failed to load queries for due page")
    
    try:
        data = svc.get_due(config_name=due_name if due_name and due_name != "default" else None, days_override=days_int)
        rows = data["rows"]
        days_used = data["days"]
        error = None
    except PTOSError as e:
        rows = []; days_used = 7; error = str(e)
    return render_template("due.html", tab="due", title="Due List",
        now=_now_str(), rows=rows, days=days_used, error=error,
        due_configs=list(due_configs.keys()), selected_due=due_name or "default")


# ══════════════════════════════════════════════════════════════════════════════
# Todo
# ══════════════════════════════════════════════════════════════════════════════

@app.route("/todo")
def todo_page():
    project = request.args.get("project", None)
    context = request.args.get("context", None)
    pri = request.args.get("priority", None)
    due_filter = request.args.get("due", None)
    search = request.args.get("search", None)

    try:
        buckets = svc.get_todos_bucketed()
        projects = svc.get_todo_projects()
        contexts = svc.get_todo_contexts()
        error = None
    except PTOSError as e:
        buckets = {"overdue": [], "today": [], "upcoming": [], "someday": [], "total_open": 0}
        projects = []
        contexts = []
        error = str(e)

    # apply project/context/priority filters within buckets
    def _filter_list(todos):
        result = todos
        if project:
            result = [t for t in result if project in t.projects]
        if context:
            result = [t for t in result if context in t.contexts]
        if pri:
            result = [t for t in result if t.priority == pri.upper()]
        if search:
            result = [t for t in result if _glob_match(search, t.description)]
        return result

    for key in ("overdue", "today", "upcoming", "someday"):
        buckets[key] = _filter_list(buckets[key])

    # apply due range filter
    if due_filter:
        if due_filter in buckets:
            for key in list(buckets.keys()):
                if key != due_filter:
                    buckets[key] = []
        elif due_filter == "none":
            buckets["overdue"] = []
            buckets["today"] = []
            buckets["upcoming"] = []

    # today progress: count completed today vs total added today
    try:
        all_done, _ = svc.ptos_todo.load_todos(svc.DONE_PATH)
        today_str = dt.date.today().isoformat()
        done_today = len([t for t in all_done if t.completed_date and t.completed_date.isoformat() == today_str])
        total_today = len(buckets["overdue"]) + len(buckets["today"])
        # most recent 50 done tasks, newest first
        done_recent = sorted(all_done, key=lambda t: t.completed_date or dt.date.min, reverse=True)[:50]
    except Exception:
        done_today = 0
        total_today = 0
        done_recent = []

    # collect all unique priorities across all todos
    all_todos_flat = buckets["overdue"] + buckets["today"] + buckets["upcoming"] + buckets["someday"]
    all_priorities = sorted(set(t.priority for t in all_todos_flat if t.priority))

    return render_template("todo.html", tab="todo", title="Todo",
        now=_now_str(), buckets=buckets, projects=projects, contexts=contexts,
        error=error, selected_project=project, selected_context=context,
        selected_priority=pri, selected_due=due_filter, selected_search=search,
        done_today=done_today, total_today=total_today, done_recent=done_recent,
        all_priorities=all_priorities)


@app.route("/todo/add", methods=["POST"])
def todo_add():
    data = request.get_json(silent=True) or {}
    text = data.get("text", "").strip()
    if not text:
        return jsonify(ok=False, error="No text provided")
    try:
        result = svc.add_todo_line(text)
        return jsonify(ok=True, todo=result["todo"])
    except PTOSError as e:
        return jsonify(ok=False, error=str(e))


@app.route("/todo/complete", methods=["POST"])
def todo_complete():
    data = request.get_json(silent=True) or {}
    line_no = data.get("line_no")
    if not line_no:
        return jsonify(ok=False, error="No line_no provided")
    try:
        svc.complete_todo_by_line(int(line_no))
        return jsonify(ok=True)
    except PTOSError as e:
        return jsonify(ok=False, error=str(e))


@app.route("/todo/undo", methods=["POST"])
def todo_undo():
    data = request.get_json(silent=True) or {}
    line_no = data.get("line_no")
    if not line_no:
        return jsonify(ok=False, error="No line_no provided")
    try:
        svc.undo_todo_by_line(int(line_no))
        return jsonify(ok=True)
    except PTOSError as e:
        return jsonify(ok=False, error=str(e))


@app.route("/todo/delete", methods=["POST"])
def todo_delete():
    data = request.get_json(silent=True) or {}
    line_no = data.get("line_no")
    if not line_no:
        return jsonify(ok=False, error="No line_no provided")
    try:
        svc.delete_todo_by_line(int(line_no))
        return jsonify(ok=True)
    except PTOSError as e:
        return jsonify(ok=False, error=str(e))


@app.route("/todo/edit", methods=["POST"])
def todo_edit():
    data = request.get_json(silent=True) or {}
    line_no = data.get("line_no")
    updates = data.get("updates", {})
    if not line_no:
        return jsonify(ok=False, error="No line_no provided")
    try:
        result = svc.edit_todo_by_line(int(line_no), updates)
        return jsonify(ok=True, todo=result["todo"])
    except PTOSError as e:
        return jsonify(ok=False, error=str(e))


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
    freq_presets, rem_presets = svc.get_frequent_presets(6)
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
    global_field_defs = _build_global_field_defs(schema, field_values)
    tag_options = []
    tag_context = []
    if selected_type:
        ts = schema.get("type", {}).get(selected_type, {})
        tag_options = svc.resolve_tags(schema, ts, initial_context)
        tag_context = svc.get_tag_context(selected_type, field_values)
    return render_template("add.html",
        tab="add", title="Add Record", now=_now_str(),
        types=types, frequent_presets=freq_presets, remaining_presets=rem_presets,
        multi_presets=multi_presets,
        selected_type=selected_type, field_defs=field_defs,
        global_field_defs=global_field_defs,
        tag_options=tag_options, history_tags=history_filtered_tags,
        tag_context=tag_context,
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
    freq_presets, rem_presets = svc.get_frequent_presets(6)
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
    # collect global optional fields from form
    for fname in svc.get_global_fields(schema):
        val = request.form.get(fname, "").strip()
        if val: record[fname] = val.replace(" ", "_")
    tags = request.form.getlist("tag") + custom_tags
    if tags: record["tag"] = tags
    
    try:   problems = svc.validate_record(schema, record)
    except PTOSError as e: problems = [str(e)]
    if problems:
        fd = _build_field_defs(schema, rtype, record)
        return render_template("add.html",
            tab="add", title="Add Record", now=_now_str(),
            types=types, frequent_presets=freq_presets, remaining_presets=rem_presets,
            multi_presets=_multi_presets(),
            selected_type=rtype, field_defs=fd,
            global_field_defs=_build_global_field_defs(schema, record),
            tag_options=svc.resolve_tags(schema, ts, record),
            tag_context=svc.get_tag_context(rtype, record),
            field_values=record, today=dt.date.today().isoformat(),
            msg=" | ".join(problems), msg_type="error", last_line=None)
    try:
        line = svc.build_record_line(date_str, record, note)
        svc.append_record(line)
    except PTOSError as e:
        fd = _build_field_defs(schema, rtype, record)
        return render_template("add.html",
            tab="add", title="Add Record", now=_now_str(),
            types=types, frequent_presets=freq_presets, remaining_presets=rem_presets,
            multi_presets=_multi_presets(),
            selected_type=rtype, field_defs=fd,
            global_field_defs=_build_global_field_defs(schema, record),
            tag_options=svc.resolve_tags(schema, ts, record),
            tag_context=svc.get_tag_context(rtype, record),
            field_values=record, today=dt.date.today().isoformat(),
            msg=str(e), msg_type="error", last_line=None)
    return render_template("add.html",
        tab="add", title="Add Record", now=_now_str(),
        types=types, frequent_presets=freq_presets, remaining_presets=rem_presets,
        multi_presets=_multi_presets(),
        selected_type="", field_defs=[], tag_options=[],
        tag_context=[],
        global_field_defs=[], msg=None, msg_type=None, last_line=None)


@app.route("/add-field-option", methods=["POST"])
def add_field_option():
    """Add a new option to schema.toml and return success/error."""
    try:
        data = request.get_json()
        if not data:
            return jsonify({"success": False, "error": "No data"}), 400
        
        type_name = data.get("type_name")
        field_name = data.get("field_name")
        new_option = data.get("new_option", "").strip()
        option_source = data.get("option_source")
        parent_field = data.get("parent_field", "")
        parent_value = data.get("parent_value", "")
        shared_key = data.get("shared_key", "")
        
        if not new_option:
            return jsonify({"success": False, "error": "Empty option"}), 400
        
        result = svc.add_field_option(
            type_name=type_name,
            field_name=field_name,
            new_option=new_option,
            option_source=option_source,
            parent_field=parent_field,
            parent_value=parent_value,
            shared_key=shared_key
        )
        
        if result.get("success"):
            return jsonify({"success": True})
        return jsonify({"success": False, "error": result.get("error", "Failed")}), 400
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500



@app.route("/add-global-field-option", methods=["POST"])
def add_global_field_option():
    """Add a new option to a global field."""
    try:
        data = request.get_json() or {}
        field_name = data.get("field_name", "").strip()
        new_option = data.get("new_option", "").strip()
        
        if not field_name or not new_option:
            return jsonify({"success": False, "error": "Missing required fields"}), 400
        
        result = svc.add_global_field_option(field_name, new_option)
        
        if result.get("success"):
            return jsonify({"success": True})
        return jsonify({"success": False, "error": result.get("error", "Failed")}), 400
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500



@app.route("/api/schema/add_tag", methods=["POST"])
def api_add_tag():
    """Add a new tag option to schema.toml."""
    try:
        data = request.get_json()
        if not data:
            return jsonify({"success": False, "error": "No data"}), 400
        
        rtype = data.get("rtype", "")
        tag_field = data.get("tag_field", "")
        parent_value = data.get("parent_value", "")
        new_tag = data.get("new_tag", "").strip()
        
        if not rtype or not tag_field or not parent_value:
            return jsonify({"success": False, "error": "Missing required fields"}), 400
        
        if not new_tag:
            return jsonify({"success": False, "error": "Empty tag"}), 400
        
        result = svc.add_tag_option(rtype, tag_field, parent_value, new_tag)
        
        if result.get("success"):
            return jsonify({"success": True, "message": result.get("message", "")})
        return jsonify({"success": False, "error": result.get("error", "Failed")}), 400
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/journal")
def journal_get():
    today_d  = dt.date.today()
    date_str = request.args.get("date", today_d.isoformat())
    try:   date = min(dt.date.fromisoformat(date_str), today_d)
    except Exception: date = today_d
    date_str  = date.isoformat()
    prev_date = (date - dt.timedelta(days=1)).isoformat()
    next_date = (date + dt.timedelta(days=1)).isoformat()
    # Build path without doing os.makedirs in the web layer
    year_dir = os.path.join(svc.JOURNAL_DIR, date_str[:4])
    path = os.path.join(year_dir, f"{date_str}.md")
    if not os.path.exists(path) and date == today_d:
        path = svc.get_today_journal()
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
    content = data.get("content", "")
    try:
        svc.save_journal(date, content)
        return jsonify(ok=True)
    except svc.PTOSError as e:
        return jsonify(ok=False, error=str(e))
    except Exception as e:
        return jsonify(ok=False, error=str(e))


def _extract_snippet(text, query, context_chars=80):
    if '*' in query or '?' in query:
        regex = fnmatch.translate(query.lower()).replace(r'\Z', '')
        m = re.search(regex, text.lower())
        if m:
            idx = m.start()
        else:
            return text[:160] + ("…" if len(text) > 160 else "")
    else:
        idx = text.lower().find(query.lower())
        if idx == -1:
            return text[:160] + ("…" if len(text) > 160 else "")
    start = max(0, idx - context_chars)
    end = min(len(text), idx + len(query) + context_chars)
    snippet = text[start:end]
    if start > 0:
        snippet = "…" + snippet
    if end < len(text):
        snippet = snippet + "…"
    return snippet


@app.route("/search")
def search_page():
    q = request.args.get("q", "").strip()
    if not q:
        return render_template("search.html",
            tab="search", title="Search", now=_now_str(), query="",
            records=[], journal=[], todo=[])
    records = []
    for fname in ptos.get_log_files():
        path = os.path.join(svc.RECORDS_DIR, fname)
        try:
            with open(path, encoding="utf-8") as f:
                for i, line in enumerate(f, 1):
                    if _glob_match(q, line):
                        records.append({"file": fname, "line": i, "text": line.rstrip()})
        except Exception:
            pass
    journal = []
    year_dirs = []
    try:
        for entry in os.listdir(svc.JOURNAL_DIR):
            yd = os.path.join(svc.JOURNAL_DIR, entry)
            if os.path.isdir(yd):
                year_dirs.append(yd)
    except Exception:
        pass
    for yd in sorted(year_dirs):
        try:
            for fname in os.listdir(yd):
                if not fname.endswith(".md"):
                    continue
                path = os.path.join(yd, fname)
                try:
                    with open(path, encoding="utf-8") as f:
                        content = f.read()
                    if _glob_match(q, content):
                        snippet = _extract_snippet(content, q)
                        journal.append({"file": fname, "snippet": snippet})
                except Exception:
                    pass
        except Exception:
            pass
    todo = []
    for tpath_name in ["todo.txt", "done.txt"]:
        tpath = os.path.join(svc.TODO_DIR, tpath_name)
        try:
            with open(tpath, encoding="utf-8") as f:
                for i, line in enumerate(f, 1):
                    if _glob_match(q, line):
                        todo.append({"file": tpath_name, "line": i, "text": line.rstrip()})
        except Exception:
            pass
    import glob as _glob
    for dpath in sorted(_glob.glob(os.path.join(svc.TODO_DIR, "done.*.txt"))):
        base = os.path.basename(dpath)
        try:
            with open(dpath, encoding="utf-8") as f:
                for i, line in enumerate(f, 1):
                    if _glob_match(q, line):
                        todo.append({"file": base, "line": i, "text": line.rstrip()})
        except Exception:
            pass
    return render_template("search.html",
        tab="search", title="Search", now=_now_str(), query=q,
        records=records, journal=journal, todo=todo)


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
    new_types     = data.get("types", [])
    type_schemas  = data.get("type_schemas", {})
    global_fields = data.get("global_fields", {})
    shared_defs   = data.get("shared_defs", {})
    field_meta    = data.get("field_meta", {})
    if not new_types:
        return jsonify(ok=False, error="At least one record type is required")
    import re as _re
    for t in new_types:
        if not _re.match(r"^[a-z][a-z0-9_]*$", t):
            return jsonify(ok=False,
                error=f"Type '{t}' must be lowercase letters, numbers, underscores")
    try:
        old_schema  = svc.get_schema()
        new_schema  = _build_schema_dict(old_schema, new_types, type_schemas,
                                         new_global_fields=global_fields,
                                         new_shared_defs=shared_defs,
                                         new_field_meta=field_meta)
        svc.save_schema(new_schema)
        return jsonify(ok=True)
    except Exception as e:
        return jsonify(ok=False, error=str(e))


@app.route("/schema-builder/preview-lint", methods=["POST"])
def schema_builder_preview_lint():
    """Preview lint results against unsaved schema changes."""
    data = request.get_json(silent=True) or {}
    new_types     = data.get("types", [])
    type_schemas  = data.get("type_schemas", {})
    global_fields = data.get("global_fields", {})
    shared_defs   = data.get("shared_defs", {})
    field_meta    = data.get("field_meta", {})

    if not new_types:
        return jsonify(ok=False, error="No types provided")

    try:
        old_schema = svc.get_schema()
        new_schema = _build_schema_dict(old_schema, new_types, type_schemas,
                                        new_global_fields=global_fields,
                                        new_shared_defs=shared_defs,
                                        new_field_meta=field_meta)
        # new_schema is already a dict — no TOML round-trip needed for lint preview

        content_parts = []
        for fname in svc.get_log_files():
            fpath = os.path.join(svc.RECORDS_DIR, fname)
            if os.path.exists(fpath):
                with open(fpath, encoding="utf-8") as f:
                    content_parts.append(f.read())
        content = "\n".join(content_parts)

        result = svc.lint_content_with_schema(content, schema_override=new_schema)
        return jsonify(ok=True, data=result)
    except Exception as e:
        return jsonify(ok=False, error=str(e))


@app.route("/settings")
def settings_page():
    cfg = svc.get_config()
    user = cfg.get("user", {})
    display = cfg.get("display", {})
    cycles_raw = cfg.get("cycles", {})
    backup = cfg.get("backup", {})
    todo = cfg.get("todo", {})
    dashboard = cfg.get("dashboard", {})
    auth = cfg.get("auth", {})
    sync = cfg.get("sync", {})
    
    rclone_available = shutil.which("rclone") is not None
    remote_exists = False
    if rclone_available and sync.get("remote_name"):
        try:
            remotes = subprocess.run(
                ["rclone", "listremotes"], capture_output=True, text=True, timeout=5
            )
            remote_exists = (sync["remote_name"] + ":") in (remotes.stdout or "")
        except Exception:
            pass
    
    cycles = [{"name": k, "day": v} for k, v in cycles_raw.items()]
    
    today = dt.date.today()
    date_examples = {
        "indian": today.strftime("%d/%m/%Y"),
        "us": today.strftime("%m/%d/%Y"),
        "eu": today.strftime("%d/%m/%Y"),
        "iso": today.strftime("%Y-%m-%d"),
    }
    date_formats = [
        ("indian", "Indian", date_examples["indian"]),
        ("us", "US", date_examples["us"]),
        ("eu", "EU", date_examples["eu"]),
        ("iso", "ISO", date_examples["iso"]),
    ]
    
    dashboards = list(svc.get_dashboard_names()) if hasattr(svc, 'get_dashboard_names') else []
    
    return render_template("settings.html",
        tab="settings", title="Settings", now=_now_str(),
        user_name=user.get("name", ""),
        currency=display.get("currency", "₹"),
        date_format=display.get("date_format", "indian"),
        date_formats=date_formats,
        cycles=cycles,
        backup=backup,
        backup_folders=backup.get("folders", []),
        dashboards=dashboards,
        default_dashboard=dashboard.get("default", ""),
        auth_enabled=auth.get("enabled", False),
        auth_username=auth.get("username", ""),
        auth_password=auth.get("password", ""),
        todo=todo,
        sync=sync,
        sync_auto_on_startup=sync.get("auto_sync_on_startup", False),
        sync_auto_on_shutdown=sync.get("auto_sync_on_shutdown", False),
        sync_interval=sync.get("sync_interval_minutes", 0),
        rclone_available=rclone_available,
        remote_exists=remote_exists,
        base_dir=ptos.BASE_DIR)


@app.route("/settings/save", methods=["POST"])
def settings_save():
    try:
        data = request.get_json(silent=True) or {}
        cfg = svc.get_config()
        
        if "user_name" in data:
            cfg.setdefault("user", {})["name"] = data["user_name"]
        if "currency" in data:
            cfg.setdefault("display", {})["currency"] = data["currency"]
        if "date_format" in data:
            cfg.setdefault("display", {})["date_format"] = data["date_format"]
        if "cycles" in data and isinstance(data["cycles"], list):
            cfg["cycles"] = {c["name"]: int(c["day"]) for c in data["cycles"] if c.get("name") and c.get("day")}
        
        if "auto_backup_on_startup" in data or "auto_backup_on_shutdown" in data or "backup_if_files_changed" in data:
            cfg.setdefault("backup", {})["auto_backup_on_startup"] = bool(data.get("auto_backup_on_startup"))
            cfg.setdefault("backup", {})["auto_backup_on_shutdown"] = bool(data.get("auto_backup_on_shutdown"))
            cfg.setdefault("backup", {})["backup_if_files_changed"] = bool(data.get("backup_if_files_changed"))
        
        if "max_full_backups" in data:
            cfg.setdefault("backup", {})["max_full_backups"] = max(1, min(100, int(data["max_full_backups"])))
        if "max_config_backups" in data:
            cfg.setdefault("backup", {})["max_config_backups"] = max(1, min(100, int(data["max_config_backups"])))
        if "notify_interval" in data:
            cfg.setdefault("todo", {})["notify_interval"] = max(1, min(120, int(data["notify_interval"])))
        if "archive_months" in data:
            cfg.setdefault("todo", {})["archive_months"] = max(1, min(24, int(data["archive_months"])))
        if "remote_name" in data:
            val = data["remote_name"].strip().rstrip(":").replace(":", "")
            cfg.setdefault("sync", {})["remote_name"] = val
        if "remote_path" in data:
            val = data["remote_path"].strip()
            if val and not val.endswith("/"):
                val += "/"
            cfg.setdefault("sync", {})["remote_path"] = val
        if "auto_sync_on_startup" in data or "auto_sync_on_shutdown" in data:
            cfg.setdefault("sync", {})["auto_sync_on_startup"] = bool(data.get("auto_sync_on_startup"))
            cfg.setdefault("sync", {})["auto_sync_on_shutdown"] = bool(data.get("auto_sync_on_shutdown"))
        if "sync_interval_minutes" in data:
            cfg.setdefault("sync", {})["sync_interval_minutes"] = max(0, min(120, int(data["sync_interval_minutes"])))
        
        if "default_dashboard" in data:
            db_val = data["default_dashboard"]
            cfg["dashboard"] = {"default": db_val} if db_val else {}
        
        if "backup_folders" in data and isinstance(data["backup_folders"], list):
            core_folders = ["records", "config", "templates", "journal", "todo", "notes"]
            valid_folders = list(data["backup_folders"])
            for cf in core_folders:
                if cf not in valid_folders:
                    valid_folders.insert(0, cf)
            cfg.setdefault("backup", {})["folders"] = valid_folders
        
        if "auth_enabled" in data:
            enabled = bool(data["auth_enabled"])
            username = data.get("auth_username", "").strip()
            password = data.get("auth_password", "").strip()
            if enabled and (not username or not password):
                return jsonify(ok=False, error="Username and password required when auth is enabled")
            cfg["auth"] = {"enabled": enabled, "username": username, "password": password}
        
        result = svc.save_config(cfg)
        if result.get("ok"):
            return jsonify(ok=True)
        return jsonify(ok=False, error=result.get("message", "Save failed"))
    except Exception as e:
        return jsonify(ok=False, error=str(e))


# ══════════════════════════════════════════════════════════════════════════════
# Backup
# ══════════════════════════════════════════════════════════════════════════════

@app.route("/backup")
def backup_page():
    backups_raw = svc.list_backups()
    # Format dates before passing to template
    backups = [(name, svc.fmt_datetime(created), btype) 
               for name, created, btype in backups_raw]
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
    
    backup_path = os.path.join(svc.BACKUP_DIR, name)
    
    # Verify path is within BACKUP_DIR
    real_path = os.path.realpath(backup_path)
    real_backup_dir = os.path.realpath(svc.BACKUP_DIR)
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
    all_exist, missing = svc.check_backup_folders()
    return jsonify(ok=all_exist, missing=missing)


@app.route("/backup/preview", methods=["GET"])
def backup_preview():
    """Get preview of what will be backed up."""
    try:
        result = svc.get_backup_preview()
        return jsonify(result)
    except Exception as e:
        return jsonify(ok=False, error=str(e))


@app.route("/backup/restore/preview/<name>", methods=["GET"])
def backup_restore_preview(name):
    """Get preview of what will be restored from a backup."""
    try:
        result = svc.get_restore_preview(name)
        return jsonify(result)
    except Exception as e:
        return jsonify(ok=False, error=str(e))


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
        backup_path = os.path.join(svc.BACKUP_DIR, name)
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


@app.route("/backup/config/restore/<name>", methods=["POST"])
def backup_config_restore_from_list(name):
    """Restore config from existing backup file in backup list."""
    # Validate it's a config backup
    if not name.startswith("ptos-backup-config-") or not name.endswith(".zip"):
        return jsonify(ok=False, error="Not a valid config backup file")
    
    backup_path = os.path.join(svc.BACKUP_DIR, name)
    if not os.path.exists(backup_path):
        return jsonify(ok=False, error=f"Backup file not found: {name}")
    
    try:
        result = svc.restore_config(backup_path)
        return jsonify(ok=True, message=result.get("message", "Config restored"))
    except Exception as e:
        return jsonify(ok=False, error=str(e))


# ══════════════════════════════════════════════════════════════════════════════
# Sync (rclone)
# ══════════════════════════════════════════════════════════════════════════════

_sync_busy = False
_sync_result = None


@app.route("/sync/run", methods=["POST"])
def sync_run():
    global _sync_busy, _sync_result
    if _sync_busy:
        return jsonify(ok=False, error="Sync already in progress"), 409

    if not shutil.which("rclone"):
        return jsonify(ok=False, error="rclone not found. Install from https://rclone.org")

    data = request.get_json(silent=True) or {}
    command = data.get("command", "")
    if command not in ("bisync", "sync", "resync"):
        return jsonify(ok=False, error="Invalid command. Use bisync, sync, or resync")

    cfg = svc.get_config()
    sync_cfg = cfg.get("sync", {})
    if not sync_cfg.get("remote_name") or not sync_cfg.get("remote_path"):
        return jsonify(ok=False, error="[sync] not configured in config.toml")

    _sync_busy = True
    _sync_result = None
    _sse_broadcast("sync-start")

    def _run():
        global _sync_busy, _sync_result
        try:
            actual_cmd = "bisync"
            resync = False
            if command == "sync":
                actual_cmd = "sync"
            elif command == "resync":
                actual_cmd = "bisync"
                resync = True
            _sync_result = ptos.run_sync(actual_cmd, resync=resync)
        except Exception as e:
            _sync_result = {"ok": False, "output": "", "error": str(e), "returncode": 1}
        finally:
            _sync_busy = False
            _sse_broadcast("sync-done", _sync_result)

    threading.Thread(target=_run, daemon=True).start()
    return jsonify(ok=True, message="Sync started")


@app.route("/sync/status")
def sync_status():
    return jsonify(running=_sync_busy, result=_sync_result)


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


def _build_schema_dict(old_schema, new_types, type_schemas,
                       new_global_fields=None,
                       new_shared_defs=None,
                       new_field_meta=None):
    """
    Merge Schema Builder state with the existing schema dict.
    Returns a plain Python dict ready for tomli_w.dump() via svc.save_schema().
    Same logic as the old _build_schema_toml but produces a dict instead of strings.
    """
    schema = {}

    # ── [types] ──────────────────────────────────────────────────────────────
    schema["types"] = {"allowed": list(new_types)}

    # ── [fields.*] global field metadata ─────────────────────────────────────
    old_fields = old_schema.get("fields", {})
    fm_source  = dict(old_fields)
    if new_field_meta and isinstance(new_field_meta, dict):
        for fname, fmeta in new_field_meta.items():
            if isinstance(fmeta, dict):
                fm_source[fname] = fmeta
    fields_out = {}
    for fname, fmeta in fm_source.items():
        if not isinstance(fmeta, dict):
            continue
        fd = {}
        fd["type"] = fmeta.get("type", "string")
        if "aggregatable" in fmeta: fd["aggregatable"] = fmeta["aggregatable"]
        if "dimension"    in fmeta: fd["dimension"]    = fmeta["dimension"]
        if fmeta.get("unit"):       fd["unit"]         = fmeta["unit"]
        if fmeta.get("derived"):    fd["derived"]      = fmeta["derived"]
        fields_out[fname] = fd
    schema["fields"] = fields_out

    # ── [shared.*] ───────────────────────────────────────────────────────────
    sd_source = new_shared_defs if new_shared_defs is not None                 else old_schema.get("shared", {})
    shared_out = {}
    for sname, sdef in sd_source.items():
        if not isinstance(sdef, dict):
            continue
        sd = {"type": "int" if sdef.get("is_int") else "string"}
        opts = sdef.get("options", [])
        if opts:
            sd["options"] = opts
        shared_out[sname] = sd
    schema["shared"] = shared_out

    # ── [global_fields.*] ────────────────────────────────────────────────────
    gf_source = new_global_fields if new_global_fields is not None                 else old_schema.get("global_fields", {})
    gf_out = {}
    for fname, fdef in gf_source.items():
        if not isinstance(fdef, dict):
            continue
        gfd = {"type": "int" if fdef.get("is_int") else "string"}
        opts = fdef.get("options", [])
        if opts:
            gfd["options"] = opts
        gf_out[fname] = gfd
    schema["global_fields"] = gf_out

    # ── [type.*] ─────────────────────────────────────────────────────────────
    old_types  = old_schema.get("type", {})
    types_out  = {}

    for tname in new_types:
        ts_new = type_schemas.get(tname, {})
        ts_old = old_types.get(tname, {})
        tdict  = {}

        required = ts_new.get("required", ts_old.get("required", []))
        if required:
            tdict["required"] = list(required)

        # ── fields ──
        fields_new  = ts_new.get("fields", {})
        fields_old  = ts_old.get("fields", {})
        derived_new = ts_new.get("derived_fields", {})

        seen = list(fields_new.keys())
        for fn in fields_old:
            if fn not in seen: seen.append(fn)
        for fn in derived_new:
            if fn not in seen: seen.append(fn)

        fields_dict = {}
        for fname in seen:
            fdef_new     = fields_new.get(fname)
            fdef_old     = fields_old.get(fname, {})
            fdef_derived = derived_new.get(fname)

            if fdef_derived is not None:
                fd = {}
                if fdef_derived.get("expr"):  fd["derived"] = fdef_derived["expr"]
                if fdef_derived.get("type"):  fd["type"]    = fdef_derived["type"]
                fields_dict[fname] = fd
            elif fdef_new is not None:
                fd = {}
                if fdef_new.get("use"):
                    fd["use"] = fdef_new["use"]
                elif fdef_new.get("parent"):
                    fd["parent"] = fdef_new["parent"]
                    by_parent = fdef_new.get("options_by_parent", {})
                    if by_parent:
                        fd["options"] = {pv: list(popts)
                                         for pv, popts in by_parent.items()}
                elif fdef_new.get("is_int"):
                    fd["type"] = "int"
                else:
                    opts = fdef_new.get("options", [])
                    if opts:
                        fd["options"] = list(opts)
                fields_dict[fname] = fd
            else:
                # preserve old field verbatim
                if isinstance(fdef_old, dict):
                    fields_dict[fname] = dict(fdef_old)

        if fields_dict:
            tdict["fields"] = fields_dict

        # ── tags ──
        tags_new = ts_new.get("tags", {})
        tags_old = ts_old.get("tags", {})
        seen_tags = list(tags_new.keys())
        for tf in tags_old:
            if tf not in seen_tags: seen_tags.append(tf)

        tags_dict = {}
        for tfield in seen_tags:
            tdef_new = tags_new.get(tfield)
            tdef_old = tags_old.get(tfield, {})
            if tdef_new is not None:
                opts_dict = {fval: list(tags)
                             for fval, tags in tdef_new.items() if tags}
                if opts_dict:
                    tags_dict[tfield] = {"options": opts_dict}
            else:
                if isinstance(tdef_old, dict):
                    tags_dict[tfield] = dict(tdef_old)
        if tags_dict:
            tdict["tags"] = tags_dict

        # ── conditions ──
        conditions_new = ts_new.get("conditions", {})
        conditions_old = ts_old.get("conditions", {})
        all_cfields = list(conditions_new.keys())
        for cf in conditions_old:
            if cf not in all_cfields: all_cfields.append(cf)

        conds_dict = {}
        for cname in all_cfields:
            cdef_new = conditions_new.get(cname)
            cdef_old = conditions_old.get(cname, {})
            if cdef_new is not None:
                tfield = cdef_new.get("trigger_field", "")
                tval   = cdef_new.get("trigger_value", "")
                if tfield and tval:
                    conds_dict[cname] = {"when": {tfield: tval}}
            else:
                if isinstance(cdef_old, dict):
                    conds_dict[cname] = dict(cdef_old)
        if conds_dict:
            tdict["conditions"] = conds_dict

        types_out[tname] = tdict

    schema["type"] = types_out
    return schema

# ══════════════════════════════════════════════════════════════════════════════
# Query Builder
# ══════════════════════════════════════════════════════════════════════════════

@app.route("/query-builder")
def query_builder():
    try:
        queries = svc.get_queries()
        schema  = svc.get_schema()
        types   = schema.get("types", {}).get("allowed", [])
        field_types = _build_field_types(schema)
    except Exception:
        queries = {}
        types   = []
        field_types = {}
    
    # Collect all due configs from nested [due] section or separate [due.*] sections
    all_due_configs = {}
    due_section = queries.get("due", {})
    if isinstance(due_section, dict):
        # Root-level keys = default config (type, key, sort_by are strings at root)
        if due_section.get("type"):
            all_due_configs["default"] = {
                "type": due_section.get("type", "followup"),
                "key": due_section.get("key", "client"),
                "sort_by": due_section.get("sort_by", ""),
                "days": due_section.get("days", 7),
                "exclude_results": due_section.get("exclude_results", [])
            }
        # Nested configs (followup, assessment, investment are dicts)
        for name, cfg in due_section.items():
            if isinstance(cfg, dict) and cfg.get("type"):
                all_due_configs[name] = cfg
    
    for k, v in queries.items():
        if not isinstance(v, dict):
            continue
        if k.startswith("due."):
            name = k[4:]
            if name not in all_due_configs:
                all_due_configs[name] = v
        elif k.startswith("due_"):
            name = k[4:]
            if name not in all_due_configs:
                all_due_configs[name] = v
    
    # Ensure at least default exists
    if not all_due_configs:
        all_due_configs = {"default": {
            "type": "followup",
            "key": "client",
            "sort_by": "intent",
            "days": 7,
            "exclude_results": ["fix_appointment", "deceased", "not_relevant", "another_provider"]
        }}
    
    return render_template("query_builder.html",
        tab="query_builder", title="Query Builder",
        now=_now_str(), queries=queries, types=types,
        field_types=field_types,
        time_options=_get_time_options(), year_range=_YEAR_RANGE,
        due_config=all_due_configs)


@app.route("/query-builder/save", methods=["POST"])
def query_builder_save():
    """Receive full queries state from builder and rewrite queries.toml."""
    data = request.get_json(silent=True) or {}
    try:
        svc.save_queries_full(
            data.get("queries", {}),
            data.get("metrics", {}),
            data.get("dashboards", {}),
            data.get("aliases", {}),
            data.get("due", {}),
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
        queries = svc.get_queries()
        reserved = ("metrics", "dashboards", "due")
        # helper: normalise raw queries from TOML (list group → string)
        def _raw_q():
            return {k: _normalise_query_for_write(v)
                    for k, v in queries.items()
                    if k not in reserved and isinstance(v, dict) and "alias" not in v}
        def _raw_a():
            return {k: v for k, v in queries.items()
                    if k not in reserved and isinstance(v, dict) and "alias" in v}
        if kind == "metric":
            if name not in queries.get("metrics", {}):
                return jsonify(ok=False, error=f"Metric '{name}' not found")
            del queries["metrics"][name]
            svc.save_queries_full(_raw_q(), queries.get("metrics", {}),
                                queries.get("dashboards", {}), _raw_a())
        elif kind == "dashboard":
            if name not in queries.get("dashboards", {}):
                return jsonify(ok=False, error=f"Dashboard '{name}' not found")
            del queries["dashboards"][name]
            svc.save_queries_full(_raw_q(), queries.get("metrics", {}),
                                queries.get("dashboards", {}), _raw_a())
        elif kind == "alias":
            svc.save_queries_full(_raw_q(), queries.get("metrics", {}),
                                queries.get("dashboards", {}),
                                {k: v for k, v in _raw_a().items() if k != name})
        else:
            if name not in queries or name in reserved:
                return jsonify(ok=False, error=f"Query '{name}' not found")
            del queries[name]
            svc.save_queries_full(_raw_q(), queries.get("metrics", {}),
                                queries.get("dashboards", {}), _raw_a())
        return jsonify(ok=True)
    except Exception as e:
        return jsonify(ok=False, error=str(e))


# ══════════════════════════════════════════════════════════════════════════════
# Queries
# ══════════════════════════════════════════════════════════════════════════════

@app.route("/queries")
def queries_get():
    try:
        all_q = svc.get_queries()
        schema = svc.get_schema()
        field_types = _build_field_types(schema)
    except Exception:
        log.exception("Failed to load schema/queries for queries page")
        all_q = {}
        field_types = {}
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
        custom_time=request.args.get("custom_time", ""),
        from_date=request.args.get("from_date", ""),
        to_date=request.args.get("to_date", ""),
        field_types=field_types)

@app.route("/queries/run", methods=["POST"])
def queries_run():
    data = request.get_json(silent=True) or {}
    kind = data.get("kind","q")
    name = data.get("name","")
    from_date = data.get("from_date") or None
    to_date   = data.get("to_date") or None
    raw_time = data.get("time","") or None
    # reject any value that is not a known alias and not a valid YYYY, YYYY-MM, or YYYY-MM-DD
    _valid = {code for _, code in _get_time_options()}
    if from_date:
        time = "range"
    elif raw_time and raw_time not in _valid and \
       not re.fullmatch(r"\d{4}(?:-\d{2}(?:-\d{2})?)?", raw_time):
        return jsonify(ok=False, error=f"Invalid time window: {raw_time}")
    else:
        time = raw_time
    try:
        if kind == "d":
            result = svc.get_dashboard(name, time or "tm", use_dashboard_time=True,
                                       from_date=from_date, to_date=to_date)
            result["kind"] = "dashboard"
            # Add human-readable time label
            cfg = svc.get_config()
            cycles = cfg.get("cycles", {})
            custom_time = ""
            time_for_label = time or "tm"
            result["time_label"] = _build_period_label(time_for_label, custom_time, cycles)
        elif kind == "m":
            result = svc.get_metric(name, time or "tm", from_date=from_date, to_date=to_date)
            result["kind"] = "metric"
        else:
            result = svc.run_query(name, time, from_date=from_date, to_date=to_date)
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
        field_types = _build_field_types(schema)
    except PTOSError:
        types = []
        field_types = {}
    log_files = svc.get_log_files()
    return render_template("browse.html",
        tab="browse", title="Browse", now=_now_str(),
        types=types, field_types=field_types, log_files=log_files,
        time_options=_get_time_options(), year_range=_YEAR_RANGE,
        current_time=request.args.get("time", "tm"),
        custom_time=request.args.get("custom_time", ""),
        from_date=request.args.get("from_date", ""),
        to_date=request.args.get("to_date", ""))

@app.route("/browse/run", methods=["POST"])
def browse_run():
    data   = request.get_json(silent=True) or {}
    raw_time = data.get("time","tm")
    from_date = data.get("from_date") or None
    to_date   = data.get("to_date") or None
    _valid = {code for _, code in _get_time_options()}
    if from_date:
        time = "range"
    elif raw_time and raw_time not in _valid and \
       not re.fullmatch(r"\d{4}(?:-\d{2}(?:-\d{2})?)?", raw_time):
        time = "tm"
    else:
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
        combined = svc._filters_to_expr(where)
        filters  = [f"({combined}) AND ({expr})"] if combined else [expr]
    elif expr:
        filters = [expr]
    elif where:
        filters = where
    else:
        filters = []
    try:
        if group:
            result = svc.get_group(filters, time, [group], from_file=file,
                                   from_date=from_date, to_date=to_date)
            result["kind"] = "group"
        else:
            result = svc.get_records(filters, time, search=search,
                                     sort=sort, from_file=file,
                                     from_date=from_date, to_date=to_date)
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
    from_date = params.get("from_date") or None
    to_date   = params.get("to_date") or None
    if isinstance(where, str):
        where = [where] if where.strip() else []
    if expr and where:
        combined = svc._filters_to_expr(where)
        filters  = [f"({combined}) AND ({expr})"] if combined else [expr]
    elif expr:
        filters = [expr]
    elif where:
        filters = where
    else:
        filters = []
    try:
        data    = svc.get_records(filters, time, search=search, from_file=file,
                                  from_date=from_date, to_date=to_date)
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
    log_files = svc.get_log_files()
    current = request.args.get("file","")
    if not current and log_files: current = log_files[-1]
    content = ""
    if current:
        path = os.path.join(svc.RECORDS_DIR, current)
        if os.path.exists(path):
            with open(path,encoding="utf-8") as f: content = f.read()
    return render_template("editor.html",
        tab="editor", title="Log Editor", now=_now_str(),
        log_files=log_files, current_file=current, content=content, msg=None)

@app.route("/editor/content")
def editor_content():
    """Return file content for AJAX loading (used for goto line feature)."""
    file = request.args.get("file", "")
    if not file or "/" in file or "\\" in file or " " in file:
        return "Invalid filename", 400
    path = os.path.join(svc.RECORDS_DIR, file)
    if not os.path.exists(path):
        return "File not found", 404
    with open(path, encoding="utf-8") as f:
        return f.read(), 200, {"Content-Type": "text/plain"}

@app.route("/editor/save", methods=["POST"])
def editor_save():
    data = request.get_json(silent=True) or {}
    file = data.get("file",""); content = data.get("content","")
    if not file or "/" in file or "\\" in file:
        return jsonify(ok=False, error="Invalid filename")
    path = os.path.join(svc.RECORDS_DIR, file)
    if not os.path.exists(path):
        return jsonify(ok=False, error=f"File not found: {file}")
    svc.write_file(path, content)
    # invalidate caches — editor can modify any config file
    svc.invalidate_all()
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
        result = svc.safe_parse_line(line)
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
        result = svc.lint_all()
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
    parsed = svc.safe_parse_line(line)
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
    
    # Override with URL params if present (supports cascade parent field changes)
    for key in request.args:
        if key not in ("filepath", "lineno", "line", "return_to"):
            val = request.args.get(key, "")
            if val:
                field_values[key] = val
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
    tag_context = []
    if rtype:
        ts = schema.get("type", {}).get(rtype, {})
        schema_tag_options = svc.resolve_tags(schema, ts, field_values)
        tag_context = svc.get_tag_context(rtype, field_values)
    tag_options = list(current_tags) + [t for t in schema_tag_options if t not in current_tags]
    return_to = request.args.get("return_to") or request.referrer or url_for("browse_get")
    # Only allow internal paths — reject anything that could be javascript: or external
    if not return_to.startswith("/"):
        return_to = url_for("browse_get")
    return render_template("edit.html",
        tab="browse", title="Edit Record", now=_now_str(),
        filepath=filepath, lineno=lineno_int, old_line=line,
        return_to=return_to,
        rtype=rtype, field_defs=field_defs,
        global_field_defs=_build_global_field_defs(schema, field_values),
        tag_options=tag_options, history_tags=history_filtered_tags,
        tag_context=tag_context,
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
    # collect global optional fields from form
    for fname in svc.get_global_fields(schema):
        val = request.form.get(fname, "").strip()
        if val: new_record[fname] = val.replace(" ", "_")
    tags = request.form.getlist("tag") + custom_tags
    if tags: new_record["tag"] = tags
    
    parsed = svc.safe_parse_line(old_line)
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
    if not return_to.startswith("/"):
        return_to = url_for("browse_get")
    if not set_args and new_note is None:
        return redirect(return_to)
    if not os.path.abspath(filepath).startswith(os.path.abspath(svc.RECORDS_DIR)):
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
        tag_options = svc.resolve_tags(schema, ts, field_values)
        history_filtered_tags = []
        try:
            history_with_context = svc.get_history_suggestions(rtype, field_values)
            history_filtered_tags = history_with_context.get("filtered_tags", [])
        except Exception:
            pass
        tag_context = svc.get_tag_context(rtype, field_values) if rtype else []
        return render_template("edit.html",
            tab="browse", title="Edit Record", now=_now_str(),
            filepath=filepath, lineno=lineno_int, old_line=old_line,
            return_to=return_to,
            rtype=rtype, field_defs=field_defs,
            global_field_defs=_build_global_field_defs(schema, field_values),
            tag_options=tag_options, history_tags=history_filtered_tags,
            tag_context=tag_context,
            field_values=field_values,
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
        combined = svc._filters_to_expr(where)
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
        except Exception: lineno = None
    if not filepath or not old_line:
        return jsonify(ok=False, error="filepath and old_line required")
    if not os.path.abspath(filepath).startswith(os.path.abspath(svc.RECORDS_DIR)):
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
        except Exception: lineno = None
    if not filepath or not old_line:
        return jsonify(ok=False, error="filepath and old_line required")
    if not os.path.abspath(filepath).startswith(os.path.abspath(svc.RECORDS_DIR)):
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


@app.route("/api/records/bulk_delete", methods=["POST"])
def api_records_bulk_delete():
    data    = request.get_json(silent=True) or {}
    records = data.get("records", [])
    if not records:
        return jsonify(ok=False, error="No records provided")
    # Validate all filepaths before touching anything
    for r in records:
        fp = r.get("filepath", "")
        if not fp or not os.path.abspath(fp).startswith(
                os.path.abspath(svc.RECORDS_DIR)):
            return jsonify(ok=False, error=f"Invalid filepath: {fp}")
    try:
        result = svc.bulk_delete(records)
        return jsonify(ok=True, **result)
    except PTOSError as e:
        return jsonify(ok=False, error=str(e))
    except Exception as e:
        return jsonify(ok=False, error=str(e))


@app.route("/api/records/bulk_set", methods=["POST"])
def api_records_bulk_set():
    data     = request.get_json(silent=True) or {}
    records  = data.get("records", [])
    set_args = data.get("set_args", [])
    if not records:
        return jsonify(ok=False, error="No records provided")
    if not set_args:
        return jsonify(ok=False, error="No set_args provided")
    # Validate all filepaths
    for r in records:
        fp = r.get("filepath", "")
        if not fp or not os.path.abspath(fp).startswith(
                os.path.abspath(svc.RECORDS_DIR)):
            return jsonify(ok=False, error=f"Invalid filepath: {fp}")
    try:
        result = svc.bulk_set(records, set_args)
        return jsonify(ok=True, **result)
    except PTOSError as e:
        return jsonify(ok=False, error=str(e))
    except Exception as e:
        return jsonify(ok=False, error=str(e))

@app.route("/api/type_fields/<rtype>")
def api_type_fields(rtype):
    try:
        schema     = svc.get_schema()
        bad        = svc.non_dimension_fields()
        
        # Parse context from query param (e.g., ?context=domain:self,category:transport)
        context = {}
        ctx_str = request.args.get("context", "")
        if ctx_str:
            for pair in ctx_str.split(","):
                if ":" in pair:
                    k, v = pair.split(":", 1)
                    context[k.strip()] = v.strip()
        
        defs       = _build_field_defs(schema, rtype, context if context else None)
        
        # Get history suggestions with context filtering (like add/edit)
        history    = svc.get_history_suggestions(rtype, context if context else None)
        
        # Add tag field with cascade options if type has tag triggers
        type_schema = schema.get("type", {}).get(rtype, {})
        tag_triggers = type_schema.get("tags", {})
        if tag_triggers:
            # Find the first/primary tag trigger (usually 'category')
            tag_parent = list(tag_triggers.keys())[0] if tag_triggers else None
            # Schema-based tag options (context-dependent, only from tag triggers)
            schema_opts = []
            if tag_parent and tag_parent in context:
                schema_opts = tag_triggers.get(tag_parent, {}).get("options", {}).get(context[tag_parent], [])
            defs.append({
                "name": "tag",
                "required": False,
                "options": schema_opts,
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

        # append global_fields so Browse chips and Query Builder can filter on them
        for fname, fdef in schema.get("global_fields", {}).items():
            if not isinstance(fdef, dict):
                continue
            defs.append({
                "name":                 fname,
                "required":             False,
                "options":              fdef.get("options", []),
                "is_int":               fdef.get("type") == "int",
                "is_datetime":          fdef.get("type") == "datetime",
                "unit":                 fdef.get("unit", ""),
                "parent":               "",
                "has_parent":           False,
                "is_parent":            False,
                "is_tag_trigger":       False,
                "is_condition_trigger": False,
                "show_when":            {},
            })
            if fname not in bad and fdef.get("type") != "int":
                dimensions.append(fname)
        
        # Always include date for sorting (applies to all record types)
        if "date" not in dimensions:
            dimensions.insert(0, "date")
        for vf in ("day", "month", "year"):
            if vf not in dimensions:
                dimensions.append(vf)
        
        return jsonify(fields=defs, dimensions=dimensions,
                       history_tags=history.get("filtered_tags", history.get("tags", [])),
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
            line = svc.build_record_line(date_str, record, note)
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
        svc.save_as_preset(name, record, note=note)
        svc.invalidate("presets")
        return jsonify(ok=True, name=name)
    except PTOSError as e:
        return jsonify(ok=False, error=str(e))
    except Exception as e:
        return jsonify(ok=False, error=str(e))


@app.route("/api/preset_use", methods=["POST"])
def api_preset_use():
    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()
    if name:
        svc.increment_preset_use(name)
    return jsonify(ok=True)


@app.route("/api/preset_delete", methods=["POST"])
def api_preset_delete():
    data = request.get_json(silent=True) or {}
    name = data.get("name", "").strip()
    if not name:
        return jsonify(ok=False, error="Preset name required")
    try:
        svc.delete_preset(name)
        svc.invalidate("presets")
        return jsonify(ok=True)
    except PTOSError as e:
        return jsonify(ok=False, error=str(e))
    except Exception as e:
        return jsonify(ok=False, error=str(e))


# ── SSE (Server-Sent Events) ──────────────────────────────────────────────────
_sse_clients = []
_sse_lock = threading.Lock()

def _sse_broadcast(event_type, data=""):
    payload = json.dumps({"type": event_type, "data": data})
    with _sse_lock:
        for q in _sse_clients:
            try:
                q.put_nowait(payload)
            except Exception:
                pass

@app.route("/api/events")
def api_events():
    def stream():
        q = queue.Queue()
        with _sse_lock:
            _sse_clients.append(q)
        try:
            yield "data: connected\n\n"
            while True:
                msg = q.get()
                if msg is None:
                    break
                yield f"data: {msg}\n\n"
        except GeneratorExit:
            pass
        finally:
            with _sse_lock:
                if q in _sse_clients:
                    _sse_clients.remove(q)
    return Response(stream(), mimetype="text/event-stream")

# ── Todo notification background thread ─────────────────────────────────────

def _detect_notify_platform():
    if "termux" in os.environ.get("PREFIX", "") or os.path.exists("/data/data/com.termux"):
        return "termux"
    if platform.system() == "Linux":
        return "linux"
    if platform.system() == "Darwin":
        return "macos"
    if platform.system() == "Windows":
        return "windows"
    return None

_notify_platform = _detect_notify_platform()

def _system_notify(title, body):
    try:
        if _notify_platform == "termux":
            subprocess.run(["termux-notification", "--title", title, "--content", body],
                          timeout=5, capture_output=True)
        elif _notify_platform == "linux":
            subprocess.run(["notify-send", title, body],
                          timeout=5, capture_output=True)
        elif _notify_platform == "macos":
            script = f'display notification "{body}" with title "{title}"'
            subprocess.run(["osascript", "-e", script],
                          timeout=5, capture_output=True)
        elif _notify_platform == "windows":
            ps = (
                '[void][System.Reflection.Assembly]::LoadWithPartialName("System.Windows.Forms");'
                '$n=New-Object System.Windows.Forms.NotifyIcon;'
                '$n.Icon=[System.Drawing.SystemIcons]::Information;'
                '$n.Visible=$true;'
                f'$n.ShowBalloonTip(5000,"{title}","{body}",[System.Windows.Forms.ToolTipIcon]::Info)'
            )
            subprocess.run(["powershell", "-Command", ps],
                          timeout=5, capture_output=True)
    except Exception:
        pass

def _housekeeping_loop(interval_minutes=5):
    """Background thread: check due todos, broadcast via SSE."""
    import ptos_todo as _todo_mod
    notified = set()
    while True:
        time.sleep(interval_minutes * 60)
        # ── todo notifications ──
        try:
            todos, _ = _todo_mod.load_todos(svc.TODO_PATH)
            due = _todo_mod.get_due_todos(todos, lookahead_days=1)
            current = {(t.line_no, str(t.due), t.due_time) for t in due}
            new = [t for t in due if (t.line_no, str(t.due), t.due_time) not in notified]
            if new:
                tasks = [{"line_no": t.line_no, "description": t.description,
                          "priority": t.priority, "due": str(t.due),
                          "due_time": t.due_time} for t in new]
                _sse_broadcast("todo-due", tasks)
                if len(new) == 1:
                    t = new[0]
                    p = f"({t.priority}) " if t.priority else ""
                    body = f"{p}{t.description} (due {t.due})"
                else:
                    body = f"{len(new)} tasks due today/tomorrow"
                _system_notify("Todo due", body)
            notified = current
        except Exception:
            pass


def _sync_loop(interval_minutes=30):
    """Background thread: periodic rclone bisync."""
    while True:
        time.sleep(interval_minutes * 60)
        if _sync_busy:
            continue
        try:
            sync_cfg = svc.get_config().get("sync", {})
            if not sync_cfg.get("remote_name") or not sync_cfg.get("remote_path"):
                continue
            if not shutil.which("rclone"):
                continue
            result = ptos.run_sync("bisync")
            if result.get("ok"):
                _sse_broadcast("sync-done", result)
        except Exception:
            pass

# ── Shutdown ──────────────────────────────────────────────────────────────────

@app.route("/shutdown", methods=["GET", "POST"])
def shutdown_server():
    _sse_broadcast("shutdown")
    try:
        _exit_backup()
    except Exception:
        pass
    try:
        _exit_sync()
    except Exception:
        pass
    def _exit():
        time.sleep(3)  # Give SSE time to deliver to all tabs
        os._exit(0)
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
        combined   = svc._filters_to_expr(where)
        where_expr = f"({combined}) AND ({expr})" if combined else expr
    elif expr:
        where_expr = expr
    elif where:
        where_expr = svc._filters_to_expr(where)
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

def _exit_backup():
    """Run backup on exit if configured."""
    try:
        backup_config = svc.get_backup_config()
        if backup_config.get("auto_backup_on_shutdown", True):
            created, backup_path = svc.backup_if_needed()
            if created:
                print(f"Exit backup created: {os.path.basename(backup_path)}")
            else:
                print("Exit backup skipped: no changes detected")
    except Exception as e:
        print(f"Exit backup failed: {e}")

atexit.register(_exit_backup)

def _exit_sync():
    """Run sync on exit if configured."""
    try:
        sync_cfg = svc.get_config().get("sync", {})
        if sync_cfg.get("auto_sync_on_shutdown") and sync_cfg.get("remote_name") and sync_cfg.get("remote_path"):
            if not shutil.which("rclone"):
                print("Shutdown sync skipped: rclone not found")
                return
            print("Running shutdown sync...")
            result = ptos.run_sync("bisync")
            if result.get("ok"):
                print("Shutdown sync complete")
            else:
                print(f"Shutdown sync failed: {result.get('error', 'unknown')}")
    except Exception as e:
        print(f"Shutdown sync skipped: {e}")

atexit.register(_exit_sync)

if __name__ == "__main__":
    # Smart backup on startup if configured
    try:
        backup_config = svc.get_backup_config()
        if backup_config.get("auto_backup_on_startup", True):
            created, backup_path = svc.backup_if_needed()
            if created:
                print(f"Startup backup created: {os.path.basename(backup_path)}")
            else:
                print("Startup backup skipped: no changes detected")
        else:
            print("Startup backup disabled in config")
    except PTOSError as e:
        print(f"Startup backup skipped: {e}")
    except Exception as e:
        print(f"Startup backup skipped: {e}")
    
    # Auto sync on startup if configured
    try:
        sync_cfg = svc.get_config().get("sync", {})
        if sync_cfg.get("auto_sync_on_startup") and sync_cfg.get("remote_name") and sync_cfg.get("remote_path"):
            if not shutil.which("rclone"):
                print("Startup sync skipped: rclone not found")
            else:
                print("Running startup sync...")
                result = ptos.run_sync("bisync")
                if result.get("ok"):
                    print("Startup sync complete")
                else:
                    print(f"Startup sync failed: {result.get('error', 'unknown')}")
    except Exception as e:
        print(f"Startup sync skipped: {e}")
    
    # Archive old done tasks on startup
    try:
        todo_cfg = svc.get_config().get("todo", {})
        archive_mo = todo_cfg.get("archive_months", 6)
        import ptos_todo as _todo
        archived = _todo.archive_done_todos(ptos.DONE_PATH, threshold_months=archive_mo)
        if archived:
            print(f"Archived {archived} old done tasks")
    except Exception as e:
        print(f"Archive skipped: {e}")
    
    print("\nPTOS Web UI")
    print("Open: http://localhost:5000\n")

    # Start housekeeping background thread
    try:
        todo_cfg = svc.get_config().get("todo", {})
        notify_min = todo_cfg.get("notify_interval", 5)
        if notify_min > 0:
            _t = threading.Thread(target=_housekeeping_loop, args=(notify_min,), daemon=True)
            _t.start()
            print(f"Todo notifications enabled (every {notify_min} min) [{_notify_platform or 'browser-only'}]")
    except Exception:
        pass

    # Start periodic sync background thread
    try:
        sync_cfg = svc.get_config().get("sync", {})
        sync_min = sync_cfg.get("sync_interval_minutes", 0)
        if sync_min > 0:
            _t = threading.Thread(target=_sync_loop, args=(sync_min,), daemon=True)
            _t.start()
            print(f"Periodic sync enabled (every {sync_min} min)")
    except Exception:
        pass

    app.run(host="127.0.0.1", port=5000)
