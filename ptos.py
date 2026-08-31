import argparse
import os
import sys
import datetime as dt
import time
import tomllib
import re
import shutil
import subprocess
import uuid
import zipfile
import tempfile
import fnmatch

if sys.stdout:
    sys.stdout.reconfigure(encoding="utf-8")

# --------------------------------------------------
# Paths
# --------------------------------------------------

_home = os.environ.get("PTOS_HOME")
if _home:
    _home = os.path.expanduser(_home)
DESKTOP_MODE = os.environ.get("DESKTOP_MODE") == "1"
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

if not _home:
    bootstrap = os.path.join(SCRIPT_DIR, ".ptos_home")
    if os.path.isfile(bootstrap):
        with open(bootstrap, encoding="utf-8") as f:
            path = f.readline().strip()
        if path:
            path = os.path.expanduser(path)
            if os.path.isdir(path):
                _home = path

if _home:
    BASE_DIR = _home
elif DESKTOP_MODE:
    BASE_DIR = os.path.join(os.environ.get('LOCALAPPDATA', os.path.expanduser('~')), 'ptos')
else:
    BASE_DIR = SCRIPT_DIR

if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
    STARTER_DIR = os.path.join(sys._MEIPASS, 'starters')
else:
    STARTER_DIR = os.path.join(SCRIPT_DIR, 'starters')

CONFIG_DIR   = os.path.join(BASE_DIR, "config")
RECORDS_DIR  = os.path.join(BASE_DIR, "records")
JOURNAL_DIR  = os.path.join(BASE_DIR, "journal")
TEMPLATE_DIR = os.path.join(BASE_DIR, "templates")
EXPORTS_DIR  = os.path.join(BASE_DIR, "exports")
_default_backup_dir = os.path.join(
    os.path.dirname(os.path.normpath(BASE_DIR)), "ptos-backups")
BACKUP_DIR   = os.environ.get("PTOS_BACKUP_DIR", _default_backup_dir)
TODO_DIR     = os.path.join(BASE_DIR, "todo")
TODO_PATH    = os.path.join(TODO_DIR, "todo.txt")
DONE_PATH    = os.path.join(TODO_DIR, "done.txt")
NOTES_DIR    = os.path.join(BASE_DIR, "notes")
BACKUP_FOLDERS = ["records", "config", "templates", "journal", "todo", "notes"]
MAX_BACKUPS = 10  # Keep last 10 backups

VERSION_FILE = os.path.join(SCRIPT_DIR, ".version")
GITHUB_REPO = "godwinburby/ptos"
GITHUB_API_URL = f"https://api.github.com/repos/{GITHUB_REPO}/commits/main"


def _glob_match(pattern, text):
    if '*' not in pattern and '?' not in pattern:
        return pattern.lower() in text.lower()
    regex = fnmatch.translate(pattern.lower())
    regex = regex.replace(r'\Z', '')
    return re.search(regex, text.lower())


class PTOSError(Exception):
    """Raised instead of sys.exit() so callers can handle gracefully."""
    pass


def get_log_files():
    """Get list of log files from records/, excluding conflict files."""
    if not os.path.isdir(RECORDS_DIR):
        return []
    return sorted(f for f in os.listdir(RECORDS_DIR)
                  if f.endswith(".log") and "conflict" not in f.lower())


def get_backup_config():
    """Load backup configuration from config.toml."""
    try:
        with open(CONFIG_PATH, "rb") as f:
            config = tomllib.load(f)
        return config.get("backup", {})
    except Exception:
        return {}


def get_backup_folders():
    """Get list of folders to backup from config, fallback to default."""
    config = get_backup_config()
    folders = config.get("folders", BACKUP_FOLDERS)
    # Filter to only existing folders
    return [f for f in folders if os.path.exists(os.path.join(BASE_DIR, f))]


def get_backup_max_backups():
    """Get maximum full backups to keep from config."""
    config = get_backup_config()
    return config.get("max_full_backups", MAX_BACKUPS)


def get_backup_max_config_backups():
    """Get maximum config-only backups to keep from config."""
    config = get_backup_config()
    return config.get("max_config_backups", 10)


def should_backup():
    """Check if backup is needed by comparing file mod times with last backup.
    Returns True if backup is needed, False if files unchanged since last backup.
    """
    # Check config setting first
    config = get_backup_config()
    if not config.get("backup_if_files_changed", True):
        return True  # Always backup when this setting is false
    
    backup_folders = get_backup_folders()
    
    # Find most recent full backup
    last_backup_time = None
    if os.path.exists(BACKUP_DIR):
        backup_files = []
        for f in os.listdir(BACKUP_DIR):
            if f.startswith("ptos-backup-full-") and f.endswith(".zip"):
                # Extract timestamp from filename: ptos-backup-full-YYYYMMDD_HHMMSS.zip
                try:
                    ts_str = f.replace("ptos-backup-full-", "").replace(".zip", "")
                    backup_time = dt.datetime.strptime(ts_str, "%Y%m%d_%H%M%S")
                    backup_files.append((backup_time, os.path.join(BACKUP_DIR, f)))
                except:
                    continue
        
        if backup_files:
            # Get most recent backup
            backup_files.sort(key=lambda x: x[0], reverse=True)
            last_backup_time = backup_files[0][0]
    
    # If no previous backup found, need to backup
    if not last_backup_time:
        return True
    
    # Check if any file in backup folders has been modified since last backup
    last_backup_timestamp = last_backup_time.timestamp()
    
    for folder in backup_folders:
        folder_path = os.path.join(BASE_DIR, folder)
        if os.path.exists(folder_path):
            for root, dirs, files in os.walk(folder_path):
                for file in files:
                    # Skip .bak and .tmp files
                    if file.endswith(".bak") or file.endswith(".tmp"):
                        continue
                    file_path = os.path.join(root, file)
                    try:
                        # Check if file modified after last backup
                        if os.path.getmtime(file_path) > last_backup_timestamp:
                            return True
                    except:
                        continue
    
    return False


def get_backup_preview():
    """Get preview of what will be backed up.
    Returns dict with folder summary and file details.
    """
    backup_folders = get_backup_folders()
    preview = {
        "folders": [],
        "total_files": 0,
        "total_size": 0,
        "last_backup": None
    }
    
    # Find most recent full backup timestamp
    if os.path.exists(BACKUP_DIR):
        backup_files = []
        for f in os.listdir(BACKUP_DIR):
            if f.startswith("ptos-backup-full-") and f.endswith(".zip"):
                # Extract timestamp from filename: ptos-backup-full-YYYYMMDD_HHMMSS.zip
                try:
                    ts_str = f.replace("ptos-backup-full-", "").replace(".zip", "")
                    backup_time = dt.datetime.strptime(ts_str, "%Y%m%d_%H%M%S")
                    backup_files.append((backup_time, f))
                except:
                    continue
        
        if backup_files:
            backup_files.sort(key=lambda x: x[0], reverse=True)
            last_backup_time, last_backup_file = backup_files[0]
            preview["last_backup"] = {
                "timestamp": last_backup_time.isoformat(),
                "filename": last_backup_file
            }
    
    for folder in backup_folders:
        folder_path = os.path.join(BASE_DIR, folder)
        if not os.path.exists(folder_path):
            continue
            
        folder_info = {
            "name": folder,
            "path": folder_path,
            "file_count": 0,
            "size": 0,
            "files": []
        }
        
        # Count files and size in this folder
        for root, dirs, files in os.walk(folder_path):
            for file in files:
                # Skip .bak and .tmp files (same as backup logic)
                if file.endswith(".bak") or file.endswith(".tmp"):
                    continue
                    
                file_path = os.path.join(root, file)
                try:
                    size = os.path.getsize(file_path)
                    folder_info["file_count"] += 1
                    folder_info["size"] += size
                    preview["total_files"] += 1
                    preview["total_size"] += size
                    
                    # Add file details (limit to first 20 files per folder for performance)
                    if len(folder_info["files"]) < 20:
                        folder_info["files"].append({
                            "name": file,
                            "path": os.path.relpath(file_path, BASE_DIR),
                            "size": size,
                            "modified": os.path.getmtime(file_path)
                        })
                except Exception:
                    continue
        
        preview["folders"].append(folder_info)
    
    # Format sizes for display
    preview["total_size_formatted"] = _format_size(preview["total_size"])
    for folder in preview["folders"]:
        folder["size_formatted"] = _format_size(folder["size"])
    
    return preview


def _format_size(bytes_size):
    """Format bytes to human readable size."""
    if bytes_size < 1024:
        return f"{bytes_size} bytes"
    elif bytes_size < 1024 * 1024:
        return f"{bytes_size / 1024:.1f} KB"
    elif bytes_size < 1024 * 1024 * 1024:
        return f"{bytes_size / (1024 * 1024):.1f} MB"
    else:
        return f"{bytes_size / (1024 * 1024 * 1024):.1f} GB"


def get_restore_preview(backup_path):
    """Get preview of what will be restored from a backup file.
    Returns dict with backup contents summary.
    """
    import zipfile
    import json
    
    preview = {
        "filename": os.path.basename(backup_path),
        "type": "config" if "config" in os.path.basename(backup_path).lower() else "full",
        "total_files": 0,
        "total_size": 0,
        "folders": {},
        "contents": [],
        "backup_date": None
    }
    
    try:
        if not os.path.exists(backup_path):
            return {"error": f"Backup file not found: {backup_path}"}
        
        # Try to extract backup date from filename
        import re
        match = re.search(r"(\d{8}_\d{6})", os.path.basename(backup_path))
        if match:
            try:
                dt_str = match.group(1)
                dt_obj = dt.datetime.strptime(dt_str, "%Y%m%d_%H%M%S")
                preview["backup_date"] = dt_obj.isoformat()
            except:
                pass
        
        # Read backup contents
        with zipfile.ZipFile(backup_path, 'r') as zipf:
            # Get all file info
            for file_info in zipf.infolist():
                if file_info.filename.endswith('/'):
                    continue  # Skip directories
                    
                preview["total_files"] += 1
                preview["total_size"] += file_info.file_size
                
                # Extract folder structure
                parts = file_info.filename.split('/')
                if len(parts) > 1:
                    folder = parts[0]
                    if folder not in preview["folders"]:
                        preview["folders"][folder] = {"file_count": 0, "size": 0}
                    preview["folders"][folder]["file_count"] += 1
                    preview["folders"][folder]["size"] += file_info.file_size
                
                # Add to contents list (limit to first 30 files)
                if len(preview["contents"]) < 30:
                    preview["contents"].append({
                        "path": file_info.filename,
                        "size": file_info.file_size,
                        "compressed_size": file_info.compress_size,
                        "modified": dt.datetime(*file_info.date_time).isoformat() if file_info.date_time else None
                    })
            
            # Try to read metadata if it exists
            try:
                if '.last_backup_info' in zipf.namelist():
                    with zipf.open('.last_backup_info') as f:
                        metadata = json.loads(f.read().decode('utf-8'))
                        preview["metadata"] = metadata
            except:
                pass
        
        # Format sizes
        preview["total_size_formatted"] = _format_size(preview["total_size"])
        preview["folders_formatted"] = {}
        for folder, info in preview["folders"].items():
            preview["folders_formatted"][folder] = {
                "file_count": info["file_count"],
                "size": _format_size(info["size"])
            }
        
        for item in preview["contents"]:
            item["size_formatted"] = _format_size(item["size"])
            if item.get("compressed_size"):
                item["compressed_size_formatted"] = _format_size(item["compressed_size"])
        
    except Exception as e:
        preview["error"] = str(e)
    
    return preview


def get_current_version():
    """Get the stored current version SHA from .version file."""
    if os.path.exists(VERSION_FILE):
        with open(VERSION_FILE, "r") as f:
            return f.read().strip()
    return None

def save_current_version(sha):
    """Save the current version SHA to .version file."""
    with open(VERSION_FILE, "w") as f:
        f.write(sha)

def init_version():
    """Initialize version file with current SHA.
    For git: use HEAD. For non-git (Termux): fetch from GitHub API.
    """
    if os.path.exists(VERSION_FILE):
        return  # Already initialized
    
    sha = None
    
    # Try git first
    if os.path.exists(os.path.join(SCRIPT_DIR, ".git")):
        try:
            result = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=SCRIPT_DIR,
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0:
                sha = result.stdout.strip()
        except Exception:
            pass
    
    # For non-git (Termux), fetch from GitHub API
    if not sha:
        try:
            import urllib.request
            req = urllib.request.Request(
                GITHUB_API_URL,
                headers={"User-Agent": "PTOS/1.0"}
            )
            with urllib.request.urlopen(req, timeout=10) as response:
                import json
                data = json.loads(response.read().decode())
                sha = data.get("sha", "")
        except Exception:
            pass
    
    # Save if we got something
    if sha:
        save_current_version(sha)

# --------------------------------------------------
# Atomic write operations
# --------------------------------------------------

def atomic_write(filepath, content):
    """Write file atomically with .bak backup for rollback on failure."""
    backup_path = filepath + ".bak"
    temp_path = filepath + ".tmp"
    
    # Create .bak backup
    if os.path.exists(filepath):
        shutil.copy2(filepath, backup_path)
    
    try:
        # Write to .tmp
        with open(temp_path, "w", encoding="utf-8") as f:
            f.write(content)
        
        # Atomic rename
        os.replace(temp_path, filepath)
        
        # Success - remove .bak
        if os.path.exists(backup_path):
            os.remove(backup_path)
            
    except Exception as e:
        # Failure - cleanup temp, restore .bak
        if os.path.exists(temp_path):
            os.remove(temp_path)
        if os.path.exists(backup_path):
            shutil.copy2(backup_path, filepath)
            os.remove(backup_path)
        _log_error(f"Atomic write failed for {filepath}: {e}")
        raise

def atomic_append(filepath, content):
    """Append to file atomically with .bak backup for rollback on failure."""
    backup_path = filepath + ".bak"
    temp_path = filepath + ".tmp"
    
    # Create .bak backup
    if os.path.exists(filepath):
        shutil.copy2(filepath, backup_path)
    
    try:
        # Read existing content
        existing = ""
        if os.path.exists(filepath):
            with open(filepath, "r", encoding="utf-8") as f:
                existing = f.read()
        
        # Write to .tmp with appended content
        with open(temp_path, "w", encoding="utf-8") as f:
            if existing and not existing.endswith("\n"):
                f.write(existing + "\n")
            elif existing:
                f.write(existing)
            f.write(content + "\n")
        
        # Atomic rename
        os.replace(temp_path, filepath)
        
        # Success - remove .bak
        if os.path.exists(backup_path):
            os.remove(backup_path)
            
    except Exception as e:
        # Failure - restore .bak
        if os.path.exists(temp_path):
            os.remove(temp_path)
        if os.path.exists(backup_path):
            shutil.copy2(backup_path, filepath)
            os.remove(backup_path)
        _log_error(f"Atomic append failed for {filepath}: {e}")
        raise

def _log_error(message):
    """Log error to ptos_error.log."""
    try:
        log_path = os.path.join(BASE_DIR, "ptos_error.log")
        timestamp = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(f"[{timestamp}] {message}\n")
    except Exception:
        pass

def _backup_file(path):
    """Copy path to path.bak before any write operation.
    Silent no-op if file does not exist yet.
    """
    import shutil
    if os.path.exists(path):
        shutil.copy2(path, path + ".bak")


class AtomicWrite:
    """Context manager for atomic file writes with backup and cache invalidation.

    Usage:
        with AtomicWrite(path, "queries") as w:
            tomli_w.dump(data, w.stream)

    On success: writes via temp file + atomic rename, removes .bak, invalidates cache.
    On failure: removes temp, restores from .bak, logs error.
    """

    def __init__(self, path, resource=None):
        self.path = path
        self.resource = resource
        self.backup_path = path + ".bak"
        self.temp_path = path + ".tmp"
        self._stream = None

    def __enter__(self):
        if os.path.exists(self.path):
            shutil.copy2(self.path, self.backup_path)
        return self

    @property
    def stream(self):
        if self._stream is None:
            self._stream = open(self.temp_path, "wb")
        return self._stream

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self._stream is not None:
            self._stream.close()

        if exc_type is None:
            os.replace(self.temp_path, self.path)
            if os.path.exists(self.backup_path):
                os.remove(self.backup_path)
            if self.resource:
                _invalidate(self.resource)
        else:
            if os.path.exists(self.temp_path):
                os.remove(self.temp_path)
            if os.path.exists(self.backup_path):
                shutil.copy2(self.backup_path, self.path)
                os.remove(self.backup_path)
            _log_error(f"Atomic write failed for {self.path}: {exc_val}")

# --------------------------------------------------
# Doctor — check PTOS health
# --------------------------------------------------

def doctor_check(verbose=False, fix=False, json_output=False):
    """Run health checks on PTOS installation.
    Returns (errors, warnings, messages).
    """
    errors = []
    warnings = []
    messages = []
    fixes_applied = []
    
    # Python version check
    py_version = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    if sys.version_info < (3, 11):
        errors.append(f"Python 3.11+ required, found {py_version}")
    else:
        messages.append(("Python", f"Python {py_version}"))
    
    # Flask check
    try:
        import flask
        messages.append(("Flask", f"Flask installed"))
    except ImportError:
        errors.append("Flask not installed. Run: pip install flask")
    
    # Config folder check
    if not os.path.isdir(CONFIG_DIR):
        errors.append(f"Config folder missing at {CONFIG_DIR}")
        if fix:
            os.makedirs(CONFIG_DIR, exist_ok=True)
            fixes_applied.append(f"Created config/ folder")
    else:
        messages.append(("config/", "Folder exists"))
    
    # Config files check
    config_file = os.path.join(CONFIG_DIR, "config.toml")
    if not os.path.exists(config_file):
        errors.append("config/config.toml missing")
        if fix:
            _write_if_missing(CONFIG_PATH, _load_starter("config"), "config/config.toml")
            fixes_applied.append("Created config/config.toml")
    else:
        messages.append(("config/config.toml", "Exists"))
    
    schema_file = os.path.join(CONFIG_DIR, "schema.toml")
    if not os.path.exists(schema_file):
        errors.append("config/schema.toml missing")
        if fix:
            _write_if_missing(SCHEMA_PATH, _load_starter("schema"), "config/schema.toml")
            fixes_applied.append("Created config/schema.toml")
    else:
        messages.append(("config/schema.toml", "Exists"))
    
    queries_file = os.path.join(CONFIG_DIR, "queries.toml")
    if not os.path.exists(queries_file):
        warnings.append("config/queries.toml missing (optional)")
        if fix:
            _write_if_missing(QUERIES_PATH, _load_starter("queries"), "config/queries.toml")
            fixes_applied.append("Created config/queries.toml")
    else:
        messages.append(("config/queries.toml", "Exists"))
    
    presets_file = os.path.join(CONFIG_DIR, "presets.toml")
    if not os.path.exists(presets_file):
        warnings.append("config/presets.toml missing (optional)")
        if fix:
            _write_if_missing(PRESETS_PATH, _load_starter("presets"), "config/presets.toml")
            fixes_applied.append("Created config/presets.toml")
    else:
        messages.append(("config/presets.toml", "Exists"))
    
    # Records folder check
    if not os.path.isdir(RECORDS_DIR):
        errors.append(f"Records folder missing at {RECORDS_DIR}")
        if fix:
            os.makedirs(RECORDS_DIR, exist_ok=True)
            fixes_applied.append(f"Created records/ folder")
    else:
        messages.append(("records/", "Folder exists"))
        
        # Check for year log files
        log_files = get_log_files()
        if not log_files:
            errors.append("No records found (create at least one .log file)")
            if fix:
                year_log = os.path.join(RECORDS_DIR, f"{dt.date.today().year}.log")
                open(year_log, "a", encoding="utf-8").close()
                fixes_applied.append(f"Created records/{dt.date.today().year}.log")
        else:
            messages.append(("records/*.log", f"{len(log_files)} file(s)"))
    
    # Templates folder check
    if not os.path.isdir(TEMPLATE_DIR):
        warnings.append("templates/ folder missing (optional)")
        if fix:
            os.makedirs(TEMPLATE_DIR, exist_ok=True)
            fixes_applied.append("Created templates/ folder")
    else:
        messages.append(("templates/", "Folder exists"))
    
    template_file = os.path.join(TEMPLATE_DIR, "daily.md")
    if not os.path.exists(template_file):
        warnings.append("templates/daily.md missing (optional)")
        if fix:
            _write_if_missing(template_file, _load_starter("journal"), "templates/daily.md")
            fixes_applied.append("Created templates/daily.md")
    else:
        messages.append(("templates/daily.md", "Exists"))
    
    # ── Spec checks: TOML validity, config shape, .ptos_home, data sanity ──
    
    # TOML syntax validity
    for label, path in [("schema.toml", SCHEMA_PATH), ("queries.toml", QUERIES_PATH),
                         ("presets.toml", PRESETS_PATH), ("config.toml", CONFIG_PATH)]:
        if os.path.isfile(path):
            try:
                with open(path, "rb") as f:
                    tomllib.load(f)
                messages.append((f"TOML {label}", "Valid syntax"))
            except tomllib.TOMLDecodeError as e:
                errors.append(f"{label}: invalid TOML — {e}")
    
    # Config shape sanity — check for numeric fields in schema
    if os.path.isfile(SCHEMA_PATH):
        try:
            schema = get_schema()
            int_fields = [f for f, m in schema.get("fields", {}).items()
                          if isinstance(m, dict) and m.get("type") == "int"]
            if not int_fields:
                warnings.append("schema.toml: no fields declared type=\"int\" — "
                                "min/max/sum metrics will silently show \"no data\"")
            else:
                messages.append(("schema.toml numeric fields", f"{len(int_fields)} declared"))
        except (SystemExit, Exception):
            pass
    
    # .ptos_home sanity check
    bootstrap = os.path.join(SCRIPT_DIR, ".ptos_home")
    if os.path.isfile(bootstrap):
        with open(bootstrap, encoding="utf-8") as f:
            home_path = f.read().strip()
        tmp_root = os.path.realpath(tempfile.gettempdir())
        if os.path.realpath(home_path).startswith(tmp_root) or "pytest-of-" in home_path:
            if os.path.realpath(home_path) != os.path.realpath(BASE_DIR):
                errors.append(f".ptos_home points at a temp path: {home_path}")
            else:
                messages.append((".ptos_home", f"-> {home_path}"))
        elif not os.path.isdir(home_path):
            errors.append(f".ptos_home points at a nonexistent path: {home_path}")
        else:
            messages.append((".ptos_home", f"-> {home_path}"))
    
    # Data sanity — empty-when-shouldn't-be checks
    current_year_log = os.path.join(RECORDS_DIR, f"{dt.date.today().year}.log")
    if os.path.isfile(current_year_log):
        size = os.path.getsize(current_year_log)
        if size == 0:
            warnings.append(f"records/{dt.date.today().year}.log is 0 bytes — "
                            "check for data loss before assuming fresh install")
        else:
            messages.append((f"records/{dt.date.today().year}.log", f"{size} bytes"))
    
    for folder, path in [("config", CONFIG_DIR), ("todo", TODO_DIR)]:
        if os.path.isdir(path) and not os.listdir(path):
            warnings.append(f"{folder}/ exists but is empty")
    
    # Output results
    if json_output:
        return {
            "status": "errors" if errors else "warnings" if warnings else "ok",
            "errors": len(errors),
            "warnings": len(warnings),
            "checks": [
                {"name": name, "status": "pass" if name in [m[0] for m in messages] else "fail", "message": msg}
                for name, msg in messages
            ]
        }
    
    return errors, warnings, messages, fixes_applied

