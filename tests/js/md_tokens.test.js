// Part F — pure tokenize + nextBoundary (node --test, no DOM needed).
// The TreeWalker span pass is pinned statically from tests/test_md_render.py.
const test = require("node:test");
const assert = require("node:assert");
const path = require("path");

globalThis.window = globalThis;
require(path.join(__dirname, "..", "..", "web_static", "js", "md_render.js"));

const { tokenize, nextBoundary, tokenValue, periodOf } = window.PtosMarkdown;

// Local-component dates so getHours()/getDate() are process-TZ safe.
function at(h, m, s) {
  return new Date(2026, 9, 19, h, m || 0, s || 0); // 2026-10-19
}
const CTX = { now: at(9, 30), name: "Godwin", locale: "en-GB" };

test("every token with an injected context", () => {
  assert.equal(tokenize("{{greeting}}", CTX), "Good morning");
  assert.equal(tokenize("{{period}}", CTX), "morning");
  assert.equal(tokenize("{{name}}", CTX), "Godwin");
  assert.equal(tokenize("{{date}}", CTX), "Mon 19 Oct");
  assert.equal(tokenize("{{date:long}}", CTX), "Monday, 19 October 2026");
  assert.equal(tokenize("{{date:iso}}", CTX), "2026-10-19");
  assert.equal(tokenize("{{weekday}}", CTX), "Monday");
  assert.equal(tokenize("{{time}}", CTX), "09:30");
});

test("period boundaries at 11:59, 12:00, 16:59 and 17:00", () => {
  const cases = [
    [at(11, 59), "morning", "Good morning"],
    [at(12, 0), "afternoon", "Good afternoon"],
    [at(16, 59), "afternoon", "Good afternoon"],
    [at(17, 0), "evening", "Good evening"],
    [at(23, 59), "evening", "Good evening"],
  ];
  for (const [now, period, greeting] of cases) {
    assert.equal(tokenize("{{period}}", { now, name: "X" }), period);
    assert.equal(tokenize("{{greeting}}", { now, name: "X" }), greeting);
  }
});

test("unknown tokens are left exactly as typed", () => {
  assert.equal(tokenize("{{foo}} and {{Name}}", CTX), "{{foo}} and {{Name}}");
  assert.equal(tokenize("{{ notatoken }}", CTX), "{{ notatoken }}");
});

test("spaces inside the braces are allowed", () => {
  assert.equal(tokenize("{{ name }}", CTX), "Godwin");
  assert.equal(tokenize("{{  date:iso  }}", CTX), "2026-10-19");
});

test("backslash escapes to the literal token text", () => {
  assert.equal(tokenize("\\{{name}}", CTX), "{{name}}");
  assert.equal(tokenize("a \\{{date}} b", CTX), "a {{date}} b");
});

test("adjacent tokens and surrounding text", () => {
  assert.equal(tokenize("{{name}}{{date:iso}}", CTX), "Godwin2026-10-19");
  assert.equal(
    tokenize("Hi {{name}}, it is {{time}} on {{date}}!", CTX),
    "Hi Godwin, it is 09:30 on Mon 19 Oct!");
});

test("an empty name renders as nothing", () => {
  assert.equal(tokenize("A{{name}}B", { now: at(9, 30), name: "" }), "AB");
  assert.equal(tokenize("{{name}}", { now: at(9, 30) }), "");
});

test("CRLF input survives", () => {
  assert.equal(tokenize("a\r\n{{name}}", CTX), "a\r\nGodwin");
});

test("non-string input coerces to empty", () => {
  assert.equal(tokenize(null, CTX), "");
  assert.equal(tokenize(undefined, CTX), "");
});

test("iso date uses the local calendar date, not UTC", () => {
  // 23:30 local is already "tomorrow" in UTC for east-of-UTC zones —
  // the ISO date must follow the local components.
  const late = at(23, 30);
  assert.equal(
    tokenize("{{date:iso}}", { now: late, name: "" }),
    "2026-10-19");
});

test("nextBoundary measures to 12:00, 17:00 and midnight", () => {
  assert.equal(nextBoundary(at(11, 59, 0)), 60000);
  assert.equal(nextBoundary(at(16, 59, 0)), 60000);
  assert.equal(nextBoundary(at(12, 0, 0)), 5 * 3600 * 1000); // → 17:00
  assert.equal(nextBoundary(at(17, 0, 0)), 7 * 3600 * 1000); // → midnight
  assert.equal(nextBoundary(at(23, 59, 30)), 30000);
  assert.equal(nextBoundary(at(0, 0, 0)), 12 * 3600 * 1000); // → 12:00
});

test("tokenValue rejects unknown keys with null", () => {
  assert.equal(tokenValue("nope", at(9, 30), "X"), null);
  assert.equal(periodOf(at(11, 59)), "morning");
});
