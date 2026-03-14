import argparse
from collections import defaultdict
import datetime
import os
import calendar
import sys


# -----------------------------
# Utilities
# -----------------------------

def format_indian_number(n):
    s = str(abs(n))
    if len(s) <= 3:
        result = s
    else:
        last3 = s[-3:]
        rest = s[:-3]
        parts = []
        while len(rest) > 2:
            parts.insert(0, rest[-2:])
            rest = rest[:-2]
        if rest:
            parts.insert(0, rest)
        result = ",".join(parts) + "," + last3
    return "-" + result if n < 0 else result


# -----------------------------
# Record Parsing
# -----------------------------

def parse_line(line):
    if "|" in line:
        structured, note = line.split("|", 1)
        note = note.strip()
    else:
        structured = line
        note = ""

    parts = structured.strip().split()
    record = {"note": note, "tags": []}
    record["date"] = parts[0]

    for part in parts[1:]:
        if ":" in part:
            key, value = part.split(":", 1)
            if key == "tag":
                record["tags"].append(value)
            else:
                record[key] = value

    return record


def date_in_range(date, start, end):
    if start and date < start:
        return False
    if end and date > end:
        return False
    return True


# -----------------------------
# Time Resolution
# -----------------------------

def resolve_relative_month(offset=0):
    today = datetime.date.today()
    year = today.year
    month = today.month + offset

    while month <= 0:
        month += 12
        year -= 1
    while month > 12:
        month -= 12
        year += 1

    last_day = calendar.monthrange(year, month)[1]
    return f"{year:04d}-{month:02d}-01", f"{year:04d}-{month:02d}-{last_day}"


def resolve_explicit_month(month_str):
    year, month = map(int, month_str.split("-"))
    last_day = calendar.monthrange(year, month)[1]
    return f"{year:04d}-{month:02d}-01", f"{year:04d}-{month:02d}-{last_day}"


def resolve_explicit_quarter(q_str):
    year_str, q_part = q_str.split("-Q")
    year = int(year_str)
    quarter = int(q_part)

    start_month = (quarter - 1) * 3 + 1
    end_month = start_month + 2

    start = f"{year:04d}-{start_month:02d}-01"
    last_day = calendar.monthrange(year, end_month)[1]
    end = f"{year:04d}-{end_month:02d}-{last_day}"
    return start, end


def resolve_relative_quarter(offset=0):
    today = datetime.date.today()
    current_q = (today.month - 1) // 3 + 1
    year = today.year
    quarter = current_q + offset

    while quarter <= 0:
        quarter += 4
        year -= 1
    while quarter > 4:
        quarter -= 4
        year += 1

    return resolve_explicit_quarter(f"{year}-Q{quarter}")


# -----------------------------
# Profiles
# -----------------------------

