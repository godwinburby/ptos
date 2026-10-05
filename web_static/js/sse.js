
// ── SSE listener — shutdown overlay + todo notifications ──
function _showTodoToast(tasks) {
  var old = document.getElementById("todo-toast");
  if (old) old.remove();
  var n = tasks.length;
  var arrivedTask = tasks.find(function(t){ return t.arrived; });
  var label;
  if (n === 1) {
    label = tasks[0].description;
  } else if (arrivedTask) {
    var extra = n - 1;
    label = arrivedTask.description + (extra ? " — plus " + extra + " more due today" : "");
  } else {
    label = n + " tasks due";
  }
  var d = document.createElement("div");
  d.id = "todo-toast";
  d.style.cssText = "position:fixed;top:12px;right:12px;z-index:9998;background:var(--error);color:#fff;padding:12px 18px;border-radius:10px;font-size:14px;cursor:pointer;box-shadow:0 4px 12px rgba(0,0,0,.2);max-width:320px;";
  d.innerHTML = "\uD83D\uDCCC " + label + ' <span style="margin-left:8px;opacity:.7;font-size:12px;">\u2715</span>';
  d.onclick = function() { window.location = "/todo"; };
  d.querySelector("span").onclick = function(e) { e.stopPropagation(); d.remove(); };
  document.body.appendChild(d);
  setTimeout(function() { if (d.parentNode) d.remove(); }, 15000);
}
(function(){
  try {
    var es = new EventSource("/api/events");
    es.onmessage = function(e) {
      try {
        var msg = JSON.parse(e.data);
        if (msg.type === "shutdown") {
          es.close();
          var d = document.createElement("div");
          d.id = "sse-shutdown-overlay";
          d.style.cssText = "position:fixed;inset:0;z-index:9999;display:flex;align-items:center;justify-content:center;flex-direction:column;background:#1a1a1a;color:#fff;font-family:system-ui,sans-serif;";
          d.innerHTML = "<h1 style='font-size:32px;margin-bottom:12px;'>Server stopped</h1><p style='font-size:18px;opacity:.7;'>You can close this tab.</p>";
          document.body.appendChild(d);
        }
        if (msg.type === "todo-due") {
          var tasks = msg.data;
          if ("Notification" in window && Notification.permission === "default") {
            Notification.requestPermission();
          }
          if ("Notification" in window && Notification.permission === "granted") {
            var body = tasks.map(function(t) {
              var p = t.priority ? "(" + t.priority + ") " : "";
              var time = t.due_time ? " at " + t.due_time : "";
              return p + t.description + " (due " + t.due + time + ")";
            }).join("\n");
            new Notification("Todo due", {body: body, icon: "/static/icon-192.png"});
          }
          _showTodoToast(tasks);
        }
        if (msg.type === "todo-reminder") {
          var tasks = msg.data;
          if ("Notification" in window && Notification.permission === "default") {
            Notification.requestPermission();
          }
          if ("Notification" in window && Notification.permission === "granted") {
            var t = tasks[0];
            var p = t.priority ? "(" + t.priority + ") " : "";
            var body = p + t.description + " (due in ~" + t.mins_until + " min, " + t.due + " " + t.due_time + ")";
            new Notification("Todo due soon", {body: body, icon: "/static/icon-192.png"});
          }
          _showTodoToast(tasks);
        }
      } catch(ex) {}
    };
  } catch(ex) {}
})();
