// Safe formula engine. Reads math text without running real code (never eval).
// Matches backend/app/formula.py, so a slider move needs no server call.
const FUNCS = {
  sin: Math.sin, cos: Math.cos, tan: Math.tan, asin: Math.asin, acos: Math.acos, atan: Math.atan,
  sqrt: Math.sqrt, ln: Math.log, log: Math.log, log10: Math.log10, log2: Math.log2, exp: Math.exp,
  abs: Math.abs, floor: Math.floor, ceil: Math.ceil, round: Math.round, min: Math.min, max: Math.max, pow: Math.pow,
};
const CONSTS = { pi: Math.PI, e: Math.E };
const TOKEN = /\s*(?:(\d+\.?\d*(?:[eE][+-]?\d+)?|\.\d+)|([A-Za-z_][A-Za-z0-9_]*)|(.))/gy;

export class FormulaError extends Error {}

function tokens(src) {
  if (src.length > 300) throw new FormulaError('formula too long');
  const out = [];
  TOKEN.lastIndex = 0;
  let m;
  while (TOKEN.lastIndex < src.length && (m = TOKEN.exec(src))) {
    if (m[1] !== undefined) out.push(['num', parseFloat(m[1])]);
    else if (m[2] !== undefined) out.push(['name', m[2]]);
    else if (m[3] !== undefined && m[3].trim()) {
      if (!'+-*/%^(),'.includes(m[3])) throw new FormulaError(`unexpected ${m[3]}`);
      out.push(['op', m[3]]);
    }
  }
  return out;
}

export function compile(src) {
  const t = tokens(String(src));
  let i = 0, depth = 0;
  const names = new Set();
  const peek = () => t[i] || [null, null];
  const isOp = (v) => { const [k, x] = peek(); return k === 'op' && x === v; };
  const eat = (v) => { if (!isOp(v)) throw new FormulaError(`expected ${v}`); i++; };

  function expr() {
    let l = term();
    while (isOp('+') || isOp('-')) { const op = t[i++][1]; const a = l, b = term(); l = op === '+' ? (e) => a(e) + b(e) : (e) => a(e) - b(e); }
    return l;
  }
  function term() {
    let l = unary();
    while (isOp('*') || isOp('/') || isOp('%')) {
      const op = t[i++][1]; const a = l, b = unary();
      l = op === '*' ? (e) => a(e) * b(e) : op === '/' ? (e) => a(e) / b(e) : (e) => a(e) % b(e);
    }
    return l;
  }
  function unary() {
    if (++depth > 40) throw new FormulaError('too deeply nested');
    try {
      if (isOp('-')) { i++; const a = unary(); return (e) => -a(e); }
      if (isOp('+')) { i++; return unary(); }
      return power();
    } finally { depth--; }
  }
  function power() {
    const base = atom();
    if (isOp('^')) { i++; const ex = unary(); return (e) => { const b = ex(e); if (Math.abs(b) > 1000) throw new FormulaError('exponent too large'); return Math.pow(base(e), b); }; }
    return base;
  }
  function atom() {
    const [k, v] = peek();
    if (k === 'num') { i++; return () => v; }
    if (k === 'name') {
      i++;
      if (isOp('(')) {
        i++;
        const args = [];
        if (!isOp(')')) { args.push(expr()); while (isOp(',')) { i++; args.push(expr()); } }
        eat(')');
        const fn = Object.prototype.hasOwnProperty.call(FUNCS, v) ? FUNCS[v] : null;
        if (!fn) throw new FormulaError(`unknown function ${v}`);
        if (!args.length) throw new FormulaError(`${v} needs a value`);
        return (e) => fn(...args.map((a) => a(e)));
      }
      if (Object.prototype.hasOwnProperty.call(CONSTS, v)) return () => CONSTS[v];
      names.add(v);
      return (e) => { if (!(v in e)) throw new FormulaError(`unknown name ${v}`); return e[v]; };
    }
    if (isOp('(')) { i++; const x = expr(); eat(')'); return x; }
    throw new FormulaError('incomplete formula');
  }
  const fn = expr();
  if (i !== t.length) throw new FormulaError('unexpected text after formula');
  const run = (env = {}) => fn(env);
  run.names = [...names];
  return run;
}
