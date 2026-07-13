"""
ptos_sync.py  —  OneDrive sync (rclone bisync) for PTOS
=======================================================
Platforms:
  - Windows: no-op (native OneDrive desktop app)
  - Linux / Termux: rclone bisync against PTOS_HOME

Three triggers: startup, periodic (piggybacks on todo-notify loop),
and manual (POST /sync/run).
"""

import os, time, threading, subprocess, dataclasses
from dataclasses import dataclass, field
from typing import Optional, Literal


@dataclass
class SyncResult:
    status: Literal["idle", "running", "ok", "conflict", "error", "skipped"] = "idle"
    output: str = ""
    conflicts: list = field(default_factory=list)
    timestamp: str = ""
    duration_seconds: float = 0.0


_last_result = SyncResult()
_sync_lock = threading.Lock()
_state_file = None  # set by init


def init(base_dir):
    global _state_file
    _state_file = os.path.join(base_dir, ".sync_state")


def get_sync_platform():
    if os.name == "nt":
        return "windows"
    if "com.termux" in os.environ.get("PREFIX", "") or os.path.exists("/data/data/com.termux"):
        return "termux"
    return "linux"


def get_sync_config():
    try:
        import ptos
        cfg = ptos.get_config()
        sync_cfg = dict(cfg.get("sync", {}))
        platform = get_sync_platform()
        if platform != "windows" and sync_cfg.get("enabled"):
            if not _which("rclone"):
                sync_cfg["enabled"] = False
        return sync_cfg
    except Exception:
        return {}


def folders_changed_since_last_sync(folders, base_dir):
    if not _state_file or not os.path.isfile(_state_file):
        return True
    try:
        with open(_state_file, encoding="utf-8") as f:
            last_mtime = float(f.read().strip() or "0")
    except Exception:
        return True
    for folder in folders:
        folder_path = os.path.join(base_dir, folder)
        if not os.path.isdir(folder_path):
            continue
        try:
            for root, dirs, files in os.walk(folder_path):
                for fname in files:
                    if fname.endswith(".bak") or fname.endswith(".tmp") or fname.startswith("."):
                        continue
                    fpath = os.path.join(root, fname)
                    mtime = os.path.getmtime(fpath)
                    if mtime > last_mtime:
                        return True
        except Exception:
            return True
    return False


def _save_state():
    if _state_file:
        try:
            os.makedirs(os.path.dirname(_state_file), exist_ok=True)
            with open(_state_file, "w", encoding="utf-8") as f:
                f.write(str(time.time()))
        except Exception:
            pass


def run_sync(force_resync=False):
    global _last_result
    if not _sync_lock.acquire(blocking=False):
        return SyncResult(status="running", output="Sync already in progress")

    try:
        if _state_file is None:
            import ptos as _ptos
            init(_ptos.BASE_DIR)

        platform = get_sync_platform()
        if platform == "windows":
            _last_result = SyncResult(status="ok", timestamp=str(time.time()))
            return _last_result

        if not _which("rclone"):
            _last_result = SyncResult(
                status="error", output="rclone not found. Install from https://rclone.org",
                timestamp=str(time.time()))
            return _last_result

        import ptos
        cfg = get_sync_config()
        remote_name = cfg.get("remote_name", "onedrive")
        remote_path = cfg.get("remote_path", "PTOS")
        base_dir = ptos.BASE_DIR

        cmd = [
            "rclone", "bisync",
            base_dir,
            f"{remote_name}:{remote_path}",
            "--exclude", "backups/**",
            "--exclude", "exports/**",
            "--exclude", "*.bak",
            "--exclude", "*.tmp",
            "--exclude", ".sync*",
            "--conflict-resolve", "none",
            "--log-file", os.path.join(base_dir, ".sync.log"),
            "--log-level", "INFO",
        ]
        if not cfg.get("resynced", False) or force_resync:
            cmd.append("--resync")

        t0 = time.time()
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        elapsed = time.time() - t0
        output = result.stdout + result.stderr

        conflicts = _parse_conflicts(output)
        if result.returncode != 0:
            status = "error"
        elif conflicts:
            status = "conflict"
        else:
            status = "ok"
            if not cfg.get("resynced", False):
                _mark_resynced()

        _last_result = SyncResult(
            status=status, output=output, conflicts=conflicts,
            timestamp=str(time.time()), duration_seconds=elapsed)
        _save_state()
        return _last_result

    except subprocess.TimeoutExpired:
        _last_result = SyncResult(status="error", output="Sync timed out after 5 minutes",
                                  timestamp=str(time.time()))
        return _last_result
    except Exception as e:
        _last_result = SyncResult(status="error", output=str(e),
                                  timestamp=str(time.time()))
        return _last_result
    finally:
        _sync_lock.release()


def _mark_resynced():
    try:
        import ptos
        import tomli_w
        cfg = ptos.get_config()
        cfg.setdefault("sync", {})["resynced"] = True
        with ptos.AtomicWrite(ptos.CONFIG_PATH, "config") as w:
            tomli_w.dump(cfg, w.stream)
    except Exception:
        pass


def _parse_conflicts(output):
    conflicts = []
    for line in output.splitlines():
        if "conflict" in line.lower() and "rename" in line.lower():
            m = __import__("re").search(r'renamed to "?([^"\n]+)"?', line)
            if m:
                conflicts.append(m.group(1))
    return list(set(conflicts))


def _which(name):
    for path in os.environ.get("PATH", "").split(os.pathsep):
        exe = os.path.join(path, name)
        if os.path.isfile(exe) or os.path.isfile(exe + ".exe"):
            return exe
    return None


def get_last_result():
    return _last_result


def run_sync_async(force_resync=False):
    threading.Thread(target=run_sync, args=(force_resync,), daemon=True).start()
