"""Visual health check dialog for Yaku."""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from yaku.core.config import YakuConfig
from yaku.ui.health_check import run_health_checks, overall_status


class CheckResultWidget(QWidget):
    """Custom widget to represent a single check result row."""

    def __init__(self, check_result, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(52)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(16)

        # Status badge
        self.badge = QLabel(check_result.status.upper())
        self.badge.setFixedWidth(75)
        self.badge.setAlignment(Qt.AlignmentFlag.AlignCenter)

        status_colors = {
            "pass": ("#10b981", "#064e3b"),  # text, bg
            "warn": ("#fbbf24", "#78350f"),  # text, bg
            "fail": ("#f87171", "#7f1d1d"),  # text, bg
        }

        text_color, bg_color = status_colors.get(check_result.status, ("#94a3b8", "#1e293b"))
        self.badge.setStyleSheet(
            f"color: {text_color}; "
            f"background-color: {bg_color}; "
            f"border: 1px solid {text_color}44; "
            f"border-radius: 4px; "
            f"font-weight: bold; "
            f"font-size: 11px; "
            f"padding: 3px 6px;"
        )

        # Name
        self.name_lbl = QLabel(check_result.name)
        self.name_lbl.setStyleSheet("font-weight: bold; font-size: 13px; color: #ffffff;")
        self.name_lbl.setFixedWidth(130)

        # Message
        self.msg_lbl = QLabel(check_result.message)
        self.msg_lbl.setWordWrap(True)
        self.msg_lbl.setStyleSheet("color: #cbd5e1; font-size: 12px;")

        layout.addWidget(self.badge)
        layout.addWidget(self.name_lbl)
        layout.addWidget(self.msg_lbl, 1)  # allow message to stretch


class HealthCheckDialog(QDialog):
    """Dialogue to run health checks and view results visually."""

    def __init__(self, config: YakuConfig, config_path: Optional[Path], parent=None) -> None:
        super().__init__(parent)
        self.config = config
        self.config_path = config_path

        self.setWindowTitle("Yaku Diagnostics")
        self.resize(680, 460)

        layout = QVBoxLayout(self)
        layout.setSpacing(16)
        layout.setContentsMargins(20, 20, 20, 20)

        # Title Header
        header_layout = QVBoxLayout()
        header_layout.setSpacing(4)
        self.title_lbl = QLabel("System Diagnostics")
        self.title_lbl.setStyleSheet("font-size: 20px; font-weight: bold; color: #ffffff;")
        self.subtitle_lbl = QLabel("Verifying translation environments, key settings, and cache writes.")
        self.subtitle_lbl.setStyleSheet("color: #94a3b8; font-size: 12px;")
        header_layout.addWidget(self.title_lbl)
        header_layout.addWidget(self.subtitle_lbl)
        layout.addLayout(header_layout)

        # Results List
        self.list_widget = QListWidget()
        self.list_widget.setStyleSheet(
            "background-color: #0f172a; border: 1px solid #334155; border-radius: 8px;"
        )
        self.list_widget.setSelectionMode(QListWidget.SelectionMode.NoSelection)
        layout.addWidget(self.list_widget)

        # Bottom Summary & Action
        bottom_layout = QHBoxLayout()
        bottom_layout.setSpacing(12)
        
        self.overall_lbl = QLabel("Overall Status: Checking...")
        self.overall_lbl.setStyleSheet("font-weight: 600; font-size: 13px; color: #ffffff;")
        
        self.btn_recheck = QPushButton("Run Re-check")
        self.btn_recheck.setObjectName("btn_primary")
        self.btn_recheck.clicked.connect(self._run_check)
        
        self.btn_close = QPushButton("Close")
        self.btn_close.clicked.connect(self.accept)

        bottom_layout.addWidget(self.overall_lbl)
        bottom_layout.addStretch()
        bottom_layout.addWidget(self.btn_recheck)
        bottom_layout.addWidget(self.btn_close)
        layout.addLayout(bottom_layout)

        self._run_check()

    def _run_check(self) -> None:
        self.list_widget.clear()
        results = run_health_checks(self.config, self.config_path)

        for r in results:
            item = QListWidgetItem()
            self.list_widget.addItem(item)

            widget = CheckResultWidget(r)
            widget.adjustSize()
            item.setSizeHint(widget.sizeHint())
            self.list_widget.setItemWidget(item, widget)

        status = overall_status(results)
        status_text = {
            "pass": "SYSTEM OK",
            "warn": "WARNINGS ISSUED",
            "fail": "ISSUES FOUND",
        }.get(status, "UNKNOWN")

        status_colors = {
            "pass": "#10b981",
            "warn": "#fbbf24",
            "fail": "#f87171",
        }

        color = status_colors.get(status, "#94a3b8")
        self.overall_lbl.setText(
            f"Status: <span style='color: {color}; font-weight: bold;'>{status_text}</span>"
        )
