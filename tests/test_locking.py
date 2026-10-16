"""Sidecar file locking — file_lock helper + write-helper coverage (spec Part B, tests 1-9)."""
import ast
import contextlib
import os
import signal
import socket
import subprocess
import sys
import threading
import time
import tomllib

import pytest

import ptos

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

_HOLD_WHILE_LOCKED = """\
import sys, time
import ptos

with ptos.file_lock(sys.argv[1], timeout=10.0):
    print("locked", flush=True)
    time.sleep(float(sys.argv[2]))
"""

_HOLD_FOREVER = """\
import sys, time
import ptos

with ptos.file_lock(sys.argv[1], timeout=10.0):
    print("locked", flush=True)
    while True:
        time.sleep(0.5)
"""

_APPENDER = """\
import sys, ptos
path = sys.argv[1]
n = int(sys.argv[2])
for i in range(n):
    ptos.append_line_fast(path, "app-%03d" % i)
print("done", flush=True)
"""

_EDITOR = """\
import sys, ptos
path = sys.argv[1]
start = int(sys.argv[2])
count = int(sys.argv[3])
for i in range(start, start + count):
    ptos.rewrite_line_in_file(path, "seed-%03d" % i, "done-%03d" % i)
print("done", flush=True)
"""

_FAV_RACER = """\
import sys, ptos
n = int(sys.argv[1])
for i in range(n):
    ptos.save_favorites([{"name": "fav%d" % i, "url": "/page%d" % i}])
print("done", flush=True)
"""


def _spawn(script, home, *args, env_extra=None):
    env = dict(os.environ, PTOS_HOME=home)
    env.update(env_extra or {})
    return subprocess.Popen(
        [sys.executable, "-c", script, *args],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, env=env, cwd=REPO)


def _dead_pid():
    proc = subprocess.Popen([sys.executable, "-c", "pass"])
    proc.wait()
    return proc.pid


def _write_owner(lock_path, pid, host=None, age=0.0):
    with open(lock_path, "w", encoding="utf-8") as f:
        f.write(f"{pid}\n{host if host is not None else socket.gethostname()}\n")
    if age:
        old = time.time() - age
        os.utime(lock_path, (old, old))


@contextlib.contextmanager
def _held_elsewhere(path):
    """Hold `path` from another thread so this thread's acquire really blocks
    (same-thread re-acquire is a reentrancy no-op by design)."""
    ready = threading.Event()
    release = threading.Event()

    def holder():
        with ptos.file_lock(path, timeout=10.0):
            ready.set()
            release.wait(20.0)

    thread = threading.Thread(target=holder, daemon=True)
    thread.start()
    assert ready.wait(10.0), "holder thread never acquired"
    try:
        yield
    finally:
        release.set()
        thread.join(20.0)


@pytest.fixture()
def lockfile_mode(monkeypatch):
    monkeypatch.setenv("PTOS_LOCK_MODE", "lockfile")
    monkeypatch.setattr(ptos, "_LOCK_MODE", {})
    monkeypatch.setattr(ptos, "_LOCK_FALLBACK_LOGGED", False)


# ── 1. mutual exclusion ───────────────────────────────────────────────────────

class TestMutualExclusion:
    def test_two_processes_serialize(self, tmp_path):
        path = str(tmp_path / "data.txt")
        child = _spawn(_HOLD_WHILE_LOCKED, str(tmp_path), path, "1.5")
        try:
            assert child.stdout.readline().strip() == "locked"
            start = time.monotonic()
            with ptos.file_lock(path, timeout=10.0):
                held_for = time.monotonic() - start
            assert held_for >= 1.0, "acquired while the child still held it"
        finally:
            if child.poll() is None:
                child.kill()
            child.wait(30)

    def test_two_threads_serialize(self, tmp_path):
        path = str(tmp_path / "data.txt")
        order = []
        started = threading.Event()
        release = threading.Event()

        def holder():
            with ptos.file_lock(path, timeout=10.0):
                order.append("holder-in")
                started.set()
                release.wait(10.0)
                order.append("holder-out")

        t = threading.Thread(target=holder)
        t.start()
        assert started.wait(5.0)
        # Second thread must NOT be a reentrancy no-op: it is a different
        # thread, so it has to block until the holder releases.
        with pytest.raises(ptos.FileBusyError):
            with ptos.file_lock(path, timeout=0.15):
                order.append("intruder")
        release.set()
        t.join(10.0)
        with ptos.file_lock(path, timeout=5.0):
            order.append("final")
        assert order == ["holder-in", "holder-out", "final"]


# ── 2. timeout and release-on-exception ───────────────────────────────────────

