"""401 + plaintext-migration checks over the real Flask app."""
import base64

import pytest
import tomli_w
import tomllib

import ptos
import ptos_web

BASE = "http://localhost"


def write_auth(auth):
    with open(ptos.CONFIG_PATH, "rb") as f:
        cfg = tomllib.load(f)
    cfg["auth"] = auth
    with open(ptos.CONFIG_PATH, "wb") as f:
        tomli_w.dump(cfg, f)


def creds(user, pw):
    token = base64.b64encode(f"{user}:{pw}".encode()).decode()
    return {"Authorization": "Basic " + token}


@pytest.fixture
def client():
    return ptos_web.app.test_client()


def test_no_auth_section_allows_everything(client):
    assert client.get("/").status_code == 200


def test_wrong_password_is_401(client):
    write_auth({"enabled": True, "username": "u", "password": ptos.hash_password("right")})
    assert client.get("/").status_code == 401
    assert client.get("/", headers=creds("u", "wrong")).status_code == 401
    assert client.get("/", headers=creds("other", "right")).status_code == 401
    assert client.get("/", headers=creds("u", "right")).status_code == 200


def test_disabled_auth_allows_everything(client):
    write_auth({"enabled": False, "username": "u", "password": "irrelevant"})
    assert client.get("/").status_code == 200


def test_plaintext_password_is_upgraded_on_first_login(client):
    write_auth({"enabled": True, "username": "u", "password": "legacy"})
    assert client.get("/", headers=creds("u", "legacy")).status_code == 200
    stored = ptos.get_config()["auth"]["password"]
    assert ptos.is_hashed_password(stored), stored
    assert "legacy" not in open(ptos.CONFIG_PATH, encoding="utf-8").read()
    # the upgraded hash still authenticates
    assert client.get("/", headers=creds("u", "legacy")).status_code == 200


def test_failed_login_does_not_upgrade(client):
    write_auth({"enabled": True, "username": "u", "password": "legacy"})
    assert client.get("/", headers=creds("u", "nope")).status_code == 401
    assert ptos.get_config()["auth"]["password"] == "legacy"


def test_static_files_stay_unauthenticated(client):
    write_auth({"enabled": True, "username": "u", "password": ptos.hash_password("p")})
    assert client.get("/static/js/sse.js").status_code == 200


def test_settings_page_never_renders_the_password(client):
    write_auth({"enabled": True, "username": "u",
                "password": ptos.hash_password("supersecret")})
    body = client.get("/settings", headers=creds("u", "supersecret")).get_data(as_text=True)
    assert body.count('id="auth-password"') == 1
    stored = ptos.get_config()["auth"]["password"]
    assert stored not in body
    assert "pbkdf2" not in body
    assert "Leave blank to keep current" in body


def test_settings_save_keeps_password_when_left_blank(client):
    stored = ptos.hash_password("keepme")
    write_auth({"enabled": True, "username": "u", "password": stored})
    r = client.post("/settings/save", json={
        "auth_enabled": True, "auth_username": "u", "auth_password": ""},
        headers=creds("u", "keepme"))
    assert r.status_code == 200
    assert ptos.get_config()["auth"]["password"] == stored
    assert client.get("/", headers=creds("u", "keepme")).status_code == 200


def test_settings_save_hashes_a_new_password(client):
    write_auth({"enabled": True, "username": "u", "password": ptos.hash_password("old")})
    r = client.post("/settings/save", json={
        "auth_enabled": True, "auth_username": "u", "auth_password": "brandnew"},
        headers=creds("u", "old"))
    assert r.status_code == 200
    new = ptos.get_config()["auth"]["password"]
    assert ptos.verify_password(new, "brandnew")
    assert "brandnew" not in new


def test_settings_save_rejects_blank_password_when_none_set(client):
    write_auth({"enabled": False, "username": "", "password": ""})
    r = client.post("/settings/save", json={
        "auth_enabled": True, "auth_username": "u", "auth_password": ""})
    assert r.status_code == 200
    assert r.get_json()["ok"] is False


def test_settings_save_rejects_blank_username(client):
    write_auth({"enabled": True, "username": "u", "password": ptos.hash_password("p")})
    r = client.post("/settings/save", json={
        "auth_enabled": True, "auth_username": "  ", "auth_password": "x"},
        headers=creds("u", "p"))
    assert r.get_json()["ok"] is False
    assert "Username" in r.get_json()["error"]


def _count_verify(monkeypatch):
    """Patch ptos.verify_password with a call counter; return the counter."""
    import ptos as _ptos
    calls = {"n": 0}
    real = _ptos.verify_password

    def wrapper(stored, pw):
        calls["n"] += 1
        return real(stored, pw)

    monkeypatch.setattr(_ptos, "verify_password", wrapper)
    return calls


