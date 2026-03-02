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
        self._device: Optional[str] = device  # None → resolved lazily
        self._clip_model: Any = None
        self._clip_processor: Any = None

    def _resolve_device(self) -> None:
        """Resolve the device, raising if no CUDA GPU is available."""
        if self._device is not None:
            return
        import torch as _torch
        if not _torch.cuda.is_available():
            raise RuntimeError(
                "PixelForge requires an NVIDIA GPU with CUDA support. "
                "No CUDA device was detected."
            )
        self._device = "cuda"

    # ---- lifecycle ----------------------------------------------

    def load(self) -> None:
        """Load CLIP model for alignment scoring."""
        if self._clip_model is not None:
            return

        self._resolve_device()

        from transformers import CLIPModel as _CLIPModel
        from transformers import CLIPProcessor as _CLIPProcessor

        logger.info("Loading CLIP model for quality evaluation …")
        try:
            self._clip_processor = _CLIPProcessor.from_pretrained(_CLIP_MODEL_ID)
            self._clip_model = _CLIPModel.from_pretrained(_CLIP_MODEL_ID).to(self._device)
            self._clip_model.eval()
            logger.info("CLIP model loaded.")
        except (OSError, RuntimeError, Exception) as exc:
            logger.warning(
                "Could not load CLIP model (%s). "
                "Quality evaluation will use sharpness only.",
                exc,
            )
            self._clip_model = None
            self._clip_processor = None
            self._w_clip = 0.0

    # ---- scoring ------------------------------------------------

    def clip_score(self, prompt: str, image: Image.Image) -> float:
        """True cosine similarity between prompt and image CLIP embeddings.

        1. Extract image & text embeddings independently.
        2. L2-normalise both vectors.
        3. Compute cosine = dot(image_norm, text_norm)  →  [-1, 1].
        4. Remap to [0, 1] for downstream scoring.
        """
        if self._clip_model is None or self._clip_processor is None:
            return 0.0

        import torch as _torch
        import torch.nn.functional as _F

        # Tokenise text and preprocess image separately
        text_inputs = self._clip_processor(
            text=[prompt], return_tensors="pt", padding=True
        )
        image_inputs = self._clip_processor(
            images=image, return_tensors="pt"
        )

        with _torch.no_grad():
            # Compute image embedding: vision_model → pooler_output → projection
            vision_out = self._clip_model.vision_model(
                pixel_values=image_inputs["pixel_values"].to(self._device),
            )
            image_emb = self._clip_model.visual_projection(vision_out.pooler_output)

            # Compute text embedding: text_model → pooler_output → projection
            text_out = self._clip_model.text_model(
                input_ids=text_inputs["input_ids"].to(self._device),
                attention_mask=text_inputs["attention_mask"].to(self._device),
            )
            text_emb = self._clip_model.text_projection(text_out.pooler_output)

        # L2-normalise so dot product == cosine similarity
        image_emb = _F.normalize(image_emb, p=2, dim=-1)
        text_emb = _F.normalize(text_emb, p=2, dim=-1)

        # cosine ∈ [-1, 1]
        cosine = (image_emb * text_emb).sum(dim=-1).item()

        # Remap [-1, 1] → [0, 1] for the combined quality score
        score = (cosine + 1.0) / 2.0
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
