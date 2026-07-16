"""
ptos_todo.py  —  Todo module for PTOS (todo.txt format)
Storage: todo/todo.txt (open tasks), todo/done.txt (completed tasks).
Format: https://github.com/todotxt/todo.txt

Run:  python ptos_todo.py              (list open todos)
      python ptos_todo.py add "..."     (add a todo)
      python ptos_todo.py done N        (mark line N complete)
"""

import os, re, sys, calendar, datetime as dt, dataclasses
from dataclasses import dataclass, field
from typing import Optional, List

from ptos import BASE_DIR, TODO_DIR, TODO_PATH, DONE_PATH

# ── errors ──────────────────────────────────────────────────────────────────

class TodoParseError(Exception):
    """Raised when a single todo.txt line cannot be parsed."""
    pass

# ── data model ──────────────────────────────────────────────────────────────

@dataclass
class Todo:
    raw_line: str = ""
    done: bool = False
    priority: Optional[str] = None          # A-Z or None
    completed_date: Optional[dt.date] = None
    created_date: Optional[dt.date] = None
    description: str = ""
    projects: List[str] = field(default_factory=list)   # ["+Project", ...]
    contexts: List[str] = field(default_factory=list)   # ["@context", ...]
    due: Optional[dt.date] = None
    due_time: Optional[str] = None          # "14:30" or None
    threshold: Optional[dt.date] = None
    threshold_time: Optional[str] = None    # "09:00" or None
    rec: Optional[str] = None               # "1w", "+1m", "3d", etc.
    line_no: int = 0

# ── date resolution ─────────────────────────────────────────────────────────

_WEEKDAYS = {
    "monday": 0, "tuesday": 1, "wednesday": 2,
    "thursday": 3, "friday": 4, "saturday": 5, "sunday": 6,
    "mon": 0, "tue": 1, "wed": 2,
    "thu": 3, "fri": 4, "sat": 5, "sun": 6,
}

def resolve_todo_date(s):
    """Resolve a natural-language date string to (date, time_str|None).

    Accepts: today, tomorrow, yesterday, monday-sunday (next occurrence),
    this_week, next_week, this_month, next_month,
    +Nd (days), +Nw (weeks), +Nm (months), YYYY-MM-DD.
    Time suffixes: "3pm", "3:30pm", "15:30", "3 PM" etc.
    Returns (date, "HH:MM"|None).
    """
    s = s.strip()
    # extract trailing time component
    date_part, time_part = _extract_time_suffix(s)
    date_part = date_part.strip().lower()
    today = dt.date.today()

    resolved_date = None

    if date_part == "today":
        resolved_date = today
    elif date_part == "tomorrow":
        resolved_date = today + dt.timedelta(days=1)
    elif date_part == "yesterday":
        resolved_date = today - dt.timedelta(days=1)
    elif date_part == "this_week":
        days_until_sat = (5 - today.weekday()) % 7
        resolved_date = today + dt.timedelta(days=days_until_sat)
    elif date_part == "next_week":
        days_until_mon = (7 - today.weekday()) % 7
        if days_until_mon == 0:
            days_until_mon = 7
        resolved_date = today + dt.timedelta(days=days_until_mon)
    elif date_part == "this_month":
        last_day = calendar.monthrange(today.year, today.month)[1]
        resolved_date = today.replace(day=last_day)
    elif date_part == "next_month":
        resolved_date = _add_months(today, 1).replace(day=1)
    elif date_part in _WEEKDAYS:
        target = _WEEKDAYS[date_part]
        diff = (target - today.weekday()) % 7
        if diff == 0:
            diff = 7
        resolved_date = today + dt.timedelta(days=diff)
    else:
        # +Nd / +Nw / +Nm
        m = re.match(r'^\+(\d+)([dwm])$', date_part)
        if m:
            n, unit = int(m.group(1)), m.group(2)
            if unit == "d":
                resolved_date = today + dt.timedelta(days=n)
            elif unit == "w":
                resolved_date = today + dt.timedelta(weeks=n)
            elif unit == "m":
                resolved_date = _add_months(today, n)
        else:
            # YYYY-MM-DD
            try:
                resolved_date = dt.date.fromisoformat(date_part)
            except (ValueError, TypeError):
                raise TodoParseError(f"Cannot resolve date: {s!r}")

    return resolved_date, time_part


