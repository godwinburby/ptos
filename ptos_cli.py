"""
ptos_cli.py — Command-line interface for PTOS
==============================================
Entry point for the `ptos` CLI command.
All engine logic lives in ptos.py; this file owns argument parsing,
output rendering, and the main() dispatch loop.

Run:  python ptos_cli.py [args]
      python ptos.py     [args]   ← still works via backward-compat shim
"""

import sys
import os
import datetime as dt
import json
import csv
import re
import argparse
import subprocess

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import ptos
from ptos import (
    # Constants
    BASE_DIR, RECORDS_DIR, BACKUP_DIR, EXPORTS_DIR,
    SCHEMA_PATH, CONFIG_PATH, QUERIES_PATH, PRESETS_PATH, TODO_PATH,
    TimeCode,
    # Config / schema helpers
    get_config, get_schema, get_queries, get_presets,
    # Record I/O
    scan_records, append_record, find_records_with_location,
    rewrite_line_in_file, run_set,
    # Validation / lint
    validate_record, lint_all_records,
    # Interactive helpers
    interactive_add, quick_add, complete_record,
    choose_from_list, choose_from_list_optional,
    # Query / metric / dashboard runners
    run_metric, run_dashboard,
    # Output helpers
    render_group, render_pivot, render_summary, show_fields,
    fmt_date, fmt_datetime, currency,
    # Preset / query management
    save_as_preset, delete_preset, save_query,
    # Misc
    resolve_time, resolve_date, parse_date, today,
    edit_target, init_ptos, set_home, set_user_name, set_date_format,
    set_currency, add_cycle, set_auth,
    add_type, add_type_field, remove_type,
    restore_data, restore_config,
    backup_data, backup_config, list_backups, delete_backup,
    doctor_check, print_doctor_results,
    get_log_files, atomic_write, run_sync,
    # Output / rendering helpers
    group_results, pivot_results, detect_value_field,
    fmt_avg, render_group, render_pivot,
    # Field introspection
    numeric_fields, non_dimension_fields, derived_fields,
    datetime_fields, compute_derived,
    # Record helpers
    parse_line, lint_records, build_record_line,
    # Link helpers
    resolve_link, list_link_ids, check_dangling_links,
    generate_unique_id, append_links_to_line, append_record_id,
    append_todo_id, append_links_to_todo_line,
    # Date helpers
    month_range, quarter_range, resolve_cycle,
    # Internal helpers used by CLI
    _disp, _filters_to_expr, resolve_editor, _TIME_ALIASES, _glob_match,
)

# --------------------------------------------------
# CLI  — argument parsing only, no logic
# --------------------------------------------------

