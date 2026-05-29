"""Simple PyQt6 settings panel for V1 overlay runtime options."""
from __future__ import annotations

from pathlib import Path
from typing import Callable, Optional

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from yaku.core.config import YakuConfig, save_config


class SettingsPanel(QDialog):
    """Small functional settings dialog that saves back to the active config."""

    def __init__(
        self,
        config: YakuConfig,
        config_path: Optional[Path],
        parent: Optional[QWidget] = None,
        *,
        on_saved: Optional[Callable[[], None]] = None,
    ) -> None:
        super().__init__(parent, Qt.WindowType.Tool)
        self.setWindowTitle("Yaku Settings")
        self._config = config
        self._config_path = config_path
        self._on_saved = on_saved

        root = QVBoxLayout(self)
        form = QFormLayout()
        root.addLayout(form)

        self._backend = QComboBox()
        self._backend.addItems(["llama_cpp", "deepl"])
        self._backend.setCurrentText(config.translator.backend)
        form.addRow("Translator backend", self._backend)

        self._ocr_backend = QComboBox()
        self._ocr_backend.addItems(["paddleocr", "manga_ocr", "dummy"])
        self._ocr_backend.setCurrentText(config.ocr.backend)
        form.addRow("OCR backend", self._ocr_backend)

        self._target_lang = QComboBox()
        self._target_lang.setEditable(True)
        self._target_lang.addItems(["en", "EN-US", "DE", "FR", "ES", "JA"])
        self._target_lang.setCurrentText(config.app.target_lang)
        form.addRow("Target language", self._target_lang)

        self._overlay_opacity = QDoubleSpinBox()
        self._overlay_opacity.setRange(0.10, 1.00)
        self._overlay_opacity.setSingleStep(0.05)
        self._overlay_opacity.setDecimals(2)
        self._overlay_opacity.setValue(config.v1_overlay.opacity)
        form.addRow("Overlay opacity", self._overlay_opacity)

        self._background_opacity = QDoubleSpinBox()
        self._background_opacity.setRange(0.00, 1.00)
        self._background_opacity.setSingleStep(0.05)
        self._background_opacity.setDecimals(2)
        self._background_opacity.setValue(config.v1_overlay.background_opacity)
        form.addRow("Background opacity", self._background_opacity)

        self._font_size = QSpinBox()
        self._font_size.setRange(8, 96)
        self._font_size.setValue(config.v1_overlay.font_size)
        form.addRow("Font size", self._font_size)

        self._click_through = QCheckBox()
        self._click_through.setChecked(config.v1_overlay.click_through)
        form.addRow("Click-through", self._click_through)

        self._locked = QCheckBox()
        self._locked.setChecked(config.v1_overlay.locked)
        form.addRow("Lock overlay", self._locked)

        self._tick_ms = QSpinBox()
        self._tick_ms.setRange(50, 5000)
        self._tick_ms.setSingleStep(50)
        self._tick_ms.setValue(config.app.tick_ms)
        form.addRow("Tick ms", self._tick_ms)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    def _save(self) -> None:
        self._config.translator.backend = self._backend.currentText()  # type: ignore[assignment]
        self._config.ocr.backend = self._ocr_backend.currentText()  # type: ignore[assignment]
        self._config.app.target_lang = self._target_lang.currentText().strip() or "en"
        self._config.v1_overlay.opacity = self._overlay_opacity.value()
        self._config.v1_overlay.background_opacity = self._background_opacity.value()
        self._config.v1_overlay.font_size = self._font_size.value()
        self._config.v1_overlay.click_through = self._click_through.isChecked()
        self._config.v1_overlay.locked = self._locked.isChecked()
        self._config.app.tick_ms = self._tick_ms.value()

        if self._config_path is not None:
            save_config(self._config, self._config_path)
        if self._on_saved is not None:
            self._on_saved()
        self.accept()
