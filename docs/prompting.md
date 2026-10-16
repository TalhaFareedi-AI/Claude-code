# How the prompts, skills and tools are built

Every prompt lives in `backend/app/prompts/` as `name.vN.md`. The loader picks the highest version, so a
prompt can be rewritten without touching code, and the old one stays readable in git. Nothing is inlined in
Python any more: `team.py` used to carry six prompts in string literals, which meant improvements never
reached the team path.

## What the research says, and what we did about it

| Finding | Where it came from | What the code does |
| --- | --- | --- |
| Instructions at the start and end are followed most; material buried in the middle is missed ("lost in the middle") | summarised from Liu et al. 2024 in practitioner guides | Every role prompt opens with its hard rules and closes by repeating the two that matter most ("JSON only", "never invent facts"). |
| Elaborate role-play framing adds little on current models; lean structured prompts do more | 2026 practitioner guides | No "you are a world-class expert" openers. Each prompt is a short contract: what to produce, the rules, the failure cases. |
| Chain-of-thought helps real multi-step reasoning and hurts simple tasks | same | Thinking is a per-role dial (`reasoning` in `modes.py`), off for routing, checking and answering from notes. No prompt says "think step by step" unconditionally. |
| Tool descriptions should say what it returns and **when not to use it**; typed, constrained parameters | [Anthropic, writing tools for agents](https://www.anthropic.com/engineering/writing-tools-for-agents) | Every skill description now ends with "Use when ... Not for ..., which is <other skill>". A test enforces it. |
| Return filtered or summarised tool results, not raw payloads | token-efficiency guides | Step results are trimmed before they re-enter the context; chart, table and flashcard data is validated and handed to the browser instead of being re-described in prose. |
| Progressive disclosure: preload only name and description, load the body on demand | [Anthropic skill authoring](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices) | 19 skills: only the one-line headers are ever shown to the picker, and a keyword match usually avoids even that. One body averages 138 tokens against 2,640 for all of them. |
| Context management matters most when the window is tight; eliding before summarising is the cheapest strategy | [An Empirical Study of Harness Design for Coding Agents](https://arxiv.org/abs/2609.20804) | The desk keeps the last 8 messages verbatim, elides older ones into session notes, and only then pays for a summary. |
| Harness value depends on model strength and task type; complex scaffolding gives diminishing returns on simple tasks | [Beyond the Model: Demystifying Harness Effects](https://arxiv.org/abs/2609.32459) | Planning is off for Fast and Normal and only switches on for bigger work, and the router is told to pick the cheaper label when torn. |

## Token budget

Run `python scripts/token_report.py` for the current numbers, or `--live` to spend a fraction of a cent and
see real usage per mode. At the time of writing:

- default system prompt: ~366 tokens. Chart, table and flashcard rules (~600 more) load only when that artifact is wanted.
- skills: ~138 tokens for the one body that gets loaded, instead of ~2,640 for all of them.
- Anthropic models get an explicit `cache_control` mark on the system prefix, so a repeat within the cache
  window is billed at a fraction of the input price. Other labs cache on their own, so marking them would only add noise.

## Teaching mode is opt-in

`teacher_enabled` defaults to **false**. The default prompt (`direct.v1.md`) answers at the user's own level
and is explicitly forbidden from adding analogies, lessons, praise or a closing question. `teacher.v2.md` is
used only when the user turns Teaching mode on in Settings → Build and check.

A greeting gets neither the learning profile nor saved memories on the desk: both used to read as the current
task, which made "hi" answer the previous chat's question.