def print_doctor_results(errors, warnings, messages, fixes_applied, verbose=False, fix=False):
    """Print doctor check results in human-readable format."""
    print("\nPTOS Doctor")
    print("=" * 40)
    print()
    
    if verbose:
        print("Checks:")
        for name, msg in messages:
            print(f"  [OK]   {name}: {msg}")
    
    if warnings and (verbose or not fix):
        print()
        for w in warnings:
            print(f"  [WARN] {w}")
    
    if errors:
        print()
        for e in errors:
            print(f"  [FAIL] {e}")
    
    if fix and fixes_applied:
        print()
        print("Fixes applied:")
        for f in fixes_applied:
            print(f"  - {f}")
    
    print()
    if errors:
        print(f"Summary: {len(errors)} error(s), {len(warnings)} warning(s)")
    elif warnings:
        print(f"Summary: {len(warnings)} warning(s)")
    else:
        print("All checks passed!")

# --------------------------------------------------
# Backup functions
# --------------------------------------------------

def backup_data(force=False):
    """Create a timestamped backup ZIP of configured folders.
    Returns the path to the created backup file.
    Automatically removes oldest backups if limit is exceeded.
    Uses atomic write with .tmp file for crash safety.
    
    Args:
        force: If True, backup even if no changes detected
    """
    backup_folders = get_backup_folders()
    
    # Validate mandatory folders exist
    if not os.path.isdir(CONFIG_DIR):
        raise Exception("Cannot create full backup: config/ folder missing")
    if not os.path.isdir(RECORDS_DIR):
        raise Exception("Cannot create full backup: records/ folder missing")
    
    os.makedirs(BACKUP_DIR, exist_ok=True)
    timestamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    temp_path = os.path.join(BACKUP_DIR, f".ptos-backup-full-{timestamp}.tmp")
    final_path = os.path.join(BACKUP_DIR, f"ptos-backup-full-{timestamp}.zip")
    
    try:
        # Write to .tmp file (skip .bak files)
        with zipfile.ZipFile(temp_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for folder in backup_folders:
                folder_path = os.path.join(BASE_DIR, folder)
                if os.path.exists(folder_path):
                    for root, dirs, files in os.walk(folder_path):
                        for file in files:
                            # Skip .bak and .tmp files
                            if file.endswith(".bak") or file.endswith(".tmp"):
                                continue
                            file_path = os.path.join(root, file)
                            arcname = os.path.relpath(file_path, BASE_DIR)
                            zf.write(file_path, arcname)
        
        # Verify ZIP integrity
        with zipfile.ZipFile(temp_path, "r") as zf:
            bad_file = zf.testzip()
            if bad_file:
                raise Exception(f"ZIP verification failed: {bad_file}")
        
        # Atomic rename to final location
        os.replace(temp_path, final_path)
        
        # Clean up old backups if limit exceeded
        _cleanup_old_backups()
        
        return final_path
        
    except Exception as e:
        if os.path.exists(temp_path):
            os.remove(temp_path)
        _log_error(f"Backup failed: {e}")
        raise


def backup_if_needed():
    """Create backup only if changes detected since last backup.
    Returns tuple: (backup_created: bool, backup_path: str or None)
    """
    try:
        if should_backup():
            backup_path = backup_data()
            return True, backup_path
        return False, None
    except Exception as e:
        _log_error(f"Smart backup failed: {e}")
        return False, None

def backup_config():
    """Create a timestamped backup ZIP of config/ folder only.
    Returns the path to the created backup file.
    Uses atomic write with .tmp file for crash safety.
    """
    os.makedirs(BACKUP_DIR, exist_ok=True)
    timestamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    temp_path = os.path.join(BACKUP_DIR, f".ptos-backup-config-{timestamp}.tmp")
    final_path = os.path.join(BACKUP_DIR, f"ptos-backup-config-{timestamp}.zip")
    
    config_path = os.path.join(BASE_DIR, "config")
    
    try:
        # Write to .tmp file
        with zipfile.ZipFile(temp_path, "w", zipfile.ZIP_DEFLATED) as zf:
            if os.path.exists(config_path):
                for file in os.listdir(config_path):
                    if file.endswith(".toml"):
                        file_path = os.path.join(config_path, file)
                        zf.write(file_path, os.path.join("config", file))
        
        # Verify ZIP integrity
        with zipfile.ZipFile(temp_path, "r") as zf:
            bad_file = zf.testzip()
            if bad_file:
                raise Exception(f"ZIP verification failed: {bad_file}")
        
        # Atomic rename to final location
        os.replace(temp_path, final_path)
        
        # Clean up old backups if limit exceeded
        _cleanup_old_backups()
        
        return final_path
        
    except Exception as e:
        if os.path.exists(temp_path):
            os.remove(temp_path)
        _log_error(f"Config backup failed: {e}")
        raise

def restore_data(zip_path):
    """Restore data from a backup ZIP file.
    Overwrites existing files with the contents of the backup.
    """
    if not os.path.exists(zip_path):
        raise FileNotFoundError(f"Backup file not found: {zip_path}")
    
    temp_dir = os.path.join(BACKUP_DIR, f".restore-{uuid.uuid4().hex[:8]}")
    
    try:
        os.makedirs(temp_dir)
        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extractall(temp_dir)
        
        folders_in_zip = {item for item in os.listdir(temp_dir) if os.path.isdir(os.path.join(temp_dir, item))}
        
        if "config" not in folders_in_zip:
            raise Exception("Invalid backup: config/ folder not found in archive")
        if "records" not in folders_in_zip:
            raise Exception("Invalid backup: records/ folder not found in archive")
        
        for item in os.listdir(temp_dir):
            src = os.path.join(temp_dir, item)
            dst = os.path.join(BASE_DIR, item)
            
            if os.path.isdir(src):
                if os.path.exists(dst):
                    shutil.rmtree(dst)
                shutil.copytree(src, dst)
            else:
                if os.path.exists(dst):
                    os.remove(dst)
                shutil.copy2(src, dst)
        
        _invalidate_all()

        shutil.rmtree(temp_dir)
        
    except Exception as e:
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir)
        _log_error(f"Restore failed: {e}")
        raise

def restore_config(zip_path):
    """Restore config from a backup ZIP file (config/ folder only).
    Overwrites existing config files with the contents of the backup.
    """
    if not os.path.exists(zip_path):
        raise FileNotFoundError(f"Backup file not found: {zip_path}")
    
    temp_dir = os.path.join(BACKUP_DIR, f".restore-config-{uuid.uuid4().hex[:8]}")
    
    try:
        os.makedirs(temp_dir)
        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extractall(temp_dir)
        
        config_temp = os.path.join(temp_dir, "config")
        if not os.path.isdir(config_temp):
            raise Exception("Invalid backup: config/ folder not found in archive")
        
        config_dst = os.path.join(BASE_DIR, "config")
        if os.path.exists(config_dst):
            shutil.rmtree(config_dst)
        shutil.copytree(config_temp, config_dst)
        
        _invalidate("config")

        shutil.rmtree(temp_dir)

    except Exception as e:
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir)
        _log_error(f"Config restore failed: {e}")
        raise

def list_backups():
    """Return list of backup files with creation dates, sorted newest first.
    Returns list of tuples: (filename, created_datetime, type)
    type is 'full' for ptos-backup-full-*.zip or 'config' for ptos-backup-config-*.zip
    """
    os.makedirs(BACKUP_DIR, exist_ok=True)
    backups = []
    for f in os.listdir(BACKUP_DIR):
        if f.startswith("ptos-backup-full-") and f.endswith(".zip"):
            path = os.path.join(BACKUP_DIR, f)
            mtime = dt.datetime.fromtimestamp(os.path.getmtime(path))
            backups.append((f, mtime, "full"))
        elif f.startswith("ptos-backup-config-") and f.endswith(".zip"):
            path = os.path.join(BACKUP_DIR, f)
            mtime = dt.datetime.fromtimestamp(os.path.getmtime(path))
            backups.append((f, mtime, "config"))
    backups.sort(key=lambda x: x[1], reverse=True)
    return backups

def delete_backup(filename):
    """Delete a specific backup file.
    Returns True on success, raises error on failure.
    """
    backup_path = os.path.join(BACKUP_DIR, filename)
    if not os.path.exists(backup_path):
        raise FileNotFoundError(f"Backup not found: {filename}")
    if not ((filename.startswith("ptos-backup-full-") or filename.startswith("ptos-backup-config-")) and filename.endswith(".zip")):
        raise ValueError("Invalid backup filename")
    os.remove(backup_path)
    return True

def _cleanup_old_backups():
    """Remove oldest full backups if max_backups limit is exceeded.
    Also cleans up config backups if max_config_backups limit is exceeded.
    """
    backups = list_backups()
    
    # Clean up full backups
    full_backups = [(n, m, t) for n, m, t in backups if t == "full"]
    max_full_backups = get_backup_max_backups()
    
    if len(full_backups) > max_full_backups:
        # Get list of filenames to delete (oldest, beyond the limit)
        to_delete = full_backups[max_full_backups:]
        for name, _, _ in to_delete:
            backup_path = os.path.join(BACKUP_DIR, name)
            if os.path.exists(backup_path):
                os.remove(backup_path)
    
    # Clean up config backups
    config_backups = [(n, m, t) for n, m, t in backups if t == "config"]
    max_config_backups = get_backup_max_config_backups()
    
    if len(config_backups) > max_config_backups:
        # Get list of filenames to delete (oldest, beyond the limit)
        to_delete = config_backups[max_config_backups:]
        for name, _, _ in to_delete:
            backup_path = os.path.join(BACKUP_DIR, name)
            if os.path.exists(backup_path):
                os.remove(backup_path)

def migrate_backup_dir():
    """One-time migration: move backups/ from inside BASE_DIR to sibling ptos-backups/."""
    old_path = os.path.join(BASE_DIR, "backups")
    if os.path.isdir(old_path) and old_path != BACKUP_DIR and not os.path.isdir(BACKUP_DIR):
        try:
            print(f"Moving backups from {old_path} to {BACKUP_DIR}...")
            os.makedirs(os.path.dirname(BACKUP_DIR), exist_ok=True)
            shutil.move(old_path, BACKUP_DIR)
            print("Backups moved. Old location no longer used.")
        except Exception as e:
            print(f"Warning: could not migrate backups: {e}")

def check_backup_folders():
    """Check if all required backup folders exist.
    Returns tuple: (all_exist: bool, missing_folders: list)
    """
    backup_folders = get_backup_folders()
    missing = []
    for folder in backup_folders:
        folder_path = os.path.join(BASE_DIR, folder)
        if not os.path.exists(folder_path):
            missing.append(folder)
    return len(missing) == 0, missing

SCHEMA_PATH  = os.path.join(CONFIG_DIR, "schema.toml")
QUERIES_PATH = os.path.join(CONFIG_DIR, "queries.toml")
CONFIG_PATH  = os.path.join(CONFIG_DIR, "config.toml")
PRESETS_PATH = os.path.join(CONFIG_DIR, "presets.toml")

# --------------------------------------------------
# Config cache  (load once, reuse everywhere)
# --------------------------------------------------

_CACHE = {}

# Maps resource names to the cache keys they depend on
_CACHE_DEPS = {
    "schema":  ["schema", "derived_fields", "numeric_fields", "datetime_fields"],
    "queries": ["queries"],
    "config":  ["config"],
    "presets": ["presets"],
}


def _invalidate(resource):
    """Invalidate cache for a resource and all its dependent keys."""
    if isinstance(resource, str):
        resource = [resource]
    keys = set()
    for r in resource:
        keys.update(_CACHE_DEPS.get(r, [r]))
    for key in keys:
        _CACHE.pop(key, None)


def _invalidate_all():
    """Invalidate every cached key."""
    for key in list(_CACHE.keys()):
        _CACHE.pop(key, None)


def _load(key, path):
    """Load a TOML file once and cache it.
    Cache is invalidated via _invalidate(resource) on writes.
    Exits on parse errors or missing files."""
    if key not in _CACHE:
        try:
            with open(path, "rb") as f:
                _CACHE[key] = tomllib.load(f)
        except tomllib.TOMLDecodeError as e:
            sys.exit(f"Config error in {path}:\n  {e}\n\nFix the file and try again.")
        except OSError as e:
            sys.exit(f"Cannot read {path}:\n  {e}")
    return _CACHE[key]

def get_config():  return _load("config",  CONFIG_PATH)  if os.path.exists(CONFIG_PATH)  else {}
def get_schema():
    if not os.path.exists(SCHEMA_PATH):
        return {}
    return _load("schema", SCHEMA_PATH)

def get_global_fields(schema=None):
    """Return ordered dict of {name: field_def} from [global_fields] in schema.
    These are optional fields that appear on every record type."""
    if schema is None:
        schema = get_schema()
    return schema.get("global_fields", {})

def get_linkable_fields(schema=None):
    """Return set of field names flagged `linkable = true` in schema.
    Scans [fields.*], [global_fields.*], and per-type [type.*.fields.*]."""
    if schema is None:
        schema = get_schema()
    fields = set()
    for fname, fdef in schema.get("fields", {}).items():
        if isinstance(fdef, dict) and fdef.get("linkable"):
            fields.add(fname)
    for fname, fdef in schema.get("global_fields", {}).items():
        if isinstance(fdef, dict) and fdef.get("linkable"):
            fields.add(fname)
    for tdef in schema.get("type", {}).values():
        if not isinstance(tdef, dict):
            continue
        for fname, fdef in (tdef.get("fields") or {}).items():
            if isinstance(fdef, dict) and fdef.get("linkable"):
                fields.add(fname)
    return fields

def get_queries():
    if not os.path.exists(QUERIES_PATH):
        return {}
    return _load("queries", QUERIES_PATH)
def get_presets(): return _load("presets", PRESETS_PATH).get("presets", {}) if os.path.exists(PRESETS_PATH) else {}

def get_thresholds():
    """Return {name: config_dict} for all [threshold.*] sections in queries.toml."""
    q = get_queries()
    return {k.split(".", 1)[1]: v for k, v in q.items()
            if k.startswith("threshold.") and isinstance(v, dict)}


def _query_refs_type(query, selected):
    """Check if a base query's where clause references any of the selected types."""
    where = query.get("where", "")
    if not where:
        return False
    found = re.findall(r'type\s*=\s*(\w+)', where)
    return bool(set(found) & set(selected))


def export_schema_bundle(selected_types):
    """Build 4 filtered TOML dicts for sharing.

    Always includes config.toml. [global_fields] included if defined.
    [shared] included only if referenced by selected types via use = "shared.X".
    [fields] filtered to only those used by selected types.
    Queries, metrics, dashboards, and presets filtered to selected_types.

    Returns dict with keys: schema, queries, presets, config.
    """
    import tomli_w
    import io

    schema = get_schema()
    queries = get_queries()
    presets_raw = get_presets()
    config = get_config()

    selected = set(selected_types)

    # ── schema.toml ──
    out_schema = {}

    # [types] — always include, filtered
    all_types = schema.get("types", {}).get("allowed", [])
    out_schema["types"] = {"allowed": sorted(selected & set(all_types))}

    # [global_fields] — always include
    gf = schema.get("global_fields")
    if gf:
        out_schema["global_fields"] = gf

    # [shared] — only shared defs referenced by selected types
    shared = schema.get("shared", {})
    used_shared = set()
    for t in selected:
        tdef = schema.get("type", {}).get(t, {})
        for fdef in tdef.get("fields", {}).values():
            if isinstance(fdef, dict):
                ref = fdef.get("use", "")
                if ref.startswith("shared."):
                    used_shared.add(ref.split(".", 1)[1])
    if shared and used_shared:
        out_schema["shared"] = {k: v for k, v in shared.items() if k in used_shared}

    # [fields] — only fields used by selected types
    out_fields = {}
    for t in selected:
        tdef = schema.get("type", {}).get(t, {})
        for fname in tdef.get("fields", {}):
            if fname in schema.get("fields", {}):
                out_fields[fname] = schema["fields"][fname]
    if out_fields:
        out_schema["fields"] = out_fields

    # [type.X] — only selected types
    out_types = {}
    for t in selected:
        tdef = schema.get("type", {}).get(t)
        if tdef:
            out_types[t] = tdef
    if out_types:
        out_schema["type"] = out_types

    # ── queries.toml ──
    out_queries = {}

    # Step 1: find which base queries reference selected types
    included_queries = set()
    for key, val in queries.items():
        if isinstance(val, dict) and "where" in val:
            if _query_refs_type(val, selected):
                included_queries.add(key)

    # Step 2: include base queries
    for key in included_queries:
        out_queries[key] = queries[key]

    # Step 3: include metrics that reference included queries
    metrics = queries.get("metrics", {})
    included_metrics = set()
    for mname, mdef in metrics.items():
        refs = set()
        if isinstance(mdef, dict):
            if "derived" in mdef:
                # extract query names from expression
                refs = set(re.findall(r'[a-z_]+', mdef["derived"])) & included_queries
            elif "ratio" in mdef:
                refs = set(mdef["ratio"]) & included_queries
            elif "avg" in mdef:
                refs = {mdef["avg"]} & included_queries
            elif "sum" in mdef:
                refs = {mdef["sum"]} & included_queries
            elif "max" in mdef:
                refs = {mdef["max"]} & included_queries
            elif "min" in mdef:
                refs = {mdef["min"]} & included_queries
        if refs:
            included_metrics.add(mname)
    if included_metrics:
        out_queries["metrics"] = {m: metrics[m] for m in sorted(included_metrics)}

    # Step 4: include dashboards referencing included queries/metrics
    dashboards = queries.get("dashboards", {})
    included_names = included_queries | included_metrics
    included_dashboards = {}
    for dname, ddef in dashboards.items():
        if not isinstance(ddef, dict):
            continue
        refs = [m for m in ddef.get("metrics", []) if m in included_names]
        entry = {}
        if refs:
            entry["metrics"] = refs
        ulabel = (ddef.get("ungrouped_label") or "").strip()
        if ulabel:
            entry["ungrouped_label"] = ulabel
        groups = ddef.get("groups")
        if isinstance(groups, dict):
            clean_groups = {}
            for gname, gitems in groups.items():
                if isinstance(gitems, str):
                    gitems = [gitems]
                kept = [m for m in gitems if m in included_names]
                if kept:
                    clean_groups[gname] = kept
            if clean_groups:
                entry["groups"] = clean_groups
        if entry:
            included_dashboards[dname] = entry
    if included_dashboards:
        out_queries["dashboards"] = included_dashboards

    # Step 5: include aliases pointing to included queries
    aliases = queries.get("aliases", {})
    included_aliases = {}
    for aname, aval in aliases.items():
        if isinstance(aval, dict) and aval.get("alias") in included_names:
            included_aliases[aname] = aval
        elif isinstance(aval, str) and aval in included_names:
            included_aliases[aname] = {"alias": aval}
    if included_aliases:
        out_queries["aliases"] = included_aliases

    # Step 6: always include due config
    due = queries.get("due")
    if due:
        out_queries["due"] = due

    # ── presets.toml ──
    out_presets = {}
    for name, pdef in presets_raw.items():
        if isinstance(pdef, dict) and pdef.get("type") in selected:
            out_presets[name] = pdef
    out_presets_wrap = {"presets": out_presets} if out_presets else {}

    return {
        "schema": out_schema,
        "queries": out_queries,
        "presets": out_presets_wrap,
        "config": config,
    }


def build_schema_bundle_zip(selected_types):
    """Return (bytes, filename) for a schema share ZIP."""
    import io
    import tomli_w

    bundle = export_schema_bundle(selected_types)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name in ("schema", "queries", "presets", "config"):
            data = bundle[name]
            if not data:
                continue
            stream = io.BytesIO()
            tomli_w.dump(data, stream)
            zf.writestr(f"config/{name}.toml", stream.getvalue())

    ts = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    return buf.getvalue(), f"ptos-schema-share-{ts}.zip"

# --------------------------------------------------
# Display helpers  (currency from config)
# --------------------------------------------------

def currency():
    return get_config().get("display", {}).get("currency", "")

def _indian_commas(n):
    """Format integer with Indian grouping: last 3 digits, then groups of 2."""
    s = str(abs(int(n)))
    if len(s) <= 3:
        result = s
    else:
        result = s[-3:]
        s = s[:-3]
        while s:
            result = s[-2:] + "," + result
            s = s[:-2]
    return ("-" if n < 0 else "") + result

def fmt(n):
    """Format a number with the configured currency symbol."""
    c = currency()
    if c == "₹":
        return c + _indian_commas(n)
    return f"{c}{n}"

def fmt_avg(n):
    c = currency()
    if c == "₹":
        return c + _indian_commas(round(n))
    return f"{c}{n:.0f}"


def date_format():
    """Get configured date format for display."""
    return get_config().get("display", {}).get("date_format", "indian")


def fmt_date(date_obj):
    """Format date object according to configured format.
    
    Supports presets: indian (dd/mm/yyyy), us (mm/dd/yyyy), 
    eu (dd.mm.yyyy), readable (15 Apr 2026), iso (yyyy-mm-dd),
    or custom strftime pattern.
    """
    import datetime as dt
    fmt = date_format()
    
    if fmt == "indian":
        return date_obj.strftime("%d/%m/%Y")
    elif fmt == "us":
        return date_obj.strftime("%m/%d/%Y")
    elif fmt == "eu":
        return date_obj.strftime("%d.%m.%Y")
    elif fmt == "readable":
        return date_obj.strftime("%d %b %Y")
    elif fmt == "iso":
        if isinstance(date_obj, dt.date):
            return date_obj.isoformat()
        else:
            return date_obj.strftime("%Y-%m-%d")
    else:
        # Custom strftime format
        try:
            return date_obj.strftime(fmt)
        except (ValueError, AttributeError):
            # Fallback to ISO format on error
            if isinstance(date_obj, dt.date):
                return date_obj.isoformat()
            else:
                return date_obj.strftime("%Y-%m-%d")


