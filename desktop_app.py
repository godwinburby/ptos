import sys, os, time, subprocess, shutil, threading

if __name__ == "__main__":
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import ptos
    from ptos_web import app

    ptos.init_ptos()

    port = 5000
    t = threading.Thread(
        target=lambda: app.run(host="127.0.0.1", port=port, threaded=True, use_reloader=False),
        daemon=True,
    )
    t.start()
    time.sleep(0.5)

    browser = shutil.which("msedge") or shutil.which("chrome") or "msedge.exe"
    proc = subprocess.Popen([browser, f"--app=http://127.0.0.1:{port}", "--window-size=420,780"])
    proc.wait()
    os._exit(0)
