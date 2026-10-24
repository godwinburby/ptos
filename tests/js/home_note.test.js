// home_note.js pure helpers (node --test, no DOM needed).
// The DOM boot + wiring are pinned statically from tests/test_home_note.py.
const test = require("node:test");
const assert = require("node:assert");
const path = require("path");

globalThis.window = globalThis;
require(path.join(__dirname, "..", "..", "web_static", "js", "embeds.js"));
require(path.join(__dirname, "..", "..", "web_static", "js", "widget_toml.js"));
require(path.join(__dirname, "..", "..", "web_static", "js", "home_note.js"));

const { split, homeContext, applyParamNames, widgetAttrs } =
  window.PtosHomeNote;

test("split groups text runs and widget fences in order", () => {
  const src = [
    "# Hello",
    "",
    "```ptos",
    'view = "todo_summary"',
    "```",
    "",
    "Closing text",
  ].join("\n");
  const out = split(src);
  assert.equal(out.length, 3);
  assert.equal(out[0].type, "text");
  assert.ok(out[0].text.includes("# Hello"));
  assert.equal(out[1].type, "widget");
  assert.equal(out[1].body, 'view = "todo_summary"');
  assert.equal(out[2].type, "text");
  assert.ok(out[2].text.includes("Closing text"));
});

test("split drops blank-only text runs", () => {
  const src = "\n```ptos\nview = \"journal\"\n```\n\n";
  const out = split(src);
  assert.equal(out.length, 1);
  assert.equal(out[0].type, "widget");
});

test("split handles two consecutive fences", () => {
  const src = [
    "```ptos",
    'view = "capture"',
    "```",
    "```ptos",
    'view = "todo_summary"',
    "```",
  ].join("\n");
  const out = split(src);
  assert.equal(out.length, 2);
  assert.equal(out[0].body, 'view = "capture"');
  assert.equal(out[1].body, 'view = "todo_summary"');
});

test("split of text without fences is one text chunk", () => {
  const out = split("just words\n\nmore words");
  assert.equal(out.length, 1);
  assert.equal(out[0].type, "text");
});

test("homeContext defaults to tm", () => {
  assert.deepEqual(homeContext(""), { time: "tm" });
  assert.deepEqual(homeContext("?x=1"), { time: "tm" });
  assert.deepEqual(homeContext("?time=lm"), { time: "lm" });
});

test("homeContext from_date becomes a range", () => {
  assert.deepEqual(homeContext("?from_date=2026-01-01&to_date=2026-01-31"),
                   { time: "range", from_date: "2026-01-01",
                     to_date: "2026-01-31" });
  assert.deepEqual(homeContext("?from_date=2026-01-01"),
                   { time: "range", from_date: "2026-01-01", to_date: null });
});

test("homeContext custom_time literal passes through", () => {
  assert.deepEqual(homeContext("?time=month&custom_time=2026-03"),
                   { time: "2026-03" });
  assert.deepEqual(homeContext("?time=year&custom_time=2026"),
                   { time: "2026" });
  assert.deepEqual(homeContext("?time=date&custom_time=2026-03-09"),
                   { time: "2026-03-09" });
});

test("homeContext invalid custom_time falls back to tm", () => {
  assert.deepEqual(homeContext("?time=month&custom_time=abc"),
                   { time: "tm" });
  assert.deepEqual(homeContext("?time=month"), { time: "tm" });
});

test("applyParamNames swaps a generated due name", () => {
  const spec = { view: "due", name: "default" };
  const out = applyParamNames(spec, {
    due: { from: "default", to: "work" },
  });
  assert.notEqual(out, spec);
  assert.equal(out.name, "work");
  assert.equal(out.view, "due");
});

test("applyParamNames swaps a dashboard name", () => {
  const out = applyParamNames({ view: "dashboard", name: "money" }, {
    dashboard: { from: "money", to: "mixed" },
  });
  assert.equal(out.name, "mixed");
});

test("applyParamNames only swaps matching view + from", () => {
  const spec = { view: "due", name: "bills" };
  assert.equal(applyParamNames(spec, { due: { from: "default", to: "work" } }),
               spec);
  const other = { view: "records", name: "default" };
  assert.equal(applyParamNames(other, { due: { from: "default", to: "work" } }),
               other);
  const same = { view: "due", name: "default" };
  assert.equal(applyParamNames(same, { due: { from: "default", to: "default" } }),
               same);
});

test("applyParamNames is a no-op without params", () => {
  const spec = { view: "due", name: "default" };
  assert.equal(applyParamNames(spec, null), spec);
  assert.equal(applyParamNames(spec, {}), spec);
});

test("widgetAttrs reads span and hide_on", () => {
  assert.deepEqual(widgetAttrs('span = 2\nhide_on = ["phone"]'),
                   { span: 2, hideOn: ["phone"] });
  assert.deepEqual(widgetAttrs('hide_on = "desktop"'),
                   { span: 1, hideOn: ["desktop"] });
  assert.deepEqual(widgetAttrs('hide_on = ["phone", "desktop", "watch"]'),
                   { span: 1, hideOn: ["phone", "desktop"] });
  assert.deepEqual(widgetAttrs('view = "journal"'), { span: 1, hideOn: [] });
});

test("widgetAttrs tolerates unparsable bodies", () => {
  assert.deepEqual(widgetAttrs("span =="), { span: 1, hideOn: [] });
  assert.deepEqual(widgetAttrs(""), { span: 1, hideOn: [] });
});
