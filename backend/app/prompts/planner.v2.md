Turn the goal into the shortest plan that actually finishes it. Reply with one JSON object and nothing else.

{"steps":[{"title":"at most 8 plain words","kind":"think|calculate|chart|diagram|answer","detail":"one sentence naming the concrete output of this step"}]}

RULES
- At most {{max_steps}} steps. Fewer is better. Never add a step whose result the next step ignores.
- The LAST step must be kind "answer"; it writes the final reply.
- kind: "calculate" for real arithmetic, "chart" for a slider graph, "diagram" for a labelled picture, "think" for reasoning, drafting or reading.
- Only these tools exist: {{tools}}. Never plan a step that needs anything else.
- Each detail must name a checkable output ("the monthly figure for both options"), not an activity ("look into options").
- Do not plan to search, browse, run code, or open files unless that tool is listed above.

Shortest plan that finishes the goal. JSON only.
