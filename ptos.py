import argparse
import os
import sys
import datetime as dt
import tomllib
import re
import shutil
import subprocess

sys.stdout.reconfigure(encoding="utf-8")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_DIR = os.path.join(BASE_DIR, "config")
RECORDS_DIR = os.path.join(BASE_DIR, "records")

JOURNAL_DIR = os.path.join(BASE_DIR, "journal")
TEMPLATE_PATH = os.path.join(BASE_DIR, "templates", "daily.md")

SCHEMA_PATH = os.path.join(CONFIG_DIR, "schema.toml")
QUERIES_PATH = os.path.join(CONFIG_DIR, "queries.toml")
CONFIG_PATH = os.path.join(CONFIG_DIR, "config.toml")

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

TEMPLATE_DIR = os.path.join(SCRIPT_DIR, "templates")
# --------------------------------------------------
# Utilities
# --------------------------------------------------

def load_toml(path):
    with open(path, "rb") as f:
        return tomllib.load(f)

def today():
    return dt.date.today()

def parse_date(s):
    return dt.date.fromisoformat(s)

def ensure_dirs():
    os.makedirs(RECORDS_DIR, exist_ok=True)

def edit_target(target):

    shortcuts = {
        "r": "records",
        "s": "schema",
        "q": "queries",
        "c": "config",
        "p": "presets",
        "d": "daily",
        "x": "script"
    }

    if not target:
        target = "records"

    target = shortcuts.get(target, target)

    # resolve path

    if target == "records":

        year = dt.date.today().year
        path = os.path.join(RECORDS_DIR, f"{year}.log")

    elif target == "schema":

        path = SCHEMA_PATH

    elif target == "queries":

        path = QUERIES_PATH

    elif target == "config":

        path = CONFIG_PATH

    elif target == "presets":

        path = os.path.join(CONFIG_DIR, "presets.toml")

    elif target == "daily":

        path = get_today_journal()

    elif target == "script":
        path = get_script_path()

    else:

        sys.exit(f"Unknown edit target: {target}")

    # choose editor

    config = load_toml(CONFIG_PATH)

    editor_cmd = config.get("editor", {}).get("command")

    if editor_cmd:
        editor = editor_cmd.split()

    elif os.environ.get("EDITOR"):
        editor = os.environ["EDITOR"].split()

    else:
        editor = ["notepad"] if os.name == "nt" else ["nvim"]

    subprocess.run(editor + [path])

def init_ptos():

    print("\nInitializing PTOS...\n")

    os.makedirs(CONFIG_DIR, exist_ok=True)
    os.makedirs(RECORDS_DIR, exist_ok=True)
    os.makedirs(JOURNAL_DIR, exist_ok=True)

    os.makedirs(os.path.join(BASE_DIR, "templates"), exist_ok=True)

    copy_if_missing(
        os.path.join(TEMPLATE_DIR, "schema.toml"),
        SCHEMA_PATH
    )

    copy_if_missing(
        os.path.join(TEMPLATE_DIR, "queries.toml"),
        QUERIES_PATH
    )

    copy_if_missing(
        os.path.join(TEMPLATE_DIR, "config.toml"),
        CONFIG_PATH
    )

    copy_if_missing(
        os.path.join(TEMPLATE_DIR, "presets.toml"),
        os.path.join(CONFIG_DIR, "presets.toml")
    )

    copy_if_missing(
        os.path.join(TEMPLATE_DIR, "daily.md"),
        os.path.join(BASE_DIR, "templates", "daily.md")
    )

    year = dt.date.today().year
    year_log = os.path.join(RECORDS_DIR, f"{year}.log")

    if not os.path.exists(year_log):

        open(year_log, "a").close()

        print(f"Created: {year_log}")

    else:

        print(f"Exists: {year_log}")

    print("\nPTOS initialization complete.\n")

def copy_if_missing(src, dst):

    if os.path.exists(dst):
        print(f"Exists: {dst}")
        return

    shutil.copy(src, dst)

    print(f"Created: {dst}")

def get_script_path():
    return os.path.abspath(sys.argv[0])

# --------------------------------------------------
# Schema Helpers
# --------------------------------------------------

_SCHEMA = None
_NUMERIC_FIELDS = None


def get_schema():
    global _SCHEMA
    if _SCHEMA is None:
        _SCHEMA = load_toml(SCHEMA_PATH)
    return _SCHEMA


def numeric_fields():

    global _NUMERIC_FIELDS

    if _NUMERIC_FIELDS is not None:
        return _NUMERIC_FIELDS

    schema = get_schema()

    nums = []

    for field, meta in schema.get("fields", {}).items():

        if isinstance(meta, dict) and meta.get("type") == "int":
            nums.append(field)

    _NUMERIC_FIELDS = nums

    return _NUMERIC_FIELDS

def numeric_value(kv):

    for f in numeric_fields():
        if f in kv:
            v = kv[f]

            if isinstance(v, list):
                v = v[0]

            if str(v).isdigit():
                return int(v)

    return None

def detect_value_field(results):

    for line in results:

        _, kv, _ = parse_line(line)

        for f in numeric_fields():
            if f in kv:
                return f

    return None

