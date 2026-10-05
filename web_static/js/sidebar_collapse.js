
(function() {
  var KEY = 'sidebar-collapsed';
  var sections = document.querySelectorAll('.sidebar-section[data-section]');
  var groups = document.querySelectorAll('.sidebar-nav-group[data-group]');
  var saved = {};
  try { saved = JSON.parse(localStorage.getItem(KEY)) || {}; } catch(e) {}
  groups.forEach(function(g) {
    var name = g.getAttribute('data-group');
    var header = document.querySelector('.sidebar-section[data-section="' + name + '"]');
    if (saved[name]) {
      g.classList.add('collapsed');
      if (header) header.classList.add('collapsed');
    }
    if (header) {
      header.addEventListener('click', function() {
        var isCollapsed = g.classList.toggle('collapsed');
        header.classList.toggle('collapsed', isCollapsed);
        saved[name] = isCollapsed;
        try { localStorage.setItem(KEY, JSON.stringify(saved)); } catch(e) {}
      });
    }
  });
  var active = document.querySelector('.sidebar-nav a.active');
  if (active) {
    var group = active.closest('.sidebar-nav-group');
    if (group && group.classList.contains('collapsed')) {
      group.classList.remove('collapsed');
      var sec = document.querySelector('.sidebar-section[data-section="' + group.getAttribute('data-group') + '"]');
      if (sec) sec.classList.remove('collapsed');
      saved[group.getAttribute('data-group')] = false;
      try { localStorage.setItem(KEY, JSON.stringify(saved)); } catch(e) {}
    }
  }
})();
