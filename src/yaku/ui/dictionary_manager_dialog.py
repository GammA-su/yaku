from __future__ import annotations

import os
import sqlite3
from pathlib import Path
from typing import Optional

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QApplication,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from yaku.core.config import YakuConfig
from yaku.core.logging import get_logger
from yaku.v4_yomitan.dictionary_importer import import_dictionary_zip

_log = get_logger("dictionary_manager_dialog")


class DictionaryRowWidget(QWidget):
    """Row widget representing a single imported Yomitan dictionary in the manager."""

    def __init__(self, dict_id: int, title: str, imported_at: str, on_delete, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 6, 12, 6)
        layout.setSpacing(10)

        # Info container
        info_layout = QVBoxLayout()
        info_layout.setSpacing(2)

        self.title_lbl = QLabel(title)
        self.title_lbl.setStyleSheet("font-weight: bold; font-size: 13px; color: #ffffff;")
        
        # Parse date
        date_str = imported_at.split("T")[0] if "T" in imported_at else imported_at
        self.meta_lbl = QLabel(f"Imported: {date_str}")
        self.meta_lbl.setStyleSheet("font-size: 11px; color: #94a3b8;")

        info_layout.addWidget(self.title_lbl)
        info_layout.addWidget(self.meta_lbl)

        # Delete button
        self.delete_btn = QPushButton("Remove")
        self.delete_btn.setObjectName("btn_danger")
        self.delete_btn.setFixedWidth(80)
        self.delete_btn.clicked.connect(lambda: on_delete(dict_id, title))

        layout.addLayout(info_layout, 1)
        layout.addWidget(self.delete_btn)


