"""Scientific and research graphics (section 5, page 23).

Generates computed scientific plots (waveforms, FFT frequency spectra, damped oscillations,
Gaussian distributions, training curves, or formula plots) as clean, deterministic SVG
so every visual carries the 'Computed plot' badge.
"""
import math
from .. import formula as formula_mod


class SciencePlotError(ValueError):
    pass


KINDS = {"waveform", "spectrum", "damped", "gaussian", "training", "formula"}


def validate(spec: dict) -> dict:
    if not isinstance(spec, dict):
        raise SciencePlotError("science_plot spec must be a JSON object")
    kind = str(spec.get("kind") or "waveform").lower().strip()
    if kind not in KINDS:
        kind = "waveform"
    title = str(spec.get("title") or "Scientific Plot").strip()[:100]
    freq = float(spec.get("freq", 5.0))
    if not (0.1 <= freq <= 200.0):
        freq = 5.0
    amp = float(spec.get("amp", 1.0))
    if not (0.01 <= abs(amp) <= 1000.0):
        amp = 1.0
    duration = float(spec.get("duration", 1.0))
    if not (0.05 <= duration <= 20.0):
        duration = 1.0
    damping = float(spec.get("damping", 2.0))
    expr = str(spec.get("formula") or "sin(2 * pi * 5 * x)").strip()[:200]
    if kind == "formula":
        formula_mod.Formula(expr, {"x"})
    return {
        "kind": kind,
        "title": title,
        "freq": freq,
        "amp": amp,
        "duration": duration,
        "damping": damping,
        "formula": expr,
        "x_label": str(spec.get("x_label") or ("Time t (s)" if kind in ("waveform", "spectrum", "damped") else "x"))[:60],
        "y_label": str(spec.get("y_label") or ("Amplitude x(t)" if kind in ("waveform", "spectrum", "damped") else "y"))[:60],
        "badge": "Computed plot",
    }


def compute_series(spec: dict, n_points: int = 240) -> dict:
    clean = validate(spec)
    kind = clean["kind"]
    f = clean["freq"]
    amp = clean["amp"]
    dur = clean["duration"]
    xs, ys = [], []
    fft_freqs, fft_mags = [], []

    if kind in ("waveform", "spectrum"):
        for i in range(n_points + 1):
            t = dur * i / n_points
            xs.append(round(t, 5))
            ys.append(round(amp * math.sin(2 * math.pi * f * t), 5))
        max_f = max(10, int(f * 2.5))
        for freq_bin in range(0, max_f + 1):
            re_sum = 0.0
            im_sum = 0.0
            for t, y in zip(xs[:-1], ys[:-1]):
                angle = -2 * math.pi * freq_bin * t
                re_sum += y * math.cos(angle)
                im_sum += y * math.sin(angle)
            mag = 2.0 * math.hypot(re_sum, im_sum) / max(1, len(xs) - 1)
            fft_freqs.append(freq_bin)
            fft_mags.append(round(mag, 4))
    elif kind == "damped":
        d = clean["damping"]
        for i in range(n_points + 1):
            t = dur * i / n_points
            xs.append(round(t, 5))
            ys.append(round(amp * math.exp(-d * t) * math.cos(2 * math.pi * f * t), 5))
    elif kind == "gaussian":
        for i in range(n_points + 1):
            x = -4.0 + 8.0 * i / n_points
            xs.append(round(x, 4))
            ys.append(round((1.0 / math.sqrt(2 * math.pi)) * math.exp(-0.5 * x * x), 5))
    elif kind == "training":
        for i in range(1, 51):
            xs.append(i)
            ys.append(round(1.8 * math.exp(-0.08 * i) + 0.12, 4))
    else:
        compiled = formula_mod.Formula(clean["formula"], {"x"})
        for i in range(n_points + 1):
            x = dur * i / n_points
            xs.append(round(x, 5))
            ys.append(round(float(compiled.eval({"x": x})), 5))

    return {
        **clean,
        "xs": xs,
        "ys": ys,
        "fft_freqs": fft_freqs,
        "fft_mags": fft_mags,
    }


