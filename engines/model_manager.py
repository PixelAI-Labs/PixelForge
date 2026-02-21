"""ModelManager — loads Stable Diffusion 1.5 and exposes a generate() interface.

Constraints (from DESIGN.md / DRD):
* dtype = torch.float16 on CUDA (GPU-only, no CPU fallback)
* Load model once at startup (inside __init__)
* No model reloading during jobs
* Parameterised inference call
* Attention slicing + VAE slicing + xformers (if available)
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
    """Manage Stable Diffusion pipeline lifecycle and generation.

    The pipeline is loaded once during ``__init__`` (unless *auto_load* is
    ``False``, which is useful for unit-tests that should not require ML
    dependencies).
    """

    def __init__(
        self,
        model_id: str = _DEFAULT_MODEL_ID,
        device: Optional[str] = None,
        auto_load: bool = True,
    ) -> None:
        self._model_id = model_id
        self._explicit_device = device  # None means "resolve later"
        self._device: Optional[str] = device
        self._pipe: Any = None  # StableDiffusionPipeline at runtime

        if auto_load:
            self._resolve_device()
            self.load()

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
        """Load the pipeline once.  Subsequent calls are no-ops."""
        if self._pipe is not None:
            return

        self._resolve_device()

        import torch as _torch
        from diffusers import StableDiffusionPipeline

        logger.info("Loading model %s on %s …", self._model_id, self._device)

        dtype = _torch.float16
        self._pipe = StableDiffusionPipeline.from_pretrained(
            self._model_id,
            torch_dtype=dtype,
        )
        self._pipe = self._pipe.to(self._device)
        self._pipe.safety_checker = None  # offline system

        # --- memory optimisations ---
        self._pipe.enable_attention_slicing()
        logger.info("Attention slicing enabled.")

        self._pipe.enable_vae_slicing()
        logger.info("VAE slicing enabled.")

        try:
            self._pipe.enable_xformers_memory_efficient_attention()
            logger.info("xformers memory-efficient attention enabled.")
        except Exception:
            logger.info("xformers not available — skipping memory-efficient attention.")

        logger.info(
            "Model loaded  (device=%s, dtype=%s).",
            self._device,
            dtype,
        )

    @property
    def is_loaded(self) -> bool:
        return self._pipe is not None

    @property
    def device(self) -> str:
        """Expose device string so callers can issue CUDA cleanup."""
        return self._device

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
        """Generate a single image and return it as a PIL Image.

        Parameters
        ----------
        prompt : str
            Text prompt for generation.
        steps : int
            Number of denoising steps.
        guidance_scale : float
            Classifier-free guidance scale.
        seed : int | None
            Reproducibility seed.  A random seed is chosen when *None*.
        width, height : int
            Output resolution (must be multiples of 8).
        negative_prompt : str
            Negative prompt to steer away from undesired content.

        Returns
        -------
        PIL.Image.Image
        """
        if self._pipe is None:
            raise RuntimeError("Model not loaded — call load() first.")

        import torch as _torch

        if seed is None:
            seed = random.randint(0, 2**32 - 1)

        generator = _torch.Generator(device=self._device).manual_seed(seed)

        try:
            result = self._pipe(
                prompt=prompt,
                negative_prompt=negative_prompt or None,
                num_inference_steps=steps,
                guidance_scale=guidance_scale,
                width=width,
                height=height,
                generator=generator,
            )
        except RuntimeError as exc:
            if "out of memory" in str(exc).lower():
                logger.error(
                    "CUDA OOM during generation (steps=%d, %dx%d). "
                    "Clearing cache and re-raising.",
                    steps,
                    width,
                    height,
                )
                if self._device == "cuda":
                    _torch.cuda.empty_cache()
                raise
            raise

        image: Image.Image = result.images[0]
        return image
