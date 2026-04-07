"""
ptos_gui.py  —  Tkinter GUI front-end for PTOS
Place this file in the same folder as ptos.py.
Run:  python ptos_gui.py
"""

import sys
import os
import traceback
import datetime as dt
import webbrowser
import tkinter as tk
from tkinter import ttk, messagebox

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ptos
import ptos_service as svc
from ptos_service import PTOSError

# ── Palette ───────────────────────────────────────────────────────────────────
BG        = "#F7F8FA"   # page background
CARD      = "#FFFFFF"   # card / panel background
BORDER    = "#E2E4EA"   # separator / border
ACCENT    = "#4F6BED"   # primary blue
ACCENT_HO = "#3A54D4"   # hover
ACCENT_LT = "#EEF1FB"   # light accent (for chips)
SUCCESS   = "#2E7D56"   # saved message
ERROR_COL = "#C0392B"   # error message
TEXT      = "#1A1D2E"   # primary text
SUBTEXT   = "#6B7280"   # secondary labels
ENTRY_BG  = "#FFFFFF"
ENTRY_BD  = "#CBD0DC"
OUTPUT_BG = "#1E2130"   # dark output pane
OUTPUT_FG = "#D4D8E8"

# ── Fonts ─────────────────────────────────────────────────────────────────────
F_HEAD  = ("Segoe UI", 18, "bold")   # tab page title
F_SUBH  = ("Segoe UI", 13, "bold")   # section headings (unused but available)
F_LABEL = ("Segoe UI", 12)           # field labels, ctrl bar labels
F_BODY  = ("Segoe UI", 12)           # entries, combos, body text
F_SMALL = ("Segoe UI", 11)           # hint text (YYYY-MM-DD etc)
F_MONO  = ("Consolas", 12)           # output pane
F_BTN   = ("Segoe UI", 12, "bold")   # buttons

PAD  = 10
HPAD = 20

# ── Time windows ──────────────────────────────────────────────────────────────
TIME_LABELS = [
    ("Today",        "td"),
    ("Yesterday",    "yd"),
    ("This week",    "tw"),
    ("Last week",    "lw"),
    ("This month",   "tm"),
    ("Last month",   "lm"),
    ("This quarter", "tq"),
    ("Last quarter", "lq"),
    ("This year",    "ty"),
    ("Last year",    "ly"),
    ("All time",     "all"),
]
_TIME_CODE  = {label: code  for label, code  in TIME_LABELS}
_TIME_LABEL = {code:  label for label, code  in TIME_LABELS}


# ── Widget helpers ────────────────────────────────────────────────────────────

def _setup_ttk_styles():
    s = ttk.Style()
    s.theme_use("clam")

    # Notebook tabs
    s.configure("TNotebook",
                background=BG, borderwidth=0, tabmargins=0)
    s.configure("TNotebook.Tab",
                background=BORDER, foreground=SUBTEXT,
                font=F_BTN, padding=[20, 10], borderwidth=0)
    s.map("TNotebook.Tab",
          background=[("selected", CARD), ("active", "#EEF0F8")],
          foreground=[("selected", ACCENT)],
          font=[("selected", F_BTN)])

    # Combobox
    s.configure("TCombobox",
                fieldbackground=ENTRY_BG, background=ENTRY_BG,
                foreground=TEXT, arrowcolor=ACCENT,
                bordercolor=ENTRY_BD, lightcolor=ENTRY_BD,
                darkcolor=ENTRY_BD, selectbackground=ACCENT,
                selectforeground="white", font=F_BODY)
    s.map("TCombobox",
          fieldbackground=[("readonly", ENTRY_BG)],
          foreground=[("readonly", TEXT)])

    # Scrollbar
    s.configure("TScrollbar", background=BORDER, troughcolor=BG,
                arrowcolor=SUBTEXT, borderwidth=0)


def lbl(parent, text, font=F_LABEL, fg=TEXT, **kw):
    return tk.Label(parent, text=text, font=font, fg=fg,
                    bg=parent.cget("bg"), **kw)

def sublbl(parent, text, **kw):
    return lbl(parent, text, font=F_SMALL, fg=SUBTEXT, **kw)

def _make_entry(parent, textvariable=None, width=28):
    f = tk.Frame(parent, bg=ENTRY_BD, padx=1, pady=1)
    e = tk.Entry(f, textvariable=textvariable, width=width,
                 font=F_BODY, bg=ENTRY_BG, fg=TEXT,
                 insertbackground=TEXT, relief="flat",
                 highlightthickness=0)
    e.pack(fill="both", expand=True, ipady=5, ipadx=4)
    return f, e

def _make_combo(parent, values, textvariable=None, width=22):
    c = ttk.Combobox(parent, values=values, textvariable=textvariable,
                     width=width, state="readonly", font=F_BODY)
    return c

def _make_button(parent, text, command):
    b = tk.Button(parent, text=text, command=command,
                  font=F_BTN, bg=ACCENT, fg="white",
                  activebackground=ACCENT_HO, activeforeground="white",
                  relief="flat", cursor="hand2",
                  padx=20, pady=8, bd=0)
    return b

def hsep(parent):
    return tk.Frame(parent, bg=BORDER, height=1)


# ── Scrollable inner frame ────────────────────────────────────────────────────

class ScrollBody(tk.Frame):
    """A vertically-scrollable frame. Children pack into self."""
    def __init__(self, parent, bg=BG):
        container = tk.Frame(parent, bg=bg)
        container.pack(fill="both", expand=True)

        self._canvas = tk.Canvas(container, bg=bg, highlightthickness=0)
        vsb = ttk.Scrollbar(container, orient="vertical",
                             command=self._canvas.yview)
        self._canvas.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y")
        self._canvas.pack(side="left", fill="both", expand=True)

        super().__init__(self._canvas, bg=bg)
        self._win = self._canvas.create_window((0, 0), window=self, anchor="nw")

        self.bind("<Configure>",
                  lambda e: self._canvas.configure(
                      scrollregion=self._canvas.bbox("all")))
        self._canvas.bind("<Configure>",
                          lambda e: self._canvas.itemconfig(
                              self._win, width=e.width))
        self._canvas.bind_all("<MouseWheel>",
                              self._on_mousewheel)

    def _on_mousewheel(self, event):
        try:
            self._canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        except Exception:
            pass  # Widget may have been destroyed, ignore

    def reset(self):
        self._canvas.yview_moveto(0)


# ── Output pane (dark, monospace, both scrollbars) ────────────────────────────

def _make_output(parent):
    tf = tk.Frame(parent, bg=BORDER, padx=1, pady=1)
    xsb = ttk.Scrollbar(tf, orient="horizontal")
    ysb = ttk.Scrollbar(tf, orient="vertical")
    t = tk.Text(tf, font=F_MONO, bg=OUTPUT_BG, fg=OUTPUT_FG,
                insertbackground=OUTPUT_FG, relief="flat",
                state="disabled", wrap="none",
                xscrollcommand=xsb.set, yscrollcommand=ysb.set,
                padx=10, pady=8)
    xsb.config(command=t.xview)
    ysb.config(command=t.yview)
    ysb.pack(side="right",  fill="y")
    xsb.pack(side="bottom", fill="x")
    t.pack(side="left", fill="both", expand=True)
    return tf, t

def _write(widget, text):
    widget.config(state="normal")
    widget.delete("1.0", "end")
    widget.insert("end", text)
    widget.config(state="disabled")


# ── ResultPane — structured data renderer (replaces dark output pane) ─────────

