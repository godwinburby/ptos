"use strict";

const test = require("node:test");
const assert = require("node:assert");
const fs = require("node:fs");
const path = require("node:path");
const { JSDOM } = require("jsdom");

const ROOT = path.join(__dirname, "..", "..");
const script = fs.readFileSync(
  path.join(ROOT, "web_static", "js", "home_widgets.js"), "utf8");

function setup() {
  const dom = new JSDOM("<!doctype html><body></body>", {
    url: "http://localhost:5000/",
    runScripts: "outside-only"
  });
  const win = dom.window;
  const registrations = {};
  const calls = [];
  win.PtosWidgets = {
    register(kind, def) { registrations[kind] = def; },
    mountBatch() { return []; },
    mount() { return { refresh() {}, destroy() {} }; }
  };
  win.fetch = function (url, opts) {
    calls.push({ url, opts: opts || {}, body: JSON.parse((opts || {}).body || "{}") });
    return Promise.resolve({
      json: () => Promise.resolve({ ok: true, count: 1 })
    });
  };
  win.confirm = () => true;
  win.eval(script);
  win.document.dispatchEvent(new win.Event("DOMContentLoaded"));
  return { dom, win, registrations, calls };
}

function mountQuickAdd(ctx) {
  const env = setup();
  const def = env.registrations.quick_add;
  assert.ok(def && def.mount, "quick_add mount must be registered");
  const el = env.win.document.createElement("div");
  env.win.document.body.appendChild(el);
  const handle = def.mount(el, {
    kind: "quick_add",
    frequent: ["coffee"],
    remaining: ["tea"],
    instant: ["coffee"]
  }, ctx || { host: "home", toast() {}, refresh() {} });
  return { el, handle, calls: env.calls, env };
}

function tick() {
  return new Promise((resolve) => setTimeout(resolve, 0));
}

test("every home preset chip renders its own instant and delete buttons", () => {
  const { el } = mountQuickAdd();
  const wraps = el.querySelectorAll(".preset-chip-wrap");
  assert.strictEqual(wraps.length, 2, "both groups must render as chips");
  wraps.forEach((wrap) => {
    assert.ok(wrap.querySelector(".preset-instant-toggle"),
      "each chip owns the instant toggle");
    assert.ok(wrap.querySelector(".preset-del"),
      "each chip owns the delete button");
  });
});

test("there is no dead Manage presets control to throw on", () => {
  const { el } = mountQuickAdd();
  assert.strictEqual(el.querySelectorAll(".preset-manage-toggle").length, 0);
  assert.ok(!/Manage presets/.test(el.innerHTML));
  assert.ok(!/openManagePresets/.test(el.innerHTML));
});

test("clicking the instant toggle posts to /api/preset_instant", async () => {
  const { el, calls } = mountQuickAdd();
  el.querySelectorAll(".preset-instant-toggle")[0].click();
  await tick();
  const call = calls.find((c) => c.url === "/api/preset_instant");
  assert.ok(call, "instant toggle must POST /api/preset_instant");
  assert.deepStrictEqual(call.body, { name: "coffee", instant: false });
});

test("clicking delete posts to /api/preset_delete", async () => {
  const { el, calls } = mountQuickAdd();
  const del = Array.from(el.querySelectorAll(".preset-del"))
    .find((b) => b.getAttribute("data-preset") === "tea");
  assert.ok(del, "remaining chip must carry a delete button");
  del.click();
  await tick();
  const call = calls.find((c) => c.url === "/api/preset_delete");
  assert.ok(call, "delete must POST /api/preset_delete");
  assert.deepStrictEqual(call.body, { name: "tea" });
});
