"""Download the AI models while the laptop still has internet, then benchmark them.

Joining the car's "VisionPilot" Wi-Fi removes internet access, so run this first:
    .venv\\Scripts\\python tools\\prefetch_models.py
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np  # noqa: E402

from visionpilot.config import load_settings  # noqa: E402
from visionpilot.perception.depth_model import DepthModel  # noqa: E402
from visionpilot.perception.detector import Detector  # noqa: E402

RUNS = 20


def bench(name: str, fn, frame: np.ndarray) -> None:
    fn(frame)  # warm-up (CUDA kernels, cuDNN autotune)
    started = time.perf_counter()
    for _ in range(RUNS):
        fn(frame)
    ms = (time.perf_counter() - started) / RUNS * 1000
    print(f"{name:<8} {ms:6.1f} ms/frame  (~{1000 / ms:4.0f} fps)")


def main() -> None:
    v = load_settings().vision
    frame = np.random.default_rng(0).integers(0, 255, (360, 640, 3), dtype=np.uint8)
    print("Downloading / loading YOLO...")
    detector = Detector(v.yolo_model, v.model_dir, v.yolo_conf, v.yolo_imgsz)
    print("Downloading / loading Depth-Anything-V2-Small...")
    depth = DepthModel(v.depth_model, v.depth_size)
    print("\nBenchmark on this GPU:")
    bench("YOLO", detector.detect, frame)
    bench("depth", depth.estimate, frame)
    print("\nModels cached - you can now join the VisionPilot Wi-Fi.")


if __name__ == "__main__":
    main()
