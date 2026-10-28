(function () {
  "use strict";

  function updateBody(body, changes) {
    var keys = Object.keys(changes || {});
    var lines = String(body || "").split(/\r?\n/).filter(function (line) {
      return !keys.some(function (key) {
        return new RegExp("^\\s*" + key + "\\s*=").test(line);
      });
    });
    keys.forEach(function (key) {
      var value = changes[key];
      if (value === "" && ["project", "context", "priority", "due", "search", "linked_to"].indexOf(key) >= 0) {
        lines.push(key + " = \"\"");
      } else if (value !== null && value !== undefined && value !== "") {
        lines.push(key + " = " + (typeof value === "boolean"
          ? String(value) : JSON.stringify(String(value))));
      }
    });
    return lines.filter(Boolean).join("\n");
  }

  window.PtosTodoController = { updateBody: updateBody };
})();