def fmt_datetime(dt_obj):
    """Format datetime object: date part uses configured format, time stays HH:MM."""
    return f"{fmt_date(dt_obj)} {dt_obj.strftime('%H:%M')}"

def _disp(s):
    """Convert underscore-separated value to space-separated for display only.
    Applied at render time; never touches stored values or filter expressions."""
    return str(s).replace("_", " ") if s is not None else ""

# --------------------------------------------------
# Schema helpers
# --------------------------------------------------

def numeric_fields():
    """Return list of field names declared as type=int in schema."""
    if "numeric_fields" not in _CACHE:
        _CACHE["numeric_fields"] = [
            f for f, meta in get_schema().get("fields", {}).items()
            if isinstance(meta, dict) and meta.get("type") == "int"
        ]
    return _CACHE["numeric_fields"]

def datetime_fields():
    """Return list of field names declared as type=datetime in schema."""
    if "datetime_fields" not in _CACHE:
        _CACHE["datetime_fields"] = [
            f for f, meta in get_schema().get("fields", {}).items()
            if isinstance(meta, dict) and meta.get("type") == "datetime"
        ]
    return _CACHE["datetime_fields"]

def non_dimension_fields():
    """Return set of fields marked dimension=false in schema (for show_fields filtering)."""
    return {
        f for f, meta in get_schema().get("fields", {}).items()
        if isinstance(meta, dict) and not meta.get("dimension", True)
    }

def numeric_value(kv):
    """Return the first numeric field value found in kv, or None.
    Used as a fallback when no --sum-field is specified."""
    for f in numeric_fields():
        if f in kv:
            v = kv[f]
            if isinstance(v, list):
                v = v[0]
            if str(v).isdigit():
                return int(v)
    return None

def numeric_value_for(kv, field):
    """Return the integer value of a specific named field from kv, or None."""
    if field not in kv:
        return None
    v = kv[field]
    if isinstance(v, list):
        v = v[0]
    try:
        return int(v)
    except (ValueError, TypeError):
        return None


def derived_fields():
    """Return dict of {field_name: {"expr": str, "rtype": str|None}}.
    Reads both global [fields.X] and type-scoped [type.X.fields.Y] definitions.

    Global:  [fields.net]         derived = "amount - advance"
    Scoped:  [type.prescription.fields.net]  derived = "amount - advance"

    Type-scoped fields are only computed for records of that type.
    """
    if "derived_fields" not in _CACHE:
        schema  = get_schema()
        result  = {}
        # global fields
        for f, meta in schema.get("fields", {}).items():
            if isinstance(meta, dict) and "derived" in meta:
                result[f] = {"expr": meta["derived"], "rtype": None}
        # type-scoped fields
        for rtype, type_schema in schema.get("type", {}).items():
            for f, meta in type_schema.get("fields", {}).items():
                if isinstance(meta, dict) and "derived" in meta:
                    key = f"{rtype}.{f}"
                    result[key] = {"expr": meta["derived"], "rtype": rtype}
        _CACHE["derived_fields"] = result
    return _CACHE["derived_fields"]


def compute_derived(kv, record_date=None):
    """Compute all derived field values for a record kv dict.
    Returns {field_name: value}. None on any error (silent).
    Type-scoped derived fields are only computed for matching record type.
    """
    import re as _re
    import datetime as _dt

    _today  = _dt.date.today()
    rtype   = kv.get("type", "")
    results = {}

    for fname, defn in derived_fields().items():
        expr       = defn["expr"]
        field_rtype = defn["rtype"]

        # skip type-scoped fields that don't match this record's type
        if field_rtype is not None and field_rtype != rtype:
            continue

        # output key — strip "rtype." prefix if present
        out_key = fname.split(".", 1)[1] if "." in fname else fname

        try:
            uses_date  = bool(_re.search(r'\bdate\b', expr))
            uses_today = 'today' in expr

            if uses_date or uses_today:
                if record_date is None:
                    results[out_key] = None
                    continue

                clean_expr = _re.sub(r'(\d+)d\b', r'\1', expr)

                # auto-convert (today - date) to .days for integer comparison
                # handles both "(today - date)" and "today - date" (with word boundaries)
                clean_expr = _re.sub(
                    r'\(?\s*today\s*-\s*date\s*\)?(?!\s*\.)',
                    '(today - date).days',
                    clean_expr
                )

                namespace = {
                    "today":     _today,
                    "date":      record_date,
                    "timedelta": _dt.timedelta,
                }
                for token in _re.findall(r'\b[a-z][a-z0-9_]*\b', clean_expr):
                    if token in ("today", "date", "timedelta", "days"):
                        continue
                    val = kv.get(token)
                    if val is not None:
                        if isinstance(val, list): val = val[0]
                        try: namespace[token] = float(val)
                        except (ValueError, TypeError): pass

                raw = eval(clean_expr, {"__builtins__": {}}, namespace)  # noqa: S307

                if isinstance(raw, _dt.timedelta):
                    results[out_key] = raw.days
                elif isinstance(raw, bool):
                    results[out_key] = "true" if raw else "false"
                elif isinstance(raw, (int, float)):
                    results[out_key] = int(raw) if raw == int(raw) else raw
                else:
                    results[out_key] = str(raw)

            else:
                eval_expr = expr
                tokens = _re.findall(r'[a-z][a-z0-9_]*', expr)
                failed = False
                for token in tokens:
                    val = kv.get(token)
                    if val is None:
                        failed = True; break
                    if isinstance(val, list): val = val[0]
                    try:
                        num = float(val)
                    except (ValueError, TypeError):
                        failed = True; break
                    eval_expr = _re.sub(rf'\b{token}\b', str(num), eval_expr)
                if failed:
                    results[out_key] = None
                    continue
                if not _re.match(r'^[\d\s\.\+\-\*\/\(\)e]+$', eval_expr):
                    results[out_key] = None
                    continue
                raw = float(eval(eval_expr, {"__builtins__": {}}, {}))  # noqa: S307
                results[out_key] = int(raw) if raw == int(raw) else raw

        except Exception:
            results[out_key] = None

    return results

def detect_value_field(results):
    """Return the name of the first numeric field found across results."""
    for line in results:
        _, kv, _ = parse_line(line)
        for f in numeric_fields():
            if f in kv:
                return f
    return None

# --------------------------------------------------
# Time engine
# --------------------------------------------------

def today():
    return dt.date.today()

def parse_date(s):
    """Parse an ISO date string into a date object.
    Accepts YYYY-MM-DD format. Raises ValueError on invalid input."""
    return dt.date.fromisoformat(s)


def parse_from_to(s, as_end=False):
    """Parse a --from/--to argument into a date object.
    Accepts YYYY-MM-DD, YYYY-MM, or YYYY.
    When as_end=True: YYYY → Dec 31, YYYY-MM → last day of month.
    When as_end=False: YYYY → Jan 1, YYYY-MM → 1st of month."""
    if s is None:
        return None
    if re.fullmatch(r"\d{4}", s):
        year = int(s)
        return dt.date(year, 12, 31) if as_end else dt.date(year, 1, 1)
    if re.fullmatch(r"\d{4}-\d{2}", s):
        year, month = map(int, s.split("-"))
        if as_end:
            return dt.date(year + 1, 1, 1) - dt.timedelta(days=1) if month == 12 \
                   else dt.date(year, month + 1, 1) - dt.timedelta(days=1)
        return dt.date(year, month, 1)
    return dt.date.fromisoformat(s)


def month_range(year, month):
    """Return (start_date, end_date) inclusive bounds for a given month.
    Handles December correctly by wrapping to the next year."""
    start = dt.date(year, month, 1)
    end   = dt.date(year + 1, 1, 1) - dt.timedelta(days=1) if month == 12 \
            else dt.date(year, month + 1, 1) - dt.timedelta(days=1)
    return start, end

def quarter_range(year, quarter):
    """Return (start_date, end_date) inclusive bounds for a quarter.
    Quarter is 0-indexed (0 = Jan-Mar, 1 = Apr-Jun, 2 = Jul-Sep, 3 = Oct-Dec)."""
    start_month = quarter * 3 + 1
    start = dt.date(year, start_month, 1)
    end   = dt.date(year + 1, 1, 1) - dt.timedelta(days=1) if start_month + 3 > 12 \
            else dt.date(year, start_month + 3, 1) - dt.timedelta(days=1)
    return start, end

def resolve_cycle(start_day, offset=0):
    """Return (start_date, end_date) for a custom billing cycle.
    A cycle runs from start_day of one month to start_day-1 of the next month.
    offset=0 = current cycle, offset=1 = previous cycle, etc."""
    now = today()
    if now.day >= start_day:
        start = dt.date(now.year, now.month, start_day)
    else:
        prev  = now.replace(day=1) - dt.timedelta(days=1)
        start = dt.date(prev.year, prev.month, start_day)
    for _ in range(offset):
        prev  = start.replace(day=1) - dt.timedelta(days=1)
        start = dt.date(prev.year, prev.month, start_day)
    next_month = (start.replace(day=28) + dt.timedelta(days=4)).replace(day=1)
    end = next_month + dt.timedelta(days=start_day - 1) - dt.timedelta(days=1)
    return start, end

def resolve_date(value):
    """
    Resolve a --date argument to an ISO date string.
    Accepts: YYYY-MM-DD, today, yesterday.
    """
    if value is None:
        return today().isoformat()
    if value == "today":
        return today().isoformat()
    if value == "yesterday":
        return (today() - dt.timedelta(days=1)).isoformat()
    try:
        parse_date(value)
        return value
    except ValueError:
        sys.exit(f"Invalid date '{value}'. Use YYYY-MM-DD, today, or yesterday.")

class TimeCode:
    """Named constants for the short time-range codes used throughout PTOS.
    These mirror the keys of _TIME_ALIASES. Use these instead of bare strings
    so that misspellings become AttributeError rather than silent wrong results."""
    TODAY        = "td"
    YESTERDAY    = "yd"
    THIS_WEEK    = "tw"
    LAST_WEEK    = "lw"
    THIS_MONTH   = "tm"
    LAST_MONTH   = "lm"
    THIS_QUARTER = "tq"
    LAST_QUARTER = "lq"
    THIS_YEAR    = "ty"
    LAST_YEAR    = "ly"
    ALL          = "all"

_TIME_ALIASES = {
    "td":  "today",
    "yd":  "yesterday",
    "tw":  "this-week",
    "lw":  "last-week",
    "tm":  "this-month",
    "lm":  "last-month",
    "tq":  "this-quarter",
    "lq":  "last-quarter",
    "ty":  "this-year",
    "ly":  "last-year",
}

