"""Skills (section 13): recipe cards the AI opens only when needed.
The AI always sees the one-line headers. It opens a full recipe only when the task matches."""
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

DIR = Path(__file__).parent / "skills"
HEAD = re.compile(r"\A---\s*\n(.*?)\n---\s*\n(.*)\Z", re.S)
MAX_BODY_CHARS = 6000  # a recipe is about 1,500 tokens


@dataclass
class Skill:
    name: str
    description: str
    body: str
    version: int = 1


@lru_cache(maxsize=None)
def all_skills() -> dict[str, Skill]:
    out: dict[str, Skill] = {}
    for f in sorted(DIR.glob("*/SKILL.md")):
        m = HEAD.match(f.read_text())
        if not m:
            continue
        meta = dict(re.findall(r"^(\w+):\s*(.+)$", m.group(1), re.M))
        name = meta.get("name") or f.parent.name
        out[name] = Skill(name, meta.get("description", ""), m.group(2).strip()[:MAX_BODY_CHARS])
    return out


def headers(enabled: list[str] | None = None) -> str:
    sk = all_skills()
    names = [n for n in sk if enabled is None or n in enabled]
    return "\n".join(f"- {n}: {sk[n].description}" for n in names)


def get(name: str) -> Skill | None:
    return all_skills().get(name)


def match_keywords(text: str, enabled: list[str] | None = None) -> str | None:
    """Free first guess before paying for a model: simple keyword rules."""
    t = text.lower()
    rules = [("architect", r"\b(architect|design (a|an|the) (system|app)|scale|system design)\b"),
             ("reviewer", r"\b(review|find bugs?|security hole|audit)\b"),
             ("prompt-smith", r"\b(prompt)\b"),
             ("coder", r"\b(code|function|script|python|javascript|refactor|bug)\b"),
             ("chart-maker", r"\b(chart|graph|plot|slider)\b"),
             ("researcher", r"\b(research|compare|latest|sources?)\b"),
             ("explainer", r"\b(explain|don't understand|dont understand|eli5)\b")]
    for name, rx in rules:
        if (enabled is None or name in enabled) and re.search(rx, t):
            return name
    return None
