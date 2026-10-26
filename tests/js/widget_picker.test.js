"use strict";
const test = require("node:test");
const assert = require("node:assert");
const path = require("node:path");
const { JSDOM } = require("jsdom");

const ROOT = path.join(__dirname, "..", "..");

function setup(savedTodos = ["default"]) {
  const dom = new JSDOM("<!doctype html><body></body>", { url: "http://ptos.test" });
  globalThis.window = dom.window;
  globalThis.document = dom.window.document;
  globalThis.localStorage = dom.window.localStorage;
  dom.window.matchMedia = () => ({ matches: true });
  globalThis.PtosToml = { parse: body => {
    const out = {};
    String(body).split(/\r?\n/).forEach(line => {
      const m = /^([\w-]+)\s*=\s*"(.*)"$/.exec(line);
      if (m) out[m[1]] = m[2];
    });
    return out;
  }, serialize: obj => Object.keys(obj).map(k => k + ' = "' + obj[k] + '"').join("\n") };
  dom.window.PtosTextBlocks = [{gallery:true,label:"Heading",description:"Add a heading",seed:"# Title",caret:2}];
  const catalog = {
    ok: true,
    categories: [
      {id:"tasks",label:"Tasks",count:3},{id:"tables",label:"Tables",count:2},
      {id:"numbers",label:"Numbers",count:3},{id:"goals",label:"Goals",count:2},
      {id:"capture",label:"Capture",count:3},{id:"projects",label:"Projects",count:2}
    ],
    kinds: [
      {kind:"todo",label:"Task list",category:"tasks",named:true,quick_add:false,needs_name:false,icon:"list",fields:[]},
      {kind:"capture",label:"Capture",category:"capture",named:false,quick_add:true,needs_name:false,icon:"inbox",fields:[]},
      {kind:"dashboard",label:"Dashboard",category:"numbers",named:true,quick_add:false,needs_name:true,icon:"layout",fields:[]}
    ],
    starters: Array.from({length:9}, (_, i) => ({id:"s"+i,label:"Start "+i,kind:"capture",body:'view = "capture"'}))
  };
  globalThis.fetch = async url => ({ json: async () => String(url).includes("catalog")
    ? catalog : {ok:true,values:["default"],items:[{name:"default",description:"Six metrics · this month",tag:"chart"}]} });
  const pickerPath = path.join(ROOT, "web_static", "js", "widget_picker.js");
  delete require.cache[require.resolve(pickerPath)];
  require(pickerPath);
  return { dom, catalog };
}

test("gallery home limits starter chips and renders category counts", async () => {
  const {dom} = setup();
  window.PtosWidgetPicker.open({});
  await new Promise(resolve => setTimeout(resolve, 0));
  assert.equal(document.querySelectorAll(".wp-starter-chip").length, 6);
  assert.equal(document.querySelectorAll(".wp-category").length, 7);
  assert.ok(document.querySelector(".wp-see-all").textContent.includes("9"));
  assert.ok(document.querySelector(".wp-category").getAttribute("aria-label").includes("items"));
  window.PtosWidgetPicker.close();
  dom.window.close();
});

test("quick-add picks bypass configuration and saved rows show descriptions", async () => {
  const {dom} = setup();
  let picked = "";
  window.PtosWidgetPicker.open({onPick: body => { picked = body; }});
  await new Promise(resolve => setTimeout(resolve, 0));
  document.querySelector('[data-cat="capture"]').click();
  document.querySelector('[data-kind="capture"]').click();
  assert.equal(picked, 'view = "capture"');
  assert.equal(document.querySelector(".wp-overlay"), null);

  window.PtosWidgetPicker.open({});
  await new Promise(resolve => setTimeout(resolve, 0));
  document.querySelector('[data-cat="numbers"]').click();
  document.querySelector('[data-kind="dashboard"]').click();
  await new Promise(resolve => setTimeout(resolve, 0));
  assert.ok(document.querySelector(".wp-item-desc").textContent.includes("Six metrics"));
  assert.equal(document.querySelector(".wp-item-tag").textContent, "chart");
  let formOptions = null;
  window.PtosWidgetForm = { mount: (el, opts) => { formOptions = opts; el.textContent = "form"; } };
  document.querySelector(".wp-item").click();
  assert.equal(document.querySelector(".wp-title").textContent, "Configure widget");
  assert.equal(formOptions.saveLabel, "Add widget");
  assert.equal(formOptions.cancelLabel, "Back");
  let configured = "";
  window.PtosWidgetPicker.close();
  window.PtosWidgetPicker.open({onPick: body => { configured = body; }});
  await new Promise(resolve => setTimeout(resolve, 0));
  document.querySelector('[data-cat="numbers"]').click();
  document.querySelector('[data-kind="dashboard"]').click();
  await new Promise(resolve => setTimeout(resolve, 0));
  document.querySelector(".wp-item").click();
  formOptions.onSave('view = "dashboard"\nname = "default"');
  assert.ok(configured.includes('name = "default"'));
  window.PtosWidgetPicker.close();
  dom.window.close();
});

test("named kind with no saved views skips the default-only chooser", async () => {
  const {dom, catalog} = setup();
  globalThis.fetch = async url => ({json: async () => String(url).includes("catalog")
    ? catalog
    : {ok:true,values:[],items:[]}});
  let picked = "";
  let formOptions = null;
  window.PtosWidgetForm = {mount:(el, opts) => { formOptions = opts; }};
  window.PtosWidgetPicker.open({onPick: body => { picked = body; }});
  await new Promise(resolve => setTimeout(resolve, 0));
  document.querySelector('[data-cat="tasks"]').click();
  document.querySelector('[data-kind="todo"]').click();
  await new Promise(resolve => setTimeout(resolve, 0));
  assert.equal(document.querySelector(".wp-title").textContent, "Configure widget");
  formOptions.onSave('view = "todo"');
  assert.ok(picked.includes('view = "todo"'));
  assert.equal(document.querySelector(".wp-overlay"), null);
  dom.window.close();
});

test("named kind with saved views keeps the selection step", async () => {
  const {dom, catalog} = setup();
  globalThis.fetch = async url => ({json: async () => String(url).includes("catalog")
    ? catalog
    : {ok:true,values:["today", "week"],items:[{name:"today"},{name:"week"}]}});
  window.PtosWidgetPicker.open({});
  await new Promise(resolve => setTimeout(resolve, 0));
  document.querySelector('[data-cat="tasks"]').click();
  document.querySelector('[data-kind="todo"]').click();
  await new Promise(resolve => setTimeout(resolve, 0));
  assert.equal(document.querySelectorAll(".wp-item[data-name]").length, 3);
  window.PtosWidgetPicker.close();
  dom.window.close();
});
