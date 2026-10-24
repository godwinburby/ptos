"""Widget kind registry.

Registry mechanics only — kinds, view aliases, per-kind allowed spec
keys, name-ownership predicates used to infer a kind from a bare
`name`, and the gallery metadata (label/description/icon/category/
named/fields/starters/interactive_default) the widget form reads.
Resolvers are registered by ptos_service (which owns the data
functions), so the import direction stays ptos_service -> ptos_widgets
and this module imports nothing from the product.

Every entry's allowed keys are COMMON_KEYS plus its own:
view, name, time, from_date, to_date, title, limit, span, hide_on, live.
`span` (1 or 2) and `hide_on` (["phone"]/["desktop"]) are home-layout
keys; markdown preview embeds mount interactively by default, and
`live = false` opts out. When a kind provides `fields`, their keys must
cover that allowed-key set exactly — enforced at registration so the form
and the whitelist can never drift apart.
"""

import re

COMMON_KEYS = frozenset({
    "view", "name", "time", "from_date", "to_date", "title", "limit",
    "span", "hide_on", "live",
})

# Gallery categories, in display order (the client merges its own
# Text block category onto this list).
CATEGORIES = (
    {"id": "tasks", "label": "Tasks and reminders"},
    {"id": "tables", "label": "Tables and records"},
    {"id": "numbers", "label": "Numbers and charts"},
    {"id": "goals", "label": "Goals and habits"},
    {"id": "capture", "label": "Capture"},
    {"id": "projects", "label": "Projects"},
)

FIELD_TYPES = ("text", "number", "bool", "select", "multiselect", "chips",
               "time_window", "saved_item", "record_type", "field_filter")

# Row caps applied by the widgets batch-resolve path; the legacy
# /api/embed/resolve endpoint deliberately keeps its unlimited behavior.
DEFAULT_ROW_LIMIT = 100
MAX_ROW_LIMIT = 500

_WIDGETS = {}       # canonical kind -> entry
_VIEW_ALIASES = {}  # view name -> canonical kind


def register(kind, resolve, views=(), keys=(), needs_name=True,
             infer_order=99, owns_name=None, label=None, description=None,
             icon=None, category=None, named=False, fields=(),
             starters=(), interactive_default=False, quick_add=False):
    """Register one widget kind (re-registration replaces the entry,
    so an importlib.reload of the registering module stays safe).

    kind         canonical kind name (dispatched as view == kind)
    resolve      callable(spec, name, time, from_date, to_date)
                 -> (result_dict, link); the dispatcher attaches
                 title/link/limit on top
    views        extra view names routed to this kind
    keys         kind-specific allowed spec keys (added to COMMON_KEYS)
    needs_name   kind requires spec["name"] (path-based kinds set False)
    infer_order  position in the name->kind scan (lower wins first);
                 99 = never inferred
    owns_name    callable(name, queries) -> bool, used during inference
    label/description/icon
                 gallery card text (label defaults to the kind name)
    category     one of CATEGORIES ids (or None for test-only kinds)
    named        kind's second gallery step lists saved items
    fields       form-field dicts: key, label, type (FIELD_TYPES),
                 plus optional help, default, required, advanced,
                 show_if (False = never shown), options, options_from.
                 When provided their keys must equal the allowed-key
                 set exactly (ValueError otherwise).
    starters     ready-made configs: id, label, description, body (TOML)
    interactive_default
                 mount with interactive actions on home by default
    quick_add    skip the configure step when adding this widget
    """
    if not callable(resolve):
        raise ValueError(f"widget {kind!r}: resolve must be callable")
    if not str(kind).strip():
        raise ValueError("widget kind must be a non-empty name")
    kind = str(kind).strip().lower()
    if category is not None and category not in {c["id"] for c in CATEGORIES}:
        raise ValueError(
            f"widget {kind!r}: unknown category {category!r} "
            f"(expected one of {', '.join(c['id'] for c in CATEGORIES)})")
    fields = tuple(dict(f) for f in (fields or ()))
    for f in fields:
        if not str(f.get("key") or "").strip():
            raise ValueError(f"widget {kind!r}: field key must be a non-empty name")
        if f.get("type") not in FIELD_TYPES:
            raise ValueError(
                f"widget {kind!r}: field {f['key']!r} has unknown type "
                f"{f.get('type')!r}")
    if fields:
        declared = {f["key"] for f in fields}
        expected = COMMON_KEYS | {str(k) for k in keys}
        if declared != expected:
            missing = sorted(expected - declared)
            extra = sorted(declared - expected)
            parts = []
            if missing:
                parts.append(f"missing fields for keys: {', '.join(missing)}")
            if extra:
                parts.append(f"fields with no matching key: {', '.join(extra)}")
            raise ValueError(f"widget {kind!r}: " + "; ".join(parts))
    starters = tuple(dict(s) for s in (starters or ()))
    for s in starters:
        if not str(s.get("id") or "").strip():
            raise ValueError(f"widget {kind!r}: starter id must be a non-empty name")
        if not str(s.get("body") or "").strip():
            raise ValueError(
                f"widget {kind!r}: starter {s.get('id')!r} needs a TOML body")
    entry = {
        "kind": kind,
        "resolve": resolve,
        "keys": frozenset(keys),
        "needs_name": bool(needs_name),
        "infer_order": infer_order,
        "owns_name": owns_name,
        "label": str(label).strip() if label else kind.replace("_", " ").title(),
        "description": str(description or ""),
        "icon": str(icon or ""),
        "category": category,
        "named": bool(named),
        "fields": fields,
        "starters": starters,
        "interactive_default": bool(interactive_default),
        "quick_add": bool(quick_add),
    }
    _WIDGETS[entry["kind"]] = entry
    for v in (entry["kind"],) + tuple(views):
        _VIEW_ALIASES[str(v).strip().lower()] = entry["kind"]
    return entry