def resolve_time(keyword, cycles):
    """Resolve a time keyword into (start_date, end_date) inclusive bounds.

    Accepted keywords:
      td/today, yd/yesterday, tw/this-week, lw/last-week,
      tm/this-month, lm/last-month, tq/this-quarter, lq/last-quarter,
      ty/this-year, ly/last-year, all,
      YYYY-MM-DD (single day), YYYY-MM (literal month), YYYY (literal year),
      <cycle_name> or <cycle_name>-N (custom cycles from config)."""
    keyword = _TIME_ALIASES.get(keyword, keyword)
    now = today()

    # custom cycles  e.g. "clinic", "clinic-1"
    for name, start_day in cycles.items():
        m = re.fullmatch(rf"{name}(?:-(\d+))?", keyword)
        if m:
            offset = int(m.group(1)) if m.group(1) else 0
            return resolve_cycle(start_day, offset)

    # YYYY
    if re.fullmatch(r"\d{4}", keyword):
        year = int(keyword)
        return dt.date(year, 1, 1), dt.date(year, 12, 31)

    # YYYY-MM
    if re.fullmatch(r"\d{4}-\d{2}", keyword):
        year, month = map(int, keyword.split("-"))
        return month_range(year, month)

    # YYYY-MM-DD
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", keyword):
        d = dt.date.fromisoformat(keyword)
        return d, d

    if keyword == "today":     return now, now
    if keyword == "yesterday": y = now - dt.timedelta(days=1); return y, y
    if keyword == "this-week":
        start = now - dt.timedelta(days=now.weekday())
        return start, start + dt.timedelta(days=6)
    if keyword == "last-week":
        end = now - dt.timedelta(days=now.weekday() + 1)
        return end - dt.timedelta(days=6), end
    if keyword == "this-month":  return month_range(now.year, now.month)
    if keyword == "last-month":
        prev = now.replace(day=1) - dt.timedelta(days=1)
        return month_range(prev.year, prev.month)
    if keyword == "this-quarter":
        return quarter_range(now.year, (now.month - 1) // 3)
    if keyword == "last-quarter":
        q    = (now.month - 1) // 3 - 1
        year = now.year
        if q < 0: q, year = 3, year - 1
        return quarter_range(year, q)
    if keyword == "this-year": return dt.date(now.year, 1, 1), dt.date(now.year, 12, 31)
    if keyword == "last-year": return dt.date(now.year - 1, 1, 1), dt.date(now.year - 1, 12, 31)
    if keyword == "all":       return dt.date.min, dt.date.max

    return month_range(now.year, now.month)

# --------------------------------------------------
# Record parsing
# --------------------------------------------------

def parse_line(line):
    """Parse a log line into (date, kv_dict, note)."""
    main, _, note = line.partition("|")
    parts = main.strip().split()
    if not parts:
        raise ValueError("empty line")
    date  = parts[0]
    kv    = {}
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

def safe_parse_line(line):
    """Like parse_line but returns None on any error instead of raising."""
    try:
        return parse_line(line)
    except Exception:
        return None

def build_record_line(date, record, note=None):
    """Build a log line from its components.
    Format: YYYY-MM-DD key=value key=value ... | note
    Multi-value fields (lists) produce repeated key=value pairs."""
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

def _tok_where(expr):
    """Tokenize a filter expression string into a list of tokens.
    Token types: AND, OR, NOT, LPAREN, RPAREN, COND(string).
    """
    tokens = []
    i = 0
    s = expr.strip()
    while i < len(s):
        if s[i].isspace():
            i += 1
            continue
        if s[i] == '(':
            tokens.append(('LPAREN', '('))
            i += 1
        elif s[i] == ')':
            tokens.append(('RPAREN', ')'))
            i += 1
        elif s[i:i+3].upper() == 'AND' and (i+3 >= len(s) or not s[i+3].isalnum()):
            tokens.append(('AND', 'AND'))
            i += 3
        elif s[i:i+2].upper() == 'OR' and (i+2 >= len(s) or not s[i+2].isalnum()):
            tokens.append(('OR', 'OR'))
            i += 2
        elif s[i:i+3].upper() == 'NOT' and (i+3 >= len(s) or not s[i+3].isalnum()):
            tokens.append(('NOT', 'NOT'))
            i += 3
        else:
            j = i
            in_quote = False
            while j < len(s):
                if s[j] in ('"', "'"):
                    in_quote = not in_quote
                if not in_quote and (s[j].isspace() or s[j] in ('(', ')')):
                    break
                j += 1
            tok = s[i:j].strip('"\'')
            if tok:
                tokens.append(('COND', tok))
            i = j
    return tokens


def _eval_cond(kv, cond):
    """Evaluate a single condition string against kv dict.
    Operators: =  !=  >  <  >=  <=  ~(contains)  !~(not contains)
    Numeric fields coerced to int; date fields coerced to date; else string compare.
    """
    m = re.match(r"(\w+)(!~|!=|>=|<=|~|=|>|<)(.+)", cond)
    if not m:
        return True  # unparseable — skip silently
    key, op, val = m.groups()
    val = val.strip('"\'')

    cur = kv.get(key, "")
    cur_list = cur if isinstance(cur, list) else [cur]

    if op == "~":
        return any(val.lower() in v.lower() for v in cur_list)
    if op == "!~":
        return all(val.lower() not in v.lower() for v in cur_list)

    if key not in kv:
        return False

    if op == "=":
        return val in cur_list
    if op == "!=":
        return val not in cur_list

    # ordered operators — coerce scalar
    # Try: numeric first (covers both schema numeric fields and derived int fields),
    # then date, then fall back to string comparison.
    cur_scalar = cur_list[0] if cur_list else ""
    try:
        cur_scalar, val = float(cur_scalar), float(val)
        # use int if both are whole numbers for cleaner comparison
        if cur_scalar == int(cur_scalar) and float(val) == int(float(val)):
            cur_scalar, val = int(cur_scalar), int(val)
    except (ValueError, TypeError):
        # not numeric — try datetime first, then date
        try:
            cur_scalar = dt.datetime.fromisoformat(str(cur_scalar))
            val        = dt.datetime.fromisoformat(str(val))
        except (ValueError, TypeError):
            try:
                cur_scalar = parse_date(str(cur_scalar))
                val        = parse_date(str(val))
            except (ValueError, TypeError):
                pass  # fall through to string comparison

    ops = {
        ">":  lambda a, b: a > b,
        "<":  lambda a, b: a < b,
        ">=": lambda a, b: a >= b,
        "<=": lambda a, b: a <= b,
    }
    fn = ops.get(op)
    if fn is None:
        return True
    try:
        return fn(cur_scalar, val)
    except TypeError:
        return False


def _parse_expr(tokens, pos):
    """Recursive descent: expr := term (OR term)*"""
    node, pos = _parse_term(tokens, pos)
    while pos < len(tokens) and tokens[pos][0] == 'OR':
        pos += 1
        right, pos = _parse_term(tokens, pos)
        node = ('OR', node, right)
    return node, pos


def _parse_term(tokens, pos):
    """term := factor (AND factor)*"""
    node, pos = _parse_factor(tokens, pos)
    while pos < len(tokens) and tokens[pos][0] == 'AND':
        pos += 1
        right, pos = _parse_factor(tokens, pos)
        node = ('AND', node, right)
    return node, pos


def _parse_factor(tokens, pos):
    """factor := NOT factor | LPAREN expr RPAREN | COND"""
    if pos >= len(tokens):
        return ('COND', ''), pos
    typ, val = tokens[pos]
    if typ == 'NOT':
        child, pos = _parse_factor(tokens, pos + 1)
        return ('NOT', child), pos
    if typ == 'LPAREN':
        node, pos = _parse_expr(tokens, pos + 1)
        if pos < len(tokens) and tokens[pos][0] == 'RPAREN':
            pos += 1
        return node, pos
    if typ == 'COND':
        return ('COND', val), pos + 1
    return ('COND', ''), pos + 1


def _eval_node(node, kv):
    """Walk AST and evaluate against kv dict."""
    kind = node[0]
    if kind == 'COND':
        return _eval_cond(kv, node[1])
    if kind == 'AND':
        return _eval_node(node[1], kv) and _eval_node(node[2], kv)
    if kind == 'OR':
        return _eval_node(node[1], kv) or _eval_node(node[2], kv)
    if kind == 'NOT':
        return not _eval_node(node[1], kv)
    return True


def _is_expression(s):
    """True if string contains boolean keywords or grouping parens."""
    upper = s.upper()
    return (
        '(' in s or ')' in s
        or re.search(r'\bAND\b', upper)
        or re.search(r'\bOR\b',  upper)
        or re.search(r'\bNOT\b', upper)
    )


def apply_where(kv, filters):
    """Return True if kv matches the filter expression(s).

    Two modes — detected automatically:

    Expression mode (single string with AND / OR / NOT / parentheses):
      --where "(category=home OR category=household) AND amount>100"
      --where "NOT stage=closed AND amount>=500"

    Legacy mode (multiple simple conditions, ANDed together — backward compatible):
      --where category=home --where amount>100

    Operators: =  !=  >  <  >=  <=  ~(contains)  !~(not contains)

    Derived fields from schema are computed and merged into kv so they
    can be used in filters just like real fields:
      --where net>1000   (where net = amount - advance)
    """
    if not filters:
        return True

    # merge derived field values into a copy of kv so filters can use them
    dfields = derived_fields()
    if dfields:
        # extract date from kv if available (scan_records passes date in kv context)
        rec_date = kv.get("_date")  # injected by scan_records
        computed = compute_derived(kv, record_date=rec_date)
        kv = dict(kv)
        for fname, val in computed.items():
            if val is not None:
                kv[fname] = str(val) if not isinstance(val, str) else val

    if len(filters) == 1 and _is_expression(filters[0]):
        tokens = _tok_where(filters[0])
        node, _ = _parse_expr(tokens, 0)
        return _eval_node(node, kv)

    # Legacy AND-chain
    for cond in filters:
        tokens = _tok_where(cond)
        if not tokens:
            continue
        if len(tokens) == 1 and tokens[0][0] == 'COND':
            if not _eval_cond(kv, tokens[0][1]):
                return False
        else:
            node, _ = _parse_expr(tokens, 0)
            if not _eval_node(node, kv):
                return False
    return True

# --------------------------------------------------
# Edit / delete engine
# --------------------------------------------------

def find_records_with_location(filters, search=None, start=None, end=None):
    """Scan all log files and return list of (filepath, line_number, raw_line)
    for every record matching filters + optional date range + optional search.
    """
    if start is None: start = dt.date.min
    if end   is None: end   = dt.date.max
    matches = []
    fnames = get_log_files()
    for fname in fnames:
        if fname[:4].isdigit():
            year = int(fname[:4])
            if year < start.year or year > end.year:
                continue
        path = os.path.join(RECORDS_DIR, fname)
        with open(path, encoding="utf-8") as f:
            lines = f.readlines()
        for idx, raw in enumerate(lines):
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            try:
                d, kv, note = parse_line(line)
            except (ValueError, IndexError):
                continue
            if not (start <= d <= end):
                continue
            if search and search.lower() not in line.lower():
                continue
            kv_with_date = dict(kv); kv_with_date["_date"] = d
            if not apply_where(kv_with_date, filters):
                continue
            matches.append((path, idx, line))
    return matches


def rewrite_line_in_file(filepath, old_line, new_line, lineno=None):
    """Replace or delete one exact line in a log file.
    old_line:  the stripped line content (used for verification).
    new_line:  replacement string, or None to delete the line.
    lineno:    0-based index into the file — if provided, targets this line
               directly without searching, enabling safe edits of duplicate lines.
    Backs up the file before writing.
    Raises ValueError if the line cannot be found or verified.
    """
    with open(filepath, encoding="utf-8") as f:
        lines = f.readlines()

    if lineno is not None:
        # precise index — verify content matches as a safety check
        if lineno >= len(lines):
            raise ValueError(f"Line {lineno} out of range in {filepath}")
        if lines[lineno].strip() != old_line:
            raise ValueError(
                f"Line {lineno} content mismatch in {filepath}.\n"
                f"  Expected: {old_line}\n"
                f"  Found:    {lines[lineno].strip()}"
            )
        idx = lineno
    else:
        hits = [i for i, l in enumerate(lines) if l.strip() == old_line]
        if not hits:
            raise ValueError(f"Line not found in {filepath}:\n  {old_line}")
        if len(hits) > 1:
            raise ValueError(
                f"Line appears {len(hits)} times in {filepath} — "
                f"use lineno to target a specific occurrence.\n  {old_line}"
            )
        idx = hits[0]

    if new_line is None:
        lines.pop(idx)
    else:
        lines[idx] = new_line + "\n"

    atomic_write(filepath, "".join(lines))


def apply_set(old_line, set_args, new_note):
    """Build a new record line from old_line by applying --set changes and/or --set-note.
    set_args: list of assignment strings. Three forms:
      key=value   replace field entirely (or set date)
      key+=value  append value to a list field (e.g. tag+=urgent)
      key-=value  remove value from a list field (e.g. tag-=urgent)
    new_note: replacement note string, or None to leave unchanged.
    Returns (new_line, changed_date) where changed_date is the new date string
    if the date field was changed (may require moving to a different year file),
    or None otherwise.
    """
    d, kv, note = parse_line(old_line)
    date_str = str(d)
    changed_date = None

    for item in (set_args or []):
        # detect operator: +=  -=  =  (value may be empty for = to delete field)
        m = re.match(r"(\w+)(\+=|-=|=)(.*)", item)
        if not m:
            sys.exit(f"--set: expected key=value, key+=value, or key-=value — got '{item}'")
        k, op, v = m.groups()

        if op == "=":
            if k == "date":
                try:
                    parse_date(v)
                except ValueError:
                    sys.exit(f"--set date: invalid date '{v}' — use YYYY-MM-DD")
                date_str = v
                changed_date = v
            elif v == "":
                # empty value — delete the field entirely
                kv.pop(k, None)
            else:
                kv[k] = v

        elif op == "+=":
            if k == "date":
                sys.exit("--set: date does not support += modifier")
            cur = kv.get(k)
            if cur is None:
                kv[k] = v                        # field didn't exist — just set it
            elif isinstance(cur, list):
                if v not in cur:
                    kv[k] = cur + [v]            # append only if not already present
            else:
                if cur != v:
                    kv[k] = [cur, v]             # promote scalar to list

        elif op == "-=":
            if k == "date":
                sys.exit("--set: date does not support -= modifier")
            cur = kv.get(k)
            if cur is None:
                pass                             # field not present — nothing to remove
            elif isinstance(cur, list):
                remaining = [x for x in cur if x != v]
                if not remaining:
                    del kv[k]                    # removed last value — drop field entirely
                elif len(remaining) == 1:
                    kv[k] = remaining[0]         # collapse back to scalar
                else:
                    kv[k] = remaining
            else:
                if cur == v:
                    del kv[k]                    # removed only value — drop field

    if new_note is not None:
        note = new_note

    if "id" in kv:
        rid = str(kv["id"])
        old_id = parse_line(old_line)[1].get("id")
        if rid != old_id:
            existing = {item["target"].split(":", 1)[1] for item in list_link_ids()}
            if rid in existing:
                sys.exit(f"id '{rid}' is already in use — pick another.")
    if "links" in kv:
        for tok in _links_list(kv["links"]):
            for subtok in tok.split(","):
                subtok = subtok.strip()
                if subtok and resolve_link(subtok) is None:
                    print(f"Warning: link target '{subtok}' does not resolve — "
                          "saved anyway; lint will flag it as dangling.")

    return build_record_line(date_str, kv, note if note else None), changed_date


def run_set(filters, start, end, set_args, new_note, do_delete, do_all):
    """Core edit/delete workflow called from main().
    1. Find matching records within the date range.
    2. If >1 and not --all: show list and ask user to pick by number.
    3. Show old → new diff and ask confirmation.
    4. Rewrite (or delete) in place; handle cross-year date moves.
    """
    matches = find_records_with_location(filters, start=start, end=end)

    if not matches:
        print("\nNo records found matching the filter.\n")
        return

    # ---- select targets ----
    if do_all:
        targets = matches
    elif len(matches) == 1:
        targets = matches
    else:
        print(f"\n{len(matches)} records matched:\n")
        for i, (fp, ln, line) in enumerate(matches, 1):
            print(f"  [{i}]  {line}")
        print()
        raw = input("Pick number(s) to edit (e.g. 1 or 1,3) or 'all' or Enter to cancel: ").strip()
        if not raw:
            print("Cancelled.")
            return
        if raw.lower() == "all":
            targets = matches
        else:
            try:
                chosen = [int(x.strip()) for x in raw.replace(",", " ").split()]
                targets = [matches[i - 1] for i in chosen]
            except (ValueError, IndexError):
                sys.exit("Invalid selection.")

    # ---- build changes and confirm ----
    plan = []  # (filepath, lineno, old_line, new_line, changed_date)
    for filepath, lineno, old_line in targets:
        if do_delete:
            d, kv, _ = parse_line(old_line)
            rid = kv.get("id")
            rtype = kv.get("type")
            if rid and rtype:
                target = f"{rtype}:{rid}"
                refs = backlink_refs(target)
                if refs:
                    n = len(refs)
                    print(f"Warning: {n} entr{'y' if n == 1 else 'ies'} link to "
                          f"{target} — they will become dangling.")
            plan.append((filepath, lineno, old_line, None, None))
        else:
            new_line, changed_date = apply_set(old_line, set_args, new_note)
            if new_line == old_line:
                print(f"  (no change)  {old_line}")
                continue
            plan.append((filepath, lineno, old_line, new_line, changed_date))

    if not plan:
        print("\nNothing to change.\n")
        return

    print()
    for filepath, lineno, old_line, new_line, changed_date in plan:
        print(f"  file : {os.path.basename(filepath)}")
        print(f"  old  : {old_line}")
        if new_line is None:
            print(f"  new  : [DELETE]")
        else:
            print(f"  new  : {new_line}")
        print()

    confirm = input("Apply? [y/N]: ").strip().lower()
    if confirm != "y":
        print("Cancelled.")
        return

    # ---- apply ----
    # Sort in reverse lineno order so deletions from bottom don't shift
    # the line numbers of records yet to be processed above them.
    plan_sorted = sorted(plan, key=lambda x: (x[0], -(x[1] if x[1] is not None else 0)))
    for filepath, lineno, old_line, new_line, changed_date in plan_sorted:
        if new_line is None:
            rewrite_line_in_file(filepath, old_line, None, lineno=lineno)
            print(f"  Deleted: {old_line}")
        elif changed_date:
            old_year = os.path.basename(filepath)[:4]
            new_year = changed_date[:4]
            rewrite_line_in_file(filepath, old_line, None, lineno=lineno)
            new_path = os.path.join(RECORDS_DIR, f"{new_year}.log")
            atomic_append(new_path, new_line)
            moved = f" (moved {old_year}.log → {new_year}.log)" if old_year != new_year else ""
            print(f"  Updated{moved}: {new_line}")
        else:
            rewrite_line_in_file(filepath, old_line, new_line, lineno=lineno)
            print(f"  Updated: {new_line}")

    print()


# --------------------------------------------------
# Query engine
# --------------------------------------------------

def scan_records(start, end, filters, search, from_file=None, sum_field=None):
    """Scan log files and return (matching_lines, numeric_total).
    from_file: if given, read only that file from records/ folder.
    sum_field: if given, sum this specific field instead of the first numeric field found.
    """
    results = []
    total   = 0
    if from_file:
        # validate — no path separators, must exist in records/
        if any(c in from_file for c in ("/", "\\", " ")):
            sys.exit(f"--file: filename must not contain spaces or path separators: {from_file}")
        fnames = [from_file]
        if not os.path.exists(os.path.join(RECORDS_DIR, from_file)):
            sys.exit(f"--file: '{from_file}' not found in records/ folder")
    else:
        fnames = get_log_files()
    for fname in fnames:
        # skip files whose year cannot overlap the query window
        if fname[:4].isdigit() and start is not None and end is not None:
            year = int(fname[:4])
            if year < start.year or year > end.year:
                continue
        path = os.path.join(RECORDS_DIR, fname)
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                try:
                    d, kv, note = parse_line(line)
                except (ValueError, IndexError):
                    continue  # skip malformed lines silently
                if not (start <= d <= end):
                    continue
                if search and not _glob_match(search, line):
                    continue
                # inject date for derived field date arithmetic
                kv_with_date = dict(kv)
                kv_with_date["_date"] = d
                if not apply_where(kv_with_date, filters):
                    continue
                results.append(line)
                val = numeric_value_for(kv, sum_field) if sum_field else numeric_value(kv)
                if val is not None:
                    total += val
    return results, total

# --------------------------------------------------
# Cross-record links (type:id)
# --------------------------------------------------

_LINK_RE = re.compile(r'\b(links|id)=([^\s|]+)')


def generate_id(length=6):
    """Generate a short random id (lowercase alphanumeric)."""
    import secrets
    alphabet = "abcdefghjkmnpqrstuvwxyz23456789"
    return "".join(secrets.choice(alphabet) for _ in range(length))


def generate_unique_id(length=6, max_attempts=5):
    """Generate a random id guaranteed not to collide with any existing
    record/todo id. sys.exit if a unique id can't be found quickly."""
    existing = {item["target"].split(":", 1)[1] for item in list_link_ids()}
    for _ in range(max_attempts):
        candidate = generate_id(length)
        if candidate not in existing:
            return candidate
    sys.exit("Could not generate a unique id after several attempts — "
             "this should be extremely rare; try again.")


def split_link_target(target):
    """Split a 'type:id' link target into (type, id).
    journal targets are 'journal:YYYY-MM-DD'. Returns None if malformed."""
    if not target or ":" not in target:
        return None
    rtype, _, rid = target.partition(":")
    rtype = rtype.strip().lower()
    rid = rid.strip()
    if not rtype or not rid:
        return None
    return rtype, rid


def _links_list(value):
    """Normalise a links value (string or list) into a list of tokens."""
    if value is None:
        return []
    if isinstance(value, list):
        return [str(v) for v in value]
    return [str(value)]


def resolve_link(target):
    """Resolve a 'type:id' link target to its source location.
    Returns a dict {kind, type, id, filepath, lineno, line} or None.
    Records scan .log files for id=<id>; todos scan todo.txt/done.txt
    for id:<id>; journal targets resolve if the date file exists."""
    parts = split_link_target(target)
    if not parts:
        return None
    rtype, rid = parts

    if rtype == "journal":
        if not (len(rid) == 10 and rid[4] == "-" and rid[7] == "-"):
            return None
        path = _journal_path(rid)
        if not os.path.isfile(path):
            return None
        return {"kind": "journal", "type": "journal", "id": rid,
                "filepath": path, "lineno": 1, "line": ""}

    if rtype == "todo":
        for tpath in (TODO_PATH, DONE_PATH):
            if not os.path.isfile(tpath):
                continue
            with open(tpath, encoding="utf-8") as f:
                for lineno, line in enumerate(f, start=1):
                    line = line.rstrip("\n")
                    if re.search(rf"\bid:{re.escape(rid)}(?:\s|$)", line):
                        return {"kind": "todo", "type": "todo", "id": rid,
                                "filepath": tpath, "lineno": lineno, "line": line}
        return None

    if rtype == "note":
        for root, _, files in os.walk(NOTES_DIR):
            for fname in files:
                if fname == "template.md" or not fname.endswith(".md"):
                    continue
                fpath = os.path.join(root, fname)
                with open(fpath, encoding="utf-8") as f:
                    first_line = f.readline()
                if f"ptos-id: {rid}" in first_line:
                    return {"kind": "note", "type": "note", "id": rid,
                            "filepath": fpath, "lineno": 1,
                            "line": first_line.rstrip()}
        return None

    hits = find_records_with_location([f"type={rtype}", f"id={rid}"])
    if not hits:
        return None
    filepath, lineno, raw = hits[0]
    return {"kind": "record", "type": rtype, "id": rid,
            "filepath": filepath, "lineno": lineno, "line": raw}


def list_link_ids():
    """Return all (type, id) targets currently present in records and todos,
    sorted, deduplicated. Used by autocomplete and the link picker."""
    seen = set()
    out = []
    for filepath, lineno, raw in find_records_with_location([], search=None):
        d, kv, _ = parse_line(raw)
        rid = kv.get("id")
        rtype = kv.get("type")
        if rid and rtype:
            key = f"{rtype}:{rid}"
            if key not in seen:
                seen.add(key)
                out.append({"target": key, "kind": "record",
                            "date": str(d), "line": raw.strip()})
    for tpath in (TODO_PATH, DONE_PATH):
        if not os.path.isfile(tpath):
            continue
        with open(tpath, encoding="utf-8") as f:
            for lineno, line in enumerate(f, start=1):
                m = re.search(r'\bid:(\S+)', line)
                if m:
                    key = f"todo:{m.group(1)}"
                    if key not in seen:
                        seen.add(key)
                        out.append({"target": key, "kind": "todo",
                                    "date": "", "line": line.strip()})
    for root, _, files in os.walk(NOTES_DIR):
        for fname in sorted(files):
            if fname == "template.md" or not fname.endswith(".md"):
                continue
            fpath = os.path.join(root, fname)
            nid = _note_id_of(fpath)
            if nid:
                key = f"note:{nid}"
                if key not in seen:
                    seen.add(key)
                    out.append({"target": key, "kind": "note",
                                "date": "", "line": fname})
    out.sort(key=lambda x: x["target"])
    return out


def check_dangling_links():
    """Walk every record/todo/journal carrying links and resolve each target.
    Returns a list of {kind, target, error, filepath, lineno, line} dicts for
    broken links, plus duplicate-id reports for records and todos."""
    problems = []
    seen_ids = {}

    for filepath, lineno, raw in find_records_with_location([], search=None):
        d, kv, _ = parse_line(raw)
        rid = kv.get("id")
        rtype = kv.get("type")
        if rid and rtype:
            key = f"{rtype}:{rid}"
            if key in seen_ids:
                problems.append({
                    "kind": "record", "target": key, "error": "duplicate id",
                    "filepath": filepath, "lineno": lineno, "line": raw.strip()})
            else:
                seen_ids[key] = (filepath, lineno)
        for t in _links_list(kv.get("links")):
            for tok in str(t).split(","):
                tok = tok.strip()
                if not tok:
                    continue
                if resolve_link(tok) is None:
                    problems.append({
                        "kind": "record", "target": tok,
                        "error": "dangling link", "filepath": filepath,
                        "lineno": lineno, "line": raw.strip()})

    for tpath in (TODO_PATH, DONE_PATH):
        if not os.path.isfile(tpath):
            continue
        with open(tpath, encoding="utf-8") as f:
            for lineno, line in enumerate(f, start=1):
                line = line.rstrip("\n")
                m = re.search(r'\bid:(\S+)', line)
                if m:
                    key = f"todo:{m.group(1)}"
                    if key in seen_ids:
                        problems.append({
                            "kind": "todo", "target": key,
                            "error": "duplicate id",
                            "filepath": tpath, "lineno": lineno, "line": line})
                    else:
                        seen_ids[key] = (tpath, lineno)
                for m in re.finditer(r'\blinks:(\S+)', line):
                    for tok in m.group(1).split(","):
                        tok = tok.strip()
                        if not tok:
                            continue
                        if resolve_link(tok) is None:
                            problems.append({
                                "kind": "todo", "target": tok,
                                "error": "dangling link",
                                "filepath": tpath, "lineno": lineno, "line": line})

    for root, _, files in os.walk(NOTES_DIR):
        for fname in sorted(files):
            if fname == "template.md" or not fname.endswith(".md"):
                continue
            fpath = os.path.join(root, fname)
            nid = _note_id_of(fpath)
            if nid:
                key = f"note:{nid}"
                if key in seen_ids:
                    other_fp, other_ln = seen_ids[key]
                    problems.append({
                        "kind": "note", "target": key,
                        "error": "duplicate id",
                        "filepath": fpath, "lineno": 1,
                        "line": f"<!-- ptos-id: {nid} -->"})
                else:
                    seen_ids[key] = (fpath, 1)

    return problems


def backlink_refs(target):
    """Return {kind, filepath, lineno, line} dicts for every record/todo whose
    links= / links: tokens reference the given type:id target."""
    refs = []
    for filepath, lineno, raw in find_records_with_location([], search=None):
        kv = parse_line(raw)[1]
        links = kv.get("links")
        if not links:
            continue
        for tok in _links_list(links):
            if any(t.strip() == target for t in tok.split(",")):
                refs.append({"kind": "record", "filepath": filepath,
                             "lineno": lineno, "line": raw.strip()})
    for tpath in (TODO_PATH, DONE_PATH):
        if not os.path.isfile(tpath):
            continue
        with open(tpath, encoding="utf-8") as f:
            for lineno, line in enumerate(f, start=1):
                line = line.rstrip("\n")
                m = re.search(r'\blinks:(\S+)', line)
                if m and any(t.strip() == target for t in m.group(1).split(",")):
                    refs.append({"kind": "todo", "filepath": tpath,
                                 "lineno": lineno, "line": line})
    return refs


def append_links_to_line(raw_line, new_links):
    """Append a 'links=...' token to a record line, merging with any
    existing links value. Returns the new line."""
    existing = _links_list(parse_line(raw_line)[1].get("links"))
    all_links = []
    for v in existing:
        all_links.extend(tok.strip() for tok in str(v).split(",") if tok.strip())
    for v in new_links:
        all_links.extend(tok.strip() for tok in str(v).split(",") if tok.strip())
    merged = []
    for tok in all_links:
        if tok not in merged:
            merged.append(tok)
    # strip any existing links token, then append merged
    parts = raw_line.split()
    kept = [p for p in parts if not p.startswith("links=")]
    if merged:
        kept.append("links=" + ",".join(merged))
    return " ".join(kept)


def append_record_id(filepath, lineno, old_line, new_id=None):
    """Append id=<id> to a record line in place. Generates one if not given.
    Returns the new id."""
    if not new_id:
        new_id = generate_unique_id()
    line = old_line.rstrip("\n")
    if re.search(r'\bid=(\S+)', line):
        raise ValueError(f"Line already has an id: {line}")
    parts = line.split()
    parts.append(f"id={new_id}")
    rewrite_line_in_file(filepath, old_line, " ".join(parts), lineno=lineno)
    return new_id


def append_todo_id(line, new_id=None):
    """Append id:<id> to a todo.txt line. Generates one if not given.
    Returns (new_line, new_id)."""
    if not new_id:
        new_id = generate_unique_id()
    line = line.rstrip("\n")
    if re.search(r'\bid:(\S+)', line):
        raise ValueError(f"Line already has an id: {line}")
    return line + f" id:{new_id}", new_id


def append_links_to_todo_line(line, new_links):
    """Append/merge links:<tokens> to a todo.txt line. Returns new line."""
    existing = []
    m = re.search(r'\blinks:(\S+)', line)
    if m:
        existing = [t for t in m.group(1).split(",") if t.strip()]
    merged = list(existing)
    for v in new_links:
        for tok in str(v).split(","):
            tok = tok.strip()
            if tok and tok not in merged:
                merged.append(tok)
    parts = [p for p in line.split() if not p.startswith("links:")]
    if merged:
        parts.append("links:" + ",".join(merged))
    return " ".join(parts)


def append_record(line, return_position=False):
    """Append a single log line to the correct yearly file.
    Extracts the year from the line's first 4 characters,
    routes to records/<YEAR>.log, and writes atomically.
    Creates the records directory and yearly file if missing.

    If return_position=True, returns (filepath, lineno) of the
    newly appended line; otherwise returns None."""
    os.makedirs(RECORDS_DIR, exist_ok=True)
    year = line[:4]
    path = os.path.join(RECORDS_DIR, f"{year}.log")
    
    # Read existing content and prepare new content
    existing = ""
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            existing = f.read()
    
    # Strip trailing blank lines and append
    stripped = existing.rstrip("\n\r ")
    if stripped != existing:
        new_content = stripped + "\n" + line + "\n"
    else:
        new_content = existing + line + "\n"
    
    # The appended line is the last physical line before the trailing ""
    lineno = len(new_content.split("\n")) - 2
    atomic_write(path, new_content)
    if return_position:
        return path, lineno

# --------------------------------------------------
# Validation
# --------------------------------------------------

def _get_field_options(schema, type_schema, field, record):
    """
    Return the valid options list for a field given the current record state.
    Returns None for free-text fields or fields with no defined options.
    """
    field_def = type_schema.get("fields", {}).get(field, {})

    # shared reference
    if "use" in field_def:
        key        = field_def["use"].split(".", 1)[1]
        shared_def = schema.get("shared", {}).get(key, {})
        opts       = shared_def.get("options")
        return opts if isinstance(opts, list) else None

    opts = field_def.get("options")

    # flat list
    if isinstance(opts, list):
        return opts

    # parent-dependent
    if isinstance(opts, dict):
        parent = field_def.get("parent")
        if parent:
            parent_val = record.get(parent)
            return opts.get(parent_val, [])
        return None

    # global_fields fallback — field not in type schema, check [global_fields]
    gf = schema.get("global_fields", {}).get(field, {})
    if isinstance(gf, dict) and "options" in gf:
        return gf["options"]

    return None

def validate_record(schema, record):
    """Validate a record dict against the schema. Returns list of error strings.
    Checks: type is allowed, required fields present, int fields valid,
    datetime fields valid ISO, field names known, option values valid,
    conditional requirements satisfied. Empty list = valid."""
    problems = []
    rtype    = record.get("type")

    allowed = schema.get("types", {}).get("allowed")
    if allowed is None:
        sys.exit("schema.toml is missing [types] allowed = [...]\nAdd a [types] section listing your record types.")
    if rtype not in allowed:
        problems.append(f"Invalid type '{rtype}' — allowed: {', '.join(str(a) for a in allowed)}")
        return problems

    type_schema = schema.get("type", {}).get(rtype, {})

    # required fields  (now a flat list, not a nested dict)
    for f in type_schema.get("required", []):
        if f not in record:
            problems.append(f"Missing required field: {f}")

    # integer fields  (from global [fields] metadata)
    for field, meta in schema.get("fields", {}).items():
        if isinstance(meta, dict) and meta.get("type") == "int" and field in record:
            if not str(record[field]).isdigit():
                problems.append(f"Field '{field}' must be integer")

    # datetime fields — validate ISO format YYYY-MM-DDTHH:MM
    for field, meta in schema.get("fields", {}).items():
        if isinstance(meta, dict) and meta.get("type") == "datetime" and field in record:
            try:
                dt.datetime.fromisoformat(str(record[field]))
            except (ValueError, TypeError):
                problems.append(
                    f"Field '{field}' must be datetime format YYYY-MM-DDTHH:MM "
                    f"(e.g. 2026-04-20T10:30) — got '{record[field]}'"
                )

    # allowed field names
    allowed_fields = {"type", "tag", "id", "links"}
    allowed_fields.update(schema.get("fields", {}).keys())
    allowed_fields.update(type_schema.get("required", []))
    allowed_fields.update(type_schema.get("fields", {}).keys())
    allowed_fields.update(type_schema.get("conditions", {}).keys())
    allowed_fields.update(schema.get("global_fields", {}).keys())
    for f in record:
        if f not in allowed_fields:
            problems.append(f"Unknown field '{f}'")

    # field value validation  (check against options where defined)
    # fields with no options defined in schema are treated as free-text — skip silently
    for field, value in record.items():
        if field == "type":
            continue
        opts = _get_field_options(schema, type_schema, field, record)
        if opts is None:
            continue
        values = value if isinstance(value, list) else [value]
        for v in values:
            if str(v) not in [str(o) for o in opts]:
                problems.append(f"Invalid value '{v}' for field '{field}'")

    # conditional required
    for field, rule in type_schema.get("conditions", {}).items():
        condition = rule.get("when", {})
        if all(record.get(k) == v for k, v in condition.items()):
            if field not in record:
                problems.append(f"Field '{field}' required when {condition}")

    return problems


def validate_schema_structure(schema):
    """Validate schema.toml structure and return a list of error strings
    (empty list = schema is valid). Checks:
      - Every [types].allowed type has a [type.X] section
      - Field types are int, string, or datetime
      - required fields have a [type.X.fields.Y] definition
      - parent references point to an existing field
      - use references point to an existing [shared.X] key
      - conditions reference existing fields
    """
    issues = []
    valid_field_types = {"int", "string", "datetime", "bool"}

    # --- [types] section ---
    if "types" not in schema or not isinstance(schema.get("types"), dict):
        issues.append("Missing [types] section")
        return issues
    types_allowed = schema["types"].get("allowed", [])
    if not isinstance(types_allowed, list):
        issues.append("[types].allowed must be a list")
        return issues

    # --- global [fields] type checks ---
    for fname, fdef in schema.get("fields", {}).items():
        ft = fdef.get("type")
        if ft is not None and ft not in valid_field_types:
            issues.append(f"[fields.{fname}]: unknown type '{ft}' (expected int, string, or datetime)")

    # --- [global_fields] type checks ---
    for fname, fdef in schema.get("global_fields", {}).items():
        ft = fdef.get("type")
        if ft is not None and ft not in valid_field_types:
            issues.append(f"[global_fields.{fname}]: unknown type '{ft}' (expected int, string, or datetime)")

    # --- [shared] type checks ---
    for fname, fdef in schema.get("shared", {}).items():
        ft = fdef.get("type")
        if ft is not None and ft not in valid_field_types:
            issues.append(f"[shared.{fname}]: unknown type '{ft}' (expected int, string, or datetime)")

    # --- per-type checks ---
    all_types = schema.get("type", {})
    for t in types_allowed:
        if t not in all_types:
            issues.append(f"Type '{t}' is in [types].allowed but has no [type.{t}] section")

    all_known_fields = set(schema.get("fields", {}).keys()) | set(schema.get("global_fields", {}).keys())

    for tname, tschema in all_types.items():
        type_fields = tschema.get("fields", {})

        # required fields must have a field definition
        for req in tschema.get("required", []):
            if req not in type_fields and req not in all_known_fields:
                issues.append(f"Type '{tname}': required field '{req}' has no [type.{tname}.fields.{req}] or [global_fields.{req}] definition")

        # per-type field checks
        for fname, fdef in type_fields.items():
            ft = fdef.get("type")
            if ft is not None and ft not in valid_field_types:
                issues.append(f"Type '{tname}': field '{fname}' has unknown type '{ft}' (expected int, string, or datetime)")

            parent = fdef.get("parent")
            if parent is not None and parent not in type_fields:
                issues.append(f"Type '{tname}': field '{fname}' parent='{parent}' but '{parent}' has no [type.{tname}.fields.{parent}] definition")

            use = fdef.get("use")
            if use is not None:
                parts = str(use).split(".", 1)
                if len(parts) != 2:
                    issues.append(f"Type '{tname}': field '{fname}' use='{use}' — expected format 'shared.NAME'")
                else:
                    shared_key = parts[1]
                    if shared_key not in schema.get("shared", {}):
                        issues.append(f"Type '{tname}': field '{fname}' references [shared.{shared_key}] which doesn't exist")

        # tags: check trigger fields exist
        for tag_field, tag_opts in tschema.get("tags", {}).items():
            if tag_field not in type_fields and tag_field not in all_known_fields:
                issues.append(f"Type '{tname}': tags section references field '{tag_field}' with no [type.{tname}.fields.{tag_field}] definition")

            # if options is a dict (parent-dependent), check the parent field
            if isinstance(tag_opts, dict):
                for parent_val, _ in tag_opts.items():
                    pass  # parent values are free-form, not checked

        # conditions: check when-fields exist
        for cond_field, cond_rule in tschema.get("conditions", {}).items():
            condition = cond_rule.get("when", {}) if isinstance(cond_rule, dict) else {}
            for when_field in condition:
                if when_field not in type_fields and when_field not in all_known_fields:
                    issues.append(f"Type '{tname}': condition on '{cond_field}' references field '{when_field}' with no definition")

    return issues


def lint_records(records, schema):
    """Validate all records. Returns set of log file paths containing errors."""
    total_errors   = 0
    total_warnings = 0
    total_checked  = 0
    type_counts    = {}
    error_files    = set()

    for line in records:
        if not line.strip():
            continue
        total_checked += 1
        d, kv, note = parse_line(line)
        rtype = kv.get("type", "unknown")
        type_counts[rtype] = type_counts.get(rtype, 0) + 1
        anatomy_errors   = []
        anatomy_warnings = []

        if d == dt.date.min:
            anatomy_errors.append("ERROR: missing or malformed date")
        if "type" not in kv:
            anatomy_errors.append("ERROR: missing type field")
        if "tag" not in kv:
            anatomy_warnings.append("WARNING: no tag")
        if not note or not note.strip():
            anatomy_warnings.append("WARNING: no note")

        schema_problems = validate_record(schema, kv)

        has_issue = anatomy_errors or anatomy_warnings or schema_problems
        if has_issue:
            print(f"\n{'─' * 60}")
            print(line)
            for msg in anatomy_errors:
                print(f"  ✖ {msg}"); total_errors += 1
            for msg in schema_problems:
                print(f"  ✖ {msg}"); total_errors += 1
            for msg in anatomy_warnings:
                print(f"  ⚠ {msg}"); total_warnings += 1
            if d != dt.date.min:
                error_files.add(os.path.join(RECORDS_DIR, f"{d.year}.log"))

    type_summary = "  ".join(f"{t}:{n}" for t, n in sorted(type_counts.items()))
    print(f"\nChecked {total_checked} record(s) across {len(type_counts)} type(s)  [{type_summary}]")

    for link_issue in check_dangling_links():
        total_errors += 1
        print(f"\n{'─' * 60}")
        print(link_issue.get("line", ""))
        print(f"  ✖ {link_issue['error']}: {link_issue['target']}")
        error_files.add(link_issue.get("filepath", ""))

    print()
    if total_errors == 0 and total_warnings == 0:
        print("✔ All records clean — no errors or warnings")
    else:
        if total_errors:   print(f"✖ {total_errors} error(s) found")
        if total_warnings: print(f"⚠ {total_warnings} warning(s) found")
    print()
    return error_files

def lint_all_records():
    """Lint all records and return structured data for web UI.
    Returns dict with: clean, checked, error_count, warning_count, type_counts, errors, warnings
    Each error/warning includes filepath and lineno for linking to editor.
    """
    schema = get_schema()
    
    total_errors        = 0
    total_warnings      = 0
    total_quality_issues = 0
    total_checked  = 0
    type_counts    = {}
    errors_list    = []
    warnings_list  = []
    quality_list   = []
    
    for fname in get_log_files():
        path = os.path.join(RECORDS_DIR, fname)
        if not os.path.exists(path):
            continue
        with open(path, encoding="utf-8") as f:
            for lineno, raw_line in enumerate(f, 1):
                line = raw_line.strip()
                if not line or line.startswith("#"):
                    continue
                total_checked += 1
                try:
                    d, kv, note = parse_line(line)
                except Exception:
                    errors_list.append({
                        "line": line,
                        "problems": ["cannot parse line"],
                        "filepath": fname,
                        "lineno": lineno
                    })
                    continue
                
                rtype = kv.get("type", "unknown")
                type_counts[rtype] = type_counts.get(rtype, 0) + 1
                line_errors    = []
                line_warnings  = []
                line_quality   = []
                
                if d == dt.date.min:
                    line_errors.append("missing or malformed date")
                if "type" not in kv:
                    line_errors.append("missing type field")
                if "tag" not in kv:
                    line_quality.append("no tag")
                if not note or not note.strip():
                    line_quality.append("no note")
                
                schema_problems = validate_record(schema, kv)
                line_errors.extend(schema_problems)
                
                if line_errors:
                    total_errors += len(line_errors)
                    errors_list.append({
                        "line": line,
                        "problems": line_errors,
                        "filepath": fname,
                        "lineno": lineno
                    })
                
                if line_warnings:
                    total_warnings += len(line_warnings)
                    warnings_list.append({
                        "line": line,
                        "problems": line_warnings,
                        "filepath": fname,
                        "lineno": lineno
                    })
                
                if line_quality:
                    total_quality_issues += len(line_quality)
                    quality_list.append({
                        "line": line,
                        "problems": line_quality,
                        "filepath": fname,
                        "lineno": lineno
                    })

    for link_issue in check_dangling_links():
        total_errors += 1
        errors_list.append({
            "line": link_issue.get("line", ""),
            "problems": [f"{link_issue['error']}: {link_issue['target']}"],
            "filepath": os.path.basename(link_issue.get("filepath", "")),
            "lineno": link_issue.get("lineno", 1),
        })

    return {
        "clean": total_errors == 0 and total_warnings == 0,
        "checked": total_checked,
        "error_count": total_errors,
        "warning_count": total_warnings,
        "quality_warning_count": total_quality_issues,
        "type_counts": type_counts,
        "errors": errors_list,
        "warnings": warnings_list,
        "quality_warnings": quality_list,
    }

# --------------------------------------------------
# Analysis  —  group + pivot return data, render separately
# --------------------------------------------------

def group_results(results, fields, sum_field=None):
    """Return (counts, sums, has_numeric) keyed by tuple of field values.
    sum_field: if given, sum this specific field instead of the first numeric field found.
    """
    counts     = {}
    sums       = {}
    has_amount = False
    for line in results:
        d, kv, _ = parse_line(line)
        key_parts = []
        for field in fields:
            if field == "day": key_parts.append(d.strftime("%Y-%m-%d"))
            elif field == "month": key_parts.append(d.strftime("%Y-%m"))
            elif field == "year": key_parts.append(str(d.year))
            else: key_parts.append(str(kv.get(field, "-")))
        key    = tuple(key_parts)
        amount = numeric_value_for(kv, sum_field) if sum_field else numeric_value(kv)
        counts[key] = counts.get(key, 0) + 1
        if amount is not None:
            sums[key]  = sums.get(key, 0) + amount
            has_amount = True
    return counts, sums, has_amount

def pivot_results(results, row_field, col_field, count_mode=False, sort_col=None, sum_field=None):
    """Return pivot table as (table_dict, sorted_cols, row_order).
    sum_field: if given, sum this specific field instead of the first numeric field found.
    """
    table = {}
    cols  = set()

    def resolve_vals(d, kv, field):
        if field == "month": return [d.strftime("%Y-%m")]
        if field == "year":  return [str(d.year)]
        if field in kv:      return kv[field] if isinstance(kv[field], list) else [kv[field]]
        return None

    for line in results:
        d, kv, _ = parse_line(line)
        row_vals = resolve_vals(d, kv, row_field)
        col_vals = resolve_vals(d, kv, col_field)
        if row_vals is None or col_vals is None:
            continue
        amount = numeric_value_for(kv, sum_field) if sum_field else numeric_value(kv)
        for row in row_vals:
            for col in col_vals:
                cols.add(col)
                table.setdefault(row, {})
                table[row][col] = table[row].get(col, 0)
                if count_mode or amount is None:
                    table[row][col] += 1
                else:
                    table[row][col] += int(amount)

    cols     = sorted(cols)
    row_tots = {row: sum(table[row].get(c, 0) for c in cols) for row in table}

    if sort_col and sort_col in cols:
        rows = sorted(table, key=lambda r: table[r].get(sort_col, 0), reverse=True)
    else:
        rows = sorted(row_tots, key=row_tots.get, reverse=True)

    return table, cols, rows

def render_group(counts, sums, has_amount, fields):
    """Print a grouped count/summary table to stdout.
    CLI-only. has_amount controls whether a total column is shown."""
    label_fn = lambda key: "  ".join(_disp(k) for k in key) if isinstance(key, tuple) else _disp(key)

    if has_amount:
        # show count and sum together
        col_w = 7
        print(f"{'':20} {'count':>{col_w}}  {'total':>14}")
        print("-" * 46)
        grand_count = 0
        grand_sum   = 0
        for key in sorted(counts):
            label       = label_fn(key)
            cnt         = counts[key]
            s           = sums.get(key, 0)
            grand_count += cnt
            grand_sum   += s
            print(f"{label:<20} {cnt:>{col_w}}  {fmt(s):>14}")
        print("-" * 46)
        print(f"{'Total':<20} {grand_count:>{col_w}}  {fmt(grand_sum):>14}")
    else:
        grand = 0
        for key in sorted(counts):
            grand += counts[key]
            print(f"{label_fn(key):<20} {counts[key]}")
        print("-" * 40)
        print(f"{'Total':<20} {grand}")

def render_pivot(table, cols, rows, row_field):
    """Print a pivot/cross-tab table to stdout. CLI-only."""
    width = 12
    header = f"{_disp(row_field):15}"
    for c in cols:
        header += f"{_disp(c):>{width}}"
    header += f"{'Total':>{width}}"
    print()
    print(header)
    print("-" * len(header))

    col_totals = {c: 0 for c in cols}
    grand      = 0
    for row in rows:
        row_total = 0
        line      = f"{_disp(row):15}"
        for c in cols:
            val = table[row].get(c, 0)
            line += f"{val:>{width}}"
            row_total      += val
            col_totals[c]  += val
        line  += f"{row_total:>{width}}"
        grand += row_total
        print(line)

    print("-" * len(header))
    total_line = f"{'Total':15}"
    for c in cols:
        total_line += f"{col_totals[c]:>{width}}"
    total_line += f"{grand:>{width}}"
    print(total_line)
    print()

def render_summary(results, start, end, time_label, filters, total, sum_field=None):
    """Print a query summary header to stdout. CLI-only."""
    count = len(results)
    rows  = [("Time range", f"{start} to {end} ({time_label})")]
    if results:
        rows.append(("Data span", f"{results[0].split()[0]} to {results[-1].split()[0]}"))
    rows.append(("Records", count))
    if filters:
        rows.append(("Filters", " ".join(filters)))
    if total > 0:
        total_label = f"Total ({sum_field})" if sum_field else "Total"
        avg_label   = f"Average ({sum_field})" if sum_field else "Average"
        rows.append((total_label, fmt(total)))
        rows.append((avg_label,   fmt_avg(total / count)))
    width = max(len(r[0]) for r in rows)
    print()
    print("-" * 50)
    for label, value in rows:
        print(f"{label:<{width}} : {value}")
    print("-" * 50)

# --------------------------------------------------
# Dashboard engine
# --------------------------------------------------

def _run_base_query(name, queries, start, end, cycles, sum_field=None):
    """Run a named base query. Returns (count, total_sum).
    sum_field controls which field is summed; None defaults to amount."""
    q = queries[name]
    where = q.get("where", "") if isinstance(q, dict) else ""
    if not isinstance(where, str):
        sys.exit(f"Query '{name}': 'where' must be a string, got {type(where).__name__}")
    filters = [where] if where.strip() else []
    results, total = scan_records(start, end, filters, None, sum_field=sum_field)
    return len(results), total

def _run_base_query_lines(name, queries, start, end, cycles):
    """Run a named base query. Returns (raw_lines, total_sum).
    Unlike _run_base_query, returns full raw log lines for post-processing."""
    q = queries[name]
    where = q.get("where", "") if isinstance(q, dict) else ""
    if not isinstance(where, str):
        sys.exit(f"Query '{name}': 'where' must be a string, got {type(where).__name__}")
    filters = [where] if where.strip() else []
    return scan_records(start, end, filters, None)

def run_metric(name, queries, start, end, cycles, color="", reset=""):
    """Compute and print a named metric. Returns True if found, False if not.

    Metric types (defined under [metrics] in queries.toml):
      sum     — sum of a field across matching records
      avg     — average (simple or weighted)
      ratio   — percentage of two sub-metrics
      max/min — extreme values across matching records
      derived — arithmetic expression referencing other metrics"""
    def _lbl(n):
        label = f"{_disp(n):<24}"
        return f"{color}{label}{reset}" if color else label
    metrics = queries.get("metrics", {})
    if name not in metrics:
        return False
    m = metrics[name]

    if "ratio" in m:
        def _resolve_ratio_operand(op, queries, start, end, cycles):
            """Return (count, total) for op — resolving as metric or base query."""
            metrics = queries.get("metrics", {})
            if op in metrics:
                dep = metrics[op]
                if "sum" in dep:
                    return _run_base_query(dep["sum"], queries, start, end, cycles,
                                          sum_field=dep.get("field"))
                elif "avg" in dep:
                    return _run_base_query(dep["avg"], queries, start, end, cycles)
                elif "ratio" in dep:
                    dq1, dq2 = dep["ratio"]
                    dc1, _ = _resolve_ratio_operand(dq1, queries, start, end, cycles)
                    dc2, _ = _resolve_ratio_operand(dq2, queries, start, end, cycles)
                    return dc1, dc2
            return _run_base_query(op, queries, start, end, cycles)

        q1, q2 = m["ratio"]
        c1, t1 = _resolve_ratio_operand(q1, queries, start, end, cycles)
        c2, t2 = _resolve_ratio_operand(q2, queries, start, end, cycles)
        # use totals (sums) when operands are sum metrics, else counts
        v1 = t1 if t1 else c1
        v2 = t2 if t2 else c2
        if v2 == 0:
            print(f"{_lbl(name)} no data")
        else:
            print(f"{_lbl(name)} {(v1/v2)*100:.1f}%  ({v1}/{v2})")
        return True

    if "avg" in m:
        unit_field   = m.get("unit_field")
        unit_weights = m.get("unit_weights")
        if unit_field and unit_weights:
            # weighted average: divide total by sum of per-record unit weights
            lines, total = _run_base_query_lines(m["avg"], queries, start, end, cycles)
            if not lines:
                print(f"{_lbl(name)} no data")
                return True
            units = 0
            for line in lines:
                _, kv, _ = parse_line(line)
                val = kv.get(unit_field, "")
                if isinstance(val, list):
                    val = val[0]
                units += unit_weights.get(val, 1)
            print(f"{_lbl(name)} {fmt_avg(total / units)}")
        else:
            count, total = _run_base_query(m["avg"], queries, start, end, cycles)
            if count == 0:
                print(f"{_lbl(name)} no data")
            else:
                print(f"{_lbl(name)} {fmt_avg(total / count)}")
        return True

    if "sum" in m:
        sum_field = m.get("field")
        _, total = _run_base_query(m["sum"], queries, start, end, cycles, sum_field=sum_field)
        print(f"{_lbl(name)} {fmt(total)}")
        return True

    if "max" in m or "min" in m:
        key      = "max" if "max" in m else "min"
        lines, _ = _run_base_query_lines(m[key], queries, start, end, cycles)
        if not lines:
            print(f"{_lbl(name)} no data")
            return True
        values = []
        for line in lines:
            _, kv, _ = parse_line(line)
            v = numeric_value(kv)
            if v is not None:
                values.append(v)
        if not values:
            print(f"{_lbl(name)} no data")
        else:
            result = max(values) if key == "max" else min(values)
            print(f"{_lbl(name)} {fmt(result)}")
        return True

    if "derived" in m:
        # Evaluate arithmetic expression referencing other metric names
        # or base queries.
        # e.g.  derived = "income - (expense + investment)"
        expr = m["derived"]
        tokens = re.findall(r'[a-z][a-z0-9_]*', expr)
        resolved = {}
        for token in tokens:
            if token in metrics and token not in resolved:
                # temporarily capture stdout by running the metric and reading raw value
                dep_m = metrics[token]
                
                # Use the dependency metric's own time window, not the parent's
                dep_time = dep_m.get("time", "tm")  # default to "tm" if not specified
                dep_start, dep_end = resolve_time(dep_time, cycles)
                
                if "sum" in dep_m:
                    _, val = _run_base_query(dep_m["sum"], queries, dep_start, dep_end, cycles,
                                            sum_field=dep_m.get("field"))
                elif "ratio" in dep_m:
                    def _res_derived(op):
                        if op in metrics:
                            dm = metrics[op]
                            # Use the sub-metric's own time
                            dm_time = dm.get("time", "tm")
                            dm_start, dm_end = resolve_time(dm_time)
                            if "sum" in dm:
                                _, t = _run_base_query(dm["sum"], queries, dm_start, dm_end, cycles,
                                                       sum_field=dm.get("field"))
                                return t
                        c, _ = _run_base_query(op, queries, start, end, cycles)
                        return c
                    dc1 = _res_derived(dep_m["ratio"][0])
                    dc2 = _res_derived(dep_m["ratio"][1])
                    val = (dc1 / dc2 * 100) if dc2 else 0
                elif "avg" in dep_m:
                    cnt, total = _run_base_query(dep_m["avg"], queries, dep_start, dep_end, cycles)
                    val = (total / cnt) if cnt else 0
                elif "max" in dep_m or "min" in dep_m:
                    key2 = "max" if "max" in dep_m else "min"
                    dep_lines, _ = _run_base_query_lines(dep_m[key2], queries, dep_start, dep_end, cycles)
                    dep_vals = [numeric_value(parse_line(l)[1]) for l in dep_lines]
                    dep_vals = [v for v in dep_vals if v is not None]
                    val = (max(dep_vals) if key2 == "max" else min(dep_vals)) if dep_vals else 0
                else:
                    val = 0
                resolved[token] = val
            elif token in queries and token not in resolved:
                # resolve as base query — use its own time window
                q = queries[token]
                query_name = token
                if isinstance(q, dict) and "alias" in q:
                    target = q["alias"]
                    if target in queries:
                        query_name = target
                q_resolved = queries.get(query_name, {})
                
                # Use query's own time if specified
                q_time = q_resolved.get("time", "tm") if isinstance(q_resolved, dict) else "tm"
                q_start, q_end = resolve_time(q_time, cycles)
                
                if isinstance(q_resolved, dict) and "where" in q_resolved:
                    _, val = _run_base_query(query_name, queries, q_start, q_end, cycles)
                    resolved[token] = val
                else:
                    resolved[token] = 0
        
        # Add special tokens for date/day arithmetic
        import calendar as _cal
        now = dt.date.today()
        month_days = _cal.monthrange(now.year, now.month)[1]
        month_day = now.day
        
        # Try to use first configured cycle
        cycle_start_day = None
        for _name, day in cycles.items():
            cycle_start_day = day
            break
        
        if cycle_start_day:
            if now.day >= cycle_start_day:
                cycle_start = dt.date(now.year, now.month, cycle_start_day)
            else:
                prev = now.replace(day=1) - dt.timedelta(days=1)
                cycle_start = dt.date(prev.year, prev.month, cycle_start_day)
            next_month = cycle_start.replace(day=28) + dt.timedelta(days=4)
            next_cycle_start = next_month.replace(day=cycle_start_day)
            cycle_end = next_cycle_start - dt.timedelta(days=1)
            cycle_days = (cycle_end - cycle_start).days + 1
            cycle_day = (now - cycle_start).days + 1
        else:
            cycle_days = month_days
            cycle_day = month_day
        
        resolved['cycle_day'] = cycle_day
        resolved['cycle_days'] = cycle_days
        resolved['month_day'] = month_day
        resolved['month_days'] = month_days
        
        eval_expr = expr
        for token, val in resolved.items():
            eval_expr = re.sub(rf'\b{token}\b', str(val), eval_expr)
        if not re.match(r'^[\d\s\.+\-*/()e]+$', eval_expr):
            print(f"{_lbl(name)} unsafe: [{eval_expr!r}]")
            return True
        try:
            result = float(eval(eval_expr))  # noqa: S307
            formatted = fmt(int(result)) if result == int(result) else fmt_avg(result)
            print(f"{_lbl(name)} {formatted}")
        except ZeroDivisionError:
            print(f"{_lbl(name)} no data")
        except Exception as e:
            print(f"{_lbl(name)} error: {e}")
        return True

    return False

def run_dashboard(name, queries, start, end, cycles):
    _ANSI = {"accent": "\033[94m", "warn": "\033[93m", "success": "\033[92m", "error": "\033[91m",
             "purple": "\033[95m", "teal": "\033[96m", "rose": "\033[35;1m", "slate": "\033[90m"}
    _RESET = "\033[0m"
    _BOLD  = "\033[1m"
    dashboards = queries.get("dashboards", {})
    if name not in dashboards:
        return False
    try:
        cfg = get_config()
        highlight_map = cfg.get("dashboard", {}).get("highlights", {}).get(name, {})
    except Exception:
        highlight_map = {}
    print(f"\nDashboard: {_disp(name)}")
    print(f"Period:    {start} to {end}")
    print("-" * 40)
    dashdef = dashboards[name]
    group_defs = dashdef.get("groups") or {}
    has_groups = bool(group_defs)
    unlabel = (dashdef.get("ungrouped_label") or "").strip() or None
    ordered = []
    if has_groups:
        grouped = set()
        for gname, gitems in group_defs.items():
            if isinstance(gitems, str):
                gitems = [gitems]
            for item in gitems:
                grouped.add(item)
        for item in dashdef.get("metrics", []):
            if item not in grouped:
                ordered.append((unlabel, item))
        for gname, gitems in group_defs.items():
            if isinstance(gitems, str):
                gitems = [gitems]
            for item in gitems:
                ordered.append((gname, item))
    else:
        ordered = [(unlabel, item) for item in dashdef.get("metrics", [])]
    prev_group = None
    first = True
    for gname, item in ordered:
        if gname != prev_group and (has_groups or unlabel):
            if not first:
                print()
            if gname:
                print(_BOLD + gname + _RESET)
            first = False
            prev_group = gname
        color = _ANSI.get(highlight_map.get(item, ""), "")
        reset = _RESET if color else ""
        if run_metric(item, queries, start, end, cycles, color=color, reset=reset):
            continue
        if item in queries:
            count, total = _run_base_query(item, queries, start, end, cycles)
            suffix = f"  ({fmt(total)})" if total > 0 else ""
            label = f"{_disp(item):<24}"
            if color:
                label = f"{color}{_BOLD}{label}{reset}"
            print(f"{label} {count}{suffix}")
    print()
    return True

# --------------------------------------------------
# Field discovery
# --------------------------------------------------

def show_fields(results):
    """Analyze records and print all discovered fields grouped by type.
    Flags recommended dimension fields and suggests group/pivot commands.
    CLI-only."""
    bad = non_dimension_fields()
    types = {}
    for line in results:
        d, kv, _ = parse_line(line)
        rtype = kv.get("type", "unknown")
        types.setdefault(rtype, {"fields": {}, "counts": {}})
        for k, v in kv.items():
            types[rtype]["fields"].setdefault(k, set())
            types[rtype]["counts"][k] = types[rtype]["counts"].get(k, 0) + 1
            vals = v if isinstance(v, list) else [v]
            for item in vals:
                if len(types[rtype]["fields"][k]) < 5:
                    types[rtype]["fields"][k].add(str(item))

    pivot_pairs = get_config().get("discovery", {}).get("pivot_pairs", [])

    suggested_groups  = []
    suggested_pivots  = []

    print("\nFields by record type\n")
    for rtype in sorted(types):
        print(f"[{rtype}]\n")
        fields = types[rtype]["fields"]
        counts = types[rtype]["counts"]
        good   = []
        for field in sorted(fields):
            unique = len(fields[field])
            total  = counts[field]
            ratio  = unique / total if total else 1
            is_dim = field not in bad and not field.endswith("_id") and ratio < 0.4
            star   = "★ " if is_dim else "  "
            if is_dim:
                good.append(field)
            print(f"{star}{_disp(field):12} {', '.join(_disp(v) for v in sorted(fields[field]))}")
        print()
        for f in good[:3]:
            suggested_groups.append(f"ptos -y {rtype} -G {f}")
        for a, b in pivot_pairs:
            if a in good and b in good:
                suggested_pivots.append(f"ptos -y {rtype} -v {a} {b}")

    print("★ = recommended dimension\n")
    if suggested_groups:
        print("Suggested group commands\n")
        for cmd in suggested_groups[:6]: print(cmd)
        print()
    if suggested_pivots:
        print("Suggested pivot commands\n")
        for cmd in suggested_pivots: print(cmd)
        print()

# --------------------------------------------------
# Interactive prompts
# --------------------------------------------------

def choose_from_list(prompt, options, default=None):
    while True:
        print(f"\n{prompt}")
        for i, opt in enumerate(options, 1):
            marker = "   ← default" if opt == default else ""
            print(f"{i}) {opt}{marker}")
        choice = input("\nEnter number: ").strip()
        if not choice and default in options:
            return default
        if choice.isdigit() and 1 <= int(choice) <= len(options):
            return options[int(choice) - 1]

def choose_from_list_optional(prompt, options, default=None):
    """Like choose_from_list but Enter with no input skips (returns empty string).
    When default is provided and valid, Enter accepts it instead of skipping."""
    print(f"\n{prompt} (Enter to skip):")
    for i, opt in enumerate(options, 1):
        print(f"  {i}) {opt}")
    while True:
        raw = input("> ").strip()
        if not raw:
            return default if default in options else ""
        if raw.isdigit() and 1 <= int(raw) <= len(options):
            return options[int(raw) - 1]
        if raw in options:
            return raw
        print(f"  Enter a number 1–{len(options)} or press Enter to skip.")

def input_text(prompt, default=None):
    while True:
        suffix = f" [{default}]" if default else ""
        val = input(f"\n{prompt}{suffix}: ").strip()
        if not val and default is not None:
            return default
        if val:
            return val.replace(" ", "_")

def input_int(prompt, default=None):
    while True:
        suffix = f" [{default}]" if default else ""
        val = input(f"\n{prompt}{suffix}: ").strip()
        if not val and default is not None:
            return str(default)
        if val.isdigit():
            return val

def input_date():
    default = today().isoformat()
    while True:
        val = input(f"\nDate [{default}]: ").strip()
        if not val:
            return default
        try:
            parse_date(val)
            return val
        except ValueError:
            print("Invalid date format (YYYY-MM-DD)")

def input_tags(allowed_tags):
    """Show tag options once. Accept numbers (space/comma separated), custom text, or Enter to skip.
    Returns (selected_tags, new_tags) where new_tags are not in allowed_tags.
    """
    if not allowed_tags:
        # no schema tags — just prompt for free text
        val = input("\nTags (comma separated, or Enter to skip): ").strip()
        if not val:
            return [], []
        tags = [t.strip().replace(" ", "_") for t in val.split(",") if t.strip()]
        return tags, tags  # all are new when no schema tags exist

    print("\nTag options (pick numbers, add custom, or Enter to skip):")
    for i, t in enumerate(allowed_tags, 1):
        print(f"  {i}) {t}")
    print("  Enter numbers separated by spaces/commas, custom words, or mix")
    print("  Example: 1 3 or auto,bus or 1 petrol or quick delivery (becomes quick_delivery)")

    val = input("\nTags: ").strip()
    if not val:
        return [], []

    tags = []
    # if input contains commas, treat as comma-separated (spaces within = underscores)
    # otherwise treat as space-separated tokens (numbers or single words)
    if "," in val:
        parts = val.split(",")
        for part in parts:
            part = part.strip()
            if not part:
                continue
            if part.isdigit():
                i = int(part)
                if 1 <= i <= len(allowed_tags):
                    t = allowed_tags[i - 1]
                    if t not in tags:
                        tags.append(t)
            else:
                tokens = part.split()
                if tokens and all(tok.isdigit() for tok in tokens):
                    for tok in tokens:
                        i = int(tok)
                        if 1 <= i <= len(allowed_tags):
                            t = allowed_tags[i - 1]
                            if t not in tags:
                                tags.append(t)
                else:
                    match = next((t for t in allowed_tags if t.lower() == part.lower()), None)
                    t = match if match else part.replace(" ", "_")
                    if t not in tags:
                        tags.append(t)
    else:
        # separate numeric tokens (schema picks) from word tokens (custom tag)
        tokens     = val.split()
        num_tokens = [tok for tok in tokens if tok.isdigit()]
        word_tokens = [tok for tok in tokens if not tok.isdigit()]

        # numeric picks
        for tok in num_tokens:
            i = int(tok)
            if 1 <= i <= len(allowed_tags):
                t = allowed_tags[i - 1]
                if t not in tags:
                    tags.append(t)

        # word tokens: check if it's a single known tag, otherwise join as one custom tag
        if word_tokens:
            joined = "_".join(word_tokens)
            # try matching the joined form or a single word against allowed list
            match = next((t for t in allowed_tags
                          if t.lower() == joined.lower()), None)
            if not match and len(word_tokens) == 1:
                match = next((t for t in allowed_tags
                              if t.lower() == word_tokens[0].lower()), None)
            t = match if match else joined
            if t not in tags:
                tags.append(t)

    new_tags = [t for t in tags if t not in allowed_tags]
    return tags, new_tags

# --------------------------------------------------
# Schema interpreter  (field resolution for interactive add)
# --------------------------------------------------

def resolve_options(schema, type_schema, field):
    """
    Return the options list for a field, resolving shared references
    and parent-independent flat lists.  Returns None for free-text fields.
    """
    field_def = type_schema.get("fields", {}).get(field, {})

    # shared reference  →  use = "shared.X"
    if "use" in field_def:
        ref  = field_def["use"]              # e.g. "shared.source"
        key  = ref.split(".", 1)[1]          # e.g. "source"
        shared_def = schema.get("shared", {}).get(key, {})
        opts = shared_def.get("options")
        return opts if isinstance(opts, list) else None

    opts = field_def.get("options")

    # flat list
    if isinstance(opts, list):
        return opts

    # parent-dependent — caller must use resolve_options_for_value
    if isinstance(opts, dict):
        return None

    return None

def resolve_options_for_value(type_schema, field, parent_value):
    """
    Return the options list for a parent-dependent field given the
    parent's current value.  e.g. category options when domain=self.
    """
    field_def = type_schema.get("fields", {}).get(field, {})
    opts      = field_def.get("options", {})
    if isinstance(opts, dict):
        return opts.get(parent_value, [])
    return []


def _save_schema(schema):
    """Save schema to config/schema.toml using tomli-w with atomic write."""
    try:
        import tomli_w
    except ImportError:
        raise RuntimeError("tomli-w not installed: pip install tomli-w")

    toml_path = os.path.join(CONFIG_DIR, "schema.toml")
    with AtomicWrite(toml_path, "schema") as w:
        tomli_w.dump(schema, w.stream)


def add_type(name, required=None):
    """Add a new record type to schema.toml. sys.exit on invalid name or
    a schema that would fail validate_schema_structure."""
    name = name.strip()
    if not name:
        sys.exit("Error: Type name cannot be empty.")
    if not re.match(r"^[a-z][a-z0-9_]*$", name):
        sys.exit("Error: Invalid type name '%s' — use lowercase letters, digits, underscores." % name)

    schema = get_schema()
    types_allowed = schema.setdefault("types", {}).setdefault("allowed", [])
    if name in types_allowed:
        sys.exit(f"Error: Type '{name}' already exists.")

    req = [r.strip() for r in (required or []) if r.strip()]
    types_allowed.append(name)
    type_entry = {"required": req}
    global_fields = schema.setdefault("global_fields", {})
    type_fields = type_entry.setdefault("fields", {})
    for r in req:
        if r in global_fields or r in type_fields:
            continue
        type_fields[r] = {"type": "string"}
    schema.setdefault("type", {})[name] = type_entry

    issues = validate_schema_structure(schema)
    if issues:
        sys.exit("Schema would be invalid:\n  " + "\n".join(f"  {i}" for i in issues))
    _save_schema(schema)
    print(f"Added type '{name}' (required: {', '.join(req) if req else 'none'}).")


def add_type_field(type_name, field_name, field_type="string", options=None):
    """Add a field to a record type in schema.toml.
    options is an optional flat list of valid values.
    sys.exit on invalid input or a schema that would fail validation."""
    valid = {"int", "string", "datetime", "bool"}
    if field_type not in valid:
        sys.exit("Error: Unknown field type '%s' (expected %s)."
                 % (field_type, ", ".join(sorted(valid))))
    type_name = type_name.strip()
    field_name = field_name.strip()
    if not field_name or not re.match(r"^[a-z][a-z0-9_]*$", field_name):
        sys.exit("Error: Invalid field name '%s' — use lowercase letters, digits, underscores." % field_name)

    schema = get_schema()
    if type_name not in schema.setdefault("type", {}):
        sys.exit(f"Error: Type '{type_name}' not found.")
    fields = schema["type"][type_name].setdefault("fields", {})
    if field_name in fields:
        sys.exit(f"Error: Type '{type_name}' already has field '{field_name}'.")

    field_def = {"type": field_type}
    if options:
        field_def["options"] = list(options)
    fields[field_name] = field_def

    issues = validate_schema_structure(schema)
    if issues:
        sys.exit("Schema would be invalid:\n  " + "\n".join(f"  {i}" for i in issues))
    _save_schema(schema)
    print(f"Added field '{field_name}' (type={field_type}) to type '{type_name}'.")


def remove_type(name):
    """Remove a record type and its definition from schema.toml.
    sys.exit if the type doesn't exist or removal would break the schema."""
    name = name.strip()
    schema = get_schema()
    types_allowed = schema.setdefault("types", {}).setdefault("allowed", [])
    if name not in types_allowed:
        sys.exit(f"Error: Type '{name}' not found.")

    types_allowed.remove(name)
    schema.setdefault("type", {}).pop(name, None)

    issues = validate_schema_structure(schema)
    if issues:
        sys.exit("Schema would be invalid:\n  " + "\n".join(f"  {i}" for i in issues))
    _save_schema(schema)
    recs = find_records_with_location([f"type={name}"])
    if recs:
        ids_count = sum(1 for _, _, raw in recs if parse_line(raw)[1].get("id"))
        print(f"{len(recs)} existing records use type '{name}' "
              f"(id set on {ids_count} of them); they are not modified but "
              "will fail schema validation from now on.")
    print(f"Removed type '{name}'.")


def add_field_option(type_name, field_name, new_option, option_source,
                    parent_field="", parent_value="", shared_key=""):
    """Add a new option to schema.toml and save."""
    schema = get_schema()
    new_opt = new_option.strip().replace(" ", "_")
    if not new_opt:
        return {"success": False, "error": "Empty option"}
    
    if option_source == "shared":
        if not shared_key:
            return {"success": False, "error": "No shared_key"}
        shared_defs = schema.get("shared", {})
        if shared_key not in shared_defs:
            return {"success": False, "error": f"Shared field {shared_key} not found"}
        opts = shared_defs[shared_key].get("options", [])
        if new_opt in opts:
            return {"success": True}
        opts.append(new_opt)
        shared_defs[shared_key]["options"] = sorted(opts)
    
    elif option_source == "parent_dependent":
        if not type_name:
            return {"success": False, "error": "No type_name"}
        type_schema = schema.get("type", {}).get(type_name, {})
        if not type_schema:
            return {"success": False, "error": f"Type {type_name} not found"}
        field_def = type_schema.get("fields", {}).get(field_name, {})
        if not field_def:
            return {"success": False, "error": f"Field {field_name} not found"}
        opts = field_def.get("options", {})
        if not isinstance(opts, dict):
            return {"success": False, "error": "Not a parent-dependent field"}
        if parent_value not in opts:
            return {"success": False, "error": f"Parent value {parent_value} not found"}
        if new_opt in opts[parent_value]:
            return {"success": True}
        opts[parent_value].append(new_opt)
        opts[parent_value] = sorted(opts[parent_value])
    
    elif option_source == "flat":
        if not type_name:
            return {"success": False, "error": "No type_name"}
        type_schema = schema.get("type", {}).get(type_name, {})
        if not type_schema:
            return {"success": False, "error": f"Type {type_name} not found"}
        field_def = type_schema.get("fields", {}).get(field_name, {})
        if not field_def:
            return {"success": False, "error": f"Field {field_name} not found"}
        opts = field_def.get("options", [])
        if not isinstance(opts, list):
            return {"success": False, "error": "Not a flat options field"}
        if new_opt in opts:
            return {"success": True}
        opts.append(new_opt)
        field_def["options"] = sorted(opts)
    
    else:
        return {"success": False, "error": f"Unknown option_source: {option_source}"}
    
    try:
        _save_schema(schema)
    except Exception as e:
        return {"success": False, "error": str(e)}
    
    return {"success": True}


def add_global_field_option(field_name, new_option):
    """Add a new option to a global field in schema.toml."""
    schema = get_schema()
    new_opt = new_option.strip().replace(" ", "_")
    if not new_opt:
        return {"success": False, "error": "Empty option"}
    
    gfields = schema.get("global_fields", {})
    if field_name not in gfields:
        return {"success": False, "error": f"Global field {field_name} not found"}
    
    fdef = gfields[field_name]
    if not isinstance(fdef, dict):
        return {"success": False, "error": "Invalid field definition"}
    
    opts = fdef.get("options", [])
    if not isinstance(opts, list):
        return {"success": False, "error": "Not an options field"}
    
    if new_opt in opts:
        return {"success": True}
    
    opts.append(new_opt)
    fdef["options"] = sorted(opts)
    
    try:
        _save_schema(schema)
    except Exception as e:
        return {"success": False, "error": str(e)}
    
    return {"success": True}


def resolve_field(schema, type_schema, field, record, default=None):
    """Prompt user for a single field value.
    default is shown as the accepted value when the user presses Enter."""
    # integer field  (from global [fields] metadata)
    field_meta = schema.get("fields", {}).get(field, {})
    if isinstance(field_meta, dict) and field_meta.get("type") == "int":
        return input_int(f"Enter {field}", default=default)

    # datetime field — prompt with format hint and validate
    if isinstance(field_meta, dict) and field_meta.get("type") == "datetime":
        while True:
            suffix = f" [{default}]" if default else ""
            raw = input(f"  {field} (YYYY-MM-DDTHH:MM, e.g. 2026-04-20T10:30){suffix}: ").strip()
            if not raw:
                return default if default else ""
            try:
                dt.datetime.fromisoformat(raw)
                return raw
            except ValueError:
                print(f"  Invalid format. Use YYYY-MM-DDTHH:MM (e.g. 2026-04-20T10:30)")

    field_def = type_schema.get("fields", {}).get(field, {})

    # parent-dependent field  (options depend on another field's value)
    if isinstance(field_def.get("options"), dict):
        parent       = field_def["parent"]
        parent_value = record.get(parent)
        options      = resolve_options_for_value(type_schema, field, parent_value)
        if options:
            d = default if default in options else None
            return choose_from_list(f"Select {field}:", options, default=d)
        return input_text(f"Enter {field}", default=default)

    # flat options or shared reference
    options = resolve_options(schema, type_schema, field)
    if options:
        d = default if default in options else None
        return choose_from_list(f"Select {field}:", options, default=d)

    # free text fallback
    return input_text(f"Enter {field}", default=default)

def resolve_tags(schema, type_schema, record):
    """
    Return sorted list of tag options for a record based on field values.
    Reads from  [type.X.tags.fieldname]  options.value = [...]
    """
    allowed_tags = set()
    tag_section  = type_schema.get("tags", {})

    for field, trigger in tag_section.items():
        # field value(s) in the current record
        value = record.get(field)
        if value is None:
            continue
        values   = value if isinstance(value, list) else [value]
        opts_map = trigger.get("options", {})
        for v in values:
            allowed_tags.update(opts_map.get(v, []))

    return sorted(allowed_tags)

def add_tags_to_schema(schema_path, rtype, record, new_tags):
    """Add new tags to schema.toml using tomli-w via _save_schema().
    Finds the best matching type.X.tags.fieldname options.value section
    based on current record field values. Creates section if missing.
    """
    schema = get_schema()
    type_schema = schema.get("type", {}).get(rtype, {})
    tag_section = type_schema.get("tags", {})

    target_field = None
    target_value = None

    for field, trigger in tag_section.items():
        val = record.get(field)
        if val and not isinstance(val, list):
            target_field = field
            target_value = val
            break

    if not target_field:
        for field in type_schema.get("required", []):
            val = record.get(field)
            if val and field != "type":
                target_field = field
                target_value = val
                break

    if not target_field:
        print(f"  Could not determine tag context — skipping schema update.")
        return

    type_key = rtype
    if "type" not in schema:
        schema["type"] = {}
    if type_key not in schema["type"]:
        schema["type"][type_key] = {}
    if "tags" not in schema["type"][type_key]:
        schema["type"][type_key]["tags"] = {}
    if target_field not in schema["type"][type_key]["tags"]:
        schema["type"][type_key]["tags"][target_field] = {}

    field_tags = schema["type"][type_key]["tags"][target_field]
    option_key = target_value
    if option_key not in field_tags:
        field_tags[option_key] = []

    for tag in new_tags:
        ans = input(f"  Add tag '{tag}' to schema under {rtype} › {target_field}={target_value}? (y/N): ").strip().lower()
        if ans != "y":
            continue
        if tag not in field_tags[option_key]:
            field_tags[option_key].append(tag)
            field_tags[option_key] = sorted(field_tags[option_key])

            try:
                _save_schema(schema)
            except Exception as e:
                print(f"  ✘ Failed to save schema: {e}")
                return
            print(f"  ✔ Added '{tag}' to schema.")


def complete_record(schema, record, skip_optional=False, suggest_fn=None):
    """Fill missing required and conditional fields interactively. Returns (record, note).
    When skip_optional=True, skips tags, note, and global fields prompts.
    suggest_fn(rtype, record) may return {field: default_value} — shown as
    the accepted default (Enter picks it) for still-unset fields."""
    rtype = record.get("type")
    if not rtype:
        rtype          = choose_from_list("Select type:", schema["types"]["allowed"])
        record["type"] = rtype

    type_schema = schema["type"][rtype]
    defaults    = suggest_fn(rtype, record) if suggest_fn else {}

    # required fields
    for field in type_schema.get("required", []):
        if field not in record:
            record[field] = resolve_field(schema, type_schema, field, record, defaults.get(field))

    # conditional required  (e.g. fit when outcome=prescribed)
    for field, rule in type_schema.get("conditions", {}).items():
        if all(record.get(k) == v for k, v in rule.get("when", {}).items()):
            if field not in record:
                record[field] = resolve_field(schema, type_schema, field, record, defaults.get(field))

    if skip_optional:
        return record, None

    # tags — always prompt so user can confirm, add to, or clear preset tags
    allowed = resolve_tags(schema, type_schema, record)
    existing_tags = record.get("tag", [])
    if isinstance(existing_tags, str):
        existing_tags = [existing_tags]
    if existing_tags:
        print(f"\nCurrent tags: {', '.join(existing_tags)}")
        print("Press Enter to keep, or enter new tags to replace/extend.")
    tags, new_tags = input_tags(allowed)
    if new_tags and allowed:
        schema_path = SCHEMA_PATH
        add_tags_to_schema(schema_path, rtype, record, new_tags)
        schema.update(get_schema())
    if tags:
        record["tag"] = tags
    elif existing_tags and not tags:
        pass

    note = input("\nAdd note (optional): ").strip()

    # global optional fields — prompt once after note, all skippable
    gfields = get_global_fields(schema)
    if gfields:
        print("\nAdditional info (all optional — press Enter to skip each):")
        for fname, fdef in gfields.items():
            if fname in record:
                continue
            opts = fdef.get("options", []) if isinstance(fdef, dict) else []
            if opts:
                val = choose_from_list_optional(f"  {fname}", opts, defaults.get(fname))
            else:
                suffix = f" [{defaults.get(fname)}]" if defaults.get(fname) else ""
                val = input(f"  {fname}{suffix}: ").strip()
                if not val and defaults.get(fname):
                    val = defaults[fname]
            if val:
                record[fname] = val.replace(" ", "_")

    return record, note


def filters_to_expr(filters):
    """Convert a list of filter conditions to a single expression string.
    Single expression strings are kept as-is.
    Multiple plain conditions are joined with AND.
    Mixed (expression + plain conditions) wraps the expression in parens then ANDs.
    """
    if not filters:
        return ""
    if len(filters) == 1:
        return filters[0]
    parts = []
    for f in filters:
        # wrap sub-expressions in parens if they contain OR (to preserve precedence)
        if _is_expression(f) and re.search(r'\bOR\b', f.upper()):
            parts.append(f"({f})")
        else:
            parts.append(f)
    return " AND ".join(parts)


_filters_to_expr = filters_to_expr


def save_query(name, args, extra_filters):
    """Save a named query to queries.toml from current CLI args using tomli-w.

    where is always saved as a single expression string.
    """
    try:
        import tomli_w
    except ImportError:
        raise RuntimeError("tomli-w not installed: pip install tomli-w")

    queries = get_queries()
    if name in queries:
        ans = input(f"Query '{name}' already exists. Overwrite? (y/N): ").strip().lower()
        if ans != "y":
            print("Cancelled.")
            return

    where_filters = [item for group in (args.where or []) for item in group]
    type_filter = [f"type={args.type}"] if getattr(args, "type", None) else []
    tag_filters = [f"tag={t}" for t in (args.tag or [])]

    all_conditions = where_filters + type_filter + tag_filters
    expr = _filters_to_expr(all_conditions)

    entry = {}
    if expr:
        entry["where"] = expr

    if getattr(args, "date_from", None) or getattr(args, "date_to", None):
        if getattr(args, "date_from", None):
            entry["from"] = args.date_from
        if getattr(args, "date_to", None):
            entry["to"] = args.date_to
    else:
        entry["time"] = args.time

    if getattr(args, "search", None):
        entry["search"] = args.search

    if getattr(args, "group", None):
        entry["group"] = args.group if isinstance(args.group, list) else [args.group]

    if getattr(args, "pivot", None):
        entry["pivot"] = list(args.pivot)
        if getattr(args, "count", False):
            entry["count"] = True
        if getattr(args, "sort", None):
            entry["sort"] = args.sort

    if getattr(args, "trend", None) is not None:
        entry["trend"] = args.trend

    if getattr(args, "sum", False):
        entry["sum"] = True

    queries[name] = entry

    with AtomicWrite(QUERIES_PATH, "queries") as w:
        tomli_w.dump(queries, w.stream)

    print(f"\nQuery '{name}' saved to queries.toml")
    print(f"Run with: ptos -q {name}")

def save_as_preset(name, record, note=None, instant=False):
    """Write a preset to presets.toml using tomli-w.
    If a preset with the same name already exists it is replaced.
    note: optional note string to store alongside the record fields.
    instant: flag the preset for one-click (no form) record saving.
    """
    try:
        import tomli_w
    except ImportError:
        raise RuntimeError("tomli-w not installed: pip install tomli-w")

    presets_path = os.path.join(CONFIG_DIR, "presets.toml")

    # Load existing data
    data = {"presets": {}}
    if os.path.exists(presets_path):
        with open(presets_path, "rb") as f:
            try:
                import tomllib
            except ImportError:
                import tomli as tomllib
            data = tomllib.load(f)

    if "presets" not in data:
        data["presets"] = {}

    # Build new preset entry
    entry = {}
    for k, v in record.items():
        if k == "tag" and isinstance(v, str):
            entry[k] = [v]
        else:
            entry[k] = v
    if note:
        entry["note"] = note
    if instant:
        entry["instant"] = True

    data["presets"][name] = entry

    with AtomicWrite(presets_path, "presets") as w:
        tomli_w.dump(data, w.stream)
    print(f"Preset '{name}' saved to presets.toml")


def delete_preset(name):
    """Delete a preset from presets.toml using tomli-w."""
    try:
        import tomli_w
    except ImportError:
        raise RuntimeError("tomli-w not installed: pip install tomli-w")

    presets_path = os.path.join(CONFIG_DIR, "presets.toml")
    if not os.path.exists(presets_path):
        return

    with open(presets_path, "rb") as f:
        try:
            import tomllib
        except ImportError:
            import tomli as tomllib
        data = tomllib.load(f)

    presets = data.get("presets", {})
    if name not in presets:
        raise ValueError(f"Preset '{name}' not found")

    del presets[name]
    data["presets"] = presets

    with AtomicWrite(presets_path, "presets") as w:
        tomli_w.dump(data, w.stream)
    print(f"Preset '{name}' deleted from presets.toml")


def set_preset_instant(name, instant):
    """Set or clear the `instant` flag on a preset in presets.toml."""
    try:
        import tomli_w
    except ImportError:
        raise RuntimeError("tomli-w not installed: pip install tomli-w")

    presets_path = os.path.join(CONFIG_DIR, "presets.toml")
    if not os.path.exists(presets_path):
        raise ValueError(f"Preset '{name}' not found")

    with open(presets_path, "rb") as f:
        try:
            import tomllib
        except ImportError:
            import tomli as tomllib
        data = tomllib.load(f)

    presets = data.get("presets", {})
    if name not in presets:
        raise ValueError(f"Preset '{name}' not found")

    entry = presets[name]
    if instant:
        entry["instant"] = True
    else:
        entry.pop("instant", None)
    data["presets"] = presets

    with AtomicWrite(presets_path, "presets") as w:
        tomli_w.dump(data, w.stream)


def interactive_add(schema, date=None, save_preset_name=None, suggest_fn=None):
    """Interactive guided record addition.
    Prompts user for all fields, validates, shows preview, asks for
    confirmation, then appends. Optionally saves as a preset.
    suggest_fn(rtype, record) may return {field: default_value} to pre-fill
    prompts from history (see complete_record)."""
    record, note = complete_record(schema, {}, suggest_fn=suggest_fn)
    problems     = validate_record(schema, record)
    if problems:
        sys.exit(problems[0])
    date = date if date else input_date()
    line = build_record_line(date, record, note)
    print("\nRecord preview:\n")
    print(line)
    ans = input("\nSave? (y/N): ").strip().lower()
    if ans != "y":
        print("Cancelled.")
        return
    append_record(line)
    print("Record added.")
    # --save-preset flag skips the prompt and uses the provided name directly
    if save_preset_name:
        save_as_preset(save_preset_name, record)
    else:
        preset_name = input("\nSave as preset? (name or Enter to skip): ").strip().replace(" ", "_")
        if preset_name:
            save_as_preset(preset_name, record)

def quick_add(args):
    """Non-interactive record addition from command-line args.
    Handles: preset listing, alias resolution, multi-record presets,
    single-record presets with optional field overrides."""
    presets = get_presets()
    if not args.preset:
        print("\nAvailable presets:\n")
        if not presets:
            print("  No presets defined yet.")
            print("  Add them to config/presets.toml or use --save-preset after --add.")
            print()
            return
        for name in sorted(presets):
            p = presets[name]
            if isinstance(p, dict) and "alias" in p:
                print(f"  {name} → {p['alias']}")
            elif isinstance(p, dict) and "records" in p:
                items = p["records"]
                names = [x if isinstance(x, str) else "…" for x in items]
                print(f"  {name} [{', '.join(names)}]")
            else:
                print(" ", name)
        print()
        return

    name = args.preset[0]
    if name not in presets:
        sys.exit(f"Unknown preset: {name}")

    # resolve alias
    if isinstance(presets[name], dict) and "alias" in presets[name]:
        target = presets[name]["alias"]
        if target not in presets:
            sys.exit(f"Preset alias '{name}' points to '{target}' which does not exist.")
        name = target

    preset_data = presets[name]

    # ── multi-record preset ───────────────────────────────────────────────────
    if isinstance(preset_data, dict) and "records" in preset_data:
        schema   = get_schema()
        date_str = resolve_date(args.date)
        added    = []

        # records is a list of preset names — each must resolve to a single-record preset
        resolved = []
        for item in preset_data["records"]:
            if not isinstance(item, str):
                sys.exit(f"Preset '{name}': records list must contain preset names (strings), not inline dicts.\n"
                         f"  Define each record as its own preset and reference it by name.")
            if item not in presets:
                sys.exit(f"Preset '{name}': references unknown preset '{item}'")
            ref = presets[item]
            if isinstance(ref, dict) and "alias" in ref:
                target = ref["alias"]
                if target not in presets:
                    sys.exit(f"Preset '{item}' alias points to unknown preset '{target}'")
                ref = presets[target]
            if isinstance(ref, dict) and "records" in ref:
                sys.exit(f"Preset '{name}': nested multi-record presets not supported ('{item}')")
            resolved.append({k: v for k, v in ref.items() if k not in ("use_count", "usage_count")})

        print(f"\nMulti-record preset '{name}' — {len(resolved)} record(s)\n")
        for i, rec_template in enumerate(resolved, 1):
            print(f"── Record {i} ──────────────────────────────")
            record = dict(rec_template)
            record, note = complete_record(schema, record, skip_optional=True)
            problems = validate_record(schema, record)
            if problems:
                sys.exit(f"Record {i}: {problems[0]}")
            line = build_record_line(date_str, record, note if note else args.note)
            append_record(line)
            added.append(line)
            print(f"✔  {line}\n")
        print(f"\n{len(added)} record(s) added.")
        return

    # ── single-record preset ──────────────────────────────────────────────────
    record = {k: v for k, v in preset_data.items() if k not in ("use_count", "usage_count")}
    for item in args.preset[1:]:
        if "=" not in item:
            continue
        k, v = item.split("=", 1)
        if k == "tag":
            record.setdefault("tag", [])
            if isinstance(record["tag"], list):
                record["tag"].append(v)
            else:
                record["tag"] = [record["tag"], v]
        else:
            record[k] = v
    schema       = get_schema()
    record, note = complete_record(schema, record)
    problems     = validate_record(schema, record)
    if problems:
        sys.exit(problems[0])
    line = build_record_line(resolve_date(args.date), record, note if note else args.note)
    append_record(line)
    print("\nRecord added:\n")
    print(line)

# --------------------------------------------------
# Journal
# --------------------------------------------------

def slugify(text):
    """Convert text to a filename-safe slug. 'Hello World!' -> 'hello-world'"""
    text = text.lower().strip()
    text = re.sub(r'[^\w\s-]', '', text)
    text = re.sub(r'[-\s]+', '-', text)
    return text.strip('-') or "untitled"


def get_note_template(category, context=None):
    """Return template content for a note category, with placeholders
    substituted. Falls back to a minimal default if no template exists
    for this category."""
    context = context or {}
    for name in [category, "note"]:
        template_path = os.path.join(TEMPLATE_DIR, f"{name}.md")
        if os.path.exists(template_path):
            with open(template_path, "r", encoding="utf-8") as f:
                content = f.read()
            break
    else:
        content = _load_starter(category) or _load_starter("note")
    for key, val in context.items():
        content = content.replace(f"{{{{{key}}}}}", str(val))
    return content


def get_today_journal():
    """Return the path to today's journal file, creating it from
    template if it doesn't exist. Creates year/month subdirectory as needed."""
    return get_journal_path(today().isoformat())


def get_journal_path(date_str):
    """Return the path to a journal file for the given YYYY-MM-DD date,
    creating it from template if it doesn't exist.
    Creates year/month subdirectory as needed."""
    date_str = date_str[:10]
    month_dir = os.path.join(JOURNAL_DIR, date_str[:4], date_str[5:7])
    os.makedirs(month_dir, exist_ok=True)
    path = os.path.join(month_dir, f"{date_str}.md")
    if not os.path.exists(path):
        content = get_note_template("daily", {"date": date_str})
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
    return path


def get_journal_template_content(date_str):
    """Return template content for a journal date without writing to disk."""
    return get_note_template("daily", {"date": date_str})


def journal_path(date_str):
    """Return the file path for a journal date."""
    return os.path.join(JOURNAL_DIR, date_str[:4], date_str[5:7], f"{date_str}.md")


_journal_path = journal_path


def delete_journal(date_str):
    """Delete a journal file. Cleans empty year/month dirs."""
    path = _journal_path(date_str)
    if not os.path.isfile(path):
        raise FileNotFoundError(f"Journal not found: {date_str}")
    os.remove(path)
    month_dir = os.path.dirname(path)
    if os.path.isdir(month_dir) and not os.listdir(month_dir):
        os.rmdir(month_dir)
        year_dir = os.path.dirname(month_dir)
        if os.path.isdir(year_dir) and not os.listdir(year_dir):
            os.rmdir(year_dir)

# --------------------------------------------------
# Notes
# --------------------------------------------------

def _ensure_notes_dir():
    os.makedirs(NOTES_DIR, exist_ok=True)


def _safe_path(rel_path):
    """Resolve a relative path under NOTES_DIR, rejecting anything that
    escapes it (../, absolute paths, symlink tricks)."""
    _ensure_notes_dir()
    if not rel_path:
        return NOTES_DIR
    full = os.path.normpath(os.path.join(NOTES_DIR, rel_path))
    if not full.startswith(os.path.abspath(NOTES_DIR) + os.sep) \
       and full != os.path.abspath(NOTES_DIR):
        raise PTOSError("Invalid path")
    return full


def _validate_name(name):
    if not name or "/" in name or "\\" in name or name in (".", ".."):
        raise PTOSError("Invalid name")


def list_dir(rel_path=""):
    """Return {folders: [...], files: [...]} for a directory under
    NOTES_DIR. Each entry: {name, rel_path}. template.md is excluded
    from the files list — it's a folder property, not a note."""
    full = _safe_path(rel_path)
    if not os.path.isdir(full):
        raise PTOSError("Folder not found")
    folders, files = [], []
    for name in sorted(os.listdir(full)):
        entry_rel = (rel_path + "/" + name) if rel_path else name
        if os.path.isdir(os.path.join(full, name)):
            folders.append({"name": name, "rel_path": entry_rel})
        elif name.endswith(".md"):
            files.append({"name": name, "rel_path": entry_rel})
    return {"folders": folders, "files": files}


def create_folder(rel_path, name):
    """mkdir under rel_path. name sanitized: no /, no .., no leading dot."""
    _validate_name(name)
    full = _safe_path(os.path.join(rel_path, name))
    try:
        os.makedirs(full, exist_ok=False)
    except FileExistsError:
        raise PTOSError(f"'{name}' already exists")


def create_file(rel_path, name, content):
    """Create name.md (append .md if missing) under rel_path with the
    given content. No date prefix, no auto-slugging."""
    _validate_name(name)
    if not name.endswith(".md"):
        name += ".md"
    full = _safe_path(os.path.join(rel_path, name))
    if os.path.exists(full):
        raise PTOSError(f"'{name}' already exists")
    os.makedirs(os.path.dirname(full), exist_ok=True)
    with open(full, "w", encoding="utf-8") as f:
        f.write(content)


def rename_note(rel_path, new_name):
    """Rename a file or a folder. Works identically for both."""
    _validate_name(new_name)
    full = _safe_path(rel_path)
    parent = os.path.relpath(os.path.dirname(full), NOTES_DIR)
    if parent == ".":
        parent = ""
    new_full = _safe_path((parent + "/" + new_name) if parent else new_name)
    if os.path.exists(new_full):
        raise PTOSError(f"'{new_name}' already exists")
    os.rename(full, new_full)


def note_id_of(fpath):
    """Extract the ptos-id from a note file's first line comment.
    Returns the id string or None."""
    try:
        with open(fpath, encoding="utf-8") as f:
            first_line = f.readline()
        m = re.match(r'<!--\s*ptos-id:\s*(\S+)\s*-->', first_line)
        if m:
            return m.group(1)
    except Exception:
        pass
    return None


_note_id_of = note_id_of


def ensure_note_id(rel_path):
    """Return this note's id, generating and writing one as the first
    line if it doesn't already have one. Called only when a note is
    about to become a link target — never on note creation."""
    full = _safe_path(rel_path)
    with open(full, encoding="utf-8") as f:
        content = f.read()
    m = re.match(r'<!--\s*ptos-id:\s*(\S+)\s*-->', content)
    if m:
        return m.group(1)
    new_id = generate_unique_id()
    with open(full, "w", encoding="utf-8") as f:
        f.write(f"<!-- ptos-id: {new_id} -->\n" + content)
    return new_id


def delete_note_entry(rel_path):
    """Delete a file, or a folder and everything under it. Folder
    delete is destructive and irreversible — route layer must require
    explicit confirmation before calling this."""
    full = _safe_path(rel_path)
    if os.path.isdir(full):
        shutil.rmtree(full)
    else:
        os.remove(full)


def find_parent_template(rel_path):
    """Walk up from rel_path toward NOTES_DIR root, returning the
    nearest ancestor's template.md if one exists. Does not check
    rel_path itself — caller already confirmed that's absent."""
    rel_path = rel_path.replace("/", os.sep)
    parts = rel_path.split(os.sep) if rel_path else []
    while parts:
        parts.pop()
        candidate = os.sep.join(parts)
        tpl_path = os.path.join(NOTES_DIR, candidate, "template.md")
        if os.path.isfile(tpl_path):
            with open(tpl_path, encoding="utf-8") as f:
                return {"rel_path": candidate or ".", "content": f.read()}
    return None


def resolve_new_file_template(rel_path):
    """Called when the user clicks 'New File' in a folder. Returns
    what the route layer needs to decide whether to prompt:
      {source: "local", content: str}                    — silent, no prompt
      {source: "choice", parent: {...} or None}           — prompt needed
    """
    local_path = os.path.join(NOTES_DIR, rel_path, "template.md")
    if os.path.isfile(local_path):
        with open(local_path, encoding="utf-8") as f:
            return {"source": "local", "content": f.read()}
    parent = find_parent_template(rel_path)
    return {"source": "choice", "parent": parent}


# --------------------------------------------------
# Editor
# --------------------------------------------------

def resolve_editor():
    """Return the editor command as a list of args.
    Priority: config.editor.command > $EDITOR > notepad (win) / nvim."""
    cmd = get_config().get("editor", {}).get("command")
    if cmd:
        return cmd.split()
    if os.environ.get("EDITOR"):
        return os.environ["EDITOR"].split()
    return ["notepad"] if os.name == "nt" else ["nvim"]

def edit_target(target, date_str=None):
    """Open a PTOS file in the system editor.
    Targets: records, schema, queries, config, presets, daily.
    Single-letter shortcuts supported (r, s, q, c, p, d/j, x).
    date_str (YYYY-MM-DD) selects the journal file for the daily target."""
    shortcuts = {
        "r": "records", "s": "schema", "q": "queries",
        "c": "config",  "p": "presets", "d": "daily", "j": "daily", "x": "script",
    }
    target = shortcuts.get(target, target) if target else "records"
    paths  = {
        "records": os.path.join(RECORDS_DIR, f"{today().year}.log"),
        "schema":  SCHEMA_PATH,
        "queries": QUERIES_PATH,
        "config":  CONFIG_PATH,
        "presets": PRESETS_PATH,
        "daily":   get_journal_path(date_str) if date_str else get_today_journal(),
        "script":  os.path.abspath(sys.argv[0]),
    }
    if target not in paths:
        sys.exit(f"Unknown edit target: {target}")
    editor = resolve_editor()
    try:
        subprocess.run(editor + [paths[target]])
    except FileNotFoundError:
        sys.exit(f"Editor '{editor[0]}' not found.\nSet [editor] command in config/config.toml or set $EDITOR.")

# --------------------------------------------------
# Init
# --------------------------------------------------

def _load_starter(name):
    """Load starter content from starters/ folder.
    Falls back to a minimal stub if the file is missing."""
    base = STARTER_DIR
    md_names = {"journal", "note", "book", "audiobook", "youtube"}
    fname = f"starter_{name}.md" if name in md_names else f"starter_{name}.toml"
    path = os.path.join(base, fname)
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return f.read()
    stubs = {
        "config":  "[user]\nname = \"User\"\n\n[display]\ncurrency = \"₹\"\ndate_format = \"indian\"\n",
        "schema":  "[types]\nallowed = []\n",
        "queries": "# no starter queries\n",
        "presets": "# no starter presets\n",
        "journal": "---\ndate: {{date}}\nmood: \"\"\nenergy: \"\"\nword: \"\"\n---\n\n# {{date}}\n\n## ARRIVE\n\n### Reality\n\n### Body\n\n### Mood\n\n### Word\n\n### Intention\n\n### Prayer\n\n---\n\n## ENGAGE\n\n### Top 3\n- [ ]\n- [ ]\n- [ ]\n\n### Habits\n- [ ] Prayer\n- [ ] Move\n- [ ] Connect\n- [ ] Learn\n\n---\n\n## RELEASE\n\n### Wins\n\n### Drifted\n\n### Gratitude\n\n### Tomorrow\n",
        "note":    "---\ntitle: {{title}}\ndate: {{date}}\n---\n\n# {{title}}\n\n_Created: {{date}}_\n",
        "book":    "---\ntitle: {{title}}\ndate: {{date}}\nauthor: \"\"\nrating: \"\"\ntags: \"\"\n---\n\n# {{title}}\n\n## Key Takeaways\n\n-\n\n## Favorite Quotes\n\n>\n\n## Would Recommend?\n\n## What I'll Apply\n",
        "audiobook": "---\ntitle: {{title}}\ndate: {{date}}\nauthor: \"\"\nnarrator: \"\"\nrating: \"\"\nduration: \"\"\nspeed: \"1x\"\ntags: \"\"\n---\n\n# {{title}}\n\n## Key Takeaways\n\n-\n\n## Favorite Quotes\n\n>\n\n## Would Recommend?\n\n## What I'll Apply\n",
        "youtube": "---\ntitle: {{title}}\ndate: {{date}}\nchannel: \"\"\nurl: \"\"\nduration: \"\"\ntags: \"\"\n---\n\n# {{title}}\n\n## Key Takeaways\n\n-\n\n## Key Timestamps\n\n- 00:00 —\n\n## Would Rewatch?\n",
    }
    return stubs.get(name, "")

def _write_if_missing(path, content, label):
    if os.path.exists(path):
        print(f"  exists   {label}")
    else:
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"  created  {label}")