class ResultPane(tk.Frame):
    """
    Renders structured data dicts from ptos_service as proper Tkinter widgets.
    Supports: records (Treeview), group (Treeview), pivot (Treeview),
              trend (Treeview), metric (label), dashboard (label grid).
    Falls back to a plain text pane for errors or unknown kinds.
    """
    def __init__(self, parent, **kw):
        super().__init__(parent, bg=BG, **kw)
        self._inner = None

    def clear(self):
        if self._inner:
            self._inner.destroy()
            self._inner = None

    def show_error(self, msg):
        self.clear()
        f = tk.Frame(self, bg=BG, pady=8)
        f.pack(fill="both", expand=True)
        tk.Label(f, text=msg, font=F_LABEL, fg=ERROR_COL,
                 bg=BG, wraplength=600, justify="left").pack(anchor="w", padx=8)
        self._inner = f

    def show_message(self, msg):
        self.clear()
        f = tk.Frame(self, bg=BG, pady=8)
        f.pack(fill="both", expand=True)
        tk.Label(f, text=msg, font=F_LABEL, fg=SUBTEXT,
                 bg=BG).pack(anchor="w", padx=8)
        self._inner = f

    def show(self, data):
        """data is a dict returned by ptos_service with a 'kind' key."""
        self.clear()
        if not data:
            self.show_message("No data.")
            return
        kind = data.get("kind", "")
        try:
            if kind == "records":   self._show_records(data)
            elif kind == "group":   self._show_group(data)
            elif kind == "pivot":   self._show_pivot(data)
            elif kind == "trend":   self._show_trend(data)
            elif kind == "metric":  self._show_metric(data)
            elif kind == "dashboard": self._show_dashboard(data)
            else:
                self.show_message(str(data))
        except Exception as e:
            self.show_error(f"Render error: {e}")

    # ── summary bar ───────────────────────────────────────────────────────────

    def _summary_bar(self, parent, data):
        bar = tk.Frame(parent, bg=CARD, pady=4, padx=4)
        parts = []
        if data.get("count") is not None:
            parts.append(f"{data['count']} records")
        if data.get("total_fmt"):
            parts.append(f"Total: {data['total_fmt']}")
        if data.get("avg_fmt"):
            parts.append(f"Avg: {data['avg_fmt']}")
        if data.get("time_label"):
            parts.append(data["time_label"])
        if parts:
            tk.Label(bar, text="  ·  ".join(parts),
                     font=F_SMALL, fg=SUBTEXT, bg=CARD).pack(anchor="w")
        return bar

    # ── treeview helper ───────────────────────────────────────────────────────

    def _make_tree(self, parent, columns, rows, totals_row=None):
        """columns: list of str. rows: list of dicts. totals_row: dict or None."""
        frame = tk.Frame(parent, bg=BG)
        frame.pack(fill="both", expand=True)

        xsb = ttk.Scrollbar(frame, orient="horizontal")
        ysb = ttk.Scrollbar(frame, orient="vertical")
        tree = ttk.Treeview(frame, columns=columns, show="headings",
                            yscrollcommand=ysb.set, xscrollcommand=xsb.set,
                            selectmode="browse")
        xsb.config(command=tree.xview)
        ysb.config(command=tree.yview)
        ysb.pack(side="right", fill="y")
        xsb.pack(side="bottom", fill="x")
        tree.pack(side="left", fill="both", expand=True)

        # configure columns
        for col in columns:
            tree.heading(col, text=col)
            # right-align numeric-looking columns
            tree.column(col, anchor="e" if col in ("count","total","total_fmt","avg_fmt","days","amount","advance") else "w",
                        width=110, minwidth=60)
        tree.column(columns[0], width=160)  # first col wider

        # fill rows
        for row in rows:
            vals = [str(row.get(c,"")) for c in columns]
            tree.insert("", "end", values=vals)

        # totals row in bold tag
        if totals_row:
            tree.tag_configure("total", font=(F_LABEL[0], F_LABEL[1], "bold"))
            vals = [str(totals_row.get(c,"")) for c in columns]
            tree.insert("", "end", values=vals, tags=("total",))

        return frame

    # ── kind renderers ────────────────────────────────────────────────────────

    def _show_records(self, data):
        f = tk.Frame(self, bg=BG)
        f.pack(fill="both", expand=True)
        self._inner = f
        if not data.get("records"):
            tk.Label(f, text="No records found.", font=F_LABEL,
                     fg=SUBTEXT, bg=BG).pack(anchor="w", padx=8, pady=8)
            return
        self._records_data = data.get("records", [])
        self._summary_bar(f, data).pack(fill="x")
        cols = [c for c in (data.get("columns") or []) if not c.startswith("_")]
        tree_frame = self._make_tree(f, cols, data["records"])

        # action bar
        act = tk.Frame(f, bg=CARD, pady=6, padx=HPAD)
        act.pack(fill="x", side="bottom")
        self._edit_btn = tk.Button(act, text="✎  Edit", state="disabled",
            font=F_BTN, bg=CARD, fg=ACCENT, activeforeground=ACCENT_HO,
            relief="flat", bd=0, cursor="hand2", padx=12, pady=6,
            command=self._edit_selected)
        self._edit_btn.pack(side="left", padx=(0, 8))
        self._del_btn = tk.Button(act, text="✕  Delete", state="disabled",
            font=F_BTN, bg=CARD, fg=ERROR_COL, activeforeground=ERROR_COL,
            relief="flat", bd=0, cursor="hand2", padx=12, pady=6,
            command=self._delete_selected)
        self._del_btn.pack(side="left")
        tk.Label(act, text="Select a row to edit or delete",
            font=F_SMALL, fg=SUBTEXT, bg=CARD).pack(side="left", padx=16)

        # find treeview inside tree_frame
        tree = None
        for w in tree_frame.winfo_children():
            if isinstance(w, ttk.Treeview):
                tree = w
                break
        if tree is None:
            for w in tree_frame.winfo_descendants() if hasattr(tree_frame, 'winfo_descendants') else []:
                if isinstance(w, ttk.Treeview):
                    tree = w
                    break

        if tree:
            self._tree = tree
            def _on_select(_=None):
                sel = tree.selection()
                state = "normal" if sel else "disabled"
                self._edit_btn.config(state=state)
                self._del_btn.config(state=state)
            tree.bind("<<TreeviewSelect>>", _on_select)
            tree.bind("<Double-1>", lambda _: self._edit_selected())

    def set_refresh_callback(self, cb):
        """Register a callback to refresh results after edit/delete."""
        self._refresh_cb = cb

    def _selected_record(self):
        """Return the full record dict for the selected tree row, or None."""
        tree = getattr(self, "_tree", None)
        if not tree:
            return None
        sel = tree.selection()
        if not sel:
            return None
        idx = tree.index(sel[0])
        records = getattr(self, "_records_data", [])
        if idx < len(records):
            return records[idx]
        return None

    def _edit_selected(self):
        rec = self._selected_record()
        if not rec:
            return
        if not rec.get("_line") or not rec.get("_filepath"):
            messagebox.showwarning("Edit", "Record location unavailable — re-run the query and try again.")
            return
        def _on_saved():
            cb = getattr(self, "_refresh_cb", None)
            if cb:
                cb()
        EditRecordDialog(self, rec, _on_saved)

    def _delete_selected(self):
        rec = self._selected_record()
        if not rec:
            return
        if not rec.get("_line") or not rec.get("_filepath"):
            messagebox.showwarning("Delete", "Record location unavailable — re-run the query and try again.")
            return
        line_preview = rec.get("_line", "")
        if len(line_preview) > 80:
            line_preview = line_preview[:80] + "…"
        confirmed = messagebox.askyesno(
            "Delete Record",
            f"Delete this record?\n\n{line_preview}\n\nThis cannot be undone (backup kept).",
            icon="warning")
        if not confirmed:
            return
        try:
            svc.delete_record(
                rec["_filepath"], rec["_line"],
                lineno=rec.get("_lineno"))
            cb = getattr(self, "_refresh_cb", None)
            if cb:
                cb()
        except PTOSError as e:
            messagebox.showerror("Delete Failed", str(e))
        except Exception as e:
            messagebox.showerror("Delete Failed", str(e))


        f = tk.Frame(self, bg=BG)
        f.pack(fill="both", expand=True)
        self._inner = f
        has_amt = data.get("has_amount", False)
        cols = ["key", "count"] + (["total"] if has_amt else [])
        rows = []
        for r in data.get("rows", []):
            row = {"key": r["key"], "count": str(r["count"])}
            if has_amt: row["total"] = r["total_fmt"]
            rows.append(row)
        totals = {"key": "Total", "count": str(data.get("grand_count",0))}
        if has_amt: totals["total"] = data.get("grand_total_fmt","")
        tk.Label(f, text=f"Grouped by {', '.join(data.get('fields',[]))}  ·  {data.get('time_label','')}",
                 font=F_SMALL, fg=SUBTEXT, bg=BG).pack(anchor="w", padx=4, pady=(4,0))
        self._make_tree(f, cols, rows, totals_row=totals)

    def _show_pivot(self, data):
        f = tk.Frame(self, bg=BG)
        f.pack(fill="both", expand=True)
        self._inner = f
        cols  = [data.get("row_field","row")] + data.get("cols",[]) + ["total"]
        rows  = []
        for r in data.get("rows", []):
            row = {data.get("row_field","row"): r["label"], "total": str(r["total"])}
            for c in data.get("cols", []): row[c] = str(r.get(c,0))
            rows.append(row)
        ct = data.get("col_totals", {})
        totals = {data.get("row_field","row"): "Total", "total": str(data.get("grand",0))}
        for c in data.get("cols", []): totals[c] = str(ct.get(c,0))
        tk.Label(f, text=f"Pivot  {data.get('row_field','')} × {data.get('col_field','')}  ·  {data.get('time_label','')}",
                 font=F_SMALL, fg=SUBTEXT, bg=BG).pack(anchor="w", padx=4, pady=(4,0))
        self._make_tree(f, cols, rows, totals_row=totals)

    def _show_trend(self, data):
        f = tk.Frame(self, bg=BG)
        f.pack(fill="both", expand=True)
        self._inner = f
        has_amt = data.get("has_amount", False)
        cols    = ["label", "count"] + (["total","avg"] if has_amt else [])
        rows    = []
        for p in data.get("periods", []):
            row = {"label": p["label"], "count": str(p["count"])}
            if has_amt:
                row["total"] = p.get("total_fmt","")
                row["avg"]   = p.get("avg_fmt","")
            rows.append(row)
        tk.Label(f, text=f"Trend  ·  {data.get('filter_str','')}",
                 font=F_SMALL, fg=SUBTEXT, bg=BG).pack(anchor="w", padx=4, pady=(4,0))
        self._make_tree(f, cols, rows)

    def _show_metric(self, data):
        f = tk.Frame(self, bg=CARD, relief="flat", bd=1)
        f.pack(fill="x", padx=8, pady=8)
        self._inner = f
        tk.Label(f, text=data.get("name","").replace("_"," "),
                 font=F_SMALL, fg=SUBTEXT, bg=CARD).pack(anchor="w", padx=12, pady=(10,0))
        tk.Label(f, text=data.get("value","—"),
                 font=(F_HEAD[0], 28, "bold"), fg=ACCENT, bg=CARD).pack(anchor="w", padx=12, pady=(2,10))

    def _show_dashboard(self, data):
        f = tk.Frame(self, bg=BG)
        f.pack(fill="both", expand=True)
        self._inner = f
        tk.Label(f, text=f"Dashboard: {data.get('name','')}  ·  {data.get('period','')}",
                 font=F_SMALL, fg=SUBTEXT, bg=BG).pack(anchor="w", padx=4, pady=(4,4))
        grid = tk.Frame(f, bg=BG)
        grid.pack(fill="x", padx=4)
        col_n = 0
        for item in data.get("items", []):
            card = tk.Frame(grid, bg=CARD, relief="flat", bd=1,
                            padx=14, pady=10)
            card.grid(row=0, column=col_n, padx=6, pady=4, sticky="nsew")
            grid.columnconfigure(col_n, weight=1)
            tk.Label(card, text=item["name"].replace("_"," "),
                     font=F_SMALL, fg=SUBTEXT, bg=CARD).pack(anchor="w")
            tk.Label(card, text=item.get("value","—"),
                     font=(F_LABEL[0], 16, "bold"), fg=TEXT, bg=CARD).pack(anchor="w")
            col_n += 1



# ── Date Picker ───────────────────────────────────────────────────────────────

class DatePicker(tk.Toplevel):
    """Popup calendar — sets a StringVar to the chosen YYYY-MM-DD date."""

    def __init__(self, parent, date_var):
        super().__init__(parent)
        self.date_var = date_var
        self.overrideredirect(True)   # no title bar
        self.resizable(False, False)

        try:
            chosen = dt.date.fromisoformat(date_var.get())
        except ValueError:
            chosen = dt.date.today()
        self._year  = chosen.year
        self._month = chosen.month
        self._chosen = chosen

        self._build()
        self._position(parent)
        self.grab_set()
        self.focus_set()
        self.bind("<Escape>", lambda _: self.destroy())
        self.bind("<FocusOut>", self._on_focus_out)

    def _on_focus_out(self, e):
        # close if focus moves outside this window
        if self.focus_get() is None:
            self.destroy()

    def _position(self, parent):
        self.update_idletasks()
        x = parent.winfo_rootx()
        y = parent.winfo_rooty() + parent.winfo_height() + 4
        self.geometry(f"+{x}+{y}")

    def _build(self):
        for w in self.winfo_children():
            w.destroy()

        outer = tk.Frame(self, bg=BORDER, padx=1, pady=1)
        outer.pack()
        inner = tk.Frame(outer, bg=CARD)
        inner.pack()

        # ── nav row ──────────────────────────────────────────────────────────
        nav = tk.Frame(inner, bg=ACCENT, pady=6)
        nav.pack(fill="x")

        tk.Button(nav, text="◀", command=self._prev_month,
                  font=F_BTN, bg=ACCENT, fg="white",
                  activebackground=ACCENT_HO, relief="flat",
                  bd=0, padx=10).pack(side="left")

        self._title = tk.Label(nav,
                               text=dt.date(self._year, self._month, 1).strftime("%B %Y"),
                               font=F_BTN, fg="white", bg=ACCENT)
        self._title.pack(side="left", expand=True)

        tk.Button(nav, text="▶", command=self._next_month,
                  font=F_BTN, bg=ACCENT, fg="white",
                  activebackground=ACCENT_HO, relief="flat",
                  bd=0, padx=10).pack(side="right")

        # ── day-of-week headers ───────────────────────────────────────────────
        dow = tk.Frame(inner, bg=CARD, pady=4)
        dow.pack(fill="x", padx=6)
        for d in ["Mo", "Tu", "We", "Th", "Fr", "Sa", "Su"]:
            tk.Label(dow, text=d, font=F_SMALL, fg=SUBTEXT,
                     bg=CARD, width=3).pack(side="left", padx=2)

        # ── day grid ──────────────────────────────────────────────────────────
        grid = tk.Frame(inner, bg=CARD, padx=6, pady=2)
        grid.pack()

        import calendar
        cal = calendar.monthcalendar(self._year, self._month)
        today = dt.date.today()

        for week in cal:
            row = tk.Frame(grid, bg=CARD)
            row.pack()
            for day in week:
                if day == 0:
                    tk.Label(row, text="", width=3, bg=CARD).pack(side="left", padx=2, pady=2)
                else:
                    d = dt.date(self._year, self._month, day)
                    is_chosen = (d == self._chosen)
                    is_today  = (d == today)
                    bg  = ACCENT if is_chosen else ("#E8F0FE" if is_today else CARD)
                    fg  = "white" if is_chosen else (ACCENT if is_today else TEXT)
                    btn = tk.Button(row, text=str(day), width=3,
                                    font=F_BODY, bg=bg, fg=fg,
                                    activebackground=ACCENT_HO,
                                    activeforeground="white",
                                    relief="flat", bd=0,
                                    command=lambda d=d: self._pick(d))
                    btn.pack(side="left", padx=2, pady=2)

        # ── today shortcut ────────────────────────────────────────────────────
        foot = tk.Frame(inner, bg=CARD, pady=6)
        foot.pack(fill="x")
        tk.Button(foot, text="Today", command=lambda: self._pick(dt.date.today()),
                  font=F_SMALL, bg=BG, fg=ACCENT,
                  activeforeground=ACCENT_HO, relief="flat", bd=0).pack()

    def _prev_month(self):
        self._month -= 1
        if self._month == 0:
            self._month = 12
            self._year -= 1
        self._build()

    def _next_month(self):
        self._month += 1
        if self._month == 13:
            self._month = 1
            self._year += 1
        self._build()

    def _pick(self, d):
        self.date_var.set(d.isoformat())
        self.destroy()


# ══════════════════════════════════════════════════════════════════════════════
# Add Record Tab
# ══════════════════════════════════════════════════════════════════════════════

