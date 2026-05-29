"""Tests for HashGate perceptual-hash change detection."""
from __future__ import annotations

import numpy as np
import pytest
from PIL import Image

from yaku.core.hash_gate import HashGate


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _solid(value: int, size: int = 64) -> Image.Image:
    """Return a solid-colour RGB PIL image."""
    return Image.fromarray(np.full((size, size, 3), value, dtype=np.uint8))


def _noise(seed: int = 0, size: int = 64) -> Image.Image:
    """Deterministic pseudo-random noise image.

    pHash of noise has ~32 bits set; phash of any solid colour has 0–1 bits,
    so the Hamming distance is reliably >> 6 (our default threshold).
    """
    rng = np.random.default_rng(seed)
    arr = rng.integers(0, 256, (size, size, 3), dtype=np.uint8)
    return Image.fromarray(arr)


# ---------------------------------------------------------------------------
# Basic behaviour
# ---------------------------------------------------------------------------

def test_first_image_always_processed():
    gate = HashGate()
    assert gate.should_process(_solid(0)) is True


def test_identical_image_skipped():
    gate = HashGate()
    img = _solid(0)
    gate.should_process(img)
    assert gate.should_process(img) is False


def test_below_threshold_skipped():
    """Near-identical images (phash distance 0) must not trigger processing."""
    gate = HashGate(threshold=6)
    # brightness 128 vs 129 — perceptually indistinguishable, same phash
    gate.should_process(_solid(128))
    assert gate.should_process(_solid(129)) is False


def test_zero_threshold_processes_pixel_changes():
    gate = HashGate(threshold=0)
    gate.should_process(_solid(128))
    assert gate.should_process(_solid(129)) is True


def test_zero_threshold_skips_identical_pixels():
    gate = HashGate(threshold=0)
    img = _solid(128)
    gate.should_process(img)
    assert gate.should_process(img.copy()) is False


def test_above_threshold_processed():
    """Solid-colour vs noise image: Hamming distance is >> threshold=6."""
    gate = HashGate(threshold=6)
    gate.should_process(_solid(0))
    assert gate.should_process(_noise(seed=42)) is True


# ---------------------------------------------------------------------------
# force flag
# ---------------------------------------------------------------------------

def test_force_processes_identical_image():
    gate = HashGate()
    img = _solid(0)
    gate.should_process(img)
    assert gate.should_process(img, force=True) is True


def test_force_updates_hash_so_next_call_still_skips():
    """After a forced call, subsequent non-forced calls with the same image skip."""
    gate = HashGate()
    img = _solid(0)
    gate.should_process(img, force=True)
    assert gate.should_process(img) is False


def test_force_on_first_call():
    gate = HashGate()
    assert gate.should_process(_solid(0), force=True) is True


# ---------------------------------------------------------------------------
# reset
# ---------------------------------------------------------------------------

def test_reset_clears_last_hash():
    gate = HashGate()
    gate.should_process(_solid(0))
    gate.reset()
    assert gate.last_hash is None


def test_reset_causes_next_call_to_process():
    gate = HashGate()
    img = _solid(0)
    gate.should_process(img)
    gate.reset()
    assert gate.should_process(img) is True


# ---------------------------------------------------------------------------
# last_hash property
# ---------------------------------------------------------------------------

def test_last_hash_is_none_before_first_call():
    gate = HashGate()
    assert gate.last_hash is None


def test_last_hash_set_after_processing():
    gate = HashGate()
    gate.should_process(_solid(42))
    assert gate.last_hash is not None


def test_last_hash_not_updated_on_skip():
    """When a frame is skipped, last_hash must remain the hash of the last *processed* frame."""
    gate = HashGate(threshold=6)
    gate.should_process(_solid(0))   # processed — hash updated to black
    h_after_first = gate.last_hash
    gate.should_process(_solid(1))   # skipped (near-identical)
    assert gate.last_hash == h_after_first
