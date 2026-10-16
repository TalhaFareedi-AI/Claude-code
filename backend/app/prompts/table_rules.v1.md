When the answer compares things or holds more than three rows of data, write ONE fenced block tagged table:
```table
{"title":"Plan comparison","columns":[{"key":"plan","label":"Plan"},{"key":"price","label":"Price","type":"number","unit":"$"},{"key":"credits","label":"Credits","type":"number"}],"rows":[{"plan":"Free","price":0,"credits":100}]}
```
Rules: 2 to 8 columns, 1 to 60 rows. Every row must use the same keys as "columns". Use type "number" for anything sortable as a number, and put units in "unit", never inside the value. Keep cell text under 120 characters. The browser makes it sortable, so do not repeat the table as prose; add one sentence saying what it shows.
