"""QualityEvaluator — scores generated images using CLIP alignment + sharpness.
LLaVA evaluator — describes the image and checks prompt alignment.

Metrics (from DESIGN.md / Evaluation.md):
* CLIP alignment  – cosine similarity between prompt & image embeddings
  → drives steps / CFG adjustments in the adaptive loop
* Sharpness       – Laplacian variance via OpenCV
* LLaVA alignment – VLM describes the image; semantic match against prompt
  → drives prompt-level feedback (future: auto-rewrite prompt)
* Face detection   – Mediapipe confidence (optional, weighted)

Combined score = w1*clip + w2*face + w3*sharpness  (normalised 0-1)
LLaVA alignment is reported separately for prompt feedback.
Scoring overhead target: <200 ms (CLIP+sharpness), LLaVA ~1-3 s
"""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING, Any, Optional, Tuple

import cv2
import numpy as np
from PIL import Image

if TYPE_CHECKING:  # pragma: no cover
    import torch
    from transformers import CLIPModel, CLIPProcessor

logger = logging.getLogger(__name__)

_CLIP_MODEL_ID = "openai/clip-vit-base-patch32"
_LLAVA_MODEL_ID = "llava-hf/llava-1.5-7b-hf"


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
        # LLaVA (loaded separately via load_llava())
        self._llava_model: Any = None
        self._llava_processor: Any = None

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

    # ---- LLaVA prompt-alignment evaluation ----------------------

    def load_llava(self) -> None:
        """Load the LLaVA VLM for image description & prompt alignment.

        Uses 4-bit quantisation to fit alongside SD 1.5 on a single GPU.
        Gracefully falls back if the model cannot be loaded.
        """
        if self._llava_model is not None:
            return

        self._resolve_device()

        logger.info("Loading LLaVA model (%s) for prompt alignment …", _LLAVA_MODEL_ID)
        try:
            import torch as _torch
            from transformers import (
                AutoProcessor,
                BitsAndBytesConfig,
                LlavaForConditionalGeneration,
            )

            bnb_config = BitsAndBytesConfig(
                load_in_4bit=True,
                bnb_4bit_compute_dtype=_torch.float16,
                bnb_4bit_quant_type="nf4",
            )

            self._llava_processor = AutoProcessor.from_pretrained(_LLAVA_MODEL_ID)
            self._llava_model = LlavaForConditionalGeneration.from_pretrained(
                _LLAVA_MODEL_ID,
                quantization_config=bnb_config,
                device_map={"": self._device},
                torch_dtype=_torch.float16,
            )
            self._llava_model.eval()
            logger.info("LLaVA model loaded (4-bit quantised).")
        except Exception as exc:
            logger.warning(
                "Could not load LLaVA model (%s). "
                "Prompt-alignment evaluation disabled.",
                exc,
            )
            self._llava_model = None
            self._llava_processor = None

    @property
    def llava_available(self) -> bool:
        """Return True if the LLaVA model is loaded and ready."""
        return self._llava_model is not None and self._llava_processor is not None

    def describe_image(self, image: Image.Image) -> str:
        """Use LLaVA to generate a natural-language description of the image.

        Returns an empty string if LLaVA is not loaded.
        """
        if not self.llava_available:
            return ""

        import torch as _torch

        prompt_text = (
            "USER: <image>\n"
            "Describe this image in detail. "
            "Focus on the main subject, style, colours, lighting, and composition.\n"
            "ASSISTANT:"
        )

        inputs = self._llava_processor(
            text=prompt_text,
            images=image,
            return_tensors="pt",
        ).to(self._llava_model.device)

        with _torch.no_grad():
            output_ids = self._llava_model.generate(
                **inputs,
                max_new_tokens=150,
                do_sample=False,
            )

        # Decode only the new tokens (skip the input prompt tokens)
        generated_ids = output_ids[0][inputs["input_ids"].shape[-1]:]
        description = self._llava_processor.decode(generated_ids, skip_special_tokens=True).strip()
        return description

    def prompt_alignment_score(
        self, prompt: str, image: Image.Image
    ) -> Tuple[float, str]:
        """Score how well the image matches the original prompt using LLaVA.

        Asks LLaVA to rate the match on a 1-10 scale and extracts the score.

        Returns
        -------
        (score, description) : tuple
            score ∈ [0, 1]  (normalised from 1-10).
            description : LLaVA's textual assessment.
            If LLaVA is unavailable, returns (0.0, "").
        """
        if not self.llava_available:
            return 0.0, ""

        import torch as _torch

        assessment_prompt = (
            "USER: <image>\n"
            f"The intended prompt for this image was: \"{prompt}\"\n"
            "On a scale of 1 to 10, how well does this image match the prompt? "
            "Give your rating as a single number first, then briefly explain why.\n"
            "ASSISTANT:"
        )

        inputs = self._llava_processor(
            text=assessment_prompt,
            images=image,
            return_tensors="pt",
        ).to(self._llava_model.device)

        with _torch.no_grad():
            output_ids = self._llava_model.generate(
                **inputs,
                max_new_tokens=200,
                do_sample=False,
            )

        generated_ids = output_ids[0][inputs["input_ids"].shape[-1]:]
        response = self._llava_processor.decode(generated_ids, skip_special_tokens=True).strip()

        # Extract numeric rating from the response
        score = self._parse_rating(response)
        return score, response

    @staticmethod
    def _parse_rating(text: str) -> float:
        """Extract a 1-10 rating from LLaVA's response, normalise to [0, 1]."""
        # Look for patterns like "8", "8/10", "8 out of 10"
        match = re.search(r"\b(\d{1,2})(?:\s*/\s*10|\s+out\s+of\s+10)?\b", text)
        if match:
            raw = int(match.group(1))
            raw = max(1, min(raw, 10))
            return (raw - 1) / 9.0  # map 1→0.0, 10→1.0
        return 0.5  # default if parsing fails
