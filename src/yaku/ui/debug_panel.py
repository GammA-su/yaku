"""Floating debug and diagnostics panel for the Yaku overlay."""
from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QFormLayout,
    QLabel,
    QScrollArea,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)


class DebugPanel(QWidget):
    """Shows OCR and translation diagnostics updated live by the pipeline."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent, Qt.WindowType.Tool | Qt.WindowType.WindowStaysOnTopHint)
        self.setWindowTitle("Yaku Debug")
        self.resize(480, 340)

        root = QVBoxLayout(self)

        form_widget = QWidget()
        form = QFormLayout(form_widget)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)

        def _label(text: str = "-") -> QLabel:
            lbl = QLabel(text)
            lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            lbl.setWordWrap(True)
            return lbl

        self._ocr_raw = _label()
        self._ocr_clean = _label()
        self._translation = _label()
        self._backend = _label()
        self._cached = _label()
        self._ocr_ms = _label()
        self._trans_ms = _label()
        self._error = _label()
        self._error.setStyleSheet("color: #ff6060;")

        # Latency metrics (rolling averages).
        self._metrics = _label()
        self._errors = _label()

        # Input-forwarding diagnostics.
        self._target = _label()
        self._last_input = _label()
        self._mapped = _label()
        self._forward_status = _label()

        form.addRow("OCR raw:", self._ocr_raw)
        form.addRow("OCR clean:", self._ocr_clean)
        form.addRow("Translation:", self._translation)
        form.addRow("Backend:", self._backend)
        form.addRow("Cached:", self._cached)
        form.addRow("OCR ms:", self._ocr_ms)
        form.addRow("Trans ms:", self._trans_ms)
        form.addRow("Metrics:", self._metrics)
        form.addRow("Errors:", self._errors)
        form.addRow("Target:", self._target)
        form.addRow("Last input:", self._last_input)
        form.addRow("Mapped:", self._mapped)
        form.addRow("Forwarded:", self._forward_status)
        form.addRow("Error:", self._error)

        scroll = QScrollArea()
        scroll.setWidget(form_widget)
        scroll.setWidgetResizable(True)
        root.addWidget(scroll)

        self._log = QTextEdit()
        self._log.setReadOnly(True)
        self._log.setMaximumHeight(80)
        self._log.setPlaceholderText("Pipeline log")
        root.addWidget(self._log)

    def update_result(
        self,
        ocr_raw: str = "",
        ocr_clean: str = "",
        translation: str = "",
        backend: str = "",
        backend_model: Optional[str] = None,
        cached: bool = False,
        ocr_ms: Optional[float] = None,
        trans_ms: Optional[float] = None,
        error: str = "",
    ) -> None:
        """Refresh all fields from the latest pipeline result."""
        self._ocr_raw.setText(ocr_raw or "-")
        self._ocr_clean.setText(ocr_clean or "-")
        self._translation.setText(translation or "-")
        model_str = f"{backend}" + (f"/{backend_model}" if backend_model else "")
        self._backend.setText(model_str or "-")
        self._cached.setText("yes" if cached else "no")
        self._ocr_ms.setText(f"{ocr_ms:.1f}" if ocr_ms is not None else "-")
        self._trans_ms.setText(f"{trans_ms:.1f}" if trans_ms is not None else "-")
        self._error.setText(error or "-")
        if error:
            self._log.append(f"[ERR] {error}")

    def update_metrics(self, averages: dict, errors_count: int = 0) -> None:
        """Display rolling latency averages and the cumulative error count."""
        a = averages or {}
        self._metrics.setText(
            "cap {cap:.0f} hash {hash:.0f} ocr {ocr:.0f} "
            "tr {tr:.0f} rend {rend:.0f} tot {tot:.0f} ms  "
            "hit {hit:.0f}%  n={n}".format(
                cap=a.get("capture_ms", 0.0),
                hash=a.get("hash_ms", 0.0),
                ocr=a.get("ocr_ms", 0.0),
                tr=a.get("translate_ms", 0.0),
                rend=a.get("render_ms", 0.0),
                tot=a.get("total_ms", 0.0),
                hit=a.get("cache_hit_rate", 0.0) * 100.0,
                n=a.get("samples", 0),
            )
        )
        self._errors.setText(str(errors_count))
        self._errors.setStyleSheet("color: #ff6060;" if errors_count else "")

    def update_input(
        self,
        last_input: str = "",
        mapped: Optional[tuple[int, int]] = None,
        success: Optional[bool] = None,
        hwnd: Optional[int] = None,
        title: str = "",
    ) -> None:
        """Refresh the input-forwarding diagnostics fields."""
        if hwnd is not None or title:
            self._target.setText(
                f"hwnd={hwnd} {title}".strip() if hwnd is not None else (title or "-")
            )
        if last_input:
            self._last_input.setText(last_input)
        self._mapped.setText(f"{mapped[0]}, {mapped[1]}" if mapped is not None else "-")
        if success is not None:
            ok = "ok" if success else "FAILED"
            self._forward_status.setText(ok)
            self._forward_status.setStyleSheet(
                "color: #60c060;" if success else "color: #ff6060;"
            )
            self._log.append(f"[input] {last_input} → {self._mapped.text()} [{ok}]")

    def set_target(self, hwnd: Optional[int], title: str) -> None:
        """Set the current forwarding target shown in diagnostics."""
        if hwnd is None and not title:
            self._target.setText("-")
        else:
            self._target.setText(
                f"hwnd={hwnd} {title}".strip() if hwnd is not None else title
            )

    def log(self, message: str) -> None:
        self._log.append(message)

    def append(self, message: str) -> None:
        self._log.append(message)

    def clear(self) -> None:
        self._log.clear()
