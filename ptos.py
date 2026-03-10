import argparse
import os
import sys
import datetime as dt
import tomllib
import re
import shutil
import subprocess

sys.stdout.reconfigure(encoding="utf-8")

# --------------------------------------------------
# Paths
# --------------------------------------------------

_home    = os.environ.get("PTOS_HOME")
BASE_DIR = _home if _home else os.path.dirname(os.path.abspath(__file__))

CONFIG_DIR   = os.path.join(BASE_DIR, "config")
RECORDS_DIR  = os.path.join(BASE_DIR, "records")
JOURNAL_DIR  = os.path.join(BASE_DIR, "journal")
TEMPLATE_DIR = os.path.join(BASE_DIR, "templates")

SCHEMA_PATH  = os.path.join(CONFIG_DIR, "schema.toml")
QUERIES_PATH = os.path.join(CONFIG_DIR, "queries.toml")
CONFIG_PATH  = os.path.join(CONFIG_DIR, "config.toml")
PRESETS_PATH = os.path.join(CONFIG_DIR, "presets.toml")

# --------------------------------------------------
# Config cache  (load once, reuse everywhere)
# --------------------------------------------------

_CACHE = {}

def _load(key, path):
    if key not in _CACHE:
        with open(path, "rb") as f:
            _CACHE[key] = tomllib.load(f)
    return _CACHE[key]

def get_config():  return _load("config",  CONFIG_PATH)  if os.path.exists(CONFIG_PATH)  else {}
def get_schema():
    if not os.path.exists(SCHEMA_PATH):
        sys.exit("schema.toml not found. Run: ptos --init")
    return _load("schema", SCHEMA_PATH)

def get_queries():
    if not os.path.exists(QUERIES_PATH):
        sys.exit("queries.toml not found. Run: ptos --init")
    return _load("queries", QUERIES_PATH)
def get_presets(): return _load("presets", PRESETS_PATH).get("presets", {}) if os.path.exists(PRESETS_PATH) else {}

# --------------------------------------------------
# Display helpers  (currency from config)
# --------------------------------------------------

def currency():
    return get_config().get("display", {}).get("currency", "")

def fmt(n):
    """Format a number with the configured currency symbol."""
    return f"{currency()}{n}"

def fmt_avg(n):
    return f"{currency()}{n:.0f}"

# --------------------------------------------------
# Schema helpers
# --------------------------------------------------

def numeric_fields():
    """Return list of field names declared as type=int in schema."""
    if "numeric_fields" not in _CACHE:
        _CACHE["numeric_fields"] = [
            f for f, meta in get_schema().get("fields", {}).items()
            if isinstance(meta, dict) and meta.get("type") == "int"
        ]
    return _CACHE["numeric_fields"]

def non_dimension_fields():
    """Return set of fields marked dimension=false in schema (for show_fields filtering)."""
    return {
        f for f, meta in get_schema().get("fields", {}).items()
        if isinstance(meta, dict) and not meta.get("dimension", True)
    }

def numeric_value(kv):
    """Return the first numeric field value found in kv, or None."""
    for f in numeric_fields():
        if f in kv:
            v = kv[f]
            if isinstance(v, list):
                v = v[0]
            if str(v).isdigit():
                return int(v)
    return None

def detect_value_field(results):
    """Return the name of the first numeric field found across results."""
    for line in results:
        _, kv, _ = parse_line(line)
        for f in numeric_fields():
            if f in kv:
                return f
    return None

# --------------------------------------------------
# Time engine
# --------------------------------------------------

def today():
    return dt.date.today()

def parse_date(s):
    return dt.date.fromisoformat(s)

def month_range(year, month):
    start = dt.date(year, month, 1)
    end   = dt.date(year + 1, 1, 1) - dt.timedelta(days=1) if month == 12 \
            else dt.date(year, month + 1, 1) - dt.timedelta(days=1)
    return start, end

def quarter_range(year, quarter):
    start_month = quarter * 3 + 1
    start = dt.date(year, start_month, 1)
    end   = dt.date(year + 1, 1, 1) - dt.timedelta(days=1) if start_month + 3 > 12 \
            else dt.date(year, start_month + 3, 1) - dt.timedelta(days=1)
    return start, end

def resolve_cycle(start_day, offset=0):
    now = today()
    if now.day >= start_day:
        start = dt.date(now.year, now.month, start_day)
    else:
        prev  = now.replace(day=1) - dt.timedelta(days=1)
        start = dt.date(prev.year, prev.month, start_day)
    for _ in range(offset):
        prev  = start.replace(day=1) - dt.timedelta(days=1)
        start = dt.date(prev.year, prev.month, start_day)
    next_month = (start.replace(day=28) + dt.timedelta(days=4)).replace(day=1)
    end = next_month + dt.timedelta(days=start_day - 1) - dt.timedelta(days=1)
    return start, end

def resolve_date(value):
    """
    Resolve a --date argument to an ISO date string.
    Accepts: YYYY-MM-DD, today, yesterday.
    """
    if value is None:
        return today().isoformat()
    if value == "today":
        return today().isoformat()
    if value == "yesterday":
        return (today() - dt.timedelta(days=1)).isoformat()
    try:
        parse_date(value)
        return value
    except ValueError:
        sys.exit(f"Invalid date '{value}'. Use YYYY-MM-DD, today, or yesterday.")

_TIME_ALIASES = {
    "td":  "today",
    "yd":  "yesterday",
    "tw":  "this-week",
    "lw":  "last-week",
    "tm":  "this-month",
    "lm":  "last-month",
    "tq":  "this-quarter",
    "lq":  "last-quarter",
    "ty":  "this-year",
    "ly":  "last-year",
}

