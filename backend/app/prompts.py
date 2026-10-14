"""Prompt library (section 4). Prompts are files with version numbers (name.v1.md), not code.
Pick the highest version. `{{var}}` is replaced by render()."""
import re
from functools import lru_cache
from pathlib import Path

DIR = Path(__file__).parent / "prompts"
_VER = re.compile(r"^(?P<name>.+)\.v(?P<v>\d+)\.md$")


@lru_cache(maxsize=None)
def _index() -> dict[str, tuple[int, Path]]:
    best: dict[str, tuple[int, Path]] = {}
    for p in DIR.glob("*.md"):
        m = _VER.match(p.name)
        if m and int(m["v"]) >= best.get(m["name"], (0, p))[0]:
            best[m["name"]] = (int(m["v"]), p)
    return best


def get(name: str) -> str:
    return _index()[name][1].read_text().strip()


def version(name: str) -> int:
    return _index()[name][0]


def render(name: str, **vars) -> str:
    text = get(name)
    for k, v in vars.items():
        text = text.replace("{{" + k + "}}", str(v))
    return text
