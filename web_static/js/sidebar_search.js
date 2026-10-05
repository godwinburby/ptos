
    setTimeout(function() {
      var el = document.getElementById("sidebar-search");
      if (el && typeof attachBracketAutocomplete === "function") {
        attachBracketAutocomplete(el);
      }
    }, 0);
