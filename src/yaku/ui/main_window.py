"""Main GUI launcher window."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from PyQt6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)


class MainWindow(QMainWindow):
    """Small GUI-first launcher for common Yaku actions."""

    def __init__(self, profile: str | None = None, config_path: str | None = None) -> None:
        super().__init__()
        self.profile = profile
        self.config_path = config_path
        self._run_process: subprocess.Popen | None = None

        self.setWindowTitle("Yaku")
        self.resize(560, 420)

        root = QWidget(self)
        self.setCentralWidget(root)

        layout = QVBoxLayout(root)

        self.profile_label = QLabel(f"Profile: {profile or 'default'}")
        layout.addWidget(self.profile_label)

        form = QFormLayout()
        self.mode_combo = QComboBox()
        self.mode_combo.addItems(["v1-overlay", "v2-mirror"])
        form.addRow("Mode", self.mode_combo)

        self.translator_combo = QComboBox()
        self.translator_combo.addItems(["llama-cpp", "deepl"])
        form.addRow("Translator", self.translator_combo)

        self.target_lang_input = QLineEdit("en")
        form.addRow("Target language", self.target_lang_input)
        layout.addLayout(form)

        button_rows = [
            [
                ("Setup Wizard", self._open_setup_wizard),
                ("Pick Window", self._pick_window),
                ("Draw OCR Rectangle", self._select_ocr_region),
            ],
            [
                ("Draw Replacement Rectangle", self._select_replacement_region),
                ("Start", self._start),
                ("Stop", self._stop),
                ("Health Check", self._health_check),
                ("Logs", self._show_logs),
            ],
        ]
        for row in button_rows:
            row_layout = QHBoxLayout()
            for label, handler in row:
                button = QPushButton(label)
                button.clicked.connect(handler)
                row_layout.addWidget(button)
            layout.addLayout(row_layout)

    def _base_command(self) -> list[str]:
        cmd = [sys.executable, "-m", "yaku.main"]
        if self.profile:
            cmd.extend(["--profile", self.profile])
        if self.config_path:
            cmd.extend(["--config", self.config_path])
        return cmd

    def _run_command(self, args: list[str]) -> subprocess.Popen | None:
        try:
            return subprocess.Popen(self._base_command() + args)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "Yaku", f"Could not start command:\n{exc}")
            return None

    def _open_setup_wizard(self) -> None:
        self._run_command(["--setup"])

    def _pick_window(self) -> None:
        self._run_command(["--pick-window"])

    def _select_ocr_region(self) -> None:
        self._run_command(["--select-ocr-region"])

    def _select_replacement_region(self) -> None:
        self._run_command(["--select-replacement-region"])

    def _start(self) -> None:
        if self._run_process is not None and self._run_process.poll() is None:
            QMessageBox.information(self, "Yaku", "Yaku is already running.")
            return
        self._run_process = self._run_command(
            [
                "--mode",
                self.mode_combo.currentText(),
                "--translator",
                self.translator_combo.currentText(),
                "--target-lang",
                self.target_lang_input.text().strip() or "en",
                "--run",
            ]
        )

    def _stop(self) -> None:
        self._stop_run_process()

    def _stop_run_process(self) -> None:
        process = self._run_process
        self._run_process = None
        if process is None or process.poll() is not None:
            return
        process.terminate()
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=3)

    def _health_check(self) -> None:
        self._run_command(["--health-check"])

    def _show_logs(self) -> None:
        path = Path("out") / "yaku.log"
        if not path.exists():
            QMessageBox.information(self, "Yaku logs", "No log file found yet.")
            return

        dialog = QMessageBox(self)
        dialog.setWindowTitle("Yaku logs")
        viewer = QTextEdit()
        viewer.setReadOnly(True)
        viewer.setPlainText(path.read_text(encoding="utf-8", errors="replace")[-8000:])
        viewer.setMinimumSize(720, 420)
        dialog.layout().addWidget(viewer, 1, 0, 1, dialog.layout().columnCount())
        dialog.exec()

    def closeEvent(self, event) -> None:  # noqa: N802
        self._stop_run_process()
        super().closeEvent(event)
