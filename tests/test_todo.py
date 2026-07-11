"""
tests/test_todo.py  —  Tests for ptos_todo.py (todo.txt module)
"""

import os, datetime as dt, pytest
import ptos_todo
from ptos_todo import (
    Todo, parse_todo_line, safe_parse_todo_line, format_line,
    load_todos, save_todos, add_todo, complete_todo, delete_todo, edit_todo,
    filter_todos, get_projects, get_contexts, bucket_todos,
    resolve_todo_date, preprocess_todo_text, get_due_todos,
    archive_done_todos,
    TodoParseError,
)


# ── sample data ─────────────────────────────────────────────────────────────

SAMPLE_TODO_LINES = [
    "(A) 2026-07-10 Call supplier +HearSpeechPro @phone due:2026-07-20",
    "(B) Buy groceries +Home @errand due:2026-07-12",
    "Renew clinic license +Amplifon @admin due:2026-07-15",
    "Read Python book +Learning @home",
    "(A) 2026-07-08 File taxes +Finance @admin due:2026-07-10",
]

SAMPLE_DONE_LINES = [
    "x 2026-07-11 2026-07-09 Fix printer +Home @office",
    "x 2026-07-10 2026-07-08 (B) Buy milk +Home @errand",
]


def _write_todo(tmpdir, lines=None, filename="todo.txt"):
    """Write lines to a todo file in tmpdir."""
    if lines is None:
        lines = SAMPLE_TODO_LINES
    path = os.path.join(str(tmpdir), filename)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for line in lines:
            f.write(line + "\n")
    return path


def _write_done(tmpdir, lines=None):
    """Write lines to done.txt in tmpdir."""
    if lines is None:
        lines = SAMPLE_DONE_LINES
    return _write_todo(tmpdir, lines, filename="done.txt")


# ── parsing ─────────────────────────────────────────────────────────────────

class TestParseTodoLine:
    def test_basic_with_priority(self):
        t = parse_todo_line("(A) Buy milk +Home @errand due:2026-07-12")
        assert t is not None
        assert t.priority == "A"
        assert t.description == "Buy milk"
        assert t.projects == ["+Home"]
        assert t.contexts == ["@errand"]
        assert t.due == dt.date(2026, 7, 12)
        assert t.done is False

    def test_no_priority(self):
        t = parse_todo_line("Read Python book +Learning @home")
        assert t is not None
        assert t.priority is None
        assert t.description == "Read Python book"
        assert t.projects == ["+Learning"]
        assert t.contexts == ["@home"]

    def test_completed_task(self):
        t = parse_todo_line("x 2026-07-11 2026-07-09 Fix printer +Home @office")
        assert t.done is True
        assert t.completed_date == dt.date(2026, 7, 11)
        assert t.created_date == dt.date(2026, 7, 9)
        assert t.description == "Fix printer"
        assert t.projects == ["+Home"]
        assert t.contexts == ["@office"]

    def test_with_sched(self):
        t = parse_todo_line("(C) Deploy app due:2026-07-20 sched:2026-07-15 +DevOps @work")
        assert t.priority == "C"
        assert t.due == dt.date(2026, 7, 20)
        assert t.sched == dt.date(2026, 7, 15)
        assert t.projects == ["+DevOps"]
        assert t.contexts == ["@work"]

    def test_empty_line_returns_none(self):
        assert parse_todo_line("") is None
        assert parse_todo_line("   ") is None

    def test_blank_line_returns_none(self):
        assert parse_todo_line("\n") is None

    def test_line_no_is_set(self):
        t = parse_todo_line("Buy milk", line_no=5)
        assert t.line_no == 5

    def test_raw_line_preserved(self):
        raw = "(A) Buy milk +Home @errand due:2026-07-12"
        t = parse_todo_line(raw)
        assert t.raw_line == raw

    def test_completed_without_date_raises(self):
        with pytest.raises(TodoParseError):
            parse_todo_line("x Buy milk")

    def test_multiple_projects_and_contexts(self):
        t = parse_todo_line("Task +Proj1 +Proj2 @ctx1 @ctx2")
        assert t.projects == ["+Proj1", "+Proj2"]
        assert t.contexts == ["@ctx1", "@ctx2"]

    def test_description_with_metadata(self):
        t = parse_todo_line("(A) Call supplier about stock +HearSpeechPro @phone due:2026-07-20")
        assert t.description == "Call supplier about stock"

    def test_due_with_time(self):
        t = parse_todo_line("Task due:2026-07-12T14:30")
        assert t.due == dt.date(2026, 7, 12)
        assert t.due_time == "14:30"

    def test_sched_with_time(self):
        t = parse_todo_line("Task sched:2026-07-15T09:00 due:2026-07-20T17:00")
        assert t.sched == dt.date(2026, 7, 15)
        assert t.sched_time == "09:00"
        assert t.due == dt.date(2026, 7, 20)
        assert t.due_time == "17:00"

    def test_due_without_time(self):
        t = parse_todo_line("Task due:2026-07-12")
        assert t.due == dt.date(2026, 7, 12)
        assert t.due_time is None