def resolve_time(keyword, cycles):
    keyword = _TIME_ALIASES.get(keyword, keyword)
    now = today()

    # custom cycles  e.g. "clinic", "clinic-1"
    for name, start_day in cycles.items():
        m = re.fullmatch(rf"{name}(?:-(\d+))?", keyword)
        if m:
            offset = int(m.group(1)) if m.group(1) else 0
            return resolve_cycle(start_day, offset)

    # YYYY-MM
    if re.fullmatch(r"\d{4}-\d{2}", keyword):
        year, month = map(int, keyword.split("-"))
        return month_range(year, month)

    if keyword == "today":     return now, now
    if keyword == "yesterday": y = now - dt.timedelta(days=1); return y, y
    if keyword == "this-week":
        start = now - dt.timedelta(days=now.weekday())
        return start, start + dt.timedelta(days=6)
    if keyword == "last-week":
        end = now - dt.timedelta(days=now.weekday() + 1)
        return end - dt.timedelta(days=6), end
    if keyword == "this-month":  return month_range(now.year, now.month)
    if keyword == "last-month":
        prev = now.replace(day=1) - dt.timedelta(days=1)
        return month_range(prev.year, prev.month)
    if keyword == "this-quarter":
        return quarter_range(now.year, (now.month - 1) // 3)
    if keyword == "last-quarter":
        q    = (now.month - 1) // 3 - 1
        year = now.year
        if q < 0: q, year = 3, year - 1
        return quarter_range(year, q)
    if keyword == "this-year": return dt.date(now.year, 1, 1), dt.date(now.year, 12, 31)
    if keyword == "last-year": return dt.date(now.year - 1, 1, 1), dt.date(now.year - 1, 12, 31)
    if keyword == "all":       return dt.date.min, dt.date.max

    raise ValueError(f"Unknown time keyword: {keyword}")

# --------------------------------------------------
# Record parsing
# --------------------------------------------------

def parse_line(line):
    """Parse a log line into (date, kv_dict, note)."""
    main, _, note = line.partition("|")
    parts = main.strip().split()
    date  = parts[0]
    kv    = {}
    for p in parts[1:]:
        if "=" not in p:
            continue
        k, v = p.split("=", 1)
        if k not in kv:
            kv[k] = v
        elif isinstance(kv[k], list):
            kv[k].append(v)
        else:
            kv[k] = [kv[k], v]
    return parse_date(date), kv, note.strip()

def build_record_line(date, record, note=None):
    parts = []
    for k, v in record.items():
        if isinstance(v, list):
            parts.extend(f"{k}={i}" for i in v)
        else:
            parts.append(f"{k}={v}")
    line = date + " " + " ".join(parts)
    if note:
        line += " | " + note
    return line

def apply_where(kv, filters):
    """Return True if kv matches all filter expressions."""
    ops = {
        "=":  lambda a, b: a == b,
        "!=": lambda a, b: a != b,
        ">":  lambda a, b: a > b,
        "<":  lambda a, b: a < b,
        ">=": lambda a, b: a >= b,
        "<=": lambda a, b: a <= b,
    }
    for cond in filters:
        m = re.match(r"(\w+)(!=|>=|<=|~|=|>|<)(.+)", cond)
        if not m:
            continue
        key, op, val = m.groups()
        # ~ operator: field contains substring (case-insensitive)
        if op == "~":
            cur = kv.get(key, "")
            if isinstance(cur, list):
                if not any(val.lower() in v.lower() for v in cur):
                    return False
            else:
                if val.lower() not in cur.lower():
                    return False
            continue
        if key not in kv:
            return False
        cur = kv[key]
        if isinstance(cur, list):
            if op == "="  and val not in cur: return False
            if op == "!=" and val in cur:     return False
            if op not in ("=", "!="):         return False
            continue
        if key in numeric_fields():
            try:
                cur, val = int(cur), int(val)
            except (ValueError, TypeError):
                pass
        if op not in ops or not ops[op](cur, val):
            return False
    return True

# --------------------------------------------------
# Query engine
# --------------------------------------------------

def scan_records(start, end, filters, search):
    """Scan all log files and return (matching_lines, numeric_total)."""
    results = []
    total   = 0
    os.makedirs(RECORDS_DIR, exist_ok=True)
    for fname in sorted(os.listdir(RECORDS_DIR)):
        if not fname.endswith(".log"):
            continue
        path = os.path.join(RECORDS_DIR, fname)
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                d, kv, note = parse_line(line)
                if not (start <= d <= end):
                    continue
                if search and search.lower() not in line.lower():
                    continue
                if not apply_where(kv, filters):
                    continue
                results.append(line)
                val = numeric_value(kv)
                if val is not None:
                    total += val
    return results, total

def append_record(line):
    os.makedirs(RECORDS_DIR, exist_ok=True)
    year = line[:4]
    path = os.path.join(RECORDS_DIR, f"{year}.log")
    with open(path, "a", encoding="utf-8") as f:
        f.write(line + "\n")

# --------------------------------------------------
# Validation
# --------------------------------------------------

def _get_field_options(schema, type_schema, field, record):
    """
    Return the valid options list for a field given the current record state.
    Returns None for free-text fields or fields with no defined options.
    """
    field_def = type_schema.get("fields", {}).get(field, {})

    # shared reference
    if "use" in field_def:
        key        = field_def["use"].split(".", 1)[1]
        shared_def = schema.get("shared", {}).get(key, {})
        opts       = shared_def.get("options")
        return opts if isinstance(opts, list) else None

    opts = field_def.get("options")

    # flat list
    if isinstance(opts, list):
        return opts

    # parent-dependent
    if isinstance(opts, dict):
        parent = field_def.get("parent")
        if parent:
            parent_val = record.get(parent)
            return opts.get(parent_val, [])
        return None

    return None

def validate_record(schema, record):
    problems = []
    rtype    = record.get("type")

    if rtype not in schema["types"]["allowed"]:
        problems.append(f"Invalid type '{rtype}'")
        return problems

    type_schema = schema["type"][rtype]

    # required fields  (now a flat list, not a nested dict)
    for f in type_schema.get("required", []):
        if f not in record:
            problems.append(f"Missing required field: {f}")

    # integer fields  (from global [fields] metadata)
    for field, meta in schema.get("fields", {}).items():
        if isinstance(meta, dict) and meta.get("type") == "int" and field in record:
            if not str(record[field]).isdigit():
                problems.append(f"Field '{field}' must be integer")

    # allowed field names
    allowed_fields = {"type", "tag"}
    allowed_fields.update(schema.get("fields", {}).keys())
    allowed_fields.update(type_schema.get("required", []))
    allowed_fields.update(type_schema.get("fields", {}).keys())
    allowed_fields.update(type_schema.get("conditions", {}).keys())
    for f in record:
        if f not in allowed_fields:
            problems.append(f"Unknown field '{f}'")

    # field value validation  (check against options where defined)
    # fields with no options defined in schema are treated as free-text — skip silently
    for field, value in record.items():
        if field == "type":
            continue
        opts = _get_field_options(schema, type_schema, field, record)
        if opts is None:
            continue
        values = value if isinstance(value, list) else [value]
        for v in values:
            if str(v) not in [str(o) for o in opts]:
                problems.append(f"Invalid value '{v}' for field '{field}'")

    # conditional required
    for field, rule in type_schema.get("conditions", {}).items():
        condition = rule.get("when", {})
        if all(record.get(k) == v for k, v in condition.items()):
            if field not in record:
                problems.append(f"Field '{field}' required when {condition}")

    return problems

def lint_records(records, schema):
    errors = 0
    for line in records:
        _, kv, _ = parse_line(line)
        problems = validate_record(schema, kv)
        if problems:
            errors += 1
            print("\n⚠ Problem in record:")
            print(line)
            for p in problems:
                print("  -", p)
    if errors == 0:
        print("✔ No lint errors found")

# --------------------------------------------------
# Analysis  —  group + pivot return data, render separately
# --------------------------------------------------

def group_results(results, fields):
    """Return (counts, sums, has_numeric) keyed by tuple of field values."""
    counts     = {}
    sums       = {}
    has_amount = False
    for line in results:
        d, kv, _ = parse_line(line)
        key_parts = []
        for field in fields:
            if field == "month": key_parts.append(d.strftime("%Y-%m"))
            elif field == "year": key_parts.append(str(d.year))
            else: key_parts.append(str(kv.get(field, "-")))
        key    = tuple(key_parts)
        amount = numeric_value(kv)
        counts[key] = counts.get(key, 0) + 1
        if amount is not None:
            sums[key]  = sums.get(key, 0) + amount
            has_amount = True
    return counts, sums, has_amount

def pivot_results(results, row_field, col_field, count_mode=False, sort_col=None):
    """Return pivot table as (table_dict, sorted_cols, row_order)."""
    table = {}
    cols  = set()

    def resolve_vals(d, kv, field):
        if field == "month": return [d.strftime("%Y-%m")]
        if field == "year":  return [str(d.year)]
        if field in kv:      return kv[field] if isinstance(kv[field], list) else [kv[field]]
        return None

    for line in results:
        d, kv, _ = parse_line(line)
        row_vals = resolve_vals(d, kv, row_field)
        col_vals = resolve_vals(d, kv, col_field)
        if row_vals is None or col_vals is None:
            continue
        amount = numeric_value(kv)
        for row in row_vals:
            for col in col_vals:
                cols.add(col)
                table.setdefault(row, {})
                table[row][col] = table[row].get(col, 0)
                if count_mode or amount is None:
                    table[row][col] += 1
                else:
                    table[row][col] += int(amount)

    cols     = sorted(cols)
    row_tots = {row: sum(table[row].get(c, 0) for c in cols) for row in table}

    if sort_col and sort_col in cols:
        rows = sorted(table, key=lambda r: table[r].get(sort_col, 0), reverse=True)
    else:
        rows = sorted(row_tots, key=row_tots.get, reverse=True)

    return table, cols, rows

def render_group(counts, sums, has_amount, fields):
    label_fn = lambda key: "  ".join(key) if isinstance(key, tuple) else key

    if has_amount:
        grand = 0
        for key in sorted(sums):
            grand += sums[key]
            print(f"{label_fn(key):<20} {fmt(sums[key])}")
        print("-" * 40)
        print(f"{'Total':<20} {fmt(grand)}")
    else:
        grand = 0
        for key in sorted(counts):
            grand += counts[key]
            print(f"{label_fn(key):<20} {counts[key]}")
        print("-" * 40)
        print(f"{'Total':<20} {grand}")

def render_pivot(table, cols, rows, row_field):
    width = 12
    header = f"{row_field:15}"
    for c in cols:
        header += f"{c:>{width}}"
    header += f"{'Total':>{width}}"
    print()
    print(header)
    print("-" * len(header))

    col_totals = {c: 0 for c in cols}
    grand      = 0
    for row in rows:
        row_total = 0
        line      = f"{row:15}"
        for c in cols:
            val = table[row].get(c, 0)
            line += f"{val:>{width}}"
            row_total      += val
            col_totals[c]  += val
        line  += f"{row_total:>{width}}"
        grand += row_total
        print(line)

    print("-" * len(header))
    total_line = f"{'Total':15}"
    for c in cols:
        total_line += f"{col_totals[c]:>{width}}"
    total_line += f"{grand:>{width}}"
    print(total_line)
    print()

def render_summary(results, start, end, time_label, filters, total):
    count = len(results)
    rows  = [("Time range", f"{start} to {end} ({time_label})")]
    if results:
        rows.append(("Data span", f"{results[0].split()[0]} to {results[-1].split()[0]}"))
    rows.append(("Records", count))
    if filters:
        rows.append(("Filters", " ".join(filters)))
    if total > 0:
        rows.append(("Total",   fmt(total)))
        rows.append(("Average", fmt_avg(total / count)))
    width = max(len(r[0]) for r in rows)
    print()
    print("-" * 50)
    for label, value in rows:
        print(f"{label:<{width}} : {value}")
    print("-" * 50)

# --------------------------------------------------
# Dashboard engine
# --------------------------------------------------

def _run_base_query(name, queries, start, end, cycles):
    """Run a named base query, respecting its own time if defined."""
    q       = queries[name]
    filters = q["where"].split()
    if "time" in q:
        start, end = resolve_time(q["time"], cycles)
    results, total = scan_records(start, end, filters, None)
    return len(results), total

def run_metric(name, queries, start, end, cycles):
    metrics = queries.get("metrics", {})
    if name not in metrics:
        return False
    m = metrics[name]

    if "ratio" in m:
        q1, q2  = m["ratio"]
        c1, _   = _run_base_query(q1, queries, start, end, cycles)
        c2, _   = _run_base_query(q2, queries, start, end, cycles)
        if c2 == 0:
            print(f"{name:<24} no data")
        else:
            print(f"{name:<24} {(c1/c2)*100:.1f}%  ({c1}/{c2})")
        return True

    if "avg" in m:
        count, total = _run_base_query(m["avg"], queries, start, end, cycles)
        if count == 0:
            print(f"{name:<24} no data")
        else:
            print(f"{name:<24} {fmt_avg(total / count)}")
        return True

    return False

def run_dashboard(name, queries, start, end, cycles):
    dashboards = queries.get("dashboards", {})
    if name not in dashboards:
        return False
    print(f"\nDashboard: {name}")
    print(f"Period:    {start} to {end}")
    print("-" * 40)
    for item in dashboards[name].get("metrics", []):
        if run_metric(item, queries, start, end, cycles):
            continue
        if item in queries:
            count, total = _run_base_query(item, queries, start, end, cycles)
            suffix = f"  ({fmt(total)})" if total > 0 else ""
            print(f"{item:<24} {count}{suffix}")
    print()
    return True

# --------------------------------------------------
# Field discovery
# --------------------------------------------------

def show_fields(results):
    bad = non_dimension_fields()
    types = {}
    for line in results:
        d, kv, _ = parse_line(line)
        rtype = kv.get("type", "unknown")
        types.setdefault(rtype, {"fields": {}, "counts": {}})
        for k, v in kv.items():
            types[rtype]["fields"].setdefault(k, set())
            types[rtype]["counts"][k] = types[rtype]["counts"].get(k, 0) + 1
            vals = v if isinstance(v, list) else [v]
            for item in vals:
                if len(types[rtype]["fields"][k]) < 5:
                    types[rtype]["fields"][k].add(str(item))

    pivot_pairs = get_config().get("discovery", {}).get("pivot_pairs", [])

    suggested_groups  = []
    suggested_pivots  = []

    print("\nFields by record type\n")
    for rtype in sorted(types):
        print(f"[{rtype}]\n")
        fields = types[rtype]["fields"]
        counts = types[rtype]["counts"]
        good   = []
        for field in sorted(fields):
            unique = len(fields[field])
            total  = counts[field]
            ratio  = unique / total if total else 1
            is_dim = field not in bad and not field.endswith("_id") and ratio < 0.4
            star   = "★ " if is_dim else "  "
            if is_dim:
                good.append(field)
            print(f"{star}{field:12} {', '.join(sorted(fields[field]))}")
        print()
        for f in good[:3]:
            suggested_groups.append(f"ptos -y {rtype} -G {f}")
        for a, b in pivot_pairs:
            if a in good and b in good:
                suggested_pivots.append(f"ptos -y {rtype} -v {a} {b}")

    print("★ = recommended dimension\n")
    if suggested_groups:
        print("Suggested group commands\n")
        for cmd in suggested_groups[:6]: print(cmd)
        print()
    if suggested_pivots:
        print("Suggested pivot commands\n")
        for cmd in suggested_pivots: print(cmd)
        print()

# --------------------------------------------------
# Interactive prompts
# --------------------------------------------------

def choose_from_list(prompt, options):
    while True:
        print(f"\n{prompt}")
        for i, opt in enumerate(options, 1):
            print(f"{i}) {opt}")
        choice = input("\nEnter number: ").strip()
        if choice.isdigit() and 1 <= int(choice) <= len(options):
            return options[int(choice) - 1]

def input_text(prompt):
    while True:
        val = input(f"\n{prompt}: ").strip()
        if val:
            return val.replace(" ", "_")

def input_int(prompt):
    while True:
        val = input(f"\n{prompt}: ").strip()
        if val.isdigit():
            return val

def input_date():
    default = today().isoformat()
    while True:
        val = input(f"\nDate [{default}]: ").strip()
        if not val:
            return default
        try:
            parse_date(val)
            return val
        except ValueError:
            print("Invalid date format (YYYY-MM-DD)")

def input_tags(allowed_tags):
    tags = []
    while True:
        remaining = [t for t in allowed_tags if t not in tags]
        options   = {i: t for i, t in enumerate(remaining, 1)}
        print("\nTag options:")
        for i, t in options.items():
            print(f"{i}) {t}")
        n = len(options)
        print(f"{n+1}) Custom")
        print(f"{n+2}) Done")
        val = input("Enter number or tags: ").strip()
        if not val or val.lower() in ("done", "d"):
            break
        if val.isdigit():
            i = int(val)
            if i in options:
                tags.append(options[i])
            elif i == n + 1:
                tag = input_text("Enter custom tag")
                if tag not in tags:
                    tags.append(tag)
            elif i == n + 2:
                break
        else:
            for p in val.split(","):
                tag = p.strip().replace(" ", "_")
                if tag and tag not in tags:
                    tags.append(tag)
    return tags

# --------------------------------------------------
# Schema interpreter  (field resolution for interactive add)
# --------------------------------------------------

def resolve_options(schema, type_schema, field):
    """
    Return the options list for a field, resolving shared references
    and parent-independent flat lists.  Returns None for free-text fields.
    """
    field_def = type_schema.get("fields", {}).get(field, {})

    # shared reference  →  use = "shared.X"
    if "use" in field_def:
        ref  = field_def["use"]              # e.g. "shared.source"
        key  = ref.split(".", 1)[1]          # e.g. "source"
        shared_def = schema.get("shared", {}).get(key, {})
        opts = shared_def.get("options")
        return opts if isinstance(opts, list) else None

    opts = field_def.get("options")

    # flat list
    if isinstance(opts, list):
        return opts

    # parent-dependent — caller must use resolve_options_for_value
    if isinstance(opts, dict):
        return None

    return None

def resolve_options_for_value(type_schema, field, parent_value):
    """
    Return the options list for a parent-dependent field given the
    parent's current value.  e.g. category options when domain=self.
    """
    field_def = type_schema.get("fields", {}).get(field, {})
    opts      = field_def.get("options", {})
    if isinstance(opts, dict):
        return opts.get(parent_value, [])
    return []

def resolve_field(schema, type_schema, field, record):
    """Prompt user for a single field value."""
    # integer field  (from global [fields] metadata)
    field_meta = schema.get("fields", {}).get(field, {})
    if isinstance(field_meta, dict) and field_meta.get("type") == "int":
        return input_int(f"Enter {field}")

    field_def = type_schema.get("fields", {}).get(field, {})

    # parent-dependent field  (options depend on another field's value)
    if isinstance(field_def.get("options"), dict):
        parent       = field_def["parent"]
        parent_value = record.get(parent)
        options      = resolve_options_for_value(type_schema, field, parent_value)
        if options:
            return choose_from_list(f"Select {field}:", options)
        return input_text(f"Enter {field}")

    # flat options or shared reference
    options = resolve_options(schema, type_schema, field)
    if options:
        return choose_from_list(f"Select {field}:", options)

    # free text fallback
    return input_text(f"Enter {field}")

def resolve_tags(schema, type_schema, record):
    """
    Return sorted list of tag options for a record based on field values.
    Reads from  [type.X.tags.fieldname]  options.value = [...]
    """
    allowed_tags = set()
    tag_section  = type_schema.get("tags", {})

    for field, trigger in tag_section.items():
        # field value(s) in the current record
        value = record.get(field)
        if value is None:
            continue
        values   = value if isinstance(value, list) else [value]
        opts_map = trigger.get("options", {})
        for v in values:
            allowed_tags.update(opts_map.get(v, []))

    return sorted(allowed_tags)

def complete_record(schema, record):
    """Fill missing required and conditional fields interactively. Returns (record, note)."""
    rtype = record.get("type")
    if not rtype:
        rtype          = choose_from_list("Select type:", schema["types"]["allowed"])
        record["type"] = rtype

    type_schema = schema["type"][rtype]

    # required fields
    for field in type_schema.get("required", []):
        if field not in record:
            record[field] = resolve_field(schema, type_schema, field, record)

    # conditional required  (e.g. fit when outcome=prescribed)
    for field, rule in type_schema.get("conditions", {}).items():
        if all(record.get(k) == v for k, v in rule.get("when", {}).items()):
            if field not in record:
                record[field] = resolve_field(schema, type_schema, field, record)

    # tags
    if "tag" not in record:
        tags = input_tags(resolve_tags(schema, type_schema, record))
        if tags:
            record["tag"] = tags

    note = input("\nAdd note (optional): ").strip()
    return record, note

def save_as_preset(name, record):
    """Append a new preset to presets.toml from a record dict."""
    presets_path = os.path.join(CONFIG_DIR, "presets.toml")
    lines = []
    lines.append(f"\n[presets.{name}]")
    for k, v in record.items():
        if k == "tag":
            if isinstance(v, list):
                tags = ", ".join(f'"{t}"' for t in v)
                lines.append(f"tag      = [{tags}]")
            else:
                lines.append(f'tag      = ["{v}"]')
        elif k == "amount":
            lines.append(f"amount   = {v}")
        else:
            lines.append("{:<8} = \"{}\"".format(k, v))
    lines.append("# amount omitted — will be prompted each time" if "amount" not in record else "")
    block = "\n".join(l for l in lines if l is not None)
    with open(presets_path, "a", encoding="utf-8") as f:
        f.write(block + "\n")
    print(f"Preset '{name}' saved to presets.toml")

def interactive_add(schema, date=None):
    record, note = complete_record(schema, {})
    problems     = validate_record(schema, record)
    if problems:
        sys.exit(problems[0])
    date = date if date else input_date()
    line = build_record_line(date, record, note)
    print("\nRecord preview:\n")
    print(line)
    ans = input("\nSave? (Y/n): ").strip().lower()
    if ans == "n":
        return
    append_record(line)
    print("Record added.")
    # offer to save as preset
    preset_name = input("\nSave as preset? (name or Enter to skip): ").strip()
    if preset_name:
        save_as_preset(preset_name, record)

def quick_add(args):
    presets = get_presets()
    if not args.preset:
        print("\nAvailable presets:\n")
        for name in sorted(presets):
            print(" ", name)
        print()
        return
    name = args.preset[0]
    if name not in presets:
        sys.exit(f"Unknown preset: {name}")
    record = dict(presets[name])
    for item in args.preset[1:]:
        if "=" not in item:
            continue
        k, v = item.split("=", 1)
        if k == "tag":
            record.setdefault("tag", [])
            if isinstance(record["tag"], list):
                record["tag"].append(v)
            else:
                record["tag"] = [record["tag"], v]
        else:
            record[k] = v
    schema       = get_schema()
    record, note = complete_record(schema, record)
    problems     = validate_record(schema, record)
    if problems:
        sys.exit(problems[0])
    line = build_record_line(resolve_date(args.date), record, note if note else args.note)
    append_record(line)
    print("\nRecord added:\n")
    print(line)

# --------------------------------------------------
# Journal
# --------------------------------------------------

def get_today_journal():
    today_str = today().isoformat()
    year_dir  = os.path.join(JOURNAL_DIR, today_str[:4])
    os.makedirs(year_dir, exist_ok=True)
    path = os.path.join(year_dir, f"{today_str}.md")
    if not os.path.exists(path):
        template_path = os.path.join(TEMPLATE_DIR, "daily.md")
        if os.path.exists(template_path):
            with open(template_path, "r", encoding="utf-8") as f:
                content = f.read().replace("{{date}}", today_str)
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)
        else:
            open(path, "a", encoding="utf-8").close()
    return path