class AddRecordTab(tk.Frame):
    def __init__(self, parent):
        super().__init__(parent, bg=BG)
        self.schema      = ptos.get_schema()
        self.type_schema = {}
        self.field_vars  = {}
        self.field_rows  = {}
        self.tag_vars    = {}
        self._build()

    def _build(self):
        # ── top header bar ────────────────────────────────────────────────────
        hdr = tk.Frame(self, bg=CARD, pady=16)
        hdr.pack(fill="x")
        tk.Label(hdr, text="Add Record", font=F_HEAD,
                 fg=TEXT, bg=CARD).pack(side="left", padx=HPAD)
        tk.Button(hdr, text="⟳  Reload", command=self._reload,
                  font=F_SMALL, bg=CARD, fg=ACCENT,
                  activeforeground=ACCENT_HO, relief="flat", bd=0,
                  cursor="hand2").pack(side="right", padx=HPAD)

        # ── preset + type row ─────────────────────────────────────────────────
        row = tk.Frame(self, bg=BG, pady=PAD)
        row.pack(fill="x", padx=HPAD)

        # ── Quick presets chips ───────────────────────────────────────────────
        presets = ptos.get_presets()
        simple_presets = {k: v for k, v in presets.items()
                         if isinstance(v, dict) and "type" in v}
        if simple_presets:
            # Compact preset row - minimal vertical space
            chip_frame = tk.Frame(self, bg=BG)
            chip_frame.pack(fill="x", padx=HPAD, pady=(4, 2))
            for pname in sorted(simple_presets.keys()):
                btn = tk.Button(chip_frame, text=f"+{pname}",
                               font=("Segoe UI", 10), fg=ACCENT, bg=ACCENT_LT,
                               activebackground=ACCENT, activeforeground="white",
                               relief="flat", cursor="hand2", padx=6, pady=2, bd=0,
                               command=lambda n=pname: self._load_preset_by_name(n))
                btn.pack(side="left", padx=2)

        preset_col = tk.Frame(row, bg=BG)
        preset_col.pack(side="left", padx=(0, 32))
        lbl(preset_col, "Load preset", fg=SUBTEXT, font=F_LABEL).pack(anchor="w")
        self._preset_var = tk.StringVar()
        preset_names = ["—"] + sorted(presets.keys())
        self._preset_combo = _make_combo(preset_col, preset_names,
                                         textvariable=self._preset_var, width=22)
        self._preset_combo.pack(anchor="w", pady=(4, 0))
        self._preset_combo.bind("<<ComboboxSelected>>", self._on_preset_change)

        type_col = tk.Frame(row, bg=BG)
        type_col.pack(side="left")
        lbl(type_col, "Record type", fg=SUBTEXT, font=F_LABEL).pack(anchor="w")
        self._type_var = tk.StringVar()
        c = _make_combo(type_col, self.schema["types"]["allowed"],
                        textvariable=self._type_var, width=28)
        c.pack(anchor="w", pady=(4, 0))
        c.bind("<<ComboboxSelected>>", self._on_type_change)

        hsep(self).pack(fill="x", pady=(PAD, 0))

        # ── scrollable fields area ────────────────────────────────────────────
        self._body = ScrollBody(self, bg=BG)

        # ── footer ────────────────────────────────────────────────────────────
        hsep(self).pack(fill="x", side="bottom")
        foot = tk.Frame(self, bg=CARD, pady=12, padx=HPAD)
        foot.pack(fill="x", side="bottom")
        self._status = tk.Label(foot, text="", font=F_LABEL,
                                fg=SUCCESS, bg=CARD,
                                wraplength=560, justify="left")
        self._status.pack(side="left", fill="x", expand=True)
        tk.Button(foot, text="Save as Preset",
                  command=self._save_as_preset,
                  font=F_BTN, bg=BG, fg=ACCENT,
                  activeforeground=ACCENT_HO,
                  relief="flat", bd=0, cursor="hand2",
                  padx=12, pady=8).pack(side="right", padx=(0, 8))
        _make_button(foot, "Save Record", self._submit).pack(side="right")
        tk.Button(foot, text="✕  Clear", command=self._clear,
                  font=F_BTN, bg=BG, fg=SUBTEXT,
                  activeforeground=TEXT, relief="flat",
                  cursor="hand2", padx=12, pady=8, bd=0).pack(side="right", padx=(0, 8))

    # ── type change ───────────────────────────────────────────────────────────

    def _clear(self):
        """Reset all fields and type selector back to blank state."""
        self._type_var.set("")
        self._preset_var.set("—")
        self.type_schema = {}
        for w in self._body.winfo_children():
            w.destroy()
        self.field_vars = {}
        self.tag_vars   = {}
        self._status.config(text="")

    def _reload(self):
        """Reload schema and presets from disk — updates all dropdowns."""
        self.schema = ptos.get_schema()
        presets = ptos.get_presets()
        self._preset_combo["values"] = ["—"] + sorted(presets.keys())
        rtype = self._type_var.get()
        if rtype:
            self.type_schema = self.schema["type"].get(rtype, {})
            self._rebuild_fields()
        self._status.config(text="⟳  Reloaded schema and presets.", fg=ACCENT)

    def _on_type_change(self, _=None):
        rtype = self._type_var.get()
        if not rtype:
            return
        self.type_schema = self.schema["type"].get(rtype, {})
        self._rebuild_fields()
        self._status.config(text="")

    def _rebuild_fields(self):
        for w in self._body.winfo_children():
            w.destroy()
        self.field_vars = {}
        self.field_rows = {}
        self.tag_vars   = {}

        required   = self.type_schema.get("required", [])
        all_fields = list(required)
        for f in self.type_schema.get("fields", {}):
            if f not in all_fields:
                all_fields.append(f)
        for f in self.type_schema.get("conditions", {}):
            if f not in all_fields:
                all_fields.append(f)

        for field in all_fields:
            self._add_field_row(field, field in required)

        self._update_conditionals()
        self._add_tag_section()
        self._add_date_note_section()
        self._body.reset()

    # ── field rows ────────────────────────────────────────────────────────────

    def _add_field_row(self, field, required):
        frame = tk.Frame(self._body, bg=BG, pady=5)
        frame.pack(fill="x", padx=HPAD)
        self.field_rows[field] = frame

        cap = field.replace("_", " ").title()
        mark = "  *" if required else ""
        lbl(frame, f"{cap}{mark}", font=F_LABEL,
            fg=SUBTEXT if not required else TEXT).pack(anchor="w")

        field_meta = self.schema.get("fields", {}).get(field, {})
        is_int     = isinstance(field_meta, dict) and field_meta.get("type") == "int"
        opts       = self._resolve_opts(field, {})
        var        = tk.StringVar()
        self.field_vars[field] = var

        if is_int:
            unit = field_meta.get("unit", "")
            # number-only validation
            vcmd = (frame.register(lambda s: s == "" or s.isdigit()), "%P")
            int_row = tk.Frame(frame, bg=BG)
            int_row.pack(anchor="w", pady=(3, 0))
            wf, we = _make_entry(int_row, textvariable=var, width=12)
            we.config(validate="key", validatecommand=vcmd)
            we.bind("<Control-Return>", lambda _: self._submit())
            wf.pack(side="left")
            if unit:
                tk.Label(int_row, text=unit, font=F_LABEL, fg=SUBTEXT,
                         bg=BG).pack(side="left", padx=(8, 0))
            var.trace_add("write", lambda *_: self._refresh_tags())
        elif opts is not None:
            c = _make_combo(frame, opts, textvariable=var, width=32)
            c.pack(anchor="w", pady=(3, 0))
            c.bind("<<ComboboxSelected>>", self._on_field_change)
        else:
            wf, fe = _make_entry(frame, textvariable=var, width=36)
            fe.bind("<Control-Return>", lambda _: self._submit())
            wf.pack(anchor="w", pady=(3, 0))

    def _resolve_opts(self, field, record):
        fd = self.type_schema.get("fields", {}).get(field, {})
        if "use" in fd:
            key = fd["use"].split(".", 1)[1]
            s   = self.schema.get("shared", {}).get(key, {})
            o   = s.get("options")
            return o if isinstance(o, list) else None
        opts = fd.get("options")
        if isinstance(opts, list):
            return opts
        if isinstance(opts, dict):
            parent = fd.get("parent")
            pval   = record.get(parent) or \
                     self.field_vars.get(parent, tk.StringVar()).get()
            return opts.get(pval, [])
        return None

    def _on_field_change(self, _=None):
        record = self._record_now()
        for field in list(self.field_vars):
            fd = self.type_schema.get("fields", {}).get(field, {})
            if isinstance(fd.get("options"), dict):
                new_opts = self._resolve_opts(field, record)
                row = self.field_rows.get(field)
                if row:
                    for w in row.winfo_children():
                        if isinstance(w, ttk.Combobox):
                            if w.get() not in new_opts:
                                w.set("")
                                self.field_vars[field].set("")
                            w["values"] = new_opts
        self._update_conditionals()
        self._refresh_tags()

    def _update_conditionals(self):
        record = self._record_now()
        for field, rule in self.type_schema.get("conditions", {}).items():
            show = all(record.get(k) == v
                       for k, v in rule.get("when", {}).items())
            row  = self.field_rows.get(field)
            if row:
                if show:
                    row.pack(fill="x", padx=HPAD)
                else:
                    row.pack_forget()
                    self.field_vars.get(field, tk.StringVar()).set("")

    # ── tags ──────────────────────────────────────────────────────────────────

    def _add_tag_section(self):
        hsep(self._body).pack(fill="x", padx=HPAD, pady=8)

        outer = tk.Frame(self._body, bg=BG, pady=5)
        outer.pack(fill="x", padx=HPAD)
        lbl(outer, "Tags", font=F_LABEL, fg=SUBTEXT).pack(anchor="w")

        inp_row = tk.Frame(outer, bg=BG)
        inp_row.pack(anchor="w", pady=(3, 0))
        self._custom_tag_var = tk.StringVar()
        wf, _ = _make_entry(inp_row, textvariable=self._custom_tag_var, width=30)
        wf.pack(side="left")
        sublbl(inp_row, "  comma separated for multiple").pack(
            side="left", padx=(8, 0))

        self._tag_frame = tk.Frame(outer, bg=BG)
        self._tag_frame.pack(anchor="w", pady=(6, 0))
        self._refresh_tags()

    def _refresh_tags(self):
        if not hasattr(self, "_tag_frame"):
            return
        allowed = ptos.resolve_tags(self.schema, self.type_schema,
                                    self._record_now())
        prev = {t: v.get() for t, v in self.tag_vars.items()}
        for w in self._tag_frame.winfo_children():
            w.destroy()
        self.tag_vars = {}
        for tag in allowed:
            var = tk.IntVar(value=prev.get(tag, 0))
            tk.Checkbutton(
                self._tag_frame, text=tag, variable=var,
                font=F_BODY, bg=BG, fg=TEXT,
                selectcolor=ACCENT, activebackground=BG,
                relief="flat"
            ).pack(side="left", padx=(0, 12))
            self.tag_vars[tag] = var

    # ── date + note ───────────────────────────────────────────────────────────

    def _add_date_note_section(self):
        hsep(self._body).pack(fill="x", padx=HPAD, pady=8)

        # date
        dr = tk.Frame(self._body, bg=BG, pady=5)
        dr.pack(fill="x", padx=HPAD)
        lbl(dr, "Date  *", font=F_LABEL, fg=TEXT).pack(anchor="w")
        date_row = tk.Frame(dr, bg=BG)
        date_row.pack(anchor="w", pady=(3, 0))
        self._date_var = tk.StringVar(value=dt.date.today().isoformat())
        wf, de = _make_entry(date_row, textvariable=self._date_var, width=14)
        de.bind("<Control-Return>", lambda _: self._submit())
        wf.pack(side="left")
        cal_btn = tk.Button(date_row, text="📅",
                            font=("Segoe UI Emoji", 13),
                            bg=BG, fg=ACCENT, relief="flat", bd=0,
                            cursor="hand2",
                            command=lambda: DatePicker(cal_btn, self._date_var))
        cal_btn.pack(side="left", padx=(6, 0))

        # note
        nr = tk.Frame(self._body, bg=BG, pady=5)
        nr.pack(fill="x", padx=HPAD)
        lbl(nr, "Note", font=F_LABEL, fg=SUBTEXT).pack(anchor="w")
        self._note_var = tk.StringVar()
        wf, ne = _make_entry(nr, textvariable=self._note_var, width=48)
        ne.bind("<Control-Return>", lambda _: self._submit())
        wf.pack(anchor="w", pady=(3, 0))

        # bottom padding
        tk.Frame(self._body, bg=BG, height=16).pack()

    # ── preset ───────────────────────────────────────────────────────────────

    def _on_preset_change(self, _=None):
        name = self._preset_var.get()
        if not name or name == "—":
            return
        presets = ptos.get_presets()
        preset  = presets.get(name, {})
        if not preset:
            return

        # resolve alias
        if isinstance(preset, dict) and "alias" in preset:
            preset = presets.get(preset["alias"], {})

        # multi-record preset — cannot populate a single form; show message
        if isinstance(preset, dict) and "records" in preset:
            refs = preset["records"]
            label = ", ".join(refs) if isinstance(refs, list) else str(refs)
            self._status.config(
                text=f"'{name}' is a multi-record preset ({label}). "
                     f"Use the CLI: ptos -p {name}", fg=ACCENT)
            self._preset_var.set("—")
            return
        rtype = preset.get("type", "")
        if rtype:
            self._type_var.set(rtype)
            self.type_schema = self.schema["type"].get(rtype, {})
            self._rebuild_fields()
        # set field values first so tag context is correct
        for field, val in preset.items():
            if field in ("type", "tag"):
                continue
            if field in self.field_vars:
                self.field_vars[field].set(str(val))
        # rebuild tags now that field values are set
        self._update_conditionals()
        self._refresh_tags()
        # now set tag checkboxes
        if "tag" in preset:
            tags = preset["tag"]
            if isinstance(tags, str):
                tags = [tags]
            for tag in tags:
                if tag in self.tag_vars:
                    self.tag_vars[tag].set(1)
                else:
                    # tag not in schema checkboxes — put in custom tag field
                    existing = self._custom_tag_var.get().strip()
                    self._custom_tag_var.set(
                        f"{existing},{tag}" if existing else tag)
        # load note from preset if present
        if "note" in preset and hasattr(self, "_note_var"):
            self._note_var.set(preset["note"])
        self._status.config(
            text=f"Preset '{name}' loaded — edit fields then save.", fg=ACCENT)

    def _load_preset_by_name(self, name):
        """Load a preset by name (called from quick preset chips)."""
        if not name:
            return
        self._preset_var.set(name)
        self._on_preset_change()

    def _save_as_preset(self):
        rtype = self._type_var.get()
        if not rtype:
            self._status.config(text="Select a record type first.", fg=ERROR_COL)
            return

        record = self._record_now()
        tags   = [t for t, v in self.tag_vars.items() if v.get()]
        for t in self._custom_tag_var.get().split(","):
            t = t.strip().replace(" ", "_")
            if t and t not in tags:
                tags.append(t)
        if tags:
            record["tag"] = tags
        note = getattr(self, "_note_var", tk.StringVar()).get().strip() or None

        dlg = tk.Toplevel(self)
        dlg.title("Save as Preset")
        dlg.resizable(False, False)
        dlg.grab_set()

        tk.Label(dlg, text="Preset name", font=F_LABEL, fg=TEXT,
                 padx=20, pady=12).pack(anchor="w")
        name_var = tk.StringVar()
        ef, entry_w = _make_entry(dlg, textvariable=name_var, width=28)
        ef.pack(padx=20, pady=(0, 4))
        tk.Label(dlg, text="lowercase, use _ for spaces — overwrites if exists",
                 font=F_SMALL, fg=SUBTEXT, padx=20).pack(anchor="w")
        status = tk.Label(dlg, text="", font=F_SMALL, fg=ERROR_COL, padx=20)
        status.pack(anchor="w")

        def _do_save():
            name = name_var.get().strip().replace(" ", "_").lower()
            if not name:
                status.config(text="Name cannot be empty.")
                return
            try:
                ptos._CACHE.pop("presets", None)
                ptos.save_as_preset(name, record, note=note)
                ptos._CACHE.pop("presets", None)
                self._preset_combo["values"] = ["—"] + sorted(ptos.get_presets().keys())
                self._status.config(
                    text=f"✔  Preset '{name}' saved.", fg=SUCCESS)
                dlg.destroy()
            except Exception as e:
                status.config(text=f"Error: {e}")

        btn_row = tk.Frame(dlg, pady=12, padx=20)
        btn_row.pack(fill="x")
        _make_button(btn_row, "Save", _do_save).pack(side="right")
        tk.Button(btn_row, text="Cancel", command=dlg.destroy,
                  font=F_BODY, relief="flat", padx=12, pady=8).pack(
                  side="right", padx=(0, 8))

        entry_w.focus_set()
        entry_w.bind("<Return>", lambda _: _do_save())
        dlg.bind("<Escape>", lambda _: dlg.destroy())
        dlg.update_idletasks()
        px, py = self.winfo_rootx(), self.winfo_rooty()
        pw, ph = self.winfo_width(), self.winfo_height()
        dw, dh = dlg.winfo_width(), dlg.winfo_height()
        dlg.geometry(f"+{px + (pw-dw)//2}+{py + (ph-dh)//2}")

    # ── submit ────────────────────────────────────────────────────────────────

    def _record_now(self):
        r = {"type": self._type_var.get()}
        for f, v in self.field_vars.items():
            val = v.get().strip()
            if val:
                r[f] = "_".join(val.split())
        return r

    def _submit(self):
        self._status.config(text="", fg=SUCCESS)
        rtype = self._type_var.get()
        if not rtype:
            self._status.config(text="Select a record type first.", fg=ERROR_COL)
            return

        record = self._record_now()

        tags = [t for t, v in self.tag_vars.items() if v.get()]
        for t in self._custom_tag_var.get().split(","):
            t = t.strip().replace(" ", "_")
            if t and t not in tags:
                tags.append(t)
        if tags:
            record["tag"] = tags

        date_str = getattr(self, "_date_var", tk.StringVar()).get().strip()
        try:
            ptos.parse_date(date_str)
        except ValueError:
            self._status.config(text="Invalid date. Use YYYY-MM-DD.", fg=ERROR_COL)
            return

        problems = ptos.validate_record(self.schema, record)
        if problems:
            self._status.config(text="  |  ".join(problems), fg=ERROR_COL)
            return

        note = getattr(self, "_note_var", tk.StringVar()).get().strip() or None
        line = ptos.build_record_line(date_str, record, note)
        ptos.append_record(line)
        self._status.config(text=f"✔  Saved:  {line}", fg=SUCCESS)

        # reset
        self._type_var.set("")
        self._preset_var.set("—")
        self.type_schema = {}
        for w in self._body.winfo_children():
            w.destroy()
        self.field_vars = {}
        self.tag_vars   = {}


