"""Characterization tests for /browse page (Wave 2 Phase 1, G0).

Lock the current /browse GET output and /browse/run POST behavior so the
migration to a controller-based shell cannot silently change them.
"""
import os

import pytest

from ptos_web import app


@pytest.fixture
def client():
    return app.test_client()


class TestBrowsePageGet:
    def test_returns_200(self, client):
        r = client.get("/browse")
        assert r.status_code == 200

    def test_contains_filter_mount(self, client):
        body = client.get("/browse").get_data(as_text=True)
        assert 'id="browse-filter"' in body

    def test_contains_result_area(self, client):
        body = client.get("/browse").get_data(as_text=True)
        assert 'id="result-area"' in body

    def test_contains_time_select(self, client):
        body = client.get("/browse").get_data(as_text=True)
        assert 'id="b-time-select"' in body

    def test_contains_group_sort_selects(self, client):
        body = client.get("/browse").get_data(as_text=True)
        assert 'id="b-group"' in body
        assert 'id="b-sort"' in body

    def test_contains_search_input(self, client):
        body = client.get("/browse").get_data(as_text=True)
        assert 'id="b-search"' in body

    def test_contains_save_as_query_button(self, client):
        body = client.get("/browse").get_data(as_text=True)
        assert "Save as Query" in body

    def test_legacy_renders_old_template(self, client):
        body = client.get("/browse?legacy=1").get_data(as_text=True)
        assert 'id="browse-filter"' in body
        assert 'id="result-area"' in body

    def test_time_param_reflected(self, client):
        body = client.get("/browse?time=lw").get_data(as_text=True)
        assert 'value="lw"' in body

    def test_search_param_reflected(self, client):
        body = client.get("/browse?search=foo").get_data(as_text=True)
        assert 'value="foo"' in body or "foo" in body

    def test_group_param_reflected(self, client):
        body = client.get("/browse?group=date").get_data(as_text=True)
        assert "date" in body


class TestBrowseRunPost:
    def test_returns_ok_with_records(self, client):
        r = client.post("/browse/run", json={"time": "tm"})
        assert r.status_code == 200
        d = r.get_json()
        assert d["ok"] is True
        assert d["data"]["kind"] == "records"

    def test_group_path(self, client):
        r = client.post("/browse/run", json={"time": "tm", "group": "type"})
        assert r.status_code == 200
        d = r.get_json()
        assert d["ok"] is True
        assert d["data"]["kind"] == "group"

    def test_expr_where_combination(self, client):
        r = client.post("/browse/run", json={"time": "tm", "expr": "type=expense", "where": ["tag=food"]})
        assert r.status_code == 200
        d = r.get_json()
        assert d["ok"] is True

    def test_invalid_time_falls_back(self, client):
        r = client.post("/browse/run", json={"time": "notacode"})
        assert r.status_code == 200
        d = r.get_json()
        assert d["ok"] is True

    def test_error_response_shape(self, client):
        r = client.post("/browse/run", json={"time": "tm", "expr": "==="})
        d = r.get_json()
        assert "ok" in d
