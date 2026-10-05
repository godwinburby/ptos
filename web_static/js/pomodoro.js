
(function(){
  var _pomoKey = 'ptos_pomodoro';
  var _pomoInterval = null;
  var _pomoExpanded = false;

  function _pomoState() {
    try { return JSON.parse(localStorage.getItem(_pomoKey)); } catch(e) { return null; }
  }

  function _savePomo(s) {
    localStorage.setItem(_pomoKey, JSON.stringify(s));
  }

  function _clearPomo() {
    localStorage.removeItem(_pomoKey);
    if (_pomoInterval) { clearInterval(_pomoInterval); _pomoInterval = null; }
  }

  function _fmtPomo(sec) {
    var m = Math.floor(sec / 60);
    var s = sec % 60;
    return String(m).padStart(2,'0') + ':' + String(s).padStart(2,'0');
  }

  function _showPill(show) {
    var pill = document.getElementById('pomo-pill');
    if (pill) pill.classList.toggle('active', show);
  }

  function _updateRowPomoIndicators() {
    var s = _pomoState();
    document.querySelectorAll('.todo-row').forEach(function(r) {
      r.classList.remove('pomo-active', 'pomo-running', 'pomo-paused');
      var btn = r.querySelector('.pomo-row-btn');
      if (btn) btn.textContent = '\u25B6';
    });
    if (s && !s.done) {
      var row = document.querySelector('.todo-row[data-line="'+s.lineNo+'"]');
      if (row) {
        row.classList.add('pomo-active');
        row.classList.add(s.paused ? 'pomo-paused' : 'pomo-running');
        var btn = row.querySelector('.pomo-row-btn');
        if (btn) btn.textContent = s.paused ? '\u25B6' : '\u23F8';
      }
    }
  }

  function _updatePill() {
    _updateRowPomoIndicators();
    var s = _pomoState();
    if (!s || s.done) { _showPill(false); return; }
    var pill = document.getElementById('pomo-pill');
    var taskEl = document.getElementById('pomo-task-name');
    var timeEl = document.getElementById('pomo-time');
    var iconBtn = document.getElementById('pomo-icon-btn');
    if (!pill || !taskEl || !timeEl || !iconBtn) return;
    taskEl.textContent = s.desc || 'Pomodoro';
    if (s.paused) {
      var remain = s.pausedRemain;
      timeEl.textContent = _fmtPomo(Math.max(0, remain));
      pill.className = 'pomo-pill active paused' + (_pomoExpanded ? ' expanded' : '');
      iconBtn.textContent = '▶';
    } else {
      var remain = Math.round((s.endTime - Date.now()) / 1000);
      if (remain <= 0) { _completePomo(); return; }
      timeEl.textContent = _fmtPomo(remain);
      pill.className = 'pomo-pill active running' + (_pomoExpanded ? ' expanded' : '');
      iconBtn.textContent = '⏸';
    }
    _showPill(true);
  }

  function _tickPomo() {
    var s = _pomoState();
    if (!s || s.paused || s.done) return;
    var remain = Math.round((s.endTime - Date.now()) / 1000);
    if (remain <= 0) { _completePomo(); }
    else { _updatePill(); }
  }

  function _completePomo() {
    var s = _pomoState();
    var desc = s ? s.desc : 'Pomodoro';
    var mins = s && s.minutes ? s.minutes : window.PTOS.pomoMinutes;
    _clearPomo();
    _updatePill();
    if ("Notification" in window && Notification.permission === "default") {
      Notification.requestPermission();
    }
    if ("Notification" in window && Notification.permission === "granted") {
      new Notification("Pomodoro complete!", {body: desc, icon: "/static/icon-192.png"});
    }
    _showTodoToast([{description: "\u23F0 " + desc + " \u2014 pomodoro complete!", due: "now", arrived: true}]);
    if (window.PTOS.pomoLog) {
    try {
      fetch('/api/pomo-log', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({task: desc, minutes: mins})
      });
    } catch (e) {}
    }
  }

  window.startPomo = function(lineNo, desc, minutes) {
    var dur = (minutes || window.PTOS.pomoMinutes) * 60 * 1000;
    var s = {lineNo: lineNo, desc: desc, minutes: (minutes || window.PTOS.pomoMinutes), endTime: Date.now() + dur, paused: false, pausedRemain: 0, done: false};
    _savePomo(s);
    if (_pomoInterval) clearInterval(_pomoInterval);
    _pomoInterval = setInterval(_tickPomo, 1000);
    _updatePill();
  };

  window.startPomodoro = function(lineNo, desc) {
    startPomo(lineNo, desc);
  };

  window.pomoIconAction = function(e) {
    e.stopPropagation();
    var s = _pomoState();
    if (!s || s.done) return;
    if (s.paused) {
      s.endTime = Date.now() + s.pausedRemain * 1000;
      s.paused = false;
      _savePomo(s);
      if (!_pomoInterval) _pomoInterval = setInterval(_tickPomo, 1000);
    } else {
      s.pausedRemain = Math.round((s.endTime - Date.now()) / 1000);
      s.paused = true;
      _savePomo(s);
    }
    _updatePill();
  };

  window.stopPomo = function() {
    _clearPomo();
    _updatePill();
  };

  window.todoPomoAction = function(btn, desc) {
    var lineNo = parseInt(btn.dataset.line);
    var s = _pomoState();
    if (s && s.lineNo === lineNo && !s.done) {
      if (s.paused) {
        s.endTime = Date.now() + s.pausedRemain * 1000;
        s.paused = false;
        _savePomo(s);
        if (!_pomoInterval) { _pomoInterval = setInterval(_tickPomo, 1000); }
      } else {
        s.pausedRemain = Math.round((s.endTime - Date.now()) / 1000);
        s.paused = true;
        _savePomo(s);
      }
      _updatePill();
    } else {
      startPomo(lineNo, desc);
    }
  };

  window.todoPomoStop = function() {
    _clearPomo();
    _updatePill();
  };

  window.togglePomoExpand = function(e) {
    if (e.target.closest('.pomo-ctrl-btn') || e.target.closest('.pomo-icon')) return;
    _pomoExpanded = !_pomoExpanded;
    var pill = document.getElementById('pomo-pill');
    if (pill) pill.classList.toggle('expanded', _pomoExpanded);
  };

  // Resume on page load
  (function(){
    var s = _pomoState();
    if (s && !s.done) {
      if (!s.paused) {
        var remain = Math.round((s.endTime - Date.now()) / 1000);
        if (remain <= 0) { _completePomo(); return; }
        _pomoInterval = setInterval(_tickPomo, 1000);
      }
      _updatePill();
    }
  })();
})();