def build_parser(cycles):
    cycle_help = ", ".join(f"{n}, {n}-1, {n}-2" for n in cycles) if cycles \
                 else "custom cycles defined in config.toml"

    p = argparse.ArgumentParser(
        prog="ptos",
        description=(
            "PTOS — Plain Text Operating System\n"
            "Log it. Query it. Own it.\n"
            "github.com/godwinburby/ptos\n\n"
            "Record and analyse life, work, and finance events\n"
            "using structured plain-text logs.\n\n"
            "Fields become dimensions. Numeric fields become measures."
        ),
        epilog=(
            "Examples:\n"
            "  ptos --add type=expense domain=self category=food amount=120\n"
            "  ptos --add type=expense domain=self category=food amount=120 --date yesterday\n"
            "  ptos --preset commute\n"
            "  ptos --where type=expense --group category\n"
            "  ptos --where type=expense --group category --time lm\n"
            "  ptos --where type=expense --trend\n"
            "  ptos --where type=expense --pivot domain category --count\n"
            "  ptos --query dashboard\n"
            "  ptos --query myquery --time tq\n"
            "  ptos --due\n"
            "  ptos --time 2026-03\n"
            "  ptos --time 2026-03-15\n"
            "  ptos --from 2026-01-01 --to 2026-03-31\n"
            "  ptos --lint\n"
            "  ptos --backup-full\n"
            "  ptos --backup-config\n"
            "  ptos --restore-full\n"
            "  ptos --restore-config\n"
            "  ptos --list-backups\n"
            "\n"
            "Todo:\n"
            "  ptos --todo-add \"(A) Call supplier @phone due:tomorrow\"\n"
            "  ptos --todo-list\n"
            "  ptos --todo-list --project Home --context phone\n"
            "  ptos --todo-list --due-range overdue --table\n"
            "  ptos --todo-list --all\n"
            "  ptos --todo-done 3\n"
            "  ptos --todo-edit 3 priority=B due:tomorrow +Urgent\n"
            "  ptos --todo-edit 3 -+Home -@errand\n"
            "  ptos --todo-bulk-edit 1,3,5 priority=B due:tomorrow\n"
            "  ptos --todo-delete 5\n"
            "  ptos --todo-undo 5\n"
            "  ptos --todo-done-list\n"
            "  ptos --todo-done-edit 3 priority=C\n"
            "  ptos --todo-done-delete 5\n"
            "  ptos --todo-due\n"
            "  ptos --todo-due 7\n"
            "  ptos --todo-projects\n"
            "  ptos --todo-contexts\n"
            "  ptos --todo-archive\n"
            "\n"
            "Time windows (full form / short):\n"
            "  today              td\n"
            "  yesterday          yd\n"
            "  this-week          tw\n"
            "  last-week          lw\n"
            "  this-month         tm   (default)\n"
            "  last-month         lm\n"
            "  this-quarter       tq\n"
            "  last-quarter       lq\n"
            "  this-year          ty\n"
            "  last-year          ly\n"
            "  YYYY-MM              (e.g. 2026-03)\n"
            "  YYYY-MM-DD           (e.g. 2026-03-15)\n"
            "  custom cycles defined in config.toml (e.g. clinic, clinic-1)\n"
        ),
        formatter_class=argparse.RawTextHelpFormatter,
    )

    add = p.add_argument_group("Add")
    add.add_argument("-a", "--add",          nargs="*", help="Add record (no args = interactive)")
    add.add_argument("-n", "--note",                    help="Note to attach to record")
    add.add_argument("-d", "--date",                    help="Date for the record (YYYY-MM-DD, default: today)")
    add.add_argument("-p", "--preset",       nargs="*", help="Quick-add from preset")
    add.add_argument("--save-preset",                   help="Save the record being added as a preset under this name")
    add.add_argument("--delete-preset",                  help="Delete a preset by name")
    add.add_argument("--link", nargs="+", metavar=("TARGET", "SRC_TARGET"),
                     help="Link an entry. With --add: one TARGET to link the new\n"
                          "  record to (generates its id). Standalone: link existing\n"
                          "  entries: --link SRC_TARGET TARGET\n"
                          "  (e.g. --link expense:k3f9a1 project:p91a)")

    qry = p.add_argument_group("Query")
    qry.add_argument("-q", "--query",  nargs="?", const="__LIST__", help="Run saved query (no name = list all)")
    qry.add_argument("-w", "--where",  nargs="+", action="append",  help="Filter expressions — operators: = != > < >= <= ~(contains) !~(not contains)\n  Simple: --where type=expense --where amount>100\n  Expression: --where \"(category=home OR category=household) AND amount>100\"")
    qry.add_argument("-t", "--time",   default="this-month",        help="Time window — full or short: td yd tw lw tm lm tq lq ty ly YYYY YYYY-MM YYYY-MM-DD, or custom cycles from config.toml")
    qry.add_argument("-f", "--from",   dest="date_from",            help="Start date YYYY-MM-DD, YYYY-MM, or YYYY")
    qry.add_argument("-T", "--to",     dest="date_to",              help="End date YYYY-MM-DD, YYYY-MM, or YYYY")
    qry.add_argument("-y", "--type",                                help="Filter by record type")
    qry.add_argument("-g", "--tag",    action="append",             help="Filter by tag (repeatable)")
    qry.add_argument("-S", "--search",                              help="Full-text search")
    qry.add_argument("--linked-to", dest="linked_to", nargs="+", metavar="TYPE:ID",
                     help="Only show entries whose links reference the given\n"
                          "  type:id target (e.g. project:p91a)")
    qry.add_argument("--save",                                      help="Save current query to queries.toml under this name")
    qry.add_argument("--add-dashboard", dest="add_dashboard", metavar="NAME",
                     help="Add a dashboard referencing metrics to queries.toml")
    qry.add_argument("--metrics", nargs="+", metavar="METRIC",
                     help="Metrics for the new dashboard (with --add-dashboard)")
    qry.add_argument("--highlight", nargs="+", metavar="METRIC:COLOR",
                     help="Highlight entries (with --add-dashboard). Colors: accent, warn, success, error")
    qry.add_argument("--file",   dest="from_file", metavar="FILENAME", help="Read from this file in records/ folder (e.g. 2025.log)")
    qry.add_argument("--select", nargs="+", metavar="FIELD",           help="Show only these fields in output (date and type always included; add note to include notes)")

    ana = p.add_argument_group("Analyse")
    ana.add_argument("-G", "--group",  nargs="+", help="Group by one or more fields")
    ana.add_argument("-v", "--pivot",  nargs="+", metavar=("ROW", "COL"), help="Pivot table")
    ana.add_argument("--count",        action="store_true", help="Count rows instead of summing")
    ana.add_argument("--sort",                              help="Sort pivot by column name")
    ana.add_argument("--trend",        nargs="?", const=6, type=int, metavar="N",
                     help="Show last N periods side by side (default: 6)")
    ana.add_argument("--due",          nargs="?", const="__DEFAULT__", metavar="NAME_OR_DAYS",
                     help="Show overdue records. Optional: named due config from queries.toml, or N days override")
    ana.add_argument("--thresholds",   nargs="?", const="__ALL__", metavar="TIME",
                     help="Show threshold status. Optional: time window override (default: this-month)")
    ana.add_argument("--sum-field", dest="sum_field", metavar="FIELD",
                     help="Field to sum instead of the default numeric field (e.g. advance, duration)")
    ana.add_argument("--table",        action="store_true", help="Show results as a table instead of raw lines")
    ana.add_argument("--export",       nargs="?", const="__AUTO__", metavar="FILENAME",
                     help="Export results to CSV in exports/ folder. Optional filename (no extension).")

    todo = p.add_argument_group("Todo")
    todo.add_argument("--todo-add", nargs="*", metavar="TEXT",
                     help="Add a todo (todo.txt format — pri:a +Project @context due:tomorrow)\n"
                          "  No args = interactive prompt")
    todo.add_argument("--todo-list", action="store_true",
                     help="List open todos (with --all: include done)")
    todo.add_argument("--todo-done", metavar="N",
                     help="Mark todo at line N complete")
    todo.add_argument("--todo-edit", nargs="+", metavar=("N", "KEY=VALUE"),
                     help="Edit fields on todo at line N  (e.g. --todo-edit 3 due:2026-07-25 priority=B)\n"
                          "  +Project add project, -+Project remove, @context add, -@context remove")
    todo.add_argument("--todo-bulk-edit", nargs="+", metavar=("LINE_NOS", "KEY=VALUE"),
                     help="Edit multiple todos  (e.g. --todo-bulk-edit 1,3,5 priority=B due:tomorrow)\n"
                          "  Supports ranges: 1-5, combos: 1,3,5-7")
    todo.add_argument("--todo-delete", metavar="N",
                     help="Delete todo at line N")
    todo.add_argument("--todo-undo", metavar="N",
                     help="Undo completion — move todo from done.txt back to todo.txt")
    todo.add_argument("--todo-done-list", action="store_true",
                     help="List completed todos")
    todo.add_argument("--todo-done-delete", metavar="N",
                     help="Permanently delete a completed todo from done.txt")
    todo.add_argument("--todo-done-edit", nargs="+", metavar=("N", "KEY=VALUE"),
                     help="Edit a completed todo (e.g. --todo-done-edit 3 priority=C)")
    todo.add_argument("--todo-projects", action="store_true",
                     help="List all projects with task counts")
    todo.add_argument("--todo-contexts", action="store_true",
                     help="List all contexts with task counts")
    todo.add_argument("--todo-due", nargs="?", const=1, type=int, default=None, metavar="DAYS",
                     help="Show due/overdue todos (default: today+overdue)\n"
                          "  Optional: lookahead DAYS (e.g. --todo-due 7)")
    todo.add_argument("--todo-archive", action="store_true",
                     help="Archive old done items to done.YYYY.txt")

    tod_f = p.add_argument_group("Todo filters (use with --todo-list)")
    tod_f.add_argument("--project", action="append", metavar="NAME",
                       help="Filter by +Project (repeatable)")
    tod_f.add_argument("--context", action="append", metavar="NAME",
                       help="Filter by @context (repeatable)")
    tod_f.add_argument("--priority", action="append", metavar="P",
                       help="Filter by priority A-D (repeatable)")
    tod_f.add_argument("--due-range", dest="due_range",
                       choices=["overdue", "today", "tomorrow", "upcoming", "someday", "none"],
                       help="Filter by due range")
    tod_f.add_argument("--todo-search", metavar="TEXT",
                       help="Search todo description (glob wildcards supported)")

    utl = p.add_argument_group("Utilities")
    utl.add_argument("-l", "--lint",    action="store_true", help="Validate records against schema")
    utl.add_argument("--fix",           action="store_true", help="With --lint: open files with errors in editor")
    utl.add_argument("-j", "--journal", nargs="?", const="today", default=None, metavar="DATE",
                     help="Open a journal file (default: today; accepts today/yesterday/YYYY-MM-DD)")
    utl.add_argument("-e", "--edit",    nargs="?", const="records", metavar="TARGET",
                     help="Edit a workspace file  (r s q c p d/j x)")
    utl.add_argument("--set",      nargs="+", metavar="KEY=VALUE",
                     help="Edit matched record(s)  (use with --where)\n"
                          "  key=value   replace field\n"
                          "  key+=value  append to list field (e.g. tag+=urgent)\n"
                          "  key-=value  remove from list field (e.g. tag-=urgent)")
    utl.add_argument("--set-note", dest="set_note", metavar="TEXT",
                     help="Replace the note on matched record(s)  (use with --where)")
    utl.add_argument("--delete",   action="store_true",
                     help="Delete matched record(s)  (use with --where)")
    utl.add_argument("--all",      action="store_true",
                     help="Apply --set/--delete to all matched records without interactive pick")
    utl.add_argument("--fields", action="store_true", help="Show field discovery report")
    utl.add_argument("--init",   action="store_true", help="Initialise workspace")
    utl.add_argument("--set-name", dest="set_name", metavar="NAME",
                     help="Set user name in config")
    utl.add_argument("--set-date-format", dest="set_date_format", metavar="FORMAT",
                     help="Set date display format: indian, us, eu, readable, iso, or custom strftime")
    utl.add_argument("--backup-full", action="store_true", help="Full backup: records/, templates/, config/, and backups/ folder")
    utl.add_argument("--backup-config", action="store_true", help="Config backup: only schema, queries, presets, and config toml files")
    utl.add_argument("--restore-full", nargs="?", const="", metavar="PATH", help="Restore from full backup (shows list if no path given)")
    utl.add_argument("--restore-config", nargs="?", const="", metavar="PATH", help="Restore from config backup (shows list if no path given)")
    utl.add_argument("--list-backups", action="store_true", help="List available backups in backups/ folder")
    utl.add_argument("--delete-backup", dest="delete_backup", metavar="NAME",
                     help="Delete a specific backup file by name")
    utl.add_argument("--set-currency", dest="set_currency", metavar="SYMBOL",
                     help="Set currency symbol in config")
    utl.add_argument("--add-cycle", dest="add_cycle", nargs=2, metavar=("NAME", "DAY"),
                     help="Add or replace a custom cycle: NAME DAY (day of month, 1-31)")
    utl.add_argument("--set-auth", dest="set_auth", nargs=2, metavar=("USERNAME", "PASSWORD"),
                     help="Set HTTP Basic Auth credentials (stored in plaintext in config)")
    utl.add_argument("--retro-id", dest="retro_id", metavar="TYPE",
                     help="Assign an id to an existing entry so it can be linked to.\n"
                          "  Records: --retro-id expense --where \"amount=450 category=food\"\n"
                          "  Todo:    --retro-id todo --search \"call nair\"")
    utl.add_argument("--doctor", action="store_true", help="Check PTOS installation health")
    utl.add_argument("--doctor-fix", dest="doctor_fix", action="store_true", help="With --doctor: fix any issues found")
    utl.add_argument("--check-schema", action="store_true", help="Validate schema.toml structure and report issues")
    utl.add_argument("--set-home", dest="set_home", metavar="PATH",
                     help="Point PTOS at a data folder  (writes .ptos_home)\n"
                          "  Migrates existing data to the new location")
    utl.add_argument("--bisync", action="store_true",
                     help="Bidirectional sync with remote (rclone bisync)\n"
                          "  Reads [sync] config from config.toml")
    utl.add_argument("--sync", action="store_true",
                     help="One-way push to remote (rclone sync) — DELETES\n"
                          "  anything on remote not present locally.\n"
                          "  Requires --confirm-delete")
    utl.add_argument("--confirm-delete", action="store_true",
                     help="Required alongside --sync to acknowledge it can\n"
                          "  delete remote files")
    utl.add_argument("--resync", action="store_true",
                     help="With --bisync: initialize bisync relationship\n"
                          "  (first-time setup or reset)")

    sch = p.add_argument_group("Schema")
    sch.add_argument("--add-type", dest="add_type", metavar="NAME",
                     help="Add a new record type to schema.toml")
    sch.add_argument("--required", nargs="+", metavar="FIELD",
                     help="Required fields for the new type (with --add-type)")
    sch.add_argument("--add-field", dest="add_field", metavar="TYPE.FIELD",
                     help="Add a field to a type (e.g. expense.fuel)")
    sch.add_argument("--field-type", dest="field_type",
                     choices=["int", "string", "datetime", "bool"], default="string",
                     help="Field type for --add-field (default: string)")
    sch.add_argument("--field-options", dest="field_options", nargs="+", metavar="OPTION",
                     help="Flat list of valid options for the new field (with --add-field)")
    sch.add_argument("--remove-type", dest="remove_type", metavar="NAME",
                     help="Remove a record type from schema.toml")

    return p

# --------------------------------------------------
# Query context  —  resolve what a saved query requests
# --------------------------------------------------

def resolve_query_context(args, queries):
    """
    Apply saved query settings to args.
    Returns (query_filters, metric_mode, dashboard_mode).
    Mutates args.time / args.date_from / args.date_to only when
    the CLI left them at their defaults.
    """
    # resolve alias first
    q_raw = queries.get(args.query, {})
    if isinstance(q_raw, dict) and "alias" in q_raw:
        target = q_raw["alias"]
        if target not in queries:
            sys.exit(f"Alias '{args.query}' points to '{target}' which does not exist.")
        args.query = target

    metrics    = queries.get("metrics",    {})
    dashboards = queries.get("dashboards", {})

    metric_mode    = args.query in metrics
    dashboard_mode = args.query in dashboards

    q = queries.get(args.query)
    if not q and not metric_mode and not dashboard_mode:
        sys.exit(f"Query not found: {args.query}")

    query_filters = []
    if q:
        raw_where = q.get("where")
        if isinstance(raw_where, list):
            # old array format — convert to single expression for apply_where
            expr = _filters_to_expr(raw_where)
            query_filters = [expr] if expr else []
        elif isinstance(raw_where, str) and raw_where.strip():
            query_filters = [raw_where]
        else:
            query_filters = []
        cli_time_default = (
            args.date_from is None and
            args.date_to   is None and
            args.time      == "this-month"
        )
        if cli_time_default:
            if "from" in q: args.date_from = q["from"]
            if "to"   in q: args.date_to   = q["to"]
            if "time" in q: args.time       = q["time"]
        if q.get("sum"):                args.sum   = True
        if "group" in q:                args.group = q["group"]
        if "pivot" in q:                args.pivot = q["pivot"]
        if q.get("count"):              args.count = True
        if "sort"  in q:                args.sort  = q["sort"]
        if "search" in q and not args.search:
            args.search = q["search"]
        if "trend" in q and args.trend is None:
            try:
                args.trend = int(q["trend"])
            except (ValueError, TypeError):
                sys.exit(f"Query '{args.query}': 'trend' must be an integer, got {q['trend']!r}")

    return query_filters, metric_mode, dashboard_mode