# --------------------------------------------------
# Editor
# --------------------------------------------------

def resolve_editor():
    cmd = get_config().get("editor", {}).get("command")
    if cmd:
        return cmd.split()
    if os.environ.get("EDITOR"):
        return os.environ["EDITOR"].split()
    return ["notepad"] if os.name == "nt" else ["nvim"]

def edit_target(target):
    shortcuts = {
        "r": "records", "s": "schema", "q": "queries",
        "c": "config",  "p": "presets", "d": "daily", "x": "script",
    }
    target = shortcuts.get(target, target) if target else "records"
    paths  = {
        "records": os.path.join(RECORDS_DIR, f"{today().year}.log"),
        "schema":  SCHEMA_PATH,
        "queries": QUERIES_PATH,
        "config":  CONFIG_PATH,
        "presets": PRESETS_PATH,
        "daily":   get_today_journal(),
        "script":  os.path.abspath(sys.argv[0]),
    }
    if target not in paths:
        sys.exit(f"Unknown edit target: {target}")
    subprocess.run(resolve_editor() + [paths[target]])

# --------------------------------------------------
# Init
# --------------------------------------------------

# --------------------------------------------------
# Starter file content  (written by --init, no external templates needed)
# --------------------------------------------------

_STARTER_CONFIG = """[editor]
command = "nvim"

[display]
currency = "₹"

[cycles]
# Define billing/reporting cycles as day-of-month they start
# Example: clinic = 26  means cycle runs 26th → 25th next month
# Usage:   ptos -t clinic      (current cycle)
#          ptos -t clinic-1    (previous cycle)
"""

