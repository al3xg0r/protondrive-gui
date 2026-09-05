"""Main window for the (unofficial) Proton Drive GUI."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path, PurePosixPath

from PySide6.QtCore import QEvent, QSize, Qt, QThreadPool
from PySide6.QtGui import QAction, QActionGroup, QIcon, QPalette
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMenu,
    QMessageBox,
    QProgressDialog,
    QSizePolicy,
    QStackedWidget,
    QStatusBar,
    QTableWidget,
    QTableWidgetItem,
    QToolBar,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from .cli import DriveItem, ProtonDriveCLI, ProtonDriveNotFoundError
from .icons import DRAWERS, make_icon
from .workers import Worker


def format_timestamp(iso: str) -> str:
    """The CLI reports timestamps as ISO 8601 UTC, e.g.
    "2026-07-02T19:26:54.000Z" — 'T' separates date/time, 'Z' means UTC.
    Shown converted to local time in a plainer format instead."""
    if not iso:
        return ""
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        return dt.astimezone().strftime("%Y-%m-%d %H:%M:%S")
    except ValueError:
        return iso


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
# on my disk" experience we skip that raw listing and instead offer
# named roots as buttons in the sidebar. "devices" and "albums" are
# still reachable by typing a raw "/section/..." path, just not exposed
# as dedicated buttons (yet).
MY_FILES_ROOT = "/my-files"
PHOTOS_ROOT = "/photos"
TRASH_ROOT = "/trash"
SHARED_BY_ME_ROOT = "/shared-by-me"
SHARED_WITH_ME_ROOT = "/shared-with-me"

ROOT_LABELS = {
    MY_FILES_ROOT: "My files",
    PHOTOS_ROOT: "Photos",
    TRASH_ROOT: "Trash",
    SHARED_BY_ME_ROOT: "Shared by me",
    SHARED_WITH_ME_ROOT: "Shared with me",
}
ROOT_ICONS = {
    MY_FILES_ROOT: "folder",
    PHOTOS_ROOT: "photos",
    TRASH_ROOT: "delete",
    SHARED_BY_ME_ROOT: "shared",
    SHARED_WITH_ME_ROOT: "shared",
}
# Roots where rename/delete semantics haven't been confirmed against the
# real CLI (Photos definitely doesn't support them via `filesystem`;
# Shared roots are guesses by analogy — content you don't own, or share
# settings, may need entirely different verbs like "leave"/"unshare"
# rather than a plain delete). Context menu is skipped there rather than
# risk a wrong guess.
CONTEXT_MENU_UNSUPPORTED_ROOTS = {PHOTOS_ROOT, SHARED_BY_ME_ROOT, SHARED_WITH_ME_ROOT}

_SIDEBAR_STYLESHEET = """
    QToolButton { text-align: left; padding: 6px 8px; border: none; border-radius: 5px; }
    QToolButton:hover { background: palette(alternate-base); }
    QToolButton:checked { background: palette(highlight); color: palette(highlighted-text); }
    QToolButton#newFolderButton {
        background: palette(highlight); color: palette(highlighted-text);
        font-weight: bold; padding: 8px;
    }
    QToolButton#newFolderButton:hover { background: palette(highlight); }
    QToolButton#newFolderButton:disabled { background: palette(mid); color: palette(dark); }
