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
    extra_dirs = ["d3-diagram-maker", "scientific-plotter", "docx-writer", "pptx-designer", "document-reviewer"]
    files = {f.parent.name: f for f in DIR.glob("*/SKILL.md")}
    for d in extra_dirs:
        cand = DIR / d / "SKILL.md"
        if cand.exists():
            files[d] = cand
    for _, f in sorted(files.items()):
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
    """Free first guess before paying a model to choose. Most specific rules first.

    A hit here skips the skill-picker model call entirely, so every rule added saves tokens.
    """
    t = text.lower()
    rules = [
        ("debugger", r"\b(bug|crash(e[sd])?|stack ?trace|traceback|exception|error message|failing test|does ?n[o']t work|broken|why (is|does).{0,30}(fail|break))\b"),
        ("test-writer", r"\b(unit tests?|write tests?|test coverage|pytest|jest|regression test|edge cases? to test)\b"),
        ("sql-helper", r"\b(sql|query plan|select \*|inner join|left join|postgres|mysql|sqlite|index(es)? on|group by)\b"),
        ("api-designer", r"\b(api design|rest api|endpoints?|openapi|swagger|status code|payload shape|versioning)\b"),
        ("d3-diagram-maker", r"\b(d3 diagram|interactive (architecture )?diagram|cnn diagram|transformer diagram|clickable diagram)\b"),
        ("scientific-plotter", r"\b(waveform|sine wave|fft|frequency spectrum|signal spectrum|training curve|damped oscillat)\b"),
        ("docx-writer", r"\b(word template|research paper docx|technical report docx|proposal docx)\b"),
        ("pptx-designer", r"\b(pptx theme|slide master|academic theme|business theme)\b"),
        ("document-reviewer", r"\b(audit document|review (this|the) (docx|pptx|pdf|deck|document)|check overflow)\b"),
        ("reviewer", r"\b(review (my|this|the)|code review|find (bugs|issues)|security hole|vulnerab|audit)\b"),
        ("prompt-smith", r"\b(prompt|system message|jailbreak|few.?shot)\b"),
        ("coder", r"\b(code|function|script|python|javascript|typescript|rust|java\b|refactor|regex|implement)\b"),
        ("math-solver", r"\b(solve|equation|integral|derivative|probability|prove|theorem|simplify|factorise|factorize)\b|\d\s*[-+*/^]\s*\d"),
        ("data-analyst", r"\b(csv|dataset|data ?set|spreadsheet|these numbers|my data|correlat|median|average of|trend)\b"),
        ("chart-maker", r"\b(chart|graph|plot|slider|visuali[sz]e|interactive)\b"),
        ("exam-coach", r"\b(quiz me|test me|mark (my|this)|past paper|exam practice|practice questions?|mock exam)\b"),
        ("study-planner", r"\b(revision (plan|schedule|timetable)|study plan|learn .{0,20}in \d+ (days?|weeks?|months?)|syllabus|before my exam)\b"),
        ("summarizer", r"\b(summari[sz]e|tl;?dr|key points|gist|condense|shorten this (document|paper|transcript))\b"),
        ("note-taker", r"\b(my notes|organi[sz]e (these|my) notes|clean up .{0,15}notes|meeting notes|transcript)\b"),
        ("writer", r"\b(write (an?|my|the) (essay|email|letter|report|post|article)|draft|cover letter|proofread|edit my)\b"),
        ("decision-helper", r"\b(which (one |option )?should i|compare .{0,30}(and|vs|versus)|better choice|pros and cons|worth it)\b"),
        ("architect", r"\b(architect|system design|design (a|an|the) (system|app|service|cnn|transformer|mamba|pipeline)|scale|microservice)\b"),
        ("researcher", r"\b(research|sources?|latest|current|cite|evidence|papers? on|find out about)\b"),
        ("explainer", r"\b(explain|what (is|are|does)|how (does|do)|don'?t understand|eli5|teach me)\b"),
    ]
    for name, rx in rules:
        if (enabled is None or name in enabled) and name in all_skills() and re.search(rx, t):
            return name
    return None
