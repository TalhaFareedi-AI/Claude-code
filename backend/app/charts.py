"""Chart recipe (section 5). The AI writes the recipe once, the browser draws and redraws it.

The server checks the recipe: right shape, and every formula gives real numbers at the
lowest, default and highest input values. A bad recipe never reaches the user.
"""
import itertools
import re

from .formula import Formula, FormulaError, RESERVED, finite

CHART_TYPES = {"line", "area", "scatter", "bar", "pie"}
ID_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,15}$")
MAX_INPUTS, MAX_SERIES, MAX_STEPS, MAX_BARS = 6, 5, 400, 24


class RecipeError(ValueError):
    pass


def _num(v, what):
    if isinstance(v, bool) or not isinstance(v, (int, float)) or not finite(float(v)):
        raise RecipeError(f"{what} must be a number")
    return float(v)


def _formula(src, what) -> Formula:
    if isinstance(src, (int, float)) and not isinstance(src, bool):
        src = repr(src)
    if not isinstance(src, str) or not src.strip():
        raise RecipeError(f"{what} needs a formula")
    try:
        return Formula(src)
    except FormulaError as e:
        raise RecipeError(f"{what}: {e}") from e


def validate(recipe: dict) -> dict:
    """Return a cleaned recipe, or raise RecipeError with a message the AI can fix."""
    if not isinstance(recipe, dict):
        raise RecipeError("recipe must be a JSON object")
    kind = str(recipe.get("chart", "line")).lower()
    if kind not in CHART_TYPES:
        raise RecipeError(f"chart must be one of {sorted(CHART_TYPES)}")
    out: dict = {"chart": kind, "title": str(recipe.get("title", "Chart"))[:120]}

    inputs = recipe.get("inputs") or []
    if not isinstance(inputs, list) or len(inputs) > MAX_INPUTS:
        raise RecipeError(f"inputs must be a list of at most {MAX_INPUTS}")
    clean_inputs, seen = [], set()
    for i in inputs:
        if not isinstance(i, dict):
            raise RecipeError("each input must be an object")
        iid = str(i.get("id", ""))
        if not ID_RE.match(iid) or iid in RESERVED:
            raise RecipeError(f"input id {iid!r} is not allowed (use letters, not x/pi/e or function names)")
        if iid in seen:
            raise RecipeError(f"duplicate input id {iid}")
        seen.add(iid)
        typ = i.get("type", "slider" if "min" in i else "number")
        if typ not in ("slider", "number"):
            raise RecipeError("input type must be slider or number")
        value = _num(i.get("value", 0), f"input {iid} value")
        item = {"id": iid, "label": str(i.get("label", iid))[:60], "type": typ, "value": value}
        if typ == "slider":
            lo, hi = _num(i.get("min", 0), f"{iid} min"), _num(i.get("max", 1), f"{iid} max")
            if not lo < hi:
                raise RecipeError(f"input {iid}: min must be below max")
            if not lo <= value <= hi:
                raise RecipeError(f"input {iid}: value must be between min and max")
            step = _num(i.get("step", (hi - lo) / 100 or 1), f"{iid} step")
            if step <= 0:
                raise RecipeError(f"input {iid}: step must be above 0")
            item.update(min=lo, max=hi, step=step)
        clean_inputs.append(item)
    out["inputs"] = clean_inputs

    if kind in ("bar", "pie"):
        data = recipe.get("data")
        if not isinstance(data, list) or not 1 <= len(data) <= MAX_BARS:
            raise RecipeError(f"{kind} chart needs data: a list of 1 to {MAX_BARS} {{label, formula}} items")
        out["data"] = [{"label": str(d.get("label", ""))[:40], "formula": str(d.get("formula", d.get("value", "")))}
                       for d in data if isinstance(d, dict)]
        if len(out["data"]) != len(data):
            raise RecipeError("each data item must be an object")
        formulas = [(f"data[{n}]", _formula(d["formula"], f"data[{n}]")) for n, d in enumerate(out["data"])]
        x_formulas: list = []
    else:
        x = recipe.get("x") or {}
        if not isinstance(x, dict):
            raise RecipeError("x must be an object with label, from, to")
        x_from = _formula(x.get("from", 0), "x.from")
        x_to = _formula(x.get("to", 10), "x.to")
        out["x"] = {"label": str(x.get("label", "x"))[:40], "from": str(x.get("from", 0)), "to": str(x.get("to", 10))}
        steps = int(_num(recipe.get("steps", 60), "steps"))
        out["steps"] = max(5, min(steps, MAX_STEPS))
        lines = recipe.get("lines")
        if not isinstance(lines, list) or not 1 <= len(lines) <= MAX_SERIES:
            raise RecipeError(f"lines must be a list of 1 to {MAX_SERIES} {{name, formula}} items")
        out["lines"] = [{"name": str(l.get("name", f"Line {n+1}"))[:40], "formula": str(l.get("formula", ""))}
                        for n, l in enumerate(lines) if isinstance(l, dict)]
        if len(out["lines"]) != len(lines):
            raise RecipeError("each line must be an object")
        formulas = [(f"lines[{n}]", _formula(l["formula"], f"lines[{n}]")) for n, l in enumerate(out["lines"])]
        x_formulas = [("x.from", x_from), ("x.to", x_to)]

    # Every name used must be an input (or x for line-type charts).
    allowed = {i["id"] for i in clean_inputs} | ({"x"} if kind not in ("bar", "pie") else set())
    for label, f in formulas + x_formulas:
        bad = [n for n in f.names if n not in allowed]
        if bad:
            raise RecipeError(f"{label} uses unknown name(s) {bad}; define them as inputs")
    for label, f in x_formulas:
        if "x" in f.names:
            raise RecipeError(f"{label} cannot use x")

    # Numbers must be real at the lowest, default and highest input values.
    for env in _corner_envs(clean_inputs):
        try:
            if x_formulas:
                lo, hi = x_formulas[0][1](env), x_formulas[1][1](env)
                if not (finite(lo) and finite(hi)):
                    raise RecipeError("x range is not a real number")
                if hi <= lo:
                    raise RecipeError("x.to must be above x.from at every input value")
                xs = [lo, (lo + hi) / 2, hi]
            else:
                xs = [None]
            for xv in xs:
                e2 = dict(env, x=xv) if xv is not None else env
                for label, f in formulas:
                    v = f(e2)
                    if not finite(v):
                        raise RecipeError(f"{label} gives a non-real number at {e2}")
        except FormulaError as e:
            raise RecipeError(f"formula fails at {env}: {e}") from e
    return out


