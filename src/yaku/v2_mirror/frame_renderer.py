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
from yaku.render.style_extract import estimate_text_style, TextStyle
from yaku.render.text_draw import draw_text_box
from yaku.v2_mirror.ai_text_edit import BaseAITextEditor
from yaku.v2_mirror.inpaint import BaseInpainter, build_rect_mask

_log = get_logger("frame_renderer")


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

        # In-memory display layer cache: (crop_hash, translated_text, render_mode) -> rendered crop
        self._edited_layer_cache: dict[tuple[str, str, str], Image.Image] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def render(
        self,
        frame: Image.Image,
        text: str,
        source_text: Optional[str] = "",
        config: Optional[V2MirrorConfig] = None,
    ) -> Image.Image:
        """Return a new frame with *text* rendered per ``render_mode``.

        The input *frame* is never mutated.  The result is the same size and
        ``RGB`` mode as the input.  Empty/whitespace *text* returns an
        unmodified copy.  *source_text* is only used for style estimation and
        edit-cache bookkeeping.
        """
        cfg = config if config is not None else self._config
        mode = cfg.render_mode

        if not text or not text.strip():
            return frame.convert("RGB")

        rep_rect = self._replacement_rect(frame.width, frame.height, cfg)
        if rep_rect.w <= 0 or rep_rect.h <= 0:
            return frame.convert("RGB")

        # Check in-memory display layer cache of cleaned background crop
        crop = frame.crop((rep_rect.x, rep_rect.y, rep_rect.x + rep_rect.w, rep_rect.y + rep_rect.h))
        crop_hash = hashlib.sha1(crop.tobytes()).hexdigest()

        # Cache key includes text ONLY for ai-text-edit (since text is burned in by AI)
        cache_text = text if mode == "ai-text-edit" else ""
        cache_key = (crop_hash, cache_text, mode)

        base = frame.convert("RGB")

        if cache_key in self._edited_layer_cache:
            cleaned_crop = self._edited_layer_cache[cache_key]
            cleaned = base.copy()
            cleaned.paste(cleaned_crop, (rep_rect.x, rep_rect.y))
        else:
            # Cache miss: prepare background
            if mode == "mask-text":
                cleaned = self._prepare_mask_background(base, cfg)
            elif mode == "inpaint-text":
                cleaned = self._prepare_inpaint_background(base, rep_rect, cfg)
                # metadata caching to sqlite DB:
                mask = build_rect_mask(base.size, rep_rect, cfg.inpaint.mask_padding)
                self._maybe_cache_edit(base, source_text or "", text, mask, cfg)
            elif mode == "ai-text-edit":
                cleaned = self._prepare_ai_background(base, text, source_text or "", rep_rect, cfg)
            else:
                raise NotImplementedError(f"render_mode '{mode}' is not implemented yet")

            # Crop the cleaned replacement region and store in cache
            cleaned_crop = cleaned.crop((rep_rect.x, rep_rect.y, rep_rect.x + rep_rect.w, rep_rect.y + rep_rect.h))
            if len(self._edited_layer_cache) >= 200:
                self._edited_layer_cache.pop(next(iter(self._edited_layer_cache)))
            self._edited_layer_cache[cache_key] = cleaned_crop

        # Determine if we should draw the deterministic text overlay
        if mode == "ai-text-edit":
            ai_cfg = cfg.ai_text_edit
            if ai_cfg.enabled:
                editor = self._get_ai_editor(cfg)
                if editor is not None and not ai_cfg.deterministic_text_after_ai:
                    # Cleaned background already contains the AI-generated text, no overlay needed
                    return cleaned

        text_rect = self._text_rect(base.width, base.height, cfg)

        # Estimate text style if enabled (only relevant for inpaint-text)
        style = None
        if mode == "inpaint-text" and cfg.render_text.sample_style_from_source and source_text:
            crop_rect = text_rect
            if crop_rect.w > 0 and crop_rect.h > 0:
                original_crop = base.crop((crop_rect.x, crop_rect.y, crop_rect.x + crop_rect.w, crop_rect.y + crop_rect.h))
                try:
                    style = estimate_text_style(original_crop)
                except Exception as exc:
                    _log.debug("Style extraction failed, falling back: %s", exc)

        if style is None:
            style = TextStyle(
                fill_rgb=tuple(cfg.render_text.fallback_fill),
                stroke_rgb=tuple(cfg.render_text.fallback_stroke),
            )

        result = self._draw_translated_text(
            cleaned, rep_rect, text_rect, text, cfg, draw_box=False, style=style
        )

        if mode == "inpaint-text" and cfg.inpaint.debug_draw_mask:
            result = self._draw_mask_outline(result, rep_rect, cfg.inpaint.mask_padding)

        return result

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

    def _replacement_rect(self, frame_w: int, frame_h: int, cfg: V2MirrorConfig) -> Rect:
        rr = cfg.replacement_region
        norm = NormalizedRect(rr.x_ratio, rr.y_ratio, rr.w_ratio, rr.h_ratio)
        rect = normalized_to_rect(norm, frame_w, frame_h)
        return clamp_rect(rect, frame_w, frame_h)

    def _text_rect(self, frame_w: int, frame_h: int, cfg: V2MirrorConfig) -> Rect:
        tr = cfg.text_region
        norm = NormalizedRect(tr.x_ratio, tr.y_ratio, tr.w_ratio, tr.h_ratio)
        rect = normalized_to_rect(norm, frame_w, frame_h)
        return clamp_rect(rect, frame_w, frame_h)

    def _draw_translated_text(
        self,
        base_rgb: Image.Image,
        rep_rect: Rect,
        text_rect: Rect,
        text: str,
        cfg: V2MirrorConfig,
        *,
        draw_box: bool,
        style: TextStyle,
    ) -> Image.Image:
        """Compose *text* in *text_rect* using the given *style*."""
        rgba = base_rgb.convert("RGBA")
        overlay = Image.new("RGBA", rgba.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)

        if draw_box:
            draw.rectangle(
                (rep_rect.x, rep_rect.y, rep_rect.x + rep_rect.w, rep_rect.y + rep_rect.h),
                fill=(0, 0, 0, self._box_alpha),
            )
            base_rgb = Image.alpha_composite(rgba, overlay).convert("RGB")

        # Map style parameter to draw_text_box format
        style_dict = {
            "fill_rgb": style.fill_rgb,
            "stroke_rgb": style.stroke_rgb,
            "font_size": style.estimated_font_size or cfg.render_text.font_size,
            "font_path": cfg.render_text.font_path,
            "font_family": cfg.render_text.font_family,
            "auto_fit": cfg.render_text.auto_fit,
            "min_font_size": cfg.render_text.min_font_size,
            "max_font_size": cfg.render_text.max_font_size,
            "line_spacing": cfg.render_text.line_spacing,
            "stroke_width": cfg.render_text.stroke_width,
            "alignment": "left",
        }

        return draw_text_box(base_rgb, text, text_rect, style_dict)

    # ------------------------------------------------------------------
    # mask-text background
    # ------------------------------------------------------------------

    def _prepare_mask_background(self, base: Image.Image, cfg: V2MirrorConfig) -> Image.Image:
        rep_rect = self._replacement_rect(base.width, base.height, cfg)
        rgba = base.convert("RGBA")
        overlay = Image.new("RGBA", rgba.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)
        draw.rectangle(
            (rep_rect.x, rep_rect.y, rep_rect.x + rep_rect.w, rep_rect.y + rep_rect.h),
            fill=(0, 0, 0, self._box_alpha),
        )
        return Image.alpha_composite(rgba, overlay).convert("RGB")

    # ------------------------------------------------------------------
    # inpaint-text background
    # ------------------------------------------------------------------

    def _get_inpainter(self, cfg: V2MirrorConfig) -> Optional[BaseInpainter]:
        if self._inpainter is not None:
            return self._inpainter
        if self._inpainter_failed:
            return None
        try:
            from yaku.v2_mirror.inpaint import create_inpainter
            self._inpainter = create_inpainter(cfg.inpaint)
        except Exception as exc:  # noqa: BLE001
            _log.error("Inpainter unavailable: %s", exc)
            self._inpainter_failed = True
            return None
        return self._inpainter

    def _prepare_inpaint_background(
        self, base: Image.Image, rep_rect: Rect, cfg: V2MirrorConfig
    ) -> Image.Image:
        mask = build_rect_mask(base.size, rep_rect, cfg.inpaint.mask_padding)
        inpainter = self._get_inpainter(cfg)
        try:
            if inpainter is None:
                raise RuntimeError("no inpainter available")
            cleaned = inpainter.inpaint(base, mask)
        except Exception as exc:  # noqa: BLE001
            _log.error("Inpaint failed (%s)", exc)
            if cfg.inpaint.fallback_to_mask_text:
                _log.info("Falling back to mask-text background.")
                return self._prepare_mask_background(base, cfg)
            cleaned = base  # draw exact text directly on original frame
        return cleaned

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
    # ai-text-edit background
    # ------------------------------------------------------------------

    def _get_ai_editor(self, cfg: V2MirrorConfig) -> Optional[BaseAITextEditor]:
        if self._ai_editor is not None:
            return self._ai_editor
        if self._ai_editor_failed:
            return None
        try:
            from yaku.v2_mirror.ai_text_edit import create_ai_text_editor
            self._ai_editor = create_ai_text_editor(cfg.ai_text_edit)
        except Exception as exc:  # noqa: BLE001
            _log.error("AI text editor unavailable: %s", exc)
            self._ai_editor_failed = True
            return None
        return self._ai_editor

    def _prepare_ai_background(
        self, base: Image.Image, text: str, source_text: str, rep_rect: Rect, cfg: V2MirrorConfig
    ) -> Image.Image:
        ai_cfg = cfg.ai_text_edit
        if not ai_cfg.enabled:
            _log.warning(
                "ai-text-edit is disabled; falling back to %s.", ai_cfg.fallback
            )
            return self._prepare_ai_fallback(base, text, source_text, rep_rect, cfg)

        editor = self._get_ai_editor(cfg)
        if editor is None:
            _log.warning(
                "ai-text-edit backend unavailable; falling back to %s.", ai_cfg.fallback
            )
            return self._prepare_ai_fallback(base, text, source_text, rep_rect, cfg)

        mask = build_rect_mask(base.size, rep_rect, cfg.inpaint.mask_padding)
        try:
            # Delegate to 'edit' method (or edit_text alias)
            edited = editor.edit(base, mask, text, style_hint=self._style_hint(rep_rect))
        except Exception as exc:  # noqa: BLE001 — never crash the display loop
            _log.warning(
                "ai-text-edit failed (%s); falling back to %s.", exc, ai_cfg.fallback
            )
            return self._prepare_ai_fallback(base, text, source_text, rep_rect, cfg)

        if edited.size != base.size:
            edited = edited.resize(base.size)

        return edited.convert("RGB")

    def _prepare_ai_fallback(
        self, base: Image.Image, text: str, source_text: str, rep_rect: Rect, cfg: V2MirrorConfig
    ) -> Image.Image:
        """Render via the configured AI fallback mode."""
        ai_cfg = cfg.ai_text_edit
        if ai_cfg.fallback == "mask-text":
            return self._prepare_mask_background(base, cfg)
        return self._prepare_inpaint_background(base, rep_rect, cfg)

    def _style_hint(self, rect: Rect) -> dict:
        return {
            "box": [rect.x, rect.y, rect.w, rect.h],
            "target_lang": "en",
        }

    # ------------------------------------------------------------------
    # Edit-frame metadata cache
    # ------------------------------------------------------------------

    def _maybe_cache_edit(
        self, frame: Image.Image, source_text: str, text: str, mask: Image.Image, cfg: V2MirrorConfig
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
                    "method": cfg.inpaint.method,
                    "radius": cfg.inpaint.radius,
                    "mask_padding": cfg.inpaint.mask_padding,
                    "mask_bbox": list(bbox) if bbox else None,
                },
            )
            self._cached_edits.add(key)
        except Exception as exc:  # noqa: BLE001 — caching is best-effort
            _log.debug("Edit-frame cache write skipped: %s", exc)

