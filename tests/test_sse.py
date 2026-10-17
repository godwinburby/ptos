"""SSE stream — heartbeat reaping, client cap, headers, client JS close.

The old stream blocked forever on q.get() with no timeout and only noticed a
closed client on the next broadcast, so every page view leaked one queue and
one blocked thread until a broadcast happened (pre-modularization spec A4)."""
import os
import socket
import threading
import time

import pytest

import ptos_web

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@pytest.fixture
def client():
    ptos_web.app.config["TESTING"] = True
    return ptos_web.app.test_client()


@pytest.fixture(autouse=True)
def _clean_sse_state():
    yield
    with ptos_web._sse_lock:
        ptos_web._sse_clients.clear()
    ptos_web._pending_notifications.clear()


def _next_chunk(it):
    chunk = next(it)
    return chunk.decode("utf-8") if isinstance(chunk, bytes) else chunk


class TestSseHeaders:
    def test_stream_headers(self, client):
        resp = client.get("/api/events")
        assert resp.status_code == 200
        assert resp.mimetype == "text/event-stream"
        assert resp.headers["Cache-Control"] == "no-cache"
        assert resp.headers["X-Accel-Buffering"] == "no"

    def test_stream_starts_with_retry_then_connected(self, client, monkeypatch):
        monkeypatch.setattr(ptos_web, "_SSE_HEARTBEAT_SECONDS", 5.0)
        resp = client.get("/api/events")
        it = resp.response
        assert _next_chunk(it).startswith("retry: 3000")
        assert "connected" in _next_chunk(it)
        resp.close()
        assert ptos_web._sse_clients == []


class TestSseLifecycle:
    def test_close_releases_client(self, client, monkeypatch):
        monkeypatch.setattr(ptos_web, "_SSE_HEARTBEAT_SECONDS", 5.0)
        resp = client.get("/api/events")
        it = resp.response
        next(it)
        next(it)
        assert len(ptos_web._sse_clients) == 1
        resp.close()
        assert ptos_web._sse_clients == []

    def test_broadcast_reaches_live_stream(self, client, monkeypatch):
        monkeypatch.setattr(ptos_web, "_SSE_HEARTBEAT_SECONDS", 5.0)
        resp = client.get("/api/events")
        it = resp.response
        _next_chunk(it)
        _next_chunk(it)
        ptos_web._sse_broadcast("shutdown", "")
        line = _next_chunk(it)
        assert line.startswith("data: ")
        assert "shutdown" in line
        resp.close()

    def test_cap_evicts_oldest_streams(self, client, monkeypatch):
        monkeypatch.setattr(ptos_web, "_SSE_HEARTBEAT_SECONDS", 5.0)
        monkeypatch.setattr(ptos_web, "_SSE_MAX_CLIENTS", 4)
        resps = []
        try:
            for _ in range(6):
                r = client.get("/api/events")
                it = r.response
                next(it)
                next(it)
                resps.append(r)
            assert len(ptos_web._sse_clients) <= 4
        finally:
            for r in resps:
                r.close()


class TestHeartbeatReaping:
    def test_dead_sockets_reaped_within_heartbeat(self, monkeypatch):
        from werkzeug.serving import make_server
        monkeypatch.setattr(ptos_web, "_SSE_HEARTBEAT_SECONDS", 0.15)
        srv = make_server("127.0.0.1", 0, ptos_web.app, threaded=True)
        port = srv.socket.getsockname()[1]
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        socks = []
        try:
            for _ in range(10):
                s = socket.create_connection(("127.0.0.1", port), timeout=5)
                s.sendall(
                    b"GET /api/events HTTP/1.1\r\n"
                    b"Host: 127.0.0.1\r\n"
                    b"Accept: text/event-stream\r\n\r\n")
                s.settimeout(5)
                s.recv(4096)
                socks.append(s)
            deadline = time.time() + 5
            while time.time() < deadline and len(ptos_web._sse_clients) < 10:
                time.sleep(0.05)
            assert len(ptos_web._sse_clients) >= 1
            for s in socks:
                s.close()
            deadline = time.time() + 5
            while time.time() < deadline and ptos_web._sse_clients:
                time.sleep(0.05)
            assert ptos_web._sse_clients == []
        finally:
            for s in socks:
                try:
                    s.close()
                except OSError:
                    pass
            srv.shutdown()


class TestSseClientJs:
    def test_pagehide_closes_and_pageshow_recreates(self):
        path = os.path.join(REPO, "web_static", "js", "sse.js")
        with open(path, encoding="utf-8") as f:
            src = f.read()
        assert "pagehide" in src
        assert "es.close()" in src
        assert "pageshow" in src
        assert 'new EventSource("/api/events")' in src
