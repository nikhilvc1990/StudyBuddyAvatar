"""
Offline replacement for Label Studio (bounding boxes, YOLO export).

Loads images from captured/<Class>/ (made by capture_tool.py) and from
Dataset_Full/images/ (earlier exports, e.g. from Label Studio), lets you draw
and label boxes, and saves straight into the YOLO layout that
DatasetTrainTestSplit.py expects:

    Dataset_Full/images/<name>.jpg
    Dataset_Full/labels/<name>.txt     "class cx cy w h" (normalised 0–1)
    Dataset_Full/classes.txt

Run: python label_tool.py   (or press Run in PyCharm)
"""
import copy
import os
import shutil
import sys
from pathlib import Path

from PyQt6.QtCore import QPointF, QRectF, Qt, pyqtSignal
from PyQt6.QtGui import QBrush, QColor, QCursor, QFont, QKeySequence, QPainter, QPen, QShortcut
from PyQt6.QtWidgets import (
    QApplication, QButtonGroup, QCheckBox, QFileDialog, QHBoxLayout, QLabel, QListWidget,
    QListWidgetItem, QMainWindow, QMessageBox, QPushButton, QRadioButton, QSplitter,
    QVBoxLayout, QWidget,
)

from config import CAPTURE_DIR, DATASET_FULL_DIR, YOLO_MODEL_PATH
from dataset_tools_common import (
    IMG_EXTS, all_class_names, class_color, cv_to_qimage, load_class_names, read_image,
)

IMAGES_DIR = Path(DATASET_FULL_DIR) / "images"
LABELS_DIR = Path(DATASET_FULL_DIR) / "labels"
CLASSES_FILE = Path(DATASET_FULL_DIR) / "classes.txt"
MIN_BOX = 4          # px (image space); smaller drags are ignored


def label_path_for(image_path):
    return LABELS_DIR / f"{Path(image_path).stem}.txt"


def load_class_list():
    """Existing Dataset_Full/classes.txt wins (keeps old label ids valid), else data.yaml."""
    if CLASSES_FILE.exists():
        base = [l.strip() for l in CLASSES_FILE.read_text(encoding="utf-8").splitlines() if l.strip()]
    else:
        base = load_class_names()
    return all_class_names(base=base)


