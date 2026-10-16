"""The user's look and layout. Stored per user, so it follows them to any device.

The browser applies these as CSS variables and data attributes. The server only checks that every value
is one of the known choices, so a saved look can never carry script, markup or an odd size.
"""
import re

CHOICES = {
    "theme": ("auto", "light", "dark", "sepia", "midnight", "contrast"),
    "font": ("system", "serif", "rounded", "mono", "readable"),
    "density": ("compact", "cozy", "spacious"),
    "width": ("narrow", "normal", "wide", "full"),
    "round": ("sharp", "normal", "round"),
    "anim": ("on", "reduced", "off"),
    "steps_open": ("running", "always", "never"),
}
FLAGS = ("timing", "thinking", "fold_long", "workspace_auto", "show_estimate", "send_on_enter")
CHIPS = ("mode", "team", "tools", "brains", "effort", "length")
SIDE_ITEMS = ("memory", "activity", "files")
ACCENTS = ("teal", "blue", "violet", "orange", "rose", "slate")
HEX = re.compile(r"^#[0-9a-fA-F]{6}$")
SIZE = (85, 140)

DEFAULTS = {
    "theme": "auto", "accent": "teal", "size": 100, "font": "system", "density": "cozy", "width": "normal",
    "round": "normal", "anim": "on", "steps_open": "running",
    "timing": True, "thinking": True, "fold_long": True, "workspace_auto": True, "show_estimate": True, "send_on_enter": True,
    "chips": ["mode", "team", "tools"], "side_items": ["memory", "activity", "files"],
}


def clean(data) -> dict:
    """Keep only known keys with known values. Anything else is dropped, never repaired by guessing."""
    out: dict = {}
    if not isinstance(data, dict):
        return out
    for key, allowed in CHOICES.items():
        if data.get(key) in allowed:
            out[key] = data[key]
    accent = data.get("accent")
    if accent in ACCENTS or (isinstance(accent, str) and HEX.match(accent)):
        out["accent"] = accent.lower() if accent.startswith("#") else accent
    size = data.get("size")
    if isinstance(size, (int, float)) and not isinstance(size, bool):
        out["size"] = int(max(SIZE[0], min(SIZE[1], round(size))))
    for key in FLAGS:
        if isinstance(data.get(key), bool):
            out[key] = data[key]
    for key, allowed in (("chips", CHIPS), ("side_items", SIDE_ITEMS)):
        value = data.get(key)
        if isinstance(value, list):
            seen: list[str] = []
            for item in value:
                if item in allowed and item not in seen:
                    seen.append(item)
            out[key] = seen
    return out


def effective(saved) -> dict:
    return {**DEFAULTS, **clean(saved)}