def _extract_time_suffix(s):
    """Split a string into (date_part, time_str|None).

    Handles: "tomorrow 3pm", "2026-07-12T14:30", "2026-07-12 15:30",
    "monday 9:30am", "+3d 17:00", etc.
    """
    s = s.strip()

    # ISO format: YYYY-MM-DDTHH:MM
    m = re.match(r'^(\d{4}-\d{2}-\d{2})[T ](\d{1,2}:\d{2})$', s)
    if m:
        return m.group(1), _normalise_time(m.group(2))

    # trailing time: "... 3pm", "... 3:30pm", "... 15:30"
    m = re.match(r'^(.+?)\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)?$', s, re.IGNORECASE)
    if m:
        date_part = m.group(1)
        hour = int(m.group(2))
        minute = int(m.group(3) or 0)
        ampm = m.group(4)
        if ampm:
            ampm = ampm.lower()
            if ampm == "pm" and hour < 12:
                hour += 12
            elif ampm == "am" and hour == 12:
                hour = 0
        if 0 <= hour <= 23 and 0 <= minute <= 59:
            return date_part, f"{hour:02d}:{minute:02d}"

    return s, None


def _normalise_time(t):
    """Normalise a HH:MM time string."""
    try:
        h, m = t.split(":")
        return f"{int(h):02d}:{int(m):02d}"
    except (ValueError, AttributeError):
        return None


def _add_months(d, n):
    """Add n months to date d, clamping day to last day of target month."""
    month = d.month - 1 + n
    year = d.year + month // 12
    month = month % 12 + 1
    import calendar
    max_day = calendar.monthrange(year, month)[1]
    return dt.date(year, month, min(d.day, max_day))

# ── parsing ─────────────────────────────────────────────────────────────────

def parse_todo_line(line, line_no=0):
    """Parse one todo.txt line into a Todo object.

    Raises TodoParseError on malformed input.  Returns None for blank lines.
    """
    if not line or not line.strip():
        return None

    original = line
    pos = 0

    # completion marker
    done = False
    if line.startswith("x "):
        done = True
        line = line[2:]
        pos += 2

    # completed date (only if done)
    completed_date = None
    if done:
        completed_date, line = _extract_date(line)
        if completed_date is None:
            raise TodoParseError(f"Missing completion date after 'x': {original!r}")

    # priority
    priority = None
    m = re.match(r'^\(([A-Z])\)\s*', line)
    if m:
        priority = m.group(1)
        line = line[m.end():]

    # creation date
    created_date = None
    created_date, line = _extract_date(line)

    # remaining = description + metadata tokens
    remaining = line.strip()

    # extract projects, contexts, due, threshold, rec, pri:X from description
    projects = []
    contexts = []
    due = None
    due_time = None
    threshold = None
    threshold_time = None
    rec = None
    desc_parts = []

    for token in remaining.split():
        if token.startswith("+"):
            projects.append(token)
        elif token.startswith("@"):
            contexts.append(token)
        elif token.lower().startswith("due:"):
            val = token[4:]
            try:
                due, due_time = resolve_todo_date(val)
            except TodoParseError:
                desc_parts.append(token)
        elif token.lower().startswith("t:"):
            val = token[2:]
            try:
                threshold, threshold_time = resolve_todo_date(val)
            except TodoParseError:
                desc_parts.append(token)
        elif token.lower().startswith("rec:") and rec is None:
            rec = token[4:] if len(token) > 4 else None
        elif token.lower().startswith("pri:") and len(token) == 5 and token[4].isalpha() and priority is None:
            priority = token[4].upper()
        else:
            desc_parts.append(token)

    description = " ".join(desc_parts)

    return Todo(
        raw_line=original.rstrip("\n"),
        done=done,
        priority=priority,
        completed_date=completed_date,
        created_date=created_date,
        description=description,
        projects=projects,
        contexts=contexts,
        due=due,
        due_time=due_time,
        threshold=threshold,
        threshold_time=threshold_time,
        rec=rec,
        line_no=line_no,
    )


