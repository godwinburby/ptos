"""Test that all CSS url() references point to existing files."""

import pathlib
import re

CSS_DIR = pathlib.Path(__file__).resolve().parents[1] / "web_static" / "css"
STATIC_DIR = pathlib.Path(__file__).resolve().parents[1] / "web_static"

URL_RE = re.compile(r'url\([\'"]?(.*?)[\'"]?\)')


def test_css_urls_exist():
    """Every url("/static/...") in CSS files must exist under web_static/."""
    for css_file in sorted(CSS_DIR.glob("*.css")):
        text = css_file.read_text(encoding="utf-8")
        for m in URL_RE.finditer(text):
            url = m.group(1)
            # Skip data: URIs and external URLs
            if url.startswith("data:") or url.startswith("http://") or url.startswith("https://"):
                continue
            # Must be /static/... path
            if url.startswith("/static/"):
                rel = url[len("/static/"):]
                target = STATIC_DIR / rel
                assert target.exists(), f"{css_file.name}: url('{url}') -> {target} does not exist"


if __name__ == "__main__":
    test_css_urls_exist()
    print("All CSS url() references exist.")