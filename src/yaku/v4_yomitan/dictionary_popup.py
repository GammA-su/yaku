from __future__ import annotations

from PyQt6.QtCore import QPoint, Qt
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QApplication,
    QGraphicsDropShadowEffect,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from yaku.v4_yomitan.dictionary_lookup import DictionaryEntry


class DictionaryPopup(QWidget):
    """Translucent, frameless, always-on-top tooltip display for Yomitan lookup definitions."""

    def __init__(self, parent=None) -> None:
        super().__init__(
            parent,
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool,
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)

        # Main Layout
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)

        # Styled Container
        self.container = QWidget(self)
        self.container.setObjectName("popupContainer")
        self.container.setStyleSheet("""
            QWidget#popupContainer {
                background-color: rgba(20, 26, 38, 0.93);
                border: 1px solid rgba(255, 255, 255, 0.12);
                border-radius: 12px;
            }
        """)

        container_layout = QVBoxLayout(self.container)
        container_layout.setContentsMargins(12, 12, 12, 12)

        # Text Browser for rich HTML content
        self.browser = QTextBrowser(self.container)
        self.browser.setOpenExternalLinks(False)
        self.browser.setStyleSheet("""
            QTextBrowser {
                background-color: transparent;
                border: none;
            }
        """)
        container_layout.addWidget(self.browser)

        layout.addWidget(self.container)

        # Drop shadow for a premium elevated visual card appearance
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(18)
        shadow.setColor(QColor(0, 0, 0, 180))
        shadow.setOffset(0, 5)
        self.container.setGraphicsEffect(shadow)

        # Fixed dimensions or flexible bounds
        self.resize(380, 240)

    def set_entries(self, entries: list[DictionaryEntry]) -> None:
        """Renders the matching dictionary entries into structured CSS styled HTML."""
        if not entries:
            self.browser.setHtml("<div style='color: #94a3b8;'>No definition found.</div>")
            return

        html_parts = []
        html_parts.append("""
        <html>
        <head>
        <style>
            body {
                color: #e2e8f0;
                font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
                font-size: 13px;
                line-height: 1.45;
                margin: 0;
                padding: 0;
            }
            .entry {
                margin-bottom: 14px;
                border-bottom: 1px solid rgba(255, 255, 255, 0.08);
                padding-bottom: 10px;
            }
            .entry:last-child {
                border-bottom: none;
                margin-bottom: 0;
                padding-bottom: 0;
            }
            .title-row {
                margin-bottom: 4px;
            }
            .expression {
                font-size: 19px;
                font-weight: bold;
                color: #38bdf8;
            }
            .reading {
                font-size: 14px;
                color: #94a3b8;
                margin-left: 6px;
            }
            .badge {
                display: inline-block;
                background-color: rgba(56, 189, 248, 0.12);
                color: #38bdf8;
                border: 1px solid rgba(56, 189, 248, 0.25);
                border-radius: 4px;
                padding: 1px 5px;
                font-size: 9px;
                margin-left: 4px;
            }
            .tag-dict {
                background-color: rgba(168, 85, 247, 0.12);
                color: #c084fc;
                border: 1px solid rgba(168, 85, 247, 0.25);
            }
            .tag-deinflect {
                background-color: rgba(234, 179, 8, 0.12);
                color: #fde047;
                border: 1px solid rgba(234, 179, 8, 0.25);
            }
            .meta-row {
                margin-bottom: 6px;
                font-size: 11px;
                color: #cbd5e1;
            }
            .meta-item {
                margin-right: 8px;
            }
            .pitch-badge {
                color: #f472b6;
                background-color: rgba(244, 114, 182, 0.12);
                border: 1px solid rgba(244, 114, 182, 0.25);
                border-radius: 4px;
                padding: 1px 4px;
            }
            .freq-badge {
                color: #34d399;
                background-color: rgba(52, 211, 153, 0.12);
                border: 1px solid rgba(52, 211, 153, 0.25);
                border-radius: 4px;
                padding: 1px 4px;
            }
            .glossary-list {
                margin-top: 4px;
                padding-left: 16px;
                margin-bottom: 4px;
            }
            .glossary-item {
                margin-bottom: 3px;
                color: #e2e8f0;
            }
        </style>
        </head>
        <body>
        """)

        for entry in entries:
            html_parts.append("<div class='entry'>")
            
            # Title Row (Expression & Reading)
            html_parts.append("<div class='title-row'>")
            html_parts.append(f"<span class='expression'>{entry.expression}</span>")
            if entry.reading and entry.reading != entry.expression:
                html_parts.append(f"<span class='reading'>({entry.reading})</span>")
                
            # Badges (Definition Tags)
            for tag in entry.definition_tags[:4]:
                html_parts.append(f"<span class='badge'>{tag}</span>")
            
            # Dictionary tag
            html_parts.append(f"<span class='badge tag-dict'>{entry.dictionary_title}</span>")
            
            # Deinflection steps
            if entry.reasons:
                reasons_str = " &rarr; ".join(entry.reasons)
                html_parts.append(f"<span class='badge tag-deinflect'>{reasons_str}</span>")
                
            html_parts.append("</div>")

            # Meta Row (Pitch & Frequency)
            if entry.pitches or entry.frequencies:
                html_parts.append("<div class='meta-row'>")
                for pitch in entry.pitches:
                    html_parts.append(f"<span class='meta-item pitch-badge'>{pitch}</span>")
                for freq in entry.frequencies:
                    html_parts.append(f"<span class='meta-item freq-badge'>{freq}</span>")
                html_parts.append("</div>")

            # Glossary list
            html_parts.append("<ol class='glossary-list'>")
            for item in entry.glossary:
                html_parts.append(f"<li class='glossary-item'>{item}</li>")
            html_parts.append("</ol>")

            html_parts.append("</div>")

        html_parts.append("</body></html>")
        self.browser.setHtml("\n".join(html_parts))

    def show_at(self, pos: QPoint) -> None:
        """Positions the popup near the cursor, ensuring it stays on the screen bounds."""
        screen = QApplication.primaryScreen().geometry()
        
        # Determine best location: default to below and to the right of cursor
        x = pos.x() + 15
        y = pos.y() + 15

        # Constrain width and height boundaries
        if x + self.width() > screen.right():
            x = pos.x() - self.width() - 15
        if y + self.height() > screen.bottom():
            y = pos.y() - self.height() - 15

        # Lower bound protection
        if x < screen.left():
            x = screen.left() + 5
        if y < screen.top():
            y = screen.top() + 5

        self.move(x, y)
        self.show()

    def hide_popup(self) -> None:
        """Hide the popup window."""
        self.hide()
