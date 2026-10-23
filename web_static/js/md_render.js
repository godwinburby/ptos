// md_render.js — the single markdown renderer for notes, blocks and home.
// marked parses, DOMPurify sanitizes (fail closed: with either library
// missing the text renders escaped, never raw). Spec: allow standard
// markdown output plus details/summary/br; block script/style/iframe,
// event handlers and javascript:/data: URLs (the URI regex is DOMPurify's).
//
// Part F — inline {{tokens}}: substituted AFTER sanitizing, as text nodes,
// so a name containing markdown or markup characters can never become
// HTML or formatting. `tokenize(text, ctx)` is pure (node-tested via
// tests/js/md_tokens.test.js); the DOM pass walks text nodes with a
// TreeWalker, skips code/pre/script/style ancestors, and wraps each value
// in an md-token span (built with DOM methods) so the boundary/visibility
// refresh can update it in place without re-rendering the note.
(function () {
  var ALLOWED_TAGS = [
    "p", "br", "h1", "h2", "h3", "h4", "h5", "h6",
    "blockquote", "ul", "ol", "li", "hr",
    "strong", "em", "del", "code", "pre",
    "a", "img", "input",
    "table", "thead", "tbody", "tfoot", "tr", "th", "td",
    "details", "summary"
  ];

  // {{token}} or \{{token}} — keys are lowercase (case-sensitive);
  // optional spaces inside the braces are allowed.
  var TOKEN_RE = /\\?\{\{\s*([a-z]+(?::[a-z]+)?)\s*\}\}/g;
  var SKIP_TOKEN_ANCESTORS = "code,pre,script,style";

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

  // ── Part F: tokens ───────────────────────────────────────────────────

  function _pad2(n) {
    return (n < 10 ? "0" : "") + n;
  }

  // Periods keep today's boundaries: before 12:00 morning, before 17:00
  // afternoon, otherwise evening (local clock — the device's, not the
  // server's, which is what fixes the old _greeting() timezone mismatch).
  function periodOf(now) {
    var h = now.getHours();
    if (h < 12) return "morning";
    if (h < 17) return "afternoon";
    return "evening";
  }

  function _fmtDate(d, locale, opts) {
    try {
      return new Intl.DateTimeFormat(locale || undefined, opts).format(d);
    } catch (e) {
      return "";
    }
  }

  // Value for one token key, or null when the key is unknown (unknown
  // tokens are left exactly as typed). Empty values (no saved name)
  // render as nothing.
  function tokenValue(key, now, name, locale) {
    var d = now instanceof Date ? now : new Date(now == null ? Date.now() : now);
    if (key === "greeting") return "Good " + periodOf(d);
    if (key === "period") return periodOf(d);
    if (key === "name") return name == null ? "" : String(name);
    if (key === "weekday") {
      return _fmtDate(d, locale, { weekday: "long" });
    }
    if (key === "time") return _pad2(d.getHours()) + ":" + _pad2(d.getMinutes());
    if (key === "date") {
      return _fmtDate(d, locale,
        { weekday: "short", day: "numeric", month: "short" });
    }
    if (key === "date:long") {
      return _fmtDate(d, locale,
        { weekday: "long", day: "numeric", month: "long", year: "numeric" });
    }
    if (key === "date:iso") {
      return d.getFullYear() + "-" + _pad2(d.getMonth() + 1) + "-" +
        _pad2(d.getDate());
    }
    return null;
  }

  // Pure substitution over source text. ctx = {now, name, locale} —
  // injectable so node tests are machine-independent. \{{name}} shows the
  // literal {{name}}; unknown tokens pass through byte-identical.
  function tokenize(text, ctx) {
    ctx = ctx || {};
    var now = ctx.now instanceof Date ? ctx.now
      : new Date(ctx.now == null ? Date.now() : ctx.now);
    var name = ctx.name == null ? "" : String(ctx.name);
    var locale = ctx.locale || undefined;
    return String(text == null ? "" : text).replace(TOKEN_RE, function (m, key) {
      if (m.charAt(0) === "\\") return m.slice(1);
      var v = tokenValue(key, now, name, locale);
      return v == null ? m : v;
    });
  }

  function _ctx() {
    var ptos = window.PTOS || {};
    return { now: new Date(),
             name: ptos.userName == null ? "" : String(ptos.userName) };
  }

  // Build a DocumentFragment of text nodes and md-token spans for one
  // text node's value; null when the value holds no tokens (the caller
  // then leaves the node alone).
  function _buildFrag(text, ctx, doc) {
    if (String(text).indexOf("{{") === -1) return null;
    var frag = doc.createDocumentFragment();
    var last = 0;
    var m;
    var found = false;
    TOKEN_RE.lastIndex = 0;
    while ((m = TOKEN_RE.exec(text))) {
      frag.appendChild(doc.createTextNode(text.slice(last, m.index)));
      last = m.index + m[0].length;
      if (m[0].charAt(0) === "\\") {
        frag.appendChild(doc.createTextNode(m[0].slice(1)));
      } else {
        var v = tokenValue(m[1], ctx.now, ctx.name, ctx.locale);
        if (v == null) {
          frag.appendChild(doc.createTextNode(m[0]));
        } else {
          var span = doc.createElement("span");
          span.className = "md-token";
          span.setAttribute("data-token", m[1]);
          span.appendChild(doc.createTextNode(v));
          frag.appendChild(span);
        }
      }
      found = true;
    }
    if (!found) return null;
    frag.appendChild(doc.createTextNode(text.slice(last)));
    return frag;
  }

  // Post-sanitize DOM pass: replace token-bearing text nodes under root.
  // Link URLs and attributes are attributes, never text nodes, so they
  // are untouched; inline/fenced code and raw passthrough tags are
  // skipped by the ancestor check.
  function substituteTokens(root, ctx) {
    if (!root || typeof root.querySelectorAll !== "function") return;
    var doc = root.ownerDocument || document;
    if (typeof doc.createTreeWalker !== "function") return;
    ctx = ctx || _ctx();
    var walker = doc.createTreeWalker(root, 1 /* NodeFilter.SHOW_TEXT */, null);
    var nodes = [];
    var n;
    while ((n = walker.nextNode())) {
      if (String(n.nodeValue).indexOf("{{") === -1) continue;
      var par = n.parentElement;
      if (par && typeof par.closest === "function" &&
          par.closest(SKIP_TOKEN_ANCESTORS)) continue;
      nodes.push(n);
    }
    for (var i = 0; i < nodes.length; i++) {
      var node = nodes[i];
      var frag = _buildFrag(node.nodeValue, ctx, doc);
      if (frag && node.parentNode) node.parentNode.replaceChild(frag, node);
    }
  }

  // Refresh every live span in place — textContent only, never a
  // re-render, so focus, selection and open embeds survive.
  function refreshTokens(root) {
    var scope = root || (typeof document !== "undefined" ? document : null);
    if (!scope || typeof scope.querySelectorAll !== "function") return;
    var ctx = _ctx();
    var spans = scope.querySelectorAll(".md-token[data-token]");
    for (var i = 0; i < spans.length; i++) {
      var el = spans[i];
      var v = tokenValue(el.getAttribute("data-token"), ctx.now, ctx.name,
                         ctx.locale);
      if (v == null) continue;
      var doc = el.ownerDocument || document;
      while (el.firstChild) el.removeChild(el.firstChild);
      el.appendChild(doc.createTextNode(v));
    }
  }

  // Milliseconds until the next period boundary (12:00, 17:00, midnight).
  // A boundary already reached is not a candidate, so at exactly 12:00
  // the next fire is 17:00.
  function nextBoundary(now) {
    var base = now instanceof Date ? new Date(now.getTime())
      : new Date(now == null ? Date.now() : now);
    var day = new Date(base.getFullYear(), base.getMonth(), base.getDate());
    var best = null;
    var hours = [12, 17, 0]; // 0 = midnight of the following day
    for (var i = 0; i < hours.length; i++) {
      var t = new Date(day.getTime());
      if (hours[i] === 0) t.setDate(t.getDate() + 1);
      else t.setHours(hours[i], 0, 0, 0);
      var ms = t.getTime() - base.getTime();
      if (ms <= 0) continue;
      if (best === null || ms < best) best = ms;
    }
    return best === null ? 3600000 : best;
  }

  var _refreshTimer = null;

  function _scheduleRefresh() {
    if (typeof document === "undefined" || _refreshTimer != null) return;
    _refreshTimer = setTimeout(function () {
      _refreshTimer = null;
      refreshTokens(document);
      _scheduleRefresh();
    }, nextBoundary(new Date()));
  }

  if (typeof document !== "undefined" && document.addEventListener) {
    document.addEventListener("visibilitychange", function () {
      if (document.visibilityState === "visible") refreshTokens(document);
    });
  }

  function render(text, ctx) {
    var src = String(text == null ? "" : text);
    if (typeof marked === "undefined" || typeof DOMPurify === "undefined") {
      return "<pre style='white-space:pre-wrap'>" + escapeText(src) + "</pre>";
    }
    configureMarked();
    var html = marked.parse(src);
    var clean = DOMPurify.sanitize(html, { ALLOWED_TAGS: ALLOWED_TAGS });
    if (clean.indexOf("{{") === -1) return clean;
    var container = document.createElement("div");
    container.innerHTML = clean;
    substituteTokens(container, ctx || _ctx());
    _scheduleRefresh();
    return container.innerHTML;
  }

  window.PtosMarkdown = {
    render: render,
    ALLOWED_TAGS: ALLOWED_TAGS,
    tokenize: tokenize,
    tokenValue: tokenValue,
    substituteTokens: substituteTokens,
    refreshTokens: refreshTokens,
    nextBoundary: nextBoundary,
    periodOf: periodOf,
  };
  window.renderMarkdown = render;
})();
