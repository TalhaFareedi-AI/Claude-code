"""One private folder per user, one per task (section 14).

workspaces/<user_id>/<task_id>_<slug>/{todo.md, inputs/, work/, out/, run-events.log}
Every path is checked to end inside the user's own folder (stops ../ tricks).
Download links are signed and expire.
"""
import hashlib
import hmac
import re
import shutil
import time
import uuid
from pathlib import Path

from .config import settings
from .db import DB, now
from .plans import rules

ALLOWED_UPLOAD = {".txt", ".md", ".csv", ".json", ".pdf", ".png", ".jpg", ".jpeg", ".docx", ".pptx"}
TEXT_TYPES = {".txt", ".md", ".csv", ".json"}
SLUG = re.compile(r"[^a-z0-9]+")


class PathEscape(Exception):
    pass


def user_root(user_id: str) -> Path:
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", user_id):
        raise PathEscape("bad user id")
    p = (settings.workspace_root / user_id).resolve()
    p.mkdir(parents=True, exist_ok=True)
    return p


def safe_path(user_id: str, *parts: str) -> Path:
    """Resolve inside the user's folder or refuse."""
    root = user_root(user_id)
    p = root.joinpath(*parts).resolve()
    if not p.is_relative_to(root):
        raise PathEscape("path leaves the user's folder")
    return p


def path_of(row: dict) -> Path:
    """Disk path of a workspace_files row, checked to sit inside the owner's folder."""
    base = user_root(row["user_id"])
    matches = sorted(base.glob(f"{row['task_id']}_*"))
    if not matches:
        raise PathEscape("missing task folder")
    p = (matches[0] / row["path"]).resolve()
    if not p.is_relative_to(base):
        raise PathEscape("path leaves the user's folder")
    return p


def clean_name(name: str) -> str:
    base = Path(name.replace("\\", "/")).name  # drop any folders
    base = re.sub(r"[^A-Za-z0-9._ -]", "_", base).strip(" .")[:80]
    return base or "file"


def task_dir(user_id: str, task_id: str, title: str = "") -> Path:
    slug = SLUG.sub("-", title.lower()).strip("-")[:30] or "task"
    existing = [d for d in user_root(user_id).glob(f"{task_id}_*") if d.is_dir()]
    d = existing[0] if existing else safe_path(user_id, f"{task_id}_{slug}")
    for sub in ("inputs", "work", "out"):
        (d / sub).mkdir(parents=True, exist_ok=True)
    return d


def write_todo(user_id: str, task_id: str, steps: list[dict], done: int) -> None:
    d = task_dir(user_id, task_id)
    lines = [f"- [{'x' if i < done else ' '}] {s.get('title', '')}" for i, s in enumerate(steps)]
    (d / "todo.md").write_text("# Plan\n" + "\n".join(lines) + "\n")


def register(db: DB, user_id: str, task_id: str, path: Path, kind: str, plan: str) -> dict:
    """Record a file in workspace_files. A second file with the same name becomes version +1."""
    d = task_dir(user_id, task_id)
    rel = path.relative_to(d).as_posix()
    prev = db.one("SELECT version FROM workspace_files WHERE user_id=? AND task_id=? AND path=? ORDER BY version DESC",
                  (user_id, task_id, rel))
    fid = "f_" + uuid.uuid4().hex[:12]
    days = rules(plan)["retention_days"]
    db.run("INSERT INTO workspace_files(id,user_id,task_id,path,kind,name,size,version,delete_after,created_at) "
           "VALUES(?,?,?,?,?,?,?,?,?,?)",
           (fid, user_id, task_id, rel, kind, path.name, path.stat().st_size, (prev["version"] + 1) if prev else 1,
            now() + days * 86400, now()))
    return file_row(db, fid)


def file_row(db: DB, fid: str) -> dict:
    r = db.one("SELECT * FROM workspace_files WHERE id=?", (fid,))
    return {"id": r["id"], "name": r["name"], "kind": r["kind"], "size": r["size"], "version": r["version"],
            "task_id": r["task_id"], "path": r["path"]}


def usage_bytes(db: DB, user_id: str) -> int:
    return int(db.scalar("SELECT SUM(size) FROM workspace_files WHERE user_id=?", (user_id,)))


def check_storage(db: DB, user_id: str, plan: str, extra: int) -> None:
    limit = rules(plan)["storage_mb"] * 1024 * 1024
    if usage_bytes(db, user_id) + extra > limit:
        raise PathEscape("storage limit reached for your plan")


def cleanup_work(user_id: str, task_id: str) -> None:
    """Task folders are temporary: the work folder is deleted when the task ends."""
    d = task_dir(user_id, task_id)
    shutil.rmtree(d / "work", ignore_errors=True)


def purge_expired(db: DB) -> int:
    rows = db.all("SELECT * FROM workspace_files WHERE delete_after < ?", (now(),))
    for r in rows:
        try:
            safe_path(r["user_id"], *[p for p in Path(r["path"]).parts]).unlink(missing_ok=True)
        except (PathEscape, OSError):
            pass
        db.run("DELETE FROM workspace_files WHERE id=?", (r["id"],))
    return len(rows)


def delete_all(db: DB, user_id: str) -> None:
    """The real 'Delete my files' button: folders and rows."""
    shutil.rmtree(user_root(user_id), ignore_errors=True)
    db.run("DELETE FROM workspace_files WHERE user_id=?", (user_id,))


# ---- signed, expiring download links -------------------------------------------------
def sign(file_id: str, user_id: str, ttl: int | None = None) -> str:
    exp = int(time.time() + (ttl or settings.link_ttl_s))
    msg = f"{file_id}.{user_id}.{exp}".encode()
    sig = hmac.new(settings.secret.encode(), msg, hashlib.sha256).hexdigest()[:32]
    return f"{file_id}.{exp}.{sig}"


def verify(token: str, user_id: str) -> str | None:
    try:
        fid, exp, sig = token.split(".")
        msg = f"{fid}.{user_id}.{exp}".encode()
        good = hmac.new(settings.secret.encode(), msg, hashlib.sha256).hexdigest()[:32]
        if hmac.compare_digest(sig, good) and int(exp) >= time.time():
            return fid
    except (ValueError, TypeError):
        pass
    return None


def read_text_inputs(user_id: str, task_id: str, max_chars: int = 12000) -> list[tuple[str, str]]:
    """Text of uploaded files that belong to this task (the 'open-book' notes)."""
    d = task_dir(user_id, task_id)
    out = []
    for p in sorted((d / "inputs").glob("*")):
        if p.suffix.lower() in TEXT_TYPES:
            out.append((p.name, p.read_text(errors="ignore")[:max_chars]))
    return out
