"""
Gemini screenshot analysis for MoGoStickers.

Sends the screenshot together with a structured JSON reference (the canonical
sticker names, grouped by album) so the model aligns its names to the database.
The model reports, per sticker it can see:
    owned  : is the sticker present in the album at all
    extras : the in-game "+N" duplicate badge (0 if no "+N" shown)
This maps 1:1 to the DB's ownership(owned, extras) — no "+1 -> total 2" math.
"""
import difflib
import io
import json
import os

from google import genai
from google.genai import types
from PIL import Image
from pydantic import BaseModel

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
MODEL_NAME = os.getenv("GEMINI_MODEL", "gemini-3.1-flash-lite")


class StickerInfo(BaseModel):
    name: str
    owned: bool
    extras: int  # the literal in-game "+N" duplicates (0 if none shown)


class SetInfo(BaseModel):
    set_name: str
    stickers: list[StickerInfo]


def _normalize(name):
    return " ".join((name or "").lower().split())


def crop_screenshot(image_bytes, mime_type=None, top=0.09, bottom=0.15):
    """Trim the top `top` and bottom `bottom` fractions (game UI noise) from a
    screenshot, keeping the middle band. Returns (cropped_bytes, mime_type).
    Fail-soft: returns the original bytes unchanged if decoding/encoding fails.
    """
    try:
        img = Image.open(io.BytesIO(image_bytes))
        img.load()
        w, h = img.size
        y0 = round(h * top)
        y1 = round(h * (1 - bottom))
        if y1 <= y0:  # degenerate (tiny image) — leave it alone
            return image_bytes, mime_type
        cropped = img.crop((0, y0, w, y1))
        fmt = img.format or ("PNG" if (mime_type or "").endswith("png") else "JPEG")
        if fmt == "JPEG" and cropped.mode in ("RGBA", "P"):
            cropped = cropped.convert("RGB")
        buf = io.BytesIO()
        cropped.save(buf, format=fmt)
        out_mime = "image/png" if fmt == "PNG" else "image/jpeg"
        return buf.getvalue(), out_mime
    except Exception:
        return image_bytes, mime_type


def build_reference(stickers):
    """Canonical names grouped by album — sent as JSON to anchor the model."""
    by_album = {}
    for s in stickers:
        by_album.setdefault(s["album"], []).append(s["name"])
    return by_album


def analyze(image_bytes, mime_type, stickers):
    """
    Returns (raw_response_dict, detected_list).
    detected_list items: {"name", "owned", "extras"} exactly as Gemini reported.
    Raises on API/parse errors so the caller can show the failure per-file.
    """
    client = genai.Client(api_key=GEMINI_API_KEY)
    reference_json = json.dumps(build_reference(stickers), ensure_ascii=False)

    prompt = (
        "You are reading a Monopoly GO sticker album screenshot.\n"
        "Use this reference of known sticker names (grouped by album) to keep names "
        "exact — match what you see to these names:\n"
        f"{reference_json}\n\n"
        "For every sticker visible in the screenshot, report:\n"
        "- name: the sticker name (use the reference spelling when it matches)\n"
        "- owned: true if the user has this sticker (it appears in their album), else false\n"
        "- extras: the number shown on the duplicate badge, e.g. a '+2' badge means extras=2. "
        "If the sticker is owned but shows no duplicate badge, extras=0.\n"
        "Do NOT convert to a total — report the '+N' value directly. "
        "Only include stickers you can actually see."
    )

    response = client.models.generate_content(
        model=MODEL_NAME,
        contents=[{"role": "user", "parts": [
            {"text": prompt},
            {"inline_data": {"mime_type": mime_type, "data": image_bytes}},
        ]}],
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=SetInfo,
        ),
    )
    raw = json.loads(response.text)
    detected = []
    for s in raw.get("stickers", []):
        detected.append({
            "name": (s.get("name") or "").strip(),
            "owned": bool(s.get("owned", False)),
            "extras": int(s.get("extras", 0) or 0),
        })
    return raw, detected


def match(detected_name, stickers):
    """
    Match a detected name to a DB sticker.
    Returns (sticker_or_None, method) where method is 'exact' | 'fuzzy' | 'unmatched'.
    """
    target = _normalize(detected_name)
    if not target:
        return None, "unmatched"

    norm_map = {_normalize(s["name"]): s for s in stickers}
    if target in norm_map:
        return norm_map[target], "exact"

    close = difflib.get_close_matches(target, list(norm_map.keys()), n=1, cutoff=0.84)
    if close:
        return norm_map[close[0]], "fuzzy"
    return None, "unmatched"
