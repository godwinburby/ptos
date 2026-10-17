// Favorites star + in-place sidebar list updates.
//
// The server renders the initial sidebar rows and the window.PTOS.favUrls
// array (no-JS / first paint). This script only handles the ★ toggle and
// patches the sidebar / More-menu rows in place after a change, so starring
// a page never needs a reload.
(function () {
  var urls = window.PTOS && window.PTOS.favUrls ? window.PTOS.favUrls : [];

  function currentUrl() {
    return location.pathname + location.search;
  }

  function isFav(url) {
    return urls.indexOf(url) !== -1;
  }

  function setStars() {
    var on = isFav(currentUrl());
    var btns = document.querySelectorAll(".fav-star");
    for (var i = 0; i < btns.length; i++) {
      btns[i].innerHTML = on ? "&#9733;" : "&#9734;"; // ★ / ☆
      btns[i].classList.toggle("on", on);
      btns[i].title = on ? "Remove this page from favorites" : "Star this page";
    }
  }

  function markActive() {
    var url = currentUrl();
    var items = document.querySelectorAll("#fav-group .fav-item[data-url]");
    for (var i = 0; i < items.length; i++) {
      items[i].classList.toggle("fav-active", items[i].getAttribute("data-url") === url);
    }
  }

  function defaultName() {
    var t = document.title || "";
    t = t.replace(/^PTOS\s*[·|]\s*/, "").replace(/\s*[·|]\s*PTOS.*$/, "").trim();
    if (t && t !== "PTOS") return t;
    var seg = location.pathname.split("/").filter(Boolean).pop() || "Home";
    try { seg = decodeURIComponent(seg); } catch (e) {}
    return seg.replace(/\.md$/, "").replace(/[-_]/g, " ");
  }

  function patchList(items) {
    urls = (items || []).map(function (f) { return f.url; });
    var group = document.getElementById("fav-group");
    if (group) {
      var manage = group.querySelector(".fav-manage");
      var empty = group.querySelector(".fav-empty");
      var old = group.querySelectorAll(".fav-item:not(.fav-manage)");
      for (var i = 0; i < old.length; i++) old[i].remove();
      if (empty) empty.remove();
      items.forEach(function (f) {
        var a = document.createElement("a");
        a.href = f.url;
        a.className = "fav-item";
        a.setAttribute("data-url", f.url);
        a.textContent = f.name;
        group.insertBefore(a, manage);
      });
      if (!items.length && !group.querySelector(".fav-empty")) {
        var e = document.createElement("div");
        e.className = "fav-empty";
        e.textContent = "Star any page with \u2605";
        group.insertBefore(e, manage);
      }
    }
    var menu = document.getElementById("more-menu");
    if (menu) {
      var oldM = menu.querySelectorAll(".fav-more-item");
      for (var j = 0; j < oldM.length; j++) oldM[j].remove();
      var content = menu.querySelector(".more-menu-content");
      var manageM = content ? content.querySelector(".fav-more-manage") : null;
      if (content) {
        items.slice().reverse().forEach(function (f) {
          var a = document.createElement("a");
          a.href = f.url;
          a.className = "more-menu-item fav-more-item";
          a.textContent = f.name;
          content.insertBefore(a, manageM);
        });
      }
    }
    setStars();
    markActive();
  }

  function expandFavGroup() {
    // The group collapses via the section header (a click next to the ★) and
    // sidebar_collapse.js remembers that in localStorage — so a page can load
    // with existing favorites hidden inside a max-height:0 container. Click
    // the header rather than writing localStorage directly, so that script's
    // in-memory copy stays in sync and doesn't re-collapse on its next toggle.
    // Skips an empty group: an intentionally collapsed empty section stays so.
    var group = document.getElementById("fav-group");
    if (!group || !group.classList.contains("collapsed")) return;
    if (!group.querySelector(".fav-item[data-url]")) return;
    var header = document.querySelector('.sidebar-section[data-section="favorites"]');
    if (header && header.classList.contains("collapsed")) {
      header.click();
    } else {
      group.classList.remove("collapsed");
      if (header) header.classList.remove("collapsed");
    }
  }

  function post(path, body) {
    return fetch(path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body)
    }).then(function (r) {
      return r.json().catch(function () {
        throw new Error("server returned " + r.status);
      });
    });
  }

  function fail(e) {
    var msg = e && e.message ? e.message : e;
    console.error("favorites:", msg);
    alert("Couldn't update favorites: " + msg);
  }

  function toggleFav() {
    var url = currentUrl();
    if (isFav(url)) {
      post("/api/favorites/remove", { url: url }).then(function (res) {
        if (!res || !res.ok) throw new Error((res && res.error) || "failed");
        patchList(res.favorites);
      }).catch(fail);
    } else {
      var name = prompt("Name for this favorite:", defaultName());
      if (name === null) return; // cancelled
      name = name.trim();
      if (!name) return;
      post("/api/favorites/add", { name: name, url: url }).then(function (res) {
        if (!res || !res.ok) throw new Error((res && res.error) || "failed");
        patchList(res.favorites);
        expandFavGroup();
      }).catch(fail);
    }
  }

  window.toggleFav = toggleFav;

  setStars();
  markActive();
  expandFavGroup();
  window.addEventListener("pageshow", setStars);
})();