class TestSafeParseTodoLine:
    def test_valid_line(self):
        t = safe_parse_todo_line("(A) Buy milk")
        assert t is not None
        assert t.priority == "A"

    def test_bad_line_returns_none(self):
        t = safe_parse_todo_line("x ")  # completed without date
        assert t is None

    def test_empty_returns_none(self):
        assert safe_parse_todo_line("") is None


# ── formatting ──────────────────────────────────────────────────────────────

class TestFormatLine:
    def test_round_trip_basic(self):
        raw = "(A) Buy milk +Home @errand due:2026-07-12"
        t = parse_todo_line(raw)
        formatted = format_line(t)
        assert formatted == raw

    def test_round_trip_completed(self):
        raw = "x 2026-07-11 2026-07-09 Fix printer +Home @office"
        t = parse_todo_line(raw)
        formatted = format_line(t)
        assert formatted == raw

    def test_round_trip_no_priority(self):
        raw = "Read Python book +Learning @home"
        t = parse_todo_line(raw)
        formatted = format_line(t)
        assert formatted == raw

    def test_round_trip_with_sched(self):
        raw = "(C) Deploy app due:2026-07-20 sched:2026-07-15 +DevOps @work"
        t = parse_todo_line(raw)
        formatted = format_line(t)
        # format_line normalises token order; verify parsed fields survive
        t2 = parse_todo_line(formatted)
        assert t2.priority == "C"
        assert t2.description == "Deploy app"
        assert t2.due == dt.date(2026, 7, 20)
        assert t2.sched == dt.date(2026, 7, 15)
        assert t2.projects == ["+DevOps"]
        assert t2.contexts == ["@work"]

    def test_format_empty_todo(self):
        t = Todo(description="Simple task")
        formatted = format_line(t)
        assert formatted == "Simple task"

    def test_format_priority_only(self):
        t = Todo(priority="A", description="Urgent task")
        formatted = format_line(t)
        assert formatted == "(A) Urgent task"

    def test_format_with_time(self):
        t = Todo(description="Task", due=dt.date(2026, 7, 12), due_time="14:30")
        formatted = format_line(t)
        assert "due:2026-07-12T14:30" in formatted

    def test_format_sched_with_time(self):
        t = Todo(description="Task", sched=dt.date(2026, 7, 15), sched_time="09:00")
        formatted = format_line(t)
        assert "sched:2026-07-15T09:00" in formatted

    def test_format_without_time(self):
        t = Todo(description="Task", due=dt.date(2026, 7, 12))
        formatted = format_line(t)
        assert "due:2026-07-12" in formatted
        assert "T" not in formatted.split("due:")[1].split()[0]

    def test_round_trip_with_time(self):
        raw = "Task due:2026-07-12T14:30 sched:2026-07-15T09:00"
        t = parse_todo_line(raw)
        formatted = format_line(t)
        t2 = parse_todo_line(formatted)
        assert t2.due == dt.date(2026, 7, 12)
        assert t2.due_time == "14:30"
        assert t2.sched == dt.date(2026, 7, 15)
        assert t2.sched_time == "09:00"


