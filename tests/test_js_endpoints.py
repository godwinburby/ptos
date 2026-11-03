"""Every literal URL the browser JS posts or fetches must resolve to a Flask route."""
import glob
import re

import pytest
from werkzeug.exceptions import MethodNotAllowed, NotFound

from ptos_web import app

CALL = re.compile(
    r"""(?:_post|fetch|postJson|postJSON)\(\s*(["'])(/[^"'?#]*)\1\s*([,)+]?)""")


def _literal_endpoints():
    for path in sorted(glob.glob("web_static/js/*.js")):
        with open(path, encoding="utf-8") as fh:
            src = fh.read()
        for m in CALL.finditer(src):
            if m.group(3) == "+":  # prefix of a dynamic URL, cannot check
                continue
            yield path, m.group(2)


@pytest.mark.parametrize("path,url", sorted(set(_literal_endpoints())))
def test_js_endpoint_exists(path, url):
    adapter = app.url_map.bind("localhost")
    for method in ("POST", "GET"):
        try:
            adapter.match(url, method=method)
            return
        except MethodNotAllowed:
            return
        except NotFound:
            continue
    pytest.fail("%s calls %s, which has no Flask route" % (path, url))