def safe_parse_todo_line(line, line_no=0):
    """Parse a todo.txt line, returning None instead of raising."""
    try:
        return parse_todo_line(line, line_no)
    except Exception:
        return None


def _extract_date(s):
    """Try to extract a YYYY-MM-DD date from the start of s.
    Returns (date_or_None, remaining_string)."""
    s = s.strip()
    m = re.match(r'^(\d{4}-\d{2}-\d{2})\s*', s)
    if m:
        try:
            d = dt.date.fromisoformat(m.group(1))
            return d, s[m.end():]
        except ValueError:
            pass
    return None, s

# ── formatting ──────────────────────────────────────────────────────────────

def format_line(todo):
    """Format a Todo object back into a todo.txt line. Round-trip safe."""
    parts = []

    if todo.done:
        parts.append("x")
        if todo.completed_date:
            parts.append(todo.completed_date.isoformat())

    if todo.priority:
        parts.append(f"({todo.priority})")

    if todo.created_date:
        parts.append(todo.created_date.isoformat())

    if todo.description:
        parts.append(todo.description)

    for p in todo.projects:
        parts.append(p)

    for c in todo.contexts:
        parts.append(c)

    if todo.due:
        if todo.due_time:
            parts.append(f"due:{todo.due.isoformat()}T{todo.due_time}")
        else:
            parts.append(f"due:{todo.due.isoformat()}")

    if todo.threshold:
        if todo.threshold_time:
            parts.append(f"t:{todo.threshold.isoformat()}T{todo.threshold_time}")
        else:
            parts.append(f"t:{todo.threshold.isoformat()}")

    if todo.rec:
        parts.append(f"rec:{todo.rec}")

    return " ".join(parts)

# ── file I/O ────────────────────────────────────────────────────────────────

def load_todos(path):
    """Load todos from a file.  Bad lines are skipped and collected."""
    todos = []
    errors = []
    if not os.path.exists(path):
        return todos, errors

    with open(path, "r", encoding="utf-8") as f:
        for i, raw in enumerate(f, start=1):
            raw = raw.rstrip("\n")
            if not raw.strip():
                continue
            t = safe_parse_todo_line(raw, line_no=i)
            if t is None:
                errors.append((i, raw))
            else:
                todos.append(t)

    return todos, errors


def save_todos(path, todos):
    """Write todos to a file atomically (.bak + .tmp + rename)."""
    content = "\n".join(format_line(t) for t in todos) + "\n" if todos else ""
    _atomic_write_text(path, content)


def _atomic_write_text(filepath, content):
    """Atomic write with .bak rollback, same pattern as ptos.py."""
    import shutil
    backup = filepath + ".bak"
    tmp = filepath + ".tmp"

    if os.path.exists(filepath):
        shutil.copy2(filepath, backup)

    try:
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(content)
        os.replace(tmp, filepath)
        if os.path.exists(backup):
            os.remove(backup)
    except Exception:
        if os.path.exists(tmp):
            os.remove(tmp)
        if os.path.exists(backup):
            shutil.copy2(backup, filepath)
            os.remove(backup)
        raise

# ── CRUD ────────────────────────────────────────────────────────────────────

def add_todo(path, line_text, line_no=0):
    """Append a raw todo.txt line. Returns the parsed Todo.
    Preprocesses pri:/due:/t: shortcuts automatically."""
    line_text = preprocess_todo_text(line_text)
    t = parse_todo_line(line_text, line_no)
    if t is None:
        raise TodoParseError("Empty todo line")
    # set creation date if not present
    if t.created_date is None:
        t.created_date = dt.date.today()
    formatted = format_line(t)
    _atomic_append_text(path, formatted)
    return t


