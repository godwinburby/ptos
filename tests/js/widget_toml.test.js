// node --test tests/js/widget_toml.test.js
// Skips entirely when node is absent (CI has none).
const { test } = require("node:test");
const assert = require("node:assert");
const path = require("node:path");

globalThis.window = globalThis;
require(path.join(__dirname, "..", "..", "web_static", "js", "widget_toml.js"));

const { parse, serialize } = globalThis.PtosToml;

test("parse: basic keys and value types", () => {
  const d = parse('view = "records"\nlimit = 8\nper_query = false\ntitle = "Today"');
  assert.deepStrictEqual(d, {
    view: "records",
    limit: 8,
    per_query: false,
    title: "Today",
  });
});

test("parse: floats, negatives and exponents", () => {
  const d = parse("a = -1.5\nb = 2e3\nc = 1_000\nd = +7");
  assert.deepStrictEqual(d, { a: -1.5, b: 2000, c: 1000, d: 7 });
});

test("parse: string escapes survive", () => {
  const d = parse('note = "say \\"hi\\" and use \\\\ or a\\tb"');
  assert.strictEqual(d.note, 'say "hi" and use \\ or a\tb');
});

test("parse: literal single-quoted string", () => {
  const d = parse("where = 'type=expense AND amount > 10'");
  assert.strictEqual(d.where, "type=expense AND amount > 10");
});

test("parse: arrays, empty array, array with spaces", () => {
  const d = parse('project = ["work"]\nmetrics = ["a", "b"]\nempty = []\ngroups = []');
  assert.deepStrictEqual(d, {
    project: ["work"],
    metrics: ["a", "b"],
    empty: [],
    groups: [],
  });
});

test("parse: array wrapped across physical lines", () => {
  const d = parse('metrics = [\n  "a",\n  "b",\n]');
  assert.deepStrictEqual(d, { metrics: ["a", "b"] });
});

test("parse: comments are dropped, # inside strings kept", () => {
  const d = parse('# full line\nview = "metric"  # trailing\nlabel = "a # b"');
  assert.deepStrictEqual(d, { view: "metric", label: "a # b" });
});

test("parse: CRLF input", () => {
  const d = parse('view = "todo"\r\ndue = "overdue"\r\n');
  assert.deepStrictEqual(d, { view: "todo", due: "overdue" });
});

test("parse: unknown keys and hand order are preserved by round trip", () => {
  const src = 'zzz = "last"\nview = "board"\naaa = 1\nname = "demo_job"';
  const keys = Object.keys(parse(src));
  assert.deepStrictEqual(keys, ["zzz", "view", "aaa", "name"]);
  assert.deepStrictEqual(Object.keys(parse(serialize(parse(src)))), [
    "zzz",
    "view",
    "aaa",
    "name",
  ]);
});

test("parse: empty / comment-only body is an empty object", () => {
  assert.deepStrictEqual(parse(""), {});
  assert.deepStrictEqual(parse("# just a comment\n\n"), {});
  assert.strictEqual(serialize({}), "");
});

test("parse errors: bad line, section, unterminated string, missing value", () => {
  assert.throws(() => parse("just words"), /expected key = value/);
  assert.throws(() => parse('[metrics]\nview = "x"'), /tables are not supported/);
  assert.throws(() => parse('title = "open'), /Unterminated string/);
  assert.throws(() => parse("limit ="), /Missing value/);
  assert.throws(() => parse('bad key = "x"'), /bad key/);
});

test("serialize: escaping round trips quotes, backslash, newlines", () => {
  const v = 'He said "hi"\\done\nnext';
  const s = serialize({ note: v });
  assert.strictEqual(s, 'note = "He said \\"hi\\"\\\\done\\nnext"\n');
  assert.strictEqual(parse(s).note, v);
});

test("serialize: numbers and bools stay bare", () => {
  const s = serialize({ limit: 10, ratio: 1.5, on: true, off: false });
  assert.strictEqual(s, "limit = 10\nratio = 1.5\non = true\noff = false\n");
});

test("serialize: null/undefined values are skipped", () => {
  assert.strictEqual(serialize({ a: 1, b: null, c: undefined, d: 2 }), "a = 1\nd = 2\n");
});

test("round trip: full realistic widget body", () => {
  const src =
    '# my widget\nview = "query"\nname = "food_spend"\n' +
    'time = "this-month"\ntitle = "Food spend"\nlimit = 50\nchart = "bar"';
  const obj = parse(src);
  assert.deepStrictEqual(obj, {
    view: "query",
    name: "food_spend",
    time: "this-month",
    title: "Food spend",
    limit: 50,
    chart: "bar",
  });
  assert.deepStrictEqual(parse(serialize(obj)), obj);
});
