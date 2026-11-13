# {{AREA_TITLE}}

Area page for **{{AREA}}** — tasks, notes, and records filtered to this area.

---

## Now

````ptos
view = "todo"
area = "{{AREA}}"
title = "Now"
add = true
````

---

## Plan

````ptos
view = "records"
where = "area={{AREA}}"
time = "all"
title = "Plan — {{AREA_TITLE}}"
````

### Quarter

````ptos
view = "records"
where = "area={{AREA}}"
time = "tq"
title = "This Quarter"
limit = 20
````

### Year

````ptos
view = "records"
where = "area={{AREA}}"
time = "ty"
title = "This Year"
limit = 20
````

### Someday

````ptos
view = "records"
where = "area={{AREA}}"
time = "all"
title = "Someday"
limit = 20
````

---

## Log

````ptos
view = "records"
where = "area={{AREA}}"
time = "td"
title = "Log — Today"
limit = 20
````

---

## Reflections

````ptos
view = "records"
where = "area={{AREA}}"
time = "all"
title = "Reflections — {{AREA_TITLE}}"
````

---

## Reviews

### Weekly Review

````ptos
view = "records"
where = "area={{AREA}}"
time = "tw"
title = "Weekly Review"
limit = 20
````

### Monthly Review

````ptos
view = "records"
where = "area={{AREA}}"
time = "lm"
title = "Monthly Review"
limit = 20
````

### Quarterly Review

````ptos
view = "records"
where = "area={{AREA}}"
time = "lq"
title = "Quarterly Review"
limit = 20
````

---

## Tasks

````ptos
view = "todo"
area = "{{AREA}}"
add = true
title = "Tasks in {{AREA_TITLE}}"
limit = 20
````

---

## Records

````ptos
view = "records"
where = "area={{AREA}}"
time = "tm"
title = "Records in {{AREA_TITLE}}"
limit = 20
````