def _atomic_append_text(filepath, content):
    """Append a line atomically."""
    import shutil
    backup = filepath + ".bak"
    tmp = filepath + ".tmp"

    if os.path.exists(filepath):
        shutil.copy2(filepath, backup)

    try:
        existing = ""
        if os.path.exists(filepath):
            with open(filepath, "r", encoding="utf-8") as f:
                existing = f.read()

        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        with open(tmp, "w", encoding="utf-8") as f:
            if existing and not existing.endswith("\n"):
                f.write(existing + "\n")
            elif existing:
                f.write(existing)
            f.write(content + "\n")

        os.replace(tmp, filepath)
        if os.path.exists(backup):
            os.remove(backup)
    except Exception:
        if os.path.exists(tmp):
            os.remove(tmp)
        if os.path.exists(backup):
            shutil.copy2(backup, filepath)
            os.remove(backup)
        raise


def _parse_rec_interval(rec):
    """Parse rec string like '1w', '+1m', '3d' into (strict: bool, amount: int, unit: str)."""
    if not rec:
        return None
    strict = rec.startswith("+")
    val = rec.lstrip("+")
    m = re.match(r'^(\d+)([dwmy])$', val)
    if not m:
        return None
    return strict, int(m.group(1)), m.group(2)


def _advance_date(d, amount, unit):
    """Advance date d by amount in the given unit."""
    if unit == "d":
        return d + dt.timedelta(days=amount)
    elif unit == "w":
        return d + dt.timedelta(weeks=amount)
    elif unit == "m":
        return _add_months(d, amount)
    elif unit == "y":
        return _add_months(d, amount * 12)
    return d


def complete_todo(todo, completion_date=None, todo_path=None, done_path=None):
    """Move a todo from todo.txt to done.txt with completion marker."""
    todo_path = todo_path or TODO_PATH
    done_path = done_path or DONE_PATH
    if completion_date is None:
        completion_date = dt.date.today()

    # load both files
    todos, _ = load_todos(todo_path)
    done, _ = load_todos(done_path)

    # find and remove from todos (by line_no)
    found = False
    new_todos = []
    for t in todos:
        if t.line_no == todo.line_no and not found:
            # mark complete
            t.done = True
            t.completed_date = completion_date
            done.append(t)
            found = True

            # handle recurrence: create new task if rec: + due:
            if t.rec and t.due:
                parsed = _parse_rec_interval(t.rec)
                if parsed:
                    strict, amount, unit = parsed
                    base = t.due if strict else completion_date
                    new_due = _advance_date(base, amount, unit)
                    new_threshold = None
                    if t.threshold:
                        threshold_base = t.threshold if strict else completion_date
                        new_threshold = _advance_date(threshold_base, amount, unit)
                    new_todo = Todo(
                        done=False,
                        priority=t.priority,
                        created_date=completion_date,
                        description=t.description,
                        projects=list(t.projects),
                        contexts=list(t.contexts),
                        due=new_due,
                        due_time=t.due_time,
                        threshold=new_threshold,
                        threshold_time=t.threshold_time,
                        rec=t.rec,
                    )
                    new_todos.append(new_todo)
        else:
            new_todos.append(t)

    if not found:
        raise TodoParseError(f"Todo at line {todo.line_no} not found")

    # rewrite both files
    save_todos(todo_path, new_todos)
    save_todos(done_path, done)

    return todo


def undo_todo(line_no, todo_path=None, done_path=None):
    """Move a todo from done.txt back to todo.txt (undo completion)."""
    todo_path = todo_path or TODO_PATH
    done_path = done_path or DONE_PATH

    todos, _ = load_todos(todo_path)
    done, _ = load_todos(done_path)

    found = False
    new_done = []
    for t in done:
        if t.line_no == line_no and not found:
            t.done = False
            t.completed_date = None
            todos.append(t)
            found = True
        else:
            new_done.append(t)

    if not found:
        raise TodoParseError(f"Done todo at line {line_no} not found")

    save_todos(todo_path, todos)
    save_todos(done_path, new_done)

    return True