# --------------------------------------------------
# Schema Interpreter
# --------------------------------------------------

def resolve_field(schema, type_schema, field, record):

    if field in schema.get("fields", {}) and schema["fields"][field] == "int":
        return input_int(f"Enter {field}")

    allowed = type_schema.get("allowed", {})

    if field in allowed:
        return choose_from_list(f"Select {field}:", allowed[field]["values"])

    domains = type_schema.get("domains", {})

    if field == "domain" and domains:
        return choose_from_list("Select domain:", list(domains.keys()))

    if field == "category" and domains:
        domain = record.get("domain")
        return choose_from_list("Select category:", domains[domain]["categories"])

    return input_text(f"Enter {field}")

def resolve_tags(type_schema, record):

    allowed_tags = set()

    domains = type_schema.get("domains", {})
    tag_section = type_schema.get("tags", {})

    if "domain" in record and "category" in record:
        domain = record["domain"]
        category = record["category"]

        domain_tags = domains.get(domain, {}).get("tags", {})
        if category in domain_tags:
            allowed_tags.update(domain_tags[category]["values"])

    for value in record.values():

        if isinstance(value, list):
            values = value
        else:
            values = [value]

        for v in values:
            if v in tag_section:
                allowed_tags.update(tag_section[v]["values"])

    return sorted(allowed_tags)

# --------------------------------------------------
# Time Engine
# --------------------------------------------------
def month_range(year, month):

    start = dt.date(year, month, 1)

    if month == 12:
        end = dt.date(year + 1, 1, 1) - dt.timedelta(days=1)
    else:
        end = dt.date(year, month + 1, 1) - dt.timedelta(days=1)

    return start, end

def quarter_range(year, quarter):

    start_month = quarter * 3 + 1
    start = dt.date(year, start_month, 1)

    if start_month + 3 > 12:
        end = dt.date(year + 1, 1, 1) - dt.timedelta(days=1)
    else:
        end = dt.date(year, start_month + 3, 1) - dt.timedelta(days=1)

    return start, end

def resolve_cycle(start_day, offset=0):

    now = today()

    if now.day >= start_day:
        start = dt.date(now.year, now.month, start_day)
    else:
        prev = now.replace(day=1) - dt.timedelta(days=1)
        start = dt.date(prev.year, prev.month, start_day)

    for _ in range(offset):
        prev = start.replace(day=1) - dt.timedelta(days=1)
        start = dt.date(prev.year, prev.month, start_day)

    next_month = start.replace(day=28) + dt.timedelta(days=4)
    next_month = next_month.replace(day=1)

    end = next_month + dt.timedelta(days=start_day - 1) - dt.timedelta(days=1)

    return start, end

def resolve_time(keyword,cycles):

    now = today()

    # -----------------------------
    # dynamic cycles from config
    # -----------------------------
    for name, start_day in cycles.items():

        m = re.fullmatch(rf"{name}(?:-(\d+))?", keyword)

        if m:
            offset = int(m.group(1)) if m.group(1) else 0
            return resolve_cycle(start_day, offset)

    # -----------------------------
    # YYYY-MM
    # -----------------------------
    if re.fullmatch(r"\d{4}-\d{2}", keyword):

        year, month = map(int, keyword.split("-"))
        return month_range(year, month)

    # -----------------------------
    # day presets
    # -----------------------------
    if keyword == "today":
        return now, now

    if keyword == "yesterday":
        y = now - dt.timedelta(days=1)
        return y, y

    # -----------------------------
    # weeks
    # -----------------------------
    if keyword == "this-week":

        start = now - dt.timedelta(days=now.weekday())
        return start, start + dt.timedelta(days=6)

    if keyword == "last-week":

        end = now - dt.timedelta(days=now.weekday() + 1)
        return end - dt.timedelta(days=6), end

    # -----------------------------
    # months
    # -----------------------------
    if keyword == "this-month":
        return month_range(now.year, now.month)

    if keyword == "last-month":

        prev = now.replace(day=1) - dt.timedelta(days=1)
        return month_range(prev.year, prev.month)

    # -----------------------------
    # quarters
    # -----------------------------
    if keyword == "this-quarter":

        q = (now.month - 1) // 3
        return quarter_range(now.year, q)

    if keyword == "last-quarter":

        q = (now.month - 1) // 3 - 1
        year = now.year

        if q < 0:
            q = 3
            year -= 1

        return quarter_range(year, q)

    # -----------------------------
    # years
    # -----------------------------
    if keyword == "this-year":
        return dt.date(now.year, 1, 1), dt.date(now.year, 12, 31)

    if keyword == "last-year":
        return dt.date(now.year - 1, 1, 1), dt.date(now.year - 1, 12, 31)

    # -----------------------------
    # everything
    # -----------------------------
    if keyword == "all":
        return dt.date.min, dt.date.max

    raise ValueError("Invalid time keyword")

# --------------------------------------------------
# Interactive Helpers
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

        if val == "":
            return default

        try:
            parse_date(val)
            return val
        except ValueError:
            print("Invalid date format (YYYY-MM-DD)")