# --------------------------------------------------
# Trend engine
# --------------------------------------------------

def _prior_periods(time_keyword, n, cycles):
    """
    Return list of (label, start, end) for the N most recent periods
    ending with the one resolved by time_keyword, oldest first.
    ending with the one resolved by time_keyword, oldest first.
    Supports: clinic/custom cycles, this-month, last-month,
              this-week, this-quarter, YYYY-MM.
    """
    time_keyword = _TIME_ALIASES.get(time_keyword, time_keyword)
    periods = []

    # custom cycle  e.g. "clinic"
    for name, start_day in cycles.items():
        if re.fullmatch(rf"{name}(?:-\d+)?", time_keyword):
            for i in range(n - 1, -1, -1):
                s, e = resolve_cycle(start_day, i)
                label = name if i == 0 else f"{name}-{i}"
                periods.append((label, s, e))
            return periods

    # YYYY-MM
    if re.fullmatch(r"\d{4}-\d{2}", time_keyword):
        year, month = map(int, time_keyword.split("-"))
        for i in range(n - 1, -1, -1):
            m = month - i
            y = year
            while m < 1:
                m += 12
                y -= 1
            s, e = month_range(y, m)
            periods.append((f"{y}-{m:02d}", s, e))
        return periods

    now = today()

    if time_keyword in ("this-month", "last-month"):
        ref = now.replace(day=1)
        if time_keyword == "last-month":
            ref = (ref - dt.timedelta(days=1)).replace(day=1)
        for i in range(n - 1, -1, -1):
            d = ref.replace(day=1)
            for _ in range(i):
                d = (d - dt.timedelta(days=1)).replace(day=1)
            s, e = month_range(d.year, d.month)
            periods.append((d.strftime("%Y-%m"), s, e))
        return periods

    if time_keyword in ("this-week", "last-week"):
        ref_end = now - dt.timedelta(days=now.weekday() + 1)  # last Sunday
        if time_keyword == "this-week":
            ref_end = now - dt.timedelta(days=now.weekday() - 6)  # this Sunday
        for i in range(n - 1, -1, -1):
            end   = ref_end - dt.timedelta(weeks=i)
            start = end - dt.timedelta(days=6)
            periods.append((start.strftime("%b %d"), start, end))
        return periods

    if time_keyword in ("this-quarter", "last-quarter"):
        q   = (now.month - 1) // 3
        yr  = now.year
        if time_keyword == "last-quarter":
            q -= 1
            if q < 0:
                q, yr = 3, yr - 1
        for i in range(n - 1, -1, -1):
            qi = q - i
            yi = yr
            while qi < 0:
                qi += 4
                yi -= 1
            s, e = quarter_range(yi, qi)
            periods.append((f"Q{qi+1} {yi}", s, e))
        return periods

    # fallback — can't generate prior periods for this keyword
    return []


def run_trend(filters, time_keyword, n, cycles):
    """Run filters across N consecutive periods and render as a comparison table."""
    periods = _prior_periods(time_keyword, n, cycles)

    if not periods:
        sys.exit(f"--trend not supported for time window: {time_keyword}\n"
                 f"Use: this-month, this-week, this-quarter, YYYY-MM, or a named cycle")

    rows     = []
    has_amt  = False

    for label, start, end in periods:
        results, total = scan_records(start, end, filters, None)
        count = len(results)
        rows.append((label, count, total))
        if total > 0:
            has_amt = True

    # header
    col = 10
    filter_str = " ".join(filters) if filters else "all"
    print(f"\nTrend: {filter_str}\n")

    if has_amt:
        header = f"{'period':<14} {'count':>{col}} {'total':>{col}} {'avg':>{col}}"
    else:
        header = f"{'period':<14} {'count':>{col}}"

    print(header)
    print("-" * len(header))

    for label, count, total in rows:
        if has_amt:
            avg = fmt_avg(total / count) if count else "-"
            print(f"{label:<14} {count:>{col}} {fmt(total):>{col}} {avg:>{col}}")
        else:
            print(f"{label:<14} {count:>{col}}")

    print()


# --------------------------------------------------
# Followup due engine
# --------------------------------------------------

def run_due(arg):
    """Show records whose most recent entry per key is older than N days.
    arg can be:
      None / '__DEFAULT__'  → use [due] block
      a named string        → use [due.NAME] block
      a digit string        → use [due] block with days overridden
    Priority order derived from schema field options — no hardcoding."""

    queries = get_queries()

    # resolve which due config block to use and whether days is overridden
    days_override = None
    if arg is None or arg == "__DEFAULT__":
        due_cfg = queries.get("due")
        if not due_cfg:
            sys.exit("[due] section not found in queries.toml\n"
                     "Add it to enable --due. See README for details.")
    elif str(arg).isdigit():
        due_cfg = queries.get("due")
        if not due_cfg:
            sys.exit("[due] section not found in queries.toml\n"
                     "Add it to enable --due. See README for details.")
        days_override = int(arg)
    else:
        # named config: look for [due.NAME] in queries.toml
        named = queries.get("due", {})
        if isinstance(named, dict) and arg in named:
            due_cfg = named[arg]
        else:
            # also allow a top-level [due_NAME] block as fallback
            due_cfg = queries.get(f"due_{arg}")
        if not due_cfg:
            available = [k for k in queries.get("due", {}) if isinstance(queries["due"].get(k), dict)]
            hint = f"  Available: {', '.join(available)}" if available else ""
            sys.exit(f"Due config '{arg}' not found in queries.toml.{hint}\n"
                     f"Define it as [due.{arg}] with type, key, and days.")

    rec_type = due_cfg.get("type")
    key_field = due_cfg.get("key")
    if not rec_type or not key_field:
        sys.exit("[due] section in queries.toml is missing 'type' or 'key'.\n"
                 "Example:\n  [due]\n  type = \"followup\"\n  key  = \"client\"\n  days = 7")
    sort_field      = due_cfg.get("sort_by")
    exclude_results = due_cfg.get("exclude_results", [])
    days = days_override if days_override is not None else due_cfg.get("days", 7)

    # derive priority order from schema field options (list index = priority)
    priority = {}
    if sort_field:
        schema    = get_schema()
        type_meta = schema.get("type", {}).get(rec_type, {})
        options   = type_meta.get("fields", {}).get(sort_field, {}).get("options", [])
        if isinstance(options, list):
            priority = {v: i for i, v in enumerate(options)}
        # parent-dependent options — flatten all values in declaration order
        elif isinstance(options, dict):
            idx = 0
            for vals in options.values():
                for v in vals:
                    if v not in priority:
                        priority[v] = idx
                        idx += 1

    cutoff  = today() - dt.timedelta(days=days)
    results, _ = scan_records(dt.date.min, dt.date.max, [f"type={rec_type}"], None)

    # most recent record per key
    latest = {}
    for line in results:
        d, kv, note = parse_line(line)
        key_val = kv.get(key_field)
        if not key_val:
            continue
        if key_val not in latest or d > latest[key_val]["date"]:
            latest[key_val] = {"date": d, "kv": kv, "note": note}

    # drop entries whose latest result is in exclude_results
    if exclude_results:
        latest = {
            k: r for k, r in latest.items()
            if r["kv"].get("result") not in exclude_results
        }

    overdue = [r for r in latest.values() if r["date"] <= cutoff]

    if not overdue:
        print(f"\nNo records overdue (last entry within {days} days).\n")
        return

    # sort by priority (schema order) then oldest first
    overdue.sort(key=lambda r: (
        priority.get(r["kv"].get(sort_field, ""), 999) if sort_field else 0,
        r["date"]
    ))

    days_col  = 7
    sort_col  = 16
    name_col  = 24

    # build header dynamically — show sort_by column only if configured
    if sort_field:
        header = (f"{'last':>{days_col}}  {sort_field:<{sort_col}}"
                  f"{key_field:<{name_col}}  note")
    else:
        header = f"{'last':>{days_col}}  {key_field:<{name_col}}  note"

    print(f"\nDue  (>{days} days)  type={rec_type}\n")
    print(header)
    print("-" * 80)

    for rec in overdue:
        kv    = rec["kv"]
        gap   = (today() - rec["date"]).days
        name  = kv.get("name", kv.get(key_field, "-"))
        note  = rec["note"] or ""
        if sort_field:
            sv = kv.get(sort_field, "-")
            print(f"{gap:>{days_col}}d  {sv:<{sort_col}}{name:<{name_col}}  {note}")
        else:
            print(f"{gap:>{days_col}}d  {name:<{name_col}}  {note}")

    print(f"\n{len(overdue)} record(s) due\n")


def run_thresholds(time_arg):
    import ptos_service as svc
    time = None if time_arg == "__ALL__" else time_arg
    results = svc.get_all_threshold_status(time=time)
    if not results:
        print("\nNo thresholds configured.\n")
        print("Add thresholds to queries.toml:\n")
        print('  ["threshold.food_spend"]')
        print('  metric    = "food_this_month"')
        print('  agg       = "sum"')
        print('  sum_field = "amount"')
        print('  value     = 5000')
        print('  direction = "max"')
        print('  time      = "this-month"\n')
        return

    name_col = 20
    raw_col = 12
    target_col = 12
    pct_col = 8
    status_col = 10
    unit_col = 8

    print(f"\nThresholds\n")
    print(f"{'name':<{name_col}} {'raw':>{raw_col}} {'target':>{target_col}} "
          f"{'pct':>{pct_col}} {'status':>{status_col}} {'unit':<{unit_col}}")
    print("-" * 80)

    for r in results:
        raw_val = r["raw"]
        target_val = r["target"]
        unit = r["unit"] or ""
        direction = r["direction"]
        status = r["status"]
        pct = r["pct"]

        if direction == "max":
            sym = {"ok": " ", "warning": "!", "over": "X"}.get(status, "?")
        else:
            sym = {"ok": " ", "warning": "!", "met": "V"}.get(status, "?")

        raw_s = ptos.fmt(int(raw_val)) if isinstance(raw_val, (int, float)) and raw_val == int(raw_val) else ptos.fmt_avg(raw_val) if isinstance(raw_val, float) else str(raw_val)
        target_s = ptos.fmt(int(target_val)) if isinstance(target_val, (int, float)) and target_val == int(target_val) else ptos.fmt_avg(target_val) if isinstance(target_val, float) else str(target_val)

        print(f"{r['name']:<{name_col}} {raw_s:>{raw_col}} {target_s:>{target_col}} "
              f"{pct:>{pct_col}.0f}% {sym:>{status_col}} {unit:<{unit_col}}")

    print(f"\n{len(results)} threshold(s)\n")


