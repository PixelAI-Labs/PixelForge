"""ModelManager — loads Stable Diffusion 1.5 and exposes a generate() interface.

Constraints (from DESIGN.md / DRD):
* dtype = torch.float16
* Load model once at startup
* No model reloading during jobs
* Parameterised inference call
"""

from __future__ import annotations

import logging
import random
from typing import TYPE_CHECKING, Any, Optional

from PIL import Image

if TYPE_CHECKING:  # pragma: no cover
    import torch
    from diffusers import StableDiffusionPipeline

logger = logging.getLogger(__name__)

_DEFAULT_MODEL_ID = "runwayml/stable-diffusion-v1-5"


class ModelManager:
    """Manage Stable Diffusion pipeline lifecycle and generation."""

    def __init__(
        self,
        model_id: str = _DEFAULT_MODEL_ID,
        device: Optional[str] = None,
    ) -> None:
        self._model_id = model_id
        if device is not None:
            self._device = device
        else:
            try:
                import torch as _torch
                self._device = "cuda" if _torch.cuda.is_available() else "cpu"
            except ImportError:
                self._device = "cpu"
        self._pipe: Any = None  # StableDiffusionPipeline at runtime

    # ---- lifecycle ----------------------------------------------

    def load(self) -> None:
        """Load the pipeline once.  Subsequent calls are no-ops."""
        if self._pipe is not None:
            return

        import torch as _torch
        from diffusers import StableDiffusionPipeline

        logger.info("Loading model %s on %s …", self._model_id, self._device)
        dtype = _torch.float16 if self._device == "cuda" else _torch.float32
        self._pipe = StableDiffusionPipeline.from_pretrained(
            self._model_id,
            torch_dtype=dtype,
        )
        self._pipe = self._pipe.to(self._device)
        self._pipe.safety_checker = None  # offline system
        logger.info("Model loaded.")

    @property
    def is_loaded(self) -> bool:
        return self._pipe is not None

    # ---- generation ---------------------------------------------

    def generate(
        self,
        prompt: str,
        steps: int = 30,
        guidance_scale: float = 7.5,
        seed: Optional[int] = None,
        width: int = 512,
        height: int = 512,
        negative_prompt: str = "",
    ) -> Image.Image:
        """Generate a single image and return it as a PIL Image."""
        if self._pipe is None:
            raise RuntimeError("Model not loaded — call load() first.")

        import torch as _torch

        if seed is None:
            seed = random.randint(0, 2**32 - 1)

        generator = _torch.Generator(device=self._device).manual_seed(seed)

        result = self._pipe(
            prompt=prompt,
            negative_prompt=negative_prompt or None,
            num_inference_steps=steps,
            guidance_scale=guidance_scale,
            width=width,
            height=height,
            generator=generator,
        )
        return result.images[0]
