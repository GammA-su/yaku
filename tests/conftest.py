"""Shared pytest setup.

Force Qt to the offscreen platform so widget-level tests run headless (CI, no
display).  Done before any PyQt6 import.  Uses ``setdefault`` so a developer can
still override with a real platform when debugging locally.
"""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
