import sys, os, time, shutil, threading, socket, traceback

_log_path = os.path.join(os.environ.get("TEMP", "."), "ptos_desktop.log")

def _log(msg):
    with open(_log_path, "a") as f:
        f.write(f"{time.strftime('%H:%M:%S')} {msg}\n")

def _wait_for_server(host, port):
    while True:
        try:
            s = socket.create_connection((host, port), timeout=0.5)
            s.close()
            return
        except OSError:
            time.sleep(0.2)

def _show_error_dialog(title, msg, details=""):
    import tkinter as tk
    from tkinter import scrolledtext
    win = tk.Tk()
    win.title(title)
    win.geometry("560x380")
    tk.Label(win, text=msg, wraplength=520).pack(pady=(14, 4))
    if details:
        txt = scrolledtext.ScrolledText(win, height=10, font=("Consolas", 9))
        txt.insert("1.0", details)
        txt.config(state="disabled")
        txt.pack(padx=10, pady=(0, 6), fill="both", expand=True)

        def _copy():
            win.clipboard_clear()
            win.clipboard_append(details)
        tk.Button(win, text="Copy to Clipboard", command=_copy).pack(pady=(0, 10))
    else:
        tk.Button(win, text="OK", command=win.destroy).pack(pady=(0, 10))
    win.mainloop()

def _crash_handler(typ, value, tb):
    msg = "".join(traceback.format_exception(typ, value, tb))
    try:
        with open(_log_path, "a") as f:
            f.write(f"CRASH: {msg}\n")
    except Exception:
        pass
    _show_error_dialog("Unexpected Error", "Something went wrong.", msg)


# ── Single-instance detection (Windows named mutex) ───────────────────────────

def _is_already_running():
    try:
        import ctypes
        kernel32 = ctypes.windll.kernel32
        mutex = kernel32.CreateMutexW(None, False, "PTOS-Desktop-App")
        if kernel32.GetLastError() == 183:
            kernel32.CloseHandle(mutex)
            return True
        return False
    except Exception:
        return False


# ── PyWebView native window management ────────────────────────────────────────

_window = None
_stopping = False

def _has_webview():
    try:
        import webview
        return True
    except ImportError:
        return False

class _Api:
    def __init__(self, port):
        self.port = port

    def close_app(self):
        global _stopping
        _stopping = True
        try:
            import ptos_service as svc
            if svc.get_backup_config().get("auto_backup_on_startup", True):
                svc.backup_if_needed()
        except Exception:
            pass
        _destroy_window()

def _icon_path():
    try:
        base = sys._MEIPASS
    except AttributeError:
        base = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base, "icon.ico")

def _create_window(port):
    global _window
    import webview
    _window = webview.create_window(
        "PTOS", f"http://127.0.0.1:{port}",
        width=1100, height=750,
        resizable=True, text_select=True,
        icon=_icon_path(),
        js_api=_Api(port),
    )
    def _on_closing():
        global _window
        if _stopping:
            return True
        _window.hide()
        return False
    _window.events.closing += _on_closing

def _show_window():
    if _window:
        _window.show()
        try:
            _window.focus()
        except TypeError:
            pass

def _destroy_window():
    global _window
    if _window:
        _window.destroy()
        _window = None


# ── System tray icon ──────────────────────────────────────────────────────────

