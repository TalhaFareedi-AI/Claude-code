---
name: sql-helper
description: Writes, explains or speeds up SQL queries and schema. Use when the user mentions SQL, a query, a join, an index, or a database table. Not for ORM-level application code.
---
1. Confirm the dialect (PostgreSQL, MySQL, SQLite, other) and the table shapes. Ask only if the answer depends on it.
2. Write the query readably: one clause per line, explicit column lists, explicit JOIN conditions. Never SELECT *.
3. Explain what each join and filter does to the row count.
4. For slowness: name the likely cause (missing index, function on an indexed column, N+1, wrong join order) and give the one change that fixes it.
5. Warn about NULL handling, ties, and whether the result is deterministic without ORDER BY.
Never claim a query was executed. For anything that deletes or updates, show the SELECT that previews the affected rows first.
