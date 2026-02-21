"""PixelForge entry-point.

Usage:
    uvicorn main:app --host 0.0.0.0 --port 8000
"""

import logging
import os

from api.app import create_app
from engines.model_manager import ModelManager
from engines.quality_evaluator import QualityEvaluator

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

# When PIXELFORGE_SKIP_LOAD=1 (e.g. during tests), defer model loading.
_skip_load = os.getenv("PIXELFORGE_SKIP_LOAD") == "1"

_mm = ModelManager(auto_load=not _skip_load)
_qe = QualityEvaluator()

if not _skip_load:
    _qe.load()

app = create_app(model_manager=_mm, quality_evaluator=_qe)