"""


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        from . import __version__

        self.setWindowTitle(f"Proton Drive GUI (unofficial) \u2014 v{__version__}")
        self.resize(1080, 640)
        self.setAcceptDrops(True)
        # A floor narrow enough to still be usable, but wide enough that
        # even icon-only mode (see resizeEvent) never has to hide a
        # button — verified empirically: below a workable width, Qt's
        # toolbar just makes overflowing buttons invisible with no "»"
        # overflow indicator at all, which is worse than a fixed limit.
        self.setMinimumWidth(480)
        self.setMinimumHeight(360)

        self.thread_pool = QThreadPool()
        # PySide6 gotcha: a QRunnable handed to QThreadPool.start() can be
        # garbage-collected by Python before the pool is done with it if
        # nothing else holds a reference (the local `worker` variable in
        # the calling method goes out of scope immediately). When the pool
        # thread then tries to call back into a half-collected Python
        # object, it segfaults rather than raising a catchable exception —
        # this was very likely the cause of a crash/hang seen after login.
        # Every in-flight worker is kept here until it reports
        # finished/error, guaranteeing it stays alive for the whole call.
        self._active_workers: list[Worker] = []
        self._sidebar_buttons: list[QToolButton] = []

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

    def _sidebar_button(self, action: QAction, object_name: str | None = None) -> QToolButton:
        btn = QToolButton()
        btn.setDefaultAction(action)
        btn.setAutoRaise(True)
        btn.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        btn.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        if object_name:
            btn.setObjectName(object_name)
        self._sidebar_buttons.append(btn)
        return btn

    def _build_ui(self):
        # -- top toolbar: the few actions that act on the current selection --
        toolbar = QToolBar("Main")
        toolbar.setMovable(False)
        toolbar.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.addToolBar(toolbar)
        self._toolbar = toolbar

        self.back_action = QAction(self._icon("back"), "Back", self)
        self.back_action.triggered.connect(self.go_up)
        self.back_action.setEnabled(False)  # we start at the root
        toolbar.addAction(self.back_action)

        toolbar.addSeparator()

        self.upload_action = QAction(self._icon("upload"), "Upload", self)
        self.upload_action.triggered.connect(self.upload_files)
        toolbar.addAction(self.upload_action)

        self.download_action = QAction(self._icon("download"), "Download", self)
        self.download_action.triggered.connect(self.download_selected)
        toolbar.addAction(self.download_action)

        toolbar.addSeparator()

        self.empty_trash_action = QAction(self._icon("delete"), "Empty Trash", self)
        self.empty_trash_action.triggered.connect(self.empty_trash)
        self.empty_trash_action.setVisible(False)  # only shown while browsing Trash
        toolbar.addAction(self.empty_trash_action)

        # -- left sidebar: create, navigate, account --
        sidebar = QWidget()
        sidebar.setStyleSheet(_SIDEBAR_STYLESHEET)
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(8, 10, 8, 10)
        sidebar_layout.setSpacing(3)
        self._sidebar = sidebar

        self.new_folder_action = QAction(self._icon("new_folder"), "New folder", self)
        self.new_folder_action.triggered.connect(self.create_folder)
        sidebar_layout.addWidget(self._sidebar_button(self.new_folder_action, "newFolderButton"))
        sidebar_layout.addSpacing(10)

        self.root_actions: dict[str, QAction] = {}
        for root in (MY_FILES_ROOT, PHOTOS_ROOT, TRASH_ROOT):
            action = QAction(self._icon(ROOT_ICONS[root]), ROOT_LABELS[root], self)
            action.setCheckable(True)
            action.triggered.connect(lambda _checked=False, r=root: self.switch_root(r))
            sidebar_layout.addWidget(self._sidebar_button(action))
            self.root_actions[root] = action

        divider = QFrame()
        divider.setFrameShape(QFrame.HLine)
        divider.setFrameShadow(QFrame.Sunken)
        sidebar_layout.addWidget(divider)

        for root in (SHARED_BY_ME_ROOT, SHARED_WITH_ME_ROOT):
            action = QAction(self._icon(ROOT_ICONS[root]), ROOT_LABELS[root], self)
            action.setCheckable(True)
            action.triggered.connect(lambda _checked=False, r=root: self.switch_root(r))
            sidebar_layout.addWidget(self._sidebar_button(action))
            self.root_actions[root] = action

        sidebar_layout.addStretch(1)

        self._login_icon = self._icon("login")
        self._logout_icon = self._icon("logout")
        self.login_action = QAction(self._login_icon, "Log in", self)
        self.login_action.triggered.connect(self.toggle_auth)
        sidebar_layout.addWidget(self._sidebar_button(self.login_action))

        self.about_action = QAction(self._icon("about"), "About", self)
        self.about_action.triggered.connect(self.show_about)
        sidebar_layout.addWidget(self._sidebar_button(self.about_action))

        self.root_actions[MY_FILES_ROOT].setChecked(True)

        self._row_folder_icon = self._icon("folder", size=16)
        self._row_file_icon = self._icon("file", size=16)
        self._row_photo_icon = self._icon("photos", size=16)
        self._row_video_icon = self._icon("video", size=16)

        # -- content area: breadcrumb/path row + the file list itself --
        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(6, 6, 6, 6)

        crumb_row = QHBoxLayout()

        self.refresh_action = QAction(self._icon("refresh"), "Refresh", self)
        self.refresh_action.triggered.connect(self.refresh)
        refresh_btn = QToolButton()
        refresh_btn.setDefaultAction(self.refresh_action)
        refresh_btn.setToolButtonStyle(Qt.ToolButtonIconOnly)
        refresh_btn.setAutoRaise(True)
        crumb_row.addWidget(refresh_btn)

        self.breadcrumb_bar = QHBoxLayout()
        crumb_row.addLayout(self.breadcrumb_bar)
        crumb_row.addStretch(1)

        view_mode_group = QActionGroup(self)
        view_mode_group.setExclusive(True)
        self.list_view_action = QAction(self._icon("list_view"), "List view", self)
        self.list_view_action.setCheckable(True)
        self.list_view_action.setChecked(True)
        self.list_view_action.triggered.connect(lambda: self._set_view_mode("list"))
        view_mode_group.addAction(self.list_view_action)
        list_btn = QToolButton()
        list_btn.setDefaultAction(self.list_view_action)
        list_btn.setToolButtonStyle(Qt.ToolButtonIconOnly)
        list_btn.setAutoRaise(True)
        crumb_row.addWidget(list_btn)

        self.grid_view_action = QAction(self._icon("grid_view"), "Grid view", self)
        self.grid_view_action.setCheckable(True)
        self.grid_view_action.triggered.connect(lambda: self._set_view_mode("grid"))
        view_mode_group.addAction(self.grid_view_action)
        grid_btn = QToolButton()
        grid_btn.setDefaultAction(self.grid_view_action)
        grid_btn.setToolButtonStyle(Qt.ToolButtonIconOnly)
        grid_btn.setAutoRaise(True)
        crumb_row.addWidget(grid_btn)

        content_layout.addLayout(crumb_row)

        path_row = QHBoxLayout()
        path_row.addWidget(QLabel("Path:"))
        self.path_edit = QLineEdit(self._display_path(self.current_path))
        self.path_edit.returnPressed.connect(self._path_edited)
        path_row.addWidget(self.path_edit)
        content_layout.addLayout(path_row)

        self.view_stack = QStackedWidget()

        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["Name", "Size", "Modified"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.cellDoubleClicked.connect(self._row_double_clicked)
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._show_context_menu_table)
        self.table.installEventFilter(self)
        self.view_stack.addWidget(self.table)

        self.grid = QListWidget()
        self.grid.setViewMode(QListWidget.IconMode)
        self.grid.setIconSize(QSize(64, 64))
        self.grid.setResizeMode(QListWidget.Adjust)
        self.grid.setMovement(QListWidget.Static)
        # A fixed grid cell size is what actually makes this a *grid* —
        # without it, Qt lays items out by natural per-item size (varies
        # with filename length), producing the ragged/uneven flow seen
        # in testing rather than clean aligned rows and columns.
        self.grid.setGridSize(QSize(120, 110))
        self.grid.setUniformItemSizes(True)
        self.grid.setWordWrap(True)
        self.grid.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.grid.itemDoubleClicked.connect(
            lambda item: self._row_double_clicked(self.grid.row(item), 0)
        )
        self.grid.setContextMenuPolicy(Qt.CustomContextMenu)
        self.grid.customContextMenuRequested.connect(self._show_context_menu_grid)
        self.grid.installEventFilter(self)
        self.view_stack.addWidget(self.grid)

        content_layout.addWidget(self.view_stack)

        # -- assemble: sidebar (left) + content, as the central widget --
        outer = QWidget()
        outer_layout = QHBoxLayout(outer)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.setSpacing(0)
        outer_layout.addWidget(sidebar)
        outer_layout.addWidget(content, 1)

        self.setCentralWidget(outer)
        self.setStatusBar(QStatusBar())
        self._update_breadcrumbs()

    def _init_cli(self):
        try:
            self.cli = ProtonDriveCLI()
        except ProtonDriveNotFoundError as e:
            QMessageBox.critical(self, "proton-drive not found", str(e))
            self.statusBar().showMessage("proton-drive CLI not found", 5000)
            return
        self._refresh_auth_state(then_refresh=True)

    # -- view mode (list / grid) --------------------------------------------------

    def _set_view_mode(self, mode: str):
        self.view_stack.setCurrentWidget(self.grid if mode == "grid" else self.table)

    def _selected_rows(self) -> list[int]:
        if self.view_stack.currentWidget() is self.grid:
            return sorted({self.grid.row(it) for it in self.grid.selectedItems()})
        return sorted({idx.row() for idx in self.table.selectedIndexes()})

    # -- responsive layout -------------------------------------------------------

    _SIDEBAR_TEXT_THRESHOLD = 760
    _TOOLBAR_TEXT_THRESHOLD = 620
    _SIDEBAR_WIDE = 180
    _SIDEBAR_NARROW = 52

    def resizeEvent(self, event):
        super().resizeEvent(event)

        sidebar_wide = self.width() >= self._SIDEBAR_TEXT_THRESHOLD
        sidebar_style = Qt.ToolButtonTextBesideIcon if sidebar_wide else Qt.ToolButtonIconOnly
        for btn in self._sidebar_buttons:
            if btn.toolButtonStyle() != sidebar_style:
                btn.setToolButtonStyle(sidebar_style)
        new_width = self._SIDEBAR_WIDE if sidebar_wide else self._SIDEBAR_NARROW
        if self._sidebar.minimumWidth() != new_width:
            self._sidebar.setFixedWidth(new_width)

        top_style = (
            Qt.ToolButtonIconOnly
            if self.width() < self._TOOLBAR_TEXT_THRESHOLD
            else Qt.ToolButtonTextBesideIcon
        )
        if self._toolbar.toolButtonStyle() != top_style:
            self._toolbar.setToolButtonStyle(top_style)

    # -- keyboard shortcuts -------------------------------------------------------

    def eventFilter(self, obj, event):
        if (
            event.type() == QEvent.KeyPress
            and event.key() == Qt.Key_Delete
            and obj in (self.table, self.grid)
            and self.current_root == MY_FILES_ROOT
            and self._selected_rows()
        ):
            self._delete_selected()
            return True
        return super().eventFilter(obj, event)

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
        self.new_folder_action.setEnabled(root == MY_FILES_ROOT)
        self.upload_action.setEnabled(root not in (TRASH_ROOT, SHARED_WITH_ME_ROOT))
        self.empty_trash_action.setVisible(root == TRASH_ROOT)
        for r, action in self.root_actions.items():
            action.setChecked(r == root)
        self.navigate_to(root)

    def _path_edited(self):
        self.navigate_to(self._actual_path(self.path_edit.text()))

    def navigate_to(self, path: str):
        self.current_path = path if path.startswith("/") else f"/{path}"
        self.path_edit.setText(self._display_path(self.current_path))
        self.back_action.setEnabled(self.current_path != self.current_root)
        self._update_breadcrumbs()
        self.refresh()

    def _update_breadcrumbs(self):
        while self.breadcrumb_bar.count():
            item = self.breadcrumb_bar.takeAt(0)
            widget = item.widget()
            if widget:
                # Removing from the layout doesn't hide it immediately —
                # deleteLater()'s actual cleanup waits for the event loop,
                # which briefly left the old crumb rendered on top of the
                # new one (visible in testing). Hide synchronously first.
                widget.hide()
                widget.deleteLater()

        def add_crumb(text: str, target: str, current: bool):
            btn = QToolButton()
            btn.setText(text)
            btn.setAutoRaise(True)
            font = btn.font()
            font.setBold(current)
            btn.setFont(font)
            btn.setEnabled(not current)
            btn.clicked.connect(lambda: self.navigate_to(target))
            self.breadcrumb_bar.addWidget(btn)

        segments = [s for s in self._display_path(self.current_path).split("/") if s]
        add_crumb(ROOT_LABELS.get(self.current_root, "/"), self.current_root, not segments)

        accumulated = ""
        for i, seg in enumerate(segments):
            self.breadcrumb_bar.addWidget(QLabel("\u203a"))
            accumulated += f"/{seg}"
            add_crumb(seg, self.current_root + accumulated, i == len(segments) - 1)

    def go_up(self):
        if self.current_path in ("/", "", self.current_root):
            return
        parent = str(PurePosixPath(self.current_path).parent)
        # Never let "Back" escape above the current root into the raw
        # virtual-section root ("/devices", ...).
        if not (parent + "/").startswith(self.current_root + "/") and parent != self.current_root:
            parent = self.current_root
        self.navigate_to(parent)

    def _row_double_clicked(self, row: int, _col: int):
        item = self.items[row]
        if item.is_folder:
            new_path = f"{self.current_path.rstrip('/')}/{item.name}"
            self.navigate_to(new_path)

    def _show_context_menu_table(self, pos):
        index = self.table.indexAt(pos)
        if not index.isValid():
            return
        row = index.row()
        if row not in self._selected_rows():
            self.table.selectRow(row)
        self._open_context_menu(row, self.table.viewport().mapToGlobal(pos))

    def _show_context_menu_grid(self, pos):
        item = self.grid.itemAt(pos)
        if item is None:
            return
        row = self.grid.row(item)
        if row not in self._selected_rows():
            self.grid.clearSelection()
            item.setSelected(True)
        self._open_context_menu(row, self.grid.viewport().mapToGlobal(pos))

    def _open_context_menu(self, row: int, global_pos):
        if self.current_root in CONTEXT_MENU_UNSUPPORTED_ROOTS:
            return  # rename/delete/restore semantics unconfirmed here — skip rather than guess

        menu = QMenu(self)

        if self.current_root == TRASH_ROOT:
            restore_action = menu.addAction(self._icon("refresh", size=16), "Restore")
            delete_action = menu.addAction(self._icon("delete", size=16), "Delete Permanently\u2026")
            chosen = menu.exec(global_pos)
            if chosen == restore_action:
                self._restore_selected()
            elif chosen == delete_action:
                self._permanently_delete_selected()
            return

        rename_action = menu.addAction(self._icon("rename", size=16), "Rename\u2026")
        delete_action = menu.addAction(self._icon("delete", size=16), "Move to Trash\u2026")
        chosen = menu.exec(global_pos)
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
        rows = self._selected_rows()
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
        rows = self._selected_rows()
        if not rows:
            return
        paths = [f"{self.current_path.rstrip('/')}/{self.items[r].name}" for r in rows]
        self.statusBar().showMessage(f"Restoring {len(paths)} item(s) \u2026")
        self._start_worker(self.cli.restore, paths, on_finished=lambda _: self.refresh())

    def _permanently_delete_selected(self):
        rows = self._selected_rows()
        if not rows:
            return
        names = [self.items[r].name for r in rows]
        listing = "\n".join(f"\u2022 {n}" for n in names)
        confirm = QMessageBox.question(
            self,
            "Delete Permanently",
            f"Permanently delete:\n{listing}\n\nThis cannot be undone.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if confirm != QMessageBox.Yes:
            return
        paths = [f"{self.current_path.rstrip('/')}/{self.items[r].name}" for r in rows]
        self.statusBar().showMessage(f"Deleting {len(paths)} item(s) permanently \u2026")
        self._start_worker(self.cli.delete, paths, on_finished=lambda _: self.refresh())

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
        self.grid.clear()
        for row, item in enumerate(self.items):
            if item.is_folder:
                icon = self._row_folder_icon
            elif self.current_root == PHOTOS_ROOT:
                media_type = item.raw.get("mediaType", "")
                icon = self._row_video_icon if media_type.startswith("video/") else self._row_photo_icon
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
            self.table.setItem(row, 2, QTableWidgetItem(format_timestamp(item.modified)))

            size_label = "" if item.is_folder else human_size(item.size)
            grid_text = f"{item.name}\n{size_label}" if size_label else item.name
            grid_item = QListWidgetItem(icon, grid_text)
            grid_item.setTextAlignment(Qt.AlignHCenter)
            self.grid.addItem(grid_item)

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
            self.grid.clear()
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
        rows = self._selected_rows()
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
                self.items[row].raw.get("uid") or self.items[row].raw.get("nodeUid")
                for row in rows
                if self.items[row].raw.get("uid") or self.items[row].raw.get("nodeUid")
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

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            style = "QTableWidget, QListWidget { border: 2px dashed palette(highlight); }"
            self.table.setStyleSheet(style)
            self.grid.setStyleSheet(style)

    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dragLeaveEvent(self, event):
        self.table.setStyleSheet("")
        self.grid.setStyleSheet("")

    def dropEvent(self, event):
        self.table.setStyleSheet("")
        self.grid.setStyleSheet("")
        if not self.cli:
            event.ignore()
            return

        local_paths = [
            url.toLocalFile() for url in event.mimeData().urls() if url.isLocalFile()
        ]
        existing = [p for p in local_paths if Path(p).exists()]
        event.acceptProposedAction()
        if not existing:
            return

        if self.current_root == PHOTOS_ROOT:
            # `photo upload`'s docs only show individual files, unlike
            # `filesystem upload` below — not confirmed for folders.
            files = [p for p in existing if Path(p).is_file()]
            dirs = [p for p in existing if Path(p).is_dir()]
            if not files:
                if dirs:
                    QMessageBox.information(
                        self,
                        "Folders not supported here",
                        "Photos upload doesn't accept whole folders — drop individual "
                        "photo/video files, or use the Upload button.",
                    )
                return
            self._upload_paths(files)
            return

        # The official CLI docs show `filesystem upload ./local-folder
        # /my-files/parent` as a normal example, so folders are passed
        # straight through here too, not just files.
        self._upload_paths(existing)