def delete_todo(todo_path, line_no):
    """Delete a todo by line number."""
    todos, _ = load_todos(todo_path)
    new_todos = [t for t in todos if t.line_no != line_no]
    if len(new_todos) == len(todos):
        raise TodoParseError(f"Todo at line {line_no} not found")
    save_todos(todo_path, new_todos)


def archive_done_todos(done_path, threshold_months=6):
    """Move old done items to done.YYYY.txt year archive files.

    Items with completed_date older than threshold_months are appended
    to their year's archive file and removed from done.txt.
    Items without a completed_date stay in done.txt (safety fallback).

    Returns the number of items archived.
    """
    if not os.path.exists(done_path):
        return 0

    done, _ = load_todos(done_path)
    if not done:
        return 0

    cutoff = dt.date.today() - dt.timedelta(days=threshold_months * 30)

    recent = []
    old_by_year = {}
    archived_count = 0

    for t in done:
        if t.completed_date and t.completed_date < cutoff:
            year = t.completed_date.year
            old_by_year.setdefault(year, []).append(t)
            archived_count += 1
        else:
            recent.append(t)

    if not old_by_year:
        return 0

    # append old items to year archive files
    done_dir = os.path.dirname(done_path)
    for year, items in sorted(old_by_year.items()):
        archive_path = os.path.join(done_dir, f"done.{year}.txt")
        # load existing archive to preserve line numbers, then just append raw lines
        existing_lines = ""
        if os.path.exists(archive_path):
            with open(archive_path, "r", encoding="utf-8") as f:
                existing_lines = f.read()
        with open(archive_path, "a", encoding="utf-8") as f:
            for item in items:
                line = format_line(item)
                if existing_lines and not existing_lines.endswith("\n"):
                    f.write("\n")
                existing_lines = ""  # only check first item
                f.write(line + "\n")

    # rewrite done.txt with only recent items
    save_todos(done_path, recent)

    return archived_count


def edit_todo(todo_path, line_no, updates):
    """Edit fields on a todo by line number. updates is a dict of field=value."""
    todos, _ = load_todos(todo_path)
    found = False
    for t in todos:
        if t.line_no == line_no:
            found = True
            for key, val in updates.items():
                if key == "priority":
                    t.priority = val.upper() if val else None
                elif key == "description":
                    t.description = val
                elif key == "due":
                    if val:
                        d, tm = resolve_todo_date(val)
                        t.due = d
                        t.due_time = tm
                    else:
                        t.due = None
                        t.due_time = None
                elif key == "threshold":
                    if val:
                        d, tm = resolve_todo_date(val)
                        t.threshold = d
                        t.threshold_time = tm
                    else:
                        t.threshold = None
                        t.threshold_time = None
                elif key == "projects":
                    t.projects = val if isinstance(val, list) else [val]
                elif key == "contexts":
                    t.contexts = val if isinstance(val, list) else [val]
                elif key == "rec":
                    t.rec = val if val else None
                elif key == "done":
                    t.done = bool(val)
            break

    if not found:
        raise TodoParseError(f"Todo at line {line_no} not found")

    save_todos(todo_path, todos)
    return [t for t in todos if t.line_no == line_no][0]

# ── filtering ───────────────────────────────────────────────────────────────

def filter_todos(todos, project=None, context=None, priority=None,
                 due_before=None, threshold_before=None, include_done=False):
    """Filter a list of Todo objects by various criteria."""
    result = []
    for t in todos:
        if not include_done and t.done:
            continue
        if project and project not in t.projects:
            continue
        if context and context not in t.contexts:
            continue
        if priority and t.priority != priority:
            continue
        if due_before and (t.due is None or t.due > due_before):
            continue
        if threshold_before and (t.threshold is not None and t.threshold > threshold_before):
            continue
        result.append(t)
    return result

# ── derived data ────────────────────────────────────────────────────────────

def get_projects(todos):
    """Get all unique +Project tokens from a list of todos."""
    projects = set()
    for t in todos:
        for p in t.projects:
            projects.add(p)
    return sorted(projects)


