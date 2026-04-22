# PTOS Records Schema

Format:
YYYY-MM-DD key:value key:value +project | optional_note

Rules:
- Date must be first token
- One event per line
- Structured fields before pipe
- No spaces in structured values
- Append-only

Allowed Keys:

Clinic:
- type:
- client:
- outcome:
- model:
- value:
- issue:
- source:

Expense:
- type:expense
- category:
- amount:
- mode:
- +personal
- +company