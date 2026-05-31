from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any


DEFAULT_MODEL_DIR = Path(__file__).resolve().parents[3] / "ml" / "models" / "gec_t5_small"


def check_grammar_with_local_ml(text: str) -> dict[str, Any]:
    model_dir = Path(os.getenv("GRAMMAR_CHECK_LOCAL_ML_MODEL", str(DEFAULT_MODEL_DIR)))
    if not model_dir.exists():
        return {
            "corrected_text": text,
            "grammar_errors": [
                {
                    "category": "System",
                    "message": f"Local ML model was not found at {model_dir}.",
                    "rule_id": "SYSTEM_ERROR",
                    "suggestion": None,
                    "evidence": None,
                    "severity": "warning",
                    "knowledge_source": "local-ml",
                    "confidence": 0.0,
                }
            ],
        }

    try:
        corrected = _generate_correction(text, model_dir)
    except Exception as error:
        return {
            "corrected_text": text,
            "grammar_errors": [
                {
                    "category": "System",
                    "message": f"Local ML inference failed: {error}",
                    "rule_id": "SYSTEM_ERROR",
                    "suggestion": None,
                    "evidence": None,
                    "severity": "warning",
                    "knowledge_source": "local-ml",
                    "confidence": 0.0,
                }
            ],
        }

    if _normalize(corrected) == _normalize(text):
        return {"corrected_text": text, "grammar_errors": []}

    explanation = _generate_ml_explanation(text, corrected)

    return {
        "corrected_text": corrected,
        "grammar_errors": [
            {
                "category": "ML Correction",
                "message": explanation,
                "rule_id": "ML-GEC-REWRITE",
                "suggestion": corrected,
                "evidence": text,
                "severity": "error",
                "knowledge_source": "local-ml-gec",
                "confidence": 0.72,
            }
        ],
    }


def _generate_ml_explanation(original: str, corrected: str) -> str:
    import difflib

    orig_words = str(original or "").split()
    corr_words = str(corrected or "").split()

    matcher = difflib.SequenceMatcher(None, orig_words, corr_words)
    opcodes = matcher.get_opcodes()

    changes = []
    for tag, i1, i2, j1, j2 in opcodes:
        if tag == "equal":
            continue

        orig_part = " ".join(orig_words[i1:i2])
        corr_part = " ".join(corr_words[j1:j2])

        if tag == "replace":
            changes.append(f"changing '{orig_part}' to '{corr_part}'")
        elif tag == "delete":
            changes.append(f"removing redundant '{orig_part}'")
        elif tag == "insert":
            changes.append(f"inserting '{corr_part}'")

    if not changes:
        return "The local sequence-to-sequence model suggested a grammar rewrite for better flow."

    if len(changes) == 1:
        return "AI suggested " + changes[0] + " for better phrasing and correctness."

    explanation = ", ".join(changes[:-1]) + f", and {changes[-1]}"
    return "AI suggested " + explanation + " to improve sentence structure."


@lru_cache(maxsize=1)
def _load_model(model_dir_text: str):
    import torch
    from transformers import AutoModelForSeq2SeqLM, AutoTokenizer

    tokenizer = AutoTokenizer.from_pretrained(model_dir_text, local_files_only=True)
    model = AutoModelForSeq2SeqLM.from_pretrained(model_dir_text, local_files_only=True)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model.to(device)
    model.eval()
    return tokenizer, model, device


def _generate_correction(text: str, model_dir: Path) -> str:
    import torch

    tokenizer, model, device = _load_model(str(model_dir))
    inputs = tokenizer(
        f"correct grammar: {text}",
        return_tensors="pt",
        truncation=True,
        max_length=int(os.getenv("GRAMMAR_CHECK_LOCAL_ML_MAX_LENGTH", "128")),
    ).to(device)
    with torch.no_grad():
        output_ids = model.generate(
            **inputs,
            max_length=int(os.getenv("GRAMMAR_CHECK_LOCAL_ML_MAX_LENGTH", "128")),
            num_beams=int(os.getenv("GRAMMAR_CHECK_LOCAL_ML_BEAMS", "4")),
        )
    return _normalize(tokenizer.decode(output_ids[0], skip_special_tokens=True))


def _normalize(text: str) -> str:
    return " ".join(str(text or "").strip().split())
