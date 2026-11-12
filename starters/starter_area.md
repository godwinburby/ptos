# {{AREA_TITLE}}

Area page for **{{AREA}}** — tasks, notes, and records filtered to this area.

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

---

## Notes in this area

````ptos
view = "records"
where = "area={{AREA}} AND type=note"
time = "all"
title = "Notes in {{AREA_TITLE}}"
````