def input_tags(allowed_tags):

    tags = []

    while True:

        print("\nTag options:")

        options = {}

        remaining = [t for t in allowed_tags if t not in tags]

        for i, t in enumerate(remaining, 1):
            print(f"{i}) {t}")
            options[i] = t

        print(f"{len(options)+1}) Custom")
        print(f"{len(options)+2}) Done")

        val = input("Enter number or tags: ").strip()

        # finish
        if val == "" or val.lower() in ("done", "d"):
            break

        # numeric selection
        if val.isdigit():

            i = int(val)

            if i in options:
                tags.append(options[i])
                continue

            if i == len(options)+1:
                tag = input_text("Enter custom tag")
                if tag not in tags:
                    tags.append(tag)
                continue

            if i == len(options)+2:
                break

        # free text tags (comma separated)
        parts = [p.strip() for p in val.split(",")]

        for p in parts:

            tag = p.replace(" ", "_")

            if tag and tag not in tags:
                tags.append(tag)

    return tags

# --------------------------------------------------
# Record Helpers
# --------------------------------------------------

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

def append_record(line):

    ensure_dirs()

    year = line[:4]
    path = os.path.join(RECORDS_DIR, f"{year}.log")

    with open(path, "a") as f:
        f.write(line + "\n")

# --------------------------------------------------
# Parsing
# --------------------------------------------------

def parse_line(line):

    if "|" in line:
        main, note = line.split("|", 1)
    else:
        main, note = line, ""

    parts = main.strip().split()
    date = parts[0]
    kv = {}

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

def apply_where(kv, filters):

    ops = {
        "=": lambda a,b: a == b,
        "!=": lambda a,b: a != b,
        ">": lambda a,b: a > b,
        "<": lambda a,b: a < b,
        ">=": lambda a,b: a >= b,
        "<=": lambda a,b: a <= b,
    }

    for cond in filters:

        m = re.match(r"(\w+)(!=|>=|<=|=|>|<)(.+)", cond)
        if not m:
            continue

        key, op, val = m.groups()

        if key not in kv:
            return False

        cur = kv[key]

        if isinstance(cur, list):
            if op == "=" and val not in cur:
                return False
            if op == "!=" and val in cur:
                return False
            if op not in ("=","!="):
                return False
            continue

        if key in numeric_fields() and str(cur).isdigit():
            cur = int(cur)
            val = int(val)

        if op not in ops or not ops[op](cur,val):
            return False

    return True

# --------------------------------------------------
# Query Engine
# --------------------------------------------------

def scan_records(start, end, filters, search):

    results = []
    total = 0

    ensure_dirs()

    for fname in os.listdir(RECORDS_DIR):

        if not fname.endswith(".log"):
            continue

        path = os.path.join(RECORDS_DIR, fname)

        with open(path) as f:
            for line in f:

                d, kv, note = parse_line(line)

                if not (start <= d <= end):
                    continue

                if search and search.lower() not in line.lower():
                    continue

                if not apply_where(kv, filters):
                    continue

                results.append(line.strip())

                val = numeric_value(kv)
                if val is not None:
                    total += val

    return results, total

# --------------------------------------------------
# Summary Engine
# --------------------------------------------------

def build_summary(results, start, end, args, filters, total, first_date, last_date):

    summary = []

    count = len(results)

    summary.append(("Time range", f"{start} to {end} ({args.time})"))

    if first_date and last_date:
        summary.append(("Data span", f"{first_date} to {last_date}"))

    summary.append(("Records", count))

    if filters:
        summary.append(("Filters", " ".join(filters)))

    if total > 0:

        summary.append(("Total amount", f"₹{total}"))

        avg = total / count if count else 0
        summary.append(("Average amount", f"₹{avg:.0f}"))

    return summary


def print_context_summary(summary):

    if not summary:
        return

    line = "-" * 50

    print()
    print(line)

    width = max(len(label) for label, _ in summary)

    for label, value in summary:
        print(f"{label:<{width}} : {value}")

    print(line)

# --------------------------------------------------
# Grouping
# --------------------------------------------------

def group_results(results, fields):

    counts = {}
    sums = {}
    has_amount = False

    for record in results:

        d, kv, _ = parse_line(record)

        key_parts = []

        for field in fields:

            if field == "month":
                key_parts.append(d.strftime("%Y-%m"))

            elif field == "year":
                key_parts.append(str(d.year))

            else:
                key_parts.append(str(kv.get(field, "-")))

        key = tuple(key_parts)

        amount = numeric_value(kv)

        counts[key] = counts.get(key, 0) + 1

        if amount is not None:
            sums[key] = sums.get(key, 0) + amount
            has_amount = True

    return counts, sums, has_amount

# --------------------------------------------------
# Pivoting
# --------------------------------------------------