def init_ptos():
    """Initialize PTOS directory structure and config files.
    Creates config/, records/, journal/, templates/ directories and
    writes default config.toml, schema.toml, queries.toml, presets.toml,
    daily.md, and the current year's empty record file.
    Safe to re-run — skips existing files."""
    print("\nInitializing PTOS...\n")

    for d in [CONFIG_DIR, RECORDS_DIR, JOURNAL_DIR, TEMPLATE_DIR, TODO_DIR]:
        os.makedirs(d, exist_ok=True)

    _write_if_missing(CONFIG_PATH,  _load_starter("config"),  "config/config.toml")
    _write_if_missing(SCHEMA_PATH,  _load_starter("schema"),  "config/schema.toml")
    _write_if_missing(QUERIES_PATH, _load_starter("queries"), "config/queries.toml")
    _write_if_missing(PRESETS_PATH, _load_starter("presets"), "config/presets.toml")
    _write_if_missing(
        os.path.join(TEMPLATE_DIR, "daily.md"),
        _load_starter("journal"),
        "templates/daily.md"
    )
    _write_if_missing(
        os.path.join(TEMPLATE_DIR, "note.md"),
        _load_starter("note"),
        "templates/note.md"
    )
    for cat in ["book", "audiobook", "youtube"]:
        _write_if_missing(
            os.path.join(TEMPLATE_DIR, f"{cat}.md"),
            _load_starter(cat),
            f"templates/{cat}.md"
        )

    year_log = os.path.join(RECORDS_DIR, f"{today().year}.log")
    if not os.path.exists(year_log):
        open(year_log, "a", encoding="utf-8").close()
        print(f"  created  records/{today().year}.log")
    else:
        print(f"  exists   records/{today().year}.log")

    # Write .ptos_home bootstrap file so PTOS_HOME env var is no longer needed
    if not DESKTOP_MODE:
        import tempfile
        tmp_root = os.path.realpath(tempfile.gettempdir())
        real_base = os.path.realpath(BASE_DIR)
        real_script = os.path.realpath(SCRIPT_DIR)
        in_temp_base = real_base.startswith(tmp_root) or "pytest-of-" in real_base
        in_temp_script = real_script.startswith(tmp_root) or "pytest-of-" in real_script
        if in_temp_base and not in_temp_script:
            print(f"REFUSING to set .ptos_home to a temp directory: {BASE_DIR}")
            print("This looks like a test or debug session, not a real install.")
            print("If this is intentional, set PTOS_HOME manually instead of --init.")
            sys.exit(1)
        bootstrap = os.path.join(SCRIPT_DIR, ".ptos_home")
        with open(bootstrap, "w", encoding="utf-8") as f:
            f.write(BASE_DIR + "\n")
        print(f"  created  {bootstrap}  ->  {BASE_DIR}")

    print("\nDone. Edit config/schema.toml to define your record types.\n")
    
    # Initialize version tracking
    init_version()
    print("Version tracked.")


