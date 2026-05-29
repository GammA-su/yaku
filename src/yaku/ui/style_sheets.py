"""Global QSS Stylesheets and constants for Yaku."""
from __future__ import annotations

# Modern Slate/Indigo dark theme palette
THEME_PALETTE = {
    "bg_main": "#0b0f19",       # main window background
    "bg_card": "#1e293b",       # cards, panels, groupboxes
    "bg_input": "#0f172a",      # textboxes, dropdowns
    "border": "#334155",        # borders
    "border_focus": "#6366f1",  # focused border
    "text_main": "#f8fafc",     # primary text
    "text_muted": "#94a3b8",    # secondary text
    "primary": "#4f46e5",       # primary action button
    "primary_hover": "#6366f1", # primary action button hover
    "danger": "#e11d48",        # stop button
    "danger_hover": "#f43f5e",  # stop button hover
    "success": "#10b981",       # start / pass status
    "warning": "#f59e0b",       # warn status
    "info": "#06b6d4",          # info badge
}

GLOBAL_STYLE = f"""
/* Global Window/Dialog style */
QMainWindow, QDialog {{
    background-color: {THEME_PALETTE["bg_main"]};
    color: {THEME_PALETTE["text_main"]};
}}

QWidget {{
    color: {THEME_PALETTE["text_main"]};
    font-family: "Segoe UI", -apple-system, BlinkMacSystemFont, Roboto, Helvetica, Arial, sans-serif;
    font-size: 13px;
}}

/* Card layout / GroupBox styling */
QGroupBox {{
    background-color: {THEME_PALETTE["bg_card"]};
    border: 1px solid {THEME_PALETTE["border"]};
    border-radius: 8px;
    margin-top: 12px;
    padding: 16px;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 12px;
    padding: 0 4px;
    color: {THEME_PALETTE["text_muted"]};
    font-weight: bold;
    font-size: 11px;
    text-transform: uppercase;
}}

/* Labels */
QLabel {{
    background: transparent;
}}
QLabel#header_title {{
    font-size: 24px;
    font-weight: 800;
    color: #ffffff;
    letter-spacing: 1px;
}}
QLabel#header_subtitle {{
    font-size: 12px;
    color: {THEME_PALETTE["text_muted"]};
}}

/* Inputs (LineEdits, ComboBoxes, SpinBoxes, etc.) */
QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QTextEdit {{
    background-color: {THEME_PALETTE["bg_input"]};
    border: 1px solid {THEME_PALETTE["border"]};
    border-radius: 6px;
    padding: 6px 12px;
    color: {THEME_PALETTE["text_main"]};
    min-height: 28px;
}}

QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus, QTextEdit:focus {{
    border: 1px solid {THEME_PALETTE["border_focus"]};
}}

QTextEdit {{
    font-family: "Consolas", "Courier New", monospace;
    font-size: 12px;
}}

/* ComboBox dropdown modifications */
QComboBox::drop-down {{
    subcontrol-origin: padding;
    subcontrol-position: top right;
    width: 24px;
    border-left-width: 0px;
    border-top-right-radius: 6px;
    border-bottom-right-radius: 6px;
}}
QComboBox::down-arrow {{
    image: none; /* Can be overridden or left blank */
    border: solid {THEME_PALETTE["text_muted"]};
    border-width: 0 2px 2px 0;
    display: inline-block;
    padding: 3px;
    margin-right: 8px;
    /* Drawing custom arrow */
    width: 5px;
    height: 5px;
    transform: rotate(45deg);
}}
QComboBox QAbstractItemView {{
    background-color: {THEME_PALETTE["bg_input"]};
    border: 1px solid {THEME_PALETTE["border"]};
    selection-background-color: {THEME_PALETTE["primary"]};
    selection-color: #ffffff;
    color: {THEME_PALETTE["text_main"]};
    padding: 4px;
}}

/* Scroll bars styling */
QScrollBar:vertical {{
    border: none;
    background: {THEME_PALETTE["bg_main"]};
    width: 10px;
    margin: 0px;
    border-radius: 5px;
}}
QScrollBar::handle:vertical {{
    background: {THEME_PALETTE["border"]};
    min-height: 20px;
    border-radius: 5px;
}}
QScrollBar::handle:vertical:hover {{
    background: {THEME_PALETTE["text_muted"]};
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    background: none;
    height: 0px;
}}

QScrollBar:horizontal {{
    border: none;
    background: {THEME_PALETTE["bg_main"]};
    height: 10px;
    margin: 0px;
    border-radius: 5px;
}}
QScrollBar::handle:horizontal {{
    background: {THEME_PALETTE["border"]};
    min-width: 20px;
    border-radius: 5px;
}}
QScrollBar::handle:horizontal:hover {{
    background: {THEME_PALETTE["text_muted"]};
}}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
    background: none;
    width: 0px;
}}

/* Buttons */
QPushButton {{
    background-color: {THEME_PALETTE["border"]};
    border: 1px solid {THEME_PALETTE["border"]};
    border-radius: 6px;
    padding: 8px 16px;
    color: {THEME_PALETTE["text_main"]};
    font-weight: 600;
    min-height: 18px;
}}

QPushButton:hover {{
    background-color: #475569;
    border-color: #475569;
}}

QPushButton:pressed {{
    background-color: #1e293b;
}}

QPushButton:disabled {{
    background-color: #0f172a;
    border-color: #1e293b;
    color: #64748b;
}}

/* Styled Action Buttons */
QPushButton#btn_primary {{
    background-color: {THEME_PALETTE["primary"]};
    border: 1px solid {THEME_PALETTE["primary"]};
    color: #ffffff;
}}
QPushButton#btn_primary:hover {{
    background-color: {THEME_PALETTE["primary_hover"]};
    border-color: {THEME_PALETTE["primary_hover"]};
}}

QPushButton#btn_danger {{
    background-color: {THEME_PALETTE["danger"]};
    border: 1px solid {THEME_PALETTE["danger"]};
    color: #ffffff;
}}
QPushButton#btn_danger:hover {{
    background-color: {THEME_PALETTE["danger_hover"]};
    border-color: {THEME_PALETTE["danger_hover"]};
}}

/* Scroll Area background fix */
QScrollArea {{
    border: none;
    background-color: transparent;
}}
QScrollArea > QWidget > QWidget {{
    background-color: transparent;
}}

/* List widgets for pickers and dialogs */
QListWidget {{
    background-color: {THEME_PALETTE["bg_input"]};
    border: 1px solid {THEME_PALETTE["border"]};
    border-radius: 6px;
    padding: 4px;
    color: {THEME_PALETTE["text_main"]};
}}
QListWidget::item {{
    padding: 8px 12px;
    border-radius: 4px;
    margin-bottom: 2px;
}}
QListWidget::item:hover {{
    background-color: {THEME_PALETTE["bg_card"]};
}}
QListWidget::item:selected {{
    background-color: {THEME_PALETTE["primary"]};
    color: #ffffff;
}}
"""