_STARTER_QUERIES = """# --------------------------------------------------
# PTOS QUERIES
# --------------------------------------------------
# Base queries  →  referenced by metrics and dashboards
# Metrics        →  ratio or avg over base queries
# Dashboards     →  named list of metrics + base queries
# Saved queries  →  any filter + time + group/pivot combo
#
# Usage:
#   ptos -q <name>              run a saved query
#   ptos -q <name> -t last-month   override time window
#   ptos -q                     list all queries
# --------------------------------------------------

# Example base query
[all_expenses]
where = "type=expense"
time  = "this-month"
sum   = true

# Example metric
[metrics.avg_expense]
avg = "all_expenses"

# Example dashboard
[dashboards.home]
metrics = ["all_expenses", "avg_expense"]
"""

_STARTER_PRESETS = """# --------------------------------------------------
# PTOS PRESETS
# --------------------------------------------------
# Quick-add shortcuts for frequent records.
# Usage:  ptos -p <name>
#         ptos -p <name> field=value   (override a field)
#         ptos -p <name> -d yesterday
# --------------------------------------------------

# [presets.commute]
# type     = "expense"
# domain   = "self"
# category = "transport"
# amount   = 90
# tag      = ["auto"]
"""

_STARTER_SCHEMA = """# --------------------------------------------------
# PTOS SCHEMA
# --------------------------------------------------
#
# Every type follows the same pattern:
#
#   required = ["field1", "field2"]
#
#   [type.X.fields.fieldname]
#   options = ["a", "b", "c"]               # flat list
#
#   [type.X.fields.fieldname]               # parent-dependent
#   parent = "other_field"
#   options.value1 = ["a", "b"]
#   options.value2 = ["c", "d"]
#
#   [type.X.fields.fieldname]               # reuse shared definition
#   use = "shared.fieldname"
#
#   [type.X.tags.fieldname]                 # tags triggered by field value
#   options.value1 = ["tag_a", "tag_b"]
#
#   [type.X.conditions.fieldname]           # conditionally required field
#   when = { other_field = "value" }
#
# --------------------------------------------------

[types]
allowed = ["expense", "income", "exercise", "learning"]

# --------------------------------------------------
# GLOBAL FIELD METADATA
# --------------------------------------------------

[fields.amount]
type         = "int"
dimension    = false
aggregatable = true

[fields.duration]
type         = "int"
dimension    = false
aggregatable = true

[fields.domain]
type      = "string"
dimension = true

[fields.category]
type      = "string"
dimension = true

[fields.tag]
type      = "string"
dimension = true
multi     = true

# --------------------------------------------------
# SHARED FIELD DEFINITIONS
# --------------------------------------------------

# (add shared fields here and reference with  use = "shared.fieldname")

# ==================================================
# TYPES  —  add your own below using the pattern above
# ==================================================

# ----------------------
# EXPENSE
# ----------------------

[type.expense]
required = ["domain", "category", "amount"]

[type.expense.fields.domain]
options = ["self", "home", "work"]

[type.expense.fields.category]
parent       = "domain"
options.self = ["food", "transport", "health", "education", "personal"]
options.home = ["grocery", "utilities", "rent", "household"]
options.work = ["admin", "supplies", "travel", "meals"]

[type.expense.tags.category]
options.food      = ["snacks", "coffee", "restaurant"]
options.transport = ["auto", "bus", "taxi", "petrol"]
options.grocery   = ["vegetables", "milk", "fruits"]

# ----------------------
# INCOME
# ----------------------

[type.income]
required = ["source", "amount"]

[type.income.fields.source]
options = ["salary", "freelance", "gift", "refund", "other"]

# ----------------------
# EXERCISE
# ----------------------

[type.exercise]
required = ["activity", "duration"]

[type.exercise.fields.activity]
options = ["walk", "run", "cycle", "strength", "yoga", "stretch"]

[type.exercise.tags.activity]
options.walk = ["morning", "evening"]
options.run  = ["morning", "evening"]

# ----------------------
# LEARNING
# ----------------------

[type.learning]
required = ["topic", "source", "domain"]

[type.learning.fields.source]
options = ["youtube", "podcast", "book", "article", "course", "audio_book"]

[type.learning.fields.domain]
options = ["self", "work"]
"""

