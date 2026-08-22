"""Main window for the (unofficial) Proton Drive GUI."""

from __future__ import annotations

from pathlib import PurePosixPath

from PySide6.QtCore import Qt, QThreadPool
from PySide6.QtGui import QAction, QIcon, QPalette
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
from .icons import DRAWERS, make_icon
from .workers import Worker

REFERRAL_URL = "https://pr.tn/ref/H3Y6DHT7"


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
# trash, albums, ...) rather than actual files. For a "what's actually
# on my disk" experience we skip that raw listing and instead offer two
# named roots users actually care about — regular files, and the
# camera-upload "Photos" section (which lives outside "/my-files").
# Trash/shared/devices/albums are still reachable by typing a raw
# "/section/..." path, just not exposed as a dedicated button (yet).
MY_FILES_ROOT = "/my-files"
PHOTOS_ROOT = "/photos"


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Proton Drive GUI (unofficial)")
        self.resize(920, 600)

        self.thread_pool = QThreadPool()
        self.cli: ProtonDriveCLI | None = None
        self.current_root = MY_FILES_ROOT
        self.current_path = MY_FILES_ROOT
        self.items: list[DriveItem] = []
        self.is_logged_in = False

        self._build_ui()
        self._init_cli()

    # -- icons ------------------------------------------------------------

    def _icon(self, name: str, size: int = 20) -> QIcon:
        color = self.palette().color(QPalette.WindowText)
        return make_icon(DRAWERS[name], color, size)

    # -- setup ---------------------------------------------------------------

    def _build_ui(self):
        toolbar = QToolBar("Main")
        toolbar.setMovable(False)
        self.addToolBar(toolbar)

        self.back_action = QAction(self._icon("back"), "Back", self)
        self.back_action.triggered.connect(self.go_up)
        self.back_action.setEnabled(False)  # we start at the root
        toolbar.addAction(self.back_action)

        self.refresh_action = QAction(self._icon("refresh"), "Refresh", self)
        self.refresh_action.triggered.connect(self.refresh)
        toolbar.addAction(self.refresh_action)

        toolbar.addSeparator()

        self.my_files_action = QAction(self._icon("folder"), "My files", self)
        self.my_files_action.triggered.connect(lambda: self.switch_root(MY_FILES_ROOT))
        toolbar.addAction(self.my_files_action)

        self.photos_action = QAction(self._icon("photos"), "Photos", self)
        self.photos_action.triggered.connect(lambda: self.switch_root(PHOTOS_ROOT))
        toolbar.addAction(self.photos_action)

        toolbar.addSeparator()

        self.upload_action = QAction(self._icon("upload"), "Upload files\u2026", self)
        self.upload_action.triggered.connect(self.upload_files)
        toolbar.addAction(self.upload_action)

        self.download_action = QAction(self._icon("download"), "Download selected", self)
        self.download_action.triggered.connect(self.download_selected)
        toolbar.addAction(self.download_action)

        toolbar.addSeparator()

        self._login_icon = self._icon("login")
        self._logout_icon = self._icon("logout")
        self.login_action = QAction(self._login_icon, "Log in\u2026", self)
        self.login_action.triggered.connect(self.toggle_auth)
        toolbar.addAction(self.login_action)

        toolbar.addSeparator()

        self.about_action = QAction(self._icon("about"), "About", self)
        self.about_action.triggered.connect(self.show_about)
        toolbar.addAction(self.about_action)

        self._row_folder_icon = self._icon("folder", size=16)
        self._row_file_icon = self._icon("file", size=16)
        self._row_photo_icon = self._icon("photos", size=16)

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
        self._refresh_auth_state(then_refresh=True)

    # -- navigation ------------------------------------------------------------

    def _display_path(self, actual_path: str) -> str:
        """Show paths rooted at "/" in the UI even though the CLI's real
        root is e.g. "/my-files" or "/photos" — users shouldn't have to
        know or type that prefix."""
        root = self.current_root
        if actual_path == root:
            return "/"
        if actual_path.startswith(root + "/"):
            return actual_path[len(root):]
        return actual_path

    def _actual_path(self, display_path: str) -> str:
        display_path = display_path.strip() or "/"
        if not display_path.startswith("/"):
            display_path = f"/{display_path}"
        if display_path == "/":
            return self.current_root
        return self.current_root + display_path

    def switch_root(self, root: str):
        self.current_root = root
        self.path_edit.setEnabled(root != PHOTOS_ROOT)
        self.table.setColumnHidden(1, root == PHOTOS_ROOT)  # no file sizes in Photos
        self.navigate_to(root)

    def _path_edited(self):
        self.navigate_to(self._actual_path(self.path_edit.text()))

    def navigate_to(self, path: str):
        self.current_path = path if path.startswith("/") else f"/{path}"
        self.path_edit.setText(self._display_path(self.current_path))
        self.back_action.setEnabled(self.current_path != self.current_root)
        self.refresh()

    def go_up(self):
        if self.current_path in ("/", "", self.current_root):
            return
        parent = str(PurePosixPath(self.current_path).parent)
        # Never let "Back" escape above the current root ("/my-files" or
        # "/photos") into the raw virtual-section root ("/devices", ...).
        if not (parent + "/").startswith(self.current_root + "/") and parent != self.current_root:
            parent = self.current_root
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
        if self.current_root == PHOTOS_ROOT:
            worker = Worker(self.cli.list_photos)
        else:
            worker = Worker(self.cli.list_dir, self.current_path)
        worker.signals.finished.connect(self._on_list_loaded)
        worker.signals.error.connect(self._on_error)
        self.thread_pool.start(worker)

    def _on_list_loaded(self, items: list[DriveItem]):
        if self.current_root == PHOTOS_ROOT:
            # Flat, most-recent-first — there's no folder hierarchy here.
            self.items = sorted(items, key=lambda i: i.modified or "", reverse=True)
        else:
            self.items = sorted(items, key=lambda i: (not i.is_folder, i.name.lower()))
        self.table.setRowCount(len(self.items))
        for row, item in enumerate(self.items):
            if item.is_folder:
                icon = self._row_folder_icon
            elif self.current_root == PHOTOS_ROOT:
                icon = self._row_photo_icon
            else:
                icon = self._row_file_icon
            name_item = QTableWidgetItem(item.name)
            name_item.setIcon(icon)
            self.table.setItem(row, 0, name_item)
            size_text = "\u2014" if item.is_folder else human_size(item.size)
            size_item = QTableWidgetItem(size_text)
            if item.is_folder:
                size_item.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(row, 1, size_item)
            self.table.setItem(row, 2, QTableWidgetItem(item.modified or ""))
        self.statusBar().showMessage(f"{len(self.items)} file(s)", 3000)

    def _on_error(self, message: str):
        self.statusBar().showMessage("Error", 3000)
        QMessageBox.warning(self, "Proton Drive error", message)

    # -- auth ------------------------------------------------------------------

    def _refresh_auth_state(self, then_refresh: bool = False):
        """Proton Drive CLI has no `auth status`/`whoami` command, so this
        just probes with a cheap list call and reflects yes/no logged-in —
        there's currently no way to show an account name or storage quota
        through this CLI."""
        if not self.cli:
            return
        worker = Worker(self.cli.is_authenticated)
        worker.signals.finished.connect(lambda ok: self._on_auth_checked(ok, then_refresh))
        worker.signals.error.connect(lambda _: self._on_auth_checked(False, then_refresh))
        self.thread_pool.start(worker)

    def _on_auth_checked(self, logged_in: bool, then_refresh: bool):
        self._set_auth_ui(logged_in)
        if logged_in:
            if then_refresh:
                self.refresh()
        else:
            self.table.setRowCount(0)
            self.statusBar().showMessage('Not logged in — click "Log in…" to continue.', 6000)

    def _set_auth_ui(self, logged_in: bool):
        self.is_logged_in = logged_in
        self.login_action.setText("Log out" if logged_in else "Log in\u2026")
        self.login_action.setIcon(self._logout_icon if logged_in else self._login_icon)

    def toggle_auth(self):
        self.login_action.setEnabled(False)
        self.logout() if self.is_logged_in else self.login()

    def login(self):
        if not self.cli:
            return
        self.statusBar().showMessage("Opening browser for login \u2026")
        worker = Worker(self.cli.auth_login)
        worker.signals.finished.connect(
            lambda _: (
                self.login_action.setEnabled(True),
                self._refresh_auth_state(then_refresh=True),
            )
        )
        worker.signals.error.connect(self._on_auth_action_error)
        self.thread_pool.start(worker)

    def logout(self):
        if not self.cli:
            return
        self.statusBar().showMessage("Logging out \u2026")
        worker = Worker(self.cli.auth_logout)
        worker.signals.finished.connect(
            lambda _: (self.login_action.setEnabled(True), self._on_auth_checked(False, False))
        )
        worker.signals.error.connect(self._on_auth_action_error)
        self.thread_pool.start(worker)

    def _on_auth_action_error(self, message: str):
        self.login_action.setEnabled(True)
        self._on_error(message)

    # -- about / referral --------------------------------------------------------

    def show_about(self):
        box = QMessageBox(self)
        box.setWindowTitle("About Proton Drive GUI")
        box.setTextFormat(Qt.RichText)
        box.setText(
            "<b>Proton Drive GUI</b> (unofficial)<br><br>"
            "A free, open-source desktop client for the official Proton Drive CLI.<br><br>"
            "Don't have Proton Drive yet? "
            f'<a href="{REFERRAL_URL}">Sign up here</a> (referral link — '
            "costs you nothing extra, gives me a little credit).<br><br>"
            '<a href="https://github.com/al3xg0r/protondrive-gui">Project on GitHub</a>'
        )
        label = box.findChild(QLabel, "qt_msgbox_label")
        if label is not None:
            label.setTextInteractionFlags(Qt.TextBrowserInteraction)
            label.setOpenExternalLinks(True)
        box.exec()

    # -- upload / download -------------------------------------------------------

    def upload_files(self):
        if not self.cli:
            return
        paths, _ = QFileDialog.getOpenFileNames(self, "Select files to upload")
        if not paths:
            return
        self.statusBar().showMessage(f"Uploading {len(paths)} file(s) \u2026")
        if self.current_root == PHOTOS_ROOT:
            worker = Worker(self.cli.photo_upload, paths)
        else:
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

        if self.current_root == PHOTOS_ROOT:
            target_dir = QFileDialog.getExistingDirectory(self, "Download to\u2026")
            if not target_dir:
                return
            node_uids = [
                self.items[row].raw.get("nodeUid")
                for row in rows
                if self.items[row].raw.get("nodeUid")
            ]
            if not node_uids:
                return
            worker = Worker(self.cli.photo_download, node_uids, target_dir)
            worker.signals.finished.connect(
                lambda _: self.statusBar().showMessage("Download complete", 3000)
            )
            worker.signals.error.connect(self._on_error)
            self.thread_pool.start(worker)
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
