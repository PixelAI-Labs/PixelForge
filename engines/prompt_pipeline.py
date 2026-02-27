"""PromptPipeline — three-stage prompt preprocessing for image generation.

Stages:
1. Spelling correction   — SymSpell dictionary-based correction
2. Grammar correction    — Flan-T5-small (HuggingFace transformers)
3. Diffusion enhancement — rule-based keyword injection + negative prompt

The pipeline is designed for thread-safe, single-load usage inside
:class:`AdaptiveSampler`.
"""

from __future__ import annotations

import logging
import threading
from typing import Any, Optional, Tuple

logger = logging.getLogger(__name__)

# ---- quality keywords used by enhancement stage -----------------

_QUALITY_KEYWORDS = frozenset({
    "4k", "8k", "hd", "uhd", "high quality", "highly detailed",
    "ultra detailed", "cinematic", "sharp focus", "ultra sharp",
    "professional", "masterpiece", "best quality", "photorealistic",
    "resolution", "detailed",
})

_QUALITY_SUFFIX = ", cinematic lighting, ultra sharp focus, 4k resolution"
_SHORT_PROMPT_PREFIX = "Highly detailed image of"

_DEFAULT_NEGATIVE_PROMPT = (
    "blurry, distorted, low resolution, extra limbs, malformed anatomy"
)


class PromptPipeline:
    """Three-stage prompt preprocessor.

    Parameters
    ----------
    enabled : bool
        Master switch.  When ``False``, :meth:`process` returns the prompt
        unchanged with the default negative prompt.
    device : str | None
        Device for the grammar model (``"cpu"`` recommended — the model
        is tiny).  Defaults to ``"cpu"``.
    """

    def __init__(
        self,
        enabled: bool = True,
        device: Optional[str] = None,
    ) -> None:
        self._enabled = enabled
        self._device = device or "cpu"

        # ---- lazy-loaded resources (thread-safe) ----
        self._lock = threading.Lock()
        self._symspell: Any = None
        self._grammar_model: Any = None
        self._grammar_tokenizer: Any = None

    # ---- public API ---------------------------------------------

    def process(self, prompt: str) -> Tuple[str, str]:
        """Run the full pipeline and return (enhanced_prompt, negative_prompt).

        When the pipeline is disabled the original prompt and a default
        negative prompt are returned.
        """
        if not self._enabled or not prompt.strip():
            return prompt, _DEFAULT_NEGATIVE_PROMPT

        # Stage 1 — spelling correction
        corrected_spelling = self._correct_spelling(prompt)
        logger.info(
            "PromptPipeline | spelling: %r → %r", prompt, corrected_spelling,
        )

        # Stage 2 — grammar correction
        corrected_grammar = self._correct_grammar(corrected_spelling)
        logger.info(
            "PromptPipeline | grammar:  %r → %r",
            corrected_spelling,
            corrected_grammar,
        )

        # Stage 3 — diffusion-friendly enhancement
        enhanced, negative = self._enhance(corrected_grammar)
        logger.info(
            "PromptPipeline | enhanced: %r  |  negative: %r",
            enhanced,
            negative,
        )

        return enhanced, negative

    # ---- Stage 1: spelling correction ---------------------------

    def _ensure_symspell(self) -> None:
        """Load SymSpell dictionary once (thread-safe)."""
        if self._symspell is not None:
            return

        with self._lock:
            if self._symspell is not None:  # double-check after lock
                return

            from symspellpy import SymSpell  # type: ignore[import-unresolved]
            import importlib.resources as _resources

            sym = SymSpell(max_dictionary_edit_distance=2, prefix_length=7)
            # Locate the built-in frequency dictionary shipped with symspellpy
            dict_path = str(
                _resources.files("symspellpy").joinpath(
                    "frequency_dictionary_en_82_765.txt",
                )
            )
            sym.load_dictionary(dict_path, term_index=0, count_index=1)
            self._symspell = sym
            logger.info("SymSpell dictionary loaded.")

    def _correct_spelling(self, text: str) -> str:
        """Apply SymSpell lookup on each word, preserving structure."""
        self._ensure_symspell()
        from symspellpy import Verbosity  # type: ignore[import-unresolved]

        suggestions = self._symspell.lookup_compound(
            text, max_edit_distance=2,
        )
        if suggestions:
            return suggestions[0].term
        return text

    # ---- Stage 2: grammar correction ----------------------------

    _GRAMMAR_MODEL_ID = "google/flan-t5-small"

    def _ensure_grammar_model(self) -> None:
        """Load Flan-T5-small once (thread-safe)."""
        if self._grammar_model is not None:
            return

        with self._lock:
            if self._grammar_model is not None:
                return

            from transformers import AutoModelForSeq2SeqLM, AutoTokenizer

            logger.info("Loading grammar model %s …", self._GRAMMAR_MODEL_ID)
            self._grammar_tokenizer = AutoTokenizer.from_pretrained(
                self._GRAMMAR_MODEL_ID,
            )
            self._grammar_model = AutoModelForSeq2SeqLM.from_pretrained(
                self._GRAMMAR_MODEL_ID,
            ).to(self._device)
            self._grammar_model.eval()
            logger.info("Grammar model loaded on %s.", self._device)

    def _correct_grammar(self, text: str) -> str:
        """Use Flan-T5-small to fix grammar in *text*."""
        self._ensure_grammar_model()

        instruction = f"Correct the grammar of this sentence: {text}"

        inputs = self._grammar_tokenizer(
            instruction, return_tensors="pt", truncation=True, max_length=256,
        ).to(self._device)

        import torch as _torch

        with _torch.no_grad():
            output_ids = self._grammar_model.generate(
                **inputs,
                max_new_tokens=128,
                temperature=1.0,
                do_sample=False,
            )

        result = self._grammar_tokenizer.decode(
            output_ids[0], skip_special_tokens=True,
        ).strip()

        return result if result else text

    # ---- Stage 3: diffusion-friendly enhancement ----------------

    @staticmethod
    def _enhance(text: str) -> Tuple[str, str]:
        """Apply rule-based prompt enhancement and return (prompt, negative)."""
        enhanced = text.strip()

        # Prefix short prompts
        word_count = len(enhanced.split())
        if word_count < 8:
            enhanced = f"{_SHORT_PROMPT_PREFIX} {enhanced}"

        # Append quality keywords if none are present
        lower = enhanced.lower()
        has_quality = any(kw in lower for kw in _QUALITY_KEYWORDS)
        if not has_quality:
            enhanced = f"{enhanced}{_QUALITY_SUFFIX}"

        return enhanced, _DEFAULT_NEGATIVE_PROMPT
