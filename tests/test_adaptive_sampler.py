"""Tests for AdaptiveSampler using mock ModelManager and QualityEvaluator.

From Testing.md: "Replace ModelManager with mock generator —
test adaptive loop logic deterministically."
"""

from unittest.mock import MagicMock

from PIL import Image

from core.models import AttemptRecord
from engines.adaptive_sampler import AdaptiveSampler
from engines.model_manager import ModelManager
from engines.quality_evaluator import QualityEvaluator


def _make_mock_mm() -> ModelManager:
    mm = MagicMock(spec=ModelManager)
    mm.generate.return_value = Image.new("RGB", (64, 64), "green")
    return mm


class TestAdaptiveSampler:
    def test_accepts_on_first_attempt_if_threshold_met(self) -> None:
        mm = _make_mock_mm()
        qe = MagicMock(spec=QualityEvaluator)
        qe.evaluate.return_value = 0.80  # above default threshold 0.65

        sampler = AdaptiveSampler(mm, qe)
        result = sampler.run(prompt="a cat", seed=42)

        assert len(result.attempts) == 1
        assert result.best_attempt == 1
        mm.generate.assert_called_once()

    def test_retries_when_below_threshold(self) -> None:
        mm = _make_mock_mm()
        qe = MagicMock(spec=QualityEvaluator)
        # First two below threshold, third above
        qe.evaluate.side_effect = [0.3, 0.5, 0.8]

        sampler = AdaptiveSampler(mm, qe)
        result = sampler.run(prompt="a portrait", seed=1)

        assert len(result.attempts) == 3
        assert result.best_attempt == 3  # highest score

    def test_max_attempts_respected(self) -> None:
        mm = _make_mock_mm()
        qe = MagicMock(spec=QualityEvaluator)
        qe.evaluate.return_value = 0.2  # always below

        sampler = AdaptiveSampler(mm, qe, max_attempts=3)
        result = sampler.run(prompt="test")

        assert len(result.attempts) == 3
        assert mm.generate.call_count == 3

    def test_parameter_adjustment_increases_steps(self) -> None:
        mm = _make_mock_mm()
        qe = MagicMock(spec=QualityEvaluator)
        qe.evaluate.return_value = 0.1

        sampler = AdaptiveSampler(mm, qe, max_attempts=2)
        result = sampler.run(prompt="test", steps=30)

        # Second attempt should have steps = 40
        assert result.attempts[1].steps == 40

    def test_best_image_selected(self) -> None:
        mm = _make_mock_mm()
        qe = MagicMock(spec=QualityEvaluator)
        # Attempt 2 has the best score
        qe.evaluate.side_effect = [0.3, 0.9, 0.5]

        sampler = AdaptiveSampler(mm, qe, max_attempts=3, quality_threshold=0.95)
        result = sampler.run(prompt="test")

        assert result.best_attempt == 2

    def test_custom_threshold(self) -> None:
        mm = _make_mock_mm()
        qe = MagicMock(spec=QualityEvaluator)
        qe.evaluate.return_value = 0.50

        sampler = AdaptiveSampler(mm, qe, quality_threshold=0.45)
        result = sampler.run(prompt="test")

        # Should accept on first attempt since 0.50 >= 0.45
        assert len(result.attempts) == 1
