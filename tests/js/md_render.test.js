"use strict";
// Phase 0 A3 — behavioral tests for web_static/js/md_render.js.
// node --test tests/js/md_render.test.js
// marked parse + fail-closed + a passthrough-sanitizer case run headless;
// real DOMPurify sanitization needs jsdom and is skipped when absent
// (jsdom is never shipped, only a temp verification install).

const test = require("node:test");
const assert = require("node:assert");
const path = require("node:path");

const ROOT = path.join(__dirname, "..", "..");
const markedNs = require(path.join(ROOT, "web_static", "vendor",
                                   "marked.min.js"));

globalThis.window = globalThis;
globalThis.marked = markedNs.marked || markedNs;
require(path.join(ROOT, "web_static", "js", "md_render.js"));

const { render, ALLOWED_TAGS } = globalThis.PtosMarkdown;

test("helper exports render and an allow list without active content", () => {
  assert.equal(typeof render, "function");
  for (const tag of ["details", "summary", "br", "table", "input",
                     "pre", "a", "img"]) {
    assert.ok(ALLOWED_TAGS.includes(tag), tag);
  }
  for (const tag of ["script", "style", "iframe", "object", "embed"]) {
    assert.ok(!ALLOWED_TAGS.includes(tag), tag);
  }
});

test("fail closed: missing DOMPurify renders escaped text, not HTML", () => {
  const html = render("# hi <b>x</b>\n\n<script>alert(1)</script>");
  assert.ok(html.startsWith("<pre"));
  assert.ok(!html.includes("<h1"));
  assert.ok(!html.includes("<b>"));
  assert.ok(!html.includes("<script"));
  assert.ok(html.includes("# hi"));
  assert.ok(html.includes("&lt;script&gt;"));
});

test("fail closed: missing marked renders escaped text too", () => {
  const saved = globalThis.marked;
  delete globalThis.marked;
  try {
    const html = render("# gone");
    assert.ok(html.startsWith("<pre"));
    assert.ok(!html.includes("<h1"));
    assert.ok(html.includes("# gone"));
  } finally {
    globalThis.marked = saved;
  }
});

test("marked parses tables, task lists and fenced code", () => {
  const table = marked.parse("| a | b |\n|---|---|\n| 1 | 2 |");
  assert.ok(table.includes("<table>"));
  assert.ok(table.includes("<td>"));
  const tasks = marked.parse("- [ ] todo\n- [x] done");
  assert.ok(tasks.includes('type="checkbox"'));
  assert.ok(tasks.includes("checked"));
  const code = marked.parse("```py\nx = 1\n```");
  assert.ok(code.includes("<pre><code"));
});

test("render wires marked options and the task-list hack", () => {
  globalThis.DOMPurify = { sanitize: (html) => html };
  try {
    const html = render("- [x] done");
    assert.ok(html.includes('type="checkbox"'));
    assert.equal((html.match(/type="checkbox"/g) || []).length, 1);
    assert.ok(html.includes('class="md-task-list-item"'));
    assert.ok(html.includes("checked"));
    const breaks = render("line1\nline2");
    assert.ok(breaks.includes("<br>"));
  } finally {
    delete globalThis.DOMPurify;
  }
});

let hasJsdom = false;
try {
  require.resolve("jsdom");
  hasJsdom = true;
} catch (e) {
  hasJsdom = false;
}

test("DOMPurify sanitization end to end (needs jsdom)",
     { skip: hasJsdom ? false : "jsdom not installed" }, () => {
  const { JSDOM } = require("jsdom");
  const purifyMod = require(path.join(ROOT, "web_static", "vendor",
                                      "purify.min.js"));
  const win = new JSDOM("").window;
  const purify = typeof purifyMod === "function" ? purifyMod(win)
                                                 : purifyMod;
  assert.equal(typeof purify.sanitize, "function",
               "unexpected purify export shape");
  globalThis.DOMPurify = purify;
  globalThis.document = win.document;
  globalThis.PTOS = {userName: "Ada"};
  const savedSetTimeout = globalThis.setTimeout;
  globalThis.setTimeout = () => 1;
  try {
    const html = render("# hi\n\n| a | b |\n|---|---|\n| 1 | 2 |");
    assert.ok(html.includes("<h1"));
    assert.ok(html.includes("<table>"));
    assert.ok(render("- [x] done").includes('type="checkbox"'));
    assert.ok(render("<details><summary>s</summary>t</details>")
                .includes("<details>"));

    assert.ok(!render("<script>alert(1)</script>")
                .toLowerCase().includes("<script"));
    assert.ok(!render("<img src=x onerror=alert(1)>")
                .includes("onerror"));
    assert.ok(!render("[x](javascript:alert(1))")
                .includes("javascript:"));
    assert.ok(!render("<iframe src=//evil></iframe>")
                .includes("<iframe"));
    assert.ok(!render("<style>body{}</style>").includes("<style"));
    assert.ok(!render('<p style="position:fixed">x</p>').includes("style="));
    assert.ok(!render('<input type="password" value="secret">').includes('type="password"'));
    assert.ok(render('<input type="checkbox" disabled>').includes('type="checkbox"'));
    assert.ok(render("\\{{name}}").includes("{{name}}"));
    const doubledEscape = render("\\\\{{name}}");
    assert.ok(doubledEscape.includes("{{name}}"));
    assert.ok(!doubledEscape.includes("Ada"));
    assert.ok(render("`\\{{name}}`").includes("\\{{name}}"));
    assert.ok(render("{{name}}").includes("Ada"));
  } finally {
    delete globalThis.DOMPurify;
    delete globalThis.document;
    delete globalThis.PTOS;
    globalThis.setTimeout = savedSetTimeout;
  }
});
