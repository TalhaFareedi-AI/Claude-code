"""The 10 modes (section 3). One mode is one database row, so web and app read the same list.

slots:  role -> "tier:quick|smart|genius" (resolved live) or an exact OpenRouter model id.
        A list value means several brains (council members, think-team thinkers).
reasoning / max_tokens are set per role, so a thinker can think hard while the answerer does not.
"""
from .db import DB, jdump, jload

ALL = ["free", "student", "pro", "school"]
PAID = ["student", "pro", "school"]
PRO = ["pro", "school"]

MODES = [
    {"id": "fast", "name": "Fast", "blurb": "One quick answer, no scrap paper", "runner": "single", "big": False,
     "steps": ["answer"], "slots": {"answer": "tier:quick"}, "reasoning": {"answer": "off"},
     "max_tokens": {"answer": 500}, "params": {}, "max_credits": 10, "plans": ALL},
    {"id": "normal", "name": "Normal", "blurb": "One answer with a little thinking", "runner": "single", "big": False,
     "steps": ["answer"], "slots": {"answer": "tier:smart"}, "reasoning": {"answer": "low"},
     "max_tokens": {"answer": 2500}, "params": {}, "max_credits": 30, "plans": ALL},
    {"id": "deep", "name": "Deep", "blurb": "Plan, do the steps, check", "runner": "deep", "big": True,
     "steps": ["planner", "worker", "checker", "answer"],
     "slots": {"planner": "tier:smart", "worker": "tier:smart", "checker": "tier:quick", "answer": "tier:smart"},
     "reasoning": {"planner": "low", "worker": "medium", "checker": "off", "answer": "low"},
     "max_tokens": {"planner": 1200, "worker": 3000, "checker": 600, "answer": 2500},
     "params": {"max_steps": 8}, "max_credits": 150, "plans": PAID},
    {"id": "think_again", "name": "Think Again", "blurb": "Write, get marked by a critic, rewrite", "runner": "think_again",
     "big": True, "steps": ["write", "critic", "rewrite"],
     "slots": {"write": "tier:smart", "critic": "tier:quick"},
     "reasoning": {"write": "medium", "critic": "low"}, "max_tokens": {"write": 3000, "critic": 800},
     "params": {"default_rounds": 2, "max_rounds": 5, "stop_score": 8}, "max_credits": 80, "plans": ALL},
    {"id": "overthink", "name": "Overthink", "blurb": "Several long-thinking tries, a judge picks the best",
     "runner": "overthink", "big": True, "steps": ["think", "judge"],
     "slots": {"think": "tier:genius", "judge": "tier:genius"},
     "reasoning": {"think": "high", "judge": "low"}, "max_tokens": {"think": 8000, "judge": 1500},
     "params": {"default_tries": 3, "max_tries": 5}, "max_credits": 160, "plans": PRO, "daily_limit": 5},
    {"id": "council", "name": "Council", "blurb": "Different brains answer alone, a judge merges them",
     "runner": "council", "big": True, "steps": ["members", "judge"],
     "slots": {"members": ["tier:smart", "tier:smart", "tier:smart"], "judge": "tier:smart"},
     "reasoning": {"members": "medium", "judge": "low"}, "max_tokens": {"members": 2500, "judge": 2000},
     "params": {"min_members": 3, "max_members": 5}, "max_credits": 80, "plans": PRO, "daily_limit": 5},
    {"id": "two_brains", "name": "Two Brains", "blurb": "One brain thinks and writes notes, another answers",
     "runner": "two_brains", "big": True, "steps": ["think", "answer"],
     "slots": {"think": "tier:genius", "answer": "tier:smart"},
     "reasoning": {"think": "high", "answer": "off"}, "max_tokens": {"think": 8000, "answer": 2000},
     "params": {"notes_max_tokens": 1000}, "max_credits": 60, "plans": PAID},
    {"id": "think_team", "name": "Think Team", "blurb": "2 to 5 brains think, one answerer writes the reply",
     "runner": "think_team", "big": True, "steps": ["think", "answer"],
     "slots": {"think": ["tier:smart", "tier:smart", "tier:quick"], "answer": "tier:smart"},
     "reasoning": {"think": "medium", "answer": "off"}, "max_tokens": {"think": 3000, "answer": 2000},
     "params": {"min_thinkers": 2, "max_thinkers": 5, "notes_max_tokens": 500}, "max_credits": 80, "plans": PRO,
     "daily_limit": 5},
    {"id": "research", "name": "Research", "blurb": "Plan searches, search the web, answer with links",
     "runner": "research", "big": True, "steps": ["planner", "search", "writer"],
     "slots": {"planner": "tier:quick", "search": "tier:smart", "writer": "tier:smart"},
     "reasoning": {"planner": "off", "search": "low", "writer": "low"},
     "max_tokens": {"planner": 600, "search": 1500, "writer": 2500},
     "params": {"max_searches": 4}, "max_credits": 60, "plans": PAID},
    {"id": "developer", "name": "Developer", "blurb": "Deep loop plus skills for design, code and prompts",
     "runner": "deep", "big": True, "steps": ["planner", "worker", "checker", "answer"],
     "slots": {"planner": "tier:smart", "worker": "code", "checker": "tier:quick", "answer": "tier:smart"},
     "reasoning": {"planner": "low", "worker": "medium", "checker": "off", "answer": "low"},
     "max_tokens": {"planner": 1200, "worker": 3500, "checker": 600, "answer": 3000},
     "params": {"max_steps": 8, "skills": True}, "max_credits": 160, "plans": PAID},
]


def seed(db: DB) -> None:
    for n, m in enumerate(MODES):
        row = db.one("SELECT id FROM modes WHERE id=?", (m["id"],))
        if row:
            db.run("UPDATE modes SET data=?, sort=? WHERE id=?", (jdump(m), n, m["id"]))
        else:
            db.run("INSERT INTO modes(id,data,enabled,sort) VALUES(?,?,1,?)", (m["id"], jdump(m), n))


def get(db: DB, mode_id: str) -> dict | None:
    row = db.one("SELECT data FROM modes WHERE id=? AND enabled=1", (mode_id,))
    return jload(row["data"]) if row else None


def listing(db: DB) -> list[dict]:
    return [jload(r["data"]) for r in db.all("SELECT data FROM modes WHERE enabled=1 ORDER BY sort")]


def allowed(mode: dict, plan: str) -> bool:
    return plan in mode["plans"]
