"""Screen snapshot handling: re-compress server-side and analyse with a pluggable provider."""

from __future__ import annotations

import base64
import io
from typing import Any

from PIL import Image
from pydantic import BaseModel

from app.config import get_settings
from app.services.ai import get_ai_client
from intervue_ai import AIRequest, ImageInput, register_handler

MAX_EDGE = 1280


class ScreenAnalysis(BaseModel):
    summary: str
    visible_code_excerpt: str
    language_guess: str
    notes: list[str]


@register_handler("screen_analysis")
def _mock_screen(ctx: dict[str, Any]) -> ScreenAnalysis:
    return ScreenAnalysis(
        summary=f"Snapshot received ({ctx.get('width')}x{ctx.get('height')}). Content analysis is disabled in local mode.",
        visible_code_excerpt="",
        language_guess="unknown",
        notes=["Mock screen-analysis provider: no image understanding was performed."],
    )


def compress(data: bytes) -> tuple[bytes, int, int]:
    """Decode, strip metadata, downscale to MAX_EDGE and re-encode as JPEG q70."""
    with Image.open(io.BytesIO(data)) as src:
        img = src.convert("RGB")
        img.thumbnail((MAX_EDGE, MAX_EDGE))
        out = io.BytesIO()
        img.save(out, format="JPEG", quality=70, optimize=True)
        return out.getvalue(), img.width, img.height


async def analyze_snapshot(jpeg: bytes, width: int, height: int, reason: str) -> ScreenAnalysis:
    ctx = {"width": width, "height": height, "reason": reason}
    use_ai = get_settings().screen_analysis_provider == "ai" and not get_ai_client().primary.is_mock
    req = AIRequest(
        task="screen_analysis",
        schema=ScreenAnalysis,
        system="You describe a screenshot a candidate deliberately shared during a technical interview. Report only what is visible. "
        "Copy code exactly as shown. Never guess hidden content.",
        prompt=f"Reason for snapshot: {reason}. Describe what is on screen, focusing on any code.",
        context=ctx,
        images=[ImageInput(media_type="image/jpeg", data_b64=base64.b64encode(jpeg).decode())] if use_ai else [],
        effort="low",
        max_tokens=1500,
    )
    if not use_ai:
        return _mock_screen(ctx)
    result = await get_ai_client().run(req)
    return result.output
