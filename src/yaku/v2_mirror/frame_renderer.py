"""Composite translated text into a captured frame.

Two render modes are implemented:

- ``mask-text``  — draw a semi-transparent rectangle over the replacement
  region and render the translation on top.
- ``inpaint-text`` — erase the original text region (OpenCV inpaint), then draw
  the exact translated English on the cleaned background.  Falls back to
  ``mask-text`` if inpainting fails and ``fallback_to_mask_text`` is set.

``ai-text-edit`` is still reserved for later.
"""
from __future__ import annotations

import hashlib
from typing import Optional

from PIL import Image, ImageDraw, ImageFont

from yaku.core.config import V2MirrorConfig
from yaku.core.image_utils import NormalizedRect, Rect, clamp_rect, normalized_to_rect
from yaku.core.logging import get_logger
from yaku.render.text_draw import draw_text_block
from yaku.render.text_fit import AnyFont, fit_wrapped_text
from yaku.v2_mirror.ai_text_edit import BaseAITextEditor
from yaku.v2_mirror.inpaint import BaseInpainter, build_rect_mask

_log = get_logger("frame_renderer")

# Candidate truetype fonts tried in order before falling back to PIL's default.
_FONT_CANDIDATES: tuple[str, ...] = (
    "arial.ttf",
    "DejaVuSans.ttf",
    "Arial.ttf",
    "segoeui.ttf",
)


def _load_font(size: int) -> AnyFont:
    """Return a scalable font at *size* px, falling back gracefully.

    Tries common system truetype fonts first (so text auto-fit works), then
    Pillow's built-in scalable default, then the legacy bitmap default.
    """
    for name in _FONT_CANDIDATES:
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    try:
        return ImageFont.load_default(size=size)
    except TypeError:  # Pillow < 10.1 — non-scalable default
        return ImageFont.load_default()


