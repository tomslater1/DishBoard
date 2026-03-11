"""
Background thread helpers for DishBoard.

Usage:
    worker = Worker(some_function, arg1, key=val)
    worker.signals.result.connect(my_slot)
    worker.signals.error.connect(my_error_slot)
    QThreadPool.globalInstance().start(worker)
"""

import traceback
from PySide6.QtCore import QRunnable, QObject, Signal, QThreadPool, Qt


class WorkerSignals(QObject):
    result = Signal(object)
    error  = Signal(str)


class Worker(QRunnable):
    """Run any callable in the global thread pool."""

    def __init__(self, fn, *args, **kwargs):
        super().__init__()
        self.fn      = fn
        self.args    = args
        self.kwargs  = kwargs
        self.signals = WorkerSignals()
        self.setAutoDelete(False)   # keep Python wrapper alive until signals fire

    def run(self):
        try:
            result = self.fn(*self.args, **self.kwargs)
            self.signals.result.emit(result)
        except Exception:
            self.signals.error.emit(traceback.format_exc())


def run_async(fn, *args, on_result=None, on_error=None, **kwargs) -> Worker:
    """Convenience: create, connect, and start a Worker. Returns the worker."""
    worker = Worker(fn, *args, **kwargs)
    # QueuedConnection forces callbacks onto the main thread even if the signal
    # is emitted from a worker thread — prevents Qt thread-safety segfaults.
    if on_result:
        worker.signals.result.connect(on_result, Qt.ConnectionType.QueuedConnection)
    if on_error:
        worker.signals.error.connect(on_error, Qt.ConnectionType.QueuedConnection)
    QThreadPool.globalInstance().start(worker)
    return worker
