// widget_toml.js — minimal TOML for widget bodies (the ```ptos fence subset).
//
// The gallery form needs to read a hand-edited embed body, change only the
// fields it knows, and write it back — preserving unknown keys and the
// existing key order. There is no npm here, so this is a small purpose-built
// parser/serializer for the flat `key = value` subset widget specs use:
// basic strings (with \" and \\ escapes), literal 'strings', integers,
// floats, booleans, and single-line or line-wrapped arrays of those.
// Comments are dropped (the spec's output is comments-free) and nested
// tables ([section]) are rejected — a widget body is one flat table.
//
// Exposes window.PtosToml = {parse, serialize}. Both are pure (no DOM), so
// tests/js/widget_toml.test.js can run them under `node --test`.
(function (root) {
  "use strict";

  var KEY_RE = /^[A-Za-z0-9_-]+$/;

  function _fail(msg) {
    throw new Error(msg);
  }

  // Strip a trailing comment, respecting quoted strings so `#` inside a
  // value survives. Returns the code part of one logical line.
  function _stripComment(s) {
    var out = "";
    var quote = null;
    for (var i = 0; i < s.length; i++) {
      var c = s[i];
      if (quote) {
        out += c;
        if (c === "\\" && quote === '"' && i + 1 < s.length) {
          out += s[i + 1];
          i++;
          continue;
        }
        if (c === quote) quote = null;
        continue;
      }
      if (c === '"' || c === "'") { quote = c; out += c; continue; }
      if (c === "#") break;
      out += c;
    }
    return out;
  }

  // Bracket balance over one logical line (strings respected), so a value
  // array wrapped across physical lines can be joined before parsing.
  function _balanced(s) {
    var depth = 0;
    var quote = null;
    for (var i = 0; i < s.length; i++) {
      var c = s[i];
      if (quote) {
        if (c === "\\" && quote === '"' && i + 1 < s.length) { i++; continue; }
        if (c === quote) quote = null;
        continue;
      }
      if (c === '"' || c === "'") { quote = c; continue; }
      if (c === "[") depth++;
      else if (c === "]") depth--;
    }
    return depth <= 0;
  }

  function _readString(s, pos, quote) {
    // s[pos] is the opening quote. Returns {value, next}.
    var out = "";
    var i = pos + 1;
    while (i < s.length) {
      var c = s[i];
      if (quote === '"' && c === "\\") {
        var n = s[i + 1];
        if (n === undefined) _fail("Unterminated escape in string");
        if (n === "n") out += "\n";
        else if (n === "t") out += "\t";
        else if (n === "r") out += "\r";
        else if (n === '"') out += '"';
        else if (n === "\\") out += "\\";
        else if (n === "0") out += "\0";
        else out += n;
        i += 2;
        continue;
      }
      if (c === quote) return { value: out, next: i + 1 };
      out += c;
      i++;
    }
    _fail("Unterminated string");
  }

  function _parseScalar(s, pos, key) {
    // s.slice(pos) starts a value. Returns {value, next}.
    var rest = s.slice(pos).replace(/^\s+/, "");
    var off = pos + (s.slice(pos).length - rest.length);
    if (!rest.length) _fail("Missing value for '" + key + "'");
    var c = rest[0];
    if (c === '"' || c === "'") {
      if (rest[1] === c && rest[2] === c) {
        _fail("Multi-line strings are not supported for '" + key + "'");
      }
      var r = _readString(rest, 0, c);
      return { value: r.value, next: off + r.next };
    }
    var m = /^[-+]?(?:\d[\d_]*)(?:\.\d[\d_]*)?(?:[eE][-+]?\d+)?/.exec(rest);
    if (m) {
      var raw = m[0].replace(/_/g, "");
      var num = Number(raw);
      if (isNaN(num)) _fail("Bad number for '" + key + "'");
      return { value: num, next: off + m[0].length };
    }
    if (/^true/.test(rest)) return { value: true, next: off + 4 };
    if (/^false/.test(rest)) return { value: false, next: off + 5 };
    _fail("Cannot parse value for '" + key + "'");
  }

  function _parseValue(s, key) {
    // A complete value (whole logical line after `key =`).
    var t = s.trim();
    if (!t.length) _fail("Missing value for '" + key + "'");
    if (t[0] !== "[") {
      var r = _parseScalar(t, 0, key);
      var tail = t.slice(r.next).trim();
      if (tail) _fail("Unexpected text after value for '" + key + "'");
      return r.value;
    }
    // Array — scalars only.
    var out = [];
    var i = 1;
    while (true) {
      var body = t.slice(i).replace(/^\s+/, "");
      i += t.slice(i).length - body.length;
      if (body[0] === "]") return out;
      if (!body.length) _fail("Unterminated array for '" + key + "'");
      var item = _parseScalar(t, i, key);
      out.push(item.value);
      i = item.next;
      var after = t.slice(i).replace(/^\s+/, "");
      i += t.slice(i).length - after.length;
      if (after[0] === ",") { i += 1; continue; }
      if (after[0] === "]") return out;
      _fail("Expected ',' or ']' in array for '" + key + "'");
    }
  }

  function parse(text) {
    text = String(text == null ? "" : text).replace(/\r\n|\n/g, "\n");
    var out = {};
    var lines = text.split("\n");
    var logical = null;
    var startNo = 0;
    for (var n = 0; n < lines.length; n++) {
      var line = _stripComment(lines[n]).trim();
      if (!line && logical === null) continue;
      if (logical === null) startNo = n + 1;
      logical = logical === null ? line : logical + " " + line;
      if (!_balanced(logical)) continue;
      var body = logical;
      logical = null;
      if (/^\[/.test(body)) {
        _fail("Line " + startNo + ": tables are not supported in a widget body");
      }
      var eq = body.indexOf("=");
      if (eq === -1) _fail("Line " + startNo + ": expected key = value");
      var key = body.slice(0, eq).trim();
      if (!KEY_RE.test(key)) _fail("Line " + startNo + ": bad key '" + key + "'");
      out[key] = _parseValue(body.slice(eq + 1), key);
    }
    if (logical !== null) {
      _fail("Line " + startNo + ": unfinished value");
    }
    return out;
  }

  function _quote(s) {
    var out = '"';
    for (var i = 0; i < s.length; i++) {
      var c = s[i];
      if (c === '"') out += '\\"';
      else if (c === "\\") out += "\\\\";
      else if (c === "\n") out += "\\n";
      else if (c === "\t") out += "\\t";
      else if (c === "\r") out += "\\r";
      else out += c;
    }
    return out + '"';
  }

  function _valStr(v) {
    if (v === true) return "true";
    if (v === false) return "false";
    if (typeof v === "number") {
      if (!isFinite(v)) _fail("Cannot serialize a non-finite number");
      return String(v);
    }
    if (typeof v === "string") return _quote(v);
    if (Array.isArray(v)) {
      return "[" + v.map(_valStr).join(", ") + "]";
    }
    _fail("Cannot serialize value of type " + typeof v);
  }

  // Key order is the object's insertion order, so keys parsed from a
  // hand-edited body come back in the same order the user wrote them;
  // only keys the caller appends land at the end.
  function serialize(obj) {
    var out = [];
    Object.keys(obj || {}).forEach(function (k) {
      var v = obj[k];
      if (v === undefined || v === null) return;
      var key = KEY_RE.test(k) ? k : _quote(k);
      out.push(key + " = " + _valStr(v));
    });
    return out.length ? out.join("\n") + "\n" : "";
  }

  root.PtosToml = { parse: parse, serialize: serialize };
})(typeof window !== "undefined" ? window : globalThis);
