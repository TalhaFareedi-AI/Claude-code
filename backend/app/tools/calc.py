"""Calculator tool: 'no mental math' rule (section 7). {{calc: expr}} becomes the exact number."""
import re

from ..formula import FormulaError, evaluate

CALC = re.compile(r"\{\{\s*calc\s*:\s*([^{}]{1,200}?)\s*\}\}")


def fmt(v: float) -> str:
    if abs(v - round(v)) < 1e-9 and abs(v) < 1e15:
        return f"{int(round(v)):,}".replace(",", "") if abs(v) < 10000 else f"{int(round(v)):,}"
    return f"{v:,.6g}" if abs(v) >= 1e6 or abs(v) < 1e-4 else f"{round(v, 6):,}".rstrip("0").rstrip(".")


def run(expr: str) -> str:
    return fmt(evaluate(expr))


def fill(text: str) -> tuple[str, list[dict]]:
    """Replace every {{calc: ...}}. A bad one is left readable instead of crashing."""
    log: list[dict] = []

    def sub(m):
        expr = m.group(1)
        try:
            res = run(expr)
            log.append({"expr": expr, "result": res})
            return res
        except FormulaError as e:
            log.append({"expr": expr, "error": str(e)})
            return f"({expr})"

    return CALC.sub(sub, text), log
