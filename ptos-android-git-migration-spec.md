# Feature Spec: Android — Split Code/Data Locations, Switch to Git

## Goal

Move PTOS's code to Termux's native home directory (git-friendly) while
keeping data in Android shared storage (visible to Syncthing/rclone/file
managers), replacing the current zip-download-and-diff-copy mechanism
with plain `git clone` / `git pull`. This also resolves the `ptos_sync.py`
scoping issue found in the sync audit — once the data folder contains no
code, "sync the whole base dir" becomes correct behavior instead of a
risk.

---

## 1. Current state (confirmed from the repo)

- `setup_ptos_android.sh` installs everything — code *and* data — into
  `$HOME/storage/shared/ptos`, Android's shared storage, reached through
  Termux's FUSE/Storage-Access-Framework bridge rather than native
  filesystem access
- Setup downloads a GitHub zip archive and extracts it — no `git clone`
- `start_ptos_android.sh` re-checks the latest commit SHA via the GitHub
  API on every launch, and if outdated, re-downloads the zip and manually
  copies every file *except* an explicit `PRESERVED` blocklist (`config
  records journal notes tasks scripts backups exports templates .version
  __pycache__ .git`) to avoid clobbering user data — a hand-rolled
  reimplementation of what `git pull` gives for free when code and data
  aren't mixed together

**Why zip was chosen in the first place:** git repos perform poorly and
unreliably on Android shared storage specifically — thousands of small
`.git/` metadata writes across a FUSE bridge is a known slow/flaky
pattern in the Termux community, and symlinks/POSIX permissions aren't
consistently supported across that bridge either. Zip sidesteps this with
one bulk write. That reasoning was correct at the time; it no longer
applies once code isn't required to live in shared storage.

---

## 2. New layout

```
CODE_DIR = $HOME/ptos                          # Termux native home — git lives here
DATA_DIR = $HOME/storage/shared/ptos-data      # renamed — no longer just "ptos"
```

**`DATA_DIR` is now a genuinely new path**, not a reuse of the existing
one — naming it `ptos-data` makes the code/data split visually obvious
the moment you look at shared storage, and avoids any ambiguity with the
old colocated folder during/after migration. This means, unlike the
original draft of this spec, **existing users' data does need to move**
— not just have leftover code cleaned out of it. See Section 3.

`CODE_DIR/.ptos_home` (a one-line bootstrap file `ptos.py` already
supports — see `ptos.py`'s `_home`/`bootstrap` resolution logic) points
at `DATA_DIR`, so `BASE_DIR` resolves correctly regardless of where the
code is run from.

---

## 3. `setup_ptos_android.sh` changes

```bash
CODE_DIR="$HOME/ptos"
DATA_DIR="$HOME/storage/shared/ptos-data"
OLD_DIR="$HOME/storage/shared/ptos"   # pre-migration colocated location

# Git — trivial to auto-install in Termux, unlike Windows' chicken-and-egg
# problem: pkg doesn't need itself pre-installed first.
if ! command -v git &>/dev/null; then
    echo "Installing git..."
    pkg install -y git
fi

if [ -d "$CODE_DIR/.git" ]; then
    echo "PTOS code already present at $CODE_DIR"
else
    echo "Cloning PTOS..."
    git clone https://github.com/godwinburby/ptos.git "$CODE_DIR"
fi

mkdir -p "$DATA_DIR"
echo "$DATA_DIR" > "$CODE_DIR/.ptos_home"

cd "$CODE_DIR"
python ptos.py --init
```

### One-time migration for existing installs — a real data move now

Because `DATA_DIR`'s name changed, this is no longer just cleaning
orphaned code out of an unchanged path — existing data at `$OLD_DIR`
needs to actually move to `$DATA_DIR`. Run this **before** `mkdir -p
"$DATA_DIR"` above, so it only fires when there's old data to migrate:

```bash
if [ -d "$OLD_DIR" ] && [ ! -d "$DATA_DIR" ]; then
    echo "Migrating data from $OLD_DIR to $DATA_DIR..."
    mkdir -p "$DATA_DIR"
    PRESERVE="config records journal todo notes tasks scripts backups exports templates .version"
    for item in $PRESERVE; do
        [ -e "$OLD_DIR/$item" ] && mv "$OLD_DIR/$item" "$DATA_DIR/"
    done
    echo "Data migrated. Old code files remain at $OLD_DIR — verify PTOS"
    echo "works correctly, then you can remove that folder manually:"
    echo "  rm -rf \"$OLD_DIR\""
fi
```

**Deliberately not auto-deleting `$OLD_DIR`** after the move — leave the
old code files in place (unused, harmless) until you've confirmed the
new install works, then remove it yourself. A one-time data *move* is
exactly the kind of step that should have a manual confirmation step
before anything old gets deleted, unlike the previous draft's pure
code-cleanup (which was safe to automate since it never touched data).

This migration check is safe to run on every setup invocation — once
`$DATA_DIR` exists, the `[ ! -d "$DATA_DIR" ]` guard prevents it from
running again.

---

## 4. `start_ptos_android.sh` changes — dramatically simpler

Replace the entire zip-download / SHA-compare / preserved-blocklist-copy
block with a plain git update:

```bash
CODE_DIR="$HOME/ptos"
cd "$CODE_DIR"

echo "Checking for updates..."
git fetch --quiet origin main
LOCAL=$(git rev-parse HEAD)
REMOTE=$(git rev-parse origin/main)

if [ "$LOCAL" = "$REMOTE" ]; then
    echo "Already on latest version."
else
    echo "Updating..."
    git reset --hard origin/main
fi
```

No `PRESERVED` list needed at all — there's no data sitting alongside
code anymore for `git reset --hard` to threaten. This removes the single
most fragile piece of logic in either Android script.

The rest of the script (Python detection, Flask check, port cleanup,
server launch) stays as-is, just running from `CODE_DIR` instead of the
old colocated path. `ptos_web.py` still resolves `BASE_DIR` correctly via
the `.ptos_home` file left by setup.

---

## 5. What doesn't change

- `$HOME/.shortcuts/Start_PTOS.sh` — still symlinks to
  `$HOME/start_ptos_android.sh`, which itself stays in `$HOME` (only its
  *internal* `CODE_DIR`/`DATA_DIR` references change) — the widget
  shortcut is unaffected
- The *contents* of your data folders — nothing about `records/`,
  `todo/`, `journal/`, `config/` themselves changes, only their parent
  folder's location and name (a straightforward `mv`, not a
  transformation)
