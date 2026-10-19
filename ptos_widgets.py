"""Widget kind registry.

Registry mechanics only — kinds, view aliases, per-kind allowed spec
keys, and name-ownership predicates used to infer a kind from a bare
`name`. Resolvers are registered by ptos_service (which owns the data
functions), so the import direction stays ptos_service -> ptos_widgets
and this module imports nothing from the product.

Every entry's allowed keys are COMMON_KEYS plus its own:
view, name, time, from_date, to_date, title, limit.
"""

COMMON_KEYS = frozenset({
    "view", "name", "time", "from_date", "to_date", "title", "limit",
})

# Row caps applied by the widgets batch-resolve path; the legacy
# /api/embed/resolve endpoint deliberately keeps its unlimited behavior.
DEFAULT_ROW_LIMIT = 100
MAX_ROW_LIMIT = 500

_WIDGETS = {}       # canonical kind -> entry
_VIEW_ALIASES = {}  # view name -> canonical kind


def register(kind, resolve, views=(), keys=(), needs_name=True,
             infer_order=99, owns_name=None):
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
    """
    if not callable(resolve):
        raise ValueError(f"widget {kind!r}: resolve must be callable")
    if not str(kind).strip():
        raise ValueError("widget kind must be a non-empty name")
    entry = {
        "kind": str(kind).strip().lower(),
        "resolve": resolve,
        "keys": frozenset(keys),
        "needs_name": bool(needs_name),
        "infer_order": infer_order,
        "owns_name": owns_name,
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
