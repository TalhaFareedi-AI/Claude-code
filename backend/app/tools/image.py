"""Generated pictures. The model returns a base64 image, we save it as a real file in the user's workspace.

The user chooses the image model (Settings > Tools and skills). Nothing is generated until they have,
because image models differ a lot in price and in what they are allowed to draw.
"""
import base64
import binascii
import re

from .. import catalog, workspace

MAX_PROMPT = 600
MAX_BYTES = 6 * 1024 * 1024
MAGIC = {b"\x89PNG\r\n\x1a\n": "png", b"\xff\xd8\xff": "jpg", b"GIF8": "gif", b"RIFF": "webp"}
DATA_URL = re.compile(r"^data:image/[a-z+]{2,10};base64,(.+)$", re.I | re.S)


class ImageError(Exception):
    pass


def chosen_model(ctx) -> dict | None:
    """The image model this user picked, if it is still available."""
    wanted = getattr(ctx.req, "image_model", None) or ctx.user.get("image_model")
    if not wanted:
        return None
    row = catalog.get(ctx.db, wanted)
    return row if row and row["available"] and row["approved"] and row["image_out"] else None


def decode(images: list) -> tuple[bytes, str]:
    """Pull the first real picture out of an OpenRouter reply."""
    for item in images or []:
        url = item.get("image_url", {}).get("url") if isinstance(item, dict) else item
        if not isinstance(url, str):
            continue
        m = DATA_URL.match(url.strip())
        if not m:
            continue
        try:
            raw = base64.b64decode(m.group(1), validate=False)
        except (binascii.Error, ValueError):
            continue
        for magic, ext in MAGIC.items():
            if raw.startswith(magic):
                if len(raw) > MAX_BYTES:
                    raise ImageError("the generated image is too large to store")
                return raw, ext
    raise ImageError("the model returned no usable image")


async def generate(ctx, prompt: str, model: dict) -> dict:
    """Generate one picture and store it. Returns the workspace file row."""
    prompt = re.sub(r"\s+", " ", str(prompt or "")).strip()[:MAX_PROMPT]
    if len(prompt) < 10:
        raise ImageError("the image prompt was too short to use")
    res = await ctx.call("image", model, [
        {"role": "system", "content": "Generate exactly one image for the description. No text in the image unless "
                                      "the description asks for a label. Return the image only."},
        {"role": "user", "content": prompt}], max_tokens=1200, modalities=["image", "text"])
    raw, ext = decode(res.images)
    workspace.check_storage(ctx.db, ctx.user["id"], ctx.plan, len(raw))
    d = workspace.task_dir(ctx.user["id"], ctx.task["id"])
    slug = re.sub(r"[^a-z0-9]+", "-", prompt.lower()).strip("-")[:40] or "image"
    path = d / "out" / f"{slug}.{ext}"
    n = 2
    while path.exists():
        path = d / "out" / f"{slug}-{n}.{ext}"
        n += 1
    path.write_bytes(raw)
    return workspace.register(ctx.db, ctx.user["id"], ctx.task["id"], path, ext, ctx.plan)