# ── load / save ─────────────────────────────────────────────────────────────

class TestLoadTodos:
    def test_load_valid_file(self, tmpdir):
        path = _write_todo(tmpdir)
        todos, errors = load_todos(path)
        assert len(todos) == 5
        assert len(errors) == 0

    def test_load_empty_file(self, tmpdir):
        path = _write_todo(tmpdir, lines=[])
        todos, errors = load_todos(path)
        assert len(todos) == 0
        assert len(errors) == 0

    def test_load_nonexistent_file(self, tmpdir):
        path = os.path.join(str(tmpdir), "nonexistent.txt")
        todos, errors = load_todos(path)
        assert len(todos) == 0
        assert len(errors) == 0

    def test_load_with_bad_line(self, tmpdir):
        lines = [
            "(A) Good task",
            "x ",  # bad: completed without date
            "(B) Another good task",
        ]
        path = _write_todo(tmpdir, lines)
        todos, errors = load_todos(path)
        assert len(todos) == 2
        assert len(errors) == 1
        assert errors[0][0] == 2  # line number

    def test_load_done_file(self, tmpdir):
        path = _write_done(tmpdir)
        todos, errors = load_todos(path)
        assert len(todos) == 2
        assert all(t.done for t in todos)


class TestSaveTodos:
    def test_save_and_reload(self, tmpdir):
        path = os.path.join(str(tmpdir), "test_todo.txt")
        todos = [
            Todo(priority="A", description="Task 1", projects=["+Home"], contexts=["@work"]),
            Todo(description="Task 2"),
        ]
        save_todos(path, todos)
        loaded, _ = load_todos(path)
        assert len(loaded) == 2
        assert loaded[0].priority == "A"
        assert loaded[0].description == "Task 1"

    def test_save_empty_list(self, tmpdir):
        path = os.path.join(str(tmpdir), "test_todo.txt")
        save_todos(path, [])
        assert not os.path.exists(path) or os.path.getsize(path) == 0


# ── CRUD ────────────────────────────────────────────────────────────────────

class TestAddTodo:
    def test_add_basic(self, tmpdir):
        path = _write_todo(tmpdir, lines=[])
        t = add_todo(path, "Buy milk +Home @errand due:2026-07-12")
        assert t.description == "Buy milk"
        assert t.projects == ["+Home"]
        loaded, _ = load_todos(path)
        assert len(loaded) == 1

    def test_add_sets_creation_date(self, tmpdir):
        path = _write_todo(tmpdir, lines=[])
        t = add_todo(path, "Buy milk")
        assert t.created_date == dt.date.today()

    def test_add_empty_raises(self, tmpdir):
        path = _write_todo(tmpdir, lines=[])
        with pytest.raises(TodoParseError):
            add_todo(path, "")

    def test_add_preprocesses_pri(self, tmpdir):
        path = _write_todo(tmpdir, lines=[])
        t = add_todo(path, "pri:a Buy milk")
        assert t.priority == "A"


class TestCompleteTodo:
    def test_complete_moves_to_done(self, tmpdir):
        todo_path = _write_todo(tmpdir)
        done_path = _write_done(tmpdir, lines=[])
        todos, _ = load_todos(todo_path)
        target = todos[0]
        complete_todo(target, todo_path=todo_path, done_path=done_path)

        remaining, _ = load_todos(todo_path)
        done, _ = load_todos(done_path)

        assert len(remaining) == 4
        assert len(done) == 1
        assert done[0].done is True
        assert done[0].completed_date == dt.date.today()

    def test_complete_nonexistent_raises(self, tmpdir):
        todo_path = _write_todo(tmpdir)
        t = Todo(line_no=999, description="Ghost task")
        with pytest.raises(TodoParseError):
            complete_todo(t, todo_path=todo_path, done_path=tmpdir + "/done.txt")


class TestDeleteTodo:
    def test_delete_removes_line(self, tmpdir):
        path = _write_todo(tmpdir)
        todos, _ = load_todos(path)
        line_no = todos[1].line_no
        delete_todo(path, line_no)
        remaining, _ = load_todos(path)
        assert len(remaining) == 4

    def test_delete_nonexistent_raises(self, tmpdir):
        path = _write_todo(tmpdir)
        with pytest.raises(TodoParseError):
            delete_todo(path, 999)


