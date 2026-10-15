#!/usr/bin/env python3
"""Create or reset the admin login.   python scripts/create_admin.py admin@example.com
The password is asked on the keyboard (not stored in shell history). The admin signs in at /admin.html."""
import getpass
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from app import accounts  # noqa: E402
from app.config import settings  # noqa: E402
from app.db import DB  # noqa: E402

if len(sys.argv) != 2:
    sys.exit("usage: python scripts/create_admin.py admin@example.com")
password = getpass.getpass("New admin password (8+ characters): ")
if password != getpass.getpass("Again: "):
    sys.exit("The two passwords differ.")
try:
    user = accounts.ensure_admin(DB(settings.db_path), sys.argv[1], password)
except accounts.AuthError as exc:
    sys.exit(str(exc))
print(f"Admin ready: {user['email']} (id {user['id']}). Sign in at /admin.html")