def get_contexts(todos):
    """Get all unique @context tokens from a list of todos."""
    contexts = set()
    for t in todos:
        for c in t.contexts:
            contexts.add(c)
    return sorted(contexts)

# ── bucketing ───────────────────────────────────────────────────────────────

def bucket_todos(todos):
    """Group open todos into overdue / today / tomorrow / upcoming / someday buckets.

    - overdue: due < today
    - today: due == today
    - tomorrow: due == today+1
    - upcoming: due > today+1 and <= today+7
    - someday: due is None or > today+7

    Todos with threshold > today are hidden until their threshold date arrives.
    """
    today = dt.date.today()
    tomorrow = today + dt.timedelta(days=1)
    week_end = today + dt.timedelta(days=7)

    open_todos = [t for t in todos if not t.done and (t.threshold is None or t.threshold <= today)]

    b_overdue = []
    b_today = []
    b_tomorrow = []
    b_upcoming = []
    b_someday = []

    for t in open_todos:
        if t.due is None:
            b_someday.append(t)
        elif t.due < today:
            b_overdue.append(t)
        elif t.due == today:
            b_today.append(t)
        elif t.due == tomorrow:
            b_tomorrow.append(t)
        elif t.due <= week_end:
            b_upcoming.append(t)
        else:
            b_someday.append(t)

    # sort overdue most overdue first, upcoming by due date
    b_overdue.sort(key=lambda t: t.due)
    b_today.sort(key=lambda t: (t.priority or "Z", t.description))
    b_tomorrow.sort(key=lambda t: (t.priority or "Z", t.description))
    b_upcoming.sort(key=lambda t: t.due)
    b_someday.sort(key=lambda t: (t.priority or "Z", t.description))

    return {
        "overdue": b_overdue,
        "today": b_today,
        "tomorrow": b_tomorrow,
        "upcoming": b_upcoming,
        "someday": b_someday,
        "total_open": len(open_todos),
    }

# ── CLI preprocessing ──────────────────────────────────────────────────────

def preprocess_todo_text(text):
    """Preprocess a raw todo.txt input string.

    Converts pri:x → (X) and resolves natural-language dates in due:/t:.
    Handles two-token patterns like ``due:tomorrow 3pm`` by combining them.
    """
    text = text.strip()

    # pri:x → (X)
    m = re.match(r'^pri:([a-zA-Z])\s+', text)
    if m:
        text = f"({m.group(1).upper()}) {text[m.end():]}"

    # resolve due: and t: dates
    _TIME_RE = re.compile(
        r'^(\d{1,2}:\d{2}(?:\s*[AaPp][Mm])?|\d{1,2}\s*[AaPp][Mm])$'
    )

    def _resolve_token(tok, next_tok=None):
        low = tok.lower()
        if low.startswith("due:"):
            val = tok[4:]
            # if next token looks like a time suffix, append it
            combined = val
            if next_tok and _TIME_RE.match(next_tok):
                combined = f"{val} {next_tok}"
            try:
                d, tm = resolve_todo_date(combined)
                if tm:
                    return f"due:{d.isoformat()}T{tm}", True
                return f"due:{d.isoformat()}", False
            except TodoParseError:
                return tok, False
        elif low.startswith("t:"):
            val = tok[2:]
            combined = val
            if next_tok and _TIME_RE.match(next_tok):
                combined = f"{val} {next_tok}"
            try:
                d, tm = resolve_todo_date(combined)
                if tm:
                    return f"t:{d.isoformat()}T{tm}", True
                return f"t:{d.isoformat()}", False
            except TodoParseError:
                return tok, False
        elif low.startswith("rec:"):
            val = tok[4:]
            _REC_WORDS = {
                "daily": "1d", "weekly": "1w", "monthly": "1m", "yearly": "1y",
                "day": "1d", "week": "1w", "month": "1m", "year": "1y",
                "biweekly": "2w", "bimonthly": "2m", "quarterly": "3m",
            }
            mapped = _REC_WORDS.get(val.lower())
            if mapped:
                return f"rec:{mapped}", False
            return tok, False
        return tok, False

    tokens = text.split()
    resolved = []
    i = 0
    while i < len(tokens):
        result, consumed = _resolve_token(tokens[i], tokens[i+1] if i+1 < len(tokens) else None)
        resolved.append(result)
        if consumed:
            i += 2
        else:
            i += 1
    return " ".join(resolved)