- Storage permission flow (`termux-setup-storage`) — unchanged, still
  needed since `DATA_DIR` remains in shared storage

---

## 6. Bonus: resolves the sync scoping issue, no separate fix needed

The sync audit flagged that `ptos_sync.py`'s `run_sync()` bisyncs
`ptos.BASE_DIR` wholesale, which was dangerous specifically because
`BASE_DIR` could resolve to the code folder (containing `.git/` and
source files) in the common case. Once `BASE_DIR` resolves to `DATA_DIR`
via the `.ptos_home` bootstrap — and `DATA_DIR` contains only data, no
code — syncing "the whole base dir" becomes exactly correct: it's already
scoped to just the data folders, by construction, with no separate
folder-list filtering needed in `ptos_sync.py` itself.

---

## How It Works (plain English)

PTOS's code now lives in a private, git-friendly folder inside Termux
itself, instead of Android's shared storage — this is what makes `git
clone` and `git pull` actually reliable, since shared storage was never a
good fit for git's many small file operations. Your data — records,
todos, journal, config — moves once, automatically, into a clearly
separate `ptos-data` folder in shared storage, still visible to
Syncthing, rclone, and file managers. A small file tells the code where
to find your data, so once the one-time move is done, nothing about how
you use PTOS day-to-day changes. Your old folder is left in place
untouched (minus the data that moved out of it) until you've confirmed
everything works and choose to delete it yourself.

Updating now works the normal git way: check what's new, pull it down —
no more re-downloading the whole app as a zip file and carefully copying
around your data every time you update.

---

## Testing requirements (mandatory)

- Fresh install (no existing PTOS): `setup_ptos_android.sh` clones into
  `$HOME/ptos`, creates `$HOME/storage/shared/ptos-data`, writes
  `.ptos_home` correctly, `ptos.py --init` creates data folders in the
  right location
- Existing colocated install: after migration, `$HOME/ptos` contains
  code, `$HOME/storage/shared/ptos-data` contains the moved data folders,
  `$HOME/storage/shared/ptos` (old location) still exists but only
  contains leftover code files — nothing destroyed, nothing auto-deleted
- Verify every item in `PRESERVE` that existed in the old folder actually
  arrives in `ptos-data` — no partial moves, no silently skipped folders
- Running migration twice in a row is a no-op the second time (guarded by
  `[ ! -d "$DATA_DIR" ]`)
- `start_ptos_android.sh`: `git fetch`/`reset --hard` correctly updates
  code without touching anything in `DATA_DIR`
- Widget shortcut (`~/.shortcuts/Start_PTOS.sh`) still launches correctly
  post-migration
- `ptos_sync.py`'s `run_sync()` on a migrated install syncs only
  `DATA_DIR` (`ptos-data`) contents — confirm no `.git/` or `.py` files
  appear in the rclone bisync scope
- Simulate git clone failure (no network) — script fails with a clear
  message rather than partial state
- Simulate `mv` failure partway through migration (e.g. one folder locked
  by another process) — confirm the script reports which item failed
  rather than silently leaving a half-migrated state