def pivot_results(results, row_field, col_field, count_mode=False, sort_field=None):

    table = {}
    cols = set()

    for line in results:

        d, kv, note = parse_line(line)

        # resolve row values
        if row_field == "month":
            row_vals = [d.strftime("%Y-%m")]
        elif row_field == "year":
            row_vals = [str(d.year)]
        elif row_field in kv:
            row_vals = kv[row_field] if isinstance(kv[row_field], list) else [kv[row_field]]
        else:
            continue

        # resolve column values
        if col_field == "month":
            col_vals = [d.strftime("%Y-%m")]
        elif col_field == "year":
            col_vals = [str(d.year)]
        elif col_field in kv:
            col_vals = kv[col_field] if isinstance(kv[col_field], list) else [kv[col_field]]
        else:
            continue

        amount = numeric_value(kv)

        for row in row_vals:
            for col in col_vals:

                cols.add(col)

                if row not in table:
                    table[row] = {}

                table[row][col] = table[row].get(col, 0)

                if count_mode:
                    table[row][col] += 1

                else:
                    if amount is not None:
                        try:
                            table[row][col] += int(amount)
                        except ValueError:
                            table[row][col] += 1
                    else:
                        table[row][col] += 1

    cols = sorted(cols)

    # -------------------------
    # Row totals
    # -------------------------

    row_totals = {
        row: sum(table[row].get(c, 0) for c in cols)
        for row in table
    }

    # -------------------------
    # Row sorting
    # -------------------------

    if sort_field and sort_field in cols:

        rows_sorted = sorted(
            table,
            key=lambda r: table[r].get(sort_field, 0),
            reverse=True
        )

    else:

        rows_sorted = sorted(
            row_totals,
            key=row_totals.get,
            reverse=True
        )

    # -------------------------
    # Totals
    # -------------------------

    col_totals = {c: 0 for c in cols}
    grand_total = 0

    width = 12

    print()

    header = f"{row_field:15}"
    for c in cols:
        header += f"{c:>{width}}"
    header += f"{'Total':>{width}}"

    print(header)
    print("-" * len(header))

    # -------------------------
    # Table rows
    # -------------------------

    for row in rows_sorted:

        line = f"{row:15}"
        row_total = 0

        for c in cols:

            val = table[row].get(c, 0)

            line += f"{val:>{width}}"

            row_total += val
            col_totals[c] += val

        line += f"{row_total:>{width}}"

        grand_total += row_total

        print(line)

    print("-" * len(header))

    # -------------------------
    # Column totals
    # -------------------------

    total_line = f"{'Total':15}"

    for c in cols:
        total_line += f"{col_totals[c]:>{width}}"

    total_line += f"{grand_total:>{width}}"

    print(total_line)
    print()

def show_fields(results):

    types = {}
    max_examples = 5

    for line in results:

        d, kv, note = parse_line(line)

        rtype = kv.get("type", "unknown")

        if rtype not in types:
            types[rtype] = {"fields": {}, "counts": {}}

        for k, v in kv.items():

            if k not in types[rtype]["fields"]:
                types[rtype]["fields"][k] = set()
                types[rtype]["counts"][k] = 0

            types[rtype]["counts"][k] += 1

            if isinstance(v, list):
                for item in v:
                    if len(types[rtype]["fields"][k]) < max_examples:
                        types[rtype]["fields"][k].add(str(item))
            else:
                if len(types[rtype]["fields"][k]) < max_examples:
                    types[rtype]["fields"][k].add(str(v))

    bad_fields = {"client","name","amount","advance","balance"}

    suggested_groups = []
    suggested_pivots = []

    print("\nFields by record type\n")

    for rtype in sorted(types):

        print(f"[{rtype}]\n")

        fields = types[rtype]["fields"]
        counts = types[rtype]["counts"]

        good_fields = []

        for field in sorted(fields):

            examples = ", ".join(sorted(fields[field]))

            unique_vals = len(fields[field])
            total = counts[field]

            ratio = unique_vals / total if total else 1

            good_dimension = (
                field not in bad_fields
                and not field.endswith("_id")
                and ratio < 0.4
            )

            star = "★ " if good_dimension else "  "

            if good_dimension:
                good_fields.append(field)

            print(f"{star}{field:12} {examples}")

        print()

        # group suggestions
        for field in good_fields[:3]:
            suggested_groups.append(f"ptos -y {rtype} -G {field}")

        # pivot suggestions
        pairs = [
            ("source","outcome"),
            ("category","tag"),
            ("model","source"),
            ("provider","instrument"),
            ("domain","category"),
            ("booked_by","outcome"),
        ]

        for a,b in pairs:
            if a in good_fields and b in good_fields:
                suggested_pivots.append(f"ptos -y {rtype} -v {a} {b}")

    print("★ recommended pivot/group fields\n")

    if suggested_groups:

        print("Suggested group commands\n")

        for cmd in suggested_groups[:6]:
            print(cmd)

        print()

    if suggested_pivots:

        print("Suggested pivot commands\n")

        for cmd in suggested_pivots:
            print(cmd)

        print()


# --------------------------------------------------
# Interactive Add
# --------------------------------------------------
def complete_record(schema, record):

    rtype = record.get("type")

    if not rtype:
        rtype = choose_from_list("Select type:", schema["types"]["allowed"])
        record["type"] = rtype

    type_schema = schema["type"][rtype]

    required = type_schema["required"]["fields"]

    # ask for missing required fields
    for field in required:

        if field not in record:
            record[field] = resolve_field(schema, type_schema, field, record)

    # resolve tags
    allowed_tags = resolve_tags(type_schema, record)

    if "tag" not in record:

        tags = input_tags(allowed_tags)

        if tags:
            record["tag"] = tags

    note = input("\nAdd note (optional): ").strip()

    return record, note