def set_home(path):
    """Point PTOS at a different data folder.

    - Expands ~ in the path
    - Creates target dir if missing
    - Copies existing data to target, warns if target already has content
    - Writes path to .ptos_home bootstrap file
    """
    import shutil

    path = os.path.expanduser(path)
    target = os.path.abspath(path)

    if target == os.path.abspath(BASE_DIR):
        print(f"  Already pointing at {target}")
        return

    os.makedirs(target, exist_ok=True)

    migrated = []
    skipped = []
    FOLDERS = ["config", "records", "journal", "templates", "todo",
               "exports", "backups", "notes", "scripts"]
    for folder in FOLDERS:
        src = os.path.join(BASE_DIR, folder)
        dst = os.path.join(target, folder)
        if not os.path.isdir(src):
            continue
        if os.path.isdir(dst):
            if os.listdir(dst):
                skipped.append(f"{folder} (destination not empty, left as-is)")
            else:
                shutil.copytree(src, dst, dirs_exist_ok=True)
                migrated.append(folder)
        else:
            shutil.copytree(src, dst)
            migrated.append(folder)

    bootstrap = os.path.join(SCRIPT_DIR, ".ptos_home")

    print(f"\n  .ptos_home  ->  {target}")
    if migrated:
        print(f"  migrated    ->  {', '.join(migrated)}")
    if skipped:
        print(f"  SKIPPED     ->  {', '.join(skipped)}")
        print(f"  WARNING: some folders were not migrated. Review")
        print(f"  {target} manually before restarting the server,")
        print(f"  or your app may start with missing data.")
        confirm = input("\n  Continue anyway and write .ptos_home? [y/N] ")
        if confirm.strip().lower() != "y":
            print("  Aborted. .ptos_home was not changed.")
            return

    with open(bootstrap, "w", encoding="utf-8") as f:
        f.write(target + "\n")
    print(f"\n  Restart the server to use the new data folder.\n")


