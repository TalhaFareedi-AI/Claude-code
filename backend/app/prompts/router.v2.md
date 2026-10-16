Classify the message for a task router. Reply with one JSON object and nothing else.

{"intent":"teach|solve|make_ppt|make_doc|research|code|chat","needs":["chart","diagram","quiz"],"complexity":"easy|medium|hard","make_plan":false}

intent: what the user wants done. "chat" only for greetings and small talk.
needs: include an item ONLY if the user clearly wants that artifact. Empty list is the normal case.
complexity:
- easy: a greeting, a single fact, a definition, a rewrite, or anything answerable in under 100 words.
- medium: one topic needing explanation, a calculation, or a short piece of code.
- hard: several linked parts, a proof or derivation, a document or deck, a comparison needing evidence, or a build task.
make_plan: true only when the work needs 3 or more dependent steps.

When torn between two labels, pick the cheaper one (easy over medium, medium over hard, make_plan false).
Output JSON only. No prose, no code fence.