# --------------------------------------------------
# Table renderer
# --------------------------------------------------

def _render_single_table(lines, label=None):
    """Render one group of same-type records as a table.
    - Columns auto-detected from fields in this group only
    - Adaptive width: shrinks note first, then widest columns
    - Minimum 6 chars per column
    """
    import shutil
    MIN_COL = 6
    COL_GAP = 2

    def trunc(s, w):
        return s[:w] + "…" if len(s) > w else s

    # collect fields in encounter order — include derived fields
    all_fields = ["date"]
    seen = set()
    dfields = derived_fields()
    # determine record type from first line
    first_rtype = ""
    if lines:
        try: _, fkv, _ = parse_line(lines[0]); first_rtype = fkv.get("type","")
        except: pass

    for line in lines:
        _, kv, _ = parse_line(line)
        for k in kv:
            if k not in seen and k != "type":
                all_fields.append(k)
                seen.add(k)

    # add derived field names relevant to this type
    for fname, defn in dfields.items():
        out_key = fname.split(".", 1)[1] if "." in fname else fname
        if defn["rtype"] is None or defn["rtype"] == first_rtype:
            if out_key not in seen:
                all_fields.append(out_key)
                seen.add(out_key)

    has_note = any(parse_line(l)[2] for l in lines)
    if has_note:
        all_fields.append("note")

    # build raw rows (no truncation yet)
    rows = []
    for line in lines:
        d, kv, note = parse_line(line)
        row = {"date": str(d)}
        for k, v in kv.items():
            if k == "type":
                continue
            row[k] = ",".join(v) if isinstance(v, list) else str(v)
        # add derived values
        computed = compute_derived(kv, record_date=d)
        for fname, val in computed.items():
            if val is not None:
                row[fname] = str(val) if not isinstance(val, str) else val
        if has_note:
            row["note"] = note or ""
        rows.append(row)

    # natural column widths — header uses display name (spaces), values also displayed
    natural = {f: len(_disp(f)) for f in all_fields}
    for row in rows:
        for f in all_fields:
            natural[f] = max(natural[f], len(row.get(f, "")))

    term_width = shutil.get_terminal_size(fallback=(120, 24)).columns
    total_gap  = COL_GAP * (len(all_fields) - 1)
    widths = dict(natural)

    def table_width(w):
        return sum(w[f] for f in all_fields) + total_gap

    # step 1: shrink note first
    if has_note and table_width(widths) > term_width:
        excess = table_width(widths) - term_width
        widths["note"] = max(MIN_COL, widths["note"] - excess)

    # step 2: shrink widest columns one at a time
    if table_width(widths) > term_width:
        shrinkable = [f for f in all_fields if widths[f] > MIN_COL]
        while table_width(widths) > term_width and shrinkable:
            widest = max(shrinkable, key=lambda f: widths[f])
            widths[widest] -= 1
            if widths[widest] <= MIN_COL:
                shrinkable.remove(widest)

    gap = " " * COL_GAP

    # print label (type name) as section header
    if label:
        print(f"\n[ {label} ]")
    else:
        print()

    header = gap.join(_disp(f).ljust(widths[f]) for f in all_fields)
    print(header)
    print("-" * len(header))

    dt_fields = set(datetime_fields())
    for row in rows:
        def _fmt_cell(f, v):
            if f in dt_fields and v:
                try:
                    parsed = dt.datetime.fromisoformat(str(v))
                    return parsed.strftime("%d-%b %H:%M")
                except (ValueError, TypeError):
                    pass
            return _disp(v)
        cells = [trunc(_fmt_cell(f, row.get(f, "")), widths[f]).ljust(widths[f]) for f in all_fields]
        print(gap.join(cells))


def render_table(results):
    """Render results as a table, grouped by type when multiple types present.
    Each type gets its own sub-table with only its relevant columns.
    Single type results render as one clean table with no label.
    """
    # group results by type, preserving order
    groups = {}
    order  = []
    for line in results:
        _, kv, _ = parse_line(line)
        t = kv.get("type", "unknown")
        if t not in groups:
            groups[t] = []
            order.append(t)
        groups[t].append(line)

    multi = len(order) > 1

    for t in order:
        _render_single_table(groups[t], label=t if multi else None)


# --------------------------------------------------
# CSV export
# --------------------------------------------------

def export_csv(results, filename, filters, time_label):
    """Export results to exports/FILENAME.csv.
    Auto-name uses active type filter + time label if no filename given.
    """
    import csv

    os.makedirs(EXPORTS_DIR, exist_ok=True)

    if filename == "__AUTO__":
        # build name from filters + time
        type_part = next((f.split("=")[1] for f in filters if f.startswith("type=")), "records")
        date_part = time_label.replace(" ", "_").replace("/", "-")
        filename  = f"{type_part}_{date_part}"

    # sanitise — no spaces or path separators
    filename = filename.replace(" ", "_")
    if any(c in filename for c in ("/", "\\")):
        sys.exit("--export: filename must not contain path separators")

    path = os.path.join(EXPORTS_DIR, f"{filename}.csv")

    # collect all columns in encounter order
    cols = ["date"]
    seen = set(["date"])
    for line in results:
        _, kv, note = parse_line(line)
        for k in kv:
            if k not in seen:
                cols.append(k)
                seen.add(k)
    has_note = any(parse_line(l)[2] for l in results)
    if has_note:
        cols.append("note")

    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=cols)
        writer.writeheader()
        for line in results:
            d, kv, note = parse_line(line)
            row = {"date": str(d)}
            for k, v in kv.items():
                row[k] = ",".join(v) if isinstance(v, list) else str(v)
            if has_note:
                row["note"] = note or ""
            writer.writerow(row)

    print(f"\nExported {len(results)} record(s) to: {path}\n")


# --------------------------------------------------
# Todo CLI handlers
# --------------------------------------------------

def _handle_todo_add(args):
    """Handle --todo-add command."""
    import ptos_todo
    if args.todo_add:
        text = " ".join(args.todo_add)
    else:
        # interactive mode
        print("Enter todo (todo.txt format):")
        print("  Example: (A) Call supplier +HearSpeechPro @phone due:tomorrow")
        text = input("  > ").strip()
        if not text:
            print("Cancelled.")
            return

    text = ptos_todo.preprocess_todo_text(text)
    try:
        t = ptos_todo.add_todo(ptos.TODO_PATH, text)
        print(f"Added: {ptos_todo.format_line(t)}")
    except Exception as e:
        print(f"Error: {e}")


def _handle_todo_list(args):
    """Handle --todo-list command with optional filters, table, count."""
    import ptos_todo
    todos, errors = ptos_todo.load_todos(ptos.TODO_PATH)
    done, _ = ptos_todo.load_todos(ptos.DONE_PATH)

    if getattr(args, "all", False):
        open_t = [t for t in todos if not t.done]
        display = open_t + [t for t in done]
    else:
        open_t = [t for t in todos if not t.done]
        display = list(open_t)

    if getattr(args, "project", None):
        proj = [("+" + p if not p.startswith("+") else p) for p in args.project]
        display = ptos_todo.filter_todos(display, project=proj,
                                          include_done=getattr(args, "all", False))
    if getattr(args, "context", None):
        ctx = [("@" + c if not c.startswith("@") else c) for c in args.context]
        display = ptos_todo.filter_todos(display, context=ctx,
                                          include_done=getattr(args, "all", False))
    if getattr(args, "priority", None):
        pri = [p.upper() for p in args.priority]
        display = ptos_todo.filter_todos(display, priority=pri,
                                          include_done=getattr(args, "all", False))

    due_range = getattr(args, "due_range", None)
    if due_range:
        today = dt.date.today()
        tomorrow = today + dt.timedelta(days=1)
        upcoming_end = today + dt.timedelta(days=7)
        if due_range == "overdue":
            display = [t for t in display if t.due and t.due < today and not t.done]
        elif due_range == "today":
            display = [t for t in display if t.due == today and not t.done]
        elif due_range == "tomorrow":
            display = [t for t in display if t.due == tomorrow and not t.done]
        elif due_range == "upcoming":
            display = [t for t in display if t.due and today < t.due <= upcoming_end and not t.done]
        elif due_range == "someday":
            display = [t for t in display if (t.due is None or t.due > upcoming_end) and not t.done]
        elif due_range == "none":
            display = [t for t in display if t.due is None and not t.done]

    search = getattr(args, "todo_search", None)
    if search:
        display = [t for t in display if ptos_todo._glob_match(search, t.description)]

    if getattr(args, "count", False) and not getattr(args, "table", False):
        open_count = len([t for t in display if not t.done])
        done_count = len([t for t in display if t.done])
        parts = []
        if open_count:
            parts.append(f"{open_count} open")
        if done_count:
            parts.append(f"{done_count} done")
        print(", ".join(parts) if parts else "No todos.")
        return

    if not display:
        print("No todos.")
        return

    if getattr(args, "table", False):
        _print_todo_table(display)
    else:
        for t in display:
            pri = f"({t.priority}) " if t.priority else ""
            due = f" due:{t.due.isoformat()}" if t.due else ""
            proj = " ".join(t.projects)
            ctx = " ".join(t.contexts)
            meta = " ".join(filter(None, [proj, ctx]))
            line = f"  {t.line_no:>3}. {pri}{t.description}"
            if meta:
                line += f" {meta}"
            if due:
                line += due
            print(line)

    open_count = len([t for t in display if not t.done])
    done_count = len([t for t in display if t.done])
    parts = []
    if open_count:
        parts.append(f"{open_count} open")
    if done_count:
        parts.append(f"{done_count} done")
    print(f"\n  {', '.join(parts)}")