_STARTER_JOURNAL = """# {{date}}

## Focus


## Notes


## Log

"""

def _write_if_missing(path, content, label):
    if os.path.exists(path):
        print(f"  exists   {label}")
    else:
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"  created  {label}")

def init_ptos():
    print("\nInitializing PTOS...\n")

    for d in [CONFIG_DIR, RECORDS_DIR, JOURNAL_DIR, TEMPLATE_DIR]:
        os.makedirs(d, exist_ok=True)

    _write_if_missing(CONFIG_PATH,  _STARTER_CONFIG,  "config/config.toml")
    _write_if_missing(SCHEMA_PATH,  _STARTER_SCHEMA,  "config/schema.toml")
    _write_if_missing(QUERIES_PATH, _STARTER_QUERIES, "config/queries.toml")
    _write_if_missing(PRESETS_PATH, _STARTER_PRESETS, "config/presets.toml")
    _write_if_missing(
        os.path.join(TEMPLATE_DIR, "daily.md"),
        _STARTER_JOURNAL,
        "templates/daily.md"
    )

    year_log = os.path.join(RECORDS_DIR, f"{today().year}.log")
    if not os.path.exists(year_log):
        open(year_log, "a", encoding="utf-8").close()
        print(f"  created  records/{today().year}.log")
    else:
        print(f"  exists   records/{today().year}.log")

    print("\nDone. Edit config/schema.toml to define your record types.\n")

