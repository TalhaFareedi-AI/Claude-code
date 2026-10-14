"""Runs the real app with the fake OpenRouter behind it. For UI checks only (no network, no cost).
   python backend/tests/demo_server.py [port]"""
import os
import sys
import tempfile
from pathlib import Path

os.environ.update(NO_AUTO_APP="1", DEV_MODE="1", BRAIN_POLICY="cheap")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import uvicorn

from app.config import settings
from app.db import DB
from app.main import create_app
from app.openrouter import OpenRouter
from fake_openrouter import FakeOpenRouter

tmp = Path(tempfile.mkdtemp())
settings.workspace_root = tmp / "ws"
fake = FakeOpenRouter()
fake.delay = 0
llm = OpenRouter(api_key="demo-key", base_url="http://fake", transport=fake.transport())
app = create_app(llm=llm, db=DB(str(tmp / "demo.db")))

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=int(sys.argv[1]) if len(sys.argv) > 1 else 8765, log_level="warning")