def _handle_todo_done(n):
    """Handle --todo-done command."""
    import ptos_todo
    try:
        line_no = int(n)
    except ValueError:
        print(f"Invalid line number: {n}")
        return

    todos, _ = ptos_todo.load_todos(ptos.TODO_PATH)
    target = [t for t in todos if t.line_no == line_no]
    if not target:
        print(f"Line {line_no} not found in todo.txt")
        return

    if target[0].id:
        refs = ptos.backlink_refs(f"todo:{target[0].id}")
        if refs:
            n = len(refs)
            print(f"Warning: {n} entr{'y' if n == 1 else 'ies'} link to "
                  f"todo:{target[0].id} — they will become dangling.")

    try:
        ptos_todo.complete_todo(target[0])
        print(f"Completed: {ptos_todo.format_line(target[0])}")
    except Exception as e:
        print(f"Error: {e}")


def _parse_todo_updates(kv_strs):
    """Parse key=value strings into an updates dict.

    Handles +Project, -Project, @Context, -@Context syntax.
    Returns (updates_dict, projects_to_add, projects_to_remove, contexts_to_add, contexts_to_remove).
    """
    updates = {}
    projects_to_add = []
    projects_to_remove = []
    contexts_to_add = []
    contexts_to_remove = []
    for kv in kv_strs:
        if kv.startswith("-+") and "=" not in kv:
            projects_to_remove.append(kv[1:])
        elif kv.startswith("-@") and "=" not in kv:
            contexts_to_remove.append(kv[1:])
        elif kv.startswith("+") and "=" not in kv:
            projects_to_add.append(kv)
        elif kv.startswith("@") and "=" not in kv:
            contexts_to_add.append(kv)
        elif "=" in kv:
            key, val = kv.split("=", 1)
            updates[key.strip()] = val.strip()
        else:
            updates[kv] = ""
    return updates, projects_to_add, projects_to_remove, contexts_to_add, contexts_to_remove


def _handle_todo_edit(n, kv_strs):
    """Handle --todo-edit command with multiple key=value pairs."""
    import ptos_todo
    try:
        line_no = int(n)
    except ValueError:
        print(f"Invalid line number: {n}")
        return

    if not kv_strs:
        print("No edits specified. Use: --todo-edit N key=value ...")
        return

    updates, projects_add, projects_rm, contexts_add, contexts_rm = _parse_todo_updates(kv_strs)

    if projects_add or projects_rm or contexts_add or contexts_rm:
        todos, _ = ptos_todo.load_todos(ptos.TODO_PATH)
        target = [t for t in todos if t.line_no == line_no]
        if not target:
            print(f"Line {line_no} not found in todo.txt")
            return
        t = target[0]
        if projects_add:
            for p in projects_add:
                if p not in t.projects:
                    t.projects.append(p)
        if projects_rm:
            for p in projects_rm:
                if p in t.projects:
                    t.projects.remove(p)
        if contexts_add:
            for c in contexts_add:
                if c not in t.contexts:
                    t.contexts.append(c)
        if contexts_rm:
            for c in contexts_rm:
                if c in t.contexts:
                    t.contexts.remove(c)
        updates["projects"] = t.projects
        updates["contexts"] = t.contexts

    try:
        t = ptos_todo.edit_todo(ptos.TODO_PATH, line_no, updates)
        print(f"Updated: {ptos_todo.format_line(t)}")
    except Exception as e:
        print(f"Error: {e}")


def _parse_line_nos(s):
    """Parse a line number string like '1,3,5-7' into a list of ints."""
    result = []
    for part in s.split(","):
        part = part.strip()
        if "-" in part and not part.startswith("-"):
            a, b = part.split("-", 1)
            try:
                result.extend(range(int(a), int(b) + 1))
            except ValueError:
                print(f"Invalid range: {part}")
                return []
        else:
            try:
                result.append(int(part))
            except ValueError:
                print(f"Invalid line number: {part}")
                return []
    return result


def _handle_todo_bulk_edit(lines_str, kv_strs):
    """Handle --todo-bulk-edit command with multiple line numbers and key=value pairs."""
    import ptos_todo
    line_nos = _parse_line_nos(lines_str)
    if not line_nos:
        return

    if not kv_strs:
        print("No edits specified. Use: --todo-bulk-edit 1,3,5 priority=B due:tomorrow")
        return

    updates, projects_add, projects_rm, contexts_add, contexts_rm = _parse_todo_updates(kv_strs)

    if projects_add or projects_rm or contexts_add or contexts_rm:
        todos, _ = ptos_todo.load_todos(ptos.TODO_PATH)
        for ln in line_nos:
            target = [t for t in todos if t.line_no == ln]
            if not target:
                print(f"Line {ln} not found in todo.txt — skipped")
                continue
            t = target[0]
            if projects_add:
                for p in projects_add:
                    if p not in t.projects:
                        t.projects.append(p)
            if projects_rm:
                for p in projects_rm:
                    if p in t.projects:
                        t.projects.remove(p)
            if contexts_add:
                for c in contexts_add:
                    if c not in t.contexts:
                        t.contexts.append(c)
            if contexts_rm:
                for c in contexts_rm:
                    if c in t.contexts:
                        t.contexts.remove(c)
            updates["projects"] = t.projects
            updates["contexts"] = t.contexts

    try:
        results = ptos_todo.batch_edit_todos(ptos.TODO_PATH, line_nos, updates)
        print(f"Updated {len(results)} todo(s)")
    except Exception as e:
        print(f"Error: {e}")


def _handle_todo_delete(n):
    """Handle --todo-delete command."""
    import ptos_todo
    try:
        line_no = int(n)
    except ValueError:
        print(f"Invalid line number: {n}")
        return

    todos, _ = ptos_todo.load_todos(ptos.TODO_PATH)
    target = [t for t in todos if t.line_no == line_no]
    if not target:
        print(f"Line {line_no} not found in todo.txt")
        return
    if target[0].id:
        refs = ptos.backlink_refs(f"todo:{target[0].id}")
        if refs:
            n = len(refs)
            print(f"Warning: {n} entr{'y' if n == 1 else 'ies'} link to "
                  f"todo:{target[0].id} — they will become dangling.")

    try:
        ptos_todo.delete_todo(ptos.TODO_PATH, line_no)
        print(f"Deleted line {line_no}")
    except Exception as e:
        print(f"Error: {e}")


def _handle_todo_undo(n):
    """Handle --todo-undo command."""
    import ptos_todo
    try:
        line_no = int(n)
    except ValueError:
        print(f"Invalid line number: {n}")
        return

    try:
        ptos_todo.undo_todo(line_no)
        print(f"Undone: todo at line {line_no} moved back to todo.txt")
    except Exception as e:
        print(f"Error: {e}")


def _handle_todo_done_list(args):
    """Handle --todo-done-list command."""
    import ptos_todo
    done, _ = ptos_todo.load_todos(ptos.DONE_PATH)

    if not done:
        print("No completed todos.")
        return

    display = list(done)

    if getattr(args, "project", None):
        proj = [("+" + p if not p.startswith("+") else p) for p in args.project]
        display = ptos_todo.filter_todos(display, project=proj, include_done=True)
    if getattr(args, "context", None):
        ctx = [("@" + c if not c.startswith("@") else c) for c in args.context]
        display = ptos_todo.filter_todos(display, context=ctx, include_done=True)
    if getattr(args, "priority", None):
        pri = [p.upper() for p in args.priority]
        display = ptos_todo.filter_todos(display, priority=pri, include_done=True)

    search = getattr(args, "todo_search", None)
    if search:
        display = [t for t in display if ptos_todo._glob_match(search, t.description)]

    if getattr(args, "count", False) and not getattr(args, "table", False):
        print(f"{len(display)} done")
        return

    if not display:
        print("No completed todos.")
        return

    if getattr(args, "table", False):
        _print_todo_table(display)
    else:
        for t in display:
            pri = f"({t.priority}) " if t.priority else ""
            completed = f" x:{t.completed_date.isoformat()}" if t.completed_date else ""
            proj = " ".join(t.projects)
            ctx = " ".join(t.contexts)
            meta = " ".join(filter(None, [proj, ctx]))
            line = f"  {t.line_no:>3}. {pri}{t.description}"
            if meta:
                line += f" {meta}"
            if completed:
                line += completed
            print(line)

    print(f"\n  {len(display)} done")


def _handle_todo_done_delete(n):
    """Handle --todo-done-delete command."""
    import ptos_todo
    try:
        line_no = int(n)
    except ValueError:
        print(f"Invalid line number: {n}")
        return

    done, _ = ptos_todo.load_todos(ptos.DONE_PATH)
    target = [t for t in done if t.line_no == line_no]
    if not target:
        print(f"Line {line_no} not found in done.txt")
        return
    if target[0].id:
        refs = ptos.backlink_refs(f"todo:{target[0].id}")
        if refs:
            n = len(refs)
            print(f"Warning: {n} entr{'y' if n == 1 else 'ies'} link to "
                  f"todo:{target[0].id} — they will become dangling.")

    try:
        ptos_todo.delete_todo(ptos.DONE_PATH, line_no)
        print(f"Deleted line {line_no} from done.txt")
    except Exception as e:
        print(f"Error: {e}")


def _handle_todo_done_edit(n, kv_strs):
    """Handle --todo-done-edit command with multiple key=value pairs."""
    import ptos_todo
    try:
        line_no = int(n)
    except ValueError:
        print(f"Invalid line number: {n}")
        return

    if not kv_strs:
        print("No edits specified. Use: --todo-done-edit N key=value ...")
        return

    updates, projects_add, projects_rm, contexts_add, contexts_rm = _parse_todo_updates(kv_strs)

    if projects_add or projects_rm or contexts_add or contexts_rm:
        done, _ = ptos_todo.load_todos(ptos.DONE_PATH)
        target = [t for t in done if t.line_no == line_no]
        if not target:
            print(f"Line {line_no} not found in done.txt")
            return
        t = target[0]
        if projects_add:
            for p in projects_add:
                if p not in t.projects:
                    t.projects.append(p)
        if projects_rm:
            for p in projects_rm:
                if p in t.projects:
                    t.projects.remove(p)
        if contexts_add:
            for c in contexts_add:
                if c not in t.contexts:
                    t.contexts.append(c)
        if contexts_rm:
            for c in contexts_rm:
                if c in t.contexts:
                    t.contexts.remove(c)
        updates["projects"] = t.projects
        updates["contexts"] = t.contexts

    try:
        t = ptos_todo.edit_todo(ptos.DONE_PATH, line_no, updates)
        print(f"Updated: {ptos_todo.format_line(t)}")
    except Exception as e:
        print(f"Error: {e}")


