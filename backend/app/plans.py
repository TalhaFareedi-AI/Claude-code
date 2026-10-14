"""What each plan unlocks (section 9, step 4). Example numbers; change them in one place."""

PLAN_RULES = {
    "free": {"tiers": ["quick"], "max_rounds": 1, "max_tries": 1, "charts_per_day": 2, "retention_days": 7,
             "storage_mb": 50, "mcp": False, "images": False, "private_default": False},
    "student": {"tiers": ["quick", "smart"], "max_rounds": 3, "max_tries": 3, "charts_per_day": 50, "retention_days": 14,
                "storage_mb": 500, "mcp": False, "images": True, "private_default": False},
    "pro": {"tiers": ["quick", "smart", "genius"], "max_rounds": 5, "max_tries": 5, "charts_per_day": 500,
            "retention_days": 21, "storage_mb": 5000, "mcp": True, "images": True, "private_default": False},
    "school": {"tiers": ["quick", "smart", "genius"], "max_rounds": 3, "max_tries": 3, "charts_per_day": 200,
               "retention_days": 21, "storage_mb": 2000, "mcp": True, "images": True, "private_default": True},
}


def rules(plan: str) -> dict:
    return PLAN_RULES.get(plan, PLAN_RULES["free"])