def _detect_corruption(base_dir, state_file):
    """Compare current file sizes against sizes recorded after last sync.
    Returns list of files that went from non-zero to zero bytes."""
    import json
    _EXCLUDE = {"todo/done.txt"}
    if not os.path.isfile(state_file):
        return []
    with open(state_file, encoding="utf-8") as f:
        last_state = json.load(f)
    concerning = []
    for rel_path, prev in last_state.items():
        if rel_path.startswith("_"):
            continue
        if rel_path in _EXCLUDE:
            continue
        prev_size = prev["size"] if isinstance(prev, dict) else prev
        full_path = os.path.join(base_dir, rel_path)
        if prev_size > 0 and os.path.isfile(full_path) and os.path.getsize(full_path) == 0:
            concerning.append(rel_path)
    return concerning


def _record_sizes(base_dir, state_file, folders):
    """Record current file mtimes and sizes for change detection and corruption detection."""
    import json
    state = {}
    for folder in folders:
        folder_path = os.path.join(base_dir, folder)
        if not os.path.isdir(folder_path):
            continue
        for root, _, files in os.walk(folder_path):
            for fname in files:
                fpath = os.path.join(root, fname)
                rel = os.path.relpath(fpath, base_dir)
                try:
                    st = os.stat(fpath)
                    state[rel] = {"size": st.st_size, "mtime": st.st_mtime}
                except OSError:
                    pass
    state["_last_sync"] = time.time()
    with open(state_file, "w", encoding="utf-8") as f:
        json.dump(state, f)


