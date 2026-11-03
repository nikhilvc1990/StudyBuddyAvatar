import os

import torch
from ultralytics import YOLO

# Run from the project folder so the relative "path: dataset" in data.yaml resolves
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
os.chdir(BASE_DIR)

# Auto-select best available device
if torch.cuda.is_available():
    device = 0                  # NVIDIA GPU
elif torch.backends.mps.is_available():
    device = "mps"              # Apple Silicon GPU
else:
    device = "cpu"              # Fallback

print(f"Using device: {device}")

# Load a pretrained YOLO26 nano model (change to yolo26s/m/l/x.pt for larger models)
model = YOLO("yolo26n.pt")

# Train
results = model.train(
    data="data.yaml",           # path to your data.yaml
    epochs=100,
    imgsz=640,
    batch=8,                    # reduced batch size for CPU/MPS
    name="yolo26n_custom",      # output folder name under runs/detect/
    patience=20,                # early stopping
    device=device,
)

print("Training complete!")
best = os.path.join(model.trainer.save_dir, "weights", "best.pt")
print(f"Best weights saved to: {best}")

# The app runs the ONNX copy (works with Windows Smart App Control on).
# imgsz=(480, 640) matches the webcam frames, so results equal the .pt model.
onnx = YOLO(best).export(format="onnx", imgsz=(480, 640), simplify=True)
print(f"ONNX model saved to: {onnx}")
print("Copy best.pt and best.onnx into vision_model/weights/ to use them in the app.")