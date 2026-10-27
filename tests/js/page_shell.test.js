"use strict";

const test = require("node:test");
const assert = require("node:assert");
const fs = require("node:fs");
const path = require("node:path");
const { JSDOM } = require("jsdom");

const ROOT = path.join(__dirname, "..", "..");
const shellScript = fs.readFileSync(path.join(ROOT, "web_static", "js", "page_shell.js"), "utf8");
const widgetsScript = fs.readFileSync(path.join(ROOT, "web_static", "js", "widgets.js"), "utf8");
const hostScript = fs.readFileSync(path.join(ROOT, "web_static", "js", "widget_host.js"), "utf8");

function setup(url) {
  const dom = new JSDOM(`<!doctype html><body>
    <div data-page-controls>
      <select data-page-time><option value=""></option><option value="month">Month</option></select>
      <div data-page-custom-time><label data-page-custom="month"><input type="month" data-page-month-value></label>
        <button data-page-apply type="button">Apply</button></div>
      <div class="page-month-nav"><button data-page-month-shift="1">Next</button></div>
    </div>
    <div id="page-widget"></div>
    <script id="page-spec" type="application/json"></script>
    <script id="page-data" type="application/json">{}</script>
  </body>`, { url, runScripts: "outside-only" });
  const win = dom.window;
  win.document.getElementById("page-spec").textContent = JSON.stringify({
    body: 'view = "records"', kind: "records"
  });
  win.PTOS_PAGE = { month: { year: 2025, month: 2 }, monthParam: "custom_time" };
  const bodies = [];
  win.PtosWidgets = { mount: (_el, body) => ({
    setSpec(next) { bodies.push(next); }
  }) };
  win.eval(shellScript);
  win.document.dispatchEvent(new win.Event("DOMContentLoaded", { bubbles: true }));
  return { dom, win, bodies };
}

test("page shell applies custom time to the widget and URL", () => {
  const { dom, win, bodies } = setup("http://ptos.test/thresholds?keep=1");
  const select = win.document.querySelector("[data-page-time]");
  select.value = "month";
  select.dispatchEvent(new win.Event("change", { bubbles: true }));
  const month = win.document.querySelector("[data-page-month-value]");
  month.value = "2025-03";
  win.document.querySelector("[data-page-apply]").click();
  assert.ok(bodies.at(-1).includes('time = "2025-03"'));
  assert.equal(win.location.search, "?keep=1&time=month&custom_time=2025-03");
  dom.window.close();
});

test("page shell month arrows update the widget month and URL", () => {
  const { dom, win, bodies } = setup("http://ptos.test/habits");
  win.document.querySelector("[data-page-month-shift]").click();
  assert.ok(bodies.at(-1).includes('time = "2025-03"'));
  assert.equal(win.location.search, "?time=month&custom_time=2025-03");
  dom.window.close();
});

test("habit widget days are clickable and update after a successful toggle", async () => {
  const dom = new JSDOM("<!doctype html><body><div id='widget'></div></body>", {
    url: "http://ptos.test/habits", runScripts: "outside-only"
  });
  const win = dom.window;
  const now = new Date();
  const today = now.getFullYear() + "-" + String(now.getMonth() + 1).padStart(2, "0") +
    "-" + String(now.getDate()).padStart(2, "0");
  let request = null;
  win.fetch = async (url, options) => {
    request = { url, body: JSON.parse(options.body) };
    return { json: async () => ({ ok: true, present: true, streak: 1, days_done: 1 }) };
  };
  win.eval(widgetsScript);
  win.eval(hostScript);
  const data = {
    kind: "habit", habit_name: "meditation", toggleable: true,
    streak: 0, days_done: 0, total_days: 1,
    months: [{ name: "Current month", days: [{ date: today, present: false, is_today: true }] }]
  };
  win.PtosWidgets.mount(win.document.getElementById("widget"), 'view = "habit"\nname = "meditation"', {
    data, interactive: true, size: "full"
  });
  const cell = win.document.querySelector("td[data-date]");
  assert.ok(cell);
  assert.ok(cell.classList.contains("clickable"));
  cell.click();
  await new Promise(resolve => setTimeout(resolve, 0));
  assert.deepEqual(request, { url: "/api/habit/toggle", body: { habit_name: "meditation", date: today } });
  assert.equal(cell.getAttribute("data-present"), "1");
  assert.ok(cell.classList.contains("cnt"));
  assert.equal(win.document.querySelector('[data-stat="streak"]').textContent, "1");
  dom.window.close();
});

test("full project widget shows note titles without the markdown suffix", () => {
  const dom = new JSDOM("<!doctype html><body></body>", { runScripts: "outside-only" });
  const win = dom.window;
  win.eval(widgetsScript);
  const container = win.document.createElement("div");
  container.innerHTML = win.renderProject({
    name: "ptname", label: "PT Name", notes: [{ path: "job-hunt.md", display_name: "job-hunt" }]
  }, { full: true });
  const link = container.querySelector(".page-project-ref a");
  assert.equal(link.textContent, "📝 job-hunt");
  assert.equal(link.getAttribute("href"), "/notes/edit/job-hunt.md");
  dom.window.close();
});
