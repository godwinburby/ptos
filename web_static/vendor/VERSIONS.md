# Vendored front-end libraries

No CDN dependencies — PTOS must render offline (LAN/Tailscale phone server).

| File | Library | Version | License | Source |
|---|---|---|---|---|
| `marked.min.js` | marked (markdown parser) | 9.1.6 | MIT (+ Markdown.js BSD, see `marked-LICENSE`) | cdnjs `marked/9.1.6` |
| `purify.min.js` | DOMPurify (HTML sanitizer) | 3.4.17 | (MPL-2.0 OR Apache-2.0); Apache-2.0 text in `purify-LICENSE` | cdnjs `dompurify/3.4.17` |

Full license texts ship alongside these files (`marked-LICENSE`, `purify-LICENSE`).

- Loaded only through the `av()` Jinja global (versioned URLs, cache-busted automatically).
- The shared render helper is `web_static/js/md_render.js` (`window.renderMarkdown`):
  marked → DOMPurify.sanitize → caller inserts the result. Never call
  `marked.parse` directly from a template.
- Keep pins in sync: `tests/test_md_render.py` asserts the versions above.