# --------------------------------------------------
# CLI  — argument parsing only, no logic
# --------------------------------------------------

def build_parser(cycles):
    cycle_help = ", ".join(f"{n}, {n}-1, {n}-2" for n in cycles) if cycles \
                 else "custom cycles defined in config.toml"

    p = argparse.ArgumentParser(
        prog="ptos",
        description=(
            "PTOS — Plain Text Operating System\n\n"
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
            "  ptos --from 2026-01-01 --to 2026-03-31\n"
            "  ptos --lint\n"
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
            "  YYYY-MM            (e.g. 2026-03)\n"
            "  custom cycles defined in config.toml (e.g. clinic, clinic-1)\n"
        ),
        formatter_class=argparse.RawTextHelpFormatter,
    )

    add = p.add_argument_group("Add")
    add.add_argument("-a", "--add",    nargs="*", help="Add record (no args = interactive)")
    add.add_argument("-n", "--note",              help="Note to attach to record")
    add.add_argument("-d", "--date",              help="Date for the record (YYYY-MM-DD, default: today)")
    add.add_argument("-p", "--preset", nargs="*", help="Quick-add from preset")

    qry = p.add_argument_group("Query")
    qry.add_argument("-q", "--query",  nargs="?", const="__LIST__", help="Run saved query (no name = list all)")
    qry.add_argument("-w", "--where",  nargs="+", action="append",  help="Filter expressions — operators: = != > < >= <= ~(contains)")
    qry.add_argument("-t", "--time",   default="this-month",        help="Time window — full or short: td yd tw lw tm lm tq lq ty ly YYYY-MM, or custom cycles from config.toml")
    qry.add_argument("-f", "--from",   dest="date_from",            help="Start date YYYY-MM-DD")
    qry.add_argument("-T", "--to",     dest="date_to",              help="End date YYYY-MM-DD")
    qry.add_argument("-y", "--type",                                help="Filter by record type")
    qry.add_argument("-g", "--tag",    action="append",             help="Filter by tag (repeatable)")
    qry.add_argument("-S", "--search",                              help="Full-text search")

    ana = p.add_argument_group("Analyse")
    ana.add_argument("-G", "--group",  nargs="+", help="Group by one or more fields")
    ana.add_argument("-v", "--pivot",  nargs="+", metavar=("ROW", "COL"), help="Pivot table")
    ana.add_argument("--count",        action="store_true", help="Count rows instead of summing")
    ana.add_argument("--sort",                              help="Sort pivot by column name")
    ana.add_argument("--trend",        nargs="?", const=6, type=int, metavar="N",
                     help="Show last N periods side by side (default: 6)")
    ana.add_argument("--due",          nargs="?", const=7, type=int, metavar="DAYS",
                     help="Show records not updated in N days — type and key configured in queries.toml [due]")

    utl = p.add_argument_group("Utilities")
    utl.add_argument("-l", "--lint",    action="store_true", help="Validate records against schema")
    utl.add_argument("-j", "--journal", action="store_true", help="Open today's journal")
    utl.add_argument("-e", "--edit",    nargs="?", const="records", metavar="TARGET",
                     help="Edit a workspace file  (r s q c p d x)")
    utl.add_argument("--fields", action="store_true", help="Show field discovery report")
    utl.add_argument("--init",   action="store_true", help="Initialise workspace")

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
    metrics    = queries.get("metrics",    {})
    dashboards = queries.get("dashboards", {})

    metric_mode    = args.query in metrics
    dashboard_mode = args.query in dashboards

    q = queries.get(args.query)
    if not q and not metric_mode and not dashboard_mode:
        sys.exit(f"Query not found: {args.query}")

    query_filters = []
    if q:
        query_filters = q.get("where", "").split()
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