def _handle_todo_projects():
    """Handle --todo-projects command."""
    import ptos_todo
    todos, _ = ptos_todo.load_todos(ptos.TODO_PATH)
    done, _ = ptos_todo.load_todos(ptos.DONE_PATH)
    all_todos = todos + done

    projects = {}
    for t in all_todos:
        for p in t.projects:
            projects[p] = projects.get(p, 0) + 1

    if not projects:
        print("No projects found.")
        return

    max_name = max(len(p) for p in projects)
    for name in sorted(projects):
        count = projects[name]
        label = "task" if count == 1 else "tasks"
        print(f"  {name:<{max_name}}   {count} {label}")


def _handle_todo_contexts():
    """Handle --todo-contexts command."""
    import ptos_todo
    todos, _ = ptos_todo.load_todos(ptos.TODO_PATH)
    done, _ = ptos_todo.load_todos(ptos.DONE_PATH)
    all_todos = todos + done

    contexts = {}
    for t in all_todos:
        for c in t.contexts:
            contexts[c] = contexts.get(c, 0) + 1

    if not contexts:
        print("No contexts found.")
        return

    max_name = max(len(c) for c in contexts)
    for name in sorted(contexts):
        count = contexts[name]
        label = "task" if count == 1 else "tasks"
        print(f"  {name:<{max_name}}   {count} {label}")


def _handle_todo_due(days):
    """Handle --todo-due command."""
    import ptos_todo
    todos, _ = ptos_todo.load_todos(ptos.TODO_PATH)

    due = ptos_todo.get_due_todos(todos, lookahead_days=days)
    if not due:
        print("No due/overdue todos.")
        return

    pri_order = {"A": 0, "B": 1, "C": 2, "D": 3}
    due.sort(key=lambda t: (pri_order.get(t.priority or "", 9), t.due or dt.date.max))

    today = dt.date.today()
    for t in due:
        pri = f"({t.priority}) " if t.priority else ""
        proj = " ".join(t.projects)
        ctx = " ".join(t.contexts)
        meta = " ".join(filter(None, [proj, ctx]))
        status = "OVERDUE" if t.due < today else "today" if t.due == today else t.due.isoformat()
        line = f"  {t.line_no:>3}. {pri}{t.description}"
        if meta:
            line += f" {meta}"
        line += f"  [{status}]"
        print(line)

    print(f"\n  {len(due)} due")


def _handle_todo_archive():
    """Handle --todo-archive command."""
    import ptos_todo
    count = ptos_todo.archive_done_todos(ptos.DONE_PATH)
    if count:
        print(f"Archived {count} old done item(s) to done.{dt.date.today().year}.txt")
    else:
        print("Nothing to archive.")


def _print_todo_table(todos):
    """Print todos in a formatted table."""
    if not todos:
        return

    def col(text, width):
        return f"{text:<{width}}"

    rows = []
    for t in todos:
        pri = f"({t.priority})" if t.priority else "  -  "
        desc = t.description
        proj = " ".join(t.projects)
        ctx = " ".join(t.contexts)
        due = t.due.isoformat() if t.due else ""
        rows.append((str(t.line_no), pri, desc, proj, ctx, due))

    widths = [0, 0, 0, 0, 0, 0]
    for row in rows:
        for i, val in enumerate(row):
            widths[i] = max(widths[i], len(val))
    widths = [max(w, 4) for w in widths]
    widths[2] = max(widths[2], 20)

    header = f"  {'#':<{widths[0]}}  {'Pri':<{widths[1]}}  {'Description':<{widths[2]}}  {'Project':<{widths[3]}}  {'Context':<{widths[4]}}  {'Due':<{widths[5]}}"
    print(header)
    print("  " + "  ".join("-" * w for w in widths))

    for row in rows:
        line = f"  {col(row[0], widths[0])}  {col(row[1], widths[1])}  {col(row[2], widths[2])}  {col(row[3], widths[3])}  {col(row[4], widths[4])}  {col(row[5], widths[5])}"
        print(line)


def _interactive_suggest(rtype, record):
    """Return {field: most_common_value} for interactive --add prompts,
    sourced from history suggestions (cached full-file scan per type).
    Enter-picking a suggested default is a no-op — the value is returned as-is."""
    try:
        import ptos_service
        sugg = ptos_service.get_history_suggestions(rtype)
    except Exception:
        return {}
    defaults = dict(sugg.get("field_defaults") or {})
    for fname, values in (sugg.get("field_values") or {}).items():
        if fname not in defaults and values:
            defaults[fname] = values[0]
    return defaults


def _metric_to_internal(m):
    """Convert a stored metrics.toml entry ({avg: base, ratio: [...]}) into
    the internal {kind, base, base2, ...} form save_queries_full expects."""
    m = dict(m)
    internal = {}
    for k in ("unit_field", "unit_weights", "time"):
        if k in m:
            internal[k] = m.pop(k)
    if "derived" in m:
        internal["derived"] = m.pop("derived")
    elif "ratio" in m and isinstance(m.get("ratio"), list) and len(m["ratio"]) >= 2:
        internal["kind"] = "ratio"
        internal["base"], internal["base2"] = m.pop("ratio")[:2]
    else:
        for kind in ("avg", "sum", "max", "min"):
            if kind in m:
                internal["kind"] = kind
                internal["base"] = m.pop(kind)
                break
        else:
            internal["kind"] = "avg"
    if m:
        internal["_raw"] = m
    return internal


def _handle_add_dashboard(args):
    """Add a dashboard referencing metrics to queries.toml, preserving
    all other queries state (queries, metrics, aliases, due, boards,
    habits, calendars)."""
    import ptos_service
    queries = get_queries()
    if not isinstance(queries, dict):
        queries = {}
    reserved = ("metrics", "dashboards", "due")

    def _norm(q):
        q = dict(q)
        if isinstance(q.get("where"), list):
            q["where"] = ptos._filters_to_expr(q["where"])
        return q

    # Flat config keys are stored as "board.X" / "habit.X" / "calendar.X";
    # starter files may use [board.X] tables which tomllib nests under a
    # bare "board" key. Extract both forms so round-trips never drop configs.
    def _nested(container, is_cfg):
        cfg = {}
        if isinstance(queries.get(container), dict):
            for k, v in queries[container].items():
                if isinstance(v, dict) and is_cfg(v):
                    cfg[k] = v
        return cfg

    boards    = {k[6:]: v for k, v in queries.items() if k.startswith("board.") and isinstance(v, dict)}
    habits    = {k[6:]: v for k, v in queries.items() if k.startswith("habit.") and isinstance(v, dict)}
    calendars = {k[9:]: v for k, v in queries.items() if k.startswith("calendar.") and isinstance(v, dict)}
    boards.update(_nested("board", lambda v: "columns" in v))
    habits.update(_nested("habit", lambda v: "filters" in v))
    calendars.update(_nested("calendar", lambda v: "filters" in v))
    nested_containers = {"board", "habit", "calendar"}

    raw_q = {k: _norm(v) for k, v in queries.items()
             if k not in reserved and k not in nested_containers
             and isinstance(v, dict) and "alias" not in v
             and not k.startswith(("board.", "habit.", "calendar.", "due.", "threshold."))}
    raw_a = {k: v for k, v in queries.items()
             if k not in reserved and k not in nested_containers
             and isinstance(v, dict) and "alias" in v}
    raw_due = {}
    for k, v in queries.items():
        if isinstance(v, dict):
            if k.startswith("due."):
                raw_due[k[4:]] = v
            elif k == "due":
                raw_due["default"] = v
    thresholds = {k[10:]: v for k, v in queries.items() if k.startswith("threshold.") and isinstance(v, dict)}

    dashboards = dict(queries.get("dashboards", {}))
    if args.add_dashboard in dashboards:
        sys.exit(f"Dashboard '{args.add_dashboard}' already exists.")
    known_metrics = set((queries.get("metrics") or {}).keys())
    for m in (args.metrics or []):
        if m not in known_metrics:
            print(f"Warning: metric '{m}' not found in queries.toml — dashboard will be empty until defined.")
    highlight = {}
    for entry in (args.highlight or []):
        if ":" not in entry:
            sys.exit(f"Invalid highlight format '{entry}' — use METRIC:COLOR (e.g. food_spend:accent)")
        metric, color = entry.split(":", 1)
        if color not in ("accent", "warn", "success", "error"):
            sys.exit(f"Unknown highlight color '{color}' — use: accent, warn, success, error")
        highlight[metric] = color
    db_entry = {"metrics": list(args.metrics or [])}
    dashboards[args.add_dashboard] = db_entry

    try:
        ptos_service.save_queries_full(
            raw_q,
            {name: _metric_to_internal(m) for name, m in (queries.get("metrics") or {}).items()
             if isinstance(m, dict)},
            dashboards,
            raw_a,
            raw_due=raw_due,
            raw_boards=boards,
            raw_habits=habits,
            raw_calendars=calendars,
            raw_thresholds=thresholds,
        )
    except ptos_service.PTOSError as e:
        sys.exit(str(e))
    except Exception as e:
        sys.exit(f"Error saving dashboard: {e}")
    if highlight:
        cfg = ptos.get_config()
        cfg.setdefault("dashboard", {}).setdefault("highlights", {})[args.add_dashboard] = highlight
        ptos_service.save_config(cfg)
    metrics_str = ", ".join(args.metrics) if args.metrics else "none"
    print(f"Dashboard '{args.add_dashboard}' saved (metrics: {metrics_str}).")


