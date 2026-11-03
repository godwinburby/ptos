"use strict";

const test = require("node:test");
const assert = require("node:assert");
const fs = require("node:fs");
const path = require("node:path");
const { JSDOM } = require("jsdom");

const ROOT = path.join(__dirname, "..", "..");

function load(win, name) {
  const source = fs.readFileSync(path.join(ROOT, "web_static", "js", name), "utf8");
  win.eval(source);
}

test("todo toolbar changes filters and group mode through the controller", () => {
  const dom = new JSDOM("<!doctype html><body><div id='toolbar'></div></body>", {
    url: "http://ptos.test/todo", runScripts: "outside-only"
  });
  const win = dom.window;
  load(win, "todo_controller.js");
  load(win, "todo_toolbar.js");
  const changes = [];
  win.PtosTodoToolbar.mount(win.document.getElementById("toolbar"), {
    projects: ["+home", "+work"], contexts: ["@shop"], priorities: ["A"],
    filters: { project: "+home", context: "", priority: "", due: "", search: "", linked_to: "" },
    groupby: "timeline", sort: "default", hide_routines: false
  }, value => changes.push(value));

  const activeRow = win.document.querySelector("[data-todo-active]");
  const groupBar = win.document.querySelector(".todo-shell-groupby");
  assert.ok(activeRow.compareDocumentPosition(groupBar) & win.Node.DOCUMENT_POSITION_FOLLOWING);
  assert.match(activeRow.textContent, /Project: \+home/);
  assert.ok(activeRow.querySelector("[data-todo-clear]"));

  const groupTab = win.document.querySelector('[data-todo-groupby="project"]');
  groupTab.click();
  assert.deepEqual(changes[0], { groupby: "project" });
  assert.equal(groupTab.getAttribute("aria-selected"), "true");
  assert.equal(groupTab.getAttribute("tabindex"), "0");
  const timelineTab = win.document.querySelector('[data-todo-groupby="timeline"]');
  assert.equal(timelineTab.getAttribute("aria-selected"), "false");
  assert.equal(timelineTab.getAttribute("tabindex"), "-1");

  const search = win.document.querySelector("[data-todo-search]");
  search.value = "call*";
  win.document.querySelector("[data-todo-search-form]").dispatchEvent(
    new win.Event("submit", { bubbles: true, cancelable: true }));
  assert.deepEqual(changes[1], { search: "call*" });

  win.document.querySelector('[data-todo-remove="project"]').click();
  assert.deepEqual(changes[2], { project: "" });
  dom.window.close();
});

test("group tablist arrows move focus without changing the view", () => {
  const dom = new JSDOM("<!doctype html><body><div id='toolbar'></div></body>", {
    url: "http://ptos.test/todo", runScripts: "outside-only"
  });
  const win = dom.window;
  load(win, "todo_controller.js");
  load(win, "todo_toolbar.js");
  const changes = [];
  win.PtosTodoToolbar.mount(win.document.getElementById("toolbar"), {
    filters: { project: "", context: "", priority: "", due: "", search: "", linked_to: "" },
    groupby: "timeline", sort: "default"
  }, value => changes.push(value));

  const timeline = win.document.querySelector('[data-todo-groupby="timeline"]');
  const priority = win.document.querySelector('[data-todo-groupby="priority"]');
  const context = win.document.querySelector('[data-todo-groupby="context"]');
  timeline.focus();
  timeline.dispatchEvent(new win.KeyboardEvent("keydown", { key: "ArrowRight", bubbles: true }));
  assert.equal(win.document.activeElement, priority);
  priority.dispatchEvent(new win.KeyboardEvent("keydown", { key: "End", bubbles: true }));
  assert.equal(win.document.activeElement, context);
  context.dispatchEvent(new win.KeyboardEvent("keydown", { key: "Home", bubbles: true }));
  assert.equal(win.document.activeElement, timeline);
  timeline.dispatchEvent(new win.KeyboardEvent("keydown", { key: "ArrowLeft", bubbles: true }));
  assert.equal(win.document.activeElement, context);
  assert.deepEqual(changes, []);
  dom.window.close();
});

