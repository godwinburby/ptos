"use strict";

const test = require("node:test");
const assert = require("node:assert");
const fs = require("node:fs");
const path = require("node:path");
const { JSDOM } = require("jsdom");

const ROOT = path.join(__dirname, "..", "..");
const widgetsScript = fs.readFileSync(path.join(ROOT, "web_static", "js", "widgets.js"), "utf8");

function setup() {
  const dom = new JSDOM("<!doctype html><body></body>", {
    url: "http://ptos.test",
    runScripts: "outside-only",
  });
  const win = dom.window;
  win.eval(widgetsScript);
  return win;
}

test("renderHabit emits separate streak, days, and range elements", () => {
  const win = setup();
  const html = win.renderHabit({
    habit_name: "Maid attendance",
    streak: 3,
    days_done: 3,
    total_days: 10,
    range_label: "Nov 1 \u2013 Nov 10",
    months: [],
    toggleable: false,
  });
  const root = win.document.createElement("div");
  root.innerHTML = html;
  const stat = root.querySelector(".emb-stat");
  assert.ok(stat, "habit summary has .emb-stat");
  // Three direct span children
  const spans = Array.from(stat.children).filter((c) => c.tagName === "SPAN");
  assert.strictEqual(spans.length, 3, ".emb-stat should have three span children");
  const texts = spans.map((s) => s.textContent.trim());
  // streak child has data-stat="streak"
  assert.ok(spans[0].querySelector('[data-stat="streak"]'), "first span has streak");
  // days child has data-stat="days" on the span itself
  assert.ok(spans[1].hasAttribute("data-stat") && spans[1].getAttribute("data-stat") === "days", "second span has data-stat=days");
  // third span has range label
  assert.ok(texts[2].includes("Nov 1"), "third span contains range label");
});

test("renderDue row has separate name, due-gap, due-open children", () => {
  const win = setup();
  const html = win.renderDue(
    {
      rows: [
        {
          name: "Call supplier",
          days: 2,
          heat: "hot",
          filepath: "records/2026.log",
          lineno: 3,
          line: '2026-11-05 type=expense amount=100 note="call"',
          note: "urgent",
        },
      ],
      title: "Due",
    },
    { bare: true }
  );
  const root = win.document.createElement("div");
  root.innerHTML = html;
  const row = root.querySelector(".emb-due-row");
  assert.ok(row, "due row has .emb-due-row");
  const name = row.querySelector(".emb-name");
  const gap = row.querySelector(".emb-due-gap");
  const open = row.querySelector(".emb-due-open");
  assert.ok(name, "row has .emb-name");
  assert.ok(gap, "row has .emb-due-gap");
  assert.ok(open, "row has .emb-due-open");
  assert.strictEqual(name.textContent.trim(), "Call supplier");
  assert.strictEqual(gap.textContent.trim(), "2d");
  assert.ok(open.textContent.trim().includes("Open"));
});

test("renderTodoRow shows an area chip only when the task has an area", () => {
  const win = setup();
  const withArea = win.renderTodoRow(
    { description: "Review roster", area: "work", raw_line: "x", projects: [], contexts: [], links: [] },
    { area: "work" }
  );
  const root = win.document.createElement("div");
  root.innerHTML = withArea;
  const chip = root.querySelector(".todo-area");
  assert.ok(chip, "row has an area chip");
  assert.strictEqual(chip.getAttribute("data-todo-filter-badge"), "area");
  assert.strictEqual(chip.getAttribute("data-value"), "work");
  assert.strictEqual(chip.getAttribute("style"), null, "area chip uses a class, not an inline style");
  assert.ok(chip.classList.contains("active"), "area chip is marked active for the current filter");
  assert.strictEqual(root.querySelector(".todo-row").getAttribute("data-area"), "work");

  const other = win.renderTodoRow(
    { description: "Review roster", area: "home", raw_line: "x", projects: [], contexts: [], links: [] },
    { area: "work" }
  );
  const otherRoot = win.document.createElement("div");
  otherRoot.innerHTML = other;
  assert.ok(!otherRoot.querySelector(".todo-area").classList.contains("active"),
    "area chip of another area is not active");
});

test("renderTodoRow shows no area chip when the task has no area", () => {
  const win = setup();
  const html = win.renderTodoRow(
    { description: "Call supplier", raw_line: "x", projects: [], contexts: [], links: [] },
    {}
  );
  const root = win.document.createElement("div");
  root.innerHTML = html;
  assert.strictEqual(root.querySelector(".todo-area"), null);
  assert.strictEqual(root.querySelector(".todo-row").getAttribute("data-area"), "");
});