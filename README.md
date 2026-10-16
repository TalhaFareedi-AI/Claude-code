# Study Harness

A study chatbot built from the *Chatbot Harness and Platform Plan*: a manager (the **harness**) around the AI,
and a website with a credit wallet (the **platform**). Every AI call goes through OpenRouter.

```
backend/app    FastAPI server, harness, 10 modes, wallet, charts, file builders
frontend       the screen (plain HTML, CSS and JavaScript, no build step, no CDN)
backend/tests  unit and integration tests (a local fake OpenRouter is used, so they cost nothing)
scripts        live_test.py (real OpenRouter) and ui_check.cjs (real browser)
```

## Run it

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # then put your key in .env (git ignores this file)
uvicorn app.main:app --app-dir backend --port 8000
```
Open http://localhost:8000. With `DEV_MODE=1` the sidebar has a "Test as plan" switch and a "+500 credits" button.

Model IDs in the plan are examples. On a fresh database, live sync may retire them and hold newly discovered models
for approval. If the model picker is empty, configure a private `ADMIN_TOKEN`, restart the app, and use the admin API
with an `x-admin-token` header: POST `/api/admin/catalog/sync`, GET `/api/admin/catalog`, then POST
`/api/admin/catalog/approve` with `{"model_id":"an exact live ID","tier":"quick","on":true}`. Approve suitable
Quick, Smart and Genius models after checking their actual prices and capabilities. Unknown models are never
automatically approved. Keep the token in secure settings and out of command history and committed files.

## Test it

```bash
python -m pytest                        # backend unit/integration tests, no network, no cost
python backend/tests/demo_server.py     # the real app on port 8765, backed by the fake OpenRouter
node scripts/ui_check.cjs               # 19 checks in a real browser against that server
node scripts/team_ui_check.cjs          # team controls, edited approval, reload and reconnect
node scripts/chart_regression.cjs       # isolated browser regressions for extreme chart ranges
python scripts/live_test.py --quick     # REAL OpenRouter: key check, model sync, one call, cost check
python scripts/live_test.py             # REAL OpenRouter: every mode on the cheapest brains
```

`BRAIN_POLICY=cheap` (the default for now) makes every brain slot use the cheapest Quick or Smart model, so tests
cost almost nothing. Set `BRAIN_POLICY=preferred` to use the plan's tiers (Quick, Smart, Genius) as written.

The browser scripts require Playwright and Chromium. Set `CHROME=/usr/bin/chromium` when using the system browser.

## Agent teams and optional teaching

The **Team** chip opens Fast, Balanced and Full team profiles. Choose planning Off/Auto/Ask me, Light/Normal/Deep
replanning, up to three planners and a plan judge, UI/data/document/code architects, and up to five researchers.
Each planner or researcher can use its own model, effort, time limit and credit cap. Researchers can also use different
search engines and search limits. Architect blueprints are downloadable files. The builder receives those blueprints
and linked research notes; steps have explicit goals and acceptance checks, with at most two repairs.

**Ask me** pauses after planning, before architecture, search or building. Edit the step goals and checks, then approve.
Approval spends the remaining original budget. A later explicit credit continuation adds a new bounded budget while
reusing completed work. The server preserves the original goal, tools and privacy settings. Browser reload/reconnection
replays saved events, and repeated sends with the same request identity do not create or bill a second run.

Turn **Use a teacher model** off for direct answers. With it on, Auto applies teaching style within the answer call.
Selecting a teacher model adds a separately metered explanation pass. If that pass fails, truncates, or drops source links,
code or artifact references, the original answer is kept.

Web search must be enabled in Tools. Research uses OpenRouter's `openrouter:web_search` server tool and citation metadata,
not the deprecated plugin. Unsourced results are disclosed and excluded from factual synthesis. All foreground calls,
repairs and retries reserve credits against the shared task cap, including concurrent agents. Server-tool cost thresholds
are soft provider controls: pending searches and a final answer may still execute; native search behavior varies by provider.

Named team profiles and chat preferences are saved in the current browser. Run one Uvicorn worker with the SQLite/local
scheduler: startup reconciles interrupted runs, settles recorded usage, and pauses saved plans without repeating paid calls.
This is not a distributed worker queue. Anonymous sessions use signed cookies and a persistent ignored local signing key;
the `x-user-id` development override is accepted only in `DEV_MODE=1`. School routes and background learning require ZDR.

See [the plan coverage matrix](docs/plan-coverage.md) for every plan section, tested acceptance cases, and remaining work.

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
| PPT and Word builders, edit "make slide 3 simpler" into a new retained output [6] | `tools/` |
| 7 skills, headers used during skill selection, recipe opened only when needed [13] | `skills/`, `skills.py` |
| Prompt library with versions (`name.v1.md`) [4] | `prompts/` |
| Live run card, files panel, effort, brain, cost cap pickers, phone sheets [14] | `frontend/` |
| One private folder per user and task, path checks, signed expiring links, upload checks [14] | `workspace.py`, `main.py` |

## Not built yet (so you know)

Payments (Stripe, Toss), real accounts and login (a cookie id is used), image generation, MCP servers, the
sandboxed mini-app iframe (Level B charts), Langfuse, promptfoo test set, PPT page-image previews (LibreOffice),
virus scanning of uploads (type and signature checks only), and a safety filter on messages and answers.


## Accounts, admin, plans and memory

Everything is stored in one SQLite file (`data/app.db`, WAL mode). **Back this file up.**

**Users.** A visitor starts as a guest. "Sign up" turns the guest into an account (email and password,
PBKDF2 hashes) and keeps all chats, memory and credits. Login sessions are random tokens in an httponly
cookie (only their hash is stored). Failed logins are rate limited.

**Admin console** at `/admin.html` (set `ADMIN_EMAIL` and `ADMIN_PASSWORD` in `.env`, or run
`python scripts/create_admin.py you@example.com`):
- Overview: users, active users, questions, credits used, AI cost, revenue, pending orders.
- Users: search and sort; open one to see their full blueprint (totals, usage by mode and model, chats,
  memories, purchases, credit history, activity timeline), change plan, block, set daily and monthly
  credit limits, add or remove credits, extend a plan, write a note, or delete them and their data.
- Queries: every question every user asked, with mode and credits; click one to read the whole chat
  (opening a chat is logged in that user's own activity history).
- Plans: edit price, credits, period, benefits and what each plan unlocks (brain tiers, modes, highest
  effort, daily cap, storage, retention, rounds, tries). Create new plans and credit packs. The harness
  enforces the new rules at once.
- Purchases, Activity (everything everyone did), Models (price sync and approval).

**Credits and plans (user side).** "Plans & credits" shows the plans and credit packs the admin set.
There is no payment processor yet. `PAYMENT_PROVIDER=test` pays at once (no money moves, for demos);
`manual` keeps the order pending until the admin confirms the money arrived. A paid plan lapses to Free
after its period unless bought again; Free tops up to its allowance every 30 days.

**Memory** works in three layers: (1) long-term notes about the user, saved after each turn by a cheap
model, or at once when the user says "remember that ..."; (2) recall of related moments from the user's
earlier chats through SQLite full-text search; (3) per-chat session notes plus a running summary, with the
last 8 messages kept word for word. Only the relevant notes go on the AI's desk, inside a fixed budget.
Users see, edit, pin, search, delete or switch off memory. Passwords, keys and card numbers are never saved.

Run `python -m pytest` (192 tests), then `python backend/tests/demo_server.py` and
`node scripts/platform_ui_check.cjs` (23 browser checks for sign-up, memory, plans and the admin console).


## Screen layout and settings

- **Side panels:** drag the edge of the sidebar or the workspace with the mouse to resize (double-click resets,
  arrow keys work too). Drag the sidebar far left, or click «, to shrink it to icons. Sizes are remembered.
- **Workspace:** the "Workspace" button in the top bar opens it, and its ✕ closes it. It opens by itself when the AI makes a file.
- **Settings** is a tabbed panel: Mode, Brains (with a quick pick: Auto, Cheapest, Balanced, Strongest), Planning,
  Research, Build and check, Effort and limits, Tools and skills, Display. The chips above the message box open the matching tab.
- **Owner mode:** `UNLOCK_ALL=1` in `.env` gives every visitor the hidden Owner plan (all modes, brains, max effort,
  100,000 credits). Good while you are the only user. Set it to 0 before real users arrive.

Browser checks: `node scripts/layout_ui_check.cjs` (24, start the server with `UNLOCK_ALL=1`), `scripts/ui_check.cjs` (19),
`scripts/platform_ui_check.cjs` (23), `scripts/team_ui_check.cjs` (15). Unit tests: `python -m pytest` (194).

## Deploy
See [DEPLOY.md](DEPLOY.md): Dockerfile, docker-compose.yml and a Render blueprint (render.yaml) are included. Use `UNLOCK_ALL=admin` on a public site.