test("quick pick opens on focus, closes on blur, and toggles priority chips", async () => {
  const dom = new JSDOM("<!doctype html><body><div id='toolbar'></div></body>", {
    url: "http://ptos.test/todo", runScripts: "outside-only"
  });
  const win = dom.window;
  load(win, "todo_toolbar.js");
  win.PtosTodoToolbar.mount(win.document.getElementById("toolbar"), {
    filters: { project: "", context: "", priority: "", due: "", search: "", linked_to: "" },
    groupby: "timeline", sort: "default"
  }, () => {});
  const input = win.document.querySelector("[data-todo-add-input]");
  const chips = win.document.querySelector("[data-qp-chips]");
  const toggle = win.document.querySelector("[data-qp-toggle]");

  input.focus();
  assert.equal(chips.style.display, "grid");
  assert.equal(toggle.getAttribute("aria-expanded"), "true");

  const priA = win.document.querySelector('[data-qp-group="pri"][data-token="(A) "]');
  const priB = win.document.querySelector('[data-qp-group="pri"][data-token="(B) "]');
  priA.click();
  assert.ok(priA.classList.contains("selected"));
  assert.ok(input.value.startsWith("(A) "));
  priB.click();
  assert.ok(!priA.classList.contains("selected"));
  assert.ok(priB.classList.contains("selected"));
  assert.ok(input.value.startsWith("(B) "));
  priB.click();
  assert.ok(!priB.classList.contains("selected"));
  assert.equal(input.value, "");

  input.blur();
  await new Promise(resolve => setTimeout(resolve, 250));
  assert.equal(chips.style.display, "none");
  assert.equal(toggle.getAttribute("aria-expanded"), "false");

  toggle.click();
  assert.equal(chips.style.display, "grid");
  assert.equal(toggle.getAttribute("aria-expanded"), "true");
  dom.window.close();
});

test("todo quick add posts the task and requests a widget refresh", async () => {
  const dom = new JSDOM("<!doctype html><body><div id='toolbar'></div></body>", {
    url: "http://ptos.test/todo", runScripts: "outside-only"
  });
  const win = dom.window;
  load(win, "todo_toolbar.js");
  let request;
  win.fetch = (url, options) => {
    request = { url, options };
    return Promise.resolve({ json: () => Promise.resolve({ ok: true }) });
  };
  const changes = [];
  win.PtosTodoToolbar.mount(win.document.getElementById("toolbar"), {}, value => changes.push(value));
  win.document.querySelector('[data-qp-group="pri"][data-token="(A) "]').click();
  win.document.querySelector("[data-todo-add-input]").value = "Call the dentist";
  win.document.querySelector("[data-todo-add-form]").dispatchEvent(
    new win.Event("submit", { bubbles: true, cancelable: true }));
  await new Promise(resolve => setTimeout(resolve, 0));
  assert.equal(request.url, "/todo/add");
  assert.equal(JSON.parse(request.options.body).text, "Call the dentist");
  assert.deepEqual(changes, [{}]);
  assert.equal(win.document.querySelector("[data-todo-add-input]").value, "");
  assert.equal(win.document.querySelectorAll("[data-qp-chips] .add-chip.selected").length, 0);
  dom.window.close();
});

test("todo form add button opens the shared task modal", () => {
  const dom = new JSDOM("<!doctype html><body><div id='toolbar'></div></body>", {
    url: "http://ptos.test/todo", runScripts: "outside-only"
  });
  const win = dom.window;
  let opened = 0;
  win.openAdd = () => { opened += 1; };
  load(win, "todo_toolbar.js");
  win.PtosTodoToolbar.mount(win.document.getElementById("toolbar"), {}, () => {});
  win.document.querySelector("[data-todo-form-add]").click();
  assert.equal(opened, 1);
  dom.window.close();
});

test("saved Todo views load into filters and support save and delete", async () => {
  const dom = new JSDOM("<!doctype html><body><div id='toolbar'></div></body>", {
    url: "http://ptos.test/todo", runScripts: "outside-only"
  });
  const win = dom.window;
  load(win, "todo_toolbar.js");
  win.prompt = () => "work_week";
  win.confirm = () => true;
  const requests = [];
  win.fetch = (url, options) => {
    requests.push({ url, options });
    return Promise.resolve({ json: () => Promise.resolve({ ok: true }) });
  };
  const changes = [];
  const state = {
    views: { work_week: { project: "+work", due: "week", groupby: "project" } },
    filters: { project: "", context: "", priority: "", due: "", search: "", linked_to: "" },
    groupby: "timeline", sort: "default", hide_routines: false, include_done: true
  };
  win.PtosTodoToolbar.mount(win.document.getElementById("toolbar"), state,
    value => changes.push(value));
  const picker = win.document.querySelector("[data-todo-saved-view]");
  picker.value = "work_week";
  picker.dispatchEvent(new win.Event("change", { bubbles: true }));
  assert.equal(changes[0].project, "+work");
  assert.equal(changes[0].groupby, "project");
  assert.equal(win.document.querySelector('[data-todo-groupby="project"]').getAttribute("aria-selected"), "true");
  assert.equal(win.document.querySelector("[data-todo-saved-name]").textContent, " · work week");

  win.document.querySelector("[data-todo-update-view]").click();
  await new Promise(resolve => setTimeout(resolve, 0));
  assert.equal(requests[0].url, "/api/query-builder/todo");
  assert.equal(JSON.parse(requests[0].options.body).name, "work_week");

  win.document.querySelector("[data-todo-delete-view]").click();
  await new Promise(resolve => setTimeout(resolve, 0));
  assert.equal(JSON.parse(requests[1].options.body).action, "delete");
  assert.equal(picker.value, "");
  dom.window.close();
});

