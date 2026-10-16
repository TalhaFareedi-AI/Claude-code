#!/usr/bin/env python3
"""Safe live backup of the SQLite database (uses SQLite's own backup API, so it is consistent while the app runs).
    python scripts/backup.py backups/app-$(date +%F).db        (inside the container: docker compose exec app python scripts/backup.py /data/backup.db)
"""
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from app.config import settings  # noqa: E402

if len(sys.argv) != 2:
    sys.exit("usage: python scripts/backup.py <destination.db>")
dest = Path(sys.argv[1])
dest.parent.mkdir(parents=True, exist_ok=True)
src = sqlite3.connect(f"file:{settings.db_path}?mode=ro", uri=True)
out = sqlite3.connect(dest)
with out:
    src.backup(out)
print(f"Backed up {settings.db_path} -> {dest} ({dest.stat().st_size // 1024} KB)")