def _local_changed(state_file, folders):
    """Return True if any synced file changed since last recorded state."""
    import json
    if not os.path.isfile(state_file):
        return True
    with open(state_file, encoding="utf-8") as f:
        state = json.load(f)
    if "_last_sync" not in state:
        return True
    for folder in folders:
        folder_path = os.path.join(BASE_DIR, folder)
        if not os.path.isdir(folder_path):
            continue
        for root, _, files in os.walk(folder_path):
            for fname in files:
                fpath = os.path.join(root, fname)
                rel = os.path.relpath(fpath, BASE_DIR)
                try:
                    st = os.stat(fpath)
                    prev = state.get(rel)
                    if not prev or prev["size"] != st.st_size or prev["mtime"] != st.st_mtime:
                        return True
                except OSError:
                    return True
    return False


def _clear_rclone_bisync_locks():
    import subprocess
    import glob as _glob
    cache_dir = None
    try:
        result = subprocess.run(["rclone", "config", "paths"],
                                capture_output=True, text=True, timeout=10)
        for line in result.stdout.splitlines():
            if "Cache" in line and ":" in line:
                cache_dir = line.split(":", 1)[1].strip()
                break
    except Exception:
        pass
    if not cache_dir:
        cache_dir = os.path.join(os.path.expanduser("~"), ".cache", "rclone")
    bisync_dir = os.path.join(cache_dir, "bisync")
    if os.path.isdir(bisync_dir):
        for f in _glob.glob(os.path.join(bisync_dir, "*.lck")):
            try:
                os.remove(f)
            except OSError:
                pass


def _pid_is_running(pid):
    import errno
    try:
        os.kill(pid, 0)
        return True
    except OSError as e:
        return e.errno == errno.EPERM


def _acquire_sync_lock():
    lock_path = os.path.join(BASE_DIR, ".sync.lock")
    if os.path.isfile(lock_path):
        with open(lock_path, encoding="utf-8") as f:
            try:
                existing_pid = int(f.read().strip())
            except ValueError:
                existing_pid = None
        if existing_pid and _pid_is_running(existing_pid):
            return False
    with open(lock_path, "w", encoding="utf-8") as f:
        f.write(str(os.getpid()))
    return True


def _release_sync_lock():
    lock_path = os.path.join(BASE_DIR, ".sync.lock")
    try:
        os.remove(lock_path)
    except FileNotFoundError:
        pass


def run_sync(command, resync=False, skip_if_clean=False, remote_name=None, remote_path=None, on_line=None):
    """Run rclone sync or bisync against configured remote.

    Returns {"ok": bool, "output": str, "error": str, "returncode": int}.
    Reads [sync] section from config.toml for remote_name, remote_path, folders.
    Runs corruption pre-flight check before sync, records file sizes after success.
    Uses a PID-based file lock (`.sync.lock`) to prevent concurrent syncs across processes.
    When skip_if_clean=True, skips rclone if no local files changed since last sync.
    remote_name/remote_path override config values (used by web UI to sync without saving config).
    """
    import subprocess

    if not _acquire_sync_lock():
        return {"ok": False, "output": "", "error":
                "Another sync is already running (lock held by "
                "a different process). Try again shortly.",
                "returncode": 1}

    try:
        cfg = get_config()
        sync_cfg = cfg.get("sync", {})
        if not remote_name:
            remote_name = sync_cfg.get("remote_name", "")
        if not remote_path:
            remote_path = sync_cfg.get("remote_path", "")
        folders = sync_cfg.get("folders", ["config", "records", "journal", "todo"])

        if not remote_name or not remote_path:
            return {"ok": False, "output": "", "error":
                    "[sync] not configured in config.toml. "
                    "Add: [sync] remote_name = \"onedrive\" remote_path = \"personal/ptos-data\"",
                    "returncode": 1}

        try:
            result = subprocess.run(["rclone", "listremotes"],
                                    capture_output=True, text=True, timeout=10)
            remote_names = result.stdout.strip().splitlines()
            if not any(r.strip().rstrip(":") == remote_name for r in remote_names):
                return {"ok": False, "output": "", "error":
                        f"Remote '{remote_name}' not found in rclone config. "
                        f"Available: {', '.join(r.strip() for r in remote_names) or '(none)'}.\n"
                        f"Run 'rclone config' to set it up.",
                        "returncode": 1}
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass

        state_file = os.path.join(BASE_DIR, ".ptos_sync_state")

        if skip_if_clean and not resync:
            if not _local_changed(state_file, folders):
                _invalidate_all()
                return {"ok": True, "output": "Sync skipped: no local changes",
                        "error": "", "returncode": 0}

        concerning = _detect_corruption(BASE_DIR, state_file)
        if concerning:
            return {"ok": False, "output": "", "error":
                    f"Refusing to sync: {len(concerning)} file(s) had content "
                    f"before and are now 0 bytes: " +
                    ", ".join(concerning[:10]) +
                    (f" and {len(concerning)-10} more" if len(concerning) > 10 else "") +
                    ". Investigate before syncing — syncing now risks overwriting "
                    "your remote backup with this corrupted state.",
                    "returncode": 1}

        remote = f"{remote_name}:{remote_path}"
        local = BASE_DIR

        cmd = ["rclone", command, local, remote,
               "--exclude", ".ptos_sync_state",
               "--exclude", ".bisync.*",
               "--exclude", ".sync.lock",
               "--exclude", ".sync_scheduled.log",
               "--stats-one-line",
               "--log-level", "INFO"]
        if command == "bisync" and not resync:
            import glob as _glob
            if not _glob.glob(os.path.join(BASE_DIR, ".bisync.*")):
                resync = True
        if command == "bisync" and not resync:
            cmd.append("--conflict-resolve")
            cmd.append("none")
        if resync and command == "bisync":
            cmd.append("--resync")

        if command == "bisync":
            _clear_rclone_bisync_locks()

        try:
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE,
                                    stderr=subprocess.STDOUT, text=True)
        except FileNotFoundError:
            return {"ok": False, "output": "", "error":
                    "rclone not found. Install from https://rclone.org",
                    "returncode": 1}

        output_lines = []
        deadline = time.time() + 300
        try:
            for line in proc.stdout:
                output_lines.append(line)
                if on_line:
                    on_line(line)
                if time.time() > deadline:
                    proc.kill()
                    proc.wait()
                    return {"ok": False, "output": "".join(output_lines),
                            "error": "Sync timed out after 5 minutes",
                            "returncode": 1}
        except Exception:
            proc.kill()
            proc.wait()
            raise
        proc.wait()

        output = "".join(output_lines)

        if proc.returncode != 0:
            return {"ok": False, "output": output,
                    "error": f"rclone exited with code {proc.returncode}",
                    "returncode": proc.returncode}

        _record_sizes(BASE_DIR, state_file, folders)
        _invalidate_all()

        return {"ok": True, "output": output, "error": "", "returncode": 0}

    finally:
        _release_sync_lock()


def set_user_name(name):
    """Set the user name in config.toml using tomli-w."""
    try:
        import tomli_w
    except ImportError:
        raise RuntimeError("tomli-w not installed: pip install tomli-w")

    if not name or not name.strip():
        sys.exit("Error: Name cannot be empty.")

    name = name.strip()

    if not os.path.exists(CONFIG_PATH):
        sys.exit("Error: config.toml not found. Run 'ptos --init' first.")

    with open(CONFIG_PATH, "rb") as f:
        config = tomllib.load(f)

    if "user" not in config:
        config["user"] = {}
    config["user"]["name"] = name

    with AtomicWrite(CONFIG_PATH, "config") as w:
        tomli_w.dump(config, w.stream)

    print(f"User name set to: {name}")


def validate_date_format(fmt):
    """Validate date format string.
    
    Returns True for presets or valid strftime patterns.
    Raises ValueError for invalid formats.
    """
    import datetime as dt
    presets = ["indian", "us", "eu", "readable", "iso"]
    
    if fmt in presets:
        return True
    
    # Check if it looks like a strftime pattern (contains %)
    if '%' not in fmt:
        raise ValueError(f"Invalid date format '{fmt}': not a preset and contains no strftime directives. "
                         f"Use: indian, us, eu, readable, iso, or a valid strftime pattern starting with %.")
    
    # Basic validation: check for % at end or invalid patterns
    if fmt.endswith('%'):
        raise ValueError(f"Invalid date format '{fmt}': cannot end with %")
    
    # Test if it's a valid strftime pattern
    try:
        test_date = dt.datetime(2026, 4, 15, 10, 30)
        result = test_date.strftime(fmt)
        # If result contains a standalone % (not %% escaped), it's likely invalid
        import re
        if re.search(r'(?<!%)%(?!%)', result):
            raise ValueError(f"Invalid date format '{fmt}': contains unprocessed directives")
        return True
    except (ValueError, AttributeError) as e:
        raise ValueError(f"Invalid date format '{fmt}': {e}. "
                         f"Use: indian, us, eu, readable, iso, or a valid strftime pattern.")


def set_date_format(fmt):
    """Set the date format in config.toml using tomli-w."""
    try:
        import tomli_w
    except ImportError:
        raise RuntimeError("tomli-w not installed: pip install tomli-w")

    if fmt is None or not isinstance(fmt, str):
        sys.exit("Error: Date format must be a string.")

    fmt = fmt.strip()
    if not fmt:
        sys.exit("Error: Date format cannot be empty.")

    try:
        validate_date_format(fmt)
    except ValueError as e:
        sys.exit(str(e))

    if not os.path.exists(CONFIG_PATH):
        sys.exit("Error: config.toml not found. Run 'ptos --init' first.")

    with open(CONFIG_PATH, "rb") as f:
        config = tomllib.load(f)

    if "display" not in config:
        config["display"] = {}
        if "currency" not in config.get("display", {}):
            config["display"]["currency"] = "₹"
    config["display"]["date_format"] = fmt

    with AtomicWrite(CONFIG_PATH, "config") as w:
        tomli_w.dump(config, w.stream)

    print(f"Date format set to: {fmt}")


def set_currency(symbol):
    """Set the currency symbol in config.toml using tomli-w."""
    try:
        import tomli_w
    except ImportError:
        raise RuntimeError("tomli-w not installed: pip install tomli-w")

    if not symbol or not symbol.strip():
        sys.exit("Error: Currency symbol cannot be empty.")
    symbol = symbol.strip()

    if not os.path.exists(CONFIG_PATH):
        sys.exit("Error: config.toml not found. Run 'ptos --init' first.")

    with open(CONFIG_PATH, "rb") as f:
        config = tomllib.load(f)

    if "display" not in config:
        config["display"] = {}
    config["display"]["currency"] = symbol

    with AtomicWrite(CONFIG_PATH, "config") as w:
        tomli_w.dump(config, w.stream)

    print(f"Currency symbol set to: {symbol}")


def add_cycle(name, day):
    """Add or replace a custom cycle in config.toml.
    Cycles are stored as {name: start_day} under [cycles]."""
    try:
        import tomli_w
    except ImportError:
        raise RuntimeError("tomli-w not installed: pip install tomli-w")

    name = name.strip()
    if not re.match(r"^[a-z][a-z0-9_-]*$", name):
        sys.exit("Error: Invalid cycle name '%s' — use lowercase letters, digits, dashes, underscores." % name)
    try:
        day = int(day)
    except (TypeError, ValueError):
        sys.exit(f"Error: Cycle day must be an integer 1-31, got '{day}'.")
    if not 1 <= day <= 31:
        sys.exit(f"Error: Cycle day must be 1-31, got {day}.")

    if not os.path.exists(CONFIG_PATH):
        sys.exit("Error: config.toml not found. Run 'ptos --init' first.")

    with open(CONFIG_PATH, "rb") as f:
        config = tomllib.load(f)

    if "cycles" not in config or not isinstance(config.get("cycles"), dict):
        config["cycles"] = {}
    config["cycles"][name] = day

    with AtomicWrite(CONFIG_PATH, "config") as w:
        tomli_w.dump(config, w.stream)

    print(f"Cycle '{name}' set to start on day {day}.")


def set_auth(username, password):
    """Set HTTP Basic Auth credentials in config.toml.
    Preserves the existing 'enabled' flag (defaults to true if absent)."""
    try:
        import tomli_w
    except ImportError:
        raise RuntimeError("tomli-w not installed: pip install tomli-w")

    if not username or not username.strip():
        sys.exit("Error: Username cannot be empty.")
    if not password or not password.strip():
        sys.exit("Error: Password cannot be empty.")

    if not os.path.exists(CONFIG_PATH):
        sys.exit("Error: config.toml not found. Run 'ptos --init' first.")

    with open(CONFIG_PATH, "rb") as f:
        config = tomllib.load(f)

    auth = config.setdefault("auth", {})
    enabled = auth.get("enabled", True)
    auth.update({"enabled": enabled, "username": username.strip(), "password": password})

    with AtomicWrite(CONFIG_PATH, "config") as w:
        tomli_w.dump(config, w.stream)

    print("Auth credentials set.")
    print("  NOTE: Password is stored in plaintext in config/config.toml.")


# --------------------------------------------------
# Board / Kanban helpers
# --------------------------------------------------

def filter_fields_for_type(type_name, schema=None):
    """Get all field names applicable to a given record type.
    Returns sorted list including 'date', 'type', global fields,
    and type-specific fields."""
    if schema is None:
        schema = get_schema()
    fields = {"date", "type"}
    gf = get_global_fields(schema)
    fields.update(gf.keys())
    tdef = schema.get("type", {}).get(type_name, {})
    fields.update(tdef.get("fields", {}).keys())
    fields.update(tdef.get("required", []))
    for cond_field in tdef.get("conditions", {}):
        fields.add(cond_field)
    return sorted(fields)


def get_column_field_overlap(types, schema=None):
    """Find common shared fields between multiple record types.
    Returns sorted list of field names present in ALL given types."""
    if not types:
        return []
    if schema is None:
        schema = get_schema()
    type_sets = []
    for t in types:
        type_sets.append(set(filter_fields_for_type(t, schema)))
    common = set.intersection(*type_sets) if type_sets else set()
    return sorted(common)


# --------------------------------------------------
# Backward-compatible CLI entry point
# --------------------------------------------------
# ptos.py can still be run directly: python ptos.py [args]
# The real CLI implementation now lives in ptos_cli.py.

if __name__ == "__main__":
    from ptos_cli import main
    main()
