
function _getBracketToken(inputEl) {
  var val = inputEl.value;
  var pos = inputEl.selectionStart;
  var before = val.substring(0, pos);
  var openIdx = before.lastIndexOf("[[");
  if (openIdx === -1) return null;
  var closeIdx = before.lastIndexOf("]]");
  if (closeIdx > openIdx) return null;
  return {
    query: before.substring(openIdx + 2),
    start: openIdx,
    fullToken: val.substring(openIdx, pos),
  };
}

function _getOrCreateBracketAcList(inputEl) {
  var id = inputEl.id + '-bracket-ac';
  var list = document.getElementById(id);
  if (!list) {
    list = document.createElement('div');
    list.id = id;
    list.className = 'bracket-ac-list';
    inputEl.parentNode.style.position = 'relative';
    inputEl.parentNode.appendChild(list);
  }
  return list;
}

function attachBracketAutocomplete(inputEl) {
  var _acTimer = null;
  inputEl.addEventListener('input', function() {
    var tok = _getBracketToken(inputEl);
    var list = _getOrCreateBracketAcList(inputEl);
    if (!tok) { list.classList.remove('open'); return; }
    clearTimeout(_acTimer);
    _acTimer = setTimeout(function() {
      fetch('/api/link-candidates?q=' + encodeURIComponent(tok.query))
        .then(function(r) { return r.json(); })
        .then(function(items) {
          if (!items.length) { list.classList.remove('open'); return; }
          list.innerHTML = items.map(function(it, i) {
            return '<div class="bracket-ac-item" data-idx="'+i+'">'+it+'</div>';
          }).join('');
          list.classList.add('open');
          var _bIdx = -1;
          var _bItems = items;
          function _pickBracket(idx) {
            if (!_bItems[idx]) return;
            var before = inputEl.value.substring(0, tok.start);
            var after = inputEl.value.substring(tok.start + tok.fullToken.length);
            inputEl.value = before + '[[' + _bItems[idx] + ']]' + after;
            list.classList.remove('open');
            inputEl.focus();
            var newPos = tok.start + _bItems[idx].length + 4;
            inputEl.setSelectionRange(newPos, newPos);
          }
          list.querySelectorAll('.bracket-ac-item').forEach(function(el) {
            el.addEventListener('mousedown', function(e) {
              e.preventDefault();
              _pickBracket(parseInt(el.dataset.idx));
            });
          });
          inputEl.onkeydown = function(e) {
            if (!list.classList.contains('open')) return;
            if (e.key === 'ArrowDown') { e.preventDefault(); _bIdx = Math.min(_bIdx+1, _bItems.length-1); list.querySelectorAll('.bracket-ac-item').forEach(function(el,i){el.classList.toggle('active',i===_bIdx);}); }
            else if (e.key === 'ArrowUp') { e.preventDefault(); _bIdx = Math.max(_bIdx-1, 0); list.querySelectorAll('.bracket-ac-item').forEach(function(el,i){el.classList.toggle('active',i===_bIdx);}); }
            else if (e.key === 'Enter' && _bIdx >= 0) { e.preventDefault(); _pickBracket(_bIdx); }
            else if (e.key === 'Escape') { list.classList.remove('open'); }
          };
        });
    }, 250);
  });
  inputEl.addEventListener('blur', function() {
    setTimeout(function() {
      var list = document.getElementById(inputEl.id + '-bracket-ac');
      if (list) list.classList.remove('open');
    }, 150);
  });
}

function preprocessLinks(src) {
  return src.replace(/\[\[([^\]]+)\]\]/g, function(_, target) {
    return '[' + target + '](/search?q=' + encodeURIComponent(target) + ')';
  });
}

// ── Backlinks / "Linked mentions" panel ───────────────────────────────────────
// Given a subject, fetch /api/backlinks?q= and render four collapsible groups
// (Notes / Journal / Todo / Records). Hides the container if nothing matches.

var _blGroups = [
  { key: "notes",   label: "Notes" },
  { key: "journal", label: "Journal" },
  { key: "todo",    label: "Todo" },
  { key: "records", label: "Records" }
];

function _blItemHref(key, item) {
  if (key === "notes")   return "/notes/edit/" + encodeURIComponent(item.rel_path || (item.category + "/" + item.slug));
  if (key === "journal") return "/journal?date=" + encodeURIComponent(item.date);
  if (key === "todo")    return "/todo?search=" + encodeURIComponent(item.line);
  if (key === "records") return "/editor?file=" + encodeURIComponent(item.path) + "&goto=" + encodeURIComponent(item.lineno);
  return "#";
}

