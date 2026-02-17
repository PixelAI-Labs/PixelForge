"""AdaptiveSampler — feedback-driven regeneration loop.

Algorithm (from DESIGN.md / DRD):
1. Generate initial image
2. Evaluate quality
3. If quality >= threshold → accept
4. Else:
   - Increase steps (+10, bounded)
   - Adjust CFG ±10%
   - Change seed
   - Strengthen negative prompt
   - Regenerate
5. Repeat (max 3 attempts)
6. Return best result

Constraints:
* Max 3 attempts
* Small parameter deltas
* Log every attempt
"""

from __future__ import annotations

import logging
import random
import time
from dataclasses import dataclass
from typing import List, Optional

from PIL import Image

from core.models import AttemptRecord
from engines.model_manager import ModelManager
from engines.quality_evaluator import QualityEvaluator

logger = logging.getLogger(__name__)

_DEFAULT_QUALITY_THRESHOLD = 0.65
_MAX_ATTEMPTS = 3
_DEFAULT_NEGATIVE = "blurry, distorted, low quality, artifacts"


@dataclass
class SamplingResult:
    """Final result of the adaptive sampling loop."""

    best_image: Image.Image
    best_attempt: int
    attempts: List[AttemptRecord]


class AdaptiveSampler:
    """Run the adaptive inference loop over ModelManager + QualityEvaluator."""

    def __init__(
        self,
        model_manager: ModelManager,
        quality_evaluator: QualityEvaluator,
        quality_threshold: float = _DEFAULT_QUALITY_THRESHOLD,
        max_attempts: int = _MAX_ATTEMPTS,
    ) -> None:
        self._mm = model_manager
        self._qe = quality_evaluator
        self._threshold = quality_threshold
        self._max_attempts = max_attempts

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
        best_image: Optional[Image.Image] = None
        best_score: float = -1.0
        best_idx: int = 0
        records: List[AttemptRecord] = []

        current_seed = seed if seed is not None else random.randint(0, 2**32 - 1)
        current_steps = steps
        current_cfg = guidance_scale
        current_neg = negative_prompt or _DEFAULT_NEGATIVE

        for attempt in range(1, self._max_attempts + 1):
            logger.info(
                "Attempt %d/%d — seed=%d steps=%d cfg=%.2f",
                attempt,
                self._max_attempts,
                current_seed,
                current_steps,
                current_cfg,
            )

            t0 = time.time()
            image = self._mm.generate(
                prompt=prompt,
                steps=current_steps,
                guidance_scale=current_cfg,
                seed=current_seed,
                width=width,
                height=height,
                negative_prompt=current_neg,
            )
            gen_time = time.time() - t0

            score = self._qe.evaluate(prompt, image)
            logger.info("Attempt %d score: %.4f (threshold %.2f)", attempt, score, self._threshold)

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

            if score > best_score:
                best_score = score
                best_image = image
                best_idx = attempt

            if score >= self._threshold:
                logger.info("Quality threshold met at attempt %d.", attempt)
                break

            # ---- parameter adjustment for next attempt ----
            current_steps = min(current_steps + 10, 100)
            current_cfg = round(current_cfg * 1.1, 2)
            current_cfg = min(current_cfg, 20.0)
            current_seed = random.randint(0, 2**32 - 1)
            if _DEFAULT_NEGATIVE not in current_neg:
                current_neg = f"{current_neg}, {_DEFAULT_NEGATIVE}"

        assert best_image is not None
        return SamplingResult(
            best_image=best_image,
            best_attempt=best_idx,
            attempts=records,
        )
