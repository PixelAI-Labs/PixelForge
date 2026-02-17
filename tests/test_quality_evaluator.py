"""Tests for QualityEvaluator sharpness scoring (no CLIP model needed)."""

import numpy as np
from PIL import Image

from engines.quality_evaluator import QualityEvaluator


class TestSharpnessScore:
    def test_sharp_image_scores_higher(self) -> None:
        """A high-contrast image should score higher than a uniform one."""
        # Uniform grey → low sharpness
        flat = Image.fromarray(np.full((64, 64), 128, dtype=np.uint8), mode="L").convert("RGB")

        # Random noise → higher variance → higher sharpness
        rng = np.random.RandomState(0)
        noisy_arr = rng.randint(0, 255, (64, 64), dtype=np.uint8)
        noisy = Image.fromarray(noisy_arr, mode="L").convert("RGB")

        flat_score = QualityEvaluator.sharpness_score(flat)
        noisy_score = QualityEvaluator.sharpness_score(noisy)

        assert noisy_score > flat_score

    def test_score_in_range(self) -> None:
        img = Image.new("RGB", (64, 64), "white")
        score = QualityEvaluator.sharpness_score(img)
        assert 0.0 <= score <= 1.0