def _handle_link(src_target, target):
    """Add a links=... token to the source entry pointing at target."""
    import ptos_todo
    src = resolve_link(src_target)
    if src is None:
        sys.exit(f"Source '{src_target}' not found — give it an id first "
                 f"(ptos --retro-id ...).")
    if resolve_link(target) is None:
        print(f"Warning: target '{target}' does not resolve — link saved anyway, "
              f"lint will flag it as dangling.")
    if src["kind"] == "todo":
        new_line = append_links_to_todo_line(src["line"], [target])
        rewritten = ptos_todo.rewrite_line_by_number(src["filepath"], src["lineno"], new_line)
        print(f"Linked {src_target} -> {target}  ({'updated' if rewritten else 'unchanged'})")
    elif src["kind"] == "record":
        new_line = append_links_to_line(src["line"], [target])
        rewrite_line_in_file(src["filepath"], src["line"], new_line, lineno=src["lineno"])
        print(f"Linked {src_target} -> {target}")
    else:
        sys.exit("Journal entries can't carry links= tokens — write [[...]] in the prose instead.")


def _handle_retro_id(args):
    """Assign an id to an existing hand-typed line so it can be a link target."""
    import ptos_todo
    target_type = (args.retro_id or "").strip().lower()
    if not target_type:
        sys.exit("--retro-id requires a TYPE (record type or 'todo')")
    if target_type == "todo":
        search = " ".join(args.search or []) if isinstance(args.search, list) else (args.search or "")
        if not search:
            sys.exit("--retro-id todo requires --search TEXT to find the todo")
        todos, _ = ptos_todo.load_todos(TODO_PATH)
        matches = [t for t in todos if not t.done and _glob_match(search, t.description)]
        if not matches:
            sys.exit(f"No open todo matching '{search}'.")
        if len(matches) > 1:
            sys.exit(f"{len(matches)} todos match '{search}' — be more specific.")
        t = matches[0]
        if t.id:
            sys.exit(f"Todo already has id:{t.id}")
        new_id = generate_unique_id()
        line, _ = append_todo_id(t.raw_line, new_id)
        ptos_todo.rewrite_line_by_number(TODO_PATH, t.line_no, line)
        print(f"Added id:{new_id} to line {t.line_no}")
        return
    if target_type == "note":
        search = " ".join(args.search or []) if isinstance(args.search, list) else (args.search or "")
        if not search:
            sys.exit("--retro-id note requires --search TEXT to find the note file")
        found = None
        for root, _, files in os.walk(NOTES_DIR):
            for fname in files:
                if fname == "template.md" or not fname.endswith(".md"):
                    continue
                fpath = os.path.join(root, fname)
                rel = os.path.relpath(fpath, NOTES_DIR).replace("\\", "/")
                if _glob_match(search, fname.replace(".md", "")) or _glob_match(search, rel):
                    if found:
                        sys.exit(f"Multiple notes match '{search}' — be more specific.")
                    found = (fpath, rel)
        if not found:
            sys.exit(f"No note matching '{search}'.")
        fpath, rel = found
        existing = ptos._note_id_of(fpath)
        if existing:
            sys.exit(f"Note already has id: note:{existing}")
        nid = ensure_note_id(rel)
        print(f"Added id:note:{nid} to {rel}")
        return
    filters = [item for group in (args.where or []) for item in group]
    if not filters:
        sys.exit(f"--retro-id {target_type} requires --where filters to locate the record")
    hits = find_records_with_location([f"type={target_type}"] + filters)
    if not hits:
        sys.exit(f"No record of type '{target_type}' matches those filters.")
    if len(hits) > 1:
        sys.exit(f"{len(hits)} records match — add more --where filters to pick one.")
    filepath, lineno, raw = hits[0]
    if re.search(r'\bid=(\S+)', raw):
        sys.exit(f"Record already has an id: {raw}")
    new_id = append_record_id(filepath, lineno, raw)
    print(f"Added id={new_id} to {os.path.basename(filepath)}:{lineno}")


# --------------------------------------------------
# Main
# --------------------------------------------------

