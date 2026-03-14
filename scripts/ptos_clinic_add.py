#!/usr/bin/env python3

import datetime
from pathlib import Path


# ----------------------------
# CONTROLLED VOCABULARY
# ----------------------------

TYPES = ["assessment", "prescription", "fitting", "service"]

SOURCES = ["ent", "walkin", "raf", "outreach", "marketing", "gp", "camp"]

BOOKED_BY = ["cso", "cce", "cre","ent"]

ASSESSMENT_OUTCOMES = [
    "normal",
    "deferred",
    "prescribed_monaural",
    "prescribed_binaural",
]

PRESCRIPTION_OUTCOMES = [
    "prescribed_monaural",
    "prescribed_binaural",
]

SIDES = ["monaural", "binaural"]

WARRANTY = ["in", "out"]


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


def normalize_token(label, value):
    value = value.strip().lower()
    if not value:
        raise ValueError(f"{label} cannot be empty.")
    value = "_".join(value.split())
    return value


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


# ----------------------------
# MAIN
# ----------------------------

def main():
    print("PTOS Clinic Record Entry\n")

    # DATE
    while True:
        date_input = input(f"Date (YYYY-MM-DD) [default {today_iso()}]: ").strip()
        if not date_input:
            date_input = today_iso()

        if validate_date(date_input):
            break

        print("Invalid date format. Use YYYY-MM-DD.")

    record_type = select_from_list("Type", TYPES)

    parts = [
        date_input,
        f"type:{record_type}",
    ]

    # ----------------------------
    # TYPE BRANCHING
    # ----------------------------

    if record_type == "assessment":

        while True:
            try:
                name = normalize_token("name", input("\nName: "))
                break
            except ValueError as e:
                print(e)

        source = select_from_list("Source", SOURCES)
        outcome = select_from_list("Outcome", ASSESSMENT_OUTCOMES)
        booked_by = select_from_list("Booked By", BOOKED_BY)

        parts.extend([
            f"name:{name}",
            f"source:{source}",
            f"outcome:{outcome}",
            f"booked_by:{booked_by}",
            "category:patient",
            "domain:work",
        ])

    elif record_type == "prescription":

        while True:
            try:
                amount = validate_positive_int(
                    "amount", input("\nTotal Amount: ").strip()
                )
                break
            except ValueError as e:
                print(e)

        while True:
            try:
                advance = validate_positive_int(
                    "advance", input("Advance Received: ").strip()
                )
                if advance > amount:
                    raise ValueError("Advance cannot exceed total amount.")
                break
            except ValueError as e:
                print(e)

        while True:
            try:
                name = normalize_token("name", input("Name: "))
                break
            except ValueError as e:
                print(e)

        source = select_from_list("Source", SOURCES)
        outcome = select_from_list("Outcome", PRESCRIPTION_OUTCOMES)
        booked_by = select_from_list("Booked By", BOOKED_BY)

        while True:
            try:
                model = normalize_token("model", input("Model: "))
                break
            except ValueError as e:
                print(e)

        parts.extend([
            f"amount:{amount}",
            f"advance:{advance}",
            f"name:{name}",
            f"source:{source}",
            f"outcome:{outcome}",
            f"booked_by:{booked_by}",
            f"model:{model}",
            "category:device",
            "domain:work",
        ])

    elif record_type == "fitting":

        while True:
            try:
                amount = validate_positive_int(
                    "amount", input("\nTotal Amount: ").strip()
                )
                break
            except ValueError as e:
                print(e)

        while True:
            try:
                balance = validate_positive_int(
                    "balance", input("Balance Received: ").strip()
                )
                if balance > amount:
                    raise ValueError("Balance cannot exceed total amount.")
                break
            except ValueError as e:
                print(e)

        while True:
            try:
                name = normalize_token("name", input("Name: "))
                break
            except ValueError as e:
                print(e)

        side = select_from_list("Side", SIDES)
        booked_by = select_from_list("Booked By", BOOKED_BY)

        while True:
            try:
                model = normalize_token("model", input("Model: "))
                break
            except ValueError as e:
                print(e)

        parts.extend([
            f"amount:{amount}",
            f"balance:{balance}",
            f"name:{name}",
            f"side:{side}",
            f"booked_by:{booked_by}",
            f"model:{model}",
            "category:device",
            "domain:work",
        ])

    elif record_type == "service":

        while True:
            try:
                amount = validate_positive_int(
                    "amount", input("\nService Amount: ").strip()
                )
                break
            except ValueError as e:
                print(e)

        while True:
            try:
                name = normalize_token("name", input("Name: "))
                break
            except ValueError as e:
                print(e)

        side = select_from_list("Side", SIDES)

        while True:
            try:
                model = normalize_token("model", input("Model: "))
                break
            except ValueError as e:
                print(e)

        while True:
            try:
                complaint = normalize_token("complaint", input("Complaint: "))
                break
            except ValueError as e:
                print(e)

        warranty = select_from_list("Warranty", WARRANTY)

        parts.extend([
            f"amount:{amount}",
            f"name:{name}",
            f"side:{side}",
            f"model:{model}",
            f"complaint:{complaint}",
            f"warranty:{warranty}",
            "category:device",
            "domain:work",
        ])

    # ----------------------------
    # NOTES
    # ----------------------------

    while True:
        notes = input("\nNotes (optional): ").strip()
        if "|" in notes:
            print("Notes cannot contain '|' character.")
        else:
            break

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