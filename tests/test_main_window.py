"""Tests for the GUI launcher window."""
from __future__ import annotations


class _FakeProcess:
    def __init__(self) -> None:
        self.terminated = False
        self.killed = False
        self.waits = 0

    def poll(self):
        return None if not self.terminated and not self.killed else 0

    def terminate(self) -> None:
        self.terminated = True

    def kill(self) -> None:
        self.killed = True

    def wait(self, timeout=None):  # noqa: ANN001
        self.waits += 1
        return 0


def test_main_window_stop_terminates_run_process(monkeypatch):
    from yaku.ui.app import get_app
    from yaku.ui.main_window import MainWindow

    get_app()
    launched = []
    fake = _FakeProcess()

    def fake_popen(cmd):
        launched.append(cmd)
        return fake

    monkeypatch.setattr("subprocess.Popen", fake_popen)

    window = MainWindow(profile="test-vn")
    window._start()
    window._stop()

    assert launched
    assert "--run" in launched[0]
    assert "--profile" in launched[0]
    assert "test-vn" in launched[0]
    assert fake.terminated is True
    assert fake.waits == 1