def interactive_add(schema):

    record = {}

    rtype = choose_from_list("Select type:", schema["types"]["allowed"])
    record["type"] = rtype

    type_schema = schema["type"][rtype]
    required = type_schema["required"]["fields"]

    for field in required:
        record[field] = resolve_field(schema, type_schema, field, record)

    allowed_tags = resolve_tags(type_schema, record)

    tags = input_tags(allowed_tags)
    
    if tags:
        record["tag"] = tags

    note = input("\nAdd note (optional): ").strip()

    problems = validate_record(schema, record)

    if problems:
        sys.exit(problems[0])

    date = input_date()
    line = build_record_line(date, record, note)

    print("\nRecord preview:\n")
    print(line)

    if input("\nSave? (y/n): ").lower() != "y":
        return

    append_record(line)

    print("Record added.")

def quick_add(args):

    presets = load_presets()

    if not args.preset:

        print("\nAvailable presets:\n")

        for name in sorted(presets):
            print(" ", name)

        print()
        return

    name = args.preset[0]

    if name not in presets:
        print(f"Unknown preset: {name}")
        return

    # start with preset values
    record = dict(presets[name])

    # apply CLI overrides
    for item in args.preset[1:]:

        if "=" not in item:
            continue

        k, v = item.split("=", 1)

        if k == "tag":
            record.setdefault("tag", [])
            record["tag"].append(v)
        else:
            record[k] = v

    schema = load_toml(SCHEMA_PATH)

    # fill missing fields interactively
    record, note = complete_record(schema, record)

    problems = validate_record(schema, record)

    if problems:
        sys.exit(problems[0])

    date = today().isoformat()

    line = build_record_line(date, record, note)

    append_record(line)

    print("\nRecord added:\n")
    print(line)

# --------------------------------------------------
# Validation
# --------------------------------------------------

def validate_record(schema, record):

    problems = []

    rtype = record.get("type")

    # -------------------------
    # Type validation
    # -------------------------

    if rtype not in schema["types"]["allowed"]:
        problems.append(f"Invalid type '{rtype}'")
        return problems

    type_schema = schema["type"][rtype]

    # -------------------------
    # Required fields
    # -------------------------

    required = type_schema.get("required", {}).get("fields", [])

    for f in required:
        if f not in record:
            problems.append(f"Missing required field: {f}")

    # -------------------------
    # Integer validation (schema driven)
    # -------------------------

    for field, meta in schema.get("fields", {}).items():

        if isinstance(meta, dict) and meta.get("type") == "int" and field in record:

            if not str(record[field]).isdigit():
                problems.append(f"Field '{field}' must be integer")

    # -------------------------
    # Unknown field detection
    # -------------------------

    allowed_fields = {"type"}

    allowed_fields.update(schema.get("fields", {}).keys())

    allowed_fields.update(
        type_schema.get("required", {}).get("fields", [])
    )

    allowed_fields.update(
        type_schema.get("allowed", {}).keys()
    )

    # add hierarchy fields if defined
    hierarchy = type_schema.get("hierarchy", {})
    allowed_fields.update(hierarchy.get("levels", []))

    for field in record.keys():

        if field not in allowed_fields:
            problems.append(f"Unknown field '{field}'")

    # -------------------------
    # Hierarchy validation (generic)
    # -------------------------

    levels = type_schema.get("hierarchy", {}).get("levels", [])

    if levels:

        domains = type_schema.get("domains", {})
        current_schema = domains

        for i, field in enumerate(levels):

            value = record.get(field)

            if not value:
                break

            values = value if isinstance(value, list) else [value]

            for v in values:
                if v not in current_schema:
                    problems.append(f"Invalid {field} '{v}'")

            node = current_schema.get(values[0])

            if not node:
                break

            if i + 1 < len(levels):

                next_field = levels[i + 1]

                if next_field == "category":
                    current_schema = {c: {} for c in node.get("categories", [])}

                elif next_field == "tag":
                    current_schema = node.get("tags", {})    

    # -------------------------
    # Conditional required rules
    # -------------------------

    conditional = type_schema.get("conditional_required", {})

    for field, rule in conditional.items():

        condition = rule.get("when", {})

        match = True

        for k, v in condition.items():

            if record.get(k) != v:
                match = False
                break

        if match and field not in record:

            problems.append(
                f"Field '{field}' required when {condition}"
            )

    return problems

def lint_records(records, schema):

    errors = 0

    for line in records:

        date, kv, note = parse_line(line)

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
# Journal
# --------------------------------------------------

def get_today_journal():

    today_date = today().isoformat()
    year = today_date[:4]

    year_dir = os.path.join(JOURNAL_DIR, year)
    os.makedirs(year_dir, exist_ok=True)

    journal_file = os.path.join(year_dir, f"{today_date}.md")

    if not os.path.exists(journal_file):

        template_path = os.path.join(BASE_DIR, "templates", "daily.md")

        if os.path.exists(template_path):

            with open(template_path, "r", encoding="utf-8") as f:
                template = f.read()

            template = template.replace("{{date}}", today_date)

            with open(journal_file, "w", encoding="utf-8") as f:
                f.write(template)

        else:
            open(journal_file, "a").close()

    return journal_file

