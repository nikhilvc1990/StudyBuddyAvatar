from PyQt6.QtCore import QObject, pyqtSignal


class Bridge(QObject):
    """Thread-safe way for background threads to update the UI."""
    set_state = pyqtSignal(str)     # idle, listening, thinking, talking, alert
    set_message = pyqtSignal(str)   # caption text under the face