def _corner_envs(inputs: list[dict]) -> list[dict]:
    if not inputs:
        return [{}]
    picks = []
    for i in inputs:
        vals = [i["value"]]
        if i["type"] == "slider":
            vals = [i["min"], i["value"], i["max"]]
        picks.append([(i["id"], v) for v in dict.fromkeys(vals)])
    # all-min, all-default, all-max plus single-input extremes keeps it cheap but honest
    envs = [dict(c) for c in itertools.islice(itertools.product(*picks), 81)]
    return envs


def compute(recipe: dict, values: dict | None = None) -> dict:
    """Evaluate a validated recipe. Returns {labels/xs, series} for PPT/doc embedding and tests."""
    values = values or {}
    env = {i["id"]: float(values.get(i["id"], i["value"])) for i in recipe["inputs"]}
    if recipe["chart"] in ("bar", "pie"):
        return {"labels": [d["label"] for d in recipe["data"]],
                "series": [{"name": recipe["title"], "values": [Formula(d["formula"])(env) for d in recipe["data"]]}]}
    lo, hi = Formula(recipe["x"]["from"])(env), Formula(recipe["x"]["to"])(env)
    n = recipe["steps"]
    xs = [lo + (hi - lo) * k / n for k in range(n + 1)]
    series = []
    for ln in recipe["lines"]:
        f = Formula(ln["formula"])
        series.append({"name": ln["name"], "values": [f(dict(env, x=x)) for x in xs]})
    return {"xs": xs, "series": series}
