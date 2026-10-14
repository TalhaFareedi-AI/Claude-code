---
name: prompt-smith
description: Turns a rough idea into a clear prompt plus 5 test cases. Use when the user wants to write or improve a prompt.
---
1. Ask what good output looks like if it is not clear.
2. Write the prompt: role, task, input format, output format (a JSON shape if code reads it), and 2 rules for edge cases.
3. Write 5 test cases: 2 normal, 2 tricky, 1 that should be refused.
4. Say how to score each test (correct, simple, cost).
