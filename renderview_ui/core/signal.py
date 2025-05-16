from PySide6.QtCore import QObject, Signal  # type: ignore

class SignalEmitter(QObject):
    show_window = Signal()
    exit_app = Signal()
    close_mainwindow = Signal()
    
signal_emitter = SignalEmitter()