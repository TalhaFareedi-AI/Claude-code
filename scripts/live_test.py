#!/usr/bin/env python3
"""Live test against the REAL OpenRouter, using the cheapest models. Run this once the network allows
openrouter.ai. It proves the money math (plan section 15, step 1) and every mode on cheap brains.

    python scripts/live_test.py            # key check, model sync, one call, then all modes
    python scripts/live_test.py --quick    # key check, model sync, one call only
    python scripts/live_test.py --artifacts  # documents, charts and answer length, on real models

It uses OPENROUTER_API_KEY from the environment or the git-ignored .env file, and it prints what
each run cost. Typical total spend on the cheap policy: well under 1 US cent... plus whatever the
cheapest brains charge, so read the printed cost line.
"""
import asyncio
import os
import re
import sys
import tempfile
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
os.environ.setdefault("BRAIN_POLICY", "cheap")

from app import catalog, modes, plans, wallet  # noqa: E402
from app.config import settings  # noqa: E402
from app.db import DB  # noqa: E402
from app.harness import Harness, RunRequest  # noqa: E402
from app.openrouter import OpenRouter, OpenRouterError, build_reasoning  # noqa: E402
from app.pricing import call_cost  # noqa: E402

OK, BAD = "\033[32mPASS\033[0m", "\033[31mFAIL\033[0m"
failures = []


def check(name, ok, extra=""):
    print(f"{OK if ok else BAD}  {name}  {extra}")
    if not ok:
        failures.append(name)


