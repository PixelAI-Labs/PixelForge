"""AdaptiveSampler — feedback-driven regeneration loop.

Algorithm (from DESIGN.md / DRD):
1. Generate initial image
2. Evaluate quality (CLIP + sharpness → steps/CFG feedback)
3. If quality >= threshold → accept
4. Else:
   - Increase steps (+10, bounded to 100)
   - Multiply CFG by 1.1 (bounded to 20.0)
   - Change seed
   - Strengthen negative prompt
   - Regenerate
5. Repeat (max 10 attempts)
6. Return best result

Constraints:
* Max 10 attempts
* Small parameter deltas
* Log every attempt with full debug info
* Clear GPU memory after each attempt (CUDA)
* No direct diffusers interaction — only via ModelManager.generate()
"""

from __future__ import annotations

import logging
import random
import time
from dataclasses import dataclass, field
from typing import List, Optional

from PIL import Image

from core.models import AttemptRecord
from engines.model_manager import ModelManager
from engines.prompt_pipeline import PromptPipeline
from engines.quality_evaluator import QualityEvaluator

logger = logging.getLogger(__name__)

_DEFAULT_QUALITY_THRESHOLD = 0.80
_MAX_ATTEMPTS = 10
_MAX_STEPS = 100
_MAX_CFG = 20.0
_DEFAULT_NEGATIVE = "blurry, distorted, low quality, artifacts"


@dataclass
class SamplingResult:
    """Final result of the adaptive sampling loop."""

    best_image: Image.Image
    best_attempt: int
    attempts: List[AttemptRecord]
    images: List[Optional[Image.Image]] = field(default_factory=list)


def _clear_cuda_cache() -> None:
    """Release cached GPU memory if CUDA is available."""
    try:
        import torch as _torch
        if _torch.cuda.is_available():
            _torch.cuda.empty_cache()
    except ImportError:
        pass


class AdaptiveSampler:
    """Run the adaptive inference loop over ModelManager + QualityEvaluator.

    This class never imports or interacts with ``diffusers`` directly.
    All generation work is delegated to :class:`ModelManager`.
    """

    def __init__(
        self,
        model_manager: ModelManager,
        quality_evaluator: QualityEvaluator,
        quality_threshold: float = _DEFAULT_QUALITY_THRESHOLD,
        max_attempts: int = _MAX_ATTEMPTS,
        prompt_pipeline: Optional[PromptPipeline] = None,
    ) -> None:
        self._mm = model_manager
        self._qe = quality_evaluator
        self._threshold = quality_threshold
        self._max_attempts = max_attempts
        self._pipeline = prompt_pipeline

    # ---- adaptive loop ------------------------------------------

    def run(
        self,
        prompt: str,
        seed: Optional[int] = None,
        steps: int = 30,
        guidance_scale: float = 7.5,
        width: int = 512,
        height: int = 512,
        negative_prompt: str = "",
    ) -> SamplingResult:
        """Execute the adaptive sampling loop and return the best result."""

        # ---- prompt preprocessing pipeline ----
        if self._pipeline is not None:
            logger.info("PromptPipeline | original prompt: %r", prompt)
            enhanced_prompt, pipeline_negative = self._pipeline.process(prompt)
            prompt = enhanced_prompt
            # Merge pipeline negative with any user-supplied negative prompt
            if negative_prompt:
                negative_prompt = f"{negative_prompt}, {pipeline_negative}"
            else:
                negative_prompt = pipeline_negative
            logger.info(
                "PromptPipeline | final prompt: %r  |  negative: %r",
                prompt,
                negative_prompt,
            )

        best_image: Optional[Image.Image] = None
        best_score: float = -1.0
        best_idx: int = 0
        records: List[AttemptRecord] = []
        all_images: List[Image.Image] = []

        current_seed = seed if seed is not None else random.randint(0, 2**32 - 1)
        current_steps = steps
        current_cfg = guidance_scale
        current_neg = negative_prompt or _DEFAULT_NEGATIVE

        for attempt in range(1, self._max_attempts + 1):
            logger.info(
                "--- Attempt %d/%d ---  seed=%d  steps=%d  cfg=%.2f",
                attempt,
                self._max_attempts,
                current_seed,
                current_steps,
                current_cfg,
            )

            t0 = time.time()
            try:
                image = self._mm.generate(
                    prompt=prompt,
                    steps=current_steps,
                    guidance_scale=current_cfg,
                    seed=current_seed,
                    width=width,
                    height=height,
                    negative_prompt=current_neg,
                )
            except RuntimeError as exc:
                gen_time = time.time() - t0
                if "out of memory" in str(exc).lower():
                    logger.warning(
                        "Attempt %d hit CUDA OOM after %.2fs — clearing cache and continuing.",
                        attempt,
                        gen_time,
                    )
                    _clear_cuda_cache()
                    # Record a failed attempt with score 0
                    records.append(
                        AttemptRecord(
                            attempt_number=attempt,
                            seed=current_seed,
                            steps=current_steps,
                            guidance_scale=current_cfg,
                            width=width,
                            height=height,
                            quality_score=0.0,
                            generation_time=gen_time,
                        )
                    )
                    all_images.append(None)  # placeholder for failed attempt
                    # Reduce steps on next attempt to lower memory pressure
                    current_steps = max(current_steps - 5, 20)
                    current_seed = random.randint(0, 2**32 - 1)
                    continue
                raise  # non-OOM RuntimeErrors propagate

            gen_time = time.time() - t0

            score = self._qe.evaluate(prompt, image)

            # ---- debug logging per attempt ----
            logger.info(
                "Attempt %d  |  score=%.4f  |  threshold=%.2f  |  "
                "steps=%d  |  cfg=%.2f  |  seed=%d  |  time=%.2fs",
                attempt,
                score,
                self._threshold,
                current_steps,
                current_cfg,
                current_seed,
                gen_time,
            )

            record = AttemptRecord(
                attempt_number=attempt,
                seed=current_seed,
                steps=current_steps,
                guidance_scale=current_cfg,
                width=width,
                height=height,
                quality_score=score,
                generation_time=gen_time,
            )
            records.append(record)
            all_images.append(image)

            if score > best_score:
                best_score = score
                best_image = image
                best_idx = attempt

            # ---- GPU memory cleanup after each attempt ----
            _clear_cuda_cache()

            if score >= self._threshold:
                logger.info("Quality threshold met at attempt %d.", attempt)
                break

            # ---- parameter adjustment for next attempt ----
            current_steps = min(current_steps + 10, _MAX_STEPS)
            current_cfg = round(min(current_cfg * 1.1, _MAX_CFG), 2)
            current_seed = random.randint(0, 2**32 - 1)
            if _DEFAULT_NEGATIVE not in current_neg:
                current_neg = f"{current_neg}, {_DEFAULT_NEGATIVE}"

        assert best_image is not None, (
            "All adaptive sampling attempts failed — no image was produced.  "
            "This likely indicates persistent CUDA OOM.  Try reducing resolution."
        )
        logger.info(
            "Adaptive loop finished — best attempt=%d  best_score=%.4f  total_attempts=%d",
            best_idx,
            best_score,
            len(records),
        )
        return SamplingResult(
            best_image=best_image,
            best_attempt=best_idx,
            attempts=records,
            images=all_images,
        )
