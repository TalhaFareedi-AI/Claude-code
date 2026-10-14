"""Safe formula engine. Reads math text without running real code (never eval).

Grammar:  expr   = term (('+'|'-') term)*
          term   = unary (('*'|'/'|'%') unary)*
          unary  = ('-'|'+') unary | power
          power  = atom ('^' unary)?
          atom   = number | name | name '(' args ')' | '(' expr ')'
The browser has a matching copy in frontend/js/formula.js, so a slider move needs no server call.
"""
import math
import re

TOKEN = re.compile(r"\s*(?:(\d+\.?\d*(?:[eE][+-]?\d+)?|\.\d+)|([A-Za-z_][A-Za-z0-9_]*)|(.))")

FUNCS = {
    "sin": math.sin, "cos": math.cos, "tan": math.tan, "asin": math.asin, "acos": math.acos,
    "atan": math.atan, "sqrt": math.sqrt, "ln": math.log, "log": math.log, "log10": math.log10,
    "log2": math.log2, "exp": math.exp, "abs": abs, "floor": math.floor, "ceil": math.ceil,
    "round": round, "min": min, "max": max, "pow": math.pow,
}
CONSTS = {"pi": math.pi, "e": math.e}
RESERVED = set(FUNCS) | set(CONSTS) | {"x"}
MAX_LEN = 300
MAX_DEPTH = 40


class FormulaError(ValueError):
    pass


def _tokens(src: str) -> list[tuple[str, object]]:
    if len(src) > MAX_LEN:
        raise FormulaError("formula too long")
    out, pos = [], 0
    while pos < len(src):
        m = TOKEN.match(src, pos)
        if not m or m.end() == pos:
            break
        pos = m.end()
        num, name, op = m.groups()
        if num is not None:
            out.append(("num", float(num)))
        elif name is not None:
            out.append(("name", name))
        elif op is not None and not op.isspace():
            if op not in "+-*/%^(),":
                raise FormulaError(f"unexpected character {op!r}")
            out.append(("op", op))
    if src[pos:].strip():
        raise FormulaError("could not read formula")
    return out


class _Parser:
    def __init__(self, src: str):
        self.t = _tokens(src)
        self.i = 0
        self.depth = 0

    def peek(self):
        return self.t[self.i] if self.i < len(self.t) else (None, None)

    def eat(self, kind=None, val=None):
        tok = self.peek()
        if tok[0] is None or (kind and tok[0] != kind) or (val is not None and tok[1] != val):
            raise FormulaError(f"expected {val or kind}")
        self.i += 1
        return tok

    def parse(self):
        node = self.expr()
        if self.i != len(self.t):
            raise FormulaError("unexpected text after formula")
        return node

    def expr(self):
        node = self.term()
        while self.peek() in (("op", "+"), ("op", "-")):
            op = self.eat()[1]
            node = ("bin", op, node, self.term())
        return node

    def term(self):
        node = self.unary()
        while self.peek() in (("op", "*"), ("op", "/"), ("op", "%")):
            op = self.eat()[1]
            node = ("bin", op, node, self.unary())
        return node

    def unary(self):
        self.depth += 1
        if self.depth > MAX_DEPTH:
            raise FormulaError("formula too deeply nested")
        try:
            if self.peek() in (("op", "-"), ("op", "+")):
                op = self.eat()[1]
                inner = self.unary()
                return ("neg", inner) if op == "-" else inner
            return self.power()
        finally:
            self.depth -= 1

    def power(self):
        base = self.atom()
        if self.peek() == ("op", "^"):
            self.eat()
            return ("bin", "^", base, self.unary())
        return base

    def atom(self):
        kind, val = self.peek()
        if kind == "num":
            self.eat()
            return ("num", val)
        if kind == "name":
            self.eat()
            if self.peek() == ("op", "("):
                self.eat()
                args = []
                if self.peek() != ("op", ")"):
                    args.append(self.expr())
                    while self.peek() == ("op", ","):
                        self.eat()
                        args.append(self.expr())
                self.eat("op", ")")
                if val not in FUNCS:
                    raise FormulaError(f"unknown function {val}")
                return ("call", val, args)
            return ("var", val)
        if (kind, val) == ("op", "("):
            self.eat()
            node = self.expr()
            self.eat("op", ")")
            return node
        raise FormulaError("incomplete formula")


class Formula:
    def __init__(self, src: str):
        self.src = src
        self.ast = _Parser(src).parse()
        self.names = sorted(_names(self.ast))

    def __call__(self, env: dict[str, float] | None = None) -> float:
        env = env or {}
        try:
            return float(_eval(self.ast, env))
        except (ZeroDivisionError, OverflowError, ValueError) as e:
            raise FormulaError(f"cannot compute: {e}") from e


def _names(node) -> set[str]:
    k = node[0]
    if k == "var":
        return {node[1]} - set(CONSTS)
    if k == "bin":
        return _names(node[2]) | _names(node[3])
    if k == "neg":
        return _names(node[1])
    if k == "call":
        s: set[str] = set()
        for a in node[2]:
            s |= _names(a)
        return s
    return set()


def _eval(node, env):
    k = node[0]
    if k == "num":
        return node[1]
    if k == "var":
        n = node[1]
        if n in env:
            return env[n]
        if n in CONSTS:
            return CONSTS[n]
        raise FormulaError(f"unknown name {n}")
    if k == "neg":
        return -_eval(node[1], env)
    if k == "bin":
        a, b = _eval(node[2], env), _eval(node[3], env)
        op = node[1]
        if op == "+":
            return a + b
        if op == "-":
            return a - b
        if op == "*":
            return a * b
        if op == "/":
            return a / b
        if op == "%":
            return a % b
        if op == "^":
            if abs(b) > 1000:
                raise FormulaError("exponent too large")
            r = a ** b
            if isinstance(r, complex):
                raise FormulaError("result is not a real number")
            return r
    if k == "call":
        args = [_eval(a, env) for a in node[2]]
        if not args:
            raise FormulaError(f"{node[1]} needs a value")
        return FUNCS[node[1]](*args)
    raise FormulaError("bad formula")


def evaluate(src: str, env: dict[str, float] | None = None) -> float:
    """Evaluate once. Raises FormulaError on any problem."""
    return Formula(src)(env)


def finite(v: float) -> bool:
    return isinstance(v, (int, float)) and math.isfinite(v)