class TestEditTodo:
    def test_edit_priority(self, tmpdir):
        path = _write_todo(tmpdir)
        todos, _ = load_todos(path)
        line_no = todos[2].line_no  # no priority
        t = edit_todo(path, line_no, {"priority": "C"})
        assert t.priority == "C"

    def test_edit_due_date(self, tmpdir):
        path = _write_todo(tmpdir)
        todos, _ = load_todos(path)
        line_no = todos[2].line_no
        t = edit_todo(path, line_no, {"due": "2026-12-25"})
        assert t.due == dt.date(2026, 12, 25)

    def test_edit_description(self, tmpdir):
        path = _write_todo(tmpdir)
        todos, _ = load_todos(path)
        line_no = todos[0].line_no
        t = edit_todo(path, line_no, {"description": "New description"})
        assert t.description == "New description"

    def test_edit_nonexistent_raises(self, tmpdir):
        path = _write_todo(tmpdir)
        with pytest.raises(TodoParseError):
            edit_todo(path, 999, {"priority": "A"})


# ── filtering ───────────────────────────────────────────────────────────────

class TestFilterTodos:
    @pytest.fixture
    def todos(self):
        return [parse_todo_line(line, i+1) for i, line in enumerate(SAMPLE_TODO_LINES)]

    def test_filter_by_project(self, todos):
        result = filter_todos(todos, project="+Home")
        assert len(result) == 1
        assert result[0].description == "Buy groceries"

    def test_filter_by_context(self, todos):
        result = filter_todos(todos, context="@admin")
        assert len(result) == 2

    def test_filter_by_priority(self, todos):
        result = filter_todos(todos, priority="A")
        assert len(result) == 2

    def test_filter_by_due_before(self, todos):
        result = filter_todos(todos, due_before=dt.date(2026, 7, 13))
        assert len(result) == 2  # Buy groceries (7/12) + File taxes (7/10)

    def test_filter_combination(self, todos):
        result = filter_todos(todos, project="+Home", context="@errand")
        assert len(result) == 1
        assert result[0].description == "Buy groceries"

    def test_filter_excludes_done(self, todos):
        for t in todos:
            t.done = True
        result = filter_todos(todos)
        assert len(result) == 0

    def test_filter_include_done(self, todos):
        for t in todos:
            t.done = True
        result = filter_todos(todos, include_done=True)
        assert len(result) == 5


# ── derived data ────────────────────────────────────────────────────────────

class TestGetProjects:
    def test_projects_from_todos(self):
        todos = [parse_todo_line(line, i+1) for i, line in enumerate(SAMPLE_TODO_LINES)]
        projects = get_projects(todos)
        assert "+Amplifon" in projects
        assert "+Home" in projects
        assert "+HearSpeechPro" in projects
        assert "+Learning" in projects
        assert "+Finance" in projects

    def test_empty_todos(self):
        assert get_projects([]) == []


class TestGetContexts:
    def test_contexts_from_todos(self):
        todos = [parse_todo_line(line, i+1) for i, line in enumerate(SAMPLE_TODO_LINES)]
        contexts = get_contexts(todos)
        assert "@phone" in contexts
        assert "@errand" in contexts
        assert "@admin" in contexts
        assert "@home" in contexts


# ── bucketing ───────────────────────────────────────────────────────────────

