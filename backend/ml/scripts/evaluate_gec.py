from __future__ import annotations

import argparse
import json
from pathlib import Path

import torch
from transformers import AutoModelForSeq2SeqLM, AutoTokenizer


def load_rows(path: Path, limit: int) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    with path.open("r", encoding="utf-8") as file:
        for line in file:
            if not line.strip():
                continue
            row = json.loads(line)
            rows.append({"source": str(row["source"]), "target": str(row["target"])})
            if limit and len(rows) >= limit:
                break
    return rows


def normalize(text: str) -> str:
    return " ".join(text.strip().split())


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate a local GEC model with lightweight portfolio metrics.")
    parser.add_argument("--model-dir", type=Path, default=Path("backend/ml/models/gec_t5_small"))
    parser.add_argument("--test-file", type=Path, default=Path("backend/ml/datasets/processed/test.jsonl"))
    parser.add_argument("--limit", type=int, default=500)
    parser.add_argument("--max-length", type=int, default=128)
    args = parser.parse_args()

    tokenizer = AutoTokenizer.from_pretrained(args.model_dir)
    model = AutoModelForSeq2SeqLM.from_pretrained(args.model_dir)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model.to(device)
    model.eval()

    rows = load_rows(args.test_file, args.limit)
    exact = 0
    changed = 0
    predictions: list[dict[str, str]] = []
    for row in rows:
        prompt = f"correct grammar: {row['source']}"
        inputs = tokenizer(prompt, return_tensors="pt", truncation=True, max_length=args.max_length).to(device)
        with torch.no_grad():
            output_ids = model.generate(**inputs, max_length=args.max_length, num_beams=4)
        prediction = normalize(tokenizer.decode(output_ids[0], skip_special_tokens=True))
        target = normalize(row["target"])
        source = normalize(row["source"])
        exact += int(prediction.lower() == target.lower())
        changed += int(prediction.lower() != source.lower())
        if len(predictions) < 20:
            predictions.append({"source": source, "target": target, "prediction": prediction})

    total = max(len(rows), 1)
    print(
        json.dumps(
            {
                "model_dir": str(args.model_dir),
                "test_file": str(args.test_file),
                "rows": len(rows),
                "exact_match": exact / total,
                "changed_rate": changed / total,
                "sample_predictions": predictions,
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
