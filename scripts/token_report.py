#!/usr/bin/env python3
"""What every prompt costs, and what one message of each mode costs in tokens.

    python scripts/token_report.py            # prompt sizes and desk budget (no API calls, free)
    python scripts/token_report.py --live     # also run one real message per mode and report real usage
"""
import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app import prompts, skills  # noqa: E402

TOK = 3.5  # characters per token, close enough for a budget view


def report_static() -> None:
    files = sorted(prompts._index().items())
    print(f"{'prompt':24} {'ver':>4} {'chars':>7} {'~tokens':>8}")
    total = 0
    for name, (ver, path) in files:
        n = len(path.read_text())
        total += n
        print(f"{name:24} v{ver:<3} {n:7} {int(n / TOK):8}")
    print(f"{'TOTAL (library)':24} {'':4} {total:7} {int(total / TOK):8}\n")

    sk = skills.all_skills()
    heads = skills.headers()
    bodies = sum(len(s.body) for s in sk.values())
    print(f"skills: {len(sk)}")
    print(f"  headers always available to the picker: {int(len(heads) / TOK)} tokens")
    print(f"  all bodies if they were loaded eagerly: {int(bodies / TOK)} tokens")
    print(f"  one body loaded on demand (average):    {int(bodies / len(sk) / TOK)} tokens")
    print(f"  saved by loading one instead of all:    {int((bodies - bodies / len(sk)) / TOK)} tokens per message\n")

    print("system prompt sent with one message:")
    for style, name in (("direct (default)", "direct"), ("teaching mode", "teacher")):
        base = len(prompts.get(name))
        print(f"  {style:18} {int(base / TOK):5} tokens"
              f"   + chart rules {int(len(prompts.get('chart_rules')) / TOK)}"
              f" / table {int(len(prompts.get('table_rules')) / TOK)}"
              f" / flashcards {int(len(prompts.get('flashcard_rules')) / TOK)} only when needed")


async def report_live() -> None:
    import tempfile

    from app import catalog, modes, plans
    from app.config import settings
    from app.db import DB
    from app.harness import Harness, RunRequest
    from app.openrouter import OpenRouter

    settings.workspace_root = Path(tempfile.mkdtemp())
    llm = OpenRouter()
    if not llm.api_key:
        print("\nNo OPENROUTER_API_KEY, skipping the live pass.")
        return
    db = DB(":memory:")
    catalog.seed(db)
    modes.seed(db)
    plans.bind(db, modes.listing(db))
    catalog.sync_live(db, await llm.list_models())
    h = Harness(db, llm)
    h.get_user("u_tok")
    db.run("UPDATE users SET plan='pro' WHERE id='u_tok'")
    from app import wallet
    wallet.add(db, "u_tok", 5000, "report")
    print(f"\n{'mode':14} {'in':>7} {'cached':>7} {'out':>7} {'think':>7} {'credits':>8} {'usd':>10}")
    for mode in ("fast", "normal", "think_again"):
        tid, em = await h.start("u_tok", RunRequest(message="What is a prime number?", mode=mode, confirm=True))
        [e async for e in em.stream()]
        await h.drain()
        row = db.one("SELECT SUM(input_tokens) i, SUM(cached_tokens) c, SUM(output_tokens) o, "
                     "SUM(reasoning_tokens) r, SUM(credits_charged) cr, SUM(cost_usd) u "
                     "FROM usage_events WHERE task_id=?", (tid,))
        print(f"{mode:14} {row['i'] or 0:7} {row['c'] or 0:7} {row['o'] or 0:7} {row['r'] or 0:7} "
              f"{row['cr'] or 0:8} {row['u'] or 0:10.6f}")


if __name__ == "__main__":
    report_static()
    if "--live" in sys.argv:
        asyncio.run(report_live())
