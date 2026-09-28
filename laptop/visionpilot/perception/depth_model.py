"""Monocular relative depth with Depth-Anything-V2-Small (Hugging Face transformers)."""
from __future__ import annotations

import logging

import cv2
import numpy as np

log = logging.getLogger(__name__)

IMAGENET_MEAN = (0.485, 0.456, 0.406)
IMAGENET_STD = (0.229, 0.224, 0.225)


class DepthModel:
    def __init__(self, model_id: str, size: tuple[int, int]) -> None:
        import torch
        from transformers import AutoModelForDepthEstimation

        self._torch = torch
        cuda = torch.cuda.is_available()
        self._device = "cuda" if cuda else "cpu"
        self._dtype = torch.float16 if cuda else torch.float32
        self._model = AutoModelForDepthEstimation.from_pretrained(model_id, torch_dtype=self._dtype)
        self._model = self._model.to(self._device).eval()
        self._height, self._width = size
        self._mean = torch.tensor(IMAGENET_MEAN, device=self._device).view(1, 3, 1, 1)
        self._std = torch.tensor(IMAGENET_STD, device=self._device).view(1, 3, 1, 1)
        log.info("Depth model %s loaded on %s", model_id, self._device)

    def estimate(self, frame_bgr: np.ndarray) -> np.ndarray:
        """Relative disparity (bigger = closer), shape (h, w) of the model input size."""
        torch = self._torch
        rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        resized = cv2.resize(rgb, (self._width, self._height), interpolation=cv2.INTER_AREA)
        x = torch.from_numpy(resized).to(self._device).permute(2, 0, 1).unsqueeze(0).float() / 255.0
        x = ((x - self._mean) / self._std).to(self._dtype)
        with torch.inference_mode():
            depth = self._model(pixel_values=x).predicted_depth
        return depth[0].float().cpu().numpy()


def depth_colormap(disparity: np.ndarray, width: int, height: int) -> np.ndarray:
    """Pretty BGR visualisation for the dashboard inset."""
    top = float(np.percentile(disparity, 99)) or 1.0
    scaled = np.clip(disparity / top * 255, 0, 255).astype(np.uint8)
    return cv2.resize(cv2.applyColorMap(scaled, cv2.COLORMAP_INFERNO), (width, height))