def open_journal():
    edit_target("daily")

def load_presets():

    path = os.path.join(CONFIG_DIR, "presets.toml")

    if not os.path.exists(path):
        return {}

    with open(path, "rb") as f:
        data = tomllib.load(f)

    return data.get("presets", {})

# --------------------------------------------------
# Metrics + Dashboards
# --------------------------------------------------

def run_named_query(name, queries, start, end):

    q = queries[name]
    filters = q["where"].split()

    results, total = scan_records(start, end, filters, None)

    return len(results), total


def run_metric(name, queries, start, end):

    metrics = queries.get("metrics", {})

    if name not in metrics:
        return False
    
    m = metrics[name]

    # -------- ratio --------
    if "ratio" in m:

        q1, q2 = m["ratio"]

        c1, _ = run_named_query(q1, queries, start, end)
        c2, _ = run_named_query(q2, queries, start, end)

        if c2 == 0:
            print(f"{name:<20} no data in time range")
            return True

        val = (c1 / c2) * 100

        print(f"{name:<20} {val:.1f}% ({c1}/{c2})")

        return True

    # -------- average --------
    if "avg" in m:

        q = m["avg"]

        count, total = run_named_query(q, queries, start, end)

        if count == 0:
            print(f"{name:<20} no data")
            return True

        val = total / count

        print(f"{name:<20} ₹{val:.0f}")

        return True

    return False


def run_dashboard(name, queries, start, end):

    dashboards = queries.get("dashboards", {})

    if name not in dashboards:
        return False

    print(f"\nDashboard: {name}")
    print(f"Time range: {start} to {end}")
    print("-" * 40)

    items = dashboards[name].get("metrics", [])

    for item in items:

        # metric
        if run_metric(item, queries, start, end):
            continue

        # simple query count
        if item in queries:

            count, total = run_named_query(item, queries, start, end)

            if total > 0:
                print(f"{item:<20} {count}  (₹{total})")
            else:
                print(f"{item:<20} {count}")

    print()

    return True

# --------------------------------------------------
# Main
# --------------------------------------------------

