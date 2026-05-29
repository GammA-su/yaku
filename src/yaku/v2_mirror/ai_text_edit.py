"""Experimental AI text-editing backends for the ``ai-text-edit`` render mode.

This is a thin, generic adapter layer for *future* local models such as
AnyText2 or SD-inpainting servers (ComfyUI / Automatic1111 / a custom server).
No specific model API is implemented deeply, and **no AI package is required**
to import or run Yaku — missing/disabled backends degrade gracefully and the
renderer falls back to ``inpaint-text``.

AI-generated text is never trusted by default: see
``ai_text_edit.deterministic_text_after_ai`` in the config, which re-draws the
exact translated English with the deterministic renderer after the AI pass.
"""
from __future__ import annotations

import io
import json
from abc import ABC, abstractmethod
from typing import Optional

from PIL import Image

from yaku.core.config import AITextEditConfig
from yaku.core.errors import AITextEditError
from yaku.core.logging import get_logger

_log = get_logger("ai_text_edit")


def _to_png_bytes(image: Image.Image) -> bytes:
    buf = io.BytesIO()
    image.save(buf, format="PNG")
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Interface
# ---------------------------------------------------------------------------

class BaseAITextEditor(ABC):
    """Edits the masked region of a frame to render *target_text* natively."""

    @abstractmethod
    def edit_text(
        self,
        image: Image.Image,
        mask: Image.Image,
        target_text: str,
        style_hint: Optional[dict] = None,
    ) -> Image.Image:
        """Return a new frame with the masked region edited to show *target_text*.

        The result must be the same size as *image* (callers may resize
        defensively).  Implementations raise :class:`AITextEditError` on any
        failure so the renderer can fall back.
        """

    def close(self) -> None:
        """Release any held resources (HTTP clients, model handles, …)."""


# ---------------------------------------------------------------------------
# Disabled backend
# ---------------------------------------------------------------------------

class DisabledAITextEditor(BaseAITextEditor):
    """Placeholder used when AI editing is disabled or unconfigured.

    Every call raises :class:`AITextEditError` with a clear message so the
    renderer falls back to a deterministic mode.
    """

    def __init__(self, reason: str = "AI text editing is disabled") -> None:
        self._reason = reason

    def edit_text(
        self,
        image: Image.Image,
        mask: Image.Image,
        target_text: str,
        style_hint: Optional[dict] = None,
    ) -> Image.Image:
        raise AITextEditError(self._reason)


# ---------------------------------------------------------------------------
# External HTTP backend (generic adapter)
# ---------------------------------------------------------------------------

class ExternalHTTPAITextEditor(BaseAITextEditor):
    """Generic adapter for an external image-editing HTTP server.

    Posts a multipart request (``image`` + ``mask`` PNGs, ``target_text`` and
    ``style_hint`` JSON) to *endpoint* and expects raw image bytes back.  This
    is intentionally model-agnostic — a real AnyText2/ComfyUI/A1111 integration
    would subclass or wrap this with the server's exact route and payload.

    Pass ``_transport`` (an ``httpx.BaseTransport``) to inject a mock in tests.
    """

    def __init__(
        self,
        endpoint: str,
        timeout_sec: float = 30.0,
        *,
        _transport=None,
    ) -> None:
        try:
            import httpx
        except ImportError as exc:  # httpx is a core dep, but stay defensive
            raise AITextEditError(
                "httpx is required for the external_http AI backend"
            ) from exc

        self._httpx = httpx
        self._endpoint = endpoint
        self._client = httpx.Client(timeout=timeout_sec, transport=_transport)

    def edit_text(
        self,
        image: Image.Image,
        mask: Image.Image,
        target_text: str,
        style_hint: Optional[dict] = None,
    ) -> Image.Image:
        files = {
            "image": ("image.png", _to_png_bytes(image.convert("RGB")), "image/png"),
            "mask": ("mask.png", _to_png_bytes(mask.convert("L")), "image/png"),
        }
        data = {
            "target_text": target_text,
            "style_hint": json.dumps(style_hint or {}),
        }

        try:
            resp = self._client.post(self._endpoint, files=files, data=data)
            resp.raise_for_status()
        except self._httpx.HTTPError as exc:
            raise AITextEditError(f"AI edit request failed: {exc}") from exc

        content = resp.content
        if not content:
            raise AITextEditError("AI edit server returned an empty response")

        try:
            edited = Image.open(io.BytesIO(content))
            edited.load()
        except Exception as exc:  # noqa: BLE001 — any decode failure is invalid
            ctype = resp.headers.get("content-type", "?")
            raise AITextEditError(
                f"AI edit server returned a non-image response (content-type={ctype})"
            ) from exc

        edited = edited.convert("RGB")
        if edited.size != image.size:
            # Preserve full frame size regardless of what the server returned.
            edited = edited.resize(image.size)
        return edited

    def close(self) -> None:
        self._client.close()


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def create_ai_text_editor(config: AITextEditConfig) -> BaseAITextEditor:
    """Return an AI text editor for *config*.

    Returns a :class:`DisabledAITextEditor` when editing is turned off or the
    backend name is unknown — this never raises, so callers can construct one
    unconditionally and rely on ``edit_text`` raising at use time.
    """
    if not config.enabled:
        return DisabledAITextEditor("AI text editing is disabled in config")

    if config.backend == "external_http":
        return ExternalHTTPAITextEditor(config.endpoint, float(config.timeout_sec))

    _log.warning("Unknown ai_text_edit backend %r; treating as disabled.", config.backend)
    return DisabledAITextEditor(f"Unknown AI backend '{config.backend}'")
