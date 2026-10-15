"""Plans, credit packs, purchases and monthly renewals.

No payment processor is connected yet. Two providers exist:
  test    a purchase is paid at once (no real money). For local use and demos.
  manual  a purchase waits as 'pending' until an admin marks it paid (bank transfer, cash, invoice).
Plugging in Stripe or Toss later means adding a provider that calls `complete_purchase` from its webhook.
"""
import uuid

from . import activity, plans, wallet
from .config import settings
from .db import DB, now


class BillingError(Exception):
    pass


def renew(db: DB, user: dict) -> None:
    """The plan period ended. Free tops up to its allowance. A paid plan needs a new payment, so it lapses to Free
    (the user can buy it again; an admin can also extend it). Credits already bought are never taken away."""
    plan = plans.get(user["plan"])
    if user.get("status") == "blocked":
        db.run("UPDATE users SET plan_renews_at=NULL WHERE id=?", (user["id"],))
        return
    if plan and plan["price_usd"] > 0:
        db.run("UPDATE users SET plan='free' WHERE id=?", (user["id"],))
        activity.log(db, user["id"], "plan_expired", plan=plan["id"])
        plan = plans.get("free")
    if not plan:
        db.run("UPDATE users SET plan_renews_at=NULL WHERE id=?", (user["id"],))
        return
    grant = max(0, int(plan["credits"]) - wallet.balance(db, user["id"]))
    if grant:
        wallet.add(db, user["id"], grant, "plan:free")
    db.run("UPDATE users SET plan_renews_at=? WHERE id=?", (now() + plan["period_days"] * 86400, user["id"]))
    activity.log(db, user["id"], "plan_renewed", plan="free", credits=grant)


def start_purchase(db: DB, user: dict, plan_id: str) -> dict:
    plan = plans.get(plan_id)
    if not plan or not plan["active"]:
        raise BillingError("That plan or pack is not available.")
    if not user.get("email"):
        raise BillingError("Create an account first (Sign up), so your purchase stays with you.")
    if plan["kind"] == "subscription" and user["plan"] == plan_id:
        raise BillingError("You are already on this plan.")
    pid = "p_" + uuid.uuid4().hex[:12]
    db.run("INSERT INTO purchases(id,user_id,plan_id,kind,amount_usd,credits,status,provider,created_at) VALUES(?,?,?,?,?,?,?,?,?)",
           (pid, user["id"], plan_id, plan["kind"], plan["price_usd"], plan["credits"], "pending", settings.payment_provider, now()))
    activity.log(db, user["id"], "purchase_started", purchase=pid, plan=plan_id, usd=plan["price_usd"])
    if settings.payment_provider == "test" or plan["price_usd"] == 0:
        complete_purchase(db, pid, actor="test-provider")
    return db.one("SELECT * FROM purchases WHERE id=?", (pid,))


def complete_purchase(db: DB, purchase_id: str, actor: str = "system") -> dict:
    """Mark a purchase paid and give the user what they bought. Safe to call twice."""
    claimed = db.run("UPDATE purchases SET status='paid' WHERE id=? AND status='pending'", (purchase_id,))
    p = db.one("SELECT * FROM purchases WHERE id=?", (purchase_id,))
    if not p:
        raise BillingError("No such purchase.")
    if claimed.rowcount != 1:
        return p  # already done, nothing granted twice
    plan = plans.get(p["plan_id"]) or {}
    if p["kind"] == "topup":
        wallet.add(db, p["user_id"], int(p["credits"]), f"topup:{p['plan_id']}")
    else:
        db.run("UPDATE users SET plan=?, plan_renews_at=? WHERE id=?",
               (p["plan_id"], now() + int(plan.get("period_days") or 30) * 86400, p["user_id"]))
        wallet.add(db, p["user_id"], int(p["credits"]), f"plan:{p['plan_id']}")
    activity.log(db, p["user_id"], "purchase_paid", actor=actor, purchase=purchase_id, plan=p["plan_id"], usd=p["amount_usd"],
                 credits=p["credits"])
    return db.one("SELECT * FROM purchases WHERE id=?", (purchase_id,))


def cancel_purchase(db: DB, purchase_id: str, actor: str) -> dict:
    db.run("UPDATE purchases SET status='cancelled' WHERE id=? AND status='pending'", (purchase_id,))
    p = db.one("SELECT * FROM purchases WHERE id=?", (purchase_id,))
    if not p:
        raise BillingError("No such purchase.")
    activity.log(db, p["user_id"], "purchase_cancelled", actor=actor, purchase=purchase_id)
    return p


def catalog_for_user(db: DB, user: dict) -> list[dict]:
    out = []
    for p in plans.all_plans():
        out.append({"id": p["id"], "name": p["name"], "kind": p["kind"], "price_usd": p["price_usd"], "credits": p["credits"],
                    "period_days": p["period_days"], "benefits": p["benefits"], "current": p["id"] == user["plan"],
                    "usd_per_1000_credits": round(p["price_usd"] / p["credits"] * 1000, 2) if p["credits"] else 0})
    return out
