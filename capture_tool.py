"""
Offline replacement for Teachable Machine's "Image Project" capture step.

Shows the webcam and one card per class (Mobile, Reading, Sleeping, ...).
Hold "Hold to Record" (or hold the class's number key) to save frames into
captured/<Class>/. Then label them with label_tool.py.

Run: python capture_tool.py   (or press Run in PyCharm)
"""
import os
import shutil
import sys
import time
from datetime import datetime
from pathlib import Path

import cv2
from PyQt6.QtCore import QEvent, QSize, Qt, QTimer
from PyQt6.QtGui import QIcon, QPixmap
from PyQt6.QtWidgets import (
    QApplication, QCheckBox, QFileDialog, QFrame, QHBoxLayout, QInputDialog, QLabel,
    QLineEdit, QListView, QListWidget, QListWidgetItem, QMainWindow, QMessageBox, QPushButton,
    QScrollArea, QSizePolicy, QSpinBox, QVBoxLayout, QWidget,
)

from config import CAMERA_INDEX, CAPTURE_DELAY, CAPTURE_DIR, CAPTURE_FPS, CAPTURE_SIZE
from dataset_tools_common import (
    all_class_names, class_color, cv_to_qimage, list_images, read_image, write_image,
)

THUMB_SIZE = QSize(80, 60)
MAX_THUMBS = 40


def _thumb_icon(frame):
    pix = QPixmap.fromImage(cv_to_qimage(frame))
    return QIcon(pix.scaled(THUMB_SIZE, Qt.AspectRatioMode.KeepAspectRatio,
                            Qt.TransformationMode.SmoothTransformation))


