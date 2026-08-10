# Spec — Habit streak / heatmap view

## Goal

A read-side view showing, per habit: a GitHub-style contribution-graph
grid (presence/absence per day over N weeks) and the current streak
(consecutive days with a matching record, counting back from today).
No new record format, no new write path — habits are just records that
already exist (`type=habit name=X`, or dedicated types like your
existing `exercise`/`mood`); this only adds a way to *see* consistency
over time.

## Config

New `[habit.NAME]` table in `queries.toml`, same shape as `[board.NAME]`:

```toml
[habit.meditation]
filters = ["type=habit", "name=meditation"]
weeks = 12
```

- `filters` — any valid filter list, same syntax `find_records_with_location`
  already takes. Supports both the generic-type approach (`type=habit
  name=meditation`) and dedicated-type habits (`filters = ["type=exercise"]`
  for "did I exercise at all today," no `name` filter needed).
- `weeks` — how many weeks back the heatmap grid covers. Default 12.
- Multiple `[habit.*]` entries = multiple tracked habits, each gets its
  own grid, listed together on one `/habits` page (same relationship
  Board's `[board.*]` entries have to the eventual `/board` page).

## Backend — `get_habit_data(habit_name)` in `ptos_service.py`

```python
def get_habit_data(habit_name):
    """Return streak + weekly presence grid for a configured habit."""
    queries = ptos.get_queries()
    cfg = queries.get(f"habit.{habit_name}")
    if not cfg or not isinstance(cfg, dict):
        raise PTOSError(f"Habit '{habit_name}' not found in queries.toml")

    filters = cfg.get("filters", [])
    if not filters:
        raise PTOSError(f"Habit '{habit_name}' has no filters defined")
    weeks = cfg.get("weeks", 12)

    today = dt.date.today()
    start = today - dt.timedelta(weeks=weeks)
    matches = ptos.find_records_with_location(filters, start=start, end=today)

    # One boolean per calendar day — a habit is "done" that day if
    # ANY matching record exists, regardless of how many
    days_present = set()
    for _, _, line in matches:
        try:
            d, _, _ = ptos.parse_line(line)
            days_present.add(d)
        except Exception:
            continue

    # Streak: walk back from today (or yesterday if today has no
    # record yet — see note below) counting consecutive present days
    streak = 0
    cursor = today
    if today not in days_present:
        cursor = today - dt.timedelta(days=1)  # don't break the streak just because today isn't logged yet
    while cursor in days_present:
        streak += 1
        cursor -= dt.timedelta(days=1)

    grid = [
        {"date": str(start + dt.timedelta(days=i)),
         "present": (start + dt.timedelta(days=i)) in days_present}
        for i in range((today - start).days + 1)
    ]

    return {
        "habit_name": habit_name,
        "streak": streak,
        "weeks": weeks,
        "grid": grid,          # flat list, frontend buckets into week columns
        "total_days": len(grid),
        "days_done": len(days_present),
    }


def get_habit_names():
    """List configured [habit.*] entries, for the /habits index page."""
    queries = ptos.get_queries()
    return sorted(k.split(".", 1)[1] for k in queries if k.startswith("habit."))
```

- **"Today doesn't break your streak until the day ends"** — if you
  haven't logged today yet, the streak still counts through yesterday
  rather than showing 0 the moment midnight passes and you haven't
  tapped the preset yet. Streak only actually breaks once a day passes
  with no record and a new day starts without yesterday being logged
  retroactively.
- Grid presence is boolean, not count — logging a habit twice in one
  day (e.g. two exercise sessions) doesn't change that day's cell, it's
  still just "present." If you want per-day intensity later (like
  GitHub's darker-green-for-more-commits), that's a v2 enhancement, not
  needed for a habit tracker's actual purpose.
- Reuses `find_records_with_location` exactly as-is — no new scan
  primitive.

## Route + template

```python
@app.route("/habits")
def habits():
    names = svc.get_habit_names()
    data = {n: svc.get_habit_data(n) for n in names}
    return render_template("habits.html", habits=data)
```

- New `web_templates/habits.html` — one card per habit: streak number
  prominent at the top, grid below (weeks as columns, days as rows,
  same layout convention as GitHub's contribution graph — filled cell
  = present, empty = absent).
- Add a nav link alongside Records/Todo/Notes/Journal/Board, same place
  in `base.html`'s nav as the others.

## Caching

The same performance lesson from `get_history_suggestions` applies here
directly — `find_records_with_location` re-scans log files on every
call, and this page will get opened repeatedly (checking your streak is
exactly the kind of thing you do many times a day). Cache
`get_habit_data` results the same way, reusing `ptos._CACHE` and the
existing `_invalidate_history_cache()` hook — add `habit:*` alongside
`history:*`/`condsug:*` in that function's invalidation sweep so it's
covered by every write path already wired up (`append_record`,
`edit_record`, `delete_record`, `advance_record`, `bulk_delete`,
`bulk_set`). No new invalidation call sites needed — piggyback on the
existing ones.

## Query Builder UI

Add a "Habits" tab, same pattern as the Board tab: name, filters
(reuse whatever filter-builder widget Board/Query Builder already has
for `type=X` conditions), weeks. Round-trip through `save_queries_full`
the same way boards are, with a `raw_habits` parameter.

## Testing

New `tests/test_habits.py`:
- habit with records on 3 consecutive days ending today → streak = 3
- habit with a gap (day 2 missing) → streak = 1 (only counts back from
  today/yesterday, doesn't skip the gap)
- no record today, but yesterday and the day before are present →
  streak = 2, not 0 (the "today isn't over yet" rule)
- a day with two matching records → grid cell still just `present: true`,
  not double-counted
- `get_habit_data` result is cached; a write via `append_record`
  matching the habit's filters invalidates it (reuse the pattern from
  `test_history_cache.py`)
- unconfigured habit name raises `PTOSError`

## Acceptance

- `/habits` shows each configured habit's current streak and a 12-week
  (or configured) presence grid, matching what you'd get from manually
  checking the log.
- Logging today's habit via its preset immediately reflects in the
  streak/grid on next page load (cache invalidated by the write).
- No change to how habits are logged — this is purely a new way to see
  data that was already being recorded.
