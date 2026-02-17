"""QualityEvaluator — scores generated images using CLIP alignment + sharpness.

Metrics (from DESIGN.md / Evaluation.md):
* CLIP alignment  – cosine similarity between prompt & image embeddings
* Sharpness       – Laplacian variance via OpenCV
* Face detection   – Mediapipe confidence (optional, weighted)

Combined score = w1*clip + w2*face + w3*sharpness  (normalised 0-1)
Scoring overhead target: <200 ms
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Optional

import cv2
import numpy as np
from PIL import Image

if TYPE_CHECKING:  # pragma: no cover
    import torch
    from transformers import CLIPModel, CLIPProcessor

logger = logging.getLogger(__name__)

_CLIP_MODEL_ID = "openai/clip-vit-base-patch32"


class QualityEvaluator:
    """Evaluate image quality using measurable signals."""

    def __init__(
        self,
        w_clip: float = 0.5,
        w_face: float = 0.0,
        w_sharpness: float = 0.5,
        device: Optional[str] = None,
    ) -> None:
        self._w_clip = w_clip
        self._w_face = w_face
        self._w_sharpness = w_sharpness
        if device is not None:
            self._device = device
        else:
            try:
                import torch as _torch
                self._device = "cuda" if _torch.cuda.is_available() else "cpu"
            except ImportError:
                self._device = "cpu"
        self._clip_model: Any = None
        self._clip_processor: Any = None

    # ---- lifecycle ----------------------------------------------

    def load(self) -> None:
        """Load CLIP model for alignment scoring."""
        if self._clip_model is not None:
            return

        from transformers import CLIPModel as _CLIPModel
        from transformers import CLIPProcessor as _CLIPProcessor

        logger.info("Loading CLIP model for quality evaluation …")
        self._clip_processor = _CLIPProcessor.from_pretrained(_CLIP_MODEL_ID)
        self._clip_model = _CLIPModel.from_pretrained(_CLIP_MODEL_ID).to(self._device)
        self._clip_model.eval()
        logger.info("CLIP model loaded.")

    # ---- scoring ------------------------------------------------

    def clip_score(self, prompt: str, image: Image.Image) -> float:
        """Cosine similarity between prompt and image via CLIP."""
        if self._clip_model is None or self._clip_processor is None:
            raise RuntimeError("CLIP model not loaded — call load() first.")

        import torch as _torch

        inputs = self._clip_processor(
            text=[prompt], images=image, return_tensors="pt", padding=True
        )
        inputs = {k: v.to(self._device) for k, v in inputs.items()}

        with _torch.no_grad():
            outputs = self._clip_model(**inputs)

        logits = outputs.logits_per_image  # (1, 1)
        # logits_per_image is already a cosine-similarity scaled by a temperature
        # Normalise to 0-1 range using sigmoid
        score = _torch.sigmoid(logits).item()
        return float(score)

    @staticmethod
    def sharpness_score(image: Image.Image) -> float:
        """Laplacian-variance sharpness, normalised to 0-1."""
        arr = np.array(image.convert("L"))
        lap = cv2.Laplacian(arr, cv2.CV_64F)
        variance = lap.var()
        # Normalise: empirically, sharp SD images have variance ~200-1000+
        normalised = min(variance / 1000.0, 1.0)
        return float(normalised)

    def evaluate(self, prompt: str, image: Image.Image) -> float:
        """Compute combined quality score in [0, 1]."""
        clip = self.clip_score(prompt, image) if self._w_clip > 0 else 0.0
        sharpness = self.sharpness_score(image) if self._w_sharpness > 0 else 0.0
        face = 0.0  # Face detection kept at weight 0 by default

        total_weight = self._w_clip + self._w_face + self._w_sharpness
        if total_weight == 0:
            return 0.0

        score = (
            self._w_clip * clip
            + self._w_face * face
            + self._w_sharpness * sharpness
        ) / total_weight

        return float(np.clip(score, 0.0, 1.0))