class ClassCard(QFrame):
    """One class: name, count, thumbnails and capture buttons (like a Teachable Machine card)."""

    def __init__(self, window, name, idx):
        super().__init__()
        self.owner = window
        self.name = name
        self.folder = Path(CAPTURE_DIR) / name
        self.folder.mkdir(parents=True, exist_ok=True)

        color = class_color(idx).name()
        self.setObjectName("card")
        # Explicit colours: the card is always white, so text/buttons must not follow
        # the Windows dark-mode palette (light text) or they vanish.
        self.setStyleSheet(f"""
            QFrame#card {{ background: white; border: 1px solid #ddd;
                          border-left: 6px solid {color}; border-radius: 8px; }}
            QFrame#card QLabel {{ color: #222; background: transparent; }}
            QFrame#card QPushButton {{ color: #222; background: #eceff3; border: 1px solid #b8bec6;
                                      border-radius: 4px; padding: 5px 10px; }}
            QFrame#card QPushButton:hover {{ background: #dde2e8; }}
            QFrame#card QPushButton:pressed {{ background: #c9d0d8; }}
        """)

        title = QLabel(f"<b>{idx + 1}. {name}</b>")
        title.setStyleSheet("font-size: 15px; border: none; color: #222;")
        self.count_label = QLabel()
        self.count_label.setStyleSheet("color: #555; border: none;")
        open_btn = QPushButton("Open folder")
        open_btn.clicked.connect(lambda: os.startfile(self.folder))
        clear_btn = QPushButton("Clear")
        clear_btn.clicked.connect(self.clear)
        head = QHBoxLayout()
        head.addWidget(title)
        head.addSpacing(8)
        head.addWidget(self.count_label)
        head.addStretch()
        head.addWidget(open_btn)
        head.addWidget(clear_btn)

        self.record_btn = QPushButton("● Hold to Record")
        self.record_btn.setStyleSheet(
            f"QPushButton {{ background: {color}; color: white; font-weight: bold; padding: 6px 12px;"
            " border: none; border-radius: 4px; }"
            "QPushButton:pressed { background: #c62828; }"
        )
        self.record_btn.pressed.connect(lambda: window.start_recording(self))
        self.record_btn.released.connect(lambda: window.release_record_button(self))

        snap_btn = QPushButton("Snapshot")
        snap_btn.clicked.connect(lambda: window.save_frame(self))
        upload_btn = QPushButton("Upload…")
        upload_btn.clicked.connect(self.upload)

        buttons = QHBoxLayout()
        for b in (self.record_btn, snap_btn, upload_btn):
            buttons.addWidget(b)
        buttons.addStretch()
        for b in (self.record_btn, snap_btn, upload_btn, open_btn, clear_btn):
            b.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        self.thumbs = QListWidget()
        self.thumbs.setViewMode(QListView.ViewMode.IconMode)
        self.thumbs.setFlow(QListView.Flow.LeftToRight)
        self.thumbs.setWrapping(False)
        self.thumbs.setIconSize(THUMB_SIZE)
        self.thumbs.setFixedHeight(THUMB_SIZE.height() + 34)
        self.thumbs.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.thumbs.setStyleSheet("border: none; background: #f7f7f7;")
        self.thumbs.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        self.thumbs.itemDoubleClicked.connect(lambda it: os.startfile(it.data(Qt.ItemDataRole.UserRole)))

        layout = QVBoxLayout(self)
        layout.addLayout(head)
        layout.addLayout(buttons)
        layout.addWidget(self.thumbs)

        self.count = 0
        self.reload()

    def reload(self):
        files = list_images(self.folder)
        self.count = len(files)
        self.thumbs.clear()
        for path in files[-MAX_THUMBS:]:
            frame = read_image(path)
            if frame is not None:
                self._insert_thumb(path, frame)
        self._update_count()

    def _insert_thumb(self, path, frame):
        item = QListWidgetItem(_thumb_icon(frame), "")
        item.setData(Qt.ItemDataRole.UserRole, str(path))
        item.setToolTip(Path(path).name)
        self.thumbs.insertItem(0, item)
        while self.thumbs.count() > MAX_THUMBS:
            self.thumbs.takeItem(self.thumbs.count() - 1)

    def _update_count(self):
        self.count_label.setText(f"{self.count} image{'s' if self.count != 1 else ''}")

    def new_path(self, suffix=".jpg", tag=""):
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
        path = self.folder / f"{self.name}_{tag}{stamp}{suffix}"
        n = 1
        while path.exists():
            path = self.folder / f"{self.name}_{tag}{stamp}_{n}{suffix}"
            n += 1
        return path

    def add_frame(self, frame):
        path = self.new_path()
        if write_image(path, frame):
            self.count += 1
            self._insert_thumb(path, frame)
            self._update_count()
            return True
        return False

    def upload(self):
        files, _ = QFileDialog.getOpenFileNames(
            self, f"Add images to {self.name}", "",
            "Images (*.jpg *.jpeg *.png *.bmp *.webp)")
        for f in files:
            src = Path(f)
            dst = self.new_path(src.suffix.lower(), tag="upload_")
            shutil.copy2(src, dst)
        if files:
            self.reload()
            self.owner.update_status()

    def clear(self):
        if not self.count:
            return
        answer = QMessageBox.question(
            self, "Clear class",
            f"Delete all {self.count} images in\n{self.folder} ?\nThis cannot be undone.")
        if answer != QMessageBox.StandardButton.Yes:
            return
        for path in list_images(self.folder):
            path.unlink()
        self.reload()
        self.owner.update_status()


class CaptureWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("StudyBuddy – Image Capture (offline Teachable Machine)")
        self.resize(1250, 760)

        self.cap = None
        self.frame = None
        self.recording_card = None
        self.countdown_left = 0
        self.record_until = 0.0     # >0: timed recording (duration mode)
        self.cards = []

        # ---- Left: camera preview + settings ----
        self.preview = QLabel("Opening camera…")
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview.setMinimumSize(560, 420)
        self.preview.setStyleSheet("background: #222; color: #eee; font-size: 16px;")

        self.overlay = QLabel("")
        self.overlay.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.overlay.setStyleSheet("font-size: 18px; font-weight: bold; color: #c62828;")

        self.cam_spin = QSpinBox()
        self.cam_spin.setRange(0, 9)
        self.cam_spin.setValue(CAMERA_INDEX)
        self.cam_spin.valueChanged.connect(self.open_camera)
        self.mirror_chk = QCheckBox("Mirror preview")
        self.mirror_chk.setChecked(True)
        self.fps_spin = QSpinBox()
        self.fps_spin.setRange(1, 30)
        self.fps_spin.setValue(CAPTURE_FPS)
        self.fps_spin.setSuffix(" fps")
        self.delay_spin = QSpinBox()
        self.delay_spin.setRange(0, 10)
        self.delay_spin.setValue(CAPTURE_DELAY)
        self.delay_spin.setSuffix(" s")
        self.duration_spin = QSpinBox()
        self.duration_spin.setRange(0, 60)
        self.duration_spin.setSpecialValueText("hold")
        self.duration_spin.setSuffix(" s")
        self.duration_spin.setToolTip(
            "'hold' = record while the button/key is held.\n"
            "N s = one click starts a recording of N seconds (after the delay).")

        settings = QHBoxLayout()
        for text, w in (("Camera", self.cam_spin), ("Rate", self.fps_spin),
                        ("Delay", self.delay_spin), ("Duration", self.duration_spin)):
            settings.addWidget(QLabel(text))
            settings.addWidget(w)
        settings.addWidget(self.mirror_chk)
        settings.addStretch()

        hint = QLabel("Tip: hold keys 1–9 to record that class, Space = snapshot of the last used class. "
                      "Images are saved un-mirrored, as the detector sees them.")
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #888;")     # mid-grey: readable on light and dark

        left = QVBoxLayout()
        left.addWidget(self.preview, 1)
        left.addWidget(self.overlay)
        left.addLayout(settings)
        left.addWidget(hint)

        # ---- Right: class cards ----
        self.cards_box = QVBoxLayout()
        self.cards_box.setSpacing(10)
        add_btn = QPushButton("+ Add a class")
        add_btn.setStyleSheet("padding: 10px; border: 2px dashed #aaa; color: #555;")
        add_btn.clicked.connect(self.add_class)
        label_btn = QPushButton("Next: label boxes →")
        label_btn.clicked.connect(self.open_label_tool)

        cards_widget = QWidget()
        cards_layout = QVBoxLayout(cards_widget)
        cards_layout.addLayout(self.cards_box)
        cards_layout.addWidget(add_btn)
        cards_layout.addWidget(label_btn)
        cards_layout.addStretch()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setWidget(cards_widget)
        scroll.setMinimumWidth(600)
        scroll.setStyleSheet("QScrollArea { background: #f0f2f5; border: none; }")
        cards_widget.setStyleSheet("background: #f0f2f5;")
        label_btn.setStyleSheet("padding: 10px; font-weight: bold; color: #222; background: #e3e7ec;"
                                " border: 1px solid #b8bec6; border-radius: 4px;")

        root = QWidget()
        main = QHBoxLayout(root)
        main.addLayout(left, 1)
        main.addWidget(scroll, 1)
        self.setCentralWidget(root)

        for name in all_class_names():
            self._add_card(name)
        self.last_card = self.cards[0] if self.cards else None

        # Timers: preview, frame saving, countdown
        self.preview_timer = QTimer(self)
        self.preview_timer.timeout.connect(self.read_frame)
        self.record_timer = QTimer(self)
        self.record_timer.timeout.connect(self._record_tick)
        self.countdown_timer = QTimer(self)
        self.countdown_timer.timeout.connect(self._countdown_tick)

        self.open_camera(self.cam_spin.value())
        self.update_status()
        QApplication.instance().installEventFilter(self)

    # ---------- camera ----------
    def open_camera(self, index):
        self.preview_timer.stop()
        if self.cap is not None:
            self.cap.release()
        self.cap = cv2.VideoCapture(index)
        if not self.cap.isOpened():
            self.cap = None
            self.preview.setText(f"Camera {index} not accessible.\n"
                                 "Try another index, or check Windows camera privacy settings.\n"
                                 "You can still use Upload… on each class.")
            return
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, CAPTURE_SIZE[0])
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, CAPTURE_SIZE[1])
        self.preview_timer.start(33)

    def read_frame(self):
        if self.cap is None:
            return
        ok, frame = self.cap.read()
        if not ok:
            return
        self.frame = frame
        shown = cv2.flip(frame, 1) if self.mirror_chk.isChecked() else frame
        if self.recording_card is not None and self.countdown_left == 0:
            cv2.circle(shown, (24, 24), 10, (0, 0, 255), -1)   # red "REC" dot
        pix = QPixmap.fromImage(cv_to_qimage(shown)).scaled(
            self.preview.size(), Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation)
        self.preview.setPixmap(pix)

        if self.record_until and time.time() >= self.record_until:
            self.stop_recording()

    # ---------- recording ----------
    def save_frame(self, card):
        self.last_card = card
        if self.frame is None:
            self.statusBar().showMessage("No camera frame yet.", 3000)
            return
        card.add_frame(self.frame.copy())
        self.update_status()

    def start_recording(self, card):
        if self.recording_card is not None:
            if self.duration_spin.value() and self.recording_card is card:
                self.stop_recording()      # second click cancels a timed recording
            return
        self.recording_card = card
        self.last_card = card
        self.countdown_left = self.delay_spin.value()
        if self.countdown_left:
            self.overlay.setText(f"{card.name}: starting in {self.countdown_left}…")
            self.countdown_timer.start(1000)
        else:
            self._begin_saving()

    def _countdown_tick(self):
        self.countdown_left -= 1
        if self.countdown_left > 0:
            self.overlay.setText(f"{self.recording_card.name}: starting in {self.countdown_left}…")
        else:
            self.countdown_timer.stop()
            self._begin_saving()

    def _begin_saving(self):
        duration = self.duration_spin.value()
        self.record_until = time.time() + duration if duration else 0.0
        self.overlay.setText(f"● Recording {self.recording_card.name}"
                             + (f" for {duration} s" if duration else " – release to stop"))
        self._record_tick()
        self.record_timer.start(int(1000 / self.fps_spin.value()))

    def _record_tick(self):
        if self.recording_card is not None and self.frame is not None:
            self.recording_card.add_frame(self.frame.copy())
            self.update_status()

    def release_record_button(self, card):
        # In "hold" mode, releasing stops. In timed mode, the timer stops it.
        if self.duration_spin.value() == 0 and self.recording_card is card:
            self.stop_recording()

    def stop_recording(self):
        self.record_timer.stop()
        self.countdown_timer.stop()
        self.countdown_left = 0
        self.record_until = 0.0
        self.recording_card = None
        self.overlay.setText("")

    # ---------- keyboard: hold 1–9 to record, Space = snapshot ----------
    # App-wide filter so the keys work even when a button has focus
    # (but not while typing in a spin box or dialog).
    def eventFilter(self, obj, e):
        if e.type() not in (QEvent.Type.KeyPress, QEvent.Type.KeyRelease) or not self.isActiveWindow():
            return False
        if isinstance(QApplication.focusWidget(), (QSpinBox, QLineEdit)):
            return False
        key = e.key()
        is_digit = Qt.Key.Key_1 <= key <= Qt.Key.Key_9
        if not is_digit and key != Qt.Key.Key_Space:
            return False
        if e.isAutoRepeat():
            return True
        pressed = e.type() == QEvent.Type.KeyPress
        if is_digit:
            i = key - Qt.Key.Key_1
            if i < len(self.cards):
                if pressed:
                    self.start_recording(self.cards[i])
                else:
                    self.release_record_button(self.cards[i])
        elif pressed and self.last_card:
            self.save_frame(self.last_card)
        return True

    # ---------- classes ----------
    def _add_card(self, name):
        card = ClassCard(self, name, len(self.cards))
        self.cards.append(card)
        self.cards_box.addWidget(card)

    def add_class(self):
        name, ok = QInputDialog.getText(self, "Add class", "Class name (e.g. Drinking):")
        name = name.strip()
        if not ok or not name:
            return
        if any(c in name for c in '\\/:*?"<>|'):
            QMessageBox.warning(self, "Add class", "Class name cannot contain \\ / : * ? \" < > |")
            return
        if name in (c.name for c in self.cards):
            QMessageBox.information(self, "Add class", f"'{name}' already exists.")
            return
        self._add_card(name)
        self.update_status()

    def update_status(self):
        counts = {c.name: c.count for c in self.cards}
        text = "   ".join(f"{n}: {k}" for n, k in counts.items())
        values = [v for v in counts.values()]
        if values and min(values) and max(values) > 2 * min(values):
            text += "    ⚠ classes are unbalanced – try to capture a similar number for each"
        elif values and 0 < sum(values) and min(values) == 0:
            text += "    ⚠ some classes have no images yet"
        self.statusBar().showMessage(text)

    def open_label_tool(self):
        from label_tool import LabelWindow
        app = QApplication.instance()
        app._label_window = LabelWindow()     # keep a reference after this window closes
        app._label_window.show()
        self.close()

    def closeEvent(self, e):
        QApplication.instance().removeEventFilter(self)
        self.stop_recording()
        self.preview_timer.stop()
        if self.cap is not None:
            self.cap.release()
            self.cap = None
        super().closeEvent(e)


if __name__ == "__main__":
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(True)
    w = CaptureWindow()
    w.show()
    sys.exit(app.exec())