class TestBucketTodos:
    def test_basic_bucketing(self):
        today = dt.date.today()
        tomorrow = today + dt.timedelta(days=1)
        next_week = today + dt.timedelta(days=5)

        todos = [
            Todo(priority="A", description="Overdue task", due=today - dt.timedelta(days=1), line_no=1),
            Todo(priority="B", description="Today task", due=today, line_no=2),
            Todo(description="Upcoming task", due=next_week, line_no=3),
            Todo(description="Someday task", due=None, line_no=4),
        ]
        buckets = bucket_todos(todos)
        assert len(buckets["overdue"]) == 1
        assert len(buckets["today"]) == 1
        assert len(buckets["upcoming"]) == 1
        assert len(buckets["someday"]) == 1
        assert buckets["total_open"] == 4

    def test_completed_excluded(self):
        today = dt.date.today()
        todos = [
            Todo(description="Open", due=today, line_no=1),
            Todo(description="Done", due=today, done=True, line_no=2),
        ]
        buckets = bucket_todos(todos)
        assert buckets["total_open"] == 1

    def test_far_future_goes_to_someday(self):
        today = dt.date.today()
        far_future = today + dt.timedelta(days=30)
        todos = [Todo(description="Far task", due=far_future, line_no=1)]
        buckets = bucket_todos(todos)
        assert len(buckets["someday"]) == 1


# ── date resolution ─────────────────────────────────────────────────────────

class TestResolveTodoDate:
    def test_today(self):
        d, tm = resolve_todo_date("today")
        assert d == dt.date.today()
        assert tm is None

    def test_tomorrow(self):
        expected = dt.date.today() + dt.timedelta(days=1)
        d, tm = resolve_todo_date("tomorrow")
        assert d == expected
        assert tm is None

    def test_yesterday(self):
        expected = dt.date.today() - dt.timedelta(days=1)
        d, tm = resolve_todo_date("yesterday")
        assert d == expected
        assert tm is None

    def test_iso_date(self):
        d, tm = resolve_todo_date("2026-12-25")
        assert d == dt.date(2026, 12, 25)
        assert tm is None

    def test_plus_days(self):
        expected = dt.date.today() + dt.timedelta(days=3)
        d, tm = resolve_todo_date("+3d")
        assert d == expected

    def test_plus_weeks(self):
        expected = dt.date.today() + dt.timedelta(weeks=2)
        d, tm = resolve_todo_date("+2w")
        assert d == expected

    def test_weekday(self):
        d, tm = resolve_todo_date("monday")
        assert d.weekday() == 0
        assert d > dt.date.today()

    def test_invalid_raises(self):
        with pytest.raises(TodoParseError):
            resolve_todo_date("not-a-date")

    def test_iso_with_time(self):
        d, tm = resolve_todo_date("2026-07-12T14:30")
        assert d == dt.date(2026, 7, 12)
        assert tm == "14:30"

    def test_iso_with_space_time(self):
        d, tm = resolve_todo_date("2026-07-12 15:30")
        assert d == dt.date(2026, 7, 12)
        assert tm == "15:30"

    def test_tomorrow_3pm(self):
        expected = dt.date.today() + dt.timedelta(days=1)
        d, tm = resolve_todo_date("tomorrow 3pm")
        assert d == expected
        assert tm == "15:00"

    def test_tomorrow_330pm(self):
        expected = dt.date.today() + dt.timedelta(days=1)
        d, tm = resolve_todo_date("tomorrow 3:30pm")
        assert d == expected
        assert tm == "15:30"

    def test_monday_930am(self):
        d, tm = resolve_todo_date("monday 9:30am")
        assert d.weekday() == 0
        assert tm == "09:30"

    def test_plus_days_with_time(self):
        expected = dt.date.today() + dt.timedelta(days=3)
        d, tm = resolve_todo_date("+3d 17:00")
        assert d == expected
        assert tm == "17:00"

    def test_24h_time(self):
        d, tm = resolve_todo_date("2026-07-12T23:59")
        assert d == dt.date(2026, 7, 12)
        assert tm == "23:59"


# ── preprocessing ───────────────────────────────────────────────────────────