async def checks(quick: bool, llm: OpenRouter) -> int:
    settings.workspace_root = Path(tempfile.mkdtemp())
    if not llm.api_key:
        print("Set OPENROUTER_API_KEY first (in .env).")
        return 2

    # 1. Is the key valid?
    try:
        info = await llm.key_info()
        check("key is valid", True)
    except OpenRouterError as e:
        check("key is valid", False, str(e))
        return 1
    except Exception as e:
        print(f"Cannot reach OpenRouter: {e}\nCheck the environment's network policy allows openrouter.ai.")
        return 2

    # 2. Pull the live model list, so prices and names are real, not the plan's examples.
    db = DB(":memory:")
    catalog.seed(db)
    modes.seed(db)
    plans.bind(db, modes.listing(db))   # the plan table decides which modes a user may run
    live = await llm.list_models()
    rep = catalog.sync_live(db, live)
    check("model list synced", len(live) > 50, f"{len(live)} live models, {rep['updated']} catalog rows matched, "
          f"{len(rep['missing'])} catalog models not on OpenRouter, {rep['new']} new (held for approval)")
    if rep["missing"]:
        print("  not on OpenRouter (from the plan's examples):", ", ".join(rep["missing"]))
    # Plan's example names may not exist. Approve the cheapest live models that think, so the run has brains.
    pool = db.all("SELECT * FROM model_catalog WHERE available=1")
    if len([m for m in pool if m["approved"]]) < 4:
        for m in sorted(db.all("SELECT * FROM model_catalog WHERE source='live' AND approved=0 AND price_out>0 "
                               "AND id NOT LIKE '%:free' ORDER BY price_out LIMIT 40"), key=lambda r: r["price_out"]):
            catalog.approve(db, m["id"], "quick" if m["price_out"] < 1 else "smart")
    ok_models = catalog.listing(db)
    check("catalog has usable models", len(ok_models) >= 3, ", ".join(m["id"] for m in ok_models[:6]))

    # 3. One real call: does usage.cost match tokens x listed price?  (proves the money math)
    cheap = catalog.resolve(db, "quick", policy="cheap")
    res = await llm.chat(cheap["id"], [{"role": "user", "content": "Say hello in 5 words."}], max_tokens=256,
                         reasoning=build_reasoning(cheap, "off", 256))
    check("model returned a visible answer", bool(res.text.strip()))
    u = res.usage
    table = call_cost(cheap["price_in"], cheap["price_out"], u.prompt, u.completion, u.cached, cheap.get("price_cached"))
    check("usage.cost is returned", u.cost is not None, f"model={res.model} reply={res.text.strip()[:40]!r}")
    if u.cost is not None and table:
        ratio = Decimal(repr(u.cost)) / table
        check("OpenRouter cost matches tokens x listed price (within 25%)", Decimal("0.75") <= ratio <= Decimal("1.25"),
              f"openrouter=${u.cost:.8f} table=${float(table):.8f} ratio={float(ratio):.2f}")
    if quick:
        return 1 if failures else 0

    db.run("INSERT INTO users(id,name,plan,auto_spend,created_at) VALUES('live','Live','pro',50,0)")
    wallet.add(db, "live", 3000, "live-test")
    h = Harness(db, llm)

    # 4. Artifacts on real models: a document, a drawn chart, and the answer-length dial.
    async def one(text: str, **kw) -> tuple[str, list[dict]]:
        req = RunRequest(message=text, mode=kw.pop("mode", "normal"), confirm=True, effort="low",
                         max_credits=kw.pop("max_credits", 25),
                         tools=kw.pop("tools", ["chart", "diagram", "documents", "table"]), **kw)
        tid, em = await h.start("live", req)
        ev = [e async for e in em.stream()]
        await h.drain()
        body = ""
        for e in ev:
            if e["type"] == "text":
                body = e["delta"] if e.get("replace") else body + e["delta"]
        status = next((e for e in reversed(ev) if e["type"] == "run_done"), {}).get("status")
        err = next((e["text"] for e in ev if e["type"] == "error"), "")
        if status != "done" or err:
            print(f"      [{status}] {err[:200]}")
        return body, ev

    ascii_art = re.compile(r"[\u2500-\u257f]|[+|][-=]{3,}[+|]|^\s*[/\\_|]{6,}\s*$", re.M)

    body, ev = await one("Create a document that teaches me how AI learns. Three short sections.")
    docs = [e for e in ev if e["type"] == "artifact" and e["kind"] == "doc"]
    check("a document ask makes a real document file", bool(docs),
          f"{docs[0]['data']['name']} ({docs[0]['data']['words']} words)" if docs else "no doc artifact")
    check("the document answer has no ASCII art", not ascii_art.search(body), repr(body[:80]))

    body, ev = await one("Show me a chart of how $1000 grows at 5% interest over 10 years.")
    arts = [e["kind"] for e in ev if e["type"] == "artifact"]
    check("a chart ask draws a picture, not ASCII art", bool({"chart", "svg"} & set(arts)) and not ascii_art.search(body),
          f"artifacts={arts}")

    short, _ = await one("Explain photosynthesis.", length="short", tools=[])
    long_, _ = await one("Explain photosynthesis.", length="long", tools=[])
    check("Long gives a longer answer than Short", len(long_) > len(short) * 1.2,
          f"short={len(short)} chars, long={len(long_)} chars")
    if "--artifacts" in sys.argv:
        return 1 if failures else 0

    # 5. Every mode your plan allows, on cheap brains, through the real harness.
    prompts = {
        "fast": "What is a noun? Give one example.",
        "normal": "Explain what interest is, then show how $1000 grows at 5% for 2 years.",
        "think_again": "Explain why the sky is blue.",
        "two_brains": "What is 17 times 23? Explain the steps.",
        "council": "Is a tomato a fruit or a vegetable?",
        "overthink": "What is the sum of the first 10 odd numbers? Explain.",
        "think_team": "Why do we have seasons?",
        "research": "What is the tallest building in the world right now?",
        "deep": "Plan and compare two ways to save $100 a month for a year. Use a chart.",
        "developer": "Design a tiny Python temperature converter. Give validation rules, code and three test cases. Do not claim to execute code.",
    }
    before_total = Decimal(0)
    for mode_id, text in prompts.items():
        mode = modes.get(db, mode_id)
        req = RunRequest(message=text, mode=mode_id, confirm=True, max_credits=min(mode["max_credits"], 40),
                         rounds=1, tries=2, effort="low", tools=["web"] if mode_id == "research" else ["chart", "diagram", "documents", "ppt"],
                         team={"plan_depth": "light", "researchers": {"count": 2 if mode_id == "research" else 0,
                               "max_searches_each": 1}, "builder": {"effort": "off"}})
        tid, em = await h.start("live", req)
        events = [e async for e in em.stream()]
        await h.drain()
        status = next((e for e in reversed(events) if e["type"] == "run_done"), {}).get("status")
        err = next((e["text"] for e in events if e["type"] == "error"), "")
        txt = ""
        for e in events:
            if e["type"] == "text":
                txt = e["delta"] if e.get("replace") else txt + e["delta"]
        usd = Decimal(repr(db.scalar("SELECT usd_used FROM tasks WHERE id=?", (tid,), 0.0)))
        before_total += usd
        credits = db.scalar("SELECT credits_used FROM tasks WHERE id=?", (tid,), 0)
        check(f"{mode_id}", status == "done" and len(txt) > 20, f"status={status} credits={credits} usd=${float(usd):.5f} {err[:90]}")
        if txt:
            print("      " + " ".join(txt.split())[:140])
    print(f"\nLedger mismatches: {wallet.ledger_mismatches(db)}")
    check("ledger matches usage rows", wallet.ledger_mismatches(db) == [])
    print(f"Total AI spend this run: ${float(before_total):.5f}")
    return 1 if failures else 0


async def main(quick: bool) -> int:
    llm = OpenRouter()
    try:
        return await checks(quick, llm)
    finally:
        await llm.aclose()


if __name__ == "__main__":
    code = asyncio.run(main("--quick" in sys.argv))
    if code == 2:
        print("\nNOT RUN: could not reach OpenRouter (or no key).")
    else:
        print("\n" + (f"{len(failures)} failed" if failures else "all live checks passed"))
    sys.exit(code)
