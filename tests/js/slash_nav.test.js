"use strict";
const test = require("node:test");
const assert = require("node:assert");
const path = require("node:path");
const { JSDOM } = require("jsdom");
const ROOT = path.join(__dirname, "..", "..");

test("slash starts with categories and searches through the gallery", async () => {
  const dom = new JSDOM("<!doctype html><body><textarea id='note'></textarea></body>",
    {url:"http://ptos.test"});
  globalThis.window = dom.window;
  globalThis.document = dom.window.document;
  globalThis.Event = dom.window.Event;
  globalThis.getComputedStyle = dom.window.getComputedStyle.bind(dom.window);
  globalThis.localStorage = dom.window.localStorage;
  dom.window.matchMedia = () => ({matches:true});
  window.PtosTextBlocks = [{gallery:true,label:"Heading",description:"A heading",seed:"## Title",caret:3}];
  window.PtosToml = {parse:body=>{
    const out={}; String(body).split(/\r?\n/).forEach(line=>{
      const m=/^([\w-]+)\s*=\s*"(.*)"$/.exec(line); if(m) out[m[1]]=m[2];
    }); return out;
  },serialize:spec=>Object.keys(spec).map(k=>k+' = "'+spec[k]+'"').join("\n")};
  globalThis.PtosToml = window.PtosToml;
  const catalog = {ok:true,categories:[
    {id:"tasks",label:"Tasks",count:3},{id:"tables",label:"Tables",count:2},
    {id:"numbers",label:"Numbers",count:3},{id:"goals",label:"Goals",count:2},
    {id:"capture",label:"Capture",count:3},{id:"projects",label:"Projects",count:2}
  ],kinds:[
    {kind:"query",label:"Saved query",category:"tables",named:true,needs_name:true,description:"Tables and charts"},
    {kind:"todo",label:"Task list",category:"tasks",named:true,needs_name:false,description:"Live todo list with filters"},
    {kind:"capture",label:"Quick capture",category:"capture",named:false,needs_name:false,quick_add:true,description:"Capture a line"}
  ],starters:[]};
  globalThis.fetch = async url => ({json:async()=>String(url).includes("/options")
    ? {ok:true,values:["spend"],items:[{name:"spend",description:"Spending by category · this month",tag:"chart"}]}
    : catalog});
  for (const file of ["widget_picker.js","slash_embed.js"]) {
    const p = path.join(ROOT,"web_static","js",file);
    delete require.cache[require.resolve(p)];
    require(p);
  }
  const el = document.getElementById("note");
  el.value = "/";
  el.setSelectionRange(1,1);
  window.attachSlashEmbed(el);
  el.dispatchEvent(new window.Event("input",{bubbles:true}));
  await new Promise(resolve=>setTimeout(resolve,0));
  const list = document.getElementById("note-slash-ac");
  assert.equal(list.querySelectorAll(".slash-ac-item").length,7);
  assert.ok(list.textContent.includes("Tasks"));
  Object.defineProperty(list,"clientHeight",{configurable:true,value:44});
  list.querySelectorAll(".slash-ac-item").forEach((item,index)=>{
    Object.defineProperty(item,"offsetTop",{configurable:true,value:index*48});
    Object.defineProperty(item,"offsetHeight",{configurable:true,value:44});
  });
  el.dispatchEvent(new window.KeyboardEvent("keydown",{key:"ArrowDown",bubbles:true}));
  el.dispatchEvent(new window.KeyboardEvent("keydown",{key:"ArrowDown",bubbles:true}));
  assert.ok(list.scrollTop > 0);
  list.querySelector(".slash-ac-item").dispatchEvent(new window.MouseEvent("mousedown",{bubbles:true}));
  assert.ok(list.textContent.includes("Heading"));
  list.querySelector(".slash-ac-item").dispatchEvent(new window.MouseEvent("mousedown",{bubbles:true}));
  assert.ok(el.value.includes("## Title"));

  el.value = "/";
  el.setSelectionRange(1,1);
  el.dispatchEvent(new window.Event("input",{bubbles:true}));
  await new Promise(resolve=>setTimeout(resolve,0));
  list.querySelectorAll(".slash-ac-item")[2].dispatchEvent(new window.MouseEvent("mousedown",{bubbles:true}));
  assert.ok(list.textContent.includes("Saved query"));
  list.querySelector(".slash-ac-item").dispatchEvent(new window.MouseEvent("mousedown",{bubbles:true}));
  await new Promise(resolve=>setTimeout(resolve,0));
  assert.ok(list.textContent.includes("Spending by category"));
  let formOptions = null;
  window.PtosWidgetForm = {mount:(container,opts)=>{formOptions=opts;}};
  list.querySelector(".slash-ac-item").dispatchEvent(new window.MouseEvent("mousedown",{bubbles:true}));
  await new Promise(resolve=>setTimeout(resolve,0));
  assert.ok(formOptions && formOptions.body.includes('name = "spend"'),
    document.querySelector(".wp-title") && document.querySelector(".wp-title").textContent);
  window.PtosWidgetPicker.close();

  el.value = "/dashboard";
  el.setSelectionRange(el.value.length,el.value.length);
  el.dispatchEvent(new window.Event("input",{bubbles:true}));
  assert.ok(list.textContent.includes("Search all for “dashboard”"));
  list.querySelector(".slash-ac-item").dispatchEvent(new window.MouseEvent("mousedown",{bubbles:true}));
  assert.equal(document.querySelector(".wp-search").value,"dashboard");

  el.value = "/quick";
  el.setSelectionRange(el.value.length,el.value.length);
  el.dispatchEvent(new window.Event("input",{bubbles:true}));
  await new Promise(resolve=>setTimeout(resolve,0));
  assert.ok(list.textContent.includes("Quick capture"), list.innerHTML);
  assert.ok(!list.textContent.includes("Tasks"));

  el.value = "/todo";
  el.setSelectionRange(el.value.length,el.value.length);
  el.dispatchEvent(new window.Event("input",{bubbles:true}));
  await new Promise(resolve=>setTimeout(resolve,0));
  const taskList = Array.from(list.querySelectorAll(".slash-nav-row"))
    .find(item => item.textContent.includes("Task list"));
  assert.ok(taskList, list.innerHTML);
  taskList.dispatchEvent(new window.MouseEvent("mousedown",{bubbles:true}));
  await new Promise(resolve=>setTimeout(resolve,0));
  assert.ok(formOptions && formOptions.body.includes('view = "todo"'));
  dom.window.close();
});
