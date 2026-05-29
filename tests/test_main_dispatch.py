"""Tests for top-level command dispatch."""
from __future__ import annotations

import yaku.main as yaku_main


def _fail_gui(*args, **kwargs):  # noqa: ANN002, ANN003
    raise AssertionError("GUI should not be launched")


def test_no_args_launches_main_gui(monkeypatch):
    calls = []

    def launch_main_gui(profile=None, config_path=None):
        calls.append((profile, config_path))
        return 17

    monkeypatch.setattr(yaku_main, "launch_main_gui", launch_main_gui)

    assert yaku_main.main([]) == 17
    assert calls == [(None, None)]


def test_setup_launches_gui_wizard(monkeypatch):
    calls = []

    def launch_setup_wizard_gui(profile=None, config_path=None):
        calls.append((profile, config_path))
        return 23

    monkeypatch.setattr(yaku_main, "launch_setup_wizard_gui", launch_setup_wizard_gui)
    monkeypatch.setattr(yaku_main, "launch_main_gui", _fail_gui)

    assert yaku_main.main(["--setup"]) == 23
    assert calls == [(None, None)]


def test_profile_setup_launches_gui_wizard_for_profile(monkeypatch):
    calls = []

    def launch_setup_wizard_gui(profile=None, config_path=None):
        calls.append((profile, config_path))
        return 29

    monkeypatch.setattr(yaku_main, "launch_setup_wizard_gui", launch_setup_wizard_gui)
    monkeypatch.setattr(yaku_main, "launch_main_gui", _fail_gui)

    assert yaku_main.main(["--profile", "test-vn", "--setup"]) == 29
    assert calls == [("test-vn", None)]


def test_setup_cli_runs_terminal_setup(monkeypatch):
    calls = []

    def run_terminal_setup(profile=None, config_path=None):
        calls.append((profile, config_path))
        return 31

    monkeypatch.setattr(yaku_main, "run_terminal_setup", run_terminal_setup)
    monkeypatch.setattr(yaku_main, "launch_main_gui", _fail_gui)
    monkeypatch.setattr(yaku_main, "launch_setup_wizard_gui", _fail_gui)

    assert yaku_main.main(["--setup", "--cli"]) == 31
    assert calls == [(None, None)]


def test_health_check_does_not_call_gui(monkeypatch):
    calls = []

    def run_health_check_cli(config, config_path):
        calls.append((config.app.mode, config_path))
        return 0

    monkeypatch.setattr(yaku_main, "run_health_check_cli", run_health_check_cli)
    monkeypatch.setattr(yaku_main, "launch_main_gui", _fail_gui)
    monkeypatch.setattr(yaku_main, "launch_setup_wizard_gui", _fail_gui)

    assert yaku_main.main(["--health-check"]) == 0
    assert calls


def test_run_mode_does_not_call_gui_setup(monkeypatch):
    calls = []

    def run_app_controller(config, config_path):
        calls.append((config.app.mode, config_path))
        return 0

    monkeypatch.setattr(yaku_main, "run_app_controller", run_app_controller)
    monkeypatch.setattr(yaku_main, "launch_main_gui", _fail_gui)
    monkeypatch.setattr(yaku_main, "launch_setup_wizard_gui", _fail_gui)

    assert yaku_main.main(["--mode", "v1-overlay", "--run"]) == 0
    assert calls
    assert calls[0][0] == "v1-overlay"
