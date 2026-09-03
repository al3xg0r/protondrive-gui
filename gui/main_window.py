"""Main window for the (unofficial) Proton Drive GUI."""

from __future__ import annotations

from pathlib import Path, PurePosixPath

from PySide6.QtCore import Qt, QThreadPool
from PySide6.QtGui import QAction, QIcon, QPalette
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenu,
    QMessageBox,
    QProgressDialog,
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
TRASH_ROOT = "/trash"


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        from . import __version__

        self.setWindowTitle(f"Proton Drive GUI (unofficial) \u2014 v{__version__}")
        self.resize(1080, 640)
        self.setAcceptDrops(True)
        # A floor narrow enough to still be a usable window, but wide
        # enough that even icon-only toolbar mode (see resizeEvent) never
        # has to hide a button — verified empirically: below this, Qt's
        # toolbar just makes overflowing buttons invisible with no "»"
        # overflow indicator at all, which is worse than a fixed limit.
        self.setMinimumWidth(480)

        self.thread_pool = QThreadPool()
        # PySide6 gotcha: a QRunnable handed to QThreadPool.start() can be
        # garbage-collected by Python before the pool is done with it if
        # nothing else holds a reference (the local `worker` variable in
        # the calling method goes out of scope immediately). When the pool
        # thread then tries to call back into a half-collected Python
        # object, it segfaults rather than raising a catchable exception —
        # this was very likely the cause of the crash/hang seen after
        # login. Every in-flight worker is kept here until it reports
        # finished/error, guaranteeing it stays alive for the whole call.
        self._active_workers: list[Worker] = []

        self.cli: ProtonDriveCLI | None = None
        self.current_root = MY_FILES_ROOT
        self.current_path = MY_FILES_ROOT
        self.items: list[DriveItem] = []
        self.is_logged_in = False

        self._build_ui()
        self._init_cli()

    # -- worker helper -------------------------------------------------------

    def _start_worker(self, fn, *args, on_finished=None, on_error=None, **kwargs):
        """Run fn(*args, **kwargs) on a background thread and keep a
        reference to the worker alive until it's done (see note in
        __init__ about why that's required)."""
        worker = Worker(fn, *args, **kwargs)
        self._active_workers.append(worker)

        def _cleanup():
            try:
                self._active_workers.remove(worker)
            except ValueError:
                pass

        def _handle_finished(result):
            _cleanup()
            if on_finished:
                on_finished(result)

        def _handle_error(message):
            _cleanup()
            (on_error or self._on_error)(message)

        worker.signals.finished.connect(_handle_finished)
        worker.signals.error.connect(_handle_error)
        self.thread_pool.start(worker)
        return worker

    def _start_streaming_worker(self, fn, *args, on_progress, on_finished=None, on_error=None):
        """Like _start_worker, but for the *_with_progress() CLI calls:
        wires the worker's thread-safe `progress` signal through as the
        function's `on_progress` callback, so progress updates emitted
        from the background thread land safely back on the GUI thread."""
        worker = Worker(fn, *args)
        self._active_workers.append(worker)

        def _cleanup():
            try:
                self._active_workers.remove(worker)
            except ValueError:
                pass

        def _handle_finished(result):
            _cleanup()
            if on_finished:
                on_finished(result)

        def _handle_error(message):
            _cleanup()
            (on_error or self._on_error)(message)

        worker.signals.finished.connect(_handle_finished)
        worker.signals.error.connect(_handle_error)
        worker.signals.progress.connect(on_progress)
        # Injected now (not at Worker(...) construction) so the callback
        # can safely close over worker.signals, which only exists once
        # the Worker object itself has been created.
        worker.kwargs["on_progress"] = worker.signals.progress.emit
        self.thread_pool.start(worker)
        return worker

    # -- icons ------------------------------------------------------------

    def _icon(self, name: str, size: int = 20) -> QIcon:
        color = self.palette().color(QPalette.WindowText)
        return make_icon(DRAWERS[name], color, size)

    # -- setup ---------------------------------------------------------------

    def _build_ui(self):
        toolbar = QToolBar("Main")
        toolbar.setMovable(False)
        toolbar.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.addToolBar(toolbar)
        self._toolbar = toolbar

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

        self.trash_action = QAction(self._icon("delete"), "Trash", self)
        self.trash_action.triggered.connect(lambda: self.switch_root(TRASH_ROOT))
        toolbar.addAction(self.trash_action)

        toolbar.addSeparator()

        self.new_folder_action = QAction(self._icon("new_folder"), "New folder", self)
        self.new_folder_action.triggered.connect(self.create_folder)
        toolbar.addAction(self.new_folder_action)

        self.empty_trash_action = QAction(self._icon("delete"), "Empty Trash", self)
        self.empty_trash_action.triggered.connect(self.empty_trash)
        toolbar.addAction(self.empty_trash_action)

        toolbar.addSeparator()

        self.upload_action = QAction(self._icon("upload"), "Upload", self)
        self.upload_action.triggered.connect(self.upload_files)
        toolbar.addAction(self.upload_action)

        self.download_action = QAction(self._icon("download"), "Download", self)
        self.download_action.triggered.connect(self.download_selected)
        toolbar.addAction(self.download_action)

        toolbar.addSeparator()

        self._login_icon = self._icon("login")
        self._logout_icon = self._icon("logout")
        self.login_action = QAction(self._login_icon, "Log in", self)
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
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._show_context_menu)
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
        self.new_folder_action.setEnabled(root == MY_FILES_ROOT)
        self.upload_action.setEnabled(root != TRASH_ROOT)
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

    def _show_context_menu(self, pos):
        if self.current_root == PHOTOS_ROOT:
            return  # rename/delete/restore are unconfirmed for Photos — skip rather than guess
        index = self.table.indexAt(pos)
        if not index.isValid():
            return
        row = index.row()
        if row not in {i.row() for i in self.table.selectedIndexes()}:
            self.table.selectRow(row)

        menu = QMenu(self)

        if self.current_root == TRASH_ROOT:
            restore_action = menu.addAction(self._icon("refresh", size=16), "Restore")
            chosen = menu.exec(self.table.viewport().mapToGlobal(pos))
            if chosen == restore_action:
                self._restore_selected()
            return

        rename_action = menu.addAction(self._icon("rename", size=16), "Rename\u2026")
        delete_action = menu.addAction(self._icon("delete", size=16), "Move to Trash\u2026")
        chosen = menu.exec(self.table.viewport().mapToGlobal(pos))
        if chosen == rename_action:
            self._rename_item(row)
        elif chosen == delete_action:
            self._delete_selected()

    def _rename_item(self, row: int):
        item = self.items[row]
        new_name, ok = QInputDialog.getText(self, "Rename", "New name:", text=item.name)
        new_name = new_name.strip()
        if not ok or not new_name or new_name == item.name:
            return
        full_path = f"{self.current_path.rstrip('/')}/{item.name}"
        self.statusBar().showMessage(f"Renaming to {new_name} \u2026")
        self._start_worker(
            self.cli.rename, full_path, new_name, on_finished=lambda _: self.refresh()
        )

    def _delete_selected(self):
        rows = sorted({idx.row() for idx in self.table.selectedIndexes()})
        if not rows:
            return
        names = [self.items[r].name for r in rows]
        listing = "\n".join(f"\u2022 {n}" for n in names)
        confirm = QMessageBox.question(
            self,
            "Move to Trash",
            f"Move to Trash:\n{listing}\n\nThis can be undone from Proton Drive's Trash.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if confirm != QMessageBox.Yes:
            return
        paths = [f"{self.current_path.rstrip('/')}/{self.items[r].name}" for r in rows]
        self.statusBar().showMessage(f"Moving {len(paths)} item(s) to Trash \u2026")
        self._start_worker(self.cli.trash, paths, on_finished=lambda _: self.refresh())

    def _restore_selected(self):
        rows = sorted({idx.row() for idx in self.table.selectedIndexes()})
        if not rows:
            return
        paths = [f"{self.current_path.rstrip('/')}/{self.items[r].name}" for r in rows]
        self.statusBar().showMessage(f"Restoring {len(paths)} item(s) \u2026")
        self._start_worker(self.cli.restore, paths, on_finished=lambda _: self.refresh())

    def empty_trash(self):
        if not self.cli:
            return
        confirm = QMessageBox.question(
            self,
            "Empty Trash",
            "Permanently delete everything in Trash?\n\nThis cannot be undone.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if confirm != QMessageBox.Yes:
            return
        self.statusBar().showMessage("Emptying Trash \u2026")
        self._start_worker(self.cli.empty_trash, on_finished=lambda _: self.refresh())

    def create_folder(self):
        if not self.cli:
            return
        if self.current_root != MY_FILES_ROOT:
            QMessageBox.information(
                self, "Not available", "Creating folders is only supported in My files."
            )
            return
        name, ok = QInputDialog.getText(self, "New folder", "Folder name:")
        name = name.strip()
        if not ok or not name:
            return
        self.statusBar().showMessage(f"Creating folder \u201c{name}\u201d \u2026")
        self._start_worker(
            self.cli.create_folder, self.current_path, name, on_finished=lambda _: self.refresh()
        )

    # -- data loading --------------------------------------------------------

    def refresh(self):
        if not self.cli:
            return
        self.statusBar().showMessage(f"Loading {self.current_path} \u2026")
        if self.current_root == PHOTOS_ROOT:
            self._start_worker(self.cli.list_photos, on_finished=self._on_list_loaded)
        else:
            self._start_worker(
                self.cli.list_dir, self.current_path, on_finished=self._on_list_loaded
            )

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
        self._start_worker(
            self.cli.is_authenticated,
            on_finished=lambda ok: self._on_auth_checked(ok, then_refresh),
            on_error=lambda _: self._on_auth_checked(False, then_refresh),
        )

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
        self.login_action.setText("Log out" if logged_in else "Log in")
        self.login_action.setIcon(self._logout_icon if logged_in else self._login_icon)

    def toggle_auth(self):
        self.login_action.setEnabled(False)
        self.logout() if self.is_logged_in else self.login()

    def login(self):
        if not self.cli:
            return
        self.statusBar().showMessage("Opening browser for login \u2026")

        def _done(_):
            self.login_action.setEnabled(True)
            self._refresh_auth_state(then_refresh=True)

        def _err(message):
            self.login_action.setEnabled(True)
            self._on_error(message)

        self._start_worker(self.cli.auth_login, on_finished=_done, on_error=_err)

    def logout(self):
        if not self.cli:
            return
        self.statusBar().showMessage("Logging out \u2026")

        def _done(_):
            self.login_action.setEnabled(True)
            self._on_auth_checked(False, False)

        def _err(message):
            self.login_action.setEnabled(True)
            self._on_error(message)

        self._start_worker(self.cli.auth_logout, on_finished=_done, on_error=_err)

    # -- about ------------------------------------------------------------------

    def show_about(self):
        from . import __version__

        box = QMessageBox(self)
        box.setWindowTitle("About Proton Drive GUI")
        box.setTextFormat(Qt.RichText)
        box.setText(
            f"<b>Proton Drive GUI</b> v{__version__} (unofficial)<br><br>"
            "A free, open-source desktop client for the official Proton Drive CLI.<br><br>"
            '<a href="https://github.com/al3xg0r/protondrive-gui">Project on GitHub</a>'
        )
        label = box.findChild(QLabel, "qt_msgbox_label")
        if label is not None:
            label.setTextInteractionFlags(Qt.TextBrowserInteraction)
            label.setOpenExternalLinks(True)
        box.exec()

    # -- upload / download -------------------------------------------------------

    def _make_progress_dialog(self, title: str) -> QProgressDialog:
        dialog = QProgressDialog(title, None, 0, 100, self)  # no Cancel button (not wired up yet)
        dialog.setWindowModality(Qt.WindowModal)
        dialog.setMinimumDuration(0)
        dialog.setAutoClose(False)
        dialog.setAutoReset(False)
        dialog.setValue(0)
        return dialog

    def _on_transfer_progress(self, dialog: QProgressDialog, percent: float, name: str, size: str):
        dialog.setLabelText(f"{name} ({size})")
        dialog.setValue(int(percent))

    def upload_files(self):
        if not self.cli:
            return
        paths, _ = QFileDialog.getOpenFileNames(self, "Select files to upload")
        if not paths:
            return
        self._upload_paths(paths)

    def _upload_paths(self, paths: list[str]):
        if not self.cli:
            return
        dialog = self._make_progress_dialog(f"Uploading {len(paths)} file(s)\u2026")

        def _done(_):
            dialog.close()
            self.refresh()

        def _err(message):
            dialog.close()
            self._on_error(message)

        if self.current_root == PHOTOS_ROOT:
            self._start_streaming_worker(
                self.cli.photo_upload_with_progress,
                paths,
                on_progress=lambda p, n, s: self._on_transfer_progress(dialog, p, n, s),
                on_finished=_done,
                on_error=_err,
            )
        else:
            self._start_streaming_worker(
                self.cli.upload_with_progress,
                paths,
                self.current_path,
                on_progress=lambda p, n, s: self._on_transfer_progress(dialog, p, n, s),
                on_finished=_done,
                on_error=_err,
            )

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

        dialog = self._make_progress_dialog(f"Downloading {len(rows)} file(s)\u2026")

        def _done(_):
            dialog.close()
            self.statusBar().showMessage("Download complete", 3000)

        def _err(message):
            dialog.close()
            self._on_error(message)

        if self.current_root == PHOTOS_ROOT:
            node_uids = [
                self.items[row].raw.get("nodeUid")
                for row in rows
                if self.items[row].raw.get("nodeUid")
            ]
            if not node_uids:
                return
            self._start_streaming_worker(
                self.cli.photo_download_with_progress,
                node_uids,
                target_dir,
                on_progress=lambda p, n, s: self._on_transfer_progress(dialog, p, n, s),
                on_finished=_done,
                on_error=_err,
            )
            return

        remote_paths = [
            f"{self.current_path.rstrip('/')}/{self.items[row].name}" for row in rows
        ]
        self._start_streaming_worker(
            self.cli.download_with_progress,
            remote_paths,
            target_dir,
            on_progress=lambda p, n, s: self._on_transfer_progress(dialog, p, n, s),
            on_finished=_done,
            on_error=_err,
        )

    # -- drag & drop upload -------------------------------------------------------

    # -- responsive toolbar -------------------------------------------------------

    _TOOLBAR_TEXT_THRESHOLD = 1060  # below this window width, drop text labels
    # rather than risk Qt's overflow handling — verified it can hide toolbar
    # buttons entirely with no visible "more" indicator when they don't fit.

    def resizeEvent(self, event):
        super().resizeEvent(event)
        style = (
            Qt.ToolButtonIconOnly
            if self.width() < self._TOOLBAR_TEXT_THRESHOLD
            else Qt.ToolButtonTextBesideIcon
        )
        if self._toolbar.toolButtonStyle() != style:
            self._toolbar.setToolButtonStyle(style)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            self.table.setStyleSheet("QTableWidget { border: 2px dashed palette(highlight); }")

    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dragLeaveEvent(self, event):
        self.table.setStyleSheet("")

    def dropEvent(self, event):
        self.table.setStyleSheet("")
        if not self.cli:
            event.ignore()
            return

        local_paths = [
            url.toLocalFile() for url in event.mimeData().urls() if url.isLocalFile()
        ]
        files = [p for p in local_paths if Path(p).is_file()]
        dirs = [p for p in local_paths if Path(p).is_dir()]
        event.acceptProposedAction()

        if not files:
            if dirs:
                QMessageBox.information(
                    self,
                    "Folders not supported",
                    "Drag & drop currently only supports individual files, not whole "
                    "folders. Drop the files themselves, or use the Upload button.",
                )
            return

        self._upload_paths(files)
