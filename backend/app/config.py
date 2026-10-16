"""Settings. Read from environment (and a git-ignored .env file)."""
import os
import secrets
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _load_env() -> None:
    p = ROOT / ".env"
    if not p.exists():
        return
    for line in p.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


_load_env()


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default)


def _app_secret() -> str:
    configured = _env("APP_SECRET")
    if configured and configured != "dev-secret-change-me":
        return configured
    # Keep anonymous sessions valid across restarts without a public default signing key.
    path = Path(_env("DB_PATH", str(ROOT / "data" / "app.db"))).parent / ".app-secret"  # lives on the data volume
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        return path.read_text().strip()
    value = secrets.token_urlsafe(48)
    with os.fdopen(fd, "w") as stream:
        stream.write(value)
    return value


class Settings:
    def __init__(self) -> None:
        self.openrouter_api_key = _env("OPENROUTER_API_KEY")
        self.openrouter_base_url = _env("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
        self.db_path = _env("DB_PATH", str(ROOT / "data" / "app.db"))
        self.workspace_root = Path(_env("WORKSPACE_ROOT", str(ROOT / "workspaces")))
        # cheap = every brain resolves to the cheapest Quick/Smart model (testing).
        # preferred = use the tier lists as the plan describes.
        self.brain_policy = _env("BRAIN_POLICY", "cheap")
        self.dev_mode = _env("DEV_MODE", "0") == "1"
        self.secret = _app_secret()
        # Money rules (section 9 of the plan). Keep in settings, not in code paths.
        self.fee_factor = _env("FEE_FACTOR", "1.055")  # OpenRouter 5.5% card fee
        self.credit_cost_usd = _env("CREDIT_COST_USD", "0.003")  # AI cost one credit may cover
        self.auto_spend_limit = int(_env("AUTO_SPEND_LIMIT", "20"))  # credits per task, no ask
        self.task_time_limit_s = int(_env("TASK_TIME_LIMIT_S", "180"))
        self.max_steps = int(_env("MAX_STEPS", "8"))
        self.upload_max_bytes = int(_env("UPLOAD_MAX_BYTES", str(2 * 1024 * 1024)))
        self.link_ttl_s = int(_env("LINK_TTL_S", str(15 * 60)))
        self.rate_per_minute = int(_env("RATE_PER_MINUTE", "30"))
        self.admin_token = _env("ADMIN_TOKEN")
        self.admin_email = _env("ADMIN_EMAIL")
        self.admin_password = _env("ADMIN_PASSWORD")
        # test = a purchase is paid at once (no real money). manual = pending until an admin marks it paid.
        self.payment_provider = _env("PAYMENT_PROVIDER", "test" if _env("DEV_MODE", "0") == "1" else "manual")
        # Owner mode: every user gets the Owner plan (all modes, brains, effort, huge limits). For a one-person setup.
        # UNLOCK_ALL=1: everyone (only for your own computer). UNLOCK_ALL=admin: only admin accounts (safe on a public site).
        self.unlock_all = _env("UNLOCK_ALL", "0") == "1"
        self.unlock_admin = _env("UNLOCK_ALL", "0").lower() == "admin"
        self.app_title = _env("APP_TITLE", "Study Harness")


settings = Settings()