function _blItemText(key, item) {
  if (key === "notes")   return item.title || (item.rel_path || item.slug || "").split("/").pop();
  if (key === "journal") return item.date;
  if (key === "todo")    return item.line || "line " + item.lineno + (item.done ? " (done)" : "");
  if (key === "records") return (item.date || "") + " · " + (item.type || "") + " · " + (item.field || "");
  return "";
}

function _blItemSnippet(item) {
  return item.snippet ? item.snippet.trim() : "";
}

function _blRenderGroups(container, data, openFirst) {
  container.innerHTML = "";
  var any = false;
  _blGroups.forEach(function(g) {
    var items = data[g.key] || [];
    if (!items.length) return;
    any = true;
    var wrap = document.createElement("details");
    if (g.key === openFirst) wrap.open = true;
    wrap.style.cssText = "margin:0;border-bottom:1px solid var(--border,#ddd);";
    var sum = document.createElement("summary");
    sum.style.cssText = "cursor:pointer;font-size:12px;font-weight:700;padding:6px 2px;";
    sum.textContent = g.label + " (" + items.length + ")";
    wrap.appendChild(sum);
    var list = document.createElement("div");
    list.style.cssText = "padding:0 2px 6px 14px;display:flex;flex-direction:column;gap:4px;";
    items.forEach(function(item) {
      var a = document.createElement("a");
      a.href = _blItemHref(g.key, item);
      a.style.cssText = "color:var(--accent);text-decoration:none;font-size:12px;";
      a.textContent = _blItemText(g.key, item);
      list.appendChild(a);
      var snip = _blItemSnippet(item);
      if (snip) {
        var p = document.createElement("div");
        p.style.cssText = "font-size:11px;color:var(--sub,#888);margin-top:-2px;";
        p.textContent = "“" + snip + "”";
        list.appendChild(p);
      }
    });
    wrap.appendChild(list);
    container.appendChild(wrap);
  });
  if (!any) container.style.display = "none";
  else container.style.display = "";
}

function _blEmpty(container) {
  if (container) container.style.display = "none";
}

// Full panel for a single subject (used by notes.html).
function initBacklinksPanel(container, subject) {
  if (!container || !subject) return;
  fetch("/api/backlinks?q=" + encodeURIComponent(subject))
    .then(function(r) { return r.json(); })
    .then(function(d) { _blRenderGroups(container, d); })
    .catch(function() { _blEmpty(container); });
}

// Journal mode: show one expandable section per [[link]] found inside the
// journal content itself, each listing that link's backlinks.
function initJournalBacklinks(container, content) {
  if (!container) return;
  var links = [];
  var seen = {};
  var re = /\[\[([^\]]+)\]\]/g, m;
  while ((m = re.exec(content)) !== null) {
    var t = m[1].trim();
    if (t && !seen[t.toLowerCase()]) { seen[t.toLowerCase()] = true; links.push(t); }
  }
  if (!links.length) { _blEmpty(container); return; }
  container.innerHTML = "";
  var done = 0;
  links.forEach(function(link) {
    var wrap = document.createElement("details");
    wrap.style.cssText = "margin:0;border-bottom:1px solid var(--border,#ddd);";
    var sum = document.createElement("summary");
    sum.style.cssText = "cursor:pointer;font-size:12px;font-weight:700;padding:6px 2px;";
    sum.textContent = link;
    wrap.appendChild(sum);
    container.appendChild(wrap);
    fetch("/api/backlinks?q=" + encodeURIComponent(link))
      .then(function(r) { return r.json(); })
      .then(function(d) {
        var inner = document.createElement("div");
        inner.style.cssText = "padding:0 2px 6px 14px;";
        if (!(d.notes && d.notes.length) && !(d.journal && d.journal.length) &&
            !(d.todo && d.todo.length) && !(d.records && d.records.length)) {
          inner.textContent = "No references found.";
          inner.style.cssText += "font-size:11px;color:var(--sub,#888);";
        } else {
          _blRenderGroups(inner, d, null);
          inner.style.display = "block";
        }
        wrap.appendChild(inner);
        done++;
        if (done === links.length) container.style.display = "block";
      })
      .catch(function() {
        done++;
        if (done === links.length) container.style.display = "block";
      });
  });
}
