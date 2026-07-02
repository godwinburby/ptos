import sys, os, time, shutil, threading, socket, traceback

_log_path = os.path.join(os.environ.get("TEMP", "."), "ptos_desktop.log")

def _log(msg):
    with open(_log_path, "a") as f:
        f.write(f"{time.strftime('%H:%M:%S')} {msg}\n")

def _find_browser():
    names = ["msedge", "chrome", "msedge.exe", "chrome.exe"]
    for name in names:
        path = shutil.which(name)
        if path:
            return path
    local = os.environ.get("LOCALAPPDATA", "")
    prog = os.environ.get("ProgramFiles(x86)", "")
    candidates = [
        os.path.join(prog, "Microsoft", "Edge", "Application", "msedge.exe") if prog else "",
        os.path.join(prog.replace(" (x86)", ""), "Microsoft", "Edge", "Application", "msedge.exe"),
        os.path.join(prog, "Google", "Chrome", "Application", "chrome.exe") if prog else "",
        os.path.join(local, "Microsoft", "Edge", "Application", "msedge.exe"),
        os.path.join(local, "Google", "Chrome", "Application", "chrome.exe"),
    ]
    for path in candidates:
        if path and os.path.isfile(path):
            return path
    return None

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

if __name__ == "__main__":
    sys.excepthook = _crash_handler
    os.environ["DESKTOP_MODE"] = "1"
    _log("=== PTOS desktop start ===")
    _log(f"_MEIPASS={getattr(sys, '_MEIPASS', 'none')} frozen={getattr(sys, 'frozen', False)}")

    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import ptos
    from ptos_web import app

    ptos.init_ptos()
    _log("init_ptos done")

    import ptos_service as svc
    try:
        if svc.get_backup_config().get("backup_on_startup", True):
            created, _ = svc.backup_if_needed()
            if created:
                print("Startup backup created")
    except Exception:
        pass

    port = 5000
    threading.Thread(
        target=lambda: app.run(host="127.0.0.1", port=port, threaded=True, use_reloader=False),
        daemon=True,
    ).start()
    _log("Flask thread started")

    _wait_for_server("127.0.0.1", port)
    _log("Server ready, launching browser")

    import webbrowser
    webbrowser.open(f"http://127.0.0.1:{port}")
    _log("Browser opened")

    print(f"PTOS running at http://127.0.0.1:{port}")
    print("Close the browser window to stop the server.")
    while True:
        time.sleep(3600)