class TestPreprocessTodoText:
    def test_pri_conversion(self):
        result = preprocess_todo_text("pri:a Buy milk")
        assert result.startswith("(A)")

    def test_pri_case_insensitive(self):
        result = preprocess_todo_text("pri:b Buy milk")
        assert result.startswith("(B)")

    def test_due_tomorrow(self):
        result = preprocess_todo_text("Buy milk due:tomorrow")
        tomorrow = (dt.date.today() + dt.timedelta(days=1)).isoformat()
        assert f"due:{tomorrow}" in result

    def test_sched_today(self):
        result = preprocess_todo_text("Deploy sched:today")
        today = dt.date.today().isoformat()
        assert f"sched:{today}" in result

    def test_passthrough_iso(self):
        line = "(A) Task due:2026-12-25"
        result = preprocess_todo_text(line)
        assert "due:2026-12-25" in result

    def test_no_change_for_plain_text(self):
        line = "Simple task without metadata"
        result = preprocess_todo_text(line)
        assert result == line

    def test_due_tomorrow_with_time(self):
        result = preprocess_todo_text("Buy milk due:tomorrow 3pm")
        tomorrow = (dt.date.today() + dt.timedelta(days=1)).isoformat()
        assert f"due:{tomorrow}T15:00" in result

    def test_due_iso_with_time(self):
        result = preprocess_todo_text("Task due:2026-07-12T14:30")
        assert "due:2026-07-12T14:30" in result


# ── notify ──────────────────────────────────────────────────────────────────

class TestGetDueTodos:
    def test_due_today(self):
        today = dt.date.today()
        todos = [
            Todo(description="Due today", due=today, line_no=1),
            Todo(description="Due tomorrow", due=today + dt.timedelta(days=1), line_no=2),
            Todo(description="Due next week", due=today + dt.timedelta(days=7), line_no=3),
        ]
        result = get_due_todos(todos, lookahead_days=1)
        # lookahead=1: today and tomorrow are within range
        assert len(result) == 2
        assert result[0].description == "Due today"

    def test_overdue(self):
        yesterday = dt.date.today() - dt.timedelta(days=1)
        todos = [Todo(description="Overdue", due=yesterday, line_no=1)]
        result = get_due_todos(todos)
        assert len(result) == 1

    def test_no_due_date_excluded(self):
        todos = [Todo(description="No due", due=None, line_no=1)]
        result = get_due_todos(todos)
        assert len(result) == 0

    def test_sched_in_future_excluded(self):
        today = dt.date.today()
        tomorrow = today + dt.timedelta(days=1)
        todos = [
            Todo(description="Scheduled future", due=today, sched=tomorrow, line_no=1),
        ]
        result = get_due_todos(todos)
        assert len(result) == 0

    def test_completed_excluded(self):
        today = dt.date.today()
        todos = [Todo(description="Done", due=today, done=True, line_no=1)]
        result = get_due_todos(todos)
        assert len(result) == 0

    def test_due_with_time_in_past(self):
        """Task due today at a time that has already passed should surface."""
        today = dt.date.today()
        todos = [
            Todo(description="Past time", due=today, due_time="00:00", line_no=1),
        ]
        result = get_due_todos(todos)
        assert len(result) == 1

    def test_sched_with_time_in_future(self):
        """Task scheduled for later today should not surface yet."""
        today = dt.date.today()
        now = dt.datetime.now()
        # set sched to 1 hour from now
        future_time = (now + dt.timedelta(hours=1)).strftime("%H:%M")
        todos = [
            Todo(description="Scheduled later", due=today, sched=today,
                 sched_time=future_time, line_no=1),
        ]
        result = get_due_todos(todos)
        assert len(result) == 0


# ── round-trip integration ──────────────────────────────────────────────────

class TestRoundTrip:
    def test_parse_format_parse(self):
        """Parse → format → parse should produce identical Todo objects."""
        raw = "(A) 2026-07-10 Call supplier +HearSpeechPro @phone due:2026-07-20"
        t1 = parse_todo_line(raw)
        formatted = format_line(t1)
        t2 = parse_todo_line(formatted)

        assert t1.priority == t2.priority
        assert t1.description == t2.description
        assert t1.projects == t2.projects
        assert t1.contexts == t2.contexts
        assert t1.due == t2.due
        assert t1.created_date == t2.created_date

    def test_all_sample_lines_round_trip(self):
        """Every sample line should survive parse → format → parse."""
        for line in SAMPLE_TODO_LINES:
            t1 = parse_todo_line(line)
            formatted = format_line(t1)
            t2 = parse_todo_line(formatted)
            assert t1.priority == t2.priority
            assert t1.description == t2.description
            assert t1.projects == t2.projects
            assert t1.contexts == t2.contexts
            assert t1.due == t2.due


