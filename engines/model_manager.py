"""ModelManager — loads Stable Diffusion 1.5 and exposes generate() + img2img() interfaces.

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
import threading
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
        self._img2img_pipe: Any = None  # StableDiffusionImg2ImgPipeline at runtime
        self._lock = threading.Lock()  # serialize inference (scheduler is not thread-safe)

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
        from diffusers import StableDiffusionImg2ImgPipeline, StableDiffusionPipeline

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

        # Build img2img pipeline sharing the same components
        self._img2img_pipe = StableDiffusionImg2ImgPipeline(
            vae=self._pipe.vae,
            text_encoder=self._pipe.text_encoder,
            tokenizer=self._pipe.tokenizer,
            unet=self._pipe.unet,
            scheduler=self._pipe.scheduler,
            safety_checker=None,
            feature_extractor=self._pipe.feature_extractor,
        )
        logger.info("Img2Img pipeline ready (shared weights).")

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

        with self._lock:
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

    def img2img(
        self,
        prompt: str,
        image: Image.Image,
        strength: float = 0.35,
        steps: int = 30,
        guidance_scale: float = 7.0,
        seed: Optional[int] = None,
        negative_prompt: str = "",
    ) -> Image.Image:
        """Run img2img on *image* with the given prompt.

        Parameters
        ----------
        prompt : str
            Text prompt describing the desired output.
        image : PIL.Image.Image
            The source image to transform.
        strength : float
            Denoising strength (0 = no change, 1 = full regeneration).
        steps : int
            Number of denoising steps.
        guidance_scale : float
            Classifier-free guidance scale.
        seed : int | None
            Reproducibility seed.
        negative_prompt : str
            Negative prompt.

        Returns
        -------
        PIL.Image.Image
        """
        if self._img2img_pipe is None:
            raise RuntimeError("Model not loaded — call load() first.")

        import torch as _torch

        if seed is None:
            seed = random.randint(0, 2**32 - 1)

        generator = _torch.Generator(device=self._device).manual_seed(seed)

        # Ensure image is RGB and matches expected size
        image = image.convert("RGB").resize((512, 512))

        with self._lock:
            try:
                result = self._img2img_pipe(
                    prompt=prompt,
                    image=image,
                    strength=strength,
                    num_inference_steps=steps,
                    guidance_scale=guidance_scale,
                    negative_prompt=negative_prompt or None,
                    generator=generator,
                )
            except RuntimeError as exc:
                if "out of memory" in str(exc).lower():
                    logger.error("CUDA OOM during img2img.")
                    if self._device == "cuda":
                        _torch.cuda.empty_cache()
                    raise
                raise

        return result.images[0]