def main():

    config = load_toml(CONFIG_PATH) if os.path.exists(CONFIG_PATH) else {}

    CYCLES = config.get("cycles", {})

    if CYCLES:
        cycle_examples = ", ".join(
            f"{name}, {name}-1, {name}-2"
            for name in CYCLES.keys()
        )
    else:
        cycle_examples = "custom cycles from config.toml"

    parser = argparse.ArgumentParser(
        prog="ptos",
        description="""
    PTOS – Plain Text Operating System

    Record and analyze life, work, and finance events using
    structured plain-text logs. 
    
    PTOS treats logs as structured data: 
    fields become dimensions, 
    and numeric fields become measures.
    """,
        epilog="""
        Examples:

          # Add expense
          ptos -a type=expense domain=self category=food amount=50

          # Run saved query
          ptos -q snacks

          # Group results
          ptos -q work --group category

          # Search records
          ptos -S courier

          # Calendar month
          ptos -t 2026-03

          # Clinic cycle
          ptos -t clinic
          ptos -t clinic-1

          # Date range
          ptos -f 2026-01-01 -T 2026-01-31

          # Pivot analysis
          ptos -y expense -v domain category

        Aggregation rule:
          Group and pivot operations automatically aggregate the first numeric
          field found in a record. Numeric fields are defined in schema.toml
          using type = "int".
        """,
        formatter_class=argparse.RawTextHelpFormatter
    )


    # -------------------------
    # GROUPS
    # -------------------------

    add_group = parser.add_argument_group("Add Records")
    query_group = parser.add_argument_group("Query Records")
    analysis_group = parser.add_argument_group("Analyze Results")
    util_group = parser.add_argument_group("Utilities")


    # -------------------------
    # ADD RECORDS
    # -------------------------

    add_group.add_argument(
        "-a", "--add",
        nargs="*",
        help="Add a new record using key=value pairs or run interactive entry."
    )

    add_group.add_argument(
        "-n", "--note",
        help="Optional note attached to the record."
    )

    add_group.add_argument(
        "-p", "--preset",
        nargs="*",
        help="Quick add using preset (e.g. ptos -p commute amount=120)"
    )


    # -------------------------
    # QUERY RECORDS
    # -------------------------

    query_group.add_argument(
        "-w", "--where",
        nargs="+",
        action="append",
        help="Filter expressions (example: -w type=expense domain=self)"
    )

    query_group.add_argument(
        "-q", "--query",
        nargs="?",
        const="__LIST__",
        help="Run saved query or list queries if no name is given."
    )

    query_group.add_argument(
        "-t", "--time",
        default="this-month",
        help=(
            "Time preset.\n"
            "Examples:\n"
            "  today, yesterday\n"
            "  this-week, last-week\n"
            "  this-month, last-month\n"
            "  YYYY-MM (example: 2026-03)\n"
            f"  {cycle_examples} (cycle defined in config.toml)"
        )
    )

    query_group.add_argument(
        "-f", "--from",
        dest="date_from",
        help="Start date filter (YYYY-MM-DD)."
    )

    query_group.add_argument(
        "-T", "--to",
        dest="date_to",
        help="End date filter (YYYY-MM-DD)."
    )

    query_group.add_argument(
        "-y", "--type",
        help="Filter by record type."
    )

    query_group.add_argument(
        "-g", "--tag",
        action="append",
        help="Filter by tag (can be used multiple times)."
    )

    query_group.add_argument(
        "-S", "--search",
        help="Search text inside records."
    )


    # -------------------------
    # ANALYSIS
    # -------------------------

    analysis_group.add_argument(
        "-G", "--group",
        nargs="+",
        help="Group results by one or more fields (category, tag, source, etc)."
    )

    analysis_group.add_argument(
        "-v", "--pivot",
        nargs="+",
        metavar=("ROW", "COL"),
        help="Pivot table (example: -v source outcome)"
    )

    analysis_group.add_argument(
        "--count",
        action="store_true",
        help="Use record count instead of first numeric field in pivot."
    )

    analysis_group.add_argument(
        "--sort",
        help="Sort pivot rows by column name or 'total'."
    )


    # -------------------------
    # UTILITIES
    # -------------------------

    util_group.add_argument(
        "-l", "--lint",
        action="store_true",
        help="Validate records against schema.toml."
    )

    util_group.add_argument(
        "-j", "--journal",
        action="store_true",
        help="Open today's journal in Neovim."
    )

    util_group.add_argument(
        "-e", "--edit",
        nargs="?",
        const="records",
        metavar="TARGET",
        help=(
            "Edit workspace files.\n"
            "Targets:\n"
            "  r,records   records log (default)\n"
            "  s,schema    schema.toml\n"
            "  q,queries   queries.toml\n"
            "  c,config    config.toml\n"
            "  p,presets   presets.toml\n"
            "  d,daily     today's journal\n"
            "  x,script    ptos.py"
        )
    )

    util_group.add_argument(
        "--fields",
        action="store_true",
        help="Show available fields and system configuration (including time cycles)."
    )

    util_group.add_argument(
        "--init",
        action="store_true",
        help="Initialize PTOS directory structure and starter configuration."
    )
    
    args = parser.parse_args()

    if args.init:
        init_ptos()
        return
    if args.edit:

        edit_target(args.edit)
        return

    if args.preset is not None:
        quick_add(args)
        return

    # Flatten where filters
    if args.where:
        args.where = [item for sublist in args.where for item in sublist]
    else:
        args.where = []

    schema = load_toml(SCHEMA_PATH)

    # -------------------------
    # JOURNAL MODE
    # -------------------------

    if args.journal:
        open_journal()
        return

    # -------------------------
    # ADD MODE
    # -------------------------
    if args.add is not None:

        if len(args.add) == 0:
            interactive_add(schema)
            return

        record = {}

        for item in args.add:
            k, v = item.split("=", 1)

            if k in record:
                if isinstance(record[k], list):
                    record[k].append(v)
                else:
                    record[k] = [record[k], v]
            else:
                record[k] = v

        problems = validate_record(schema, record)

        if problems:
            sys.exit(problems[0])

        line = build_record_line(today().isoformat(), record, args.note)

        append_record(line)

        print("Record added.")
        return

    # -------------------------
    # LINT MODE
    # -------------------------

    if args.lint:

        start = dt.date.min
        end = dt.date.max

        results, _ = scan_records(start, end, [], None)

        lint_records(results,schema)
        return

    # -------------------------
    # BUILD FILTERS
    # -------------------------
    filters = []
    query_filters = []

    # -------------------------
    # NAMED QUERY
    # -------------------------
    if args.query is not None:

        queries = load_toml(QUERIES_PATH)

        metrics = queries.get("metrics", {})
        dashboards = queries.get("dashboards", {})

        # -------------------------
        # LIST
        # -------------------------
        if args.query == "__LIST__":

            print("\nQueries\n")

            for name in queries:
                if name not in ("metrics", "dashboards"):
                    print(" ", name)

            if metrics:
                print("\nMetrics\n")
                for name in metrics:
                    print(" ", name)

            if dashboards:
                print("\nDashboards\n")
                for name in dashboards:
                    print(" ", name)

            print()
            return

        # -------------------------
        # METRIC
        # -------------------------
        if args.query in metrics:
            metric_mode = True
        else:
            metric_mode = False

        # -------------------------
        # DASHBOARD
        # -------------------------
        if args.query in dashboards:
            dashboard_mode = True
        else:
            dashboard_mode = False

        # -------------------------
        # QUERY
        # -------------------------
        q = queries.get(args.query)

        if not (metric_mode or dashboard_mode or q):
            sys.exit("Query not found.")

        if q:
            query_filters = q["where"].split()

            if (
                args.date_from is None
                and args.date_to is None
                and args.time == "this-month"
            ):
                if "from" in q:
                    args.date_from = q["from"]

                if "to" in q:
                    args.date_to = q["to"]

                if "time" in q:
                    args.time = q["time"]

            if q.get("sum"):
                args.sum = True

            if "group" in q:
                args.group = q["group"]

            if "pivot" in q:
                args.pivot = q["pivot"]

            if q.get("count"):
                args.count = True

            if "sort" in q:
                args.sort = q["sort"]

    # -------------------------
    # APPLY FILTER PRIORITY
    # -------------------------

    # Start with query filters
    filters = query_filters.copy()

    # CLI --where overrides query filters
    if args.where:
        filters = args.where

    # CLI modifiers
    if args.type:
        filters.append(f"type={args.type}")

    if args.tag:
        filters.extend(f"tag={t}" for t in args.tag)

    # -------------------------
    # TIME RESOLUTION
    # -------------------------

    if args.date_from or args.date_to:
        if args.date_from:
            start = args.date_from if isinstance(args.date_from, dt.date) else dt.date.fromisoformat(args.date_from)
        else:
            start = dt.date.min

        if args.date_to:
            end = args.date_to if isinstance(args.date_to, dt.date) else dt.date.fromisoformat(args.date_to)
        else:
            end = dt.date.max
    else:
        start, end = resolve_time(args.time,CYCLES)

    # -------------------------
    # RUN QUERY
    # -------------------------

    results, total = scan_records(start, end, filters, args.search)

    if not results:
        print("\nNo records found.\n")
        return

    # -------------------------
    # DATA SPAN
    # -------------------------

    first_date = None
    last_date = None

    if results:

        first_date = results[0].split()[0]
        last_date = results[-1].split()[0]

    summary = build_summary(
        results,
        start,
        end,
        args,
        filters,
        total,
        first_date,
        last_date
    )

    # -------------------------
    # METRICS / DASHBOARDS
    # -------------------------

    if args.query and metric_mode:
        run_metric(args.query, queries, start, end)
        return

    if args.query and dashboard_mode:
        run_dashboard(args.query, queries, start, end)
        return

    # -------------------------
    # DISCOVERY
    # -------------------------

    if args.fields:
        show_fields(results)
        return

    if args.group == "?":

        dims = set()

        for line in results:
            _, kv, _ = parse_line(line)

            for k in kv:
                if k not in numeric_fields():
                    dims.add(k)

        print("\nAvailable group fields:\n")

        for d in sorted(dims):
            print(d)

        print()

        return


    if args.pivot:

        if args.pivot[0] == "?":
            # discovery mode
            dims = set()

            for line in results:
                _, kv, _ = parse_line(line)

                for k in kv:
                    if k not in {"client","name","amount","advance","balance"}:
                        dims.add(k)

            print("\nAvailable pivot fields:\n")

            for d in sorted(dims):
                print(d)

            print()
            return

        if len(args.pivot) < 2:
            print("Pivot requires two fields: ptos -v row col")
            return

    # -------------------------
    # PIVOT MODE
    # -------------------------

    if args.pivot:

        if len(args.pivot) < 2:
            print("Pivot requires two fields: ptos -v row col")
            return

        available = set()
        row, col = args.pivot[:2]

        for line in results:
            _, kv, _ = parse_line(line)
            available.update(kv.keys())

        # derived time fields
        available.update({"month", "year"})

        missing = [f for f in (row, col) if f not in available]

        if missing:
            print("\nInvalid pivot field(s):", ", ".join(missing))
            print("\nUse --fields to discover available fields:\n")
            print("  ptos --fields\n")
            return

      
        print_context_summary(summary)
        
        value_field = detect_value_field(results)
        
        if value_field and not args.count:
            print(f"\nPivot rows: {row}   columns: {col}   Value: {value_field}\n")
        else:
            print(f"\nPivot rows: {row}   columns: {col}\n")
        
        pivot_results(results, row, col, args.count, args.sort)

        return

    # -------------------------
    # GROUP MODE
    # -------------------------

    if args.group:

        print_context_summary(summary)
        
        counts, sums, has_amount = group_results(results, args.group)
        
        value_field = detect_value_field(results)
        
        group_label = " ".join(args.group)

        if value_field:
            print(f"\nGrouped by: {group_label}   Value: {value_field}\n")
        else:
            print(f"\nGrouped by: {group_label}\n")

        if has_amount:

            grand_total = 0

            for key in sorted(sums):

                val = sums[key]
                grand_total += val
                
                label = "  ".join(key) if isinstance(key, tuple) else key
                
                label = "  ".join(key) if isinstance(key, tuple) else key
                print(f"{label:<20} ₹{val}")

            print("-" * 40)
            print(f"{'Total':<20} ₹{grand_total}")

        else:

            grand_count = 0

            for key in sorted(counts):

                val = counts[key]
                grand_count += val

                label = "  ".join(key) if isinstance(key, tuple) else key
                
                label = "  ".join(key) if isinstance(key, tuple) else key
                print(f"{label:<20} ₹{val}")

            print("-" * 40)
            print(f"{'Total':<20} {grand_count}")

        return

    # -------------------------
    # DEFAULT RECORD LIST
    # -------------------------

    for line in results:
        print(line)

    print_context_summary(summary)

if __name__ == "__main__":
    main()
