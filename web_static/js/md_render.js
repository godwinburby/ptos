// md_render.js — the single markdown renderer for notes, blocks and home.
// marked parses, DOMPurify sanitizes (fail closed: with either library
// missing the text renders escaped, never raw). Spec: allow standard
// markdown output plus details/summary/br; block script/style/iframe,
// event handlers and javascript:/data: URLs (the URI regex is DOMPurify's).
(function () {
  var ALLOWED_TAGS = [
    "p", "br", "h1", "h2", "h3", "h4", "h5", "h6",
    "blockquote", "ul", "ol", "li", "hr",
    "strong", "em", "del", "code", "pre",
    "a", "img", "input",
    "table", "thead", "tbody", "tfoot", "tr", "th", "td",
    "details", "summary"
  ];

  function escapeText(s) {
    return String(s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;");
  }

  function configureMarked() {
    if (typeof marked === "undefined" || marked.__ptosDone) return;
    marked.setOptions({ gfm: true, breaks: true });
    var r = new marked.Renderer();
    var orig = r.listitem.bind(r);
    r.listitem = function (text, task, checked) {
      if (task)
        return '<li style="list-style:none;margin-left:-22px;">' +
          '<input type="checkbox" ' + (checked ? "checked" : "") +
          " disabled> " + text + "</li>";
      return orig(text, task, checked);
    };
    marked.use({ renderer: r });
    marked.__ptosDone = true;
  }

  function render(text) {
    var src = String(text == null ? "" : text);
    if (typeof marked === "undefined" || typeof DOMPurify === "undefined") {
      return "<pre style='white-space:pre-wrap'>" + escapeText(src) + "</pre>";
    }
    configureMarked();
    var html = marked.parse(src);
    return DOMPurify.sanitize(html, { ALLOWED_TAGS: ALLOWED_TAGS });
  }

  window.PtosMarkdown = { render: render, ALLOWED_TAGS: ALLOWED_TAGS };
  window.renderMarkdown = render;
})();
