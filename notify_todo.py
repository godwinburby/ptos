#!/usr/bin/env python3
"""
notify_todo.py  —  Due-detection for todo reminders.

Reads todo/todo.txt via ptos_todo and outputs a plain list of tasks
that are due today or overdue.  Platform-specific notifier scripts
(termux-notification, notify-send, PowerShell toast) consume this
output and fire native OS notifications.

Usage:
    python notify_todo.py                  # tasks due today or overdue
    python notify_todo.py --lookahead 3    # tasks due within 3 days
    python notify_todo.py --json           # JSON output for scripting

Exit codes:
    0 = tasks found (printed to stdout)
    1 = no tasks due
    2 = error loading todo.txt
"""

import sys, os, json, argparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import ptos_todo


def main():
    parser = argparse.ArgumentParser(description="List due/overdue todos for notification")
    parser.add_argument("--lookahead", type=int, default=1,
                        help="Days ahead to look (default: 1 = today + tomorrow)")
    parser.add_argument("--json", action="store_true",
                        help="Output as JSON instead of plain text")
    args = parser.parse_args()

    try:
        todos, errors = ptos_todo.load_todos(ptos_todo.TODO_PATH)
    except Exception as e:
        print(f"Error loading todo.txt: {e}", file=sys.stderr)
        sys.exit(2)

    due = ptos_todo.get_due_todos(todos, lookahead_days=args.lookahead)

    if not due:
        sys.exit(1)

    if args.json:
        items = []
        for t in due:
            items.append({
                "line_no": t.line_no,
                "description": t.description,
                "priority": t.priority,
                "due": t.due.isoformat() if t.due else None,
                "projects": t.projects,
                "contexts": t.contexts,
            })
        print(json.dumps(items, indent=2))
    else:
        for t in due:
            pri = f"({t.priority}) " if t.priority else ""
            due_str = t.due.isoformat() if t.due else "no due date"
            proj = " ".join(t.projects)
            print(f"{pri}{t.description}  due:{due_str}  {proj}".rstrip())

    sys.exit(0)


if __name__ == "__main__":
    main()
