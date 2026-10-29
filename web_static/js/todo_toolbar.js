(function () {
  "use strict";

  function esc(value) {
    return String(value == null ? "" : value)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;")
      .replace(/>/g, "&gt;").replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  function option(value, label, selected) {
    return '<option value="' + esc(value) + '"' +
      (String(value) === String(selected) ? " selected" : "") + ">" +
      esc(label) + "</option>";
  }

  function select(key, label, choices, value) {
    return '<label class="todo-shell-field">' + esc(label) +
      '<select data-todo-filter="' + esc(key) + '" aria-label="' + esc(label) + '">' +
      choices.map(function (entry) {
        return option(entry[0], entry[1], value);
      }).join("") + "</select></label>";
  }

  function currentChips(filters, hideRoutines) {
    var labels = {
      project: "Project", context: "Context", priority: "Priority",
      due: "Due", search: "Search", linked_to: "Linked"
    };
    var chips = Object.keys(labels).filter(function (key) {
      if (key === "project" && hideRoutines && String(filters.project).charAt(0) === "-") return false;
      return filters[key];
    }).map(function (key) {
      return '<button type="button" class="todo-shell-chip" data-todo-remove="' +
        key + '"><span>' + labels[key] + ': ' + esc(filters[key]) +
        '</span><b aria-hidden="true">×</b><span class="sr-only">Clear ' +
        labels[key] + ' filter</span></button>';
    }).join("");
    if (hideRoutines) {
      chips += '<button type="button" class="todo-shell-chip" data-todo-show-routines>' +
        '<span>Routines hidden</span><b aria-hidden="true">×</b>' +
        '<span class="sr-only">Show routines</span></button>';
    }
    return chips;
  }

  function mount(root, state, onChange) {
    state = state || {};
    var filters = Object.assign({
      project: "", context: "", priority: "", due: "", search: "", linked_to: ""
    }, state.filters || {});
    var projects = state.projects || [];
    var contexts = state.contexts || [];
    var priorities = state.priorities || [];
    var views = state.views || {};
    var projectChoices = [["", "All projects"]];
    projects.forEach(function (project) {
      var raw = String(project);
      var normalized = raw.charAt(0) === "+" ? raw.slice(1) : raw;
      projectChoices.push([raw, normalized]);
      projectChoices.push(["-" + normalized, "Exclude " + normalized]);
    });
    if (projectChoices.every(function (entry) { return entry[0] !== filters.project; }) && filters.project) {
      projectChoices.push([filters.project, "Current: " + filters.project]);
    }
    var contextChoices = [["", "All contexts"]].concat(contexts.map(function (value) {
      return [value, value];
    }));
    if (filters.context && contextChoices.every(function (entry) { return entry[0] !== filters.context; })) {
      contextChoices.push([filters.context, "Current: " + filters.context]);
    }
    var priorityChoices = [["", "All priorities"]].concat(priorities.map(function (value) {
      var labels = state.priority_labels || {};
      return [value, value + (labels[value] ? " · " + labels[value] : "")];
    }));
    if (filters.priority && priorityChoices.every(function (entry) { return entry[0] !== filters.priority; })) {
      priorityChoices.push([filters.priority, "Current: " + filters.priority]);
    }
    var dueChoices = [["", "Any due"]].concat([
      ["overdue", "Overdue"], ["today", "Today"], ["tomorrow", "Tomorrow"],
      ["upcoming", "Upcoming"], ["someday", "Someday"], ["none", "No due date"],
      ["week", "This week"]
    ]);
    var groupChoices = [
      ["timeline", "Timeline"], ["priority", "Priority"],
      ["project", "Project"], ["context", "Context"], ["none", "None"]
    ];
    var sortChoices = [
      ["default", "Default order"], ["reverse", "Reverse order"],
      ["most", "Most tasks first"], ["fewest", "Fewest tasks first"]
    ];
    var savedViewChoices = [['', 'Current filters']].concat(Object.keys(views).sort().map(function (name) {
      return [name, views[name].title || name.replace(/_/g, " ")];
    }));

    root.innerHTML = '<div class="todo-shell-toolbar">' +
      '<form class="todo-shell-add" data-todo-add-form>' +
      '<label class="sr-only" for="todo-shell-add-input">Add a task</label>' +
      '<input id="todo-shell-add-input" type="text" data-todo-add-input ' +
      'placeholder="Add a task... (pri:a +Project @context due:tomorrow)">' +
      '<button type="submit" class="btn btn-primary">Add</button>' +
      '<button type="button" class="btn btn-ghost todo-shell-add-form" data-todo-form-add ' +
      'title="Form add (n)" aria-label="Open task form">+</button></form>' +
      '<div class="todo-shell-add-error" data-todo-add-error role="alert" hidden></div>' +
      '<div class="chip-toggle-bar" data-qp-toggle style="cursor:pointer;font-size:12px;color:var(--sub);user-select:none;margin-top:6px;">' +
      '<span class="chip-toggle-arrow" style="display:inline-block;transition:transform .15s;">&#9654;</span> Quick pick</div>' +
      '<div class="add-chips" id="add-chips" data-qp-chips style="display:none;gap:6px;margin-top:6px;">' +
      '<div class="chip-group-card"><div class="chip-group-label">Due</div><div class="chip-row">' +
      '<button class="add-chip" data-token="due:today " data-qp-group="due">today</button>' +
      '<button class="add-chip" data-token="due:tomorrow " data-qp-group="due">tomorrow</button>' +
      '<button class="add-chip" data-token="due:this_week " data-qp-group="due">this week</button>' +
      '<button class="add-chip" data-token="due:next_week " data-qp-group="due">next week</button>' +
      '<button class="add-chip" data-token="due:this_month " data-qp-group="due">this month</button>' +
      '<button class="add-chip" data-token="due:next_month " data-qp-group="due">next month</button>' +
      '<button class="add-chip" data-token="__PICKER__:due:" data-qp-group="due" data-qp-picker="due">pick date...</button>' +
      '</div></div>' +
      '<div class="chip-group-card"><div class="chip-group-label">Priority</div><div class="chip-row">' +
      '<button class="add-chip pri-chip pri-A" data-token="(A) " data-qp-group="pri">(A) Critical</button>' +
      '<button class="add-chip pri-chip pri-B" data-token="(B) " data-qp-group="pri">(B) Important</button>' +
      '<button class="add-chip pri-chip pri-C" data-token="(C) " data-qp-group="pri">(C) Moderate</button>' +
      '<button class="add-chip pri-chip pri-D" data-token="(D) " data-qp-group="pri">(D) Low</button>' +
      '</div></div>' +
      (state.projects && state.projects.length ? '<div class="chip-group-card full-width"><div class="chip-group-label">Projects</div><div class="chip-row">' +
      state.projects.map(function (p) {
        return '<button class="add-chip" data-token="' + p.replace(/"/g, '&quot;') + ' " data-qp-group="proj">' + p + '</button>';
      }).join("") + '</div></div>' : '') +
      (state.contexts && state.contexts.length ? '<div class="chip-group-card full-width"><div class="chip-group-label">Contexts</div><div class="chip-row">' +
      state.contexts.map(function (c) {
        return '<button class="add-chip" data-token="' + c.replace(/"/g, '&quot;') + ' " data-qp-group="ctx">' + c + '</button>';
      }).join("") + '</div></div>' : '') +
      '<div class="chip-group-card"><div class="chip-group-label">Threshold</div><div class="chip-row">' +
      '<button class="add-chip" data-token="t:today " data-qp-group="threshold">today</button>' +
      '<button class="add-chip" data-token="t:tomorrow " data-qp-group="threshold">tomorrow</button>' +
      '<button class="add-chip" data-token="t:this_week " data-qp-group="threshold">this week</button>' +
      '<button class="add-chip" data-token="t:this_month " data-qp-group="threshold">this month</button>' +
      '<button class="add-chip" data-token="__PICKER__:t:" data-qp-group="threshold" data-qp-picker="t">pick date...</button>' +
      '</div></div>' +
      '<div class="chip-group-card"><div class="chip-group-label">Repeat</div><div class="chip-row">' +
      '<button class="add-chip" data-token="rec:1d " data-qp-group="rec">daily</button>' +
      '<button class="add-chip" data-token="rec:1w " data-qp-group="rec">weekly</button>' +
      '<button class="add-chip" data-token="rec:1m " data-qp-group="rec">monthly</button>' +
      '<button class="add-chip" data-token="rec:1y " data-qp-group="rec">yearly</button>' +
      '</div></div>' +
      '</div>' +
      '<div class="todo-shell-saved">' +
      '<label class="todo-shell-field">Saved view<select data-todo-saved-view aria-label="Saved Todo view">' +
      savedViewChoices.map(function (entry) {
        return option(entry[0], entry[1], state.selected_view || "");
      }).join("") + '</select></label>' +
      '<button type="button" class="btn btn-ghost btn-sm" data-todo-save-view>Save view</button>' +
      '<button type="button" class="btn btn-ghost btn-sm" data-todo-update-view>Update view</button>' +
      '<button type="button" class="btn btn-ghost btn-sm" data-todo-delete-view>Delete view</button>' +
      '<span class="todo-shell-view-message" data-todo-view-message role="status" aria-live="polite"></span></div>' +
      '<form class="todo-shell-search" data-todo-search-form role="search">' +
      '<label class="sr-only" for="todo-shell-search-input">Search tasks</label>' +
      '<input id="todo-shell-search-input" type="search" data-todo-search value="' +
      esc(filters.search) + '" placeholder="Search tasks; use +Project @context pri:A due:today * for wildcard">' +
      '<button type="submit" class="btn btn-primary btn-sm">Search</button></form>' +
'<div class="groupby-bar" style="display:flex;gap:4px;margin:8px 0;align-items:center;">' +
      groupChoices.map(function (entry) {
        var mode = entry[0];
        var label = entry[1];
        var active = (state.groupby || "timeline") === mode ? "active" : "";
        return '<button type="button" class="groupby-btn ' + active + '" data-todo-groupby="' + mode + '" ' +
          'style="padding:4px 10px;border:1px solid var(--border);border-radius:6px;background:transparent;cursor:pointer;font-size:12px;' +
          (active ? 'background:var(--accent);color:#fff;border-color:var(--accent);' : '') + '">' + label + '</button>';
      }).join("") +
      '<button type="button" class="groupby-sort" onclick="toggleSectionSort()" title="Toggle sort order" ' +
      'style="padding:4px 8px;border:1px solid var(--border);border-radius:6px;background:transparent;cursor:pointer;font-size:12px;margin-left:auto;">↕</button>' +
      '<button type="button" class="todo-sel-btn" onclick="toggleSelectMode()" title="Select multiple tasks" ' +
      'style="padding:4px 8px;border:1px solid var(--border);border-radius:6px;background:transparent;cursor:pointer;font-size:12px;">☐ Select</button>' +
      '</div>' +
      '<div class="todo-shell-filters">' +
      select("project", "Project", projectChoices, filters.project) +
      select("context", "Context", contextChoices, filters.context) +
      select("priority", "Priority", priorityChoices, filters.priority) +
      select("due", "Due", dueChoices, filters.due) +
      select("sort", "Sort sections", sortChoices, state.sort || "default") +
      '</div><div class="todo-shell-active" data-todo-active>' +
      currentChips(filters, state.hide_routines) +
      (Object.keys(filters).some(function (key) { return filters[key]; }) || state.hide_routines
        ? '<button type="button" class="todo-shell-clear" data-todo-clear>Clear filters</button>' : "") +
      '</div>' +
      '<label class="todo-shell-routines"><input type="checkbox" data-todo-hide-routines' +
      (state.hide_routines ? " checked" : "") + '> Hide routines</label>' +
      '</div>';

    var listeners = [];
    function on(node, event, fn) {
      node.addEventListener(event, fn);
      listeners.push([node, event, fn]);
    }
    root.querySelectorAll("[data-todo-filter]").forEach(function (node) {
      on(node, "change", function () {
        var key = node.getAttribute("data-todo-filter");
        var changes = {};
        changes[key] = node.value;
        if (key === "project") {
          state.hide_routines = node.value.charAt(0) === "-";
          changes.hide_routines = state.hide_routines;
        }
        if (key === "groupby") state.groupby = node.value;
        if (key === "sort") state.sort = node.value;
        if (key === "project") filters.project = node.value;
        if (["context", "priority", "due"].indexOf(key) >= 0) filters[key] = node.value;
        syncChrome();
        onChange(changes);
      });
    });
    root.querySelectorAll("[data-todo-groupby]").forEach(function (node) {
      on(node, "click", function () {
        var mode = node.getAttribute("data-todo-groupby");
        state.groupby = mode;
        syncChrome();
        onChange({ groupby: mode });
      });
    });
    on(root.querySelector("[data-todo-search-form]"), "submit", function (event) {
      event.preventDefault();
      var raw = root.querySelector("[data-todo-search]").value.trim();
      var params = {};
      var search = raw.replace(/\+(\S+)/g, function (_, v) { params.project = v; return ''; })
                    .replace(/@(\S+)/g, function (_, v) { params.context = v; return ''; })
                    .replace(/\bdue:(\S+)/gi, function (_, v) { params.due = v; return ''; })
                    .replace(/\bpri:([A-Da-d])/gi, function (_, v) { params.priority = v.toUpperCase(); return ''; })
                    .trim();
      if (search) params.search = search;
      // Clear filter tokens from the search input — only the search term remains
      root.querySelector("[data-todo-search]").value = search;
      if (params.project !== undefined) filters.project = params.project;
      if (params.context !== undefined) filters.context = params.context;
      if (params.priority !== undefined) filters.priority = params.priority;
      if (params.due !== undefined) filters.due = params.due;
      if (params.search !== undefined) filters.search = params.search;
      syncChrome();
      onChange(params);
    });
    on(root.querySelector("[data-todo-add-form]"), "submit", function (event) {
      event.preventDefault();
      var input = root.querySelector("[data-todo-add-input]");
      var message = root.querySelector("[data-todo-add-error]");
      var text = input.value.trim();
      if (!text) { input.focus(); return; }
      var button = root.querySelector('[data-todo-add-form] [type="submit"]');
      button.disabled = true;
      message.hidden = true;
      fetch("/todo/add", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text: text })
      }).then(function (response) { return response.json(); }).then(function (result) {
        if (!result || !result.ok) {
          message.textContent = (result && result.error) || "Could not add task";
          message.hidden = false;
          return;
        }
        input.value = "";
        onChange({});
      }).catch(function () {
        message.textContent = "Could not add task. Check your connection and try again.";
        message.hidden = false;
      }).then(function () { button.disabled = false; });
    });
    on(root.querySelector("[data-todo-form-add]"), "click", function () {
      if (typeof window.openAdd === "function") window.openAdd();
    });
    var viewSelect = root.querySelector("[data-todo-saved-view]");
    function refreshViewButtons() {
      root.querySelector("[data-todo-update-view]").disabled = !state.selected_view;
      root.querySelector("[data-todo-delete-view]").disabled = !state.selected_view;
    }
    function viewConfig() {
      var cfg = {};
      ["project", "context", "priority", "due", "search", "linked_to"].forEach(function (key) {
        if (filters[key]) cfg[key] = filters[key];
      });
      cfg.groupby = state.groupby || "timeline";
      cfg.sort = state.sort || "default";
      cfg.hide_routines = !!state.hide_routines;
      cfg.include_done = state.include_done !== false;
      return cfg;
    }
    function showViewMessage(text, isError) {
      var node = root.querySelector("[data-todo-view-message]");
      node.textContent = text;
      node.classList.toggle("error", !!isError);
    }
    function addViewOption(name) {
      var optionEl = Array.prototype.find.call(viewSelect.options, function (entry) {
        return entry.value === name;
      });
      if (!optionEl) {
        optionEl = document.createElement("option");
        optionEl.value = name;
        viewSelect.appendChild(optionEl);
      }
      optionEl.textContent = (views[name] && views[name].title) || name.replace(/_/g, " ");
      viewSelect.value = name;
    }
    function saveView(name) {
      var cfg = viewConfig();
      if (views[name]) {
        ["title", "limit", "add"].forEach(function (key) {
          if (Object.prototype.hasOwnProperty.call(views[name], key)) cfg[key] = views[name][key];
        });
      }
      fetch("/api/query-builder/todo", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: name, cfg: cfg })
      }).then(function (response) { return response.json(); }).then(function (result) {
        if (!result || !result.ok) {
          showViewMessage((result && result.error) || "Could not save view", true);
          return;
        }
        views[name] = cfg;
        state.selected_view = name;
        addViewOption(name);
        refreshViewButtons();
        showViewMessage("Saved", false);
        onChange({ selected_view: name });
      }).catch(function () { showViewMessage("Could not save view", true); });
    }
    on(viewSelect, "change", function () {
      var name = viewSelect.value;
      state.selected_view = name;
      state.include_done = name && views[name] && views[name].include_done === false ? false : true;
      var cfg = views[name] || {};
      ["project", "context", "priority", "due", "search", "linked_to"].forEach(function (key) {
        filters[key] = cfg[key] || "";
      });
      state.groupby = cfg.groupby || "timeline";
      state.sort = cfg.sort || "default";
      state.hide_routines = !!cfg.hide_routines;
      refreshViewButtons();
      syncChrome();
      var changes = { selected_view: name };
      ["project", "context", "priority", "due", "search", "linked_to"].forEach(function (key) {
        changes[key] = filters[key];
      });
      changes.groupby = state.groupby;
      changes.sort = state.sort;
      changes.hide_routines = state.hide_routines;
      changes.include_done = state.include_done;
      onChange(changes);
    });
    on(root.querySelector("[data-todo-save-view]"), "click", function () {
      var suggested = state.selected_view || "";
      var name = window.prompt("Name this Todo view (lowercase letters, numbers, underscores):", suggested);
      if (name == null) return;
      name = name.trim().toLowerCase().replace(/[^a-z0-9_]+/g, "_").replace(/^_+|_+$/g, "");
      if (!name) { showViewMessage("Enter a valid view name", true); return; }
      saveView(name);
    });
    on(root.querySelector("[data-todo-update-view]"), "click", function () {
      if (state.selected_view) saveView(state.selected_view);
    });
    on(root.querySelector("[data-todo-delete-view]"), "click", function () {
      var name = state.selected_view;
      if (!name || !window.confirm("Delete saved Todo view '" + name + "'?")) return;
      fetch("/api/query-builder/todo", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: name, action: "delete" })
      }).then(function (response) { return response.json(); }).then(function (result) {
        if (!result || !result.ok) {
          showViewMessage((result && result.error) || "Could not delete view", true);
          return;
        }
        delete views[name];
        Array.prototype.forEach.call(viewSelect.options, function (entry) {
          if (entry.value === name) entry.remove();
        });
        viewSelect.value = "";
        state.selected_view = "";
        refreshViewButtons();
        showViewMessage("Deleted", false);
        onChange({ selected_view: "" });
      }).catch(function () { showViewMessage("Could not delete view", true); });
    });
    refreshViewButtons();
    // Quick-pick chip delegation
    var qpToggle = root.querySelector("[data-qp-toggle]");
    if (qpToggle) {
      on(qpToggle, "click", function () {
        var chips = root.querySelector("[data-qp-chips]");
        if (!chips) return;
        var open = chips.style.display !== "none" && chips.style.display !== "";
        chips.style.display = open ? "none" : "grid";
        var arrow = qpToggle.querySelector(".chip-toggle-arrow");
        if (arrow) arrow.style.transform = open ? "" : "rotate(90deg)";
      });
    }
    var qpChips = root.querySelector("[data-qp-chips]");
    if (qpChips) {
      on(qpChips, "click", function (e) {
        var chip = e.target && e.target.closest && e.target.closest(".add-chip");
        if (!chip || !qpChips.contains(chip)) return;
        var picker = chip.getAttribute("data-qp-picker");
        if (picker) {
          if (window.PtosTodoPopups && window.PtosTodoPopups.pickAddDate) {
            window.PtosTodoPopups.pickAddDate(picker);
          }
          return;
        }
        var group = chip.getAttribute("data-qp-group");
        var token = chip.getAttribute("data-token") || "";
        var input = root.querySelector("[data-todo-add-input]");
        if (!input) return;
        var text = input.value;
        var bare = token.trim();
        if (group === "pri") {
          qpChips.querySelectorAll(".pri-chip").forEach(function (c) {
            var t = (c.getAttribute("data-token") || "").trim();
            text = text.replace(new RegExp("\\(" + t + "\\)" + "\\s*"), "");
          });
          if (text.indexOf(bare) === -1) text = token + text;
        } else if (group === "due" || group === "threshold") {
          var prefix = group === "threshold" ? "t:" : "due:";
          text = text.replace(new RegExp(prefix.replace(/[.*+?^${}()|[\]\\]/g, "\\$&") + "\\S*\\s*", "gi"), "");
          text = text.trimEnd() + " " + token;
        } else if (group === "rec") {
          text = text.replace(/rec:\\S+\\s*/gi, "");
          text = text.trimEnd() + " " + token;
        } else if (text.indexOf(bare) !== -1) {
          text = text.replace(new RegExp(bare.replace(/[.*+?^${}()|[\]\\]/g, "\\$&") + "\\s*"), "");
        } else {
          text = text.trimEnd() + " " + token;
        }
        var wasSelected = chip.classList.contains("selected");
        input.value = text.replace(/^\s+/, "");
        // Mutual exclusivity: clear selected from siblings in same group
        if (group === "pri" || group === "due" || group === "threshold" || group === "rec") {
          var grp = chip.getAttribute("data-qp-group");
          qpChips.querySelectorAll(".add-chip[data-qp-group='" + grp + "']").forEach(function (c) {
            c.classList.remove("selected");
          });
          if (!wasSelected) {
            chip.classList.add("selected");
          }
        } else {
          chip.classList.toggle("selected");
        }
        input.focus();
      });
    }

    on(root.querySelector("[data-todo-hide-routines]"), "change", function (event) {
      state.hide_routines = !!event.target.checked;
      if (state.hide_routines) filters.project = "-routine";
      else if (filters.project === "-routine") filters.project = "";
      syncChrome();
      onChange({ project: filters.project, hide_routines: state.hide_routines });
    });
    on(root.querySelector("[data-todo-active]"), "click", function (event) {
      var remove = event.target.closest && event.target.closest("[data-todo-remove]");
      if (remove) {
        var key = remove.getAttribute("data-todo-remove");
        var wasExclusion = String(filters[key] || "").charAt(0) === "-";
        var changes = {}; changes[key] = ""; filters[key] = "";
        if (key === "project" && wasExclusion) {
          changes.hide_routines = false; state.hide_routines = false;
        }
        syncChrome();
        onChange(changes);
        return;
      }
      if (event.target.closest && event.target.closest("[data-todo-show-routines]")) {
        state.hide_routines = false;
        filters.project = "";
        syncChrome();
        onChange({ project: "", hide_routines: false });
        return;
      }
      if (event.target.closest && event.target.closest("[data-todo-clear]")) {
        Object.keys(filters).forEach(function (key) { filters[key] = ""; });
        state.hide_routines = false;
        syncChrome();
        onChange({ project: "", context: "", priority: "", due: "", search: "",
          linked_to: "", hide_routines: false });
      }
    });

    function syncChrome() {
      var active = root.querySelector("[data-todo-active]");
      active.innerHTML = currentChips(filters, state.hide_routines) +
        (Object.keys(filters).some(function (key) { return filters[key]; }) || state.hide_routines
          ? '<button type="button" class="todo-shell-clear" data-todo-clear>Clear filters</button>' : "");
      root.querySelector("[data-todo-hide-routines]").checked = !!state.hide_routines;
      root.querySelectorAll("[data-todo-groupby]").forEach(function (btn) {
        var mode = btn.getAttribute("data-todo-groupby");
        if (mode === (state.groupby || "timeline")) {
          btn.classList.add("active");
          btn.style.background = "var(--accent)";
          btn.style.color = "#fff";
          btn.style.borderColor = "var(--accent)";
        } else {
          btn.classList.remove("active");
          btn.style.background = "transparent";
          btn.style.color = "";
          btn.style.borderColor = "var(--border)";
        }
      });
    }
    return { destroy: function () {
      listeners.forEach(function (entry) {
        entry[0].removeEventListener(entry[1], entry[2]);
      });
    }};
  }

  window.PtosTodoToolbar = { mount: mount };
})();
