"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const path = require("node:path");

globalThis.window = globalThis;
require(path.join(__dirname, "..", "..", "web_static", "js", "text_blocks.js"));
require(path.join(__dirname, "..", "..", "web_static", "js", "md_toolbar.js"));
const T = globalThis.PtosToolbar;

test("shared text block catalog defines picker and slash entries once", () => {
  const items = globalThis.PtosTextBlocks;
  const ids = items.map((item) => item.id);
  assert.equal(new Set(ids).size, ids.length);
  for (const item of items) {
    for (const key of ["label", "aliases", "description", "icon", "seed", "caret"]) {
      assert.ok(item[key] !== undefined, `${item.id}.${key}`);
    }
    assert.ok(item.caret >= 0 && item.caret <= item.seed.length, item.id);
  }
  for (const id of ["heading-1", "heading-2", "heading-3", "paragraph",
                    "bulleted-list", "numbered-list", "checklist", "quote",
                    "callout", "divider", "table", "code-block",
                    "greeting-line", "today-date", "your-name"]) {
    assert.ok(ids.includes(id), id);
  }
});

test("wrap selection adds and removes markdown delimiters", () => {
  const wrapped = T.wrapSelection("hello", 1, 4, "**", "**");
  assert.deepEqual(wrapped, { text: "h**ell**o", start: 3, end: 6 });
  assert.deepEqual(T.wrapSelection("**hello**", 2, 7, "**", "**"),
    { text: "hello", start: 0, end: 5 });
});

test("empty selection inserts paired markers with the caret between them", () => {
  assert.deepEqual(T.wrapSelection("x", 1, 1, "`", "`"),
    { text: "x``", start: 2, end: 2 });
});

test("line prefix toggles and replaces mixed list types", () => {
  const input = "- one\n2. two\n> three";
  assert.equal(T.togglePrefix(input, 0, input.length, "- ").text,
    "one\n- two\n- three");
  const numbered = T.togglePrefix(input, 0, input.length, "1. ");
  assert.equal(numbered.text, "1. one\n2. two\n3. three");
  assert.equal(T.togglePrefix(numbered.text, 0, numbered.text.length, "1. ").text,
    "one\ntwo\nthree");
});

test("heading levels replace existing heading markers and preserve CRLF", () => {
  assert.equal(T.heading("# First\r\nplain", 0, 13, 3).text,
    "### First\r\n### plain");
});

test("link validation accepts web and internal paths and rejects unsafe URLs", () => {
  for (const url of ["https://example.com", "http://example.com", "mailto:a@b.test", "/notes/a", "?q=x", "#part"]) {
    assert.notEqual(T.linkMarkup("label", url), null, url);
  }
  for (const url of ["javascript:alert(1)", "data:text/html,x", "//evil.test", "\\\\evil.test", "https://x.test\n"])
    assert.equal(T.linkMarkup("label", url), null, url);
  assert.deepEqual(T.insertLink("", 0, 0, null),
    { text: "[ ]()", start: 1, end: 1 });
  const selected = T.insertLink("visit", 0, 5, null);
  assert.equal(selected.text, "[visit](url)");
  assert.deepEqual([selected.start, selected.end], [8, 11]);
  const linked = T.insertLink("visit", 0, 5, "https://example.com");
  assert.equal(linked.text, "[visit](https://example.com)");
  assert.equal(linked.start, linked.text.length);
  assert.equal(T.insertLink("visit", 0, 5, "javascript:alert(1)"), null);
});

test("Enter continues bullet and numbered lists, and exits empty items", () => {
  assert.equal(T.continueList("- one", 5, 5).text, "- one\n- ");
  assert.equal(T.continueList("4. one", 6, 6).text, "4. one\n5. ");
  assert.equal(T.continueList("- ", 2, 2).text, "");
  assert.equal(T.continueList("plain", 5, 5), null);
});

test("indent and outdent selected lines, preserving CRLF", () => {
  const indented = T.indentLines("- one\r\n- two", 0, 11, false);
  assert.equal(indented.text, "  - one\r\n  - two");
  assert.equal(T.indentLines(indented.text, 0, indented.text.length, true).text,
    "- one\r\n- two");
});

test("selection helpers preserve Unicode and emoji", () => {
  const value = "A 🐈 B";
  const start = value.indexOf("🐈");
  const end = start + "🐈".length;
  const wrapped = T.wrapSelection(value, start, end, "**", "**");
  assert.equal(wrapped.text, "A **🐈** B");
  assert.equal(wrapped.text.slice(wrapped.start, wrapped.end), "🐈");
});
