# Spec — Time-proximity reminders for `due_time` (v2 — decoupled polling)

Supersedes the earlier draft. This version fixes an interaction bug in
the original design: if `remind_before_minutes < notify_interval`, the
proximity window can pass entirely between two polls and the reminder
silently never fires. Fix: the proximity check runs on its own fast
timer, independent of the existing due-today `notify_interval`.

## Problem (recap)

`_housekeeping_loop` notifies a todo once when it's due *today*
(date-only), then never again — even once `due_time` arrives. We want a
second notification when `due_time` is genuinely close.

## Config

```toml
[todo]
notify_interval = 5          # existing — due-today poll interval, minutes
remind_before_minutes = 15   # new — 0 disables time-proximity reminders
reminder_check_interval = 2  # new — how often the proximity check runs, minutes
```

- `remind_before_minutes = 0` (or unset) = feature off entirely — no new
  thread, no new checks, today's behavior unchanged.
- `reminder_check_interval` default **2 minutes**, independent of
  `notify_interval` — this is what fixes the missed-window bug. Clamp
  server-side to `min 1 / max remind_before_minutes` (a check interval
  longer than the window it's supposed to catch defeats the purpose;
  reject or clamp at save time, same pattern as the existing
  `max(1, min(120, ...))` clamp on `notify_interval`).
- Settings UI: both new fields go next to the existing "Notify every N
  minutes" control. Short helper text under `remind_before_minutes`
  explaining it's checked independently and isn't tied to the due-today
  poll rate.

## Backend — separate loop, not folded into `_housekeeping_loop`

Keep this as its own background thread rather than adding it to the
existing housekeeping loop, since the two now run on genuinely different
timers:

```python
def _reminder_loop(check_interval_minutes=2):
    """Background thread: fire a 'due soon' notice when due_time is close.
    Independent of _housekeeping_loop's due-today interval."""
    import datetime as _dt
    import ptos_todo as _todo_mod
    time_notified = set()
    while True:
        try:
            todo_cfg = svc.get_config().get("todo", {})
            remind_before = todo_cfg.get("remind_before_minutes", 0)
            if remind_before > 0:
                todos, _ = _todo_mod.load_todos(svc.TODO_PATH)
                now = _dt.datetime.now()
                for t in todos:
                    if t.done or not t.due or not t.due_time:
                        continue
                    key = (t.line_no, str(t.due), t.due_time)
                    if key in time_notified:
                        continue
                    due_dt = _dt.datetime.combine(t.due, _dt.time.fromisoformat(t.due_time))
                    mins_until = (due_dt - now).total_seconds() / 60
                    if 0 <= mins_until <= remind_before:
                        p = f"({t.priority}) " if t.priority else ""
                        _system_notify("Todo due soon", f"{p}{t.description} (due {t.due_time})")
                        time_notified.add(key)
        except Exception:
            log.exception("reminder loop error")
        # re-read config each cycle so interval changes take effect
        # without a server restart, rather than capturing it once at start
        todo_cfg = svc.get_config().get("todo", {})
        time.sleep(max(1, todo_cfg.get("reminder_check_interval", 2)) * 60)
```

- **Started conditionally**, same pattern as `_housekeeping_loop`'s
  startup block — only start the thread if `remind_before_minutes > 0`
  at server start, so the feature being off costs nothing (no idle
  thread polling for no reason):

```python
try:
    todo_cfg = svc.get_config().get("todo", {})
    remind_before = todo_cfg.get("remind_before_minutes", 0)
    if remind_before > 0:
        check_min = todo_cfg.get("reminder_check_interval", 2)
        _rt = threading.Thread(target=_reminder_loop, args=(check_min,), daemon=True)
        _rt.start()
        print(f"Due-time reminders enabled ({remind_before} min ahead, checked every {check_min} min)")
except Exception:
    pass
```

- **Fires once per task** — `time_notified` dedups the same way the
  existing `notified` set does. Same in-memory-only caveat applies here
  as it does to the existing `notified` set (resets on restart) — not
  fixing that as part of this spec, per your earlier call to leave it.
- Scans **all** open todos with a `due_time`, not just today's — a task
  due tomorrow at 00:10 should still get caught once it's within
  `remind_before` minutes, without waiting for the separate due-today
  gate in `_housekeeping_loop` to consider it "today."
- Already-past `due_time` is skipped (`mins_until < 0`) — this is
  specifically the advance-warning check, not a "you missed it" check.

## Why a separate loop instead of tuning `_housekeeping_loop`

Folding this into the existing loop would force `notify_interval` and
`remind_before_minutes` to stay coupled — exactly the bug this version
fixes. Someone who wants due-today notices checked hourly (cheap, low
urgency) but wants a tight 10-minute proximity warning (needs frequent
checks to not miss the window) can't get both from one shared interval.
Two independent threads, two independent intervals, no coupling.

## Testing

New `tests/test_reminder.py` (or extend `tests/test_notify.py` if you'd
rather keep todo-notification tests in one file):
- task with `due_time` 10 minutes out, `remind_before_minutes=15` →
  fires exactly once
- same task checked again next cycle → does not fire twice
- `remind_before_minutes < reminder_check_interval` is rejected/clamped
  at config-save time
- `notify_interval=60`, `reminder_check_interval=2`,
  `remind_before_minutes=15` → proximity check still catches a task
  whose window opens and closes entirely within one `notify_interval`
  cycle (this is the regression test for the bug this version fixes)
- `remind_before_minutes = 0` → `_reminder_loop` thread never starts
  (assert via startup log message or a mock, not a live thread check)
- task marked done before `due_time` arrives → never fires
- editing `due_time` on an already-reminded task produces a new cache
  key and can fire again for the new time

## Acceptance

- With `notify_interval=60` and `remind_before_minutes=15`, a task due
  at 1:40pm still gets a "due soon" notice sometime in the ~1:25–1:40pm
  window, regardless of when the last due-today poll happened.
- Default config (`remind_before_minutes` unset) — zero behavior change,
  no new thread started.
- `_housekeeping_loop` is untouched by this spec — the due-today notice
  behavior is exactly what it is today.
