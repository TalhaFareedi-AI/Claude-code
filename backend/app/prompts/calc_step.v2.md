List every calculation this step needs. Reply with one JSON object and nothing else.

{"calcs":[{"label":"what this number is","expr":"1000*(1+5/100)^2"}]}

- "expr" must be pure arithmetic a calculator can evaluate: digits, + - * / ^ ( ) and sqrt sin cos tan ln log exp abs min max pi. No variables, units, commas, currency signs or words.
- Substitute the real numbers from the task into the expression yourself.
- One entry per number the answer needs. At most 8. Order them so a reader could follow.
- If the step needs no arithmetic, return {"calcs":[]}.

Real numbers only, no symbols. JSON only.
