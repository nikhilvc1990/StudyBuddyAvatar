"""Helpers shared by capture_tool.py and label_tool.py."""
import re
from pathlib import Path

import cv2
import numpy as np
from PyQt6.QtGui import QColor, QImage

from config import CAPTURE_DIR, DATA_YAML_PATH

IMG_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}   # same as DatasetTrainTestSplit.py
DEFAULT_CLASSES = ["Mobile", "Reading", "Sleeping"]

# One colour per class index (cycles if there are more classes)
CLASS_COLORS = ["#FF7043", "#42A5F5", "#AB47BC", "#66BB6A", "#FFCA28", "#26C6DA", "#EC407A", "#8D6E63"]


def class_color(idx):
    return QColor(CLASS_COLORS[idx % len(CLASS_COLORS)])


def load_class_names(yaml_path=DATA_YAML_PATH):
    """Read the `names:` block of data.yaml ("  0: Mobile" lines), in index order."""
    path = Path(yaml_path)
    if not path.exists():
        return list(DEFAULT_CLASSES)
    names = {}
    in_names = False
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip().startswith("names:"):
            in_names = True
            continue
        if in_names:
            m = re.match(r"\s+(\d+)\s*:\s*(.+?)\s*$", line)
            if m:
                names[int(m.group(1))] = m.group(2).strip("'\"")
            elif line.strip():
                break   # next top-level key
    return [names[i] for i in sorted(names)] or list(DEFAULT_CLASSES)


def all_class_names(capture_dir=CAPTURE_DIR, base=None):
    """`base` (default: data.yaml order) plus any extra class folders made in captured/."""
    names = list(base) if base else load_class_names()
    folder = Path(capture_dir)
    if folder.exists():
        for sub in sorted(p.name for p in folder.iterdir() if p.is_dir()):
            if sub not in names:
                names.append(sub)
    return names


def list_images(folder):
    folder = Path(folder)
    if not folder.exists():
        return []
    return sorted(p for p in folder.iterdir() if p.is_file() and p.suffix.lower() in IMG_EXTS)


def read_image(path):
    """cv2.imread that also works with non-ASCII Windows paths."""
    data = np.fromfile(str(path), dtype=np.uint8)
    return cv2.imdecode(data, cv2.IMREAD_COLOR) if data.size else None


def write_image(path, frame, quality=95):
    ok, buf = cv2.imencode(Path(path).suffix or ".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, quality])
    if ok:
        buf.tofile(str(path))
    return ok


def cv_to_qimage(frame):
    """BGR ndarray -> QImage (deep copy, safe to keep after the frame changes)."""
    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    h, w, ch = rgb.shape
    return QImage(rgb.data, w, h, ch * w, QImage.Format.Format_RGB888).copy()
