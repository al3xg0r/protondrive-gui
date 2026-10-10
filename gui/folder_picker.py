"""Folder picker used by Move to folder: browse My files, pick a destination."""

from __future__ import annotations

from pathlib import PurePosixPath

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QToolButton,
    QVBoxLayout,
)


class FolderPickerDialog(QDialog):
    """Lists only folders. `list_dir` and `run_async` come from the main
    window, so the CLI call runs on a worker thread and the result is
    delivered back on the GUI thread. `on_pick(target_path) -> bool` is
    called when the user confirms; returning False keeps the dialog open."""

    def __init__(self, parent, title, start_path, root, root_label, list_dir, run_async, on_pick):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(440, 380)
        self._root = root
        self._root_label = root_label
        self._list_dir = list_dir
        self._run_async = run_async
        self._on_pick = on_pick
        self._path = start_path
        self._closed = False

        layout = QVBoxLayout(self)
        top = QHBoxLayout()
        self._up = QToolButton()
        self._up.setText("\u2191 Up")
        self._up.setAutoRaise(True)
        self._up.clicked.connect(self._go_up)
        self._location = QLabel()
        top.addWidget(self._up)
        top.addWidget(self._location, 1)
        layout.addLayout(top)

        self._list = QListWidget()
        self._list.itemDoubleClicked.connect(self._enter)
        layout.addWidget(self._list, 1)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        self._move_here = QPushButton("Move here")
        self._move_here.setDefault(True)
        self._move_here.clicked.connect(self._choose)
        buttons.addWidget(cancel)
        buttons.addWidget(self._move_here)
        layout.addLayout(buttons)

        self._load(start_path)

    def done(self, result):
        # Worker callbacks may still arrive after the dialog closes; ignore them.
        self._closed = True
        super().done(result)

    def _display(self, path: str) -> str:
        rest = path[len(self._root):] if path.startswith(self._root) else path
        return self._root_label + rest

    def _load(self, path: str):
        self._path = path
        self._location.setText(self._display(path))
        self._up.setEnabled(path != self._root)
        self._move_here.setEnabled(False)
        self._list.clear()
        self._list.addItem("Loading\u2026")
        self._run_async(self._list_dir, path, on_finished=self._populate, on_error=self._fail)

    def _populate(self, items):
        if self._closed:
            return
        self._list.clear()
        folders = sorted((i for i in items if i.is_folder), key=lambda i: i.name.lower())
        if not folders:
            placeholder = QListWidgetItem("(no subfolders)")
            placeholder.setFlags(Qt.ItemIsEnabled)
            self._list.addItem(placeholder)
        for item in folders:
            self._list.addItem(QListWidgetItem(item.name))
        self._move_here.setEnabled(True)

    def _fail(self, message: str):
        if self._closed:
            return
        self._list.clear()
        self._list.addItem(f"Could not open this folder: {message.splitlines()[0]}")
        self._move_here.setEnabled(True)

    def _enter(self, item):
        if item.text().startswith("("):
            return
        self._load(f"{self._path.rstrip('/')}/{item.text()}")

    def _go_up(self):
        parent = str(PurePosixPath(self._path).parent)
        if not (parent + "/").startswith(self._root + "/") and parent != self._root:
            parent = self._root
        self._load(parent)

    def _choose(self):
        if self._on_pick(self._path):
            self.accept()