# ══════════════════════════════════════════════════════════════════════════════
# Shared ctrl bar builder
# ══════════════════════════════════════════════════════════════════════════════

def _ctrl_bar(parent):
    """Returns a styled control bar frame."""
    bar = tk.Frame(parent, bg=CARD, pady=12, padx=HPAD)
    bar.pack(fill="x")
    return bar

def _ctrl_field(parent, label_text, widget_fn):
    """Pack a label+widget pair inline. Returns the widget."""
    tk.Label(parent, text=label_text, font=F_LABEL, fg=SUBTEXT,
             bg=CARD).pack(side="left", padx=(0, 4))
    w = widget_fn(parent)
    w.pack(side="left", padx=(0, 18))
    return w


# ══════════════════════════════════════════════════════════════════════════════
# Query Tab
# ══════════════════════════════════════════════════════════════════════════════

class QueryTab(tk.Frame):
    def __init__(self, parent):
        super().__init__(parent, bg=BG)
        self.cycles  = ptos.get_config().get("cycles", {})
        self.queries = ptos.get_queries()
        self._build()

    def _build(self):
        hdr = tk.Frame(self, bg=CARD, pady=16)
        hdr.pack(fill="x")
        tk.Label(hdr, text="Run Query", font=F_HEAD,
                 fg=TEXT, bg=CARD).pack(side="left", padx=HPAD)
        # reload button — refreshes query list from queries.toml
        tk.Button(hdr, text="⟳  Reload", command=self._reload,
                  font=F_SMALL, bg=CARD, fg=ACCENT,
                  activeforeground=ACCENT_HO, relief="flat", bd=0,
                  cursor="hand2").pack(side="right", padx=HPAD)

        bar = _ctrl_bar(self)

        named      = [k for k in self.queries
                      if k not in ("metrics", "dashboards", "due")]
        metrics    = [f"metric: {m}"
                      for m in self.queries.get("metrics", {})]
        dashboards = [f"dashboard: {d}"
                      for d in self.queries.get("dashboards", {})]
        self._q_var = tk.StringVar()
        q_combo = _make_combo(bar, named + metrics + dashboards,
                              textvariable=self._q_var, width=30)
        tk.Label(bar, text="Query", font=F_LABEL, fg=SUBTEXT,
                 bg=CARD).pack(side="left", padx=(0, 4))
        q_combo.pack(side="left", padx=(0, 18))
        q_combo.bind("<<ComboboxSelected>>", lambda _: self._run())

        self._time_var = tk.StringVar(value="(query default)")
        time_opts = ["(query default)"] + \
                    [label for label, _ in TIME_LABELS] + \
                    list(self.cycles.keys())
        t_combo = _make_combo(bar, time_opts,
                              textvariable=self._time_var, width=16)
        tk.Label(bar, text="Time", font=F_LABEL, fg=SUBTEXT,
                 bg=CARD).pack(side="left", padx=(0, 4))
        t_combo.pack(side="left", padx=(0, 18))
        t_combo.bind("<<ComboboxSelected>>", lambda _: self._run())
        t_combo.bind("<Return>", lambda _: self._run())
        q_combo.bind("<Return>", lambda _: self._run())

        _make_button(bar, "⟳  Refresh", self._run).pack(side="left", padx=(0, 8))
        tk.Button(bar, text="✕  Clear", command=self._clear,
                  font=F_BTN, bg=BG, fg=SUBTEXT,
                  activeforeground=TEXT, relief="flat",
                  cursor="hand2", padx=14, pady=8, bd=0).pack(side="left")

        hsep(self).pack(fill="x")

        self._result = ResultPane(self)
        self._result.pack(fill="both", expand=True, padx=HPAD, pady=HPAD)

    def _clear(self):
        self._q_var.set("")
        self._time_var.set("(query default)")
        self._result.clear()

    def _reload(self):
        self.queries = ptos.get_queries()
        for w in self.winfo_children():
            w.destroy()
        self._build()

    def _run(self):
        q_name = self._q_var.get().strip()
        if not q_name:
            return
        is_metric    = q_name.startswith("metric: ")
        is_dashboard = q_name.startswith("dashboard: ")
        if is_metric:    q_name = q_name[len("metric: "):]
        if is_dashboard: q_name = q_name[len("dashboard: "):]

        time_raw = self._time_var.get()
        time_code = None if time_raw == "(query default)" else _TIME_CODE.get(time_raw, time_raw)

        try:
            if is_dashboard:
                data = svc.get_dashboard(q_name, time_code or "tm")
                data["kind"] = "dashboard"
            elif is_metric:
                data = svc.get_metric(q_name, time_code or "tm")
                data["kind"] = "metric"
            else:
                data = svc.run_query(q_name, time_code)
            self._result.show(data)
        except PTOSError as e:
            self._result.show_error(str(e))
        except Exception as e:
            self._result.show_error(str(e))


# ══════════════════════════════════════════════════════════════════════════════
# Browse Tab
# ══════════════════════════════════════════════════════════════════════════════

# ══════════════════════════════════════════════════════════════════════════════
# Edit Record Dialog
# ══════════════════════════════════════════════════════════════════════════════

