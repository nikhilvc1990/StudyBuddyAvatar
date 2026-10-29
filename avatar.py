import math

from PyQt6.QtCore import Qt, QTimer, QPoint, QPropertyAnimation, QEasingCurve
from PyQt6.QtGui import QPainter, QBrush, QColor, QPen
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel, QApplication

from config import WAKE_WORD


class ClippyFace(QWidget):
    STATES = {
        "idle":      {"mouth": "smile",   "color": "#4FC3F7"},
        "listening": {"mouth": "open",    "color": "#81C784"},
        "thinking":  {"mouth": "hmm",     "color": "#FFD54F"},
        "talking":   {"mouth": "talking", "color": "#F48FB1"},
        "alert":     {"mouth": "open",    "color": "#FF7043"},
    }

    def __init__(self):
        super().__init__()
        self.state = "idle"
        self.blink_open = True
        self.mouth_phase = 0
        self.bob_phase = 0
        self.setFixedSize(120, 140)

        self._anim_timer = QTimer(self)
        self._anim_timer.timeout.connect(self._tick)
        self._anim_timer.start(40)

        self._blink_timer = QTimer(self)
        self._blink_timer.timeout.connect(self._do_blink)
        self._blink_timer.start(2800)

        self._bounce_anim = QPropertyAnimation(self, b"pos")
        self._bounce_anim.setDuration(400)
        self._bounce_anim.setEasingCurve(QEasingCurve.Type.OutBounce)

    def set_state(self, state):
        if state in self.STATES:
            self.state = state
            self.update()
            if state == "alert":
                self._trigger_bounce()

    def _trigger_bounce(self):
        pos = self.pos()
        self._bounce_anim.setStartValue(pos)
        self._bounce_anim.setEndValue(pos + QPoint(0, -12))
        self._bounce_anim.start()

    def _tick(self):
        self.mouth_phase = (self.mouth_phase + 0.45) % (2 * math.pi)
        self.bob_phase = (self.bob_phase + 0.12) % (2 * math.pi)
        self.update()

    def _do_blink(self):
        self.blink_open = False
        self.update()
        QTimer.singleShot(110, self._open_eyes)

    def _open_eyes(self):
        self.blink_open = True
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        cfg = self.STATES[self.state]
        cx = 60
        cy = 60 + int(5 * math.sin(self.bob_phase))

        # Face
        p.setBrush(QBrush(QColor(cfg["color"])))
        p.setPen(QPen(QColor("#333"), 3.0))
        p.drawEllipse(cx - 45, cy - 45, 90, 90)

        # Eyes
        for ex in (cx - 16, cx + 16):
            if self.blink_open:
                p.setBrush(QBrush(QColor("white")))
                p.setPen(QPen(QColor("#333"), 2.0))
                p.drawEllipse(ex - 6, cy - 20, 12, 14)
                p.setBrush(QBrush(QColor("#222")))
                p.drawEllipse(ex - 3, cy - 17, 7, 8)
                p.setBrush(QBrush(QColor("white")))
                p.drawEllipse(ex - 1, cy - 19, 3, 3)
            else:
                p.setPen(QPen(QColor("#333"), 2.5))
                p.drawLine(ex - 6, cy - 14, ex + 6, cy - 14)

        # Mouth
        p.setPen(QPen(QColor("#222"), 2.5))
        mouth = cfg["mouth"]
        if mouth == "smile":
            p.drawArc(cx - 18, cy + 10, 36, 20, 200 * 16, 140 * 16)
        elif mouth == "open":
            p.setBrush(QBrush(QColor("#222")))
            p.drawEllipse(cx - 11, cy + 12, 22, 16)
        elif mouth == "hmm":
            p.drawLine(cx - 13, cy + 18, cx + 13, cy + 18)
        elif mouth == "talking":
            h = int(10 + 8 * math.sin(self.mouth_phase))
            p.setBrush(QBrush(QColor("#222")))
            p.drawEllipse(cx - 13, cy + 11, 26, h)

        p.end()


class AssistantWindow(QWidget):
    def __init__(self, bridge):
        super().__init__()
        self.bridge = bridge
        self.drag_pos = QPoint()

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_MacAlwaysShowToolWindow, True)
        self.setFixedSize(160, 200)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(4)

        self.face = ClippyFace()
        layout.addWidget(self.face, alignment=Qt.AlignmentFlag.AlignCenter)

        self.label = QLabel(f"Say '{WAKE_WORD}' to wake me")
        self.label.setWordWrap(True)
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.label.setStyleSheet("""
            QLabel {
                background: rgba(255,255,255,220);
                border-radius: 8px;
                padding: 4px 6px;
                font-size: 10px;
                color: #222;
            }
        """)
        self.label.setFixedWidth(140)
        layout.addWidget(self.label, alignment=Qt.AlignmentFlag.AlignCenter)

        bridge.set_state.connect(self.face.set_state, Qt.ConnectionType.QueuedConnection)
        bridge.set_message.connect(self.label.setText, Qt.ConnectionType.QueuedConnection)

        self._keep_alive = QTimer(self)
        self._keep_alive.timeout.connect(self._raise_window)
        self._keep_alive.start(2000)

        screen = QApplication.primaryScreen().geometry()
        self.move(screen.width() - 180, screen.height() - 240)
        self.show()

    def _raise_window(self):
        self.raise_()
        self.show()

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self.drag_pos = e.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, e):
        if e.buttons() == Qt.MouseButton.LeftButton:
            self.move(e.globalPosition().toPoint() - self.drag_pos)

    def mouseDoubleClickEvent(self, _):
        QApplication.quit()