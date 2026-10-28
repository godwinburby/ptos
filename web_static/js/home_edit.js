(function () {
  "use strict";

  var source = null;
  var host = null;
  var editing = false;
  var parts = [];

  function parseSource() {
    var el = document.getElementById("home-note-source");
    if (!el) return null;
    try { return JSON.parse(el.textContent || ""); } catch (e) { return null; }
  }

  function serialize(items) {
    return items.map(function (part) {
      return part.type === "widget" ? "```ptos\n" + part.body + "\n```" : part.text;
    }).join("\n\n").replace(/^\n+|\n+$/g, "") + "\n";
  }

  function widgetPositions(items) {
    var out = [];
    items.forEach(function (item, i) { if (item.type === "widget") out.push(i); });
    return out;
  }

  function _isTimePicker(body) {
    try {
      return String(window.PtosToml.parse(body).view || "").toLowerCase() === "time_picker";
    } catch (e) { return false; }
  }

  function _hasOtherTimePicker(index) {
    return parts.some(function (part, i) {
      return i !== index && part.type === "widget" && _isTimePicker(part.body);
    });
  }

  function actionButton(text, action, index) {
    var button = document.createElement("button");
    button.type = "button";
    button.textContent = text;
    button.dataset.homeEditAction = action;
    button.dataset.homeEditIndex = index;
    return button;
  }

  function addActions() {
    var runs = host.querySelectorAll(".home-widget-run");
    var widgets = widgetPositions(parts);
    runs.forEach(function (run, i) {
      var old = run.querySelector(".home-widget-actions");
      if (old) old.remove();
      if (!editing || widgets[i] == null) return;
      var menu = document.createElement("details");
      menu.className = "home-widget-actions";
      var summary = document.createElement("summary");
      summary.textContent = "⋮";
      summary.title = "Widget actions";
      menu.appendChild(summary);
      var choices = document.createElement("div");
      choices.className = "home-widget-menu";
      choices.appendChild(actionButton("Configure", "configure", widgets[i]));
      choices.appendChild(actionButton("Duplicate", "duplicate", widgets[i]));
      choices.appendChild(actionButton("Move up", "up", widgets[i]));
      choices.appendChild(actionButton("Move down", "down", widgets[i]));
      choices.appendChild(actionButton("Remove", "remove", widgets[i]));
      menu.appendChild(choices);
      run.insertBefore(menu, run.firstChild);
    });
    host.classList.toggle("home-editing", editing);
    var toggle = document.getElementById("home-edit-toggle");
    if (toggle) toggle.textContent = editing ? "Done editing" : "Edit widgets";
  }

  function status(message, error) {
    var el = document.getElementById("home-edit-status");
    if (!el) return;
    el.textContent = message || "";
    el.style.color = error ? "var(--error)" : "var(--sub)";
  }

  function save(content, nextParts, saveUndo) {
    status("Saving…");
    return fetch("/notes/save", {
      method: "POST", headers: {"Content-Type":"application/json"},
      body: JSON.stringify({path:source.path, content:content, base_rev:source.rev})
    }).then(function (r) {
      return r.json().then(function (d) {
        if (!d || !d.ok) throw new Error((d && d.error) || "Could not save Home");
        try {
          if (saveUndo !== false) sessionStorage.setItem("ptos.home.undo", JSON.stringify({path:source.path, content:source.content}));
          else sessionStorage.removeItem("ptos.home.undo");
        } catch (e) {}
        source.content = content;
        source.rev = d.rev;
        parts = nextParts;
        status("Saved");
        location.reload();
        return true;
      });
    }).catch(function (e) {
      status(e.message || "Could not save Home", true);
      return false;
    });
  }

  function showUndoIfAvailable() {
    var toast = document.getElementById("home-edit-undo");
    try {
      var saved = JSON.parse(sessionStorage.getItem("ptos.home.undo") || "null");
      if (toast && saved && saved.path === source.path) toast.style.display = "block";
    } catch (e) {}
  }

  function configure(index) {
    var modal = document.getElementById("home-edit-modal");
    var form = document.getElementById("home-edit-form");
    if (!modal || !form || !window.PtosWidgetForm) return;
    modal.style.display = "flex";
    window.PtosWidgetForm.mount(form, {
      body:parts[index].body, saveLabel:"Save widget", cancelLabel:"Cancel",
      onSave:function (body) {
        if (_isTimePicker(body) && _hasOtherTimePicker(index)) {
          status("A page can have only one time window picker", true);
          return;
        }
        var next = parts.slice();
        next[index] = {type:"widget", body:body};
        window.closeHomeWidgetModal();
        save(serialize(next), next, true);
      },
      onCancel:window.closeHomeWidgetModal
    });
  }

  function act(action, index) {
    if (!parts[index] || parts[index].type !== "widget") return;
    if (action === "configure") { configure(index); return; }
    var next = parts.slice();
    if (action === "duplicate") {
      if (_isTimePicker(next[index].body)) {
        status("A page can have only one time window picker", true);
        return;
      }
      next.splice(index + 1, 0, {type:"widget", body:next[index].body});
    } else if (action === "remove") {
      if (!confirm("Remove this widget from Home?")) return;
      next.splice(index, 1);
    } else {
      var positions = widgetPositions(next);
      var pos = positions.indexOf(index);
      var other = positions[action === "up" ? pos - 1 : pos + 1];
      if (other == null) return;
      var tmp = next[index];
      next[index] = next[other];
      next[other] = tmp;
    }
    save(serialize(next), next, true);
  }

  window.toggleHomeEdit = function () { editing = !editing; addActions(); };
  window.closeHomeWidgetModal = function () {
    var modal = document.getElementById("home-edit-modal");
    var form = document.getElementById("home-edit-form");
    if (modal) modal.style.display = "none";
    if (form) form.innerHTML = "";
  };
  window.undoHomeEdit = function () {
    var previous = null;
    try { previous = JSON.parse(sessionStorage.getItem("ptos.home.undo") || "null"); } catch (e) {}
    if (!previous || previous.path !== source.path) return;
    save(previous.content, window.PtosHomeNote.split(previous.content), false);
  };

  function boot() {
    source = parseSource();
    host = document.getElementById("home");
    if (!source || !host || !window.PtosHomeNote) return;
    parts = window.PtosHomeNote.split(source.content || "");
    host.addEventListener("click", function (event) {
      var button = event.target.closest && event.target.closest("[data-home-edit-action]");
      if (button) act(button.dataset.homeEditAction, Number(button.dataset.homeEditIndex));
    });
    showUndoIfAvailable();
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot);
  else boot();
})();