# ── notify helper ───────────────────────────────────────────────────────────

def get_due_todos(todos, lookahead_days=1):
    """Return todos that are due today or earlier, respecting threshold.

    When due_time is set, compares against datetime.now() for precision.
    When no time is set, uses date-only comparison (due <= today + lookahead).
    A todo surfaces if:
      - due is set and due <= today + lookahead (with time precision when set)
      - threshold is None or threshold+time <= now
      - done is False
    """
    now = dt.datetime.now()
    today = now.date()
    cutoff_date = today + dt.timedelta(days=lookahead_days)
    result = []
    for t in todos:
        if t.done:
            continue
        if t.due is None:
            continue
        # date-only tasks: simple date comparison
        if t.due_time:
            due_dt = dt.datetime.combine(t.due, dt.time.fromisoformat(t.due_time))
            if due_dt > now + dt.timedelta(days=lookahead_days):
                continue
        else:
            if t.due > cutoff_date:
                continue
        if t.threshold is not None:
            if t.threshold_time:
                threshold_dt = dt.datetime.combine(t.threshold, dt.time.fromisoformat(t.threshold_time))
            else:
                threshold_dt = dt.datetime.combine(t.threshold, dt.time.min)
            if threshold_dt > now:
                continue
        result.append(t)
    result.sort(key=lambda t: (t.due, t.due_time or "99:99"))
    return result

# ── CLI entry point ─────────────────────────────────────────────────────────

def _cli_main():
    """Minimal CLI for standalone testing."""
    if len(sys.argv) < 2:
        todos, _ = load_todos(TODO_PATH)
        open_t = [t for t in todos if not t.done]
        for t in open_t:
            pri = f"({t.priority}) " if t.priority else ""
            due = f" due:{t.due.isoformat()}T{t.due_time}" if t.due and t.due_time else (f" due:{t.due.isoformat()}" if t.due else "")
            proj = " ".join(t.projects)
            ctx = " ".join(t.contexts)
            meta = " ".join(filter(None, [proj, ctx, due]))
            print(f"  {t.line_no:>3}. {pri}{t.description} {meta}".rstrip())
        print(f"\n  {len(open_t)} open, {len(todos) - len(open_t)} done")
        return

    cmd = sys.argv[1]

    if cmd == "add" and len(sys.argv) > 2:
        text = " ".join(sys.argv[2:])
        text = preprocess_todo_text(text)
        t = add_todo(TODO_PATH, text)
        print(f"Added: {format_line(t)}")

    elif cmd == "done" and len(sys.argv) > 2:
        line_no = int(sys.argv[2])
        todos, _ = load_todos(TODO_PATH)
        target = [t for t in todos if t.line_no == line_no]
        if target:
            complete_todo(target[0])
            print(f"Completed line {line_no}")
        else:
            print(f"Line {line_no} not found")

    elif cmd == "list":
        todos, _ = load_todos(TODO_PATH)
        done, _ = load_todos(DONE_PATH)
        open_t = [t for t in todos if not t.done]
        for t in open_t:
            pri = f"({t.priority}) " if t.priority else ""
            due = f" due:{t.due.isoformat()}T{t.due_time}" if t.due and t.due_time else (f" due:{t.due.isoformat()}" if t.due else "")
            print(f"  {t.line_no:>3}. {pri}{t.description}{due}")
        print(f"\n  {len(open_t)} open, {len(done)} done")

    else:
        print("Usage: ptos_todo.py [add \"text\" | done N | list]")

if __name__ == "__main__":
    _cli_main()
