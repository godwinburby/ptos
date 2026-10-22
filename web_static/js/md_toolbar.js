(function (root) {
  "use strict";
  function wrapSelection(text, s, e, open, close) {
    text = String(text); open = String(open); close = String(close);
    if (s > 0 && e < text.length && text.slice(s - open.length, s) === open &&
        text.slice(e, e + close.length) === close) {
      return { text: text.slice(0, s - open.length) + text.slice(s, e) + text.slice(e + close.length), start: s - open.length, end: e - open.length };
    }
    if (s === e) return { text: text.slice(0, s) + open + close + text.slice(e), start: s + open.length, end: s + open.length };
    return { text: text.slice(0, s) + open + text.slice(s, e) + close + text.slice(e), start: s + open.length, end: e + open.length };
  }
  function _lines(text, s, e, fn) {
    var a = text.lastIndexOf("\n", Math.max(0, s - 1)) + 1;
    var endPos = e > s && text.charAt(e - 1) === "\n" ? e - 1 : e;
    var b = text.indexOf("\n", endPos); if (b < 0) b = text.length;
    var chunk = text.slice(a, b).split("\n");
    var changed = chunk.map(function (line) {
      var cr = line.charAt(line.length - 1) === "\r";
      var out = fn(cr ? line.slice(0, -1) : line);
      return cr ? out + "\r" : out;
    }).join("\n");
    return { text: text.slice(0, a) + changed + text.slice(b), start: a, end: a + changed.length };
  }
  function togglePrefix(text, s, e, pre) {
    text = String(text); var marks = /^(\s*)(- \[[ xX]\] |\d+\. |[-*+] |(?:> ?)+|#{1,6} )/;
    if (pre === "1. ") {
      var a = text.lastIndexOf("\n", Math.max(0, s - 1)) + 1;
      var endPos = e > s && text.charAt(e - 1) === "\n" ? e - 1 : e;
      var b = text.indexOf("\n", endPos); if (b < 0) b = text.length;
      var chunk = text.slice(a, b).split("\n");
      var remove = chunk.every(function (line) { return /^\s*\d+\. /.test(line); });
      var i = 0;
      return _lines(text, s, e, function (line) {
        var m = line.match(marks), indent = m ? m[1] : "";
        var body = m ? line.slice(m[0].length) : line;
        if (remove) return m ? indent + body : line;
        i += 1;
        return indent + i + ". " + body;
      });
    }
    return _lines(text, s, e, function (line) {
      var m = line.match(marks), indent = m ? m[1] : "";
      var body = m ? line.slice(m[0].length) : line;
      return m && m[2] === pre ? indent + body : indent + pre + body;
    });
  }
  function heading(text, s, e, level) {
    var pre = "#".repeat(Math.max(1, Math.min(3, Number(level) || 1))) + " ";
    return _lines(String(text), s, e, function (line) {
      var m = line.match(/^(\s*)(#{1,6} )(.*)$/);
      var indent = m ? m[1] : "";
      var body = m ? m[3] : line;
      return m && m[2] === pre ? indent + body : indent + pre + body;
    });
  }
  function linkMarkup(label, url) {
    url = String(url || "");
    if (/[\\\u0000-\u001f]/.test(url)) return null;
    url = url.trim();
    if (!/^(https?:\/\/|mailto:|\/(?!\/)|#|\?)/i.test(url) ||
        /^(javascript|data):/i.test(url)) return null;
    return "[" + String(label || "link").replace(/([\\\]])/g, "\\$1") + "](" + url.replace(/[()\\]/g, "\\$&") + ")";
  }
  function insertLink(text, start, end, url) {
    text = String(text);
    var selected = text.slice(start, end);
    var template = selected ? linkMarkup(selected, "/") : "[ ]()";
    if (template === null) return null;
    if (selected && url !== null && url !== undefined) {
      template = linkMarkup(selected, url);
      if (template === null) return null;
      var endAt = start + template.length;
      return { text: text.slice(0, start) + template + text.slice(end),
        start: endAt, end: endAt };
    }
    if (selected) template = template.replace(/\(\/\)$/, "(url)");
    else if (url) {
      template = linkMarkup("", url);
      if (template === null) return null;
    }
    var from = start + (selected ? selected.length + 3 : 1);
    return { text: text.slice(0, start) + template + text.slice(end),
      start: from, end: from + (selected ? 3 : 0) };
  }
  function continueList(text, start, end) {
    text = String(text);
    if (start !== end) return null;
    var lineStart = text.lastIndexOf("\n", Math.max(0, start - 1)) + 1;
    var lineEnd = text.indexOf("\n", start);
    if (lineEnd < 0) lineEnd = text.length;
    var line = text.slice(lineStart, lineEnd).replace(/\r$/, "");
    var match = line.match(/^(\s*)(- \[[ xX]\] |[-*+] |\d+\. |> ?)(.*)$/);
    if (!match) return null;
    var prefix = match[1] + match[2];
    if (!match[3].trim()) {
      var next = text.slice(0, lineStart) + text.slice(lineStart + prefix.length);
      return { text: next, start: lineStart, end: lineStart };
    }
    var numbered = prefix.match(/^(\s*)(\d+)\. $/);
    var nextPrefix = numbered
      ? numbered[1] + (Number(numbered[2]) + 1) + ". "
      : /^\s*- \[[ xX]\] $/.test(prefix) ? prefix.replace(/\[[xX]\]/, "[ ]")
      : prefix;
    var newline = text.indexOf("\r\n") !== -1 ? "\r\n" : "\n";
    var insertion = newline + nextPrefix;
    return { text: text.slice(0, start) + insertion + text.slice(end),
      start: start + insertion.length, end: start + insertion.length };
  }
  function indentLines(text, start, end, outdent) {
    text = String(text);
    var a = text.lastIndexOf("\n", Math.max(0, start - 1)) + 1;
    var endPos = end > start && text.charAt(end - 1) === "\n" ? end - 1 : end;
    var b = text.indexOf("\n", endPos);
    if (b < 0) b = text.length;
    var found = false;
    var changed = text.slice(a, b).split("\n").map(function (line) {
      var cr = line.charAt(line.length - 1) === "\r";
      var body = cr ? line.slice(0, -1) : line;
      var m = body.match(/^(\s*)(- \[[ xX]\] |[-*+] |\d+\. )(.*)$/);
      if (!m) return line;
      found = true;
      var indent = m[1];
      if (outdent) indent = indent.replace(/(?:\t| {1,2})$/, "");
      else indent += "  ";
      var out = indent + m[2] + m[3];
      return cr ? out + "\r" : out;
    }).join("\n");
    if (!found) return null;
    return { text: text.slice(0, a) + changed + text.slice(b),
      start: a, end: a + changed.length };
  }
  function attach(ta, options) {
    options = options || {};
    if (!ta || ta.dataset.mdTool) return { destroy: function () {} };
    ta.dataset.mdTool = "1";
    var bar = document.createElement("div"); bar.className = "md-tool";
    var spacer = document.createElement("div"); spacer.className = "md-tool-spacer";
    var preview = options.preview === false ? null : document.createElement("div");
    if (preview) preview.className = "md-tool-preview md-embed";
    function action(label, title, fn) { var b=document.createElement("button"); b.type="button"; b.className="md-tool-btn"; b.textContent=label; b.title=title; b.setAttribute("aria-label",title); b.addEventListener("click",fn); bar.appendChild(b); return b; }
    function apply(result) { ta.value=result.text; ta.focus(); ta.setSelectionRange(result.start,result.end); ta.dispatchEvent(new Event("input",{bubbles:true})); }
    function wrap(o,c) {
      var s=ta.selectionStart,e=ta.selectionEnd;
      if(s===e){var insert=o+c;ta.value=ta.value.slice(0,s)+insert+ta.value.slice(e);ta.focus();ta.setSelectionRange(s+o.length,s+o.length);ta.dispatchEvent(new Event("input",{bubbles:true}));return;}
      apply(wrapSelection(ta.value,s,e,o,c));
    }
    function toggleMenu(menu, button) {
      menu.hidden = !menu.hidden;
      if (menu.hidden) return;
      var r = button.getBoundingClientRect();
      menu.style.position = "fixed";
      menu.style.left = Math.max(4, Math.min(r.left, window.innerWidth - 180)) + "px";
      menu.style.top = "auto";
      menu.style.bottom = Math.max(4, window.innerHeight - r.top + 4) + "px";
      menu.style.zIndex = "1500";
    }
    action("B","Bold",function(){wrap("**","**")}); action("I","Italic",function(){wrap("*","*")});
    action("Link","Insert link",function(){
      var s=ta.selectionStart,e=ta.selectionEnd, selected=ta.value.slice(s,e);
      if (!selected) { apply(insertLink(ta.value,s,e,null)); return; }
      var url = prompt("Link URL:");
      if (url === null) return;
      var result = insertLink(ta.value,s,e,url);
      if (!result) { alert("Use an http, https, mailto, or internal link."); return; }
      apply(result);
    });
    var hb=action("H","Heading level",function(){toggleMenu(menu,hb);});
    var holder=document.createElement("span"); holder.className="md-tool-heading";
    bar.replaceChild(holder,hb); holder.appendChild(hb);
    var menu=document.createElement("div");menu.className="md-tool-menu";menu.hidden=true; holder.appendChild(menu);
    [1,2,3].forEach(function(n){var b=document.createElement("button");b.type="button";b.textContent="H"+n;b.setAttribute("aria-label","Heading "+n);b.addEventListener("click",function(){apply(heading(ta.value,ta.selectionStart,ta.selectionEnd,n));menu.hidden=true;});menu.appendChild(b);});
    action("•","Bulleted list",function(){apply(togglePrefix(ta.value,ta.selectionStart,ta.selectionEnd,"- "));});
    action("☐","Checklist",function(){apply(togglePrefix(ta.value,ta.selectionStart,ta.selectionEnd,"- [ ] "));});
    action("1.","Numbered list",function(){apply(togglePrefix(ta.value,ta.selectionStart,ta.selectionEnd,"1. "));});
    action(">","Quote",function(){apply(togglePrefix(ta.value,ta.selectionStart,ta.selectionEnd,"> "));});
    action("`","Code",function(){wrap("`","`");});
    var tokenHolder=document.createElement("span"); tokenHolder.className="md-tool-heading";
    var tokenButton=action("{}","Insert token",function(){toggleMenu(tokenMenu,tokenButton);});
    bar.replaceChild(tokenHolder,tokenButton); tokenHolder.appendChild(tokenButton);
    var tokenMenu=document.createElement("div"); tokenMenu.className="md-tool-menu"; tokenMenu.hidden=true; tokenHolder.appendChild(tokenMenu);
    (window.PtosTextBlocks || []).filter(function(item){return item.token;}).forEach(function(item){
      var b=document.createElement("button"); b.type="button"; b.textContent=item.tokenLabel || item.label; b.setAttribute("aria-label","Insert "+(item.tokenLabel || item.label));
      b.addEventListener("click",function(){var s=ta.selectionStart,e=ta.selectionEnd,token=item.token;apply({text:ta.value.slice(0,s)+token+ta.value.slice(e),start:s+token.length,end:s+token.length});tokenMenu.hidden=true;}); tokenMenu.appendChild(b);
    });
    var help=document.createElement("a"); help.className="md-tool-help"; help.href="https://www.markdownguide.org/basic-syntax/"; help.target="_blank"; help.rel="noopener noreferrer"; help.textContent="Markdown help"; help.setAttribute("aria-label","Markdown syntax help"); bar.appendChild(help);
    ta.parentNode.insertBefore(bar,ta);
    ta.parentNode.insertBefore(spacer,ta);
    if (preview) ta.parentNode.insertBefore(preview,ta.nextSibling);
    function renderToolbarPreview() {
      if (!preview) return;
      if (typeof window.renderMarkdown === "function") {
        preview.innerHTML = window.renderMarkdown(ta.value);
      } else {
        preview.textContent = ta.value;
      }
    }
    renderToolbarPreview();
    ta.addEventListener("input",renderToolbarPreview);
    var mobile = window.matchMedia && window.matchMedia("(max-width: 767px)").matches;
    var pinned = false;
    var viewport = window.visualViewport || null;
    function updatePinned() {
      if (!pinned || !mobile) return;
      var vr = viewport;
      var bottom = vr
        ? Math.max(0, window.innerHeight - vr.offsetTop - vr.height) : 0;
      var rect = ta.parentNode.getBoundingClientRect();
      bar.style.left = Math.max(0, rect.left) + "px";
      bar.style.width = Math.max(0, Math.min(rect.width, window.innerWidth - rect.left)) + "px";
      bar.style.bottom = bottom + "px";
      spacer.style.height = (bar.offsetHeight + 6) + "px";
    }
    function pinToolbar() {
      if (!mobile || pinned) return;
      pinned = true;
      bar.classList.add("md-tool-pinned");
      updatePinned();
    }
    function unpinToolbar() {
      if (!pinned) return;
      pinned = false;
      bar.classList.remove("md-tool-pinned");
      bar.style.left = bar.style.width = bar.style.bottom = "";
      spacer.style.height = "0px";
    }
    function onFocusIn(e) {
      if (e.target === ta || bar.contains(e.target)) pinToolbar();
    }
    function onFocusOut() {
      setTimeout(function () {
        if (!bar.contains(document.activeElement) && document.activeElement !== ta) unpinToolbar();
      },0);
    }
    ta.parentNode.addEventListener("focusin",onFocusIn);
    ta.parentNode.addEventListener("focusout",onFocusOut);
    if (viewport) {
      viewport.addEventListener("resize",updatePinned);
      viewport.addEventListener("scroll",updatePinned);
    }
    function key(e){
      if(e.key==="Enter"){var continued=continueList(ta.value,ta.selectionStart,ta.selectionEnd);if(continued){e.preventDefault();apply(continued);}return;}
      if(e.key==="Tab"){var changed=indentLines(ta.value,ta.selectionStart,ta.selectionEnd,e.shiftKey);if(changed){e.preventDefault();apply(changed);}return;}
      if(!(e.ctrlKey||e.metaKey)||e.altKey)return;var k=e.key.toLowerCase();if(k==="b"||k==="i"){e.preventDefault();wrap(k==="b"?"**":"*",k==="b"?"**":"*");}else if(k==="k"){e.preventDefault();bar.querySelector('[aria-label="Insert link"]').click();}
    }
    ta.addEventListener("keydown",key);
    return {destroy:function(){
      ta.removeEventListener("keydown",key);ta.removeEventListener("input",renderToolbarPreview);
      ta.parentNode.removeEventListener("focusin",onFocusIn);ta.parentNode.removeEventListener("focusout",onFocusOut);
      if(viewport){viewport.removeEventListener("resize",updatePinned);viewport.removeEventListener("scroll",updatePinned);}
      delete ta.dataset.mdTool;
      [bar,spacer,preview].forEach(function(el){if(el&&el.parentNode)el.parentNode.removeChild(el);});
    }};
  }
  root.PtosToolbar={attach:attach,wrapSelection:wrapSelection,togglePrefix:togglePrefix,toggleLinePrefix:togglePrefix,heading:heading,linkMarkup:linkMarkup,insertLink:insertLink,continueList:continueList,indentLines:indentLines};
})(window);
