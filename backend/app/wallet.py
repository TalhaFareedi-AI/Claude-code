"""Credit wallet (section 9, step 5). A ledger, not a balance box. Hold, then settle."""
from .db import DB, now

PLANS = {
    #          monthly credits, price, auto-spend default
    "free": {"credits": 100, "price": 0},
    "student": {"credits": 800, "price": 8},
    "pro": {"credits": 2000, "price": 20},
    "school": {"credits": 1000, "price": 12},
}


class InsufficientCredits(Exception):
    def __init__(self, need: int, available: int):
        super().__init__(f"need {need} credits, {available} available")
        self.need, self.available = need, available


def balance(db: DB, user_id: str) -> int:
    """Balance = sum of ledger rows."""
    return int(db.scalar("SELECT SUM(delta) FROM credit_ledger WHERE user_id=?", (user_id,)))


def held(db: DB, user_id: str) -> int:
    return int(db.scalar("SELECT SUM(amount) FROM credit_holds WHERE user_id=? AND status='active'", (user_id,)))


def available(db: DB, user_id: str) -> int:
    return balance(db, user_id) - held(db, user_id)


def add(db: DB, user_id: str, delta: int, reason: str, task_id: str | None = None) -> None:
    db.run("INSERT INTO credit_ledger(user_id,delta,reason,task_id,created_at) VALUES(?,?,?,?,?)",
           (user_id, delta, reason, task_id, now()))


def grant_plan(db: DB, user_id: str, plan: str) -> None:
    add(db, user_id, PLANS[plan]["credits"], f"plan:{plan}")


def hold(db: DB, user_id: str, task_id: str, amount: int) -> None:
    """Reserve credits for a running job. Raises when the user cannot cover it."""
    avail = available(db, user_id)
    if amount > avail:
        raise InsufficientCredits(amount, avail)
    db.run("INSERT INTO credit_holds(user_id,task_id,amount,status,created_at) VALUES(?,?,?, 'active', ?)",
           (user_id, task_id, amount, now()))


def settle(db: DB, user_id: str, task_id: str, real: int, reason: str = "task") -> int:
    """Charge the real cost (never more than the hold) and release the rest."""
    h = db.one("SELECT * FROM credit_holds WHERE task_id=? AND status='active'", (task_id,))
    if not h:
        return 0
    charge = max(0, min(real, h["amount"]))
    if charge:
        add(db, user_id, -charge, reason, task_id)
    db.run("UPDATE credit_holds SET status='settled' WHERE id=?", (h["id"],))
    return charge


def refund(db: DB, user_id: str, task_id: str, amount: int, reason: str = "refund") -> None:
    add(db, user_id, amount, reason, task_id)


def release(db: DB, task_id: str) -> None:
    db.run("UPDATE credit_holds SET status='released' WHERE task_id=? AND status='active'", (task_id,))


def spent_today(db: DB, user_id: str) -> int:
    day_start = now() - (now() % 86400)
    return int(-db.scalar("SELECT SUM(delta) FROM credit_ledger WHERE user_id=? AND delta<0 AND created_at>=?",
                          (user_id, day_start)))


def ledger_mismatches(db: DB) -> list[dict]:
    """Tasks whose charged credits differ from their usage rows (target: none)."""
    return db.all(
        "SELECT t.id task_id, -COALESCE((SELECT SUM(delta) FROM credit_ledger l WHERE l.task_id=t.id AND l.delta<0),0) charged,"
        " COALESCE((SELECT SUM(credits_charged) FROM usage_events u WHERE u.task_id=t.id),0) used "
        "FROM tasks t WHERE t.status IN ('done','stopped','paused') AND charged != MIN(used, t.max_credits)")