def get_profiles(file_path):
    profiles = []
    if not os.path.exists(file_path):
        return profiles

    with open(file_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if ":" in line:
                profiles.append(line)
    return profiles


def list_profiles(file_path):
    profiles = get_profiles(file_path)

    if not profiles:
        print("No profiles found.")
        return

    print("Available Profiles")
    print("-" * 45)

    for idx, line in enumerate(profiles, start=1):
        name, command = line.split(":", 1)
        print(f"{idx}. {name.strip()}")
        print("   " + command.strip())
        print()


# -----------------------------
# Matching
# -----------------------------

def matches(record, args):

    if args.type and record.get("type") != args.type:
        return False

    if not date_in_range(record["date"], args.start, args.end):
        return False

    for condition in args.where:

        if "!=" in condition:
            key, value = condition.split("!=", 1)

            if key == "tag":
                if value in record.get("tags", []):
                    return False
            else:
                if record.get(key) == value:
                    return False

        elif "=" in condition:
            key, value = condition.split("=", 1)

            if key == "tag":
                if value not in record.get("tags", []):
                    return False
            else:
                if record.get(key) != value:
                    return False

    if args.tag and args.tag not in record.get("tags", []):
        return False

    if args.note and args.note.lower() not in record.get("note", "").lower():
        return False

    return True


# -----------------------------
# Header
# -----------------------------

def print_header(args, loaded_files, matched_count,
                 profile_name=None, profile_command=None):

    print("=" * 45)
    print("PTOS SUMMARY")

    if profile_name:
        print(f"Profile : {profile_name}")
        print(f"Command : {profile_command}")
        print()

    if args.start and args.end:
        print(f"Range   : {args.start} → {args.end}")

    if loaded_files:
        names = ", ".join(os.path.basename(f) for f in loaded_files)
        print(f"Files   : {names}")

    print()

    filter_lines = []

    if args.type:
        filter_lines.append(f"type   = {args.type}")

    for condition in args.where:
        if "!=" in condition:
            key, value = condition.split("!=", 1)
            filter_lines.append(f"{key} != {value}")
        elif "=" in condition:
            key, value = condition.split("=", 1)
            filter_lines.append(f"{key}  = {value}")

    if args.tag:
        filter_lines.append(f"tag    = {args.tag}")

    if args.note:
        filter_lines.append(f"note   contains '{args.note}'")

    if filter_lines:
        print("Filters :")
        for f in filter_lines:
            print(f"  {f}")
        print()

    if args.group:
        print(f"Group   : {args.group}")

    print(f"Records : {matched_count}")
    print("-" * 45)


# -----------------------------
# Main
# -----------------------------

def main():

    parser = argparse.ArgumentParser(
        prog="ptos.py",
        description="PTOS - Plain Text Operating System Query Tool"
    )

    parser.add_argument(
        "--profile",
        nargs="?",
        const="__LIST__",
        help="List profiles or run profile by number/name"
    )

    parser.add_argument("--month", help="YYYY-MM | current | last")
    parser.add_argument("--quarter", help="YYYY-Q# | current | last")
    parser.add_argument("--from", dest="start", help="Start date YYYY-MM-DD")
    parser.add_argument("--to", dest="end", help="End date YYYY-MM-DD")
    parser.add_argument("--type", help="Filter by record type")
    parser.add_argument("--tag", help="Filter by tag (legacy shortcut)")
    parser.add_argument("--note", help="Search text inside notes")
    parser.add_argument("--where", action="append", default=[], help="Key filter e.g. domain=work, tag!=snacks")
    parser.add_argument("--group", help="Group by key")
    parser.add_argument("--sum", action="store_true", help="Show sum of amount")
    parser.add_argument("--count", action="store_true", help="Show count of records")
    parser.add_argument("--show", action="store_true", help="Show matching records")

    if len(sys.argv) == 1:
        parser.print_help()
        return

    args = parser.parse_args()

    script_dir = os.path.dirname(os.path.abspath(__file__))
    root_dir = os.path.dirname(script_dir)
    records_dir = os.path.join(root_dir, "records")
    profiles_file = os.path.join(root_dir, "queries", "profiles.txt")

    profile_name = None
    profile_command = None

    if args.profile is not None:

        if args.profile == "__LIST__":
            list_profiles(profiles_file)
            return

        profiles = get_profiles(profiles_file)
        if not profiles:
            print("No profiles found.")
            return

        if args.profile.isdigit():
            idx = int(args.profile) - 1
            if 0 <= idx < len(profiles):
                line = profiles[idx]
            else:
                print("Invalid profile number.")
                return
        else:
            found = False
            for line in profiles:
                name, _ = line.split(":", 1)
                if name.strip() == args.profile:
                    found = True
                    break
            if not found:
                print("Profile not found.")
                return

        name, command = line.split(":", 1)
        profile_name = name.strip()
        profile_command = command.strip()

        profile_args = command.strip().split()
        user_args = [a for a in sys.argv[1:] if a not in ("--profile", args.profile)]
        final_args = profile_args + user_args
        args = parser.parse_args(final_args)

    if not (args.show or args.sum or args.count or args.group):
        args.show = True

    if args.month:
        if args.month == "current":
            args.start, args.end = resolve_relative_month(0)
        elif args.month == "last":
            args.start, args.end = resolve_relative_month(-1)
        else:
            args.start, args.end = resolve_explicit_month(args.month)

    elif args.quarter:
        if args.quarter == "current":
            args.start, args.end = resolve_relative_quarter(0)
        elif args.quarter == "last":
            args.start, args.end = resolve_relative_quarter(-1)
        else:
            args.start, args.end = resolve_explicit_quarter(args.quarter)

    if not args.start or not args.end:
        print("Error: A date range must be resolved.")
        return

    start_year = int(args.start[:4])
    end_year = int(args.end[:4])

    total = 0
    count = 0
    groups_sum = defaultdict(int)
    groups_count = defaultdict(int)
    matched_lines = []
    loaded_files = []

    for year in range(start_year, end_year + 1):
        file_path = os.path.join(records_dir, f"{year}.log")
        if not os.path.exists(file_path):
            continue

        loaded_files.append(file_path)

        with open(file_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue

                record = parse_line(line)

                if not matches(record, args):
                    continue

                matched_lines.append(line)
                count += 1
                amount = int(record.get("amount", 0))

                if args.group:
                    key = record.get(args.group, "unknown")
                    groups_sum[key] += amount
                    groups_count[key] += 1
                else:
                    total += amount

    if count == 0:
        print("No matching records.")
        return

    print_header(args, loaded_files, count, profile_name, profile_command)

    if args.show:
        for line in matched_lines:
            print(line)
        print("-" * 45)

    if args.group:
        for k in sorted(groups_sum.keys()):
            out = f"{k}:"
            if args.sum:
                out += f" sum={format_indian_number(groups_sum[k])}"
            if args.count:
                out += f" count={groups_count[k]}"
            print(out)
    else:
        if args.sum:
            print(f"Total: {format_indian_number(total)}")
        if args.count:
            print(f"Count: {count}")


if __name__ == "__main__":
    main()