class EditRecordDialog(tk.Toplevel):
    """Pre-filled edit form for a single record.
    Builds the same field widgets as AddRecordTab but populated from
    the existing record. On save, diffs old vs new and calls svc.edit_record.
    """

    def __init__(self, parent, record, on_saved=None):
        super().__init__(parent, bg=BG)
        self.title("Edit Record")
        self.resizable(True, True)
        self.grab_set()
        self.minsize(480, 400)

        self._record   = record          # full dict incl _line _filepath _lineno
        self._on_saved = on_saved
        self._old_line = record.get("_line", "")
        self._filepath = record.get("_filepath", "")
        self._lineno   = record.get("_lineno")

        try:
            self._schema = ptos.get_schema()
        except Exception:
            self._schema = {}

        self._rtype = record.get("type", "")
        self._type_schema = self._schema.get("type", {}).get(self._rtype, {})

        self.field_vars = {}
        self.field_rows = {}
        self.tag_vars   = {}

        self._build()
        self._populate()

    def _build(self):
        # header
        hdr = tk.Frame(self, bg=CARD, pady=14, padx=HPAD)
        hdr.pack(fill="x")
        tk.Label(hdr, text=f"Edit  ·  {self._rtype}",
                 font=F_HEAD, fg=TEXT, bg=CARD).pack(side="left")
        tk.Button(hdr, text="✕", command=self.destroy,
                  font=F_BTN, bg=CARD, fg=SUBTEXT,
                  relief="flat", bd=0, cursor="hand2").pack(side="right")

        # original line for reference
        ref = tk.Frame(self, bg=BG, padx=HPAD, pady=6)
        ref.pack(fill="x")
        tk.Label(ref, text="Original:", font=F_SMALL, fg=SUBTEXT, bg=BG).pack(anchor="w")
        tk.Label(ref, text=self._old_line, font=F_MONO, fg=SUBTEXT, bg=BG,
                 wraplength=560, justify="left").pack(anchor="w")

        hsep(self).pack(fill="x")

        # scrollable body
        self._body = ScrollBody(self, bg=BG)

        # footer
        hsep(self).pack(fill="x", side="bottom")
        foot = tk.Frame(self, bg=CARD, pady=12, padx=HPAD)
        foot.pack(fill="x", side="bottom")
        self._status = tk.Label(foot, text="", font=F_LABEL,
                                fg=SUCCESS, bg=CARD, wraplength=380, justify="left")
        self._status.pack(side="left", fill="x", expand=True)
        tk.Button(foot, text="Cancel", command=self.destroy,
                  font=F_BTN, bg=CARD, fg=SUBTEXT, relief="flat",
                  bd=0, cursor="hand2", padx=12, pady=8).pack(side="right", padx=(8, 0))
        _make_button(foot, "Save Changes", self._save).pack(side="right")

        self._build_fields()

    def _build_fields(self):
        required   = self._type_schema.get("required", [])
        all_fields = list(required)
        for f in self._type_schema.get("fields", {}):
            if f not in all_fields: all_fields.append(f)
        for f in self._type_schema.get("conditions", {}):
            if f not in all_fields: all_fields.append(f)

        for field in all_fields:
            self._add_field_row(field, field in required)

        self._update_conditionals()
        self._add_tag_section()
        self._add_date_note_section()
        self._body.reset()

    def _add_field_row(self, field, required):
        frame = tk.Frame(self._body, bg=BG, pady=5)
        frame.pack(fill="x", padx=HPAD)
        self.field_rows[field] = frame

        cap  = field.replace("_", " ").title()
        mark = "  *" if required else ""
        lbl(frame, f"{cap}{mark}", font=F_LABEL,
            fg=TEXT if required else SUBTEXT).pack(anchor="w")

        field_meta = self._schema.get("fields", {}).get(field, {})
        is_int     = isinstance(field_meta, dict) and field_meta.get("type") == "int"
        opts       = self._resolve_opts(field)
        var        = tk.StringVar()
        self.field_vars[field] = var

        if is_int:
            unit = field_meta.get("unit", "")
            vcmd = (frame.register(lambda s: s == "" or s.isdigit()), "%P")
            int_row = tk.Frame(frame, bg=BG)
            int_row.pack(anchor="w", pady=(3, 0))
            wf, we = _make_entry(int_row, textvariable=var, width=12)
            we.config(validate="key", validatecommand=vcmd)
            wf.pack(side="left")
            if unit:
                tk.Label(int_row, text=unit, font=F_LABEL, fg=SUBTEXT,
                         bg=BG).pack(side="left", padx=(8, 0))
        elif opts is not None:
            c = _make_combo(frame, opts, textvariable=var, width=32)
            c.pack(anchor="w", pady=(3, 0))
            c.bind("<<ComboboxSelected>>", lambda _: self._on_field_change())
        else:
            wf, fe = _make_entry(frame, textvariable=var, width=36)
            fe.bind("<Control-Return>", lambda _: self._save())
            wf.pack(anchor="w", pady=(3, 0))

    def _resolve_opts(self, field):
        fd   = self._type_schema.get("fields", {}).get(field, {})
        if "use" in fd:
            key = fd["use"].split(".", 1)[1]
            s   = self._schema.get("shared", {}).get(key, {})
            o   = s.get("options")
            return o if isinstance(o, list) else None
        opts = fd.get("options")
        if isinstance(opts, list):
            return opts
        if isinstance(opts, dict):
            parent = fd.get("parent")
            pval   = self.field_vars.get(parent, tk.StringVar()).get() if parent else ""
            return opts.get(pval, [])
        return None

    def _on_field_change(self):
        record = {f: v.get() for f, v in self.field_vars.items()}
        for field in list(self.field_vars):
            fd = self._type_schema.get("fields", {}).get(field, {})
            if isinstance(fd.get("options"), dict):
                parent  = fd.get("parent")
                pval    = record.get(parent, "")
                new_opts = fd["options"].get(pval, [])
                row = self.field_rows.get(field)
                if row:
                    for w in row.winfo_children():
                        if isinstance(w, ttk.Combobox):
                            if w.get() not in new_opts:
                                w.set("")
                                self.field_vars[field].set("")
                            w["values"] = new_opts
        self._update_conditionals()
        self._refresh_tags()

    def _update_conditionals(self):
        record = {f: v.get() for f, v in self.field_vars.items()}
        for field, rule in self._type_schema.get("conditions", {}).items():
            show = all(record.get(k) == v for k, v in rule.get("when", {}).items())
            row  = self.field_rows.get(field)
            if row:
                if show: row.pack(fill="x", padx=HPAD)
                else:
                    row.pack_forget()
                    self.field_vars.get(field, tk.StringVar()).set("")

    def _add_tag_section(self):
        hsep(self._body).pack(fill="x", padx=HPAD, pady=8)
        outer = tk.Frame(self._body, bg=BG, pady=5)
        outer.pack(fill="x", padx=HPAD)
        lbl(outer, "Tags", font=F_LABEL, fg=SUBTEXT).pack(anchor="w")
        inp_row = tk.Frame(outer, bg=BG)
        inp_row.pack(anchor="w", pady=(3, 0))
        self._custom_tag_var = tk.StringVar()
        wf, _ = _make_entry(inp_row, textvariable=self._custom_tag_var, width=30)
        wf.pack(side="left")
        sublbl(inp_row, "  comma separated").pack(side="left", padx=(8, 0))
        self._tag_frame = tk.Frame(outer, bg=BG)
        self._tag_frame.pack(anchor="w", pady=(6, 0))
        self._refresh_tags()

    def _refresh_tags(self):
        if not hasattr(self, "_tag_frame"):
            return
        for w in self._tag_frame.winfo_children():
            w.destroy()
        self.tag_vars = {}
        record = {f: v.get() for f, v in self.field_vars.items()}
        record["type"] = self._rtype
        tags = ptos.resolve_tags(self._schema, self._type_schema, record)
        for tag in tags:
            var = tk.IntVar()
            self.tag_vars[tag] = var
            tk.Checkbutton(self._tag_frame, text=tag, variable=var,
                           font=F_LABEL, bg=BG, fg=TEXT,
                           activebackground=BG,
                           selectcolor=ENTRY_BG).pack(side="left", padx=(0, 10))

    def _add_date_note_section(self):
        hsep(self._body).pack(fill="x", padx=HPAD, pady=8)
        dr = tk.Frame(self._body, bg=BG, pady=5)
        dr.pack(fill="x", padx=HPAD)
        lbl(dr, "Date", font=F_LABEL, fg=SUBTEXT).pack(anchor="w")
        date_row = tk.Frame(dr, bg=BG)
        date_row.pack(anchor="w", pady=(3, 0))
        self._date_var = tk.StringVar(value=dt.date.today().isoformat())
        wf, de = _make_entry(date_row, textvariable=self._date_var, width=14)
        wf.pack(side="left")
        sublbl(date_row, "  YYYY-MM-DD").pack(side="left", padx=(8, 0))
        cal_btn = tk.Button(date_row, text="📅", font=F_LABEL,
                            bg=BG, fg=ACCENT, relief="flat", bd=0, cursor="hand2",
                            command=lambda: DatePicker(cal_btn, self._date_var))
        cal_btn.pack(side="left", padx=(6, 0))
        nr = tk.Frame(self._body, bg=BG, pady=5)
        nr.pack(fill="x", padx=HPAD)
        lbl(nr, "Note", font=F_LABEL, fg=SUBTEXT).pack(anchor="w")
        self._note_var = tk.StringVar()
        wf, ne = _make_entry(nr, textvariable=self._note_var, width=48)
        ne.bind("<Control-Return>", lambda _: self._save())
        wf.pack(anchor="w", pady=(3, 0))
        tk.Frame(self._body, bg=BG, height=16).pack()

    def _populate(self):
        """Fill all widgets with values from the existing record."""
        rec = self._record
        # fields
        for field, var in self.field_vars.items():
            val = rec.get(field, "")
            if isinstance(val, list):
                val = val[0] if val else ""
            var.set(str(val))
        # rebuild tags after fields are set (so context-dependent tags resolve)
        self._update_conditionals()
        self._refresh_tags()
        # tick current tags
        raw_tags = rec.get("tag", [])
        if isinstance(raw_tags, str):
            raw_tags = [raw_tags]
        for tag in raw_tags:
            if tag in self.tag_vars:
                self.tag_vars[tag].set(1)
            else:
                existing = self._custom_tag_var.get().strip()
                self._custom_tag_var.set(f"{existing},{tag}" if existing else tag)
        # date and note
        self._date_var.set(rec.get("date", dt.date.today().isoformat()))
        self._note_var.set(rec.get("note", ""))

    def _save(self):
        # build new record dict from current widget state
        new_record = {"type": self._rtype}
        for f, var in self.field_vars.items():
            v = var.get().strip()
            if v:
                new_record[f] = v
        tags = [t for t, v in self.tag_vars.items() if v.get()]
        for t in self._custom_tag_var.get().split(","):
            t = t.strip().replace(" ", "_")
            if t and t not in tags:
                tags.append(t)
        if tags:
            new_record["tag"] = tags

        new_date = self._date_var.get().strip()
        new_note = self._note_var.get().strip() or None

        # parse old record to diff
        parsed = ptos.safe_parse_line(self._old_line)
        if not parsed:
            self._status.config(text="Could not parse original record.", fg=ERROR_COL)
            return
        old_d, old_kv, old_note = parsed

        set_args = []
        if new_date != str(old_d):
            set_args.append(f"date={new_date}")

        all_keys = set(list(old_kv.keys()) + list(new_record.keys())) - {"type"}
        for k in all_keys:
            old_v = old_kv.get(k)
            new_v = new_record.get(k)
            if old_v is None and new_v is None:
                continue
            is_list = k == "tag" or isinstance(old_v, list) or isinstance(new_v, list)
            if is_list:
                old_list = old_v if isinstance(old_v, list) else ([old_v] if old_v else [])
                new_list = new_v if isinstance(new_v, list) else ([new_v] if new_v else [])
                if set(old_list) != set(new_list):
                    for item in set(new_list) - set(old_list):
                        set_args.append(f"{k}+={item}")
                    for item in set(old_list) - set(new_list):
                        set_args.append(f"{k}-={item}")
            else:
                old_s = str(old_v or "")
                new_s = str(new_v or "")
                if old_s != new_s:
                    set_args.append(f"{k}={new_v}" if new_v else f"{k}=")

        note_changed = new_note != (old_note or "")
        effective_note = new_note if note_changed else None

        if not set_args and effective_note is None:
            self._status.config(text="No changes to save.", fg=SUBTEXT)
            return

        try:
            svc.edit_record(self._filepath, self._old_line,
                            set_args=set_args, new_note=effective_note,
                            lineno=self._lineno)
            self._status.config(text="✔  Saved.", fg=SUCCESS)
            if self._on_saved:
                self._on_saved()
            self.after(800, self.destroy)
        except PTOSError as e:
            self._status.config(text=str(e), fg=ERROR_COL)
        except Exception as e:
            self._status.config(text=str(e), fg=ERROR_COL)