class DictionaryManagerDialog(QDialog):
    """Visual panel to add, remove, and view native Yomitan dictionary indexes."""

    def __init__(self, config: YakuConfig, parent=None) -> None:
        super().__init__(parent)
        self.config = config
        self.db_path = Path(self.config.v4_yomitan.dictionaries.index_path)

        self.setWindowTitle("Yomitan Dictionary Manager")
        self.resize(580, 420)

        # Main Layout
        layout = QVBoxLayout(self)
        layout.setSpacing(16)
        layout.setContentsMargins(20, 20, 20, 20)

        # Header Title
        header_layout = QVBoxLayout()
        header_layout.setSpacing(4)
        self.title_lbl = QLabel("Imported Dictionaries")
        self.title_lbl.setStyleSheet("font-size: 20px; font-weight: bold; color: #ffffff;")
        self.subtitle_lbl = QLabel("Manage dictionaries for offline Yomitan term hover popups.")
        self.subtitle_lbl.setStyleSheet("color: #94a3b8; font-size: 12px;")
        header_layout.addWidget(self.title_lbl)
        header_layout.addWidget(self.subtitle_lbl)
        layout.addLayout(header_layout)

        # Stats section
        self.stats_lbl = QLabel("Total terms in database: ...")
        self.stats_lbl.setStyleSheet("color: #cbd5e1; font-size: 12px; font-weight: 600;")
        layout.addWidget(self.stats_lbl)

        # Scrollable List
        self.list_widget = QListWidget()
        self.list_widget.setStyleSheet(
            "background-color: #0f172a; border: 1px solid #334155; border-radius: 8px;"
        )
        self.list_widget.setSelectionMode(QListWidget.SelectionMode.NoSelection)
        layout.addWidget(self.list_widget)

        # Actions Row
        actions_layout = QHBoxLayout()
        actions_layout.setSpacing(10)

        self.btn_import = QPushButton("Import ZIP...")
        self.btn_import.setObjectName("btn_primary")
        self.btn_import.clicked.connect(self._on_import_clicked)

        self.btn_open_dir = QPushButton("Open Folder")
        self.btn_open_dir.clicked.connect(self._on_open_dir_clicked)

        self.btn_rebuild = QPushButton("Rebuild Index")
        self.btn_rebuild.clicked.connect(self._on_rebuild_clicked)

        self.btn_close = QPushButton("Close")
        self.btn_close.clicked.connect(self.accept)

        actions_layout.addWidget(self.btn_import)
        actions_layout.addWidget(self.btn_open_dir)
        actions_layout.addWidget(self.btn_rebuild)
        actions_layout.addStretch()
        actions_layout.addWidget(self.btn_close)
        layout.addLayout(actions_layout)

        self._refresh_list()

    def _get_connection(self) -> Optional[sqlite3.Connection]:
        """Establish temporary connection to query dict lists."""
        if not self.db_path.exists():
            return None
        try:
            conn = sqlite3.connect(str(self.db_path))
            conn.row_factory = sqlite3.Row
            return conn
        except Exception as exc:
            _log.error("Failed to connect to index db: %s", exc)
            return None

    def _refresh_list(self) -> None:
        """Fetch dictionaries and rebuild row views."""
        self.list_widget.clear()
        
        conn = self._get_connection()
        if not conn:
            self.stats_lbl.setText("No dictionary index found (Database is empty).")
            return

        try:
            # Query active dictionaries
            cursor = conn.cursor()
            cursor.execute("SELECT id, title, imported_at FROM dictionaries ORDER BY title;")
            rows = cursor.fetchall()
            
            # Query term count
            cursor.execute("SELECT COUNT(*) FROM terms;")
            total_terms = cursor.fetchone()[0]
            
            self.stats_lbl.setText(f"Total indexed terms: {total_terms:,}")

            for row in rows:
                item = QListWidgetItem()
                self.list_widget.addItem(item)

                widget = DictionaryRowWidget(
                    dict_id=row["id"],
                    title=row["title"],
                    imported_at=row["imported_at"],
                    on_delete=self._on_delete_dictionary
                )
                widget.adjustSize()
                item.setSizeHint(widget.sizeHint())
                self.list_widget.setItemWidget(item, widget)

        except Exception as exc:
            _log.error("Failed to query dictionary database: %s", exc)
            self.stats_lbl.setText("Error reading dictionary index database.")
        finally:
            conn.close()

    def _on_delete_dictionary(self, dict_id: int, title: str) -> None:
        """Delete dictionary row and cascade clean associated terms."""
        reply = QMessageBox.question(
            self,
            "Remove Dictionary",
            f"Are you sure you want to remove '{title}'?\nThis will delete all its terms and definitions.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        conn = self._get_connection()
        if not conn:
            return

        try:
            conn.execute("PRAGMA foreign_keys = ON;")
            with conn:
                conn.execute("DELETE FROM dictionaries WHERE id = ?;", (dict_id,))
            QMessageBox.information(self, "Removed", f"Successfully removed '{title}'.")
        except Exception as exc:
            _log.error("Failed to delete dictionary: %s", exc)
            QMessageBox.critical(self, "Error", f"Could not remove dictionary: {exc}")
        finally:
            conn.close()
            self._refresh_list()

    def _on_import_clicked(self) -> None:
        """Browse and import a Yomitan dictionary zip archive."""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Select Yomitan Dictionary ZIP", "", "Yomitan ZIP Archives (*.zip)"
        )
        if not file_path:
            return

        zip_path = Path(file_path)
        self.btn_import.setEnabled(False)
        self.btn_import.setText("Importing...")
        QApplication.processEvents()

        try:
            res = import_dictionary_zip(zip_path, self.db_path, force=True)
            if res.ok:
                QMessageBox.information(
                    self,
                    "Import Complete",
                    f"Successfully imported '{res.title}'!\n"
                    f"Terms: {res.terms_imported:,}\n"
                    f"Metadata: {res.meta_imported:,}\n"
                    f"Tags: {res.tags_imported:,}"
                )
            else:
                QMessageBox.critical(self, "Import Failed", f"Error: {res.error}")
        except Exception as exc:
            QMessageBox.critical(self, "Error", f"Unexpected import exception: {exc}")
        finally:
            self.btn_import.setEnabled(True)
            self.btn_import.setText("Import ZIP...")
            self._refresh_list()

    def _on_open_dir_clicked(self) -> None:
        """Open the dictionary zip directory in file explorer."""
        dict_dir = Path(self.config.v4_yomitan.dictionaries.dictionary_dir)
        dict_dir.mkdir(parents=True, exist_ok=True)
        os.startfile(str(dict_dir))

    def _on_rebuild_clicked(self) -> None:
        """Confirm, delete, and fully recreate index schema from scratch."""
        reply = QMessageBox.question(
            self,
            "Rebuild Database Index",
            "Are you sure you want to completely rebuild the database index?\nThis drops all tables and re-initializes schemas.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        if self.db_path.exists():
            try:
                self.db_path.unlink()
            except Exception as exc:
                QMessageBox.critical(self, "Error", f"Failed to delete index file: {exc}")
                return

        # Reconnect to initialize the schema
        from yaku.v4_yomitan.dictionary_index import DictionaryIndex
        try:
            db = DictionaryIndex(self.db_path)
            db.connect()
            db.close()
            QMessageBox.information(self, "Rebuild", "Successfully reinitialized database schemas.")
        except Exception as exc:
            QMessageBox.critical(self, "Error", f"Schema reinitialization failed: {exc}")

        self._refresh_list()