class Canvas(QWidget):
    """Image view where boxes are drawn, selected, moved and resized.

    Boxes are [class_id, x1, y1, x2, y2] in image pixels.
    """
    boxes_changed = pyqtSignal()
    selection_changed = pyqtSignal(int)

    HANDLE = 6

    def __init__(self):
        super().__init__()
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMinimumSize(500, 400)
        self.img = None
        self.boxes = []
        self.sel = -1
        self.active_cls = 0
        self.class_names = []
        self.zoom = 1.0
        self.pan = QPointF(0, 0)
        self.mode = None
        self.mouse = None
        self.undo_stack = []

    # ---------- public API ----------
    def set_image(self, qimage, boxes):
        self.img = qimage
        self.boxes = boxes
        self.sel = -1
        self.zoom = 1.0
        self.pan = QPointF(0, 0)
        self.undo_stack = []
        self.selection_changed.emit(-1)
        self.update()

    def select(self, idx):
        self.sel = idx if 0 <= idx < len(self.boxes) else -1
        self.update()

    def snapshot(self):
        self.undo_stack.append(copy.deepcopy(self.boxes))
        del self.undo_stack[:-50]

    def undo(self):
        if self.undo_stack:
            self.boxes[:] = self.undo_stack.pop()
            self.sel = -1
            self.selection_changed.emit(-1)
            self.boxes_changed.emit()
            self.update()

    def delete_selected(self):
        if self.sel >= 0:
            self.snapshot()
            del self.boxes[self.sel]
            self.sel = -1
            self.selection_changed.emit(-1)
            self.boxes_changed.emit()
            self.update()

    def set_selected_class(self, cls):
        if self.sel >= 0 and self.boxes[self.sel][0] != cls:
            self.snapshot()
            self.boxes[self.sel][0] = cls
            self.boxes_changed.emit()
            self.update()

    def add_boxes(self, new_boxes):
        if new_boxes:
            self.snapshot()
            self.boxes.extend(new_boxes)
            self.boxes_changed.emit()
            self.update()

    def reset_view(self):
        self.zoom = 1.0
        self.pan = QPointF(0, 0)
        self.update()

    # ---------- coordinates ----------
    def _geometry(self):
        iw, ih = self.img.width(), self.img.height()
        scale = min(self.width() / iw, self.height() / ih) * self.zoom
        ox = (self.width() - iw * scale) / 2 + self.pan.x()
        oy = (self.height() - ih * scale) / 2 + self.pan.y()
        return scale, ox, oy

    def to_img(self, p, clamp=True):
        s, ox, oy = self._geometry()
        x, y = (p.x() - ox) / s, (p.y() - oy) / s
        if clamp:
            x = min(max(x, 0.0), float(self.img.width()))
            y = min(max(y, 0.0), float(self.img.height()))
        return x, y

    def to_widget(self, x, y):
        s, ox, oy = self._geometry()
        return QPointF(ox + x * s, oy + y * s)

    def _box_rect(self, b):
        return QRectF(self.to_widget(b[1], b[2]), self.to_widget(b[3], b[4]))

    def _corners(self, b):
        r = self._box_rect(b)
        return [r.topLeft(), r.topRight(), r.bottomRight(), r.bottomLeft()]

    def _hit_handle(self, pos):
        if self.sel < 0:
            return -1
        for i, c in enumerate(self._corners(self.boxes[self.sel])):
            if abs(c.x() - pos.x()) <= self.HANDLE + 2 and abs(c.y() - pos.y()) <= self.HANDLE + 2:
                return i
        return -1

    def _hit_box(self, pos):
        x, y = self.to_img(pos, clamp=False)
        best, best_area = -1, None
        for i, b in enumerate(self.boxes):
            if b[1] <= x <= b[3] and b[2] <= y <= b[4]:
                area = (b[3] - b[1]) * (b[4] - b[2])
                if best_area is None or area < best_area:
                    best, best_area = i, area
        return best

    # ---------- mouse ----------
    def mousePressEvent(self, e):
        if self.img is None:
            return
        self.setFocus()
        pos = e.position()
        if e.button() in (Qt.MouseButton.RightButton, Qt.MouseButton.MiddleButton):
            self.mode = "pan"
            self.last = pos
            return
        if e.button() != Qt.MouseButton.LeftButton:
            return
        corner = self._hit_handle(pos)
        idx = self._hit_box(pos) if corner < 0 else self.sel
        if corner >= 0:
            self.snapshot()
            self.mode, self.corner = "resize", corner
        elif idx >= 0:
            self.snapshot()
            self.mode = "move"
            self.sel = idx
            self.drag_start = self.to_img(pos, clamp=False)
            self.orig_box = list(self.boxes[idx])
            self.selection_changed.emit(idx)
        else:
            self.mode = "draw"
            self.drag_start = self.to_img(pos)
            self.draw_end = self.drag_start
            if self.sel >= 0:
                self.sel = -1
                self.selection_changed.emit(-1)
        self.update()

    def mouseMoveEvent(self, e):
        pos = e.position()
        self.mouse = pos
        if self.img is None:
            return
        if self.mode == "pan":
            self.pan += pos - self.last
            self.last = pos
        elif self.mode == "draw":
            self.draw_end = self.to_img(pos)
        elif self.mode == "move":
            x, y = self.to_img(pos, clamp=False)
            dx, dy = x - self.drag_start[0], y - self.drag_start[1]
            c, x1, y1, x2, y2 = self.orig_box
            dx = min(max(dx, -x1), self.img.width() - x2)      # keep inside the image
            dy = min(max(dy, -y1), self.img.height() - y2)
            self.boxes[self.sel] = [c, x1 + dx, y1 + dy, x2 + dx, y2 + dy]
        elif self.mode == "resize":
            x, y = self.to_img(pos)
            b = self.boxes[self.sel]
            if self.corner in (0, 3):
                b[1] = x
            else:
                b[3] = x
            if self.corner in (0, 1):
                b[2] = y
            else:
                b[4] = y
        else:
            if self._hit_handle(pos) >= 0:
                self.setCursor(Qt.CursorShape.SizeFDiagCursor)
            elif self._hit_box(pos) >= 0:
                self.setCursor(Qt.CursorShape.SizeAllCursor)
            else:
                self.setCursor(Qt.CursorShape.CrossCursor)
        self.update()

    def mouseReleaseEvent(self, e):
        if self.img is None or self.mode is None:
            return
        mode, self.mode = self.mode, None
        if mode == "draw":
            (x1, y1), (x2, y2) = self.drag_start, self.draw_end
            x1, x2 = sorted((x1, x2))
            y1, y2 = sorted((y1, y2))
            if x2 - x1 >= MIN_BOX and y2 - y1 >= MIN_BOX:
                self.snapshot()
                self.boxes.append([self.active_cls, x1, y1, x2, y2])
                self.boxes_changed.emit()
        elif mode in ("move", "resize"):
            b = self.boxes[self.sel]
            b[1], b[3] = sorted((b[1], b[3]))
            b[2], b[4] = sorted((b[2], b[4]))
            if self.undo_stack and self.undo_stack[-1] == self.boxes:
                self.undo_stack.pop()       # just a click, nothing changed
            else:
                self.boxes_changed.emit()
        self.update()

    def wheelEvent(self, e):
        if self.img is None:
            return
        pos = e.position()
        ix, iy = self.to_img(pos, clamp=False)
        factor = 1.15 ** (e.angleDelta().y() / 120)
        self.zoom = min(max(self.zoom * factor, 1.0), 20.0)
        # keep the image point under the cursor fixed
        iw, ih = self.img.width(), self.img.height()
        s = min(self.width() / iw, self.height() / ih) * self.zoom
        self.pan = QPointF(pos.x() - ix * s - (self.width() - iw * s) / 2,
                           pos.y() - iy * s - (self.height() - ih * s) / 2)
        if self.zoom == 1.0:
            self.pan = QPointF(0, 0)
        self.update()

    def leaveEvent(self, _):
        self.mouse = None
        self.update()

    # ---------- painting ----------
    def _name(self, cls):
        return self.class_names[cls] if 0 <= cls < len(self.class_names) else f"class_{cls}"

    def paintEvent(self, _):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor("#2b2b2b"))
        if self.img is None:
            p.setPen(QColor("#bbb"))
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter,
                       "No images.\nCapture some with capture_tool.py, or use 'Open folder…'.")
            return
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        s, ox, oy = self._geometry()
        p.drawImage(QRectF(ox, oy, self.img.width() * s, self.img.height() * s), self.img)

        font = QFont()
        font.setPointSize(9)
        font.setBold(True)
        p.setFont(font)
        fm = p.fontMetrics()

        for i, b in enumerate(self.boxes):
            color = class_color(b[0])
            r = self._box_rect(b)
            selected = i == self.sel
            if selected:
                fill = QColor(color)
                fill.setAlpha(60)
                p.fillRect(r, fill)
            p.setPen(QPen(color, 3 if selected else 2))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRect(r)

            text = self._name(b[0])
            tw, th = fm.horizontalAdvance(text) + 8, fm.height() + 2
            ty = r.top() - th if r.top() - th >= 0 else r.top()
            p.fillRect(QRectF(r.left(), ty, tw, th), color)
            p.setPen(QColor("white"))
            p.drawText(QRectF(r.left() + 4, ty, tw, th), Qt.AlignmentFlag.AlignVCenter, text)

            if selected:
                p.setPen(QPen(QColor("white"), 1))
                p.setBrush(QBrush(color))
                for c in self._corners(b):
                    p.drawRect(QRectF(c.x() - self.HANDLE, c.y() - self.HANDLE,
                                      2 * self.HANDLE, 2 * self.HANDLE))

        active = class_color(self.active_cls)
        if self.mode == "draw":
            (x1, y1), (x2, y2) = self.drag_start, self.draw_end
            p.setPen(QPen(active, 2, Qt.PenStyle.DashLine))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRect(QRectF(self.to_widget(x1, y1), self.to_widget(x2, y2)))

        # Crosshair guide lines while hovering / drawing
        if self.mouse is not None and self.mode in (None, "draw"):
            pen = QPen(active, 1, Qt.PenStyle.DashLine)
            p.setPen(pen)
            p.drawLine(QPointF(0, self.mouse.y()), QPointF(self.width(), self.mouse.y()))
            p.drawLine(QPointF(self.mouse.x(), 0), QPointF(self.mouse.x(), self.height()))
            p.setPen(QColor("white"))
            p.drawText(self.mouse + QPointF(10, -8), self._name(self.active_cls))
        p.end()


class LabelWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("StudyBuddy – Box Labelling (offline Label Studio)")
        self.resize(1400, 850)

        self.class_names = load_class_list()
        self.images = []          # list[Path]
        self.idx = -1
        self.frame = None         # current image (BGR ndarray), for pre-labelling
        self.dirty = False
        self.detector = None
        LABELS_DIR.mkdir(parents=True, exist_ok=True)
        IMAGES_DIR.mkdir(parents=True, exist_ok=True)

        # ---- left: image list ----
        self.file_list = QListWidget()
        self.file_list.currentRowChanged.connect(self._row_changed)
        self.unlabelled_only = QCheckBox("Show unlabelled only")
        self.unlabelled_only.toggled.connect(self._refresh_list_visibility)
        open_btn = QPushButton("Open folder…")
        open_btn.clicked.connect(self.open_folder)
        left = QWidget()
        lv = QVBoxLayout(left)
        lv.setContentsMargins(0, 0, 0, 0)
        lv.addWidget(QLabel("<b>Images</b>"))
        lv.addWidget(self.file_list, 1)
        lv.addWidget(self.unlabelled_only)
        lv.addWidget(open_btn)

        # ---- centre: canvas ----
        self.canvas = Canvas()
        self.canvas.class_names = self.class_names
        self.canvas.boxes_changed.connect(self._boxes_changed)
        self.canvas.selection_changed.connect(self._canvas_selection)

        # ---- right: classes, boxes, actions ----
        right = QWidget()
        rv = QVBoxLayout(right)
        rv.setContentsMargins(0, 0, 0, 0)
        rv.addWidget(QLabel("<b>Classes</b> (keys 1–9)"))
        self.class_group = QButtonGroup(self)
        for i, name in enumerate(self.class_names):
            rb = QRadioButton(f"{i + 1}. {name}")
            rb.setStyleSheet(f"QRadioButton {{ color: {class_color(i).name()}; font-weight: bold; }}")
            rb.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            self.class_group.addButton(rb, i)
            rv.addWidget(rb)
        self.class_group.idClicked.connect(self.set_active_class)

        rv.addSpacing(10)
        rv.addWidget(QLabel("<b>Boxes on this image</b>"))
        self.box_list = QListWidget()
        self.box_list.currentRowChanged.connect(self._box_list_selection)
        rv.addWidget(self.box_list, 1)
        del_btn = QPushButton("Delete box (Del)")
        del_btn.clicked.connect(self.canvas.delete_selected)
        rv.addWidget(del_btn)

        self.background_chk = QCheckBox("Background image (no objects) (B)")
        self.background_chk.setToolTip("Saves an empty label file: a negative example for training.")
        self.background_chk.toggled.connect(self._background_toggled)
        rv.addWidget(self.background_chk)

        rv.addSpacing(10)
        self.prelabel_btn = QPushButton("Pre-label with model (P)")
        self.prelabel_btn.setToolTip(f"Runs {YOLO_MODEL_PATH} on this image and adds its boxes to correct.")
        self.prelabel_btn.clicked.connect(self.prelabel)
        self.prelabel_btn.setEnabled(os.path.exists(YOLO_MODEL_PATH))
        rv.addWidget(self.prelabel_btn)
        self.auto_prelabel = QCheckBox("Auto pre-label unlabelled images")
        self.auto_prelabel.setEnabled(os.path.exists(YOLO_MODEL_PATH))
        rv.addWidget(self.auto_prelabel)

        nav = QHBoxLayout()
        prev_btn = QPushButton("◀ Prev (A)")
        prev_btn.clicked.connect(lambda: self.step(-1))
        next_btn = QPushButton("Next (D) ▶")
        next_btn.clicked.connect(lambda: self.step(1))
        nav.addWidget(prev_btn)
        nav.addWidget(next_btn)
        rv.addLayout(nav)
        save_btn = QPushButton("Save (Ctrl+S)")
        save_btn.clicked.connect(self.save_current)
        rv.addWidget(save_btn)

        help_lbl = QLabel(
            "Drag on the image to draw a box.\n"
            "Click a box to select; drag to move;\ndrag a corner to resize.\n"
            "With a box selected, 1–9 changes its class.\n"
            "Wheel = zoom, right-drag = pan, F = fit.\n"
            "Esc = deselect, Ctrl+Z = undo.\n"
            "Saves automatically when you change image.")
        help_lbl.setStyleSheet("color: #666;")
        rv.addWidget(help_lbl)
        for w in right.findChildren(QPushButton) + left.findChildren(QPushButton):
            w.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        splitter = QSplitter()
        splitter.addWidget(left)
        splitter.addWidget(self.canvas)
        splitter.addWidget(right)
        splitter.setSizes([260, 900, 240])
        splitter.setStretchFactor(1, 1)
        self.setCentralWidget(splitter)

        self._shortcuts()
        self.set_active_class(0)
        self.load_images([Path(CAPTURE_DIR), IMAGES_DIR])

    # ---------- setup ----------
    def _shortcuts(self):
        def sc(keys, fn):
            for k in keys:
                QShortcut(QKeySequence(k), self, activated=fn)
        sc(["D", "Right"], lambda: self.step(1))
        sc(["A", "Left"], lambda: self.step(-1))
        sc(["Delete", "Backspace"], self.canvas.delete_selected)
        sc(["Ctrl+Z"], self.canvas.undo)
        sc(["Ctrl+S"], self.save_current)
        sc(["Escape"], lambda: (self.canvas.select(-1), self._canvas_selection(-1)))
        sc(["F"], self.canvas.reset_view)
        sc(["B"], self.background_chk.toggle)
        sc(["P"], self.prelabel)
        for i in range(min(9, len(self.class_names))):
            sc([str(i + 1)], lambda i=i: self._class_key(i))

    def load_images(self, folders):
        """Collect images from folders (one level of class subfolders), de-duplicated by file name."""
        seen = {p.name for p in self.images}
        for folder in folders:
            if not folder.exists():
                continue
            candidates = [p for p in folder.rglob("*") if p.is_file() and p.suffix.lower() in IMG_EXTS]
            for path in sorted(candidates):
                if path.name not in seen:
                    seen.add(path.name)
                    self.images.append(path)
        self.file_list.blockSignals(True)
        self.file_list.clear()
        for path in self.images:
            self.file_list.addItem(QListWidgetItem())
        for i in range(len(self.images)):
            self._update_list_item(i)
        self.file_list.blockSignals(False)
        self._refresh_list_visibility()
        if self.idx < 0 and self.images:
            self.file_list.setCurrentRow(0)
        self._update_status()

    def open_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Add images from folder")
        if folder:
            self.load_images([Path(folder)])

    # ---------- list ----------
    def _is_labelled(self, path):
        return label_path_for(path).exists()

    def _update_list_item(self, i):
        path = self.images[i]
        item = self.file_list.item(i)
        mark = "✓" if self._is_labelled(path) else "·"
        item.setText(f"{mark} {path.parent.name}/{path.name}")
        item.setForeground(QColor("#2e7d32") if mark == "✓" else QColor("#333"))

    def _refresh_list_visibility(self):
        only = self.unlabelled_only.isChecked()
        for i, path in enumerate(self.images):
            self.file_list.item(i).setHidden(only and self._is_labelled(path) and i != self.idx)

    def _row_changed(self, row):
        if row != self.idx and 0 <= row < len(self.images):
            self.open_image(row)

    def step(self, delta):
        i = self.idx + delta
        while 0 <= i < len(self.images) and self.file_list.item(i).isHidden():
            i += delta
        if 0 <= i < len(self.images):
            self.file_list.setCurrentRow(i)

    # ---------- load / save ----------
    def open_image(self, i):
        self.save_current()
        frame = read_image(self.images[i])
        if frame is None:
            QMessageBox.warning(self, "Open image", f"Could not read {self.images[i]}")
            return
        self.idx = i
        self.frame = frame
        h, w = frame.shape[:2]
        boxes, background = self._read_label(self.images[i], w, h)
        self.canvas.set_image(cv_to_qimage(frame), boxes)
        self.background_chk.blockSignals(True)
        self.background_chk.setChecked(background)
        self.background_chk.blockSignals(False)
        self.dirty = False

        # Default class = the capture folder the image came from (captured/Sleeping/... -> Sleeping)
        folder = self.images[i].parent.name
        if folder in self.class_names:
            self.set_active_class(self.class_names.index(folder))

        self._refresh_box_list()
        self._update_status()
        if self.auto_prelabel.isChecked() and not self._is_labelled(self.images[i]):
            self.prelabel()

    def _read_label(self, image_path, w, h):
        lbl = label_path_for(image_path)
        if not lbl.exists():
            return [], False
        boxes = []
        for line in lbl.read_text(encoding="utf-8").splitlines():
            parts = line.split()
            if len(parts) != 5:
                continue
            cls = int(float(parts[0]))
            cx, cy, bw, bh = (float(v) for v in parts[1:])
            boxes.append([cls, (cx - bw / 2) * w, (cy - bh / 2) * h, (cx + bw / 2) * w, (cy + bh / 2) * h])
            while cls >= len(self.class_names):
                self.class_names.append(f"class_{len(self.class_names)}")
        return boxes, not boxes

    def save_current(self):
        if self.idx < 0 or not self.dirty:
            return
        src = self.images[self.idx]
        dst = IMAGES_DIR / src.name
        lbl = label_path_for(src)
        h, w = self.frame.shape[:2]
        boxes = self.canvas.boxes

        if boxes or self.background_chk.isChecked():
            if not dst.exists():
                shutil.copy2(src, dst)
            lines = []
            for cls, x1, y1, x2, y2 in boxes:
                lines.append(f"{cls} {(x1 + x2) / 2 / w:.6f} {(y1 + y2) / 2 / h:.6f} "
                             f"{(x2 - x1) / w:.6f} {(y2 - y1) / h:.6f}")
            lbl.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
            CLASSES_FILE.write_text("\n".join(self.class_names) + "\n", encoding="utf-8")
        else:
            # No boxes any more: un-export it (but never delete an original that lives in Dataset_Full)
            if lbl.exists():
                lbl.unlink()
            if dst.exists() and dst.resolve() != src.resolve():
                dst.unlink()

        self.dirty = False
        self._update_list_item(self.idx)
        self._update_status()
        self.statusBar().showMessage(f"Saved {lbl.name}", 2000)

    # ---------- classes / boxes ----------
    def set_active_class(self, i):
        self.canvas.active_cls = i
        btn = self.class_group.button(i)
        if btn:
            btn.setChecked(True)
        self.canvas.update()

    def _class_key(self, i):
        self.set_active_class(i)
        self.canvas.set_selected_class(i)

    def _boxes_changed(self):
        self.dirty = True
        if self.canvas.boxes and self.background_chk.isChecked():
            self.background_chk.blockSignals(True)
            self.background_chk.setChecked(False)
            self.background_chk.blockSignals(False)
        self._refresh_box_list()

    def _background_toggled(self, checked):
        if checked and self.canvas.boxes:
            answer = QMessageBox.question(self, "Background image",
                                          "Remove all boxes and mark this image as background?")
            if answer != QMessageBox.StandardButton.Yes:
                self.background_chk.blockSignals(True)
                self.background_chk.setChecked(False)
                self.background_chk.blockSignals(False)
                return
            self.canvas.snapshot()
            self.canvas.boxes.clear()
            self.canvas.select(-1)
            self._refresh_box_list()
        self.dirty = True

    def _refresh_box_list(self):
        self.box_list.blockSignals(True)
        self.box_list.clear()
        for cls, x1, y1, x2, y2 in self.canvas.boxes:
            name = self.class_names[cls] if cls < len(self.class_names) else f"class_{cls}"
            item = QListWidgetItem(f"{name}   {int(x2 - x1)}×{int(y2 - y1)} at ({int(x1)}, {int(y1)})")
            item.setForeground(class_color(cls))
            self.box_list.addItem(item)
        self.box_list.setCurrentRow(self.canvas.sel)
        self.box_list.blockSignals(False)

    def _canvas_selection(self, idx):
        self.box_list.blockSignals(True)
        self.box_list.setCurrentRow(idx)
        self.box_list.blockSignals(False)
        if idx >= 0:
            self.set_active_class(self.canvas.boxes[idx][0])

    def _box_list_selection(self, row):
        self.canvas.select(row)
        if row >= 0:
            self.set_active_class(self.canvas.boxes[row][0])
        self.canvas.setFocus()

    # ---------- model pre-labelling (like Label Studio's ML backend, but offline) ----------
    def prelabel(self):
        if self.frame is None or not os.path.exists(YOLO_MODEL_PATH):
            return
        QApplication.setOverrideCursor(QCursor(Qt.CursorShape.WaitCursor))
        try:
            if self.detector is None:
                self.statusBar().showMessage("Loading YOLO model…")
                QApplication.processEvents()
                from detection import Detector
                self.detector = Detector(YOLO_MODEL_PATH)
            det = self.detector
            result = det.model.predict(source=self.frame, conf=det.conf, device=det.device, verbose=False)[0]
            lookup = {n.lower(): i for i, n in enumerate(self.class_names)}
            new = []
            for (x1, y1, x2, y2), c in zip(result.boxes.xyxy.cpu().numpy(), result.boxes.cls.cpu().numpy()):
                cls = lookup.get(str(det.labels[int(c)]).lower())
                if cls is None:
                    continue
                box = [cls, float(x1), float(y1), float(x2), float(y2)]
                if not any(b[0] == cls and _iou(b, box) > 0.7 for b in self.canvas.boxes):
                    new.append(box)
            self.canvas.add_boxes(new)
            self.statusBar().showMessage(f"Model suggested {len(new)} box(es) – check and fix them.", 4000)
        except Exception as e:
            QMessageBox.warning(self, "Pre-label", f"Model could not run:\n{e}")
        finally:
            QApplication.restoreOverrideCursor()

    # ---------- status / close ----------
    def _update_status(self):
        done = sum(1 for p in self.images if self._is_labelled(p))
        cur = f"Image {self.idx + 1}/{len(self.images)}" if self.idx >= 0 else "No image"
        size = f"   {self.frame.shape[1]}×{self.frame.shape[0]}" if self.frame is not None else ""
        self.statusBar().showMessage(f"{cur}{size}    Labelled: {done}/{len(self.images)}    "
                                     f"Output: {DATASET_FULL_DIR}")

    def closeEvent(self, e):
        self.save_current()
        super().closeEvent(e)


def _iou(a, b):
    ix = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    iy = max(0.0, min(a[4], b[4]) - max(a[2], b[2]))
    inter = ix * iy
    union = (a[3] - a[1]) * (a[4] - a[2]) + (b[3] - b[1]) * (b[4] - b[2]) - inter
    return inter / union if union > 0 else 0.0


if __name__ == "__main__":
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    app = QApplication(sys.argv)
    w = LabelWindow()
    w.show()
    sys.exit(app.exec())