# ── archive ──────────────────────────────────────────────────────────────────

class TestArchiveDoneTodos:
    def _make_done_file(self, tmpdir, lines):
        path = str(tmpdir.join("done.txt"))
        with open(path, "w") as f:
            f.write("\n".join(lines) + "\n")
        return path

    def test_no_file_returns_zero(self, tmpdir):
        path = str(tmpdir.join("done.txt"))
        assert archive_done_todos(path) == 0

    def test_empty_file_returns_zero(self, tmpdir):
        path = str(tmpdir.join("done.txt"))
        with open(path, "w") as f:
            f.write("")
        assert archive_done_todos(path) == 0

    def test_recent_items_stay(self, tmpdir):
        today = dt.date.today().isoformat()
        lines = [f"x {today} 2026-07-10 Recent task"]
        path = self._make_done_file(tmpdir, lines)
        archived = archive_done_todos(path, threshold_months=6)
        assert archived == 0
        remaining, _ = load_todos(path)
        assert len(remaining) == 1

    def test_old_items_archived(self, tmpdir):
        old_date = (dt.date.today() - dt.timedelta(days=200)).isoformat()
        created = (dt.date.today() - dt.timedelta(days=210)).isoformat()
        lines = [f"x {old_date} {created} Old task"]
        path = self._make_done_file(tmpdir, lines)
        archived = archive_done_todos(path, threshold_months=6)
        assert archived == 1
        remaining, _ = load_todos(path)
        assert len(remaining) == 0
        # check archive file was created
        year = dt.date.fromisoformat(old_date).year
        archive_path = str(tmpdir.join(f"done.{year}.txt"))
        assert os.path.exists(archive_path)
        archived_todos, _ = load_todos(archive_path)
        assert len(archived_todos) == 1
        assert archived_todos[0].description == "Old task"

    def test_mixed_old_and_recent(self, tmpdir):
        today = dt.date.today().isoformat()
        old_date = (dt.date.today() - dt.timedelta(days=200)).isoformat()
        old_created = (dt.date.today() - dt.timedelta(days=210)).isoformat()
        lines = [
            f"x {today} 2026-07-10 Recent task",
            f"x {old_date} {old_created} Old task",
        ]
        path = self._make_done_file(tmpdir, lines)
        archived = archive_done_todos(path, threshold_months=6)
        assert archived == 1
        remaining, _ = load_todos(path)
        assert len(remaining) == 1
        assert remaining[0].description == "Recent task"

    def test_multiple_years(self, tmpdir):
        old_2025 = "2025-03-15"
        old_created_2025 = "2025-03-10"
        old_2024 = "2024-06-01"
        old_created_2024 = "2024-05-25"
        lines = [
            f"x {old_2025} {old_created_2025} Task 2025",
            f"x {old_2024} {old_created_2024} Task 2024",
        ]
        path = self._make_done_file(tmpdir, lines)
        archived = archive_done_todos(path, threshold_months=6)
        assert archived == 2
        remaining, _ = load_todos(path)
        assert len(remaining) == 0
        assert os.path.exists(str(tmpdir.join("done.2025.txt")))
        assert os.path.exists(str(tmpdir.join("done.2024.txt")))

    def test_appends_to_existing_archive(self, tmpdir):
        old_date = (dt.date.today() - dt.timedelta(days=200)).isoformat()
        old_created = (dt.date.today() - dt.timedelta(days=210)).isoformat()
        year = dt.date.fromisoformat(old_date).year
        archive_path = str(tmpdir.join(f"done.{year}.txt"))
        # pre-existing archive entry
        with open(archive_path, "w") as f:
            f.write(f"x {old_date} {old_created} Previous archived task\n")
        lines = [f"x {old_date} {old_created} New archived task"]
        path = self._make_done_file(tmpdir, lines)
        archived = archive_done_todos(path, threshold_months=6)
        assert archived == 1
        archived_todos, _ = load_todos(archive_path)
        assert len(archived_todos) == 2
