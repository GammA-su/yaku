"""Perceptual-hash gate — skip frames that haven't changed enough to re-process."""
from __future__ import annotations

from typing import Optional

import imagehash
from PIL import ImageChops
from PIL import Image


class HashGate:
    """Decide whether a new frame is different enough from the last processed one.

    Uses pHash (DCT-based perceptual hash).  Two frames are considered
    "the same" when their Hamming distance is <= *threshold* bits.

    Typical usage::

        gate = HashGate(threshold=6)
        if gate.should_process(pil_image):
            run_ocr_pipeline(pil_image)
    """

    def __init__(self, threshold: int = 0) -> None:
        """
        Args:
            threshold: Maximum bit-distance that still counts as "same frame".
                Increase for more tolerance to minor screen changes (subtitles,
                cursor blink).  0 means only exact hash matches are skipped.
                Typical useful range: 2–10.
        """
        self._threshold = threshold
        self._last_hash: Optional[imagehash.ImageHash] = None
        self._last_image: Optional[Image.Image] = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def should_process(self, image: Image.Image, force: bool = False) -> bool:
        """Return True when *image* should be sent through the OCR pipeline.

        Returns True when:
        - This is the first call after construction or :meth:`reset`.
        - ``force=True`` — unconditional processing regardless of similarity.
        - The pHash distance to the last processed image exceeds *threshold*.

        Returns False when the distance is within *threshold* (near-duplicate).

        The internal hash is updated **only** when True is returned, so
        subsequent calls keep comparing against the last *processed* frame.
        """
        if force:
            self._update(image)
            return True

        if self._threshold <= 0:
            if self._last_image is None or _images_differ(image, self._last_image):
                self._update(image)
                return True
            return False

        h = imagehash.phash(image)
        if self._last_hash is None or (h - self._last_hash) > self._threshold:
            self._update(image)
            return True
        return False

    def reset(self) -> None:
        """Clear stored state so the next :meth:`should_process` call always returns True."""
        self._last_hash = None
        self._last_image = None

    @property
    def last_hash(self) -> Optional[imagehash.ImageHash]:
        """pHash of the last *processed* image, or ``None`` before any processing."""
        return self._last_hash

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _update(self, image: Image.Image) -> None:
        """Compute and store the pHash for *image*."""
        self._last_hash = imagehash.phash(image)
        self._last_image = image.copy()


def _images_differ(left: Image.Image, right: Image.Image) -> bool:
    """Return true when two images differ at the pixel level."""
    if left.size != right.size or left.mode != right.mode:
        return True
    return ImageChops.difference(left, right).getbbox() is not None
