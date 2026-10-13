// md_highlight.js — markdown syntax colouring for the editor's colour view.
//
// Pure, dependency-free tokenizers that turn a markdown source string into
// highlighted HTML: headings, emphasis, links, [[cross-links]], inline code,
// lists, quotes, task boxes, and fenced blocks whose ```ptos bodies are
// tokenized as TOML. The notes/journal editor renders the result into a
// read-only <pre> when you switch to its colour view (see
// _markdown_editor.html); it is never re-run per keystroke, and the stored
// text is never modified.
(function () {
  function _esc(s) {
    return String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;")
                    .replace(/>/g, "&gt;");
  }

  var _INLINE = /\*\*([^*]+)\*\*|__([^_]+)__|\*([^*]+)\*|_([^_]+)_|~~([^~]+)~~|`([^`]+)`|\[\[([^\]]+)\]\]|\[([^\]]+)\]\([^)\s]+\)/g;

  function inline(text) {
    var out = "", last = 0, m = null;
    _INLINE.lastIndex = 0;
    while ((m = _INLINE.exec(text)) !== null) {
      out += _esc(text.slice(last, m.index));
      if (m[1] !== undefined) out += '<span class="mh-b">' + _esc(m[1]) + "</span>";
      else if (m[2] !== undefined) out += '<span class="mh-b">' + _esc(m[2]) + "</span>";
      else if (m[3] !== undefined) out += '<span class="mh-i">' + _esc(m[3]) + "</span>";
      else if (m[4] !== undefined) out += '<span class="mh-i">' + _esc(m[4]) + "</span>";
      else if (m[5] !== undefined) out += '<span class="mh-s">' + _esc(m[5]) + "</span>";
      else if (m[6] !== undefined) out += '<span class="mh-c">' + _esc(m[6]) + "</span>";
      else if (m[7] !== undefined) out += '<span class="mh-br">' + _esc(m[7]) + "</span>";
      else if (m[8] !== undefined) out += '<span class="mh-link">' + _esc(m[8]) + "</span>";
      last = _INLINE.lastIndex;
    }
    return out + _esc(text.slice(last));
  }

  function tomlValue(v) {
    var out = "", last = 0, m = null;
    var RE = /("(?:[^"\\]|\\.)*")|(\b\d[\d_.]*\b)|(\b(?:true|false)\b)|(\[[^\]]*\])/g;
    while ((m = RE.exec(v)) !== null) {
      out += _esc(v.slice(last, m.index));
      if (m[1] !== undefined) out += '<span class="mh-tk-str">' + _esc(m[1]) + "</span>";
      else if (m[4] !== undefined) out += _tomlArray(m[4]);
      else out += '<span class="mh-tk-num">' + _esc(m[0]) + "</span>";
      last = RE.lastIndex;
    }
    return out + _esc(v.slice(last));
  }

  function _tomlArray(a) {
    var out = "", last = 0, m = null;
    var RE = /"(?:[^"\\]|\\.)*"|\b\d[\d_.]*\b|\b(?:true|false)\b/g;
    while ((m = RE.exec(a)) !== null) {
      out += _esc(a.slice(last, m.index));
      if (m[0].charAt(0) === '"') out += '<span class="mh-tk-str">' + _esc(m[0]) + "</span>";
      else out += '<span class="mh-tk-num">' + _esc(m[0]) + "</span>";
      last = RE.lastIndex;
    }
    return out + _esc(a.slice(last));
  }

  function tomlLine(line) {
    var lead = /^(\s*)/.exec(line)[1];
    var rest = line.slice(lead.length);
    if (!rest.trim() || rest.trim().charAt(0) === "#") return _esc(line);
    var m = /^([A-Za-z0-9_.-]+)\s*(=)\s*(.*)$/.exec(rest);
    if (m) {
      return lead +
        '<span class="mh-tk-key">' + _esc(m[1]) + "</span>" +
        '<span class="mh-tk-punct">' + _esc(m[2]) + "</span> " +
        tomlValue(m[3]);
    }
    return _esc(line);
  }

  function blockLine(line) {
    var h = /^(\s*)(#{1,6})(\s+)(.*)$/.exec(line);
    if (h) {
      return h[1] + '<span class="mh-h' + h[2].length + '">' + _esc(h[2]) + "</span>" +
        h[3] + inline(h[4]);
    }
    var q = /^(\s*)(>+)(\s*)(.*)$/.exec(line);
    if (q) {
      return q[1] + '<span class="mh-q">' + _esc(q[2]) + "</span>" + q[3] + inline(q[4]);
    }
    if (/^\s*(\*{3,}|-{3,}|_{3,})\s*$/.test(line)) {
      return '<span class="mh-hr">' + _esc(line) + "</span>";
    }
    var t = /^(\s*)([-*+])(\s+)(\[[ xX]\]\s+)?(.*)$/.exec(line);
    if (t) {
      var head = t[1] + '<span class="mh-op">' + _esc(t[2]) + "</span>";
      var body = t[3] +
        (t[4] ? '<span class="mh-task">' + _esc(t[4].trim()) + "</span> " : "") +
        inline(t[5]);
      return head + body;
    }
    var o = /^(\s*)(\d+)([.)])(\s+)(.*)$/.exec(line);
    if (o) {
      return o[1] + '<span class="mh-op">' + _esc(o[2]) + _esc(o[3]) + "</span>" +
        o[4] + inline(o[5]);
    }
    return inline(line);
  }

  function markdown(src) {
    var lines = String(src || "").split(/\r\n|\n/);
    var out = [];
    var fenced = false, fenceLang = null;
    for (var i = 0; i < lines.length; i++) {
      var line = lines[i];
      var flat = line.trim();
      if (fenced) {
        if (flat === "```") {
          out.push('<span class="mh-fence">' + _esc(line) + "</span>");
          fenced = false;
          fenceLang = null;
        } else if (fenceLang === "ptos") {
          out.push('<span class="mh-fence">' + tomlLine(line) + "</span>");
        } else {
          out.push('<span class="mh-fence">' + _esc(line) + "</span>");
        }
        continue;
      }
      var fm = /^```([\w-]*)\s*$/.exec(flat);
      if (fm) {
        out.push('<span class="mh-fence mh-fence-open">' + _esc(line) + "</span>");
        fenced = true;
        fenceLang = fm[1];
        continue;
      }
      out.push(blockLine(line));
    }
    return out.join("\n");
  }

  function toml(src) {
    var lines = String(src || "").split(/\r\n|\n/);
    var out = [];
    for (var i = 0; i < lines.length; i++) out.push(tomlLine(lines[i]));
    return out.join("\n");
  }

  window.mdHighlight = { markdown: markdown, toml: toml };
})();