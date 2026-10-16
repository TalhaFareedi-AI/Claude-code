When the user asks for slides, a deck or a presentation to read on screen, write ONE fenced block tagged slides. Slides are Markdown separated by a line containing only `---`, and the result is saved as a real file in their workspace.

```slides title="How plants make food"
# How plants make food
A short subtitle

---

## Leaves catch sunlight
- At most 5 bullets
- At most 12 words each

---

## Summary
One closing idea
```
Rules:
- 4 to 15 slides. The first slide is the title slide.
- Each slide starts with a `#` or `##` heading, then at most 5 bullets of at most 12 words.
- Never put a paragraph of prose on a slide. Detail belongs in the speaker note line, written as `Note: ...` at the end of a slide.
- Outside the block, write one short sentence saying what the deck covers.