class TestTimeoutAndRelease:
    def test_timeout_raises_ptos_error(self, tmp_path):
        path = str(tmp_path / "data.txt")
        with _held_elsewhere(path):
            with pytest.raises(ptos.FileBusyError, match="is busy; try again"):
                with ptos.file_lock(path, timeout=0.15):
                    pass

    def test_released_after_exception_inside_block(self, tmp_path):
        path = str(tmp_path / "data.txt")
        with pytest.raises(ValueError):
            with ptos.file_lock(path, timeout=5.0):
                raise ValueError("boom")
        with ptos.file_lock(path, timeout=5.0):
            pass

    def test_busy_error_is_a_ptos_error(self, tmp_path):
        assert issubclass(ptos.FileBusyError, ptos.PTOSError)


# ── 3. reentrancy ─────────────────────────────────────────────────────────────

class TestReentrancy:
    def test_same_path_nested_same_thread(self, tmp_path):
        path = str(tmp_path / "data.txt")
        with ptos.file_lock(path, timeout=0.2):
            with ptos.file_lock(path, timeout=0.2):
                with ptos.file_lock(path, timeout=0.2):
                    pass

    def test_different_paths_nested(self, tmp_path):
        a = str(tmp_path / "a.txt")
        b = str(tmp_path / "b.txt")
        with ptos.file_lock(a, timeout=0.2):
            with ptos.file_lock(b, timeout=0.2):
                with ptos.file_lock(a, timeout=0.2):
                    pass

    def test_released_in_reverse_order(self, tmp_path):
        a = str(tmp_path / "a.txt")
        b = str(tmp_path / "b.txt")
        with ptos.file_lock(a, timeout=2.0):
            with ptos.file_lock(b, timeout=2.0):
                pass
        with ptos.file_lock(a, timeout=2.0), ptos.file_lock(b, timeout=2.0):
            pass


# ── 4. process kill (kernel releases the lock) ────────────────────────────────

@pytest.mark.skipif(os.name == "nt", reason="POSIX signals only")
class TestProcessKill:
    def test_sigkill_releases_the_lock(self, tmp_path):
        path = str(tmp_path / "data.txt")
        child = _spawn(_HOLD_FOREVER, str(tmp_path), path)
        try:
            assert child.stdout.readline().strip() == "locked"
            os.kill(child.pid, signal.SIGKILL)
            child.wait(30)
        finally:
            if child.poll() is None:
                child.kill()
                child.wait(30)
        start = time.monotonic()
        with ptos.file_lock(path, timeout=5.0):
            assert time.monotonic() - start < 4.0


# ── 7. lockfile fallback mode ─────────────────────────────────────────────────

