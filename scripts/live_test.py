#!/usr/bin/env python3
"""Live test against the REAL OpenRouter, using the cheapest models. Run this once the network allows
openrouter.ai. It proves the money math (plan section 15, step 1) and every mode on cheap brains.

    python scripts/live_test.py            # key check, model sync, one call, then all modes
    python scripts/live_test.py --quick    # key check, model sync, one call only

It uses OPENROUTER_API_KEY from the environment or the git-ignored .env file, and it prints what
each run cost. Typical total spend on the cheap policy: well under 1 US cent... plus whatever the
cheapest brains charge, so read the printed cost line.
"""
import asyncio
import os
import sys
import tempfile
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
os.environ.setdefault("BRAIN_POLICY", "cheap")

from app import catalog, modes, wallet  # noqa: E402
from app.config import settings  # noqa: E402
from app.db import DB  # noqa: E402
from app.harness import Harness, RunRequest  # noqa: E402
from app.openrouter import OpenRouter, OpenRouterError  # noqa: E402
from app.pricing import call_cost  # noqa: E402

OK, BAD = "\033[32mPASS\033[0m", "\033[31mFAIL\033[0m"
failures = []


def check(name, ok, extra=""):
    print(f"{OK if ok else BAD}  {name}  {extra}")
    if not ok:
        failures.append(name)


async def main(quick: bool) -> int:
    settings.workspace_root = Path(tempfile.mkdtemp())
    llm = OpenRouter()
    if not llm.api_key:
        print("Set OPENROUTER_API_KEY first (in .env).")
        return 2

    # 1. Is the key valid?
    try:
        info = await llm.key_info()
        check("key is valid", True, f"label={info.get('label')} usage=${info.get('usage')} limit={info.get('limit')}")
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
    res = await llm.chat(cheap["id"], [{"role": "user", "content": "Say hello in 5 words."}], max_tokens=60)
    u = res.usage
    table = call_cost(cheap["price_in"], cheap["price_out"], u.prompt, u.completion, u.cached, cheap.get("price_cached"))
    check("usage.cost is returned", u.cost is not None, f"model={res.model} reply={res.text.strip()[:40]!r}")
    if u.cost is not None and table:
        ratio = Decimal(repr(u.cost)) / table
        check("OpenRouter cost matches tokens x listed price (within 25%)", Decimal("0.75") <= ratio <= Decimal("1.25"),
              f"openrouter=${u.cost:.8f} table=${float(table):.8f} ratio={float(ratio):.2f}")
    if quick:
        return 1 if failures else 0

    # 4. Every mode your plan allows, on cheap brains, through the real harness.
    db.run("INSERT INTO users(id,name,plan,auto_spend,created_at) VALUES('live','Live','pro',50,0)")
    wallet.add(db, "live", 3000, "live-test")
    h = Harness(db, llm)
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
    }
    before_total = Decimal(0)
    for mode_id, text in prompts.items():
        mode = modes.get(db, mode_id)
        req = RunRequest(message=text, mode=mode_id, confirm=True, max_credits=min(mode["max_credits"], 40),
                         rounds=1, tries=2, effort="low")
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


if __name__ == "__main__":
    code = asyncio.run(main("--quick" in sys.argv))
    if code == 2:
        print("\nNOT RUN: could not reach OpenRouter (or no key).")
    else:
        print("\n" + (f"{len(failures)} failed" if failures else "all live checks passed"))
    sys.exit(code)
