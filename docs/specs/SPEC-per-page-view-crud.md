# SPEC: Per-page view CRUD (decentralize Query Builder)

**Project:** PTOS  
**Priority:** High (UX clarity)  
**Status:** Spec for implementation  
**Related:** Projects page already owns project CRUD; Query Builder remains for analytics + advanced  

**Update:** Thresholds CRUD lives on **`/thresholds`** (Phase 1 with boards + habits), not only in Query Builder.

---

## Problem

The **Query Builder** is a monolithic page that CRUDs almost every view kind stored in `queries.toml`:

- boards, habits, calendars, due sections, todo views, projects (partially),  
- plus queries, metrics, dashboards, **thresholds**, etc.

Users **use** views on domain pages (`/board`, `/habits`, `/calendar`, `/thresholds`, …) but must **configure** them in one crowded QB UI. That is confusing and does not match the **Projects** pattern, where project CRUD lives on the projects page.

**Thresholds** are viewed and evaluated on `/thresholds` today, but create/edit/delete still forces a trip through QB — same problem as boards/habits.

---

## Goals

| Goal | Detail |
|------|--------|
| Domain ownership | Each feature page owns create / edit / delete / list of **its** view configs |
| Match Projects | Same UX idea as project CRUD on the projects page |
| Thresholds on `/thresholds` | Status UI **plus** full CRUD for threshold definitions |
| No storage rewrite | Keep `queries.toml` (and existing service save APIs) as source of truth |
| One write path | In-page UI calls the **same** service functions QB uses — no divergent writers |
| Slim QB | Query Builder becomes **queries / metrics / dashboards + advanced**, not the only place for boards / habits / thresholds / … |
| Discoverability | From a domain page, user never needs QB for basic CRUD |

## Non-goals

- Redesigning `queries.toml` schema  
- Removing Query Builder entirely  
- Moving **record queries / metrics / dashboards** off `/queries` + QB (they stay analytics-centric)  
- Moving **query/metric authoring** onto the thresholds page (thresholds only **reference** them)  
- New permission model  
- Full visual QB redesign beyond what each page needs for its forms  

---

## Target IA

| Route / area | Owns CRUD for | Notes |
|--------------|---------------|--------|
| `/projects` | `["project.NAME"]` | **Already the reference pattern** |
| `/board` (or boards index) | `["board.NAME"]` | List boards, new/edit/delete, then open board |
| `/habits` | `["habit.NAME"]` | |
| **`/thresholds`** | **Threshold definitions** (same store as today) | List + **live status** + **New / Edit / Delete**; link to underlying query/metric |
| `/calendar` | `["calendar.NAME"]` | Include `__all__` / built-ins only if already special-cased |
| `/due` | `["due.NAME"]` | |
| `/todo` | `["todo.NAME"]` saved views | If todo views exist in product |
| `/queries` + Query Builder | Record **queries**, **metrics**, **dashboards** | Primary analytics surface |
| Query Builder “Advanced” (optional) | Any kind | Power users; bulk; deep links from domain pages |

**Home / Pages embeds** keep using existing widget resolve; new views created in-page must appear in embed pickers (same `queries.toml`).

---

## Phased delivery

### Phase 1 — Boards + Habits + Thresholds

1. **Boards page**
   - List configured boards (name, title/label if any).  
   - Actions: New, Edit, Delete, Open (run board).  
   - New/Edit: form fields aligned with current QB board editor (columns, filters, time, set_field/status, etc. — **reuse field set**, don’t invent a second schema).  
   - Delete: confirm; call existing delete/save service; block or warn if in use only if product already does.

2. **Habits page**
   - Same pattern for habits (fields = current habit editor).

3. **Thresholds page**
   - Keep existing status / evaluation UI.  
   - Add **New / Edit / Delete** for threshold definitions (fields = current QB threshold editor: name, target query or metric, limits/comparators, labels, etc.).  
   - Reuse existing threshold save/delete service paths; **no second writer**.  
   - Thresholds may **reference** a query or metric — those base objects still CRUD on `/queries` (QB). Only the **threshold rule** is owned on `/thresholds`.  
   - If no query/metric exists yet, UI may link “Create query” → `/queries` without embedding full query CRUD on the thresholds page.  
   - After save/delete: refresh status list on `/thresholds`.

4. **QB (after in-page parity)**
   - Remove or hide **primary** board / habit / **threshold** CRUD tabs from default QB UX.  
   - Optional: read-only list with links “Manage on Boards / Habits / Thresholds page”.

### Phase 2 — Calendars + Due (+ Todo views)

- Same pattern for `["calendar.NAME"]`, `["due.NAME"]`, and `["todo.NAME"]` if present.

### Phase 3 — QB slim + navigation polish

- QB default tabs: **Queries, Metrics, Dashboards** (thresholds are not primary CRUD here).  
- Optional Advanced section listing other kinds with links to domain pages.  
- Sidebar/nav: update copy where “Query Builder” implied “configure everything.”  
- CHANGELOG + AGENTS/README note: where to create a board, habit, or **threshold**.

---

## Technical requirements

### Service layer

- **Reuse** existing functions used by Query Builder (`save_board`, `save_habit`, threshold save/delete, `save_queries_full` slices, validation, lint).  
- Do **not** duplicate TOML write logic in the web routes.  
- In-page forms call kind-specific endpoints or the same endpoints with the same payloads as QB.