def get_kind(view):
    """Entry for a view name (canonical or alias), or None."""
    kind = _VIEW_ALIASES.get(str(view or "").strip().lower())
    return _WIDGETS.get(kind) if kind else None


def kinds():
    """Registered entries in infer_order, then name (stable for tests)."""
    return sorted(_WIDGETS.values(), key=lambda e: (e["infer_order"],
                                                    e["kind"]))


def allowed_keys(entry):
    """Full allowed-key set for an entry."""
    return COMMON_KEYS | entry["keys"]


def unknown_keys(entry, spec):
    """Spec keys this kind does not accept, sorted."""
    return sorted(set(spec) - allowed_keys(entry))


def field_map(entry):
    """{key: field dict} for an entry's form fields."""
    return {f["key"]: f for f in entry.get("fields") or ()}


def field_errors(entry, spec, include_required=True):
    """Metadata-driven checks for a spec: [{field, message}].

    Pure and data-free — type/select membership for keys present in
    `spec`, plus (when include_required) a missing-value error for each
    required field. The resolver keeps its own domain checks; these are
    the same rules the gallery form shows inline.
    """
    errs = []
    if not isinstance(spec, dict):
        return errs
    fmap = field_map(entry)
    for key, value in spec.items():
        f = fmap.get(key)
        if not f:
            continue
        errs.extend(_value_errors(f, value))
    if include_required:
        for f in entry.get("fields") or ():
            if not f.get("required"):
                continue
            if f["key"] not in spec or spec[f["key"]] in ("", None, ()):
                errs.append({"field": f["key"],
                             "message": f"{f.get('label', f['key'])} is required"})
    return errs


def runtime_field_errors(entry, spec):
    """Checks whose generic metadata rule must also guard widget rendering.

    Most enums and compound fields have kind-specific runtime checks with
    established error messages. Numeric bounds and todo priority shape have
    no such downstream guard, so they share the exact form validator here.
    """
    errs = []
    if not isinstance(spec, dict):
        return errs
    for key, value in spec.items():
        field = field_map(entry).get(key)
        if not field:
            continue
        if field.get("min") is not None or field.get("max") is not None or \
                field.get("options_from") == "todo.priorities":
            errs.extend(_value_errors(field, value))
    return errs


def _value_errors(f, value):
    label = f.get("label", f["key"])
    t = f.get("type")
    if t == "number":
        label = f"{label} ({f['key']})"
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return [{"field": f["key"], "message": f"{label} must be a number"}]
        if f.get("min") is not None and value < f["min"]:
            return [{"field": f["key"],
                     "message": f"{label} must be at least {f['min']}"}]
        if f.get("max") is not None and value > f["max"]:
            return [{"field": f["key"],
                     "message": f"{label} must be at most {f['max']}"}]
    elif t == "bool":
        if not isinstance(value, bool):
            return [{"field": f["key"],
                     "message": f"{label} must be true or false"}]
    elif t == "select":
        opts = f.get("options") or ()
        if opts and value not in opts:
            return [{"field": f["key"],
                     "message": f"{label} must be one of: "
                                + ", ".join(str(o) for o in opts)}]
    elif t in ("chips", "multiselect"):
        if f.get("options_from"):
            if f.get("options_from") == "todo.priorities":
                vals = list(value) if isinstance(value, (list, tuple)) else [value]
                if any(not isinstance(v, str) or
                       re.fullmatch(r"[A-Z]", v) is None for v in vals):
                    return [{"field": f["key"],
                             "message": f"{label} ({f['key']}) must be letters A-Z"}]
            return []
        opts = f.get("options") or ()
        if not opts:
            return []
        vals = list(value) if isinstance(value, (list, tuple)) else [value]
        if any(v not in opts for v in vals):
            return [{"field": f["key"],
                     "message": f"{label} must be one of: "
                                + ", ".join(str(o) for o in opts)}]
    elif t in ("text", "saved_item", "record_type", "field_filter",
               "time_window"):
        if not isinstance(value, str):
            return [{"field": f["key"], "message": f"{label} must be text"}]
    return []


def catalog_entry(entry):
    """JSON-ready gallery metadata for one kind."""
    return {
        "kind": entry["kind"],
        "label": entry.get("label") or entry["kind"],
        "description": entry.get("description") or "",
        "icon": entry.get("icon") or "",
        "category": entry.get("category"),
        "named": bool(entry.get("named")),
        "needs_name": entry["needs_name"],
        "interactive_default": bool(entry.get("interactive_default")),
        "quick_add": bool(entry.get("quick_add")),
        "fields": [dict(f) for f in entry.get("fields") or ()],
    }


def starters_for(entry):
    """Starter configs for one kind (id/label/description/body)."""
    return [dict(s) for s in entry.get("starters") or ()]


def infer_kinds(name, queries):
    """Kinds whose owns_name claims `name`, in inference order.

    Mirrors the historical resolution order: dashboard -> metric ->
    threshold -> board -> habit -> calendar -> due -> project -> query.
    Callers treat a length != 1 result as missing/ambiguous.
    """
    hits = []
    for entry in kinds():
        if entry["infer_order"] >= 99 or entry["owns_name"] is None:
            continue
        if entry["owns_name"](name, queries):
            hits.append(entry["kind"])
    return hits