# ══════════════════════════════════════════════════════════════════════════════
class BrowseTab(tk.Frame):
    def __init__(self, parent):
        super().__init__(parent, bg=BG)
        self.cycles = ptos.get_config().get("cycles", {})
        self._schema = ptos.get_schema()
        self._field_filter_widgets = []
        self._row1c = None
        self._group_var = None
        self._group_combo = None
        self._build()

    def _reload(self):
        """Reload schema from disk — rebuilds tab with fresh type list."""
        self._schema = ptos.get_schema()
        self._field_filter_widgets = []
        self._row1c = None
        self._group_var = None
        self._group_combo = None
        for w in self.winfo_children():
            w.destroy()
        self._build()

    def _build(self):
        hdr = tk.Frame(self, bg=CARD, pady=16)
        hdr.pack(fill="x")
        tk.Label(hdr, text="Browse Records", font=F_HEAD,
                 fg=TEXT, bg=CARD).pack(side="left", padx=HPAD)
        tk.Button(hdr, text="⟳  Reload", command=self._reload,
                  font=F_SMALL, bg=CARD, fg=ACCENT,
                  activeforeground=ACCENT_HO, relief="flat", bd=0,
                  cursor="hand2").pack(side="right", padx=HPAD)

        # ── row 1: filters ───────────────────────────────────────────────────
        row1 = tk.Frame(self, bg=CARD, pady=10, padx=HPAD)
        row1.pack(fill="x")

        self._type_var = tk.StringVar(value="All types")
        schema = ptos.get_schema()
        type_opts = ["All types"] + schema["types"]["allowed"]
        type_combo = _make_combo(row1, type_opts,
                                 textvariable=self._type_var, width=16)
        tk.Label(row1, text="Type", font=F_LABEL, fg=SUBTEXT,
                 bg=CARD).pack(side="left", padx=(0, 4))
        type_combo.pack(side="left", padx=(0, 18))
        type_combo.bind("<<ComboboxSelected>>", lambda _: self._on_type_change())

        self._time_var = tk.StringVar(value="This month")
        time_opts = [label for label, _ in TIME_LABELS] + list(self.cycles.keys())
        time_combo = _make_combo(row1, time_opts,
                                 textvariable=self._time_var, width=14)
        tk.Label(row1, text="Time", font=F_LABEL, fg=SUBTEXT,
                 bg=CARD).pack(side="left", padx=(0, 4))
        time_combo.pack(side="left", padx=(0, 18))
        time_combo.bind("<<ComboboxSelected>>", lambda _: self._run())

        self._search_var = tk.StringVar()
        tk.Label(row1, text="Search", font=F_LABEL, fg=SUBTEXT,
                 bg=CARD).pack(side="left", padx=(0, 4))
        sf, search_entry = _make_entry(row1, textvariable=self._search_var, width=18)
        sf.pack(side="left", padx=(0, 4))
        search_entry.bind("<Return>", lambda _: self._run())
        # Debounce search - auto-run after 500ms
        self._search_var.trace_add("write", lambda *_: self._debounce_search())

        # Expression filter input
        self._expr_var = tk.StringVar()
        tk.Label(row1, text="Filter", font=F_LABEL, fg=SUBTEXT,
                 bg=CARD).pack(side="left", padx=(0, 4))
        sf3, expr_entry = _make_entry(row1, textvariable=self._expr_var, width=20)
        sf3.pack(side="left", padx=(0, 4))
        expr_entry.bind("<Return>", lambda _: self._run())
        sublbl(row1, "e.g. domain=self AND amount>100").pack(side="left", padx=(0, 8))

        # ── row 1b: file + sort ───────────────────────────────────────────────
        row1b = tk.Frame(self, bg=CARD, pady=4, padx=HPAD)
        row1b.pack(fill="x")

        self._file_var = tk.StringVar(value="(current year)")
        tk.Label(row1b, text="File", font=F_LABEL, fg=SUBTEXT,
                 bg=CARD).pack(side="left", padx=(0, 4))
        self._file_combo = _make_combo(row1b, ["(current year)"],
                                        textvariable=self._file_var, width=18)
        self._file_combo.pack(side="left", padx=(0, 18))
        self._file_combo.bind("<Button-1>", self._refresh_file_list)
        self._file_combo.bind("<<ComboboxSelected>>", lambda _: self._run())

        # Sort by dropdown - will be populated based on type
        self._sort_var = tk.StringVar(value="(none)")
        tk.Label(row1b, text="Sort by", font=F_LABEL, fg=SUBTEXT,
                 bg=CARD).pack(side="left", padx=(0, 4))
        self._sort_combo = _make_combo(row1b, ["(none)"],
                                        textvariable=self._sort_var, width=14)
        self._sort_combo.pack(side="left", padx=(0, 4))
        self._sort_combo.bind("<<ComboboxSelected>>", lambda _: self._run())

        self._group_var = tk.StringVar(value="(none)")
        tk.Label(row1b, text="Group by", font=F_LABEL, fg=SUBTEXT,
                 bg=CARD).pack(side="left", padx=(0, 4))
        self._group_combo = _make_combo(row1b, ["(none)"],
                                         textvariable=self._group_var, width=14)
        self._group_combo.pack(side="left", padx=(0, 4))
        self._group_combo.bind("<<ComboboxSelected>>", lambda _: self._run())

        # ── row 1c: dynamic field filters (shown when type selected) ──────────
        self._row1c = tk.Frame(self, bg=CARD, pady=4, padx=HPAD)
        # not packed yet — shown/hidden by _on_type_change

        # ── row 2: actions ────────────────────────────────────────────────────
        row2 = tk.Frame(self, bg=CARD, pady=8, padx=HPAD)
        row2.pack(fill="x")

        _make_button(row2, "⟳  Refresh", self._run).pack(side="left", padx=(0, 12))

        due_btn = tk.Button(row2, text="Due List", command=self._run_due,
                            font=F_BTN, bg="#E8803A", fg="white",
                            activebackground="#C96A2A", relief="flat",
                            cursor="hand2", padx=14, pady=8, bd=0)
        due_btn.pack(side="left", padx=(0, 12))

        tk.Button(row2, text="Export CSV", command=self._export_csv,
                  font=F_BTN, bg="#2E7D56", fg="white",
                  activebackground="#1F5C3E", relief="flat",
                  cursor="hand2", padx=14, pady=8, bd=0).pack(side="left", padx=(0, 12))
        tk.Button(row2, text="💾  Save as Query", command=self._save_as_query,
                  font=F_BTN, bg=ACCENT, fg="white",
                  activebackground=ACCENT_HO, relief="flat",
                  cursor="hand2", padx=14, pady=8, bd=0).pack(side="left", padx=(0, 12))
        tk.Button(row2, text="✕  Clear", command=self._clear,
                  font=F_BTN, bg=BG, fg=SUBTEXT,
                  activeforeground=TEXT, relief="flat",
                  cursor="hand2", padx=14, pady=8, bd=0).pack(side="left")

        hsep(self).pack(fill="x")

        self._result = ResultPane(self)
        self._result.pack(fill="both", expand=True, padx=HPAD, pady=HPAD)
        self._result.set_refresh_callback(self._run)
        
        # Initialize sort dropdown options
        self._populate_sort_options()

    def _run_due(self):
        """Show due list using service layer — renders as Treeview."""
        try:
            data = svc.get_due()
            data["kind"] = "records"
            # reshape due rows into records format for Treeview
            rows = data.get("rows", [])
            if not rows:
                self._result.show_message("No records overdue.")
                return
            sf   = data.get("sort_field") or "status"
            cols = ["days", "name", sf, "note"] if sf else ["days", "name", "note"]
            cols = [c for c in cols if c]
            records = [{c: str(r.get(c,"")) for c in cols} for r in rows]
            self._result.show({
                "kind":    "records",
                "records": records,
                "columns": cols,
                "count":   len(records),
                "total":   0, "total_fmt":"", "avg_fmt":"",
                "time_label": f">{data.get('days',7)} days overdue",
                "filters": [],
            })
        except PTOSError as e:
            self._result.show_error(str(e))
        except Exception as e:
            self._result.show_error(str(e))

    def _clear(self):
        self._type_var.set("All types")
        self._time_var.set("This month")
        self._search_var.set("")
        if self._group_var:
            self._group_var.set("(none)")
        self._sort_var.set("")
        self._file_var.set("(current year)")
        self._result.clear()

    def _export_csv(self):
        filters = []
        t = self._type_var.get()
        if t and t != "All types":
            filters.append(f"type={t}")
        filters += self._get_field_filters()
        time_code = _TIME_CODE.get(self._time_var.get(), self._time_var.get())
        try:
            data = svc.get_records(filters, time_code,
                                   search=self._search_var.get().strip() or None,
                                   sort=self._get_sort(),
                                   from_file=self._get_from_file())
            results_raw, _ = ptos.scan_records(
                *ptos.resolve_time(time_code, self.cycles),
                filters, self._search_var.get().strip() or None,
                self._get_from_file())
            time_label = ptos._TIME_ALIASES.get(time_code, time_code)
            ptos.export_csv(results_raw, "__AUTO__", filters, time_label)
            self._result.show_message(
                f"✔  Exported {data['count']} record(s) to exports/ folder.")
        except Exception as e:
            self._result.show_error(str(e))

    def _run(self):
        self._build_field_filters()
        filters = []
        t = self._type_var.get()
        if t and t != "All types":
            filters.append(f"type={t}")
        # Combine field filters with expression filter
        field_filters = self._get_field_filters()
        expr = self._expr_var.get().strip()
        if field_filters:
            filters.extend(field_filters)
        if expr:
            # Expression filter is added as-is (ptos.py will parse it)
            # It can contain AND, OR, operators like =, !=, >, <, ~, etc.
            filters.append(expr)
        time_code = _TIME_CODE.get(self._time_var.get(), self._time_var.get())
        group_f   = self._get_group_by()
        try:
            if group_f:
                data = svc.get_group(filters, time_code, [group_f],
                                     from_file=self._get_from_file())
                data["kind"] = "group"
            else:
                data = svc.get_records(filters, time_code,
                                       search=self._search_var.get().strip() or None,
                                       sort=self._get_sort(),
                                       from_file=self._get_from_file())
                data["kind"] = "records"
            self._result.show(data)
        except PTOSError as e:
            self._result.show_error(str(e))
        except Exception as e:
            self._result.show_error(str(e))

    def _debounce_search(self):
        """Debounce search - cancel previous timer and start new one."""
        if hasattr(self, '_search_timer') and self._search_timer:
            self.after_cancel(self._search_timer)
        self._search_timer = self.after(500, self._run)

    def _build_field_filters(self):
        """Populate row1c with filter widgets for dimension fields of selected type."""
        for w in self._row1c.winfo_children():
            w.destroy()
        self._field_filter_widgets = []

        rtype = self._type_var.get()
        if not rtype or rtype == "All types":
            self._row1c.pack_forget()
            return

        schema      = self._schema
        type_schema = schema.get("type", {}).get(rtype, {})
        non_dim     = ptos.non_dimension_fields()
        num_fields  = set(ptos.numeric_fields())

        filter_fields = []
        for field in list(type_schema.get("fields", {}).keys()):
            if field in non_dim:
                continue
            field_def = type_schema["fields"][field]
            opts = None
            if "use" in field_def:
                key  = field_def["use"].split(".", 1)[1]
                opts = schema.get("shared", {}).get(key, {}).get("options")
            elif isinstance(field_def.get("options"), list):
                opts = field_def["options"]
            elif isinstance(field_def.get("options"), dict):
                opts = []
                for vals in field_def["options"].values():
                    for v in vals:
                        if v not in opts:
                            opts.append(v)
            if field in num_fields:
                opts = None

            if opts:
                filter_fields.append((field, "options", opts))
            elif field in num_fields:
                filter_fields.append((field, "numeric", None))

        if not filter_fields:
            self._row1c.pack_forget()
            return

        for field, kind, opts in filter_fields:
            tk.Label(self._row1c, text=field, font=F_LABEL,
                     fg=SUBTEXT, bg=CARD).pack(side="left", padx=(0, 2))
            if kind == "numeric":
                op_var = tk.StringVar(value="=")
                op_combo = _make_combo(self._row1c, ["=", ">=", "<="],
                                       textvariable=op_var, width=3)
                op_combo.pack(side="left", padx=(0, 2))
                val_var = tk.StringVar()
                _, val_entry = _make_entry(self._row1c,
                                           textvariable=val_var, width=7)
                val_entry.pack(side="left", padx=(0, 14))
                val_entry.bind("<Return>", lambda _: self._run())
                self._field_filter_widgets.append((field, op_var, val_var))
            else:
                op_var  = tk.StringVar(value="=")
                val_var = tk.StringVar(value="")
                val_combo = _make_combo(self._row1c, [""] + list(opts),
                                        textvariable=val_var, width=14)
                val_combo.pack(side="left", padx=(0, 14))
                val_combo.bind("<<ComboboxSelected>>", lambda _: self._run())
                self._field_filter_widgets.append((field, op_var, val_var))

        self._row1c.pack(fill="x")

    def _build_group_opts(self):
        """Repopulate the Group by dropdown based on selected type."""
        if self._group_combo is None:
            return
        rtype = self._type_var.get()
        if not rtype or rtype == "All types":
            self._group_combo["values"] = ["(none)"]
            self._group_var.set("(none)")
            return
        schema      = self._schema
        type_schema = schema.get("type", {}).get(rtype, {})
        non_dim     = ptos.non_dimension_fields()
        dim_fields  = [f for f in type_schema.get("fields", {}).keys()
                       if f not in non_dim]
        # also include month/year as virtual group fields
        opts = ["(none)"] + dim_fields + ["month", "year"]
        self._group_combo["values"] = opts
        if self._group_var.get() not in opts:
            self._group_var.set("(none)")

    def _get_group_by(self):
        """Return the selected group field, or None."""
        if self._group_var is None:
            return None
        v = self._group_var.get()
        return v if v and v != "(none)" else None

    def _get_field_filters(self):
        """Return filter expression list from field filter widgets."""
        filters = []
        for field, op_var, val_var in self._field_filter_widgets:
            val = val_var.get().strip()
            if not val:
                continue
            op = op_var.get()
            filters.append(f"{field}{op}{val}")
        return filters

    def _save_as_query(self):
        """Save current Browse filters as a named query to queries.toml."""
        t         = self._type_var.get()
        time_raw  = self._time_var.get()
        time_code = _TIME_CODE.get(time_raw, time_raw)
        search    = self._search_var.get().strip()
        sort      = self._get_sort()

        filters = []
        if t and t != "All types":
            filters.append(f"type={t}")
        filters += self._get_field_filters()
        expr = self._expr_var.get().strip()
        if expr:
            filters.append(expr)

        if not filters and not search:
            self._result.show_message("Nothing to save — set at least a type or filter first.")
            return

        dlg = tk.Toplevel(self, bg=BG)
        dlg.title("Save as Query")
        dlg.resizable(False, False)
        dlg.grab_set()

        tk.Label(dlg, text="Save current filters as a query",
                 font=F_BODY, fg=TEXT, bg=BG).pack(padx=24, pady=(20, 4))

        preview_parts = []
        if filters:
            expr_preview = ptos._filters_to_expr(filters)
            preview_parts.append("where: " + expr_preview)
        preview_parts.append("time:  " + time_code)
        if search:
            preview_parts.append("search: " + search)
        group_f = self._get_group_by()
        if group_f:
            preview_parts.append("group: " + group_f)
        if sort:
            preview_parts.append("sort:  " + sort)
        tk.Label(dlg, text="\n".join(preview_parts),
                 font=F_MONO, fg=SUBTEXT, bg=BG,
                 justify="left").pack(padx=24, pady=(0, 12))

        tk.Label(dlg, text="Query name", font=F_LABEL,
                 fg=SUBTEXT, bg=BG).pack(padx=24, anchor="w")
        name_frame, name_entry = _make_entry(dlg, width=28)
        name_frame.pack(padx=24, pady=(2, 16))
        name_entry.focus_set()

        status_lbl = tk.Label(dlg, text="", font=F_SMALL, fg=ERROR_COL, bg=BG)
        status_lbl.pack(padx=24)

        btn_row = tk.Frame(dlg, bg=BG)
        btn_row.pack(padx=24, pady=(4, 20))
        tk.Button(btn_row, text="Cancel", command=dlg.destroy,
                  font=F_BTN, bg=BG, fg=SUBTEXT, relief="flat",
                  cursor="hand2", padx=12, pady=6).pack(side="left", padx=(0, 8))

        def _do_save():
            name = name_entry.get().strip().replace(" ", "_")
            if not name:
                status_lbl.config(text="Enter a name.")
                return
            try:
                existing = ptos.get_queries()
                if name in existing or name in existing.get("metrics", {}) \
                        or name in existing.get("dashboards", {}):
                    status_lbl.config(text=f"'{name}' already exists. Choose another name.")
                    return
            except Exception:
                pass
            lines = [f"\n[{name}]"]
            if filters:
                expr = ptos._filters_to_expr(filters)
                val  = expr.replace('"', '\\"')
                lines.append(f'where = "{val}"')
            lines.append("time  = \"" + time_code + "\"")
            if search:
                lines.append("search = \"" + search + "\"")
            group_f = self._get_group_by()
            if group_f:
                lines.append(f'group = ["{group_f}"]')
                lines.append("sum   = true")
            if sort:
                lines.append("sort  = \"" + sort + "\"")
            block = "\n".join(lines) + "\n"
            try:
                ptos._backup_file(ptos.QUERIES_PATH)
                with open(ptos.QUERIES_PATH, "a", encoding="utf-8") as f:
                    f.write(block)
                ptos._CACHE.pop("queries", None)
                dlg.destroy()
                self._result.show_message(
                    f"✔  Query '{name}' saved to queries.toml\n"
                    f"Run it from the Queries tab.")
            except Exception as e:
                status_lbl.config(text=f"Error: {e}")

        _make_button(btn_row, "Save", _do_save).pack(side="right")
        name_entry.bind("<Return>", lambda _: _do_save())

    def _get_from_file(self):
        v = self._file_var.get()
        return None if v == "(current year)" else v

    def _get_sort(self):
        v = self._sort_var.get().strip()
        return v if v and v != "(none)" else None

    def _populate_sort_options(self):
        """Populate sort dropdown with available field names based on type."""
        rtype = self._type_var.get()
        if not rtype or rtype == "All types":
            self._sort_combo["values"] = ["(none)", "date", "type"]
            self._sort_var.set("(none)")
            return
        
        type_schema = self._schema.get("type", {}).get(rtype, {})
        fields = list(type_schema.get("fields", {}).keys())
        
        # Add common options
        sort_opts = ["(none)", "date", "type"] + sorted(fields)
        self._sort_combo["values"] = sort_opts
        self._sort_var.set("(none)")

    def _refresh_file_list(self, _=None):
        try:
            log_files = sorted(
                f for f in os.listdir(ptos.RECORDS_DIR) if f.endswith(".log"))
            self._file_combo["values"] = ["(current year)"] + log_files
        except Exception:
            pass

    def _on_type_change(self):
        """Rebuild field filter row and group options when type changes, then run."""
        self._build_field_filters()
        self._build_group_opts()
        self._populate_sort_options()
        self._run()