def _run_tray(port):
    try:
        import pystray
        from PIL import Image, ImageDraw
    except ImportError:
        _log("pystray/PIL not available, running without tray icon")
        while True:
            time.sleep(3600)
        return

    def _make_image():
        # 64px tray icon matching the PTOS compass+monogram design
        img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        K = 64 / 512
        blue = (36, 86, 245)
        red  = (240, 75, 55)
        dark = (23, 68, 200)

        def rx(x): return int(x * K)
        def ry(y): return int(y * K)

        # Outer ring
        r = int(215 * K)
        w = max(1, int(24 * K))
        draw.ellipse([32 - r, 32 - r, 32 + r, 32 + r], outline=blue, width=w)

        # Break cover
        bx, by = rx(430), ry(82)
        br = int(28 * K)
        draw.ellipse([bx - br, by - br, bx + br, by + br], fill=(255, 255, 255, 255))

        # Orbit node
        nr = int(12 * K)
        draw.ellipse([bx - nr, by - nr, bx + nr, by + nr], fill=blue)

        # P stem
        draw.rounded_rectangle([rx(188), ry(150), rx(188) + int(26*K), ry(150) + int(215*K)],
                               radius=int(13*K), fill=dark)
        # P top
        draw.rounded_rectangle([rx(188), ry(150), rx(188) + int(145*K), ry(150) + int(26*K)],
                               radius=int(13*K), fill=dark)
        # P bowl as thick arc approximation
        draw.arc([rx(333)-3, ry(163), rx(333)+3, ry(255)], 90, 180, fill=dark, width=int(6*K))
        draw.arc([rx(333)-3, ry(189), rx(333)+3, ry(229)], 90, 180, fill=dark, width=int(6*K))
        # fill the gap between arcs with a rect
        draw.rectangle([rx(333)-3, ry(189), rx(333)+3, ry(229)], fill=dark)
        # fill left side of bowl
        draw.rectangle([rx(256), ry(163), rx(333), ry(255)], fill=dark)

        # T stem
        draw.rounded_rectangle([rx(240), ry(280), rx(240) + int(32*K), ry(280) + int(140*K)],
                               radius=int(16*K), fill=dark)
        # T crossbar
        draw.rounded_rectangle([rx(165), ry(280), rx(165) + int(150*K), ry(280) + int(24*K)],
                               radius=int(12*K), fill=dark)

        # Compass arrow
        draw.polygon([(rx(318), ry(165)), (rx(392), ry(126)), (rx(344), ry(205))], fill=red)

        # Center pivot
        pr = int(22 * K)
        draw.ellipse([32 - pr, 32 - pr, 32 + pr, 32 + pr], fill=blue)
        return img

    def _open():
        if _has_webview():
            _show_window()
        else:
            os.startfile(f"http://127.0.0.1:{port}")

    def _stop(icon, item):
        global _stopping
        _stopping = True
        icon.stop()
        import urllib.request
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{port}/shutdown", timeout=3)
        except Exception:
            os._exit(0)

    menu = pystray.Menu(
        pystray.MenuItem("Open PTOS", _open, default=True),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Stop Server", _stop),
    )
    pystray.Icon("ptos", _make_image(), "PTOS", menu).run()

    # After icon stops, destroy window and exit
    _destroy_window()


# ── Main ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    sys.excepthook = _crash_handler
    os.environ["DESKTOP_MODE"] = "1"
    _log("=== PTOS desktop start ===")
    _log(f"_MEIPASS={getattr(sys, '_MEIPASS', 'none')} frozen={getattr(sys, 'frozen', False)}")

    port = 5000

    if _is_already_running():
        _log("Another instance is already running")
        import ctypes
        ctypes.windll.user32.MessageBoxW(0,
            "PTOS is already running.",
            "PTOS", 0)
        sys.exit(0)

    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import ptos
    from ptos_web import app

    ptos.init_ptos()
    _log("init_ptos done")

    import ptos_service as svc
    try:
        if svc.get_backup_config().get("auto_backup_on_startup", True):
            created, _ = svc.backup_if_needed()
            if created:
                print("Startup backup created")
    except Exception:
        pass

    threading.Thread(
        target=lambda: app.run(host="127.0.0.1", port=port, threaded=True, use_reloader=False),
        daemon=True,
    ).start()
    _log("Flask thread started")

    _wait_for_server("127.0.0.1", port)
    _log("Server ready")

    # Decide window mode
    if _has_webview():
        _log("Using PyWebView native window")
        _create_window(port)
        threading.Thread(target=_run_tray, args=(port,), daemon=True).start()
        import webview
        webview.start()
    else:
        _log("PyWebView not available, using system browser")
        import webbrowser
        webbrowser.open(f"http://127.0.0.1:{port}")
        _run_tray(port)
