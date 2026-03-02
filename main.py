"""PixelForge entry-point.

Usage:
    uvicorn main:app --host 0.0.0.0 --port 8000
"""

import logging
import os

from api.app import create_app
from db.connection import verify_sync_connection
from engines.model_manager import ModelManager
from engines.prompt_pipeline import PromptPipeline
from engines.quality_evaluator import QualityEvaluator

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

logger = logging.getLogger(__name__)

# When PIXELFORGE_SKIP_LOAD=1 (e.g. during tests), defer model loading.
_skip_load = os.getenv("PIXELFORGE_SKIP_LOAD") == "1"

_mm = ModelManager(auto_load=not _skip_load)
_qe = QualityEvaluator()
_pp = PromptPipeline(enabled=not _skip_load)

if not _skip_load:
    _qe.load()        # CLIP for quality scoring (steps/CFG feedback)
    _qe.load_llava()  # LLaVA for prompt-alignment evaluation

# Verify MongoDB is reachable before creating the app
_mongo_ok = verify_sync_connection()
if _mongo_ok:
    logger.info("Starting PixelForge with MongoDB persistence.")
else:
    logger.warning("MongoDB not reachable — falling back to in-memory stores.")

app = create_app(
    model_manager=_mm,
    quality_evaluator=_qe,
    prompt_pipeline=_pp,
    use_memory=not _mongo_ok,
)
