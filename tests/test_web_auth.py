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