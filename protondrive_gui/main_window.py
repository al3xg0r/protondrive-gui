"""Main window for the (unofficial) Proton Drive GUI."""

from __future__ import annotations

from pathlib import PurePosixPath

from PySide6.QtCore import QThreadPool
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QStatusBar,
    QTableWidget,
    QTableWidgetItem,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from .cli import DriveItem, ProtonDriveCLI, ProtonDriveNotFoundError
from .workers import Worker


def human_size(n) -> str:
    if n is None:
        return ""
    try:
        n = float(n)
    except (TypeError, ValueError):
        return str(n)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024:
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} PB"


# The CLI's root listing ("/") only shows Proton's virtual top-level
# sections (my-files, devices, photos, shared-by-me, shared-with-me,
# trash, albums, ...) rather than actual files, and not all of them
# necessarily behave like a normal browsable folder. For a "what's
# actually on my disk" experience we skip that level and treat
# "/my-files" as home. (Browsing the other sections — trash, shared,
# photos — is a good candidate for a sidebar in a future version.)
HOME_PATH = "/my-files"


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Proton Drive GUI (unofficial)")
        self.resize(920, 600)

        self.thread_pool = QThreadPool()
        self.cli: ProtonDriveCLI | None = None
        self.current_path = HOME_PATH
        self.items: list[DriveItem] = []

        self._build_ui()
        self._init_cli()

    # -- setup ---------------------------------------------------------------

    def _build_ui(self):
        toolbar = QToolBar("Main")
        toolbar.setMovable(False)
        self.addToolBar(toolbar)

        self.up_action = QAction("\u2b06 Up", self)
        self.up_action.triggered.connect(self.go_up)
        toolbar.addAction(self.up_action)

        self.home_action = QAction("\U0001f3e0 Home", self)
        self.home_action.triggered.connect(lambda: self.navigate_to(HOME_PATH))
        toolbar.addAction(self.home_action)

        self.refresh_action = QAction("\u27f3 Refresh", self)
        self.refresh_action.triggered.connect(self.refresh)
        toolbar.addAction(self.refresh_action)

        toolbar.addSeparator()

        self.upload_action = QAction("\u2b06 Upload files\u2026", self)
        self.upload_action.triggered.connect(self.upload_files)
        toolbar.addAction(self.upload_action)

        self.download_action = QAction("\u2b07 Download selected", self)
        self.download_action.triggered.connect(self.download_selected)
        toolbar.addAction(self.download_action)

        toolbar.addSeparator()

        self.login_action = QAction("Log in\u2026", self)
        self.login_action.triggered.connect(self.login)
        toolbar.addAction(self.login_action)

        central = QWidget()
        layout = QVBoxLayout(central)

        path_row = QHBoxLayout()
        path_row.addWidget(QLabel("Path:"))
        self.path_edit = QLineEdit(self._display_path(self.current_path))
        self.path_edit.returnPressed.connect(self._path_edited)
        path_row.addWidget(self.path_edit)
        layout.addLayout(path_row)

        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["Name", "Size", "Modified"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.cellDoubleClicked.connect(self._row_double_clicked)
        layout.addWidget(self.table)

        self.setCentralWidget(central)
        self.setStatusBar(QStatusBar())

    def _init_cli(self):
        try:
            self.cli = ProtonDriveCLI()
        except ProtonDriveNotFoundError as e:
            QMessageBox.critical(self, "proton-drive not found", str(e))
            self.statusBar().showMessage("proton-drive CLI not found", 5000)
            return
        self.refresh()

    # -- navigation ------------------------------------------------------------

    @staticmethod
    def _display_path(actual_path: str) -> str:
        """Show paths rooted at "/" in the UI even though the CLI's real
        root for user files is "/my-files" — users shouldn't have to know
        or type that prefix."""
        if actual_path == HOME_PATH:
            return "/"
        if actual_path.startswith(HOME_PATH + "/"):
            return actual_path[len(HOME_PATH):]
        return actual_path

    @staticmethod
    def _actual_path(display_path: str) -> str:
        display_path = display_path.strip() or "/"
        if not display_path.startswith("/"):
            display_path = f"/{display_path}"
        if display_path == "/":
            return HOME_PATH
        return HOME_PATH + display_path

    def _path_edited(self):
        self.navigate_to(self._actual_path(self.path_edit.text()))

    def navigate_to(self, path: str):
        self.current_path = path if path.startswith("/") else f"/{path}"
        self.path_edit.setText(self._display_path(self.current_path))
        self.refresh()

    def go_up(self):
        if self.current_path in ("/", "", HOME_PATH):
            return
        parent = str(PurePosixPath(self.current_path).parent)
        # Never let "Up" escape above home into the raw virtual-section
        # root ("/my-files", "/devices", ...) — clamp there instead.
        if not (parent + "/").startswith(HOME_PATH + "/") and parent != HOME_PATH:
            parent = HOME_PATH
        self.navigate_to(parent)

    def _row_double_clicked(self, row: int, _col: int):
        item = self.items[row]
        if item.is_folder:
            new_path = f"{self.current_path.rstrip('/')}/{item.name}"
            self.navigate_to(new_path)

    # -- data loading --------------------------------------------------------

    def refresh(self):
        if not self.cli:
            return
        self.statusBar().showMessage(f"Loading {self.current_path} \u2026")
        worker = Worker(self.cli.list_dir, self.current_path)
        worker.signals.finished.connect(self._on_list_loaded)
        worker.signals.error.connect(self._on_error)
        self.thread_pool.start(worker)

    def _on_list_loaded(self, items: list[DriveItem]):
        self.items = sorted(items, key=lambda i: (not i.is_folder, i.name.lower()))
        self.table.setRowCount(len(self.items))
        for row, item in enumerate(self.items):
            prefix = "\U0001f4c1 " if item.is_folder else "\U0001f4c4 "
            self.table.setItem(row, 0, QTableWidgetItem(prefix + item.name))
            size_text = "" if item.is_folder else human_size(item.size)
            self.table.setItem(row, 1, QTableWidgetItem(size_text))
            self.table.setItem(row, 2, QTableWidgetItem(item.modified or ""))
        self.statusBar().showMessage(f"{len(self.items)} item(s)", 3000)

    def _on_error(self, message: str):
        self.statusBar().showMessage("Error", 3000)
        QMessageBox.warning(self, "Proton Drive error", message)

    # -- auth ------------------------------------------------------------------

    def login(self):
        if not self.cli:
            return
        self.statusBar().showMessage("Opening browser for login \u2026")
        worker = Worker(self.cli.auth_login)
        worker.signals.finished.connect(lambda _: self.refresh())
        worker.signals.error.connect(self._on_error)
        self.thread_pool.start(worker)

    # -- upload / download -------------------------------------------------------

    def upload_files(self):
        if not self.cli:
            return
        paths, _ = QFileDialog.getOpenFileNames(self, "Select files to upload")
        if not paths:
            return
        self.statusBar().showMessage(f"Uploading {len(paths)} file(s) \u2026")
        worker = Worker(self.cli.upload, paths, self.current_path)
        worker.signals.finished.connect(lambda _: self.refresh())
        worker.signals.error.connect(self._on_error)
        self.thread_pool.start(worker)

    def download_selected(self):
        if not self.cli:
            return
        rows = sorted({idx.row() for idx in self.table.selectedIndexes()})
        if not rows:
            QMessageBox.information(self, "Nothing selected", "Select one or more items first.")
            return
        target_dir = QFileDialog.getExistingDirectory(self, "Download to\u2026")
        if not target_dir:
            return
        for row in rows:
            item = self.items[row]
            remote_path = f"{self.current_path.rstrip('/')}/{item.name}"
            worker = Worker(self.cli.download, remote_path, target_dir)
            worker.signals.finished.connect(
                lambda _: self.statusBar().showMessage("Download complete", 3000)
            )
            worker.signals.error.connect(self._on_error)
            self.thread_pool.start(worker)
