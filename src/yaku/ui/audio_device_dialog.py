from __future__ import annotations
from typing import Optional, TYPE_CHECKING
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QTableWidget,
    QTableWidgetItem,
    QPushButton,
    QLabel,
    QHeaderView,
    QMessageBox,
    QWidget,
)

if TYPE_CHECKING:
    from yaku.audio.capture import AudioDeviceInfo


class AudioDeviceDialog(QDialog):
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent, Qt.WindowType.Dialog)
        self.setWindowTitle("Choose Audio Device")
        self.resize(650, 400)
        self.selected_device: Optional[AudioDeviceInfo] = None
        self.use_auto = False

        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(16, 16, 16, 16)

        # Info Label
        info = QLabel(
            "Default audio device selected automatically.\n"
            "For game/system audio translation, choose a loopback/system audio device if available.\n"
            "For microphone translation, choose your microphone."
        )
        info.setWordWrap(True)
        info.setStyleSheet("color: #94a3b8; font-size: 11px; margin-bottom: 8px;")
        layout.addWidget(info)

        # Table Widget
        self.table = QTableWidget()
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels(["ID", "Name", "Type", "Host API", "Channels", "Default"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        layout.addWidget(self.table)

        # Refresh button layout
        btn_layout = QHBoxLayout()
        self.btn_refresh = QPushButton("Refresh Devices")
        self.btn_refresh.clicked.connect(self.refresh_devices)
        btn_layout.addWidget(self.btn_refresh)
        btn_layout.addStretch()
        layout.addLayout(btn_layout)

        # Bottom Buttons
        bottom_layout = QHBoxLayout()
        
        self.btn_auto = QPushButton("Use Auto Default")
        self.btn_auto.clicked.connect(self.accept_auto)
        bottom_layout.addWidget(self.btn_auto)
        
        bottom_layout.addStretch()
        
        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.clicked.connect(self.reject)
        bottom_layout.addWidget(self.btn_cancel)

        self.btn_select = QPushButton("Use Selected Device")
        self.btn_select.setObjectName("btn_primary")
        self.btn_select.clicked.connect(self.accept_selected)
        bottom_layout.addWidget(self.btn_select)

        layout.addLayout(bottom_layout)

        # Load devices
        self.devices: list[AudioDeviceInfo] = []
        self.refresh_devices()

    def refresh_devices(self) -> None:
        from yaku.audio.capture import list_audio_devices
        self.devices = list_audio_devices()
        self.table.setRowCount(0)
        
        for row, dev in enumerate(self.devices):
            self.table.insertRow(row)
            self.table.setItem(row, 0, QTableWidgetItem(dev.id))
            self.table.setItem(row, 1, QTableWidgetItem(dev.name))
            
            dev_type = "Loopback" if dev.is_loopback else "Microphone"
            self.table.setItem(row, 2, QTableWidgetItem(dev_type))
            self.table.setItem(row, 3, QTableWidgetItem(dev.hostapi or "Unknown"))
            self.table.setItem(row, 4, QTableWidgetItem(str(dev.max_input_channels)))
            self.table.setItem(row, 5, QTableWidgetItem("Yes" if dev.is_default else "No"))

    def accept_selected(self) -> None:
        selected_ranges = self.table.selectedRanges()
        if not selected_ranges:
            QMessageBox.warning(self, "Selection Required", "Please select a device from the list.")
            return
        row = selected_ranges[0].topRow()
        if 0 <= row < len(self.devices):
            self.selected_device = self.devices[row]
            self.use_auto = False
            self.accept()

    def accept_auto(self) -> None:
        self.selected_device = None
        self.use_auto = True
        self.accept()