test("todo controller preserves TOML booleans while updating filter strings", () => {
  const dom = new JSDOM("<!doctype html><body></body>", { runScripts: "outside-only" });
  load(dom.window, "todo_controller.js");
  const body = dom.window.PtosTodoController.updateBody(
    'view = "todo"\nhide_routines = true\nsearch = "old"',
    { hide_routines: false, search: "new" }
  );
  assert.ok(body.includes("hide_routines = false"));
  assert.ok(body.includes('search = "new"'));
  assert.ok(!body.includes('hide_routines = "false"'));
  dom.window.close();
});

test("todo controller emits empty filter overrides for saved views", () => {
  const dom = new JSDOM("<!doctype html><body></body>", { runScripts: "outside-only" });
  load(dom.window, "todo_controller.js");
  const body = dom.window.PtosTodoController.updateBody(
    'view = "todo"\nname = "work"\nproject = "+work"',
    { project: "", name: "work" }
  );
  assert.ok(body.includes('project = ""'));
  assert.ok(body.includes('name = "work"'));
  dom.window.close();
});

test("todo collapsed section state survives a widget rerender", () => {
  const dom = new JSDOM("<!doctype html><body><div id='a'><details data-todo-section='today' open></details></div><div id='b'><details data-todo-section='today' open></details></div></body>", {
    url: "http://ptos.test/todo", runScripts: "outside-only"
  });
  const win = dom.window;
  load(win, "todo_list.js");
  win.PtosTodoList.mount(win.document.getElementById("a"));
  const first = win.document.querySelector("#a details");
  first.open = false;
  first.dispatchEvent(new win.Event("toggle"));
  win.PtosTodoList.mount(win.document.getElementById("b"));
  assert.equal(win.document.querySelector("#b details").open, false);
  dom.window.close();
});
test("todo toolbar without hide-routines checkbox does not throw on group change", () => {
  const dom = new JSDOM("<!doctype html><body><div id='toolbar'></div></body>", {
    url: "http://ptos.test/todo", runScripts: "outside-only"
  });
  const win = dom.window;
  const fs = require("node:fs");
  const path = require("node:path");
  const ROOT = path.join(__dirname, "..", "..");
  function load(name) { win.eval(fs.readFileSync(path.join(ROOT, "web_static", "js", name), "utf8")); }
  load("todo_controller.js");
  load("todo_toolbar.js");
  const changes = [];
  win.PtosTodoToolbar.mount(win.document.getElementById("toolbar"), {
    projects: ["+home", "+work"], contexts: ["@shop"], priorities: ["A"],
    filters: { project: "+home", context: "", priority: "", due: "", search: "", linked_to: "" },
    groupby: "timeline", sort: "default", hide_routines: false
  }, value => changes.push(value));
  const cb = win.document.querySelector("[data-todo-hide-routines]");
  if (cb) cb.remove();
  const groupTab = win.document.querySelector('[data-todo-groupby="project"]');
  let threw = false;
  try { groupTab.click(); } catch (e) { threw = true; }
  assert.equal(threw, false);
  assert.ok(changes.length >= 1);
  dom.window.close();
});

test("todo toolbar without hide-routines checkbox: clear filters no throw", () => {
  const dom = new JSDOM("<!doctype html><body><div id='toolbar'></div></body>", {
    url: "http://ptos.test/todo", runScripts: "outside-only"
  });
  const win = dom.window;
  const fs = require("node:fs");
  const path = require("node:path");
  const ROOT = path.join(__dirname, "..", "..");
  function load(name) { win.eval(fs.readFileSync(path.join(ROOT, "web_static", "js", name), "utf8")); }
  load("todo_controller.js");
  load("todo_toolbar.js");
  win.PtosTodoToolbar.mount(win.document.getElementById("toolbar"), {
    projects: [], contexts: [], priorities: [],
    filters: { project: "+home", context: "", priority: "", due: "", search: "", linked_to: "" },
    groupby: "timeline", sort: "default", hide_routines: false
  }, () => {});
  const cb = win.document.querySelector("[data-todo-hide-routines]");
  if (cb) cb.remove();
  const clearBtn = win.document.querySelector("[data-todo-clear]");
  if (clearBtn) {
    let threw = false;
    try { clearBtn.click(); } catch (e) { threw = true; }
    assert.equal(threw, false);
  }
  dom.window.close();
});
