Score an answer. Reply with one JSON object and nothing else.

{"score":1,"problems":["specific, fixable problem"]}

SCALE
- 9-10: correct, complete, nothing a careful reader would change.
- 8: correct and complete; only taste separates it from perfect. This is the pass mark.
- 6-7: usable but has a real gap or an unclear step.
- 3-5: a wrong claim, a missing required part, or reasoning that does not follow.
- 1-2: answers the wrong question, or is mostly invented.

RULES
- Check the numbers and the logic yourself before scoring.
- At most 4 problems. Each must be specific and fixable in a rewrite ("the 1.05^2 step is applied once, not twice"), never vague ("could be clearer").
- Do not lower the score for being short, plain, or missing an analogy.
- If you find no real defect, score 8 or above and return an empty list. Do not invent a problem to look useful.

Score correctness first, then completeness. JSON only.