def main():
    config = get_config()
    cycles = config.get("cycles", {})
    args   = build_parser(cycles).parse_args()

    # ---- early exits (no data needed) ----
    if args.init:
        init_ptos()
        return

    if args.set_home:
        set_home(args.set_home)
        return

    if args.bisync or args.sync:
        if args.sync and not args.confirm_delete:
            sys.exit(
                "--sync deletes anything on the remote that isn't present\n"
                "locally. If you're sure, re-run with --confirm-delete.\n"
                "If you just want to push local changes without risking\n"
                "remote deletions, use --bisync instead."
            )
        cmd = "bisync" if args.bisync else "sync"
        result = run_sync(cmd, resync=args.resync,
                          on_line=lambda line: print(line, end="", flush=True))
        if not result["ok"]:
            sys.exit(result["error"])
        return

    if args.set_name:
        set_user_name(args.set_name)
        return

    if args.set_date_format:
        set_date_format(args.set_date_format)
        return

    if args.set_currency:
        set_currency(args.set_currency)
        return

    if args.add_cycle:
        add_cycle(args.add_cycle[0], args.add_cycle[1])
        return

    if args.set_auth:
        set_auth(args.set_auth[0], args.set_auth[1])
        return

    if args.edit:
        edit_target(args.edit)
        return

    # ---- todo commands ----
    if args.todo_add is not None:
        _handle_todo_add(args)
        return
    if args.todo_list:
        _handle_todo_list(args)
        return
    if args.todo_done:
        _handle_todo_done(args.todo_done)
        return
    if args.todo_edit:
        _handle_todo_edit(args.todo_edit[0], args.todo_edit[1:])
        return
    if args.todo_bulk_edit:
        _handle_todo_bulk_edit(args.todo_bulk_edit[0], args.todo_bulk_edit[1:])
        return
    if args.todo_delete:
        _handle_todo_delete(args.todo_delete)
        return
    if args.todo_undo:
        _handle_todo_undo(args.todo_undo)
        return
    if args.todo_done_list:
        _handle_todo_done_list(args)
        return
    if args.todo_done_delete:
        _handle_todo_done_delete(args.todo_done_delete)
        return
    if args.todo_done_edit:
        _handle_todo_done_edit(args.todo_done_edit[0], args.todo_done_edit[1:])
        return
    if args.todo_projects:
        _handle_todo_projects()
        return
    if args.todo_contexts:
        _handle_todo_contexts()
        return
    if args.todo_due is not None:
        _handle_todo_due(args.todo_due)
        return
    if args.todo_archive:
        _handle_todo_archive()
        return

    if args.delete_preset:
        delete_preset(args.delete_preset)
        return

    if args.preset is not None:
        quick_add(args)
        return

    if args.journal is not None:
        edit_target("daily", date_str=resolve_date(args.journal))
        return

    if args.doctor:
        errors, warnings, messages, fixes = doctor_check(
            verbose=True,
            fix=args.doctor_fix
        )
        print_doctor_results(errors, warnings, messages, fixes, verbose=True, fix=args.doctor_fix)
        if errors:
            sys.exit(1)
        return

    if args.check_schema:
        schema = get_schema()
        issues = ptos.validate_schema_structure(schema)
        if issues:
            print("Schema issues found:\n")
            for i, err in enumerate(issues, 1):
                print(f"  {i}. {err}")
            print(f"\n{len(issues)} issue(s) found.")
        else:
            print("Schema looks valid!")
        return

    if args.add_type:
        add_type(args.add_type, args.required)
        return

    if args.add_field:
        if "." not in args.add_field:
            sys.exit("--add-field expects TYPE.FIELD (e.g. expense.fuel)")
        type_name, field_name = args.add_field.split(".", 1)
        add_type_field(type_name, field_name, args.field_type, args.field_options)
        return

    if args.remove_type:
        remove_type(args.remove_type)
        return

    if args.add_dashboard:
        _handle_add_dashboard(args)
        return

    if args.backup_full:
        backup_path = backup_data()
        print(f"Full backup created: {backup_path}")
        return

    if args.backup_config:
        backup_path = backup_config()
        print(f"Config backup created: {backup_path}")
        return

    if args.list_backups:
        backups = list_backups()
        if not backups:
            print("No backups found.")
            return
        print("\nAvailable backups:")
        for name, date, btype in backups:
            print(f"  {name}  ({btype}, {fmt_datetime(date)})")
        return

    if args.delete_backup:
        try:
            delete_backup(args.delete_backup)
        except FileNotFoundError as e:
            sys.exit(str(e))
        except ValueError as e:
            sys.exit(f"Invalid backup name: {e}")
        print(f"Deleted backup: {args.delete_backup}")
        return

    if args.restore_full is not None:
        zip_path = args.restore_full
        if not zip_path:
            zip_path = _interactive_restore("full")
        print(f"Restoring full backup from: {zip_path}")
        restore_data(zip_path)
        print("Restore complete.")
        sys.exit(0)

    if args.restore_config is not None:
        zip_path = args.restore_config
        if not zip_path:
            zip_path = _interactive_restore("config")
        print(f"Restoring config backup from: {zip_path}")
        restore_config(zip_path)
        print("Restore complete.")
        sys.exit(0)

    # ---- add mode ----
    schema = get_schema()

    if args.add is not None:
        if not args.add:
            interactive_add(schema, resolve_date(args.date), args.save_preset,
                            suggest_fn=_interactive_suggest)
            if args.link:
                sys.exit("--link requires --add with key=value fields, not the interactive prompt.")
        else:
            record = {}
            for item in args.add:
                if "=" not in item:
                    sys.exit(f"Invalid argument '{item}' — expected key=value format (e.g. type=expense)")
                k, v = item.split("=", 1)
                if k in record:
                    record[k] = record[k] if isinstance(record[k], list) else [record[k]]
                    record[k].append(v)
                else:
                    record[k] = v
            if args.link:
                if len(args.link) != 1:
                    sys.exit("With --add, --link takes exactly one TARGET (e.g. --link project:p91a)")
                target = args.link[0]
                if resolve_link(target) is None:
                    print(f"Warning: link target '{target}' does not resolve — "
                          "saved anyway; lint will flag it as dangling.")
                record["links"] = target
                if "id" not in record:
                    record["id"] = generate_unique_id()
            if "id" in record:
                existing_ids = {item["target"].split(":", 1)[1] for item in list_link_ids()}
                if record["id"] in existing_ids:
                    sys.exit(f"id '{record['id']}' is already in use — pick another.")
            problems = validate_record(schema, record)
            if problems:
                sys.exit(problems[0])
            append_record(build_record_line(resolve_date(args.date), record, args.note))
            print("Record added." + (f"  id={record.get('id', '')}  links={record.get('links', '')}"
                                     if args.link else ""))
            if args.save_preset:
                save_as_preset(args.save_preset, record)
        return

    # ---- link existing entries ----
    if args.link:
        if len(args.link) != 2:
            sys.exit("--link (standalone) takes SRC_TARGET and TARGET: "
                     "--link expense:k3f9a1 project:p91a")
        _handle_link(args.link[0], args.link[1])
        return

    # ---- retro-id ----
    if args.retro_id:
        _handle_retro_id(args)
        return

    # ---- lint mode ----
    if args.lint:
        results, _ = scan_records(dt.date.min, dt.date.max, [], None)
        error_files = lint_records(results, schema)
        if getattr(args, "fix", False) and error_files:
            editor = resolve_editor()
            print(f"Opening {len(error_files)} file(s) with errors...\n")
            for path in sorted(error_files):
                try:
                    subprocess.run(editor + [path])
                except FileNotFoundError:
                    sys.exit(f"Editor '{editor[0]}' not found.\nSet [editor] command in config/config.toml.")
        return

    # ---- flatten --where ----
    filters = [item for group in (args.where or []) for item in group]

    # ---- named query ----
    query_filters  = []
    metric_mode    = False
    dashboard_mode = False

    if args.query == "__LIST__":
        queries    = get_queries()
        metrics    = queries.get("metrics",    {})
        dashboards = queries.get("dashboards", {})
        print("\nQueries\n")
        for name in queries:
            if name not in ("metrics", "dashboards"):
                print(" ", name)
        if metrics:
            print("\nMetrics\n")
            for name in metrics: print(" ", name)
        if dashboards:
            print("\nDashboards\n")
            for name in dashboards: print(" ", name)
        print()
        return

    # ---- due mode ----
    if args.due is not None:
        run_due(args.due)
        return

    # ---- thresholds mode ----
    if args.thresholds is not None:
        run_thresholds(args.thresholds)
        return

    if args.query:
        queries = get_queries()
        query_filters, metric_mode, dashboard_mode = resolve_query_context(args, queries)

    # ---- build final filter list ----
    # CLI --where overrides saved query filters; type/tag append on top
    if filters:
        final_filters = filters
    else:
        final_filters = query_filters

    if args.type: final_filters = final_filters + [f"type={args.type}"]
    if args.tag:  final_filters = final_filters + [f"tag={t}" for t in args.tag]
    if args.linked_to:
        final_filters = final_filters + [f"links~{t}" for t in args.linked_to]

    # ---- time resolution ----
    if args.date_from or args.date_to:
        try:
            start = ptos.parse_from_to(str(args.date_from)) if args.date_from else dt.date.min
            end   = ptos.parse_from_to(str(args.date_to), as_end=True) if args.date_to else dt.date.max
        except ValueError:
            sys.exit("Invalid date format. Use YYYY-MM-DD, YYYY-MM, or YYYY.")
        time_label = "custom range"
    else:
        try:
            start, end = resolve_time(args.time, cycles)
        except ValueError:
            valid = ("today/td  yesterday/yd  this-week/tw  last-week/lw\n"
                     "  this-month/tm  last-month/lm  this-quarter/tq  last-quarter/lq\n"
                     "  this-year/ty  last-year/ly  all  YYYY  YYYY-MM  YYYY-MM-DD")
            cycle_names = "  " + "  ".join(cycles.keys()) if cycles else ""
            sys.exit(
                f"Invalid time keyword: '{args.time}'\n\n"
                f"Valid keywords:\n  {valid}"
                + (f"\nCustom cycles:\n{cycle_names}" if cycle_names else "")
            )
        time_label = _TIME_ALIASES.get(args.time, args.time)

    # ---- edit / delete mode ----
    if getattr(args, "set", None) or getattr(args, "set_note", None) or getattr(args, "delete", False):
        if not final_filters:
            sys.exit("--set/--delete requires at least one filter (--where, --type, or --tag).")
        run_set(
            final_filters,
            start     = start,
            end       = end,
            set_args  = getattr(args, "set",      None),
            new_note  = getattr(args, "set_note",  None),
            do_delete = getattr(args, "delete",    False),
            do_all    = getattr(args, "all",       False),
        )
        return

    # ---- trend mode ----
    if args.trend is not None:
        run_trend(final_filters, args.time, args.trend, cycles)
        return

    # ---- dashboard / metric (don't need full scan) ----
    if args.query and dashboard_mode:
        run_dashboard(args.query, queries, start, end, cycles)
        return

    if args.query and metric_mode:
        run_metric(args.query, queries, start, end, cycles)
        return

    # ---- save query if requested ----
    if args.save:
        save_query(args.save, args, final_filters)

    # ---- validate --sum-field ----
    sum_field = getattr(args, "sum_field", None)
    if sum_field and sum_field not in numeric_fields():
        sys.exit(f"--sum-field: '{sum_field}' is not a numeric field in schema.\n"
                 f"Numeric fields: {', '.join(numeric_fields())}")

    # ---- scan ----
    results, total = scan_records(start, end, final_filters, args.search, getattr(args, "from_file", None), sum_field=sum_field)

    if not results:
        print("\nNo records found.\n")
        if final_filters:
            all_results, _ = scan_records(dt.date.min, dt.date.max, [], None)
            known = {k for line in all_results for p in [ptos.safe_parse_line(line)] if p for k in p[1]}
            known.update({"type", "tag"})
            for f in final_filters:
                m = re.match(r"(\w+)(!~|!=|>=|<=|~|=|>|<)", f)
                if m and m.group(1) not in known:
                    print(f"  Note: '{m.group(1)}' not found in any record — check spelling.")
            print()
        return

    # ---- discovery ----
    if args.fields:
        show_fields(results)
        return

    if args.group == ["?"]:
        bad = non_dimension_fields()
        dims = sorted({k for line in results for k in parse_line(line)[1] if k not in bad})
        print("\nAvailable group fields:\n")
        for d in dims: print(d)
        print()
        return

    if args.pivot and args.pivot[0] == "?":
        available = {"month", "year"}
        for line in results:
            available.update(parse_line(line)[1].keys())
        print("\nAvailable pivot fields:\n")
        for d in sorted(available): print(d)
        print()
        return

    # ---- pivot ----
    if args.pivot:
        if len(args.pivot) < 2:
            sys.exit("Pivot requires two fields: ptos -v ROW COL")
        row, col     = args.pivot[:2]
        available    = {"month", "year"}
        for line in results:
            available.update(parse_line(line)[1].keys())
        missing = [f for f in (row, col) if f not in available]
        if missing:
            sys.exit(f"Unknown pivot field(s): {', '.join(missing)}  — try: ptos --fields")
        render_summary(results, start, end, time_label, final_filters, total, sum_field=sum_field)
        vf = sum_field or detect_value_field(results)
        label = f"Value: {vf}" if vf and not args.count else "Count mode"
        print(f"\nPivot  row={row}  col={col}  {label}")
        table, cols, rows = pivot_results(results, row, col, args.count, args.sort, sum_field=sum_field)
        render_pivot(table, cols, rows, row)
        return

    # ---- group ----
    if args.group:
        render_summary(results, start, end, time_label, final_filters, total, sum_field=sum_field)
        vf = sum_field or detect_value_field(results)
        label = f"Value: {vf}" if vf else "Count"
        print(f"\nGrouped by: {' '.join(args.group)}  ({label})\n")
        counts, sums, has_amount = group_results(results, args.group, sum_field=sum_field)
        render_group(counts, sums, has_amount, args.group)
        return

    # ---- default: list records ----
    # apply --select: keep only chosen fields
    # default always includes date + all kv fields; note excluded unless selected
    if getattr(args, "select", None):
        want_note = "note" in args.select
        selected  = set(args.select) | {"type"}  # type always included
        selected.discard("note")                  # note is not a kv field
        # warn about unknown fields
        all_keys = {k for line in results for k in parse_line(line)[1]}
        unknown  = [f for f in args.select
                    if f not in all_keys and f not in ("type", "note")]
        if unknown:
            print(f"Warning: unknown field(s) in --select: {', '.join(unknown)}")
        filtered = []
        for line in results:
            d, kv, note = parse_line(line)
            parts = [str(d)]
            for k, v in kv.items():
                if k in selected:
                    if isinstance(v, list):
                        for val in v:
                            parts.append(f"{k}={val}")
                    else:
                        parts.append(f"{k}={v}")
            rec = " ".join(parts)
            if want_note and note:
                rec += f" | {note}"
            filtered.append(rec)
        results = filtered

    # sort by field if --sort given and not in pivot mode
    if args.sort and not args.pivot:
        def sort_key(line):
            _, kv, _ = parse_line(line)
            val = kv.get(args.sort, "")
            if isinstance(val, list):
                val = val[0] if val else ""
            # sort numbers numerically, strings alphabetically
            try:
                return (0, int(val), "")
            except (ValueError, TypeError):
                return (1, 0, str(val).lower())
        results = sorted(results, key=sort_key)

    if getattr(args, "export", None):
        export_csv(results, args.export, final_filters, time_label)
        return

    if args.table:
        render_table(results)
    else:
        print()
        for line in results:
            print(line)
    render_summary(results, start, end, time_label, final_filters, total, sum_field=sum_field)


def _interactive_restore(backup_type):
    """Interactive restore - show list and let user choose."""
    backups = list_backups()
    filtered = [b for b in backups if b[2] == backup_type]
    if not filtered:
        sys.exit(f"No {backup_type} backups found.")
    
    print(f"\nAvailable {backup_type} backups:")
    for i, (name, date, _) in enumerate(filtered, 1):
        print(f"  {i}. {name} ({fmt_datetime(date)})")
    
    while True:
        choice = input("\nEnter number to restore (or 'q' to quit): ").strip()
        if choice.lower() == 'q':
            sys.exit("Restore cancelled.")
        try:
            idx = int(choice) - 1
            if 0 <= idx < len(filtered):
                return os.path.join(BACKUP_DIR, filtered[idx][0])
            print("Invalid number. Try again.")
        except ValueError:
            print("Invalid input. Enter a number or 'q'.")



if __name__ == "__main__":
    main()