class TestAuthCache:
    """Basic auth re-sends the password every request; the KDF is cached.

    The cache must never hold the password, never hold a failure, and stop
    matching the instant the stored password changes.
    """

    @pytest.fixture(autouse=True)
    def _clean_cache(self):
        import ptos_web
        ptos_web.clear_auth_cache()
        yield
        ptos_web.clear_auth_cache()

    def test_second_request_skips_the_kdf(self, client, monkeypatch):
        import ptos_web
        write_auth({"enabled": True, "username": "u",
                    "password": ptos.hash_password("p")})
        calls = _count_verify(monkeypatch)
        for _ in range(3):
            assert client.get("/", headers=creds("u", "p")).status_code == 200
        assert calls["n"] == 1, "the KDF ran more than once"
        assert len(ptos_web._AUTH_CACHE) == 1

    def test_wrong_password_is_never_cached(self, client, monkeypatch):
        import ptos_web
        write_auth({"enabled": True, "username": "u",
                    "password": ptos.hash_password("p")})
        calls = _count_verify(monkeypatch)
        for _ in range(3):
            assert client.get("/", headers=creds("u", "wrong")).status_code == 401
        assert calls["n"] == 3, "a failure was cached"
        assert not ptos_web._AUTH_CACHE

    def test_password_change_invalidates_cached_credentials(self, client):
        write_auth({"enabled": True, "username": "u",
                    "password": ptos.hash_password("old")})
        assert client.get("/", headers=creds("u", "old")).status_code == 200
        ptos.set_auth("u", "new")
        assert client.get("/", headers=creds("u", "old")).status_code == 401
        assert client.get("/", headers=creds("u", "new")).status_code == 200

    def test_settings_save_clears_cached_credentials(self, client):
        import ptos_web
        write_auth({"enabled": True, "username": "u",
                    "password": ptos.hash_password("old")})
        assert client.get("/", headers=creds("u", "old")).status_code == 200
        assert ptos_web._AUTH_CACHE
        r = client.post("/settings/save", json={
            "auth_enabled": True, "auth_username": "u", "auth_password": "new"},
            headers=creds("u", "old"))
        assert r.get_json()["ok"] is True
        assert not ptos_web._AUTH_CACHE
        assert client.get("/", headers=creds("u", "old")).status_code == 401
        assert client.get("/", headers=creds("u", "new")).status_code == 200

    def test_cache_never_exceeds_its_maximum(self, monkeypatch):
        import ptos_web
        monkeypatch.setattr(ptos_web, "_AUTH_CACHE_MAX", 3)
        for i in range(10):
            ptos_web._cache_auth("digest%d" % i, "stored%d" % i)
        assert list(ptos_web._AUTH_CACHE) == ["digest7", "digest8", "digest9"]

    def test_cache_holds_no_plaintext(self, client):
        import ptos_web
        write_auth({"enabled": True, "username": "u",
                    "password": ptos.hash_password("hunter2")})
        assert client.get("/", headers=creds("u", "hunter2")).status_code == 200
        blob = "".join(ptos_web._AUTH_CACHE) + "".join(ptos_web._AUTH_CACHE.values())
        assert "hunter2" not in blob
        assert "u" not in blob

    def test_wrong_username_skips_digest_and_kdf(self, client, monkeypatch):
        import ptos_web
        write_auth({"enabled": True, "username": "u",
                    "password": ptos.hash_password("p")})
        digest_calls = {"n": 0}
        real_digest = ptos_web._cred_digest

        def counting_digest(user, pw):
            digest_calls["n"] += 1
            return real_digest(user, pw)

        monkeypatch.setattr(ptos_web, "_cred_digest", counting_digest)
        kdf = _count_verify(monkeypatch)
        assert client.get("/", headers=creds("other", "p")).status_code == 401
        assert digest_calls["n"] == 0
        assert kdf["n"] == 0

    def test_concurrent_requests_do_not_corrupt(self):
        import threading
        import ptos_web
        write_auth({"enabled": True, "username": "u",
                    "password": ptos.hash_password("p")})
        errors = []

        def hit():
            try:
                c = ptos_web.app.test_client()
                for _ in range(5):
                    if c.get("/", headers=creds("u", "p")).status_code != 200:
                        errors.append("unexpected status")
            except Exception as e:  # pragma: no cover - failure path
                errors.append(repr(e))

        threads = [threading.Thread(target=hit) for _ in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert not errors
        assert len(ptos_web._AUTH_CACHE) <= ptos_web._AUTH_CACHE_MAX

    def test_legacy_plaintext_upgrades_exactly_once(self, client, monkeypatch):
        import ptos
        write_auth({"enabled": True, "username": "u", "password": "legacy"})
        ups = {"n": 0}
        real = ptos.upgrade_auth_password

        def wrapper(user, pw):
            ups["n"] += 1
            return real(user, pw)

        monkeypatch.setattr(ptos, "upgrade_auth_password", wrapper)
        for _ in range(3):
            assert client.get("/", headers=creds("u", "legacy")).status_code == 200
        assert ups["n"] == 1