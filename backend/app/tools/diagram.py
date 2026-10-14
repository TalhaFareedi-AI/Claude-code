"""Diagram tool: the AI draws a small SVG. We keep only safe tags and attributes."""
import re
import xml.etree.ElementTree as ET

ALLOWED_TAGS = {"svg", "g", "defs", "marker", "rect", "circle", "ellipse", "line", "polyline", "polygon", "path", "text", "tspan", "title"}
ALLOWED_ATTRS = {"viewBox", "width", "height", "x", "y", "x1", "y1", "x2", "y2", "cx", "cy", "r", "rx", "ry", "d", "points",
                 "fill", "stroke", "stroke-width", "stroke-dasharray", "stroke-linecap", "stroke-linejoin", "opacity",
                 "font-size", "font-family", "font-weight", "text-anchor", "dominant-baseline", "transform", "id",
                 "marker-end", "marker-start", "markerWidth", "markerHeight", "refX", "refY", "orient", "markerUnits",
                 "fill-opacity", "stroke-opacity", "xmlns"}
NS = "http://www.w3.org/2000/svg"
BAD = re.compile(r"<!DOCTYPE|<!ENTITY|<\?xml-stylesheet|javascript:|data:|url\s*\(\s*['\"]?(?!#)", re.I)
MAX_BYTES = 40_000


class SvgError(ValueError):
    pass


def sanitize(svg: str) -> str:
    svg = svg.strip()
    if len(svg.encode()) > MAX_BYTES:
        raise SvgError("svg too large")
    if BAD.search(svg):
        raise SvgError("svg contains blocked content")
    ET.register_namespace("", NS)
    try:
        root = ET.fromstring(svg)
    except ET.ParseError as e:
        raise SvgError(f"svg is not valid: {e}") from e
    if root.tag.split("}")[-1] != "svg":
        raise SvgError("root must be <svg>")
    _clean(root)
    root.set("xmlns", NS)
    if "viewBox" not in root.attrib:
        root.set("viewBox", "0 0 600 360")
    root.attrib.pop("width", None)
    root.attrib.pop("height", None)
    return ET.tostring(root, encoding="unicode")


def _clean(el) -> None:
    for child in list(el):
        if child.tag.split("}")[-1] not in ALLOWED_TAGS:
            el.remove(child)
            continue
        _clean(child)
    for k in list(el.attrib):
        name = k.split("}")[-1]
        v = el.attrib[k]
        if name not in ALLOWED_ATTRS or name.lower().startswith("on") or re.search(r"url\(|javascript", v, re.I) and not re.fullmatch(r"url\(#[\w-]+\)", v.strip()):
            del el.attrib[k]
    el.tag = el.tag.split("}")[-1]