# ══════════════════════════════════════════════════════════════════════════════
# Log Editor Tab
# ══════════════════════════════════════════════════════════════════════════════

class LogEditorTab(tk.Frame):
    """Plain-text editor for records and config files."""

    # label → relative path from PTOS_HOME (None = current year records)
    _FILE_TARGETS = [
        ("Records (current year)",  None),
        ("schema.toml",             "config/schema.toml"),
        ("queries.toml",            "config/queries.toml"),
        ("presets.toml",            "config/presets.toml"),
        ("config.toml",             "config/config.toml"),
    ]

    def __init__(self, parent):
        super().__init__(parent, bg=BG)
        self._path = None
        self._build()
        self._load()

    def _build(self):
        hdr = tk.Frame(self, bg=CARD, pady=16)
        hdr.pack(fill="x")
        tk.Label(hdr, text="Editor", font=F_HEAD,
                 fg=TEXT, bg=CARD).pack(side="left", padx=HPAD)

        # action buttons in header
        btn_frame = tk.Frame(hdr, bg=CARD)
        btn_frame.pack(side="right", padx=HPAD)
        tk.Button(btn_frame, text="⟳  Reload", command=self._load,
                  font=F_SMALL, bg=CARD, fg=ACCENT,
                  activeforeground=ACCENT_HO, relief="flat", bd=0,
                  cursor="hand2").pack(side="left", padx=(0, 16))
        _make_button(btn_frame, "Save", self._save).pack(side="left")

        # file selector bar
        sel_bar = tk.Frame(self, bg=CARD, pady=8, padx=HPAD)
        sel_bar.pack(fill="x")
        tk.Label(sel_bar, text="File", font=F_LABEL, fg=SUBTEXT,
                 bg=CARD).pack(side="left", padx=(0, 6))
        self._target_var = tk.StringVar(value=self._FILE_TARGETS[0][0])
        target_labels = [label for label, _ in self._FILE_TARGETS]
        tc = _make_combo(sel_bar, target_labels,
                         textvariable=self._target_var, width=28)
        tc.pack(side="left")
        tc.bind("<<ComboboxSelected>>", lambda _: self._load())

        hsep(self).pack(fill="x")

        # path info bar
        self._path_label = tk.Label(self, text="", font=F_SMALL,
                                     fg=SUBTEXT, bg=BG, anchor="w")
        self._path_label.pack(fill="x", padx=HPAD, pady=(6, 0))

        # status bar
        self._status = tk.Label(self, text="", font=F_LABEL,
                                 fg=SUCCESS, bg=BG, anchor="w")
        self._status.pack(fill="x", padx=HPAD, pady=(4, 0))

        # editor area
        tf = tk.Frame(self, bg=BORDER, padx=1, pady=1)
        tf.pack(fill="both", expand=True, padx=HPAD, pady=HPAD)
        xsb = ttk.Scrollbar(tf, orient="horizontal")
        ysb = ttk.Scrollbar(tf, orient="vertical")
        self._editor = tk.Text(tf, font=F_MONO, bg=OUTPUT_BG, fg=OUTPUT_FG,
                               insertbackground=OUTPUT_FG, relief="flat",
                               wrap="none", undo=True,
                               xscrollcommand=xsb.set,
                               yscrollcommand=ysb.set,
                               padx=10, pady=8)
        xsb.config(command=self._editor.xview)
        ysb.config(command=self._editor.yview)
        ysb.pack(side="right", fill="y")
        xsb.pack(side="bottom", fill="x")
        self._editor.pack(side="left", fill="both", expand=True)

        # Ctrl+S to save
        self._editor.bind("<Control-s>", lambda _: self._save())
        self._editor.bind("<Control-S>", lambda _: self._save())

    def _resolve_path(self):
        home = os.path.dirname(os.path.abspath(sys.modules["ptos"].__file__))
        ptos_home = os.environ.get("PTOS_HOME", home)
        label = self._target_var.get() if hasattr(self, "_target_var") else None
        rel = None
        for lbl_text, rel_path in self._FILE_TARGETS:
            if lbl_text == label:
                rel = rel_path
                break
        if rel is None:
            year = dt.date.today().year
            return os.path.join(ptos_home, "records", f"{year}.log")
        return os.path.join(ptos_home, rel)

    def _load(self):
        path = self._resolve_path()
        self._path = path
        self._path_label.config(text=path)
        self._status.config(text="")

        if not os.path.exists(path):
            self._editor.delete("1.0", "end")
            self._editor.insert("end", f"# File not found: {path}")
            return

        with open(path, encoding="utf-8") as f:
            file_content = f.read()

        self._editor.delete("1.0", "end")
        self._editor.insert("end", file_content)
        # scroll to end for records, top for config files
        if path.endswith(".log"):
            self._editor.see("end")
        else:
            self._editor.see("1.0")
        self._status.config(text=f"Loaded  {path}")

    def _save(self):
        if not self._path:
            return
        import shutil, tempfile

        content = self._editor.get("1.0", "end-1c")
        # always end with newline so appended records start on a new line
        if content and not content.endswith("\n"):
            content += "\n"

        # backup before overwrite
        backup = self._path + ".bak"
        if os.path.exists(self._path):
            shutil.copy2(self._path, backup)

        # write atomically via temp file
        dir_ = os.path.dirname(self._path)
        with tempfile.NamedTemporaryFile("w", dir=dir_,
                                         delete=False,
                                         encoding="utf-8",
                                         suffix=".tmp") as tmp:
            tmp.write(content)
            tmp_path = tmp.name

        os.replace(tmp_path, self._path)
        self._status.config(
            text=f"✔  Saved  ({backup} backup kept)",
            fg=SUCCESS)



# ══════════════════════════════════════════════════════════════════════════════
# Journal Tab
# ══════════════════════════════════════════════════════════════════════════════