class TestLockfileFallback:
    def test_mode_reports_lockfile(self, lockfile_mode):
        assert ptos.file_lock_mode() == "lockfile"

    def test_two_processes_serialize(self, tmp_path, lockfile_mode):
        path = str(tmp_path / "data.txt")
        child = _spawn(_HOLD_WHILE_LOCKED, str(tmp_path), path, "1.0")
        try:
            assert child.stdout.readline().strip() == "locked"
            start = time.monotonic()
            with ptos.file_lock(path, timeout=10.0):
                held_for = time.monotonic() - start
            assert held_for >= 0.5
        finally:
            child.kill()
            child.wait(30)

    def test_timeout_raises(self, tmp_path, lockfile_mode):
        path = str(tmp_path / "data.txt")
        with _held_elsewhere(path):
            with pytest.raises(ptos.FileBusyError, match="is busy; try again"):
                with ptos.file_lock(path, timeout=0.15):
                    pass

    def test_exception_releases(self, tmp_path, lockfile_mode):
        path = str(tmp_path / "data.txt")
        with pytest.raises(ValueError):
            with ptos.file_lock(path, timeout=5.0):
                raise ValueError("boom")
        with ptos.file_lock(path, timeout=5.0):
            pass

    def test_reentrancy(self, tmp_path, lockfile_mode):
        path = str(tmp_path / "data.txt")
        with ptos.file_lock(path, timeout=0.2):
            with ptos.file_lock(path, timeout=0.2):
                pass

    def test_no_lock_file_left_behind(self, tmp_path, lockfile_mode):
        path = str(tmp_path / "data.txt")
        with ptos.file_lock(path, timeout=5.0):
            assert os.path.exists(path + ".lock")
        assert not os.path.exists(path + ".lock")

    def test_stale_dead_owner_removed_by_age(self, tmp_path, lockfile_mode):
        path = str(tmp_path / "data.txt")
        _write_owner(path + ".lock", _dead_pid(), age=120.0)
        with ptos.file_lock(path, timeout=5.0):
            pass

    def test_stale_dead_owner_removed_when_threshold_zero(
            self, tmp_path, lockfile_mode, monkeypatch):
        monkeypatch.setattr(ptos, "_LOCK_STALE_SECONDS", 0.0)
        path = str(tmp_path / "data.txt")
        _write_owner(path + ".lock", _dead_pid(), age=0.0)
        with ptos.file_lock(path, timeout=5.0):
            pass

    def test_live_owner_is_never_stolen(self, tmp_path, lockfile_mode):
        path = str(tmp_path / "data.txt")
        _write_owner(path + ".lock", os.getpid(), age=120.0)
        with pytest.raises(ptos.FileBusyError):
            with ptos.file_lock(path, timeout=0.15):
                pass

    def test_fresh_dead_owner_respects_the_age_gate(
            self, tmp_path, lockfile_mode):
        path = str(tmp_path / "data.txt")
        _write_owner(path + ".lock", _dead_pid(), age=0.0)
        with pytest.raises(ptos.FileBusyError):
            with ptos.file_lock(path, timeout=0.15):
                pass

    def test_foreign_host_owner_left_alone(self, tmp_path, lockfile_mode):
        path = str(tmp_path / "data.txt")
        _write_owner(path + ".lock", _dead_pid(),
                     host="some-other-host", age=120.0)
        with pytest.raises(ptos.FileBusyError):
            with ptos.file_lock(path, timeout=0.15):
                pass

    def test_ancient_live_owner_is_stolen(self, tmp_path, lockfile_mode):
        path = str(tmp_path / "data.txt")
        _write_owner(path + ".lock", os.getpid(), age=700.0)
        with ptos.file_lock(path, timeout=5.0):
            pass

    def test_ancient_foreign_host_is_stolen(self, tmp_path, lockfile_mode):
        path = str(tmp_path / "data.txt")
        _write_owner(path + ".lock", _dead_pid(),
                     host="some-other-host", age=700.0)
        with ptos.file_lock(path, timeout=5.0):
            pass

    def test_recent_live_owner_respects_the_max_age_gate(
            self, tmp_path, lockfile_mode):
        path = str(tmp_path / "data.txt")
        _write_owner(path + ".lock", os.getpid(), age=590.0)
        with pytest.raises(ptos.FileBusyError):
            with ptos.file_lock(path, timeout=0.15):
                pass

    def test_max_age_constant_is_ten_minutes(self):
        assert ptos._LOCK_MAX_AGE_SECONDS == 600.0

    def test_editor_and_appender_race(self, tmp_path, lockfile_mode):
        path = str(tmp_path / "race.log")
        for i in range(25):
            ptos.append_line_fast(path, "seed-%03d" % i)
        errors = []

        def edit():
            try:
                for i in range(25):
                    ptos.rewrite_line_in_file(
                        path, "seed-%03d" % i, "done-%03d" % i)
            except Exception as exc:  # noqa: BLE001 - collected for assert
                errors.append(exc)

        def append():
            try:
                for i in range(100):
                    ptos.append_line_fast(path, "app-%03d" % i)
            except Exception as exc:  # noqa: BLE001 - collected for assert
                errors.append(exc)

        threads = [threading.Thread(target=edit),
                   threading.Thread(target=append)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(60.0)
        assert errors == []
        with open(path, encoding="utf-8") as f:
            lines = [ln.strip() for ln in f if ln.strip()]
        assert len(lines) == 125
        for i in range(25):
            assert "done-%03d" % i in lines
        for i in range(100):
            assert "app-%03d" % i in lines
        _assert_no_leftovers(tmp_path)


# ── 5. race regressions (threads + subprocesses) ─────────────────────────────

def _assert_no_leftovers(directory):
    # Spec test 6: no .tmp/.bak stragglers. The sidecar .lock itself is
    # deliberately kept in OS-lock mode (unlinking it would race waiters
    # against a fresh inode); pid mode removes it, pinned by the fallback
    # suite's test_no_lock_file_left_behind.
    stragglers = []
    for root, _dirs, files in os.walk(directory):
        for name in files:
            if name.endswith((".tmp", ".bak")):
                stragglers.append(os.path.join(root, name))
    assert stragglers == []


def _seed_seeds(path, count):
    for i in range(count):
        ptos.append_line_fast(path, "seed-%03d" % i)


def _check_race_file(path, seeds, appends):
    with open(path, encoding="utf-8") as f:
        lines = [ln.strip() for ln in f if ln.strip()]
    assert len(lines) == seeds + appends
    for i in range(seeds):
        assert "done-%03d" % i in lines
    for i in range(appends):
        assert "app-%03d" % i in lines
    assert not any(ln.startswith("seed-") for ln in lines)


class TestRaceEditorAppender:
    def test_threads_50_edits_400_appends(self, tmp_path):
        path = str(tmp_path / "race.log")
        _seed_seeds(path, 50)
        errors = []

        def edit():
            try:
                for i in range(50):
                    ptos.rewrite_line_in_file(
                        path, "seed-%03d" % i, "done-%03d" % i)
            except Exception as exc:  # noqa: BLE001 - collected for assert
                errors.append(exc)

        def append():
            try:
                for i in range(400):
                    ptos.append_line_fast(path, "app-%03d" % i)
            except Exception as exc:  # noqa: BLE001 - collected for assert
                errors.append(exc)

        threads = [threading.Thread(target=edit),
                   threading.Thread(target=append)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(120.0)
        assert errors == []
        _check_race_file(path, 50, 400)
        _assert_no_leftovers(tmp_path)

    def test_processes_50_edits_400_appends(self, tmp_path):
        path = str(tmp_path / "race.log")
        _seed_seeds(path, 50)
        child = _spawn(_APPENDER, str(tmp_path), path, "400")
        try:
            for i in range(50):
                ptos.rewrite_line_in_file(path, "seed-%03d" % i,
                                          "done-%03d" % i)
            _out, err = child.communicate(timeout=180)
        finally:
            if child.poll() is None:
                child.kill()
                child.wait(30)
        assert child.returncode == 0, err
        _check_race_file(path, 50, 400)
        _assert_no_leftovers(tmp_path)


class TestRaceTwoEditors:
    def test_threads_150_edits_each(self, tmp_path):
        path = str(tmp_path / "race.log")
        _seed_seeds(path, 300)
        errors = []

        def edit_range(start, tag):
            try:
                for i in range(start, start + 150):
                    ptos.rewrite_line_in_file(
                        path, "seed-%03d" % i, "done-%s-%03d" % (tag, i))
            except Exception as exc:  # noqa: BLE001 - collected for assert
                errors.append(exc)

        threads = [threading.Thread(target=edit_range, args=(0, "A")),
                   threading.Thread(target=edit_range, args=(150, "B"))]
        for t in threads:
            t.start()
        for t in threads:
            t.join(120.0)
        assert errors == []
        with open(path, encoding="utf-8") as f:
            lines = [ln.strip() for ln in f if ln.strip()]
        assert len(lines) == 300
        for i in range(150):
            assert "done-A-%03d" % i in lines
        for i in range(150, 300):
            assert "done-B-%03d" % i in lines
        assert not any(ln.startswith("seed-") for ln in lines)
        _assert_no_leftovers(tmp_path)

    def test_processes_150_edits_each(self, tmp_path):
        path = str(tmp_path / "race.log")
        _seed_seeds(path, 300)
        child = _spawn(_EDITOR, str(tmp_path), path, "150", "150")
        try:
            for i in range(150):
                ptos.rewrite_line_in_file(path, "seed-%03d" % i,
                                          "done-A-%03d" % i)
            _out, err = child.communicate(timeout=180)
        finally:
            if child.poll() is None:
                child.kill()
                child.wait(30)
        assert child.returncode == 0, err
        with open(path, encoding="utf-8") as f:
            lines = [ln.strip() for ln in f if ln.strip()]
        assert len(lines) == 300
        for i in range(150):
            assert "done-A-%03d" % i in lines
        for i in range(150, 300):
            assert "done-%03d" % i in lines
        assert not any(ln.startswith("seed-") for ln in lines)
        _assert_no_leftovers(tmp_path)


class TestRaceConfigWriters:
    def test_threads_save_favorites_vs_set_currency(self, tmp_path):
        ptos.set_currency("USD")
        errors = []

        def favs():
            try:
                for i in range(10):
                    ptos.save_favorites(
                        [{"name": "fav%d" % i, "url": "/page%d" % i}])
            except Exception as exc:  # noqa: BLE001 - collected for assert
                errors.append(exc)

        def cur():
            try:
                for sym in ["INR", "USD"] * 5:
                    ptos.set_currency(sym)
            except Exception as exc:  # noqa: BLE001 - collected for assert
                errors.append(exc)

        threads = [threading.Thread(target=favs),
                   threading.Thread(target=cur)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(120.0)
        assert errors == []
        with open(ptos.CONFIG_PATH, "rb") as f:
            data = tomllib.load(f)
        items = data.get("favorites", {}).get("items")
        assert items and items[0]["name"] == "fav9"
        assert data["display"]["currency"] in ("INR", "USD")
        _assert_no_leftovers(tmp_path)

    def test_processes_save_favorites_vs_set_currency(self, tmp_path):
        ptos.set_currency("USD")
        child = _spawn(_FAV_RACER,
                       os.path.join(str(tmp_path), "ptos_test_home"), "10")
        try:
            for sym in ["INR", "USD"] * 5:
                ptos.set_currency(sym)
            _out, err = child.communicate(timeout=180)
        finally:
            if child.poll() is None:
                child.kill()
                child.wait(30)
        assert child.returncode == 0, err
        with open(ptos.CONFIG_PATH, "rb") as f:
            data = tomllib.load(f)
        items = data.get("favorites", {}).get("items")
        assert items and items[0]["name"] == "fav9"
        assert data["display"]["currency"] in ("INR", "USD")
        _assert_no_leftovers(tmp_path)


# ── temp-file permissions ─────────────────────────────────────────────────────

def _current_umask():
    mask = os.umask(0)
    os.umask(mask)
    return mask


class TestTempFilePermissions:
    def test_temp_names_are_unique_and_same_dir(self, tmp_path):
        target = str(tmp_path / "data.txt")
        seen = set()
        for _ in range(5):
            fd, tmp = ptos._make_temp_file(target)
            os.close(fd)
            assert os.path.dirname(tmp) == str(tmp_path)
            assert tmp.endswith(".tmp")
            assert tmp not in seen
            seen.add(tmp)
            os.unlink(tmp)

    @pytest.mark.skipif(os.name != "posix", reason="POSIX mode bits")
    @pytest.mark.parametrize("mode", [0o640, 0o644, 0o600, 0o664])
    def test_atomic_write_preserves_existing_mode(self, tmp_path, mode):
        path = str(tmp_path / "data.txt")
        with open(path, "w", encoding="utf-8") as f:
            f.write("old")
        os.chmod(path, mode)
        ptos.atomic_write(path, "new")
        assert os.stat(path).st_mode & 0o777 == mode

    @pytest.mark.skipif(os.name != "posix", reason="POSIX mode bits")
    def test_atomic_write_new_file_gets_umask_mode(self, tmp_path):
        path = str(tmp_path / "fresh.txt")
        ptos.atomic_write(path, "content")
        assert os.stat(path).st_mode & 0o777 == 0o666 & ~_current_umask()

    @pytest.mark.skipif(os.name != "posix", reason="POSIX mode bits")
    def test_atomicwrite_stream_preserves_mode(self, tmp_path):
        path = str(tmp_path / "data.txt")
        with open(path, "w", encoding="utf-8") as f:
            f.write("old")
        os.chmod(path, 0o640)
        with ptos.AtomicWrite(path) as w:
            w.stream.write(b"new")
        assert os.stat(path).st_mode & 0o777 == 0o640

    @pytest.mark.skipif(os.name != "posix", reason="POSIX mode bits")
    def test_atomic_append_preserves_mode(self, tmp_path):
        path = str(tmp_path / "data.txt")
        with open(path, "w", encoding="utf-8") as f:
            f.write("old\n")
        os.chmod(path, 0o644)
        ptos.atomic_append(path, "line\n")
        assert os.stat(path).st_mode & 0o777 == 0o644


# ── sharing-violation retry on replace/rename ─────────────────────────────────

def _sharing_error():
    err = PermissionError(13, "sharing violation")
    err.winerror = 32
    return err


class TestReplaceWithRetry:
    def test_posix_passthrough_does_not_retry(self, monkeypatch):
        if os.name == "nt":
            pytest.skip("POSIX passthrough branch")
        calls = []

        def boom(src, dst):
            calls.append(1)
            raise PermissionError(13, "denied")

        monkeypatch.setattr(os, "replace", boom)
        with pytest.raises(PermissionError):
            ptos.replace_with_retry("a", "b")
        assert len(calls) == 1

    def test_nt_retries_transient_sharing_violation(self, tmp_path, monkeypatch):
        if os.name != "nt":
            pytest.skip("Windows-only retry branch")
        src = str(tmp_path / "src.txt")
        dst = str(tmp_path / "dst.txt")
        with open(src, "w", encoding="utf-8") as f:
            f.write("new")
        with open(dst, "w", encoding="utf-8") as f:
            f.write("old")
        state = {"n": 0}
        real = os.replace

        def flaky(a, b):
            state["n"] += 1
            if state["n"] <= 2:
                raise _sharing_error()
            real(a, b)

        monkeypatch.setattr(os, "replace", flaky)
        ptos.replace_with_retry(src, dst)
        assert state["n"] == 3
        with open(dst, encoding="utf-8") as f:
            assert f.read() == "new"

    def test_nt_raises_file_busy_after_timeout(self, tmp_path, monkeypatch):
        if os.name != "nt":
            pytest.skip("Windows-only retry branch")
        monkeypatch.setattr(ptos, "_REPLACE_RETRY_TOTAL", 0.05)

        def always(a, b):
            raise _sharing_error()

        monkeypatch.setattr(os, "replace", always)
        with pytest.raises(ptos.FileBusyError):
            ptos.replace_with_retry(str(tmp_path / "s"), str(tmp_path / "d"))

    def test_non_permission_errors_raise_immediately(self, tmp_path, monkeypatch):
        if os.name != "nt":
            pytest.skip("Windows-only retry branch")
        calls = []

        def boom(a, b):
            calls.append(1)
            raise OSError(5, "hard failure")

        monkeypatch.setattr(os, "replace", boom)
        with pytest.raises(OSError):
            ptos.replace_with_retry(str(tmp_path / "s"), str(tmp_path / "d"))
        assert len(calls) == 1

    def test_rename_with_retry_nt_retries(self, tmp_path, monkeypatch):
        if os.name != "nt":
            pytest.skip("Windows-only retry branch")
        src = str(tmp_path / "src.txt")
        dst = str(tmp_path / "dst.txt")
        with open(src, "w", encoding="utf-8") as f:
            f.write("x")
        state = {"n": 0}
        real = os.rename

        def flaky(a, b):
            state["n"] += 1
            if state["n"] <= 1:
                raise _sharing_error()
            real(a, b)

        monkeypatch.setattr(os, "rename", flaky)
        ptos.rename_with_retry(src, dst)
        assert state["n"] == 2
        assert os.path.isfile(dst)

    @pytest.mark.skipif(os.name != "nt", reason="needs Windows file handles")
    def test_real_sharing_violation_then_release_succeeds(self, tmp_path):
        import ctypes
        src = str(tmp_path / "src.txt")
        dst = str(tmp_path / "dst.txt")
        with open(src, "w", encoding="utf-8") as f:
            f.write("new")
        with open(dst, "w", encoding="utf-8") as f:
            f.write("old")
        kernel32 = ctypes.windll.kernel32
        GENERIC_WRITE = 0x40000000
        FILE_SHARE_READ = 0x1
        OPEN_EXISTING = 3
        handle = kernel32.CreateFileW(
            dst, GENERIC_WRITE, FILE_SHARE_READ, None, OPEN_EXISTING, 0, None)
        assert handle not in (0, -1)

        def release_soon():
            time.sleep(0.3)
            kernel32.CloseHandle(handle)

        t = threading.Thread(target=release_soon)
        t.start()
        ptos.replace_with_retry(src, dst)
        t.join(5.0)
        with open(dst, encoding="utf-8") as f:
            assert f.read() == "new"

    @pytest.mark.skipif(os.name != "nt", reason="needs Windows file handles")
    def test_persistent_sharing_violation_raises_file_busy(self, tmp_path,
                                                          monkeypatch):
        import ctypes
        monkeypatch.setattr(ptos, "_REPLACE_RETRY_TOTAL", 0.3)
        src = str(tmp_path / "src.txt")
        dst = str(tmp_path / "dst.txt")
        with open(src, "w", encoding="utf-8") as f:
            f.write("new")
        with open(dst, "w", encoding="utf-8") as f:
            f.write("old")
        kernel32 = ctypes.windll.kernel32
        handle = kernel32.CreateFileW(
            dst, 0x40000000, 0x1, None, 3, 0, None)
        assert handle not in (0, -1)
        try:
            with pytest.raises(ptos.FileBusyError):
                ptos.replace_with_retry(src, dst)
            with open(dst, encoding="utf-8") as f:
                assert f.read() == "old"
        finally:
            kernel32.CloseHandle(handle)


class TestNoBareReplaceOutsideHelpers:
    _ALLOWED = {"replace_with_retry", "rename_with_retry",
                "_retry_windows_sharing"}

    def _violations(self):
        violations = []
        for fname in ("ptos.py", "ptos_todo.py", "ptos_service.py"):
            path = os.path.join(REPO, fname)
            with open(path, encoding="utf-8") as f:
                tree = ast.parse(f.read())
            for fn in [n for n in ast.walk(tree)
                       if isinstance(n, ast.FunctionDef)]:
                if fn.name in self._ALLOWED:
                    continue
                for node in ast.walk(fn):
                    if not isinstance(node, ast.Call):
                        continue
                    fobj = node.func
                    if (isinstance(fobj, ast.Attribute)
                            and fobj.attr in ("replace", "rename")
                            and isinstance(fobj.value, ast.Name)
                            and fobj.value.id == "os"):
                        violations.append(f"{fname}:{fn.name}")
        return violations

    def test_every_replace_and_rename_goes_through_the_retry(self):
        assert self._violations() == []


# ── lock exclusion probe ──────────────────────────────────────────────────────

class TestLockExclusionProbe:
    def test_probe_passes_on_normal_fs(self, monkeypatch):
        monkeypatch.setattr(ptos, "_LOCK_MODE", {})
        assert ptos.file_lock_mode() in ("fcntl", "msvcrt", "lockfile")
        assert ptos._LOCK_MODE.get("exclusion_ok") is True

    def test_probe_downgrades_when_exclusion_lies(self, monkeypatch):
        monkeypatch.setattr(ptos, "_LOCK_MODE", {})
        forced = "msvcrt" if os.name == "nt" else "fcntl"
        monkeypatch.setenv("PTOS_LOCK_MODE", forced)
        monkeypatch.setattr(ptos, "_os_lock", lambda fd, backend: None)
        assert ptos.file_lock_mode() == "lockfile"
        assert ptos._LOCK_MODE.get("exclusion_ok") is False

    def test_probe_runs_once_per_process(self, monkeypatch):
        monkeypatch.setattr(ptos, "_LOCK_MODE", {})
        ptos.file_lock_mode()
        calls = []
        monkeypatch.setattr(ptos, "_run_lock_probe",
                            lambda mode: calls.append(mode))
        ptos.file_lock_mode()
        ptos.file_lock_mode()
        assert calls == []

    def test_lockfile_mode_probe_detects_honest_o_excl(self, monkeypatch):
        monkeypatch.setattr(ptos, "_LOCK_MODE", {})
        monkeypatch.setenv("PTOS_LOCK_MODE", "lockfile")
        assert ptos.file_lock_mode() == "lockfile"
        assert ptos._LOCK_MODE.get("exclusion_ok") is True

    def test_doctor_reports_probe_result(self, monkeypatch):
        monkeypatch.setattr(ptos, "_LOCK_MODE", {})
        errs, warns, msgs, fixes = ptos.doctor_check()
        locking = [m for m in msgs if m[0] == "File locking"]
        assert locking and "exclusion probe" in locking[0][1]


class TestDoctorStignore:
    def test_doctor_warns_on_missing_stignore(self):
        stignore = os.path.join(ptos.BASE_DIR, ".stignore")
        if os.path.exists(stignore):
            os.remove(stignore)
        errs, warns, msgs, fixes = ptos.doctor_check()
        assert any(".stignore missing" in w for w in warns)

    def test_fix_creates_stignore_idempotent(self):
        stignore = os.path.join(ptos.BASE_DIR, ".stignore")
        if os.path.exists(stignore):
            os.remove(stignore)
        errs, warns, msgs, fixes = ptos.doctor_check(fix=True)
        assert os.path.isfile(stignore)
        with open(stignore, encoding="utf-8") as f:
            text = f.read()
        for pattern in ("*.tmp", "*.bak", "*.lock"):
            assert pattern in text.splitlines()
        first = text
        errs, warns, msgs, fixes = ptos.doctor_check(fix=True)
        with open(stignore, encoding="utf-8") as f:
            assert f.read() == first
        assert not any("stignore" in w for w in warns)

    def test_fix_appends_only_missing_lines(self):
        stignore = os.path.join(ptos.BASE_DIR, ".stignore")
        with open(stignore, "w", encoding="utf-8") as f:
            f.write("*.tmp\n")
        errs, warns, msgs, fixes = ptos.doctor_check(fix=True)
        with open(stignore, encoding="utf-8") as f:
            lines = f.read().splitlines()
        assert lines.count("*.tmp") == 1
        assert "*.bak" in lines
        assert "*.lock" in lines
        errs, warns, msgs, fixes = ptos.doctor_check()
        assert not any("stignore" in w for w in warns)


# ── 8. static: no copy2(bak, live) rollback, reads inside the lock ───────────

_WRITE_FILES = ("ptos.py", "ptos_service.py", "ptos_todo.py", "ptos_cli.py")


def _bakish(text):
    lowered = text.lower()
    return ".bak" in lowered or "backup" in lowered


class TestStaticWriteSafety:
    def test_no_copy2_from_backup_to_live(self):
        offenders = []
        for fn in _WRITE_FILES:
            src = open(os.path.join(REPO, fn), encoding="utf-8").read()
            for node in ast.walk(ast.parse(src)):
                if not (isinstance(node, ast.Call) and node.args
                        and isinstance(node.func, ast.Attribute)
                        and node.func.attr == "copy2"):
                    continue
                if len(node.args) < 2:
                    continue
                a1 = ast.get_source_segment(src, node.args[0]) or ""
                a2 = ast.get_source_segment(src, node.args[1]) or ""
                if _bakish(a1) and not _bakish(a2):
                    offenders.append(f"{fn}:{node.lineno}: copy2({a1}, {a2})")
        assert offenders == [], (
            "rollback copy2(backup, live) must not return: " +
            "; ".join(offenders))

    def test_no_open_before_atomicwrite_outside_a_lock(self):
        offenders = []
        for fn in _WRITE_FILES:
            src = open(os.path.join(REPO, fn), encoding="utf-8").read()
            tree = ast.parse(src)
            for node in ast.walk(tree):
                if not isinstance(node, (ast.FunctionDef,
                                         ast.AsyncFunctionDef)):
                    continue
                aw = []
                opens = []
                locks = []
                for n in ast.walk(node):
                    if isinstance(n, ast.With):
                        for it in n.items:
                            c = it.context_expr
                            if (isinstance(c, ast.Call)
                                    and isinstance(c.func, ast.Name)):
                                if (c.func.id == "AtomicWrite" and c.args):
                                    aw.append(
                                        (n.lineno,
                                         ast.get_source_segment(
                                             src, c.args[0]) or ""))
                                elif (c.func.id == "file_lock" and n.end_lineno
                                      is not None):
                                    locks.append((n.lineno, n.end_lineno))
                    if (isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
                            and n.func.id == "open" and n.args):
                        opens.append(
                            (n.lineno,
                             ast.get_source_segment(src, n.args[0]) or ""))
                for awline, awpath in aw:
                    for oline, opath in opens:
                        if oline >= awline or opath.strip() != awpath.strip():
                            continue
                        covered = any(fl <= oline <= fh and fl <= awline <= fh
                                      for fl, fh in locks)
                        if not covered:
                            offenders.append(
                                f"{fn}:{node.name}: open({opath}) at {oline} "
                                f"before AtomicWrite at {awline}, outside any "
                                "file_lock")
        assert offenders == [], "; ".join(offenders)

    def test_no_fixed_tmp_names_in_write_helpers(self):
        offenders = []
        for fn in _WRITE_FILES:
            src = open(os.path.join(REPO, fn), encoding="utf-8").read()
            tree = ast.parse(src)
            for node in ast.walk(tree):
                if (isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add)
                        and isinstance(node.right, ast.Constant)
                        and node.right.value == ".tmp"):
                    seg = ast.get_source_segment(src, node) or ""
                    offenders.append(f"{fn}:{node.lineno}: {seg}")
        assert offenders == [], (
            "fixed .tmp names race between writers; use _make_temp_file: " +
            "; ".join(offenders))


# ── 9. overhead guard ────────────────────────────────────────────────────────

class TestAppendOverhead:
    def test_locked_append_stays_within_generous_multiple(self, tmp_path):
        path = str(tmp_path / "overhead.log")
        ptos.append_line_fast(path, "warmup")
        n = 150
        locked_times = []
        for i in range(n):
            t0 = time.perf_counter()
            ptos.append_line_fast(path, "line-%d" % i)
            locked_times.append(time.perf_counter() - t0)
        locked = sorted(locked_times)[n // 2]

        real_lock = ptos.file_lock
        ptos.file_lock = lambda *a, **k: contextlib.nullcontext()
        try:
            unlocked_times = []
            for i in range(n):
                t0 = time.perf_counter()
                ptos.append_line_fast(path, "uline-%d" % i)
                unlocked_times.append(time.perf_counter() - t0)
        finally:
            ptos.file_lock = real_lock
        unlocked = sorted(unlocked_times)[n // 2]

        assert locked < 0.05, f"locked median {locked * 1000:.2f}ms too slow"
        assert locked <= max(unlocked * 25.0, 0.002), (
            f"locked median {locked * 1000:.3f}ms vs unlocked "
            f"{unlocked * 1000:.3f}ms")


# ── web mapping: busy -> HTTP 423 ────────────────────────────────────────────

class TestBusyHttp423:
    def test_busy_error_maps_to_423_json(self):
        import ptos_web

        # Routes may catch PTOSError locally (200 + ok:false, like every
        # other business error here); the HTTP 423 mapping is the error
        # handler that uncaught busy errors fall through to.
        with ptos_web.app.test_request_context("/api/anything"):
            resp = ptos_web.handle_ptos_error(
                ptos.FileBusyError("todo.txt is busy; try again"))
        assert isinstance(resp, tuple)
        body, status = resp
        assert status == 423
        data = body.get_json()
        assert data["ok"] is False
        assert "busy" in data["error"]
        assert "try again" in data["error"]

    def test_route_level_busy_keeps_the_message(self):
        import ptos_service as svc_mod
        import ptos_web

        def boom(*_args, **_kwargs):
            raise ptos.FileBusyError("todo.txt is busy; try again")

        client = ptos_web.app.test_client()
        original = svc_mod.capture
        svc_mod.capture = boom
        try:
            resp = client.post("/api/capture", json={"text": "hello"})
        finally:
            svc_mod.capture = original
        data = resp.get_json()
        assert data["ok"] is False
        assert "busy" in data["error"]