def run_due(days_override):
    """Show records whose most recent entry per key is older than N days.
    All config read from queries.toml [due] section.
    Priority order derived from schema field options — no hardcoding."""

    queries = get_queries()
    due_cfg = queries.get("due")
    if not due_cfg:
        sys.exit("[due] section not found in queries.toml\n"
                 "Add it to enable --due. See README for details.")

    rec_type = due_cfg.get("type")
    key_field = due_cfg.get("key")
    if not rec_type or not key_field:
        sys.exit("[due] section in queries.toml is missing 'type' or 'key'.\n"
                 "Example:\n  [due]\n  type = \"followup\"\n  key  = \"client\"\n  days = 7")
    sort_field = due_cfg.get("sort_by")
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

    if args.edit:
        edit_target(args.edit)
        return

    if args.preset is not None:
        quick_add(args)
        return

    if args.journal:
        edit_target("daily")
        return

    # ---- add mode ----
    schema = get_schema()

    if args.add is not None:
        if not args.add:
            interactive_add(schema, resolve_date(args.date))
        else:
            record = {}
            for item in args.add:
                k, v = item.split("=", 1)
                if k in record:
                    record[k] = record[k] if isinstance(record[k], list) else [record[k]]
                    record[k].append(v)
                else:
                    record[k] = v
            problems = validate_record(schema, record)
            if problems:
                sys.exit(problems[0])
            append_record(build_record_line(resolve_date(args.date), record, args.note))
            print("Record added.")
        return

    # ---- lint mode ----
    if args.lint:
        results, _ = scan_records(dt.date.min, dt.date.max, [], None)
        lint_records(results, schema)
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

    # ---- time resolution ----
    if args.date_from or args.date_to:
        start      = dt.date.fromisoformat(str(args.date_from)) if args.date_from else dt.date.min
        end        = dt.date.fromisoformat(str(args.date_to))   if args.date_to   else dt.date.max
        time_label = "custom range"
    else:
        try:
            start, end = resolve_time(args.time, cycles)
        except ValueError:
            sys.exit(f"Invalid time keyword: '{args.time}'  —  run: ptos --help  for valid time windows")
        time_label = _TIME_ALIASES.get(args.time, args.time)

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

    # ---- scan ----
    results, total = scan_records(start, end, final_filters, args.search)

    if not results:
        print("\nNo records found.\n")
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
        render_summary(results, start, end, time_label, final_filters, total)
        vf = detect_value_field(results)
        label = f"Value: {vf}" if vf and not args.count else "Count mode"
        print(f"\nPivot  row={row}  col={col}  {label}")
        table, cols, rows = pivot_results(results, row, col, args.count, args.sort)
        render_pivot(table, cols, rows, row)
        return

    # ---- group ----
    if args.group:
        render_summary(results, start, end, time_label, final_filters, total)
        vf = detect_value_field(results)
        label = f"Value: {vf}" if vf else "Count"
        print(f"\nGrouped by: {' '.join(args.group)}  ({label})\n")
        counts, sums, has_amount = group_results(results, args.group)
        render_group(counts, sums, has_amount, args.group)
        return

    # ---- default: list records ----
    for line in results:
        print(line)
    render_summary(results, start, end, time_label, final_filters, total)


if __name__ == "__main__":
    main()
