# Study Harness

A study chatbot built from the *Chatbot Harness and Platform Plan*: a manager (the **harness**) around the AI,
and a website with a credit wallet (the **platform**). Every AI call goes through OpenRouter.

```
backend/app    FastAPI server, harness, 10 modes, wallet, charts, file builders
frontend       the screen (plain HTML, CSS and JavaScript, no build step, no CDN)
backend/tests  54 tests (a local fake OpenRouter is used, so they cost nothing)
scripts        live_test.py (real OpenRouter) and ui_check.cjs (real browser)
```

## Run it

```bash
pip install -r requirements.txt
cp .env.example .env          # then put your key in .env (git ignores this file)
uvicorn app.main:app --app-dir backend --port 8000
```
Open http://localhost:8000. With `DEV_MODE=1` the sidebar has a "Test as plan" switch and a "+500 credits" button.

## Test it

```bash
python -m pytest                        # 54 tests, no network, no cost
python backend/tests/demo_server.py     # the real app on port 8765, backed by the fake OpenRouter
node scripts/ui_check.cjs               # 19 checks in a real browser against that server
python scripts/live_test.py --quick     # REAL OpenRouter: key check, model sync, one call, cost check
python scripts/live_test.py             # REAL OpenRouter: every mode on the cheapest brains
```

`BRAIN_POLICY=cheap` (the default for now) makes every brain slot use the cheapest Quick or Smart model, so tests
cost almost nothing. Set `BRAIN_POLICY=preferred` to use the plan's tiers (Quick, Smart, Genius) as written.

## What is built (plan section in brackets)

| Piece | Where |
| --- | --- |
| One OpenRouter door: `usage.cost` billing, reasoning rules, `data_collection: deny`, fallbacks, streaming [3, 8, 10] | `openrouter.py` |
| Live model catalog, nightly price sync, 20% drift alarm, new models wait for approval [8, 10] | `catalog.py` |
| Credits = `ceil(cost x 1.055 / 0.003)`, ledger, hold then settle, daily cap [9] | `pricing.py`, `wallet.py` |
| Live estimates for every mode, matching the plan's worked examples [9] | `estimate.py` |
| Fast, Normal, Deep, Think Again, Overthink, Council, Two Brains, Think Team, Research, Developer [3] | `runners.py`, `modes.py` |
| Rules-first router, planner, checker (2 fix tries), teacher layer, three stops [3] | `harness.py`, `postprocess.py` |
| Safe formula engine and chart recipes, charts that move with 0 tokens [5] | `formula.py`, `charts.py`, `frontend/js/charts.js` |
| PPT and Word builders, edit "make slide 3 simpler" as version 2 [6] | `tools/` |
| 7 skills, headers always visible, recipe opened only when needed [13] | `skills/`, `skills.py` |
| Prompt library with versions (`name.v1.md`) [4] | `prompts/` |
| Live run card, files panel, effort, brain, cost cap pickers, phone sheets [14] | `frontend/` |
| One private folder per user and task, path checks, signed expiring links, upload checks [14] | `workspace.py`, `main.py` |

## Not built yet (so you know)

Payments (Stripe, Toss), real accounts and login (a cookie id is used), image generation, MCP servers, the
sandboxed mini-app iframe (Level B charts), Langfuse, promptfoo test set, PPT page-image previews (LibreOffice),
virus scanning of uploads (type and signature checks only), and a safety filter on messages and answers.