class FrameRenderer:
    """Render translated text into captured frames according to ``render_mode``."""

    def __init__(
        self,
        config: V2MirrorConfig,
        inpainter: Optional[BaseInpainter] = None,
        cache=None,
        ai_editor: "Optional[BaseAITextEditor]" = None,
    ) -> None:
        self._config = config
        self._cache = cache
        # Tunables for the text overlay.
        self._box_alpha = 165          # 0-255 opacity of the mask-text rectangle
        self._padding = 10             # inner padding (px) inside the box
        self._text_fill = (255, 255, 255, 255)

        # Inpainter is created lazily on first inpaint-text render unless one
        # is injected (tests).  ``_inpainter_failed`` latches a creation error
        # so we don't retry every frame.
        self._inpainter = inpainter
        self._inpainter_failed = False
        # AI editor is likewise lazily created / injectable.
        self._ai_editor = ai_editor
        self._ai_editor_failed = False
        # (source_text, translated_text) pairs already written to the edit cache.
        self._cached_edits: set[tuple[str, str]] = set()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def render(self, frame: Image.Image, text: str, source_text: str = "") -> Image.Image:
        """Return a new frame with *text* rendered per ``render_mode``.

        The input *frame* is never mutated.  The result is the same size and
        ``RGB`` mode as the input.  Empty/whitespace *text* returns an
        unmodified copy.  *source_text* is only used for edit-cache bookkeeping
        in ``inpaint-text`` mode.
        """
        mode = self._config.render_mode
        if mode == "mask-text":
            return self._render_mask_text(frame, text)
        if mode == "inpaint-text":
            return self._render_inpaint_text(frame, text, source_text)
        if mode == "ai-text-edit":
            return self._render_ai_text_edit(frame, text, source_text)
        raise NotImplementedError(f"render_mode '{mode}' is not implemented yet")

    def close(self) -> None:
        """Release backend resources (e.g. the AI editor's HTTP client)."""
        if self._ai_editor is not None:
            try:
                self._ai_editor.close()
            except Exception:  # noqa: BLE001 — best-effort cleanup
                pass

    # ------------------------------------------------------------------
    # Shared helpers
    # ------------------------------------------------------------------

    def _replacement_rect(self, frame_w: int, frame_h: int) -> Rect:
        rr = self._config.replacement_region
        norm = NormalizedRect(rr.x_ratio, rr.y_ratio, rr.w_ratio, rr.h_ratio)
        rect = normalized_to_rect(norm, frame_w, frame_h)
        return clamp_rect(rect, frame_w, frame_h)

    def _draw_translated_text(
        self,
        base_rgb: Image.Image,
        rect: Rect,
        text: str,
        *,
        draw_box: bool,
    ) -> Image.Image:
        """Auto-fit *text* into *rect* and composite it onto *base_rgb*."""
        rgba = base_rgb.convert("RGBA")
        overlay = Image.new("RGBA", rgba.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)

        if draw_box:
            draw.rectangle(
                (rect.x, rect.y, rect.x + rect.w, rect.y + rect.h),
                fill=(0, 0, 0, self._box_alpha),
            )

        box_w = max(1, rect.w - 2 * self._padding)
        box_h = max(1, rect.h - 2 * self._padding)
        fitted = fit_wrapped_text(text, box_w, box_h, _load_font)

        total_h = len(fitted.lines) * fitted.line_height
        ty = rect.y + self._padding + max(0, (box_h - total_h) // 2)
        draw_text_block(
            draw,
            fitted.lines,
            rect.x + self._padding,
            ty,
            fitted.font,
            fitted.line_height,
            fill=self._text_fill,
            outline=True,
        )

        composed = Image.alpha_composite(rgba, overlay)
        return composed.convert("RGB")

    # ------------------------------------------------------------------
    # mask-text
    # ------------------------------------------------------------------

    def _render_mask_text(self, frame: Image.Image, text: str) -> Image.Image:
        base = frame.convert("RGB")
        if not text or not text.strip():
            return base
        rect = self._replacement_rect(base.width, base.height)
        if rect.w <= 0 or rect.h <= 0:
            return base
        return self._draw_translated_text(base, rect, text, draw_box=True)

    # ------------------------------------------------------------------
    # inpaint-text
    # ------------------------------------------------------------------

    def _get_inpainter(self) -> Optional[BaseInpainter]:
        if self._inpainter is not None:
            return self._inpainter
        if self._inpainter_failed:
            return None
        try:
            from yaku.v2_mirror.inpaint import create_inpainter
            self._inpainter = create_inpainter(self._config.inpaint)
        except Exception as exc:  # noqa: BLE001
            _log.error("Inpainter unavailable: %s", exc)
            self._inpainter_failed = True
            return None
        return self._inpainter

    def _render_inpaint_text(
        self, frame: Image.Image, text: str, source_text: str
    ) -> Image.Image:
        base = frame.convert("RGB")
        if not text or not text.strip():
            return base
        rect = self._replacement_rect(base.width, base.height)
        if rect.w <= 0 or rect.h <= 0:
            return base

        mask = build_rect_mask(base.size, rect, self._config.inpaint.mask_padding)
        inpainter = self._get_inpainter()
        try:
            if inpainter is None:
                raise RuntimeError("no inpainter available")
            cleaned = inpainter.inpaint(base, mask)
        except Exception as exc:  # noqa: BLE001
            _log.error("Inpaint failed (%s)", exc)
            if self._config.inpaint.fallback_to_mask_text:
                _log.info("Falling back to mask-text rendering.")
                return self._render_mask_text(frame, text)
            cleaned = base  # draw exact text directly on the original frame

        result = self._draw_translated_text(cleaned, rect, text, draw_box=False)

        if self._config.inpaint.debug_draw_mask:
            result = self._draw_mask_outline(result, rect, self._config.inpaint.mask_padding)

        self._maybe_cache_edit(base, source_text, text, mask)
        return result

    def _draw_mask_outline(self, image: Image.Image, rect: Rect, padding: int) -> Image.Image:
        out = image.convert("RGB")
        draw = ImageDraw.Draw(out)
        padded = clamp_rect(
            Rect(rect.x - padding, rect.y - padding, rect.w + 2 * padding, rect.h + 2 * padding),
            out.width,
            out.height,
        )
        draw.rectangle(
            (padded.x, padded.y, padded.x + padded.w - 1, padded.y + padded.h - 1),
            outline=(255, 0, 0, 255),
            width=2,
        )
        return out

    # ------------------------------------------------------------------
    # ai-text-edit (experimental)
    # ------------------------------------------------------------------

    def _get_ai_editor(self) -> Optional[BaseAITextEditor]:
        if self._ai_editor is not None:
            return self._ai_editor
        if self._ai_editor_failed:
            return None
        try:
            from yaku.v2_mirror.ai_text_edit import create_ai_text_editor
            self._ai_editor = create_ai_text_editor(self._config.ai_text_edit)
        except Exception as exc:  # noqa: BLE001
            _log.error("AI text editor unavailable: %s", exc)
            self._ai_editor_failed = True
            return None
        return self._ai_editor

    def _render_fallback(
        self, frame: Image.Image, text: str, source_text: str
    ) -> Image.Image:
        """Render via the configured AI fallback mode."""
        if self._config.ai_text_edit.fallback == "mask-text":
            return self._render_mask_text(frame, text)
        return self._render_inpaint_text(frame, text, source_text)

    def _render_ai_text_edit(
        self, frame: Image.Image, text: str, source_text: str
    ) -> Image.Image:
        base = frame.convert("RGB")
        if not text or not text.strip():
            return base
        rect = self._replacement_rect(base.width, base.height)
        if rect.w <= 0 or rect.h <= 0:
            return base

        cfg = self._config.ai_text_edit
        if not cfg.enabled:
            _log.warning(
                "ai-text-edit is disabled; falling back to %s.", cfg.fallback
            )
            return self._render_fallback(frame, text, source_text)

        editor = self._get_ai_editor()
        if editor is None:
            _log.warning(
                "ai-text-edit backend unavailable; falling back to %s.", cfg.fallback
            )
            return self._render_fallback(frame, text, source_text)

        mask = build_rect_mask(base.size, rect, self._config.inpaint.mask_padding)
        try:
            edited = editor.edit_text(base, mask, text, style_hint=self._style_hint(rect))
        except Exception as exc:  # noqa: BLE001 — never crash the display loop
            _log.warning(
                "ai-text-edit failed (%s); falling back to %s.", exc, cfg.fallback
            )
            return self._render_fallback(frame, text, source_text)

        if edited.size != base.size:
            edited = edited.resize(base.size)

        if cfg.deterministic_text_after_ai:
            # AI is used only to clean/style the region; the exact English is
            # re-rendered deterministically so we never trust AI spelling.
            return self._draw_translated_text(edited, rect, text, draw_box=False)

        _log.warning(
            "ai-text-edit: using AI-rendered text directly (EXPERIMENTAL — may "
            "misspell). source=%r",
            source_text,
        )
        return edited.convert("RGB")

    def _style_hint(self, rect: Rect) -> dict:
        return {
            "box": [rect.x, rect.y, rect.w, rect.h],
            "target_lang": "en",
        }

    # ------------------------------------------------------------------
    # Edit-frame metadata cache
    # ------------------------------------------------------------------

    def _maybe_cache_edit(
        self, frame: Image.Image, source_text: str, text: str, mask: Image.Image
    ) -> None:
        """Record metadata for an edited frame keyed by hash + texts + mode.

        Writes once per unique ``(source_text, translation)`` pair to avoid
        flooding the DB with one row per live frame.  The image itself is not
        persisted (``image_path=None``) — only metadata.
        """
        if self._cache is None or not source_text:
            return
        key = (source_text, text)
        if key in self._cached_edits:
            return
        try:
            frame_hash = hashlib.sha1(frame.tobytes()).hexdigest()[:16]
            bbox = mask.getbbox()
            self._cache.put_frame_edit(
                frame_hash=frame_hash,
                source_text=source_text,
                translated_text=text,
                render_mode="inpaint-text",
                image_path=None,
                metadata={
                    "method": self._config.inpaint.method,
                    "radius": self._config.inpaint.radius,
                    "mask_padding": self._config.inpaint.mask_padding,
                    "mask_bbox": list(bbox) if bbox else None,
                },
            )
            self._cached_edits.add(key)
        except Exception as exc:  # noqa: BLE001 — caching is best-effort
            _log.debug("Edit-frame cache write skipped: %s", exc)
