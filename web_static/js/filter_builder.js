// ══════════════════════════════════════════════════════════════════════════════
// FilterBuilder  v1.0
// Shared chip + boolean-expression filter component.
// Used by:  browse.html,  query_builder.html
//
//   var fb = new FilterBuilder({
//     containerId : "my-div",        // required — renders into this element
//     types       : ["expense",...], // record type list
//     onRun       : function(expr){} // called (debounced 350ms) when filter changes
//   });
//
//   fb.setExpr("type=expense AND domain=self"); // load existing expression
//   fb.getExpr();   // current expression string
//   fb.clear();     // reset everything
// ══════════════════════════════════════════════════════════════════════════════
(function(global) {
  "use strict";
  var _reg = {};

  function esc(s) {
    return String(s == null ? "" : s)
      .replace(/&/g,"&amp;").replace(/</g,"&lt;")
      .replace(/>/g,"&gt;").replace(/"/g,"&quot;").replace(/'/g,"&#39;");
  }

  function FilterBuilder(opts) {
    var self     = this;
    self._opts   = opts || {};
    self._types  = opts.types || [];
    self._chips  = [];
    self._type   = null;
    self._active = null;
    self._cache  = {};
    self._lru    = [];
    self._timer  = null;

    var rawId = (opts.containerId || ("fb_" + Math.random().toString(36).slice(2)));
    self._id  = rawId.replace(/[^a-zA-Z0-9]/g, "_");
    _reg[self._id] = self;

    self.$ = function(suffix) {
      return document.getElementById("fb_" + self._id + "_" + suffix);
    };

    // ── Render ─────────────────────────────────────────────────────────────────
    self.init = function() {
      var c = document.getElementById(opts.containerId);
      if (!c) return;
      var id = self._id;
      c.innerHTML =
        '<div style="margin-bottom:10px;">' +
          '<div style="font-size:11px;color:var(--sub);font-weight:600;margin-bottom:6px;">TYPE</div>' +
          '<div id="fb_'+id+'_type_row" class="chip-group"></div>' +
        '</div>' +
        '<div id="fb_'+id+'_active_wrap" style="display:none;margin-bottom:10px;">' +
          '<div style="font-size:11px;color:var(--sub);font-weight:600;margin-bottom:6px;">ACTIVE FILTERS</div>' +
          '<div id="fb_'+id+'_active_list" class="chip-group"></div>' +
        '</div>' +
        '<div id="fb_'+id+'_field_wrap" style="display:none;margin-bottom:8px;">' +
          '<div style="font-size:11px;color:var(--sub);font-weight:600;margin-bottom:6px;">FIELDS</div>' +
          '<div id="fb_'+id+'_field_row" class="chip-group"></div>' +
        '</div>' +
        '<div id="fb_'+id+'_val_wrap" style="display:none;padding:10px;background:var(--bg);border-radius:8px;border:1px solid var(--border);margin-bottom:10px;">' +
          '<div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:8px;">' +
            '<div style="font-size:11px;color:var(--sub);font-weight:600;">VALUES FOR <span id="fb_'+id+'_val_label" style="color:var(--accent);"></span></div>' +
            '<button onclick="FilterBuilder._get(\''+id+'\').closeValueRow()" style="background:none;border:none;font-size:16px;color:var(--sub);cursor:pointer;">&#x2715;</button>' +
          '</div>' +
          '<div id="fb_'+id+'_val_chips" class="chip-group" style="margin-bottom:6px;"></div>' +
          '<div id="fb_'+id+'_val_hist_lbl" style="display:none;font-size:11px;color:var(--sub);margin:8px 0 4px;">from history:</div>' +
          '<div id="fb_'+id+'_val_hist" class="chip-group" style="opacity:0.65;margin-bottom:4px;"></div>' +
          '<div id="fb_'+id+'_val_text_row" style="display:none;gap:8px;margin-top:8px;">' +
            '<input type="text" id="fb_'+id+'_val_input" placeholder="type a value\u2026"' +
              ' style="flex:1;padding:8px 12px;border-radius:8px;border:1px solid var(--border);background:var(--card);color:var(--text);font-size:14px;"' +
              ' onkeydown="if(event.key===\'Enter\')FilterBuilder._get(\''+id+'\').addTextValue()">' +
            '<button onclick="FilterBuilder._get(\''+id+'\').addTextValue()"' +
              ' style="padding:8px 16px;border-radius:8px;border:none;background:var(--accent);color:#fff;font-size:14px;font-weight:600;cursor:pointer;margin-top:6px;">Add</button>' +
          '</div>' +
        '</div>' +
        '<div id="fb_'+id+'_tags_wrap" style="display:none;margin-bottom:10px;">' +
          '<div style="font-size:11px;color:var(--sub);font-weight:600;margin-bottom:6px;">TAGS</div>' +
          '<div id="fb_'+id+'_tag_chips" class="chip-group"></div>' +
          '<div id="fb_'+id+'_tag_hist_lbl" style="display:none;font-size:11px;color:var(--sub);margin:8px 0 4px;">from history:</div>' +
          '<div id="fb_'+id+'_tag_hist" class="chip-group"></div>' +
        '</div>' +
        '<div>' +
          '<div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:6px;">' +
            '<div style="font-size:11px;color:var(--sub);font-weight:600;">WHERE</div>' +
            '<span style="font-size:11px;color:var(--sub);">= != &gt; &lt; &gt;= &lt;= ~contains &nbsp;&middot;&nbsp; AND OR NOT ( )</span>' +
          '</div>' +
          '<textarea id="fb_'+id+'_expr" rows="2"' +
            ' style="width:100%;font-family:monospace;font-size:13px;padding:10px;border-radius:8px;border:1.5px solid var(--border);background:var(--bg);color:var(--text);resize:vertical;outline:none;transition:border-color .15s;"' +
            ' placeholder="e.g. type=followup AND (intent=trial OR intent=decision) AND NOT result=deceased"' +
            ' oninput="FilterBuilder._get(\''+id+'\')._onExprInput()"' +
            ' onfocus="this.style.borderColor=\'var(--accent)\'"' +
            ' onblur="this.style.borderColor=\'var(--border)\'"></textarea>' +
          '<div id="fb_'+id+'_expr_err" style="display:none;font-size:11px;color:var(--error);margin-top:4px;"></div>' +
        '</div>';

      self._renderTypeRow();
    };

    // ── Type chips ─────────────────────────────────────────────────────────────
    self._renderTypeRow = function() {
      var el = self.$("type_row"); if (!el) return;
      el.innerHTML = "";
      var all = document.createElement("button");
      all.className = "qb-chip" + (!self._type ? " active" : "");
      all.textContent = "all types";
      all.onclick = function() { self._onTypeClick(null); };
      el.appendChild(all);
      self._types.forEach(function(t) {
        var b = document.createElement("button");
        b.className = "qb-chip" + (t === self._type ? " active" : "");
        b.textContent = t;
        b.onclick = function() { self._onTypeClick(t); };
        el.appendChild(b);
      });
    };

    self._onTypeClick = function(t) {
      self._chips = self._chips.filter(function(c) { return c.field !== "type"; });
      if (t) self._chips.unshift({ field: "type", op: "=", value: t });
      self._type   = t;
      self._active = null;
      self._renderTypeRow();
      self._syncExprFromChips();
      var fw = self.$("field_wrap"); if (fw) fw.style.display = t ? "block" : "none";
      var vw = self.$("val_wrap");   if (vw) vw.style.display = "none";
      var tw = self.$("tags_wrap");  if (tw) tw.style.display = "none";
      self._renderActiveChips();
      if (t) self._fetch(function() { self._renderFieldRow(); self._renderTagsSection(); });
      self._scheduleRun();
    };

    // ── API fetch ──────────────────────────────────────────────────────────────
    self._ctxStr = function() {
      // For cache key — field=value pairs joined by &
      var out = {};
      self._chips.forEach(function(c) { if (c.field !== "type") out[c.field] = c.value; });
      return Object.keys(out).sort().map(function(k) { return k+"="+out[k]; }).join("&");
    };
    self._key = function() { return (self._type||"") + "?" + self._ctxStr(); };

    self._fetch = function(cb) {
      if (!self._type) { cb && cb({}); return; }
      var k = self._key();
      if (self._cache[k]) {
        cb && cb(self._cache[k]);
        if(self._opts.onTypeFields)self._opts.onTypeFields(self._type,self._cache[k]);
        return;
      }
      if (self._lru.length >= 20) delete self._cache[self._lru.shift()];
      var url = "/api/type_fields/" + encodeURIComponent(self._type);
      // API expects context as ?context=field:value,field:value
      var out = {};
      self._chips.forEach(function(c) { if (c.field !== "type") out[c.field] = c.value; });
      var pairs = Object.keys(out).sort().map(function(k) { return k+":"+out[k]; });
      if (pairs.length) url += "?context=" + encodeURIComponent(pairs.join(","));
      fetch(url)
        .then(function(r) { return r.json(); })
        .then(function(data) {
          var e = {
            fields:      (data.fields||[]).filter(function(f){return !f.is_int && f.name!=="type";}),
            dimensions:  data.dimensions||[],
            history:     data.history_fields||{},
            historyTags: data.history_tags||[]
          };
          self._cache[k]=e; self._lru.push(k); cb&&cb(e);
          if(self._opts.onTypeFields)self._opts.onTypeFields(self._type,e);
        })
        .catch(function() {
          var e={fields:[],dimensions:[],history:{},historyTags:[]};
          self._cache[k]=e; self._lru.push(k); cb&&cb(e);
          if(self._opts.onTypeFields)self._opts.onTypeFields(self._type,e);
        });
    };

    // ── Field chips ────────────────────────────────────────────────────────────
    self._renderFieldRow = function() {
      var el = self.$("field_row"); if (!el) return;
      el.innerHTML = "";
      var entry = self._cache[self._key()]||{};
      var ctx = {}; self._chips.forEach(function(c){if(c.field!=="type")ctx[c.field]=c.value;});
      (entry.fields||[]).filter(function(f){
        if(f.name==="tag")return false;
        return !f.has_parent || !!ctx[f.parent];
      }).forEach(function(f) {
        var isActive = self._active===f.name;
        var hasChip  = self._chips.some(function(c){return c.field===f.name;});
        var b = document.createElement("button");
        b.className = "qb-chip"+(isActive?" active":hasChip?" selected":"");
        b.textContent = f.name; b.title = f.name;
        b.onclick = function(){self._onFieldClick(f);};
        el.appendChild(b);
      });
    };

    self._onFieldClick = function(f) {
      if (self._active===f.name){self.closeValueRow();return;}
      self._active = f.name;
      self._renderFieldRow();
      var entry   = self._cache[self._key()]||{};
      var schema  = f.options||[];
      var hist    = (entry.history||{})[f.name]||[];
      var histExt = hist.filter(function(v){return schema.indexOf(v)===-1;}).slice(0,8);
      var lbl=self.$("val_label");   if(lbl)lbl.textContent=f.name;
      var vw =self.$("val_wrap");    if(vw) vw.style.display="block";
      var vc =self.$("val_chips");   if(vc) vc.innerHTML="";
      var vh =self.$("val_hist");    if(vh) vh.innerHTML="";
      var vhl=self.$("val_hist_lbl");
      var vtr=self.$("val_text_row");

      if (schema.length||histExt.length) {
        if(vtr)vtr.style.display="none";
        schema.forEach(function(opt){
          var act=self._chips.some(function(c){return c.field===f.name&&c.value===opt;});
          var b=document.createElement("button"); b.className="qb-chip"+(act?" active":"");
          b.textContent=opt;
          b.onclick=function(){self._toggleChip(f.name,"=",opt);b.className="qb-chip"+(self._chips.some(function(c){return c.field===f.name&&c.value===opt;})?" active":"");};
          if(vc)vc.appendChild(b);
        });
        if(histExt.length){
          if(vhl)vhl.style.display="block";
          histExt.forEach(function(v){
            var act=self._chips.some(function(c){return c.field===f.name&&c.value===v;});
            var b=document.createElement("button"); b.className="qb-chip"+(act?" active":"");
            b.style.opacity="0.75"; b.style.fontSize="12px"; b.textContent=v;
            b.onclick=function(){self._toggleChip(f.name,"=",v);b.className="qb-chip"+(self._chips.some(function(c){return c.field===f.name&&c.value===v;})?" active":"");};
            if(vh)vh.appendChild(b);
          });
        } else { if(vhl)vhl.style.display="none"; }
      } else if(hist.length) {
        if(vtr)vtr.style.display="none";
        hist.slice(0,8).forEach(function(v){
          var act=self._chips.some(function(c){return c.field===f.name&&c.value===v;});
          var b=document.createElement("button"); b.className="qb-chip"+(act?" active":"");
          b.textContent=v;
          b.onclick=function(){self._toggleChip(f.name,"=",v);self.closeValueRow();};
          if(vc)vc.appendChild(b);
        });
        if(vhl)vhl.style.display="none";
      } else {
        if(vtr)vtr.style.display="flex";
        if(vhl)vhl.style.display="none";
        setTimeout(function(){var vi=self.$("val_input");if(vi)vi.focus();},50);
      }
    };

    self.closeValueRow=function(){
      self._active=null;
      var vw=self.$("val_wrap");if(vw)vw.style.display="none";
      self._renderFieldRow();
    };

    self.addTextValue=function(){
      if(!self._active)return;
      var vi=self.$("val_input"); var val=vi?vi.value.trim():"";
      if(!val)return;
      self._toggleChip(self._active,"=",val);
      if(vi)vi.value=""; self.closeValueRow();
    };

    // ── Tags ───────────────────────────────────────────────────────────────────
    self._renderTagsSection=function(){
      var tw=self.$("tags_wrap"); if(!tw)return;
      var tc=self.$("tag_chips"); var th=self.$("tag_hist"); var thl=self.$("tag_hist_lbl");
      if(!self._type){tw.style.display="none";return;}
      var entry=self._cache[self._key()]||{};
      var tagFld=(entry.fields||[]).find(function(f){return f.name==="tag";});
      var schema=tagFld?(tagFld.options||[]):[];
      var histAll=entry.historyTags||[];
      var histExt=histAll.filter(function(t){return schema.indexOf(t)===-1;});
      if(!schema.length&&!histExt.length){tw.style.display="none";return;}
      tw.style.display="block";
      if(tc)tc.innerHTML=""; if(th)th.innerHTML="";
      schema.forEach(function(tag){
        var act=self._chips.some(function(c){return c.field==="tag"&&c.value===tag;});
        var b=document.createElement("button"); b.className="qb-chip"+(act?" active":"");
        b.textContent=tag;
        b.onclick=function(){self._toggleChip("tag","=",tag);b.className="qb-chip"+(self._chips.some(function(c){return c.field==="tag"&&c.value===tag;})?" active":"");};
        if(tc)tc.appendChild(b);
      });
      if(histExt.length){
        if(thl)thl.style.display="block";
        histExt.forEach(function(tag){
          var act=self._chips.some(function(c){return c.field==="tag"&&c.value===tag;});
          var b=document.createElement("button"); b.className="qb-chip"+(act?" active":"");
          b.style.opacity="0.75"; b.style.fontSize="12px"; b.textContent=tag;
          b.onclick=function(){self._toggleChip("tag","=",tag);b.className="qb-chip"+(self._chips.some(function(c){return c.field==="tag"&&c.value===tag;})?" active":"");};
          if(th)th.appendChild(b);
        });
      } else {if(thl)thl.style.display="none";}
    };

    // ── Active chips ───────────────────────────────────────────────────────────
    self._renderActiveChips=function(){
      var wrap=self.$("active_wrap"); var list=self.$("active_list");
      if(!wrap||!list)return;
      var nonType=self._chips.filter(function(c){return c.field!=="type";});
      if(!nonType.length){wrap.style.display="none";return;}
      wrap.style.display="block"; list.innerHTML="";
      nonType.forEach(function(c,i){
        var span=document.createElement("span"); span.className="qb-active-chip";
        span.innerHTML=esc(c.field+c.op+c.value)+
          ' <button onclick="FilterBuilder._get(\''+self._id+'\')._rmByIdx('+i+')"'+
          ' style="background:none;border:none;cursor:pointer;color:var(--sub);">&times;</button>';
        list.appendChild(span);
      });
    };

    self._rmByIdx=function(visIdx){
      var nonType=self._chips.filter(function(c){return c.field!=="type";});
      var t=nonType[visIdx]; if(!t)return;
      self._chips=self._chips.filter(function(c){
        return!(c.field===t.field&&c.value===t.value&&c.op===t.op);
      });
      self._renderActiveChips(); self._syncExprFromChips(); self._renderTagsSection();
      if(t.field!=="type"){delete self._cache[self._key()];self._fetch(function(){self._renderFieldRow();self._renderTagsSection();});}
      self._scheduleRun();
    };

    // ── Chip toggle ────────────────────────────────────────────────────────────
    self._toggleChip=function(field,op,value){
      var idx=self._chips.findIndex(function(c){return c.field===field&&c.value===value;});
      if(idx!==-1)self._chips.splice(idx,1);
      else self._chips.push({field:field,op:op,value:value});
      self._renderActiveChips(); self._syncExprFromChips(); self._renderTagsSection();
      if(field!=="type"&&field!=="tag"){delete self._cache[self._key()];self._fetch(function(){self._renderFieldRow();self._renderTagsSection();});}
      self._scheduleRun();
    };

    // ── Chips → expr ───────────────────────────────────────────────────────────
    self._chipsToExpr=function(){
      if(!self._chips.length)return"";
      var byF={},ord=[];
      self._chips.forEach(function(c){if(!byF[c.field]){byF[c.field]=[];ord.push(c.field);}byF[c.field].push(c);});
      return ord.map(function(f){
        var g=byF[f];
        if(g.length===1)return g[0].field+g[0].op+g[0].value;
        return"("+g.map(function(c){return c.field+c.op+c.value;}).join(" OR ")+")";
      }).join(" AND ");
    };

    self._syncExprFromChips=function(){
      var el=self.$("expr"); if(!el||document.activeElement===el)return;
      el.value=self._chipsToExpr();
    };

    // ── Live expr input ────────────────────────────────────────────────────────
    self._onExprInput=function(){
      clearTimeout(self._timer);
      self._timer=setTimeout(function(){
        var el=self.$("expr"); var expr=el?el.value.trim():"";
        var parsed=self._parseExpr(expr);
        if(parsed!==null){
          self._chips=parsed;
          var tc=self._chips.find(function(c){return c.field==="type";});
          var newType=tc?tc.value:null;
          if(newType!==self._type){
            self._type=newType; self._renderTypeRow();
            var fw=self.$("field_wrap");if(fw)fw.style.display=newType?"block":"none";
            if(newType)self._fetch(function(){self._renderFieldRow();self._renderTagsSection();});
            else{var tw=self.$("tags_wrap");if(tw)tw.style.display="none";}
          }
          self._renderActiveChips(); self._renderFieldRow(); self._renderTagsSection();
        }
        var ee=self.$("expr_err");if(ee)ee.style.display="none";
        self._scheduleRun();
      },400);
    };

    // ── Expression parser ──────────────────────────────────────────────────────
    self._parseExpr=function(expr){
      expr=(expr||"").trim().replace(/^where\s*=\s*["']?/i,"").replace(/["']?\s*$/i,"").trim();
      if(!expr)return[];
      var chips=[];
      var andP=self._splitTop(expr,"AND");
      for(var i=0;i<andP.length;i++){
        var part=andP[i].trim();if(!part)continue;
        if(/^\s*NOT\s+/i.test(part))return null;
        var inner=self._unwrap(part);
        if(inner!==null){
          var orP=self._splitTop(inner,"OR");
          for(var j=0;j<orP.length;j++){var c=self._sc(orP[j].trim());if(!c)return null;chips.push(c);}
        } else {var c=self._sc(part);if(!c)return null;chips.push(c);}
      }
      return chips;
    };
    self._sc=function(s){var m=(s||"").match(/^(\w+)\s*(!~|!=|>=|<=|~|=|>|<)\s*(.+)$/);if(!m)return null;return{field:m[1].toLowerCase(),op:m[2],value:m[3].trim().replace(/^["']|["']$/g,"")};};
    self._splitTop=function(expr,op){var parts=[],depth=0,cur="",i=0;while(i<expr.length){if(expr[i]==="("){depth++;cur+=expr[i++];}else if(expr[i]===")"){depth--;cur+=expr[i++];}else{var rest=expr.slice(i);var m=rest.match(new RegExp("^\\s+"+op+"\\s+","i"));if(m&&depth===0){parts.push(cur);cur="";i+=m[0].length;}else{cur+=expr[i++];}}}if(cur.trim())parts.push(cur);return parts;};
    self._unwrap=function(s){s=(s||"").trim();if(s[0]!=="("||s[s.length-1]!==")")return null;var inner=s.slice(1,-1),depth=0;for(var i=0;i<inner.length;i++){if(inner[i]==="(")depth++;if(inner[i]===")")depth--;if(depth<0)return null;}return inner;};

    // ── Public API ─────────────────────────────────────────────────────────────
    self.getExpr=function(){var el=self.$("expr");return el?el.value.trim():self._chipsToExpr();};
    self.setExpr=function(expr){
      var el=self.$("expr");if(el)el.value=expr||"";
      if(!expr)return;
      var parsed=self._parseExpr(expr);
      if(parsed!==null){
        self._chips=parsed;
        var tc=self._chips.find(function(c){return c.field==="type";});
        self._type=tc?tc.value:null;
        self._renderTypeRow();
        var fw=self.$("field_wrap");if(fw)fw.style.display=self._type?"block":"none";
        self._renderActiveChips();
        if(self._type)self._fetch(function(){self._renderFieldRow();self._renderTagsSection();});
      }
    };
    self.setTypes=function(types){self._types=types||[];self._renderTypeRow();};
    self.getChips=function(){return self._chips.slice();};
    self.clear=function(){
      self._chips=[];self._type=null;self._active=null;
      var el=self.$("expr");if(el)el.value="";
      var fw=self.$("field_wrap");if(fw)fw.style.display="none";
      var vw=self.$("val_wrap");if(vw)vw.style.display="none";
      var tw=self.$("tags_wrap");if(tw)tw.style.display="none";
      self._renderTypeRow();self._renderActiveChips();
    };
    self._scheduleRun=function(){
      if(!self._opts.onRun)return;
      clearTimeout(self._timer);
      self._timer=setTimeout(function(){self._opts.onRun(self.getExpr());},350);
    };
  }

  FilterBuilder._get=function(id){return _reg[id];};
  global.FilterBuilder=FilterBuilder;
})(window);
