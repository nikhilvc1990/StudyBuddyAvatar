import random
import shutil
from pathlib import Path

# ---------- Settings ----------
PROJECT_DIR = Path(__file__).resolve().parent
SRC = PROJECT_DIR / "Dataset_Full"
DST = PROJECT_DIR / "dataset"
YAML_PATH = PROJECT_DIR / "data.yaml"

VAL_RATIO = 0.2               # 20% validation
TEST_RATIO = 0.0              # set e.g. 0.1 if you also want a test split
SEED = 42
IMG_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
# ------------------------------

random.seed(SEED)

images_dir = SRC / "images"
labels_dir = SRC / "labels"

# Sanity checks
assert images_dir.exists(), f"No 'images' folder found in {SRC.resolve()}"
assert labels_dir.exists(), f"No 'labels' folder found in {SRC.resolve()}"

# Collect images that have a matching label file
pairs = []
for img in sorted(images_dir.iterdir()):
    if img.suffix.lower() in IMG_EXTS:
        lbl = labels_dir / f"{img.stem}.txt"
        if lbl.exists():
            pairs.append((img, lbl))
        else:
            print(f"Skipping (no label): {img.name}")

random.shuffle(pairs)
n = len(pairs)
n_test = int(n * TEST_RATIO)
n_val = int(n * VAL_RATIO)

splits = {
    "test": pairs[:n_test],
    "val": pairs[n_test:n_test + n_val],
    "train": pairs[n_test + n_val:],
}

# Copy files into dataset/images/<split> and dataset/labels/<split>
for split, items in splits.items():
    if not items:
        continue
    (DST / "images" / split).mkdir(parents=True, exist_ok=True)
    (DST / "labels" / split).mkdir(parents=True, exist_ok=True)
    for img, lbl in items:
        shutil.copy2(img, DST / "images" / split / img.name)
        shutil.copy2(lbl, DST / "labels" / split / lbl.name)
    print(f"{split}: {len(items)} images")

# Build data.yaml from classes.txt
classes_file = SRC / "classes.txt"
assert classes_file.exists(), f"classes.txt not found in {SRC.resolve()}"
names = [line.strip() for line in classes_file.read_text().splitlines() if line.strip()]

yaml_lines = [
    f"path: {DST.relative_to(PROJECT_DIR).as_posix()}",   # relative: portable across machines
    "train: images/train",
    "val: images/val",
]
if splits["test"]:
    yaml_lines.append("test: images/test")
yaml_lines.append("")
yaml_lines.append("names:")
for i, name in enumerate(names):
    yaml_lines.append(f"  {i}: {name}")

YAML_PATH.write_text("\n".join(yaml_lines) + "\n")
print(f"Created {YAML_PATH}")