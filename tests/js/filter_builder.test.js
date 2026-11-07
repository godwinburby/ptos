"use strict";
const test = require("node:test");
const assert = require("node:assert");
const fs = require("node:fs");
const path = require("node:path");
const { JSDOM } = require("jsdom");

const SRC = fs.readFileSync(path.join(__dirname, "..", "..", "web_static", "js", "filter_builder.js"), "utf8");

function load() {
  const dom = new JSDOM("<!doctype html><body><div id=\"fb\"></div></body>", {
    runScripts: "outside-only", url: "http://ptos.test/browse" });
  const win = dom.window;
  // The component may call fetch for field values; keep it inert.
  win.fetch = () => Promise.resolve({ ok: true, json: () => Promise.resolve({}) });
  win.eval(SRC); // a syntax error in the file throws here
  return win;
}

test("filter_builder.js parses and defines FilterBuilder", () => {
  const win = load();
  assert.equal(typeof win.FilterBuilder, "function");
});

test("FilterBuilder renders type chips and round-trips an expression", () => {
  const win = load();
  const fb = new win.FilterBuilder({
    containerId: "fb", types: ["expense", "income", "investment"], onRun: function () {} });
  fb.init();
  const html = win.document.getElementById("fb").innerHTML;
  assert.ok(html.includes("expense") && html.includes("income"), "type chips rendered");
  fb.setExpr("type=expense");
  assert.equal(fb.getExpr(), "type=expense");
  fb.clear();
  assert.equal(fb.getExpr(), "");
});