def render_svg(data: dict) -> str:
    has_fft = bool(data.get("fft_freqs"))
    W = 680
    H = 380 if has_fft else 260
    ml, mr, mt = 56, 20, 34
    pw = W - ml - mr
    ph = 130 if has_fft else 180

    xs, ys = data["xs"], data["ys"]
    x0, x1 = (min(xs), max(xs)) if xs else (0.0, 1.0)
    y0, y1 = (min(ys), max(ys)) if ys else (-1.0, 1.0)
    if abs(y1 - y0) < 1e-6:
        y0, y1 = y0 - 1.0, y1 + 1.0
    pad = 0.08 * (y1 - y0)
    y0 -= pad
    y1 += pad

    def sx(x):
        return ml + ((x - x0) / (x1 - x0 or 1.0)) * pw

    def sy(y):
        return mt + ph - ((y - y0) / (y1 - y0 or 1.0)) * ph

    pts = " ".join(f"{sx(x):.1f},{sy(y):.1f}" for x, y in zip(xs, ys))
    zero_y = sy(0.0) if y0 <= 0 <= y1 else mt + ph

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" font-family="system-ui, sans-serif" font-size="11">',
        f'<rect width="{W}" height="{H}" rx="10" fill="#ffffff" stroke="#e2e8f0"/>',
        f'<text x="{ml}" y="22" font-size="13" font-weight="700" fill="#0f172a">{_esc(data["title"])}</text>',
        f'<rect x="{W - 132}" y="8" width="116" height="20" rx="10" fill="#e6f4f1"/>',
        f'<text x="{W - 74}" y="22" font-size="10" font-weight="600" text-anchor="middle" fill="#1e6b5c">Computed plot</text>',
        f'<rect x="{ml}" y="{mt}" width="{pw}" height="{ph}" fill="#f8fafc" stroke="#cbd5e1"/>',
        f'<line x1="{ml}" y1="{zero_y:.1f}" x2="{ml + pw}" y2="{zero_y:.1f}" stroke="#94a3b8" stroke-dasharray="3 3"/>',
        f'<polyline fill="none" stroke="#2a7f6f" stroke-width="2.2" points="{pts}"/>',
        f'<text x="{ml + pw / 2:.1f}" y="{mt + ph + 24}" text-anchor="middle" fill="#475569">{_esc(data["x_label"])}</text>',
        f'<text x="16" y="{mt + ph / 2:.1f}" text-anchor="middle" fill="#475569" transform="rotate(-90 16 {mt + ph / 2:.1f})">{_esc(data["y_label"])}</text>',
    ]

    if has_fft:
        mt2 = mt + ph + 48
        ph2 = 110
        freqs, mags = data["fft_freqs"], data["fft_mags"]
        fmax = max(freqs) if freqs else 10
        mmax = max(max(mags) if mags else 1.0, 0.1)
        parts.append(f'<text x="{ml}" y="{mt2 - 8}" font-size="11" font-weight="600" fill="#334155">FFT Frequency Spectrum |X(f)| (spike at {data["freq"]:g} Hz)</text>')
        parts.append(f'<rect x="{ml}" y="{mt2}" width="{pw}" height="{ph2}" fill="#f8fafc" stroke="#cbd5e1"/>')
        for fb, mg in zip(freqs, mags):
            bx = ml + (fb / (fmax or 1)) * pw
            bh = (mg / mmax) * (ph2 - 14)
            by = mt2 + ph2 - bh
            parts.append(f'<line x1="{bx:.1f}" y1="{mt2 + ph2}" x2="{bx:.1f}" y2="{by:.1f}" stroke="#2f6fd1" stroke-width="3"/>')
            parts.append(f'<circle cx="{bx:.1f}" cy="{by:.1f}" r="3.5" fill="#2f6fd1"/>')
        parts.append(f'<text x="{ml + pw / 2:.1f}" y="{mt2 + ph2 + 20}" text-anchor="middle" fill="#475569">Frequency f (Hz)</text>')

    parts.append("</svg>")
    return "".join(parts)


def _esc(s: str) -> str:
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")
