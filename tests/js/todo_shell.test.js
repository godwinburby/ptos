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

  const groupby = win.document.querySelector('[data-todo-filter="groupby"]');
  groupby.value = "project";
  groupby.dispatchEvent(new win.Event("change", { bubbles: true }));
  assert.deepEqual(changes[0], { groupby: "project" });

  const search = win.document.querySelector("[data-todo-search]");
  search.value = "call*";
  win.document.querySelector("[data-todo-search-form]").dispatchEvent(
    new win.Event("submit", { bubbles: true, cancelable: true }));
  assert.deepEqual(changes[1], { search: "call*" });

  win.document.querySelector('[data-todo-remove="project"]').click();
  assert.deepEqual(changes[2], { project: "" });
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
  win.document.querySelector("[data-todo-add-input]").value = "Call the dentist";
  win.document.querySelector("[data-todo-add-form]").dispatchEvent(
    new win.Event("submit", { bubbles: true, cancelable: true }));
  await new Promise(resolve => setTimeout(resolve, 0));
  assert.equal(request.url, "/todo/add");
  assert.equal(JSON.parse(request.options.body).text, "Call the dentist");
  assert.deepEqual(changes, [{}]);
  assert.equal(win.document.querySelector("[data-todo-add-input]").value, "");
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
