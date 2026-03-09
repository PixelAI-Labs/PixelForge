"""IterativeGenerator — session-based iterative image editing.

Provides three public methods:
* generate_initial(prompt)          — text-to-image first frame
* edit_image(image, prompt, edit)   — img2img refinement
* prompt_update(prompt, edit)       — merge an edit instruction into a base prompt
"""

from __future__ import annotations

import logging
from typing import Optional

from PIL import Image

from engines.model_manager import ModelManager
from engines.prompt_pipeline import PromptPipeline

logger = logging.getLogger(__name__)


class IterativeGenerator:
    """Wraps ModelManager to provide a stateless iterative editing API.

    Each call is standalone — session tracking is done by the API layer.
    """

    def __init__(
        self,
        model_manager: ModelManager,
        prompt_pipeline: Optional[PromptPipeline] = None,
    ) -> None:
        self._mm = model_manager
        self._pipeline = prompt_pipeline

    # ---- public API ---------------------------------------------

    def generate_initial(
        self,
        prompt: str,
        seed: Optional[int] = None,
        negative_prompt: str = "",
    ) -> Image.Image:
        """Create the first image in an editing session (txt2img)."""
        if self._pipeline is not None:
            logger.info("PromptPipeline | original prompt: %r", prompt)
            prompt, pipeline_neg = self._pipeline.process(prompt)
            if negative_prompt:
                negative_prompt = f"{negative_prompt}, {pipeline_neg}"
            else:
                negative_prompt = pipeline_neg
            logger.info("PromptPipeline | final prompt: %r  |  negative: %r", prompt, negative_prompt)
        return self._mm.generate(
            prompt=prompt,
            steps=30,
            guidance_scale=7.5,
            seed=seed,
            width=512,
            height=512,
            negative_prompt=negative_prompt,
        )

    def edit_image(
        self,
        image: Image.Image,
        original_prompt: str,
        edit_instruction: str,
        strength: float = 0.35,
        seed: Optional[int] = None,
        negative_prompt: str = "",
    ) -> Image.Image:
        """Apply an edit to an existing image via img2img.

        Parameters
        ----------
        image : PIL.Image.Image
            The source image to transform.
        original_prompt : str
            The prompt that produced *image*.
        edit_instruction : str
            Natural-language description of the desired change.
        strength : float
            Denoising strength (lower = subtler edit).
        seed : int | None
            Reproducibility seed.
        negative_prompt : str
            Negative prompt.
        """
        if self._pipeline is not None:
            merged = self._pipeline.merge_edit(original_prompt, edit_instruction)
            merged, pipeline_neg = self._pipeline.process(merged)
            if negative_prompt:
                negative_prompt = f"{negative_prompt}, {pipeline_neg}"
            else:
                negative_prompt = pipeline_neg
            logger.info("PromptPipeline | edit merged=%r  negative=%r", merged, negative_prompt)
        else:
            merged = self.prompt_update(original_prompt, edit_instruction)
        logger.info(
            "Iterative edit  merged=%r  strength=%.2f", merged, strength,
        )
        return self._mm.img2img(
            prompt=merged,
            image=image,
            strength=strength,
            steps=30,
            guidance_scale=7.0,
            seed=seed,
            negative_prompt=negative_prompt,
        )

    # ---- prompt merging -----------------------------------------

    @staticmethod
    def prompt_update(original_prompt: str, edit_instruction: str) -> str:
        """Merge an edit instruction into the original prompt.

        Strategy: append the edit as a refinement so the base scene
        description is preserved while adding the requested change.
        """
        base = original_prompt.rstrip(" ,.")
        edit = edit_instruction.strip()
        if not edit:
            return original_prompt
        return f"{base}, {edit}"