class JournalTab(tk.Frame):
    """Daily journal — plain text editor with light markdown colouring.
    Opens today's journal automatically. Prev/Next/date picker to browse.
    """

    def __init__(self, parent):
        super().__init__(parent, bg=BG)
        self._path    = None
        self._current = dt.date.today()
        self._build()
        self._load(self._current)

    # ── build ─────────────────────────────────────────────────────────────────

    def _build(self):
        # header
        hdr = tk.Frame(self, bg=CARD, pady=12)
        hdr.pack(fill="x")
        tk.Label(hdr, text="Journal", font=F_HEAD,
                 fg=TEXT, bg=CARD).pack(side="left", padx=HPAD)

        # save button top-right
        btn_frame = tk.Frame(hdr, bg=CARD)
        btn_frame.pack(side="right", padx=HPAD)
        _make_button(btn_frame, "Save", self._save).pack(side="right")
        tk.Button(btn_frame, text="⟳  Reload", command=lambda: self._load(self._current),
                  font=F_SMALL, bg=CARD, fg=ACCENT,
                  activeforeground=ACCENT_HO, relief="flat", bd=0,
                  cursor="hand2").pack(side="right", padx=(0, 12))

        # nav bar
        nav = tk.Frame(self, bg=CARD, pady=8, padx=HPAD)
        nav.pack(fill="x")

        tk.Button(nav, text="◀  Prev", command=self._prev,
                  font=F_BODY, bg=BG, fg=ACCENT,
                  activeforeground=ACCENT_HO, relief="flat",
                  cursor="hand2", bd=0, padx=8).pack(side="left")

        tk.Button(nav, text="Today", command=self._go_today,
                  font=F_BODY, bg=BG, fg=ACCENT,
                  activeforeground=ACCENT_HO, relief="flat",
                  cursor="hand2", bd=0, padx=8).pack(side="left", padx=(4, 0))

        tk.Button(nav, text="Next  ▶", command=self._next,
                  font=F_BODY, bg=BG, fg=ACCENT,
                  activeforeground=ACCENT_HO, relief="flat",
                  cursor="hand2", bd=0, padx=8).pack(side="left", padx=(4, 0))

        # date label + calendar picker
        self._date_var = tk.StringVar()
        self._date_lbl = tk.Label(nav, textvariable=self._date_var,
                                  font=("Segoe UI", 12, "bold"),
                                  fg=TEXT, bg=CARD, cursor="hand2")
        self._date_lbl.pack(side="left", padx=(20, 0))
        self._date_lbl.bind("<Button-1>", self._pick_date)

        cal_btn = tk.Button(nav, text="📅",
                            font=("Segoe UI Emoji", 13),
                            bg=CARD, fg=ACCENT, relief="flat", bd=0,
                            cursor="hand2",
                            command=self._pick_date)
        cal_btn.pack(side="left", padx=(6, 0))

        # status bar
        self._status = tk.Label(self, text="", font=F_SMALL,
                                fg=SUCCESS, bg=BG, anchor="w")
        self._status.pack(fill="x", padx=HPAD, pady=(4, 0))

        hsep(self).pack(fill="x", pady=(4, 0))

        # create entry button — shown only when no entry exists for a past date
        # must be packed before the editor so it sits above it in layout order
        self._create_btn = tk.Button(self, text="+ Create Entry for This Date",
                                     command=self._create_entry,
                                     font=F_BTN, bg=ACCENT, fg="white",
                                     activebackground=ACCENT_HO,
                                     relief="flat", cursor="hand2",
                                     padx=20, pady=10, bd=0)
        # not packed yet — shown/hidden dynamically in _load

        # editor
        tf = tk.Frame(self, bg=BORDER, padx=1, pady=1)
        self._editor_frame = tf
        tf.pack(fill="both", expand=True, padx=HPAD, pady=HPAD)
        xsb = ttk.Scrollbar(tf, orient="horizontal")
        ysb = ttk.Scrollbar(tf, orient="vertical")
        self._editor = tk.Text(tf, font=F_MONO, bg=OUTPUT_BG, fg=OUTPUT_FG,
                               insertbackground=OUTPUT_FG, relief="flat",
                               wrap="word", undo=True,
                               xscrollcommand=xsb.set,
                               yscrollcommand=ysb.set,
                               padx=12, pady=10)
        xsb.config(command=self._editor.xview)
        ysb.config(command=self._editor.yview)
        ysb.pack(side="right", fill="y")
        xsb.pack(side="bottom", fill="x")
        self._editor.pack(side="left", fill="both", expand=True)

        # syntax highlight tags
        self._editor.tag_config("h1",       foreground="#e06c75", font=("Consolas", 13, "bold"))
        self._editor.tag_config("h2",       foreground="#e5c07b", font=("Consolas", 12, "bold"))
        self._editor.tag_config("h3",       foreground="#98c379", font=("Consolas", 12, "bold"))
        self._editor.tag_config("checkbox", foreground="#e5c07b")
        self._editor.tag_config("checked",  foreground="#98c379")
        self._editor.tag_config("rule",     foreground="#4b5263")
        self._editor.tag_config("bold",     foreground="#ffffff", font=("Consolas", 12, "bold"))
        self._editor.tag_config("italic",   foreground="#56b6c2", font=("Consolas", 12, "italic"))
        self._editor.tag_config("note_key", foreground="#61afef")

        # keybindings
        self._editor.bind("<Control-s>",      lambda _: self._save())
        self._editor.bind("<Control-S>",      lambda _: self._save())
        self._editor.bind("<Control-Return>", lambda _: self._toggle_checkbox())
        self._editor.bind("<KeyRelease>",     lambda _: self._highlight())

    # ── navigation ────────────────────────────────────────────────────────────

    def _prev(self):
        self._load(self._current - dt.timedelta(days=1))

    def _next(self):
        next_d = self._current + dt.timedelta(days=1)
        if next_d <= dt.date.today():
            self._load(next_d)

    def _go_today(self):
        self._load(dt.date.today())

    def _pick_date(self, _=None):
        dv = tk.StringVar(value=self._current.isoformat())
        DatePicker(self._date_lbl, dv)
        self.after(300, lambda: self._load_from_var(dv))

    def _load_from_var(self, dv):
        try:
            d = dt.date.fromisoformat(dv.get())
            if d != self._current:
                self._load(d)
        except ValueError:
            pass

    def _create_entry(self):
        """Create a blank journal entry for the current past date from template."""
        import shutil
        d = self._current
        path = self._journal_path(d)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        # use template if available, else starter
        home = os.path.dirname(os.path.abspath(sys.modules["ptos"].__file__))
        ptos_home = os.environ.get("PTOS_HOME", home)
        template_path = os.path.join(ptos_home, "templates", "daily.md")
        if os.path.exists(template_path):
            with open(template_path, encoding="utf-8") as f:
                text = f.read().replace("{{date}}", d.isoformat())
        else:
            text = ptos._STARTER_JOURNAL.replace("{{date}}", d.isoformat())
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
        self._load(d)  # reload — will now find the file

    # ── load / save ───────────────────────────────────────────────────────────

    def _journal_path(self, d):
        home = os.path.dirname(os.path.abspath(sys.modules["ptos"].__file__))
        ptos_home = os.environ.get("PTOS_HOME", home)
        year_dir = os.path.join(ptos_home, "journal", str(d.year))
        return os.path.join(year_dir, f"{d.isoformat()}.md")

    def _load(self, d):
        self._current = d
        self._date_var.set(d.strftime("%A, %d %B %Y"))
        self._status.config(text="")

        if d == dt.date.today():
            # use ptos to create from template if needed
            path = ptos.get_today_journal()
        else:
            path = self._journal_path(d)

        self._path = path

        if not os.path.exists(path):
            self._editor.config(state="normal")
            self._editor.delete("1.0", "end")
            self._editor.config(state="disabled")
            self._status.config(text=f"No entry for {d.isoformat()}.", fg=SUBTEXT)
            self._create_btn.pack(pady=(8, 4), before=self._editor_frame)
            return
        # entry exists — hide create button
        self._create_btn.pack_forget()

        with open(path, encoding="utf-8") as f:
            text = f.read()

        self._create_btn.pack_forget()
        self._editor.config(state="normal")
        self._editor.delete("1.0", "end")
        self._editor.insert("end", text)
        self._editor.see("1.0")
        self._highlight()
        self._status.config(text=path, fg=SUBTEXT)

    def _save(self):
        if not self._path:
            return
        import shutil, tempfile
        content = self._editor.get("1.0", "end-1c")
        if content and not content.endswith("\n"):
            content += "\n"
        backup = self._path + ".bak"
        if os.path.exists(self._path):
            shutil.copy2(self._path, backup)
        os.makedirs(os.path.dirname(self._path), exist_ok=True)
        dir_ = os.path.dirname(self._path)
        with tempfile.NamedTemporaryFile("w", dir=dir_, delete=False,
                                         encoding="utf-8", suffix=".tmp") as tmp:
            tmp.write(content)
            tmp_path = tmp.name
        os.replace(tmp_path, self._path)
        self._status.config(text=f"✔  Saved  {self._path}", fg=SUCCESS)

    # ── checkbox toggle (Ctrl+Enter) ──────────────────────────────────────────

    def _toggle_checkbox(self):
        line_start = self._editor.index("insert linestart")
        line_end   = self._editor.index("insert lineend")
        line = self._editor.get(line_start, line_end)
        if "- [ ]" in line:
            new_line = line.replace("- [ ]", "- [x]", 1)
        elif "- [x]" in line:
            new_line = line.replace("- [x]", "- [ ]", 1)
        else:
            return
        self._editor.delete(line_start, line_end)
        self._editor.insert(line_start, new_line)
        self._highlight()

    # ── syntax highlighting ───────────────────────────────────────────────────

    def _highlight(self):
        import re
        ed = self._editor
        # clear all tags
        for tag in ("h1", "h2", "h3", "checkbox", "checked", "rule", "bold", "italic", "note_key"):
            ed.tag_remove(tag, "1.0", "end")

        patterns = [
            ("h1",       r"^# .+$"),
            ("h2",       r"^## .+$"),
            ("h3",       r"^### .+$"),
            ("checked",  r"- \[x\].*$"),
            ("checkbox", r"- \[ \].*$"),
            ("rule",     r"^---+$"),
            ("bold",     r"[*][*].+?[*][*]"),
            ("italic",   r"(?<![*])[*][^*]+[*](?![*])"),
            ("note_key", r"^[A-Za-z][A-Za-z ]+:"),
        ]

        text = ed.get("1.0", "end")
        for tag, pattern in patterns:
            for m in re.finditer(pattern, text, re.MULTILINE):
                start = f"1.0 + {m.start()} chars"
                end   = f"1.0 + {m.end()} chars"
                ed.tag_add(tag, start, end)

# ── Error dialog with copyable text ──────────────────────────────────────────

def _show_error_dialog(parent, exc_text, log_path):
    """Show a resizable error dialog with scrollable copyable traceback."""
    dlg = tk.Toplevel(parent)
    dlg.title("PTOS — Error")
    dlg.geometry("680x420")
    dlg.resizable(True, True)
    dlg.grab_set()  # modal

    # header
    hdr = tk.Frame(dlg, bg="#C0392B", pady=10)
    hdr.pack(fill="x")
    tk.Label(hdr, text="  An error occurred",
             font=("Segoe UI", 13, "bold"),
             fg="white", bg="#C0392B").pack(side="left", padx=12)

    # log path info
    info = tk.Frame(dlg, pady=6, padx=12)
    info.pack(fill="x")
    tk.Label(info, text=f"Details saved to:  {log_path}",
             font=("Segoe UI", 10), fg="#555").pack(anchor="w")

    # scrollable text area
    tf = tk.Frame(dlg, padx=12, pady=4)
    tf.pack(fill="both", expand=True)
    xsb = ttk.Scrollbar(tf, orient="horizontal")
    ysb = ttk.Scrollbar(tf, orient="vertical")
    txt = tk.Text(tf, font=("Consolas", 10), wrap="none",
                  bg="#1E2130", fg="#F8C8C8",
                  xscrollcommand=xsb.set, yscrollcommand=ysb.set,
                  padx=8, pady=6)
    xsb.config(command=txt.xview)
    ysb.config(command=txt.yview)
    ysb.pack(side="right", fill="y")
    xsb.pack(side="bottom", fill="x")
    txt.pack(side="left", fill="both", expand=True)
    txt.insert("end", exc_text)
    txt.config(state="normal")  # keep selectable for manual copy

    # buttons
    foot = tk.Frame(dlg, pady=8, padx=12)
    foot.pack(fill="x")

    def _copy():
        dlg.clipboard_clear()
        dlg.clipboard_append(exc_text)
        copy_btn.config(text="  Copied!  ")
        dlg.after(1500, lambda: copy_btn.config(text="  Copy to Clipboard  "))

    copy_btn = tk.Button(foot, text="  Copy to Clipboard  ",
                         command=_copy,
                         font=("Segoe UI", 11, "bold"),
                         bg=ACCENT, fg="white",
                         activebackground=ACCENT_HO,
                         relief="flat", padx=12, pady=6)
    copy_btn.pack(side="left")

    tk.Button(foot, text="  Close  ",
              command=dlg.destroy,
              font=("Segoe UI", 11),
              relief="flat", padx=12, pady=6).pack(side="right")

    dlg.wait_window()


# ══════════════════════════════════════════════════════════════════════════════
# Main window
# ══════════════════════════════════════════════════════════════════════════════

class PTOSApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("PTOS")
        self.geometry("1200x900")
        self.minsize(800, 600)
        self.configure(bg=BG)
        # Route Tkinter callback errors to our log+popup handler
        self.report_callback_exception = self._on_callback_error

        _setup_ttk_styles()
        self.option_add("*TCombobox*Listbox.font", F_BODY)
        self.option_add("*TCombobox*Listbox.background", ENTRY_BG)
        self.option_add("*TCombobox*Listbox.foreground", TEXT)
        self.option_add("*TCombobox*Listbox.selectBackground", ACCENT)
        self.option_add("*TCombobox*Listbox.selectForeground", "white")

        # ── top bar ───────────────────────────────────────────────────────────
        NAV_PILL  = "#EEF1FB"   # light blue-grey pill
        NAV_PILLO = "#DDE3F5"   # pill hover
        NAV_LINK  = ACCENT      # accent blue for link text

        topbar = tk.Frame(self, bg=CARD, pady=0)
        topbar.pack(fill="x")

        # bottom border line
        tk.Frame(topbar, bg=BORDER, height=1).pack(fill="x", side="bottom")

        # left — compact inline brand
        left = tk.Frame(topbar, bg=CARD, padx=HPAD, pady=8)
        left.pack(side="left")

        # PTOS + subtitle on one row
        row1 = tk.Frame(left, bg=CARD)
        row1.pack(anchor="w")
        tk.Label(row1, text="PTOS",
                 font=("Segoe UI", 15, "bold"),
                 fg=TEXT, bg=CARD).pack(side="left")
        tk.Label(row1, text="  Plain Text Operating System",
                 font=("Segoe UI", 11, "bold"),
                 fg=SUBTEXT, bg=CARD).pack(side="left", pady=(2, 0))

        # tagline on second row
        tk.Label(left, text="Log it. Query it. Own it.",
                 font=("Segoe UI", 10, "italic"),
                 fg=ACCENT, bg=CARD).pack(anchor="w")

        # right — github pill link
        right = tk.Frame(topbar, bg=CARD, padx=HPAD)
        right.pack(side="right", fill="y", pady=8)
        pill = tk.Frame(right, bg=NAV_PILL, padx=14, pady=8)
        pill.pack(anchor="center")

        link = tk.Label(pill,
                        text="⭐  github.com/godwinburby/ptos",
                        font=("Segoe UI", 11, "bold underline"),
                        fg=NAV_LINK, bg=NAV_PILL, cursor="hand2")
        link.pack()

        def _open(_=None):
            webbrowser.open("https://github.com/godwinburby/ptos")
        def _enter(_=None):
            link.config(bg=NAV_PILLO)
            pill.config(bg=NAV_PILLO)
        def _leave(_=None):
            link.config(bg=NAV_PILL)
            pill.config(bg=NAV_PILL)

        for w in (link, pill):
            w.bind("<Button-1>", _open)
            w.bind("<Enter>",    _enter)
            w.bind("<Leave>",    _leave)

        nb = ttk.Notebook(self)
        nb.pack(fill="both", expand=True)

        nb.add(AddRecordTab(nb), text="   + Add Record   ")
        nb.add(JournalTab(nb),   text="   Journal   ")
        nb.add(QueryTab(nb),     text="   Queries   ")
        nb.add(BrowseTab(nb),    text="   Browse   ")
        nb.add(LogEditorTab(nb), text="   Log Editor   ")

    def _on_callback_error(self, exc_type, exc_value, exc_tb):
        """Called by Tkinter when any callback raises — log and show popup."""
        exc_text = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
        LOG_PATH  = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                 "ptos_error.log")
        timestamp = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(f"\n{'='*60}\n{timestamp}\n{exc_text}\n")
        _show_error_dialog(self, exc_text, LOG_PATH)


if __name__ == "__main__":
    LOG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            "ptos_error.log")

    def _log_and_show(exc_text):
        """Write crash to log file and show a popup."""
        timestamp = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(f"\n{'='*60}\n{timestamp}\n{exc_text}\n")
        try:
            root = tk.Tk()
            root.withdraw()
        except Exception:
            root = None
        _show_error_dialog(root, exc_text, LOG_PATH)
        if root:
            root.destroy()

    try:
        app = PTOSApp()
        app.mainloop()
    except Exception:
        _log_and_show(traceback.format_exc())
