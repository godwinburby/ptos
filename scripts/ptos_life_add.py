#!/usr/bin/env python3

import datetime
from pathlib import Path


# ----------------------------
# CONTROLLED VOCABULARY
# ----------------------------

TYPES = ["expense", "income"]

CATEGORIES = [
    "food",
    "transport",
    "medical",
    "utilities",
    "household",
    "education",
    "religious",
    "travel",
    "entertainment",
    "admin",
    "child",
    "investment",
    "income",
]

DOMAINS = ["home", "self", "work"]

DEFAULT_TAGS = [
    "snacks",
    "jayden",
    "maria",
    "mom",
    "auto",
    "bus",
    "taxi",
    "uber",
    "rapido",
    "fruits",
    "vegetables",
]


# ----------------------------
# HELPERS
# ----------------------------

def today_iso():
    return datetime.date.today().isoformat()


def validate_date(date_str):
    try:
        datetime.date.fromisoformat(date_str)
        return True
    except ValueError:
        return False


def validate_positive_int(label, value):
    try:
        num = int(value)
    except ValueError:
        raise ValueError(f"{label} must be whole number.")

    if num < 0:
        raise ValueError(f"{label} cannot be negative.")

    return num


def normalize_token(value):
    value = value.strip().lower()
    if not value:
        raise ValueError("Value cannot be empty.")
    return "_".join(value.split())


def select_from_list(label, options):
    while True:
        print(f"\n{label}:")
        for i, option in enumerate(options, 1):
            print(f"{i}) {option}")

        choice = input("> ").strip()

        if not choice.isdigit():
            print("Enter number only.")
            continue

        index = int(choice)
        if 1 <= index <= len(options):
            return options[index - 1]

        print("Invalid selection.")


def select_tags():
    while True:
        print("\nCommon Tags:")
        for i, tag in enumerate(DEFAULT_TAGS, 1):
            print(f"{i}) {tag}")
        print(f"{len(DEFAULT_TAGS)+1}) custom")
        print("Select numbers separated by comma (or press Enter to skip)")

        choice = input("> ").strip()

        if not choice:
            return []

        selected = []
        parts = [p.strip() for p in choice.split(",")]

        try:
            for part in parts:
                if not part.isdigit():
                    raise ValueError("Tag selection must be numeric.")

                index = int(part)

                if 1 <= index <= len(DEFAULT_TAGS):
                    selected.append(DEFAULT_TAGS[index - 1])
                elif index == len(DEFAULT_TAGS) + 1:
                    custom_input = input("Enter custom tags (comma separated): ")
                    custom_tags = [
                        normalize_token(t)
                        for t in custom_input.split(",")
                        if t.strip()
                    ]
                    selected.extend(custom_tags)
                else:
                    raise ValueError("Invalid tag selection.")

            return sorted(set(selected))

        except ValueError as e:
            print(e)


# ----------------------------
# MAIN
# ----------------------------

def main():
    print("PTOS Life Record Entry\n")

    # DATE
    while True:
        date_input = input(f"Date (YYYY-MM-DD) [default {today_iso()}]: ").strip()
        if not date_input:
            date_input = today_iso()

        if validate_date(date_input):
            break

        print("Invalid date format. Use YYYY-MM-DD.")

    record_type = select_from_list("Type", TYPES)
    category = select_from_list("Category", CATEGORIES)
    domain = select_from_list("Domain", DOMAINS)

    # AMOUNT
    while True:
        try:
            amount = validate_positive_int(
                "amount",
                input("\nAmount: ").strip()
            )
            break
        except ValueError as e:
            print(e)

    tags = select_tags()

    # NOTES
    while True:
        notes = input("\nNotes (optional): ").strip()
        if "|" in notes:
            print("Notes cannot contain '|' character.")
        else:
            break

    # ----------------------------
    # BUILD RECORD
    # ----------------------------

    parts = [
        date_input,
        f"type:{record_type}",
        f"amount:{amount}",
        f"category:{category}",
        f"domain:{domain}",
    ]

    for tag in tags:
        parts.append(f"tag:{tag}")

    record_line = " ".join(parts)

    if notes:
        record_line += f" | {notes}"

    # ----------------------------
    # WRITE TO ptos/records/YYYY.log
    # ----------------------------

    script_dir = Path(__file__).resolve().parent
    ptos_dir = script_dir.parent
    records_dir = ptos_dir / "records"
    records_dir.mkdir(parents=True, exist_ok=True)

    year = date_input[:4]
    filename = records_dir / f"{year}.log"

    if not filename.exists():
        filename.touch()

    with filename.open("rb+") as f:
        f.seek(0, 2)
        if f.tell() > 0:
            f.seek(-1, 2)
            if f.read(1) != b"\n":
                f.write(b"\n")

    with filename.open("a", encoding="utf-8") as f:
        f.write(record_line + "\n")

    print("\nRecord added successfully:")
    print(record_line)


if __name__ == "__main__":
    main()