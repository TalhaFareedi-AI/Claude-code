import os
import sys
from pathlib import Path

os.environ["NO_AUTO_APP"] = "1"
os.environ["DEV_MODE"] = "1"
os.environ["OPENROUTER_API_KEY"] = "test-key"
os.environ["BRAIN_POLICY"] = "cheap"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import pytest

from app import catalog, modes, plans
from app.config import settings
from app.db import DB
from app.harness import Harness
from app.openrouter import OpenRouter
from fake_openrouter import FakeOpenRouter


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "workspace_root", tmp_path / "ws")
    monkeypatch.setattr(settings, "brain_policy", "cheap")
    monkeypatch.setattr(settings, "task_time_limit_s", 60)
    from app import routes_account
    routes_account.attempts.clear()


@pytest.fixture
def fake():
    return FakeOpenRouter()


@pytest.fixture
def db():
    d = DB(":memory:")
    catalog.seed(d)
    modes.seed(d)
    plans.bind(d, modes.listing(d))
    return d


@pytest.fixture
def llm(fake):
    return OpenRouter(api_key="test-key", base_url="http://fake", transport=fake.transport())


@pytest.fixture
def harness(db, llm):
    return Harness(db, llm)
