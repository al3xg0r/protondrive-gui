"""Small QThreadPool-based helper so CLI calls never block the GUI thread."""

from __future__ import annotations

import traceback

from PySide6.QtCore import QObject, QRunnable, Signal, Slot


class WorkerSignals(QObject):
    finished = Signal(object)
    error = Signal(str)


class Worker(QRunnable):
    """Runs `fn(*args, **kwargs)` on a background thread.

    Usage:
        worker = Worker(cli.list_dir, "/Documents")
        worker.signals.finished.connect(on_done)
        worker.signals.error.connect(on_error)
        thread_pool.start(worker)
    """

    def __init__(self, fn, *args, **kwargs):
        super().__init__()
        self.fn = fn
        self.args = args
        self.kwargs = kwargs
        self.signals = WorkerSignals()

    @Slot()
    def run(self):
        try:
            result = self.fn(*self.args, **self.kwargs)
        except Exception as e:  # noqa: BLE001 - surfaced to the UI, not swallowed
            self.signals.error.emit(f"{e}\n\n{traceback.format_exc()}")
        else:
            self.signals.finished.emit(result)