### Web routes

| Pattern | Example |
|---------|---------|
| List + manage UI | `GET /board` includes manage section; `GET /thresholds` includes manage + status |
| Create/update | `POST` existing or thin wrappers |
| Delete | Existing delete with CSRF/session same as QB |
| Run/use | Keep current board/thresholds URLs and deep links |

Exact paths may match current app; implementer must **not** break existing deep links.

### UI

- Prefer **panel/modal or dedicated section** on the domain page (mobile-friendly), not a second full QB clone.  
- Validation errors shown on the domain page.  
- After save: stay on domain page; toast/banner success; list refreshes.  
- After delete: remove from list; if user was viewing that board, redirect to list or default.  
- Thresholds: form + status on one page is expected (configure and monitor together).

### Embeds / slash / gallery

- New boards / habits / **thresholds** must appear in embed candidates and widget gallery without extra registration (same queries.toml read path).  
- No separate embed catalog file.

### Auth / safety

- Same auth as QB write routes.  
- Same path containment and name validation as existing saves.  
- No silent overwrite without the same rules QB uses for name collisions.

---

## Query Builder after migration

| Still in QB (primary) | Not primary in QB (manage on domain page) |
|-----------------------|-------------------------------------------|
| Queries (records filters, group, pivot, trend) | Boards → `/board` |
| Metrics | Habits → `/habits` |
| Dashboards | **Thresholds → `/thresholds`** |
| Optional Advanced | Calendars, Due, Todo views, Projects (already on `/projects`) |

Deleting the QB route is **out of scope**.

**Threshold detail:** Creating a threshold on `/thresholds` may require picking an existing query/metric name. Do not move query/metric CRUD onto the thresholds page.

---

## Data / config

- Source of truth remains **`config/queries.toml`** (or whatever path `get_queries` / threshold helpers use).  
- Starters may include example boards / habits / thresholds; in-page create must not break starters.  
- `--lint` / doctor rules for boards / habits / thresholds unchanged.

---

## Testing

### Required (Phase 1)

1. **Create** board from Boards page → appears in list → opens with correct columns.  
2. **Edit** board → persists after reload; QB advanced (if still lists it) shows same data.  
3. **Delete** board → gone from list and from `queries.toml` section.  
4. Same three for **habit**.  
5. Same three for **threshold** on `/thresholds` (status UI still evaluates correctly after create/edit).  
6. Embed picker / `get_embed_candidates` includes new board / habit / threshold.  
7. Existing deep links to run a board / open thresholds still work.  
8. Unauthorized/anonymous write rejected same as today.  
9. Regression: save query / metric / dashboard from QB still works.

### Phase 2+

- Parallel tests for calendar, due, todo views.

### Manual

- Mobile: create habit or threshold on phone; use on the domain page.  
- Syncthing: create board/threshold on device A, appears on device B after sync (file-level; no extra work if toml write is same).

---

## Acceptance criteria

- [ ] User can create, edit, and delete a **board** without opening Query Builder.  
- [ ] User can create, edit, and delete a **habit** without opening Query Builder.  
- [ ] User can create, edit, and delete a **threshold** on **`/thresholds`** without opening Query Builder.  
- [ ] Threshold status continues to work after in-page edits.  
- [ ] Writes go through the **same service/TOML path** as before (no dual writers).  
- [ ] Projects pattern remains the UX reference.  
- [ ] Query Builder still supports **queries / metrics / dashboards** (threshold CRUD not required as primary there).  
- [ ] Phase 1 complete before removing board / habit / threshold primary editors from QB default UI.  
- [ ] Tests cover create/edit/delete for board, habit, and threshold from the new entry points.  
- [ ] CHANGELOG documents the IA change (including thresholds on `/thresholds`).

---

## Implementation order

1. Inventory current QB save/delete endpoints and form fields for **board**, **habit**, and **threshold**.  
2. Add manage UI to `/board`, `/habits`, and **`/thresholds`** reusing those endpoints/partials.  
3. Wire list of configs on each page (thresholds: alongside status).  
4. Tests for all three kinds.  
5. Hide/relocate QB board / habit / threshold tabs; add links to domain pages.  
6. Phase 2 kinds.  
7. Copy / docs / CHANGELOG.

---

## Copy guidelines

- Prefer: “New board”, “Edit habit”, “New threshold”, “Delete threshold” on the domain page.  
- Avoid: “Open Query Builder to add a threshold” as the primary CTA.  
- Optional secondary: “Advanced configuration” → QB only if a field is not yet on the in-page form.  
- Threshold form: “Based on query/metric” with link to Queries if empty.

---

## Summary for implementer

> **Configure each view kind where it is used.**  
> Boards on the board page, habits on the habits page, **thresholds on the thresholds page** (like projects on the projects page).  
> Keep `queries.toml` and existing save services; move **entry points and forms**, not the data model.  
> Thresholds **reference** queries/metrics; they do not absorb query CRUD.  
> Narrow Query Builder to **queries / metrics / dashboards** (+ optional advanced).  
> **Phase 1 = boards + habits + thresholds** with tests and parity before stripping QB.
