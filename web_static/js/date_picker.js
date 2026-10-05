
(function(){
  var _dtpYear, _dtpMonth, _dtpDate, _dtpCallback;
  var MONTHS = ['January','February','March','April','May','June','July','August','September','October','November','December'];
  var MINUTE_STEP = 5;

  function to24(h12, ampm) {
    var h = parseInt(h12, 10);
    if (ampm === 'AM') return h === 12 ? '00' : String(h).padStart(2, '0');
    return h === 12 ? '12' : String(h + 12).padStart(2, '0');
  }

  function from24(hh) {
    var h = parseInt(hh, 10);
    if (h === 0) return {h12: '12', ap: 'AM'};
    if (h < 12) return {h12: String(h), ap: 'AM'};
    if (h === 12) return {h12: '12', ap: 'PM'};
    return {h12: String(h - 12), ap: 'PM'};
  }

  function populateTimeSelects(hour12, minute, ampm) {
    var hourSel = document.getElementById('dtp-hour-select');
    var minSel = document.getElementById('dtp-min-select');
    var ampmSel = document.getElementById('dtp-ampm-select');
    hourSel.innerHTML = '';
    for (var h = 1; h <= 12; h++) {
      hourSel.innerHTML += '<option value="'+h+'">'+h+'</option>';
    }
    minSel.innerHTML = '';
    var minuteOnGrid = false;
    for (var m = 0; m < 60; m += MINUTE_STEP) {
      var mv = String(m).padStart(2, '0');
      if (mv === minute) minuteOnGrid = true;
      minSel.innerHTML += '<option value="'+mv+'">'+mv+'</option>';
    }
    if (minute && !minuteOnGrid) {
      minSel.innerHTML += '<option value="'+minute+'">'+minute+'</option>';
    }
    hourSel.value = hour12;
    minSel.value = minute;
    ampmSel.value = ampm;
  }

  function getTimeValue() {
    if (!document.getElementById('dtp-has-time').checked) return null;
    var h = document.getElementById('dtp-hour-select').value;
    var m = document.getElementById('dtp-min-select').value;
    var ap = document.getElementById('dtp-ampm-select').value;
    return to24(h, ap) + ':' + m;
  }

  function updateOK() {
    document.getElementById('dt-picker-ok').disabled = !_dtpDate;
  }

  function renderCalendar() {
    var title = document.getElementById('dt-picker-title');
    title.textContent = MONTHS[_dtpMonth] + ' ' + _dtpYear;
    var el = document.getElementById('dt-picker-days');
    var first = new Date(_dtpYear, _dtpMonth, 1);
    var startDay = (first.getDay() + 6) % 7;
    var daysInMonth = new Date(_dtpYear, _dtpMonth + 1, 0).getDate();
    var today = new Date();
    var html = '';
    for (var i = 0; i < startDay; i++) html += '<div class="dtp-day empty"></div>';
    for (var d = 1; d <= daysInMonth; d++) {
      var cls = 'dtp-day';
      if (_dtpDate && _dtpYear === _dtpDate.y && _dtpMonth === _dtpDate.m && d === _dtpDate.d) cls += ' selected';
      if (today.getFullYear() === _dtpYear && today.getMonth() === _dtpMonth && today.getDate() === d) cls += ' today';
      html += '<div class="'+cls+'" onclick="selectDTPDay('+d+')">'+d+'</div>';
    }
    el.innerHTML = html;
  }

  window.dtpNavMonth = function(dir) {
    _dtpMonth += dir;
    if (_dtpMonth > 11) { _dtpMonth = 0; _dtpYear++; }
    if (_dtpMonth < 0) { _dtpMonth = 11; _dtpYear--; }
    renderCalendar();
  };

  window.selectDTPDay = function(d) {
    _dtpDate = {y:_dtpYear, m:_dtpMonth, d:d};
    renderCalendar();
    updateOK();
  };

  window.dtpToggleTime = function() {
    var on = document.getElementById('dtp-has-time').checked;
    var wrap = document.getElementById('dtp-time-selects');
    if (on) {
      wrap.classList.add('open');
      populateTimeSelects(
        document.getElementById('dtp-hour-select').value || '9',
        document.getElementById('dtp-min-select').value || '00',
        document.getElementById('dtp-ampm-select').value || 'AM'
      );
    } else {
      wrap.classList.remove('open');
    }
  };

  window.openDTPicker = function(opts) {
    _dtpCallback = opts.callback;
    var now = new Date();
    var hasTime = false;
    var h12 = '9', mm = '00', ap = 'AM';
    if (opts.value) {
      var parts = opts.value.split('T');
      var dp = parts[0].split('-');
      _dtpDate = {y:+dp[0], m:+dp[1]-1, d:+dp[2]};
      if (parts[1]) {
        var tp = parts[1].split(':');
        var f = from24(tp[0]);
        h12 = f.h12; ap = f.ap; mm = tp[1] || '00';
        hasTime = true;
      }
    } else {
      _dtpDate = {y:now.getFullYear(), m:now.getMonth(), d:now.getDate()};
    }
    _dtpYear = _dtpDate.y;
    _dtpMonth = _dtpDate.m;
    renderCalendar();

    var hourSel = document.getElementById('dtp-hour-select');
    var minSel = document.getElementById('dtp-min-select');
    hourSel.innerHTML = '';
    for (var h = 1; h <= 12; h++) hourSel.innerHTML += '<option value="'+h+'">'+h+'</option>';
    minSel.innerHTML = '';
    for (var m = 0; m < 60; m += MINUTE_STEP) {
      var mv = String(m).padStart(2,'0');
      minSel.innerHTML += '<option value="'+mv+'">'+mv+'</option>';
    }

    populateTimeSelects(hasTime ? h12 : '9', hasTime ? mm : '00', hasTime ? ap : 'AM');
    var cb = document.getElementById('dtp-has-time');
    cb.checked = hasTime;
    var wrap = document.getElementById('dtp-time-selects');
    if (hasTime) wrap.classList.add('open');
    else wrap.classList.remove('open');

    updateOK();
    var picker = document.getElementById('dt-picker');
    picker.style.top = '50%';
    picker.style.left = '50%';
    picker.style.transform = 'translate(-50%, -50%)';
    document.getElementById('dt-picker-overlay').classList.add('open');
  };

  window.closeDTPicker = function() {
    document.getElementById('dt-picker-overlay').classList.remove('open');
    _dtpCallback = null;
  };

  window.confirmDTPicker = function() {
    if (!_dtpDate) return;
    var dateStr = _dtpDate.y + '-' + String(_dtpDate.m+1).padStart(2,'0') + '-' + String(_dtpDate.d).padStart(2,'0');
    var result = dateStr;
    var timeVal = getTimeValue();
    if (timeVal) result = dateStr + 'T' + timeVal;
    var cb = _dtpCallback;
    closeDTPicker();
    if (cb) cb(result);
  };
})();
