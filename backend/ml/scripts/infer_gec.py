from __future__ import annotations

import argparse
from pathlib import Path

import torch
from transformers import AutoModelForSeq2SeqLM, AutoTokenizer


def main() -> int:
    parser = argparse.ArgumentParser(description="Run one local grammar-correction inference.")
    parser.add_argument("text")
    parser.add_argument("--model-dir", type=Path, default=Path("backend/ml/models/gec_t5_small"))
    parser.add_argument("--max-length", type=int, default=128)
    args = parser.parse_args()

    tokenizer = AutoTokenizer.from_pretrained(args.model_dir)
    model = AutoModelForSeq2SeqLM.from_pretrained(args.model_dir)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model.to(device)
    model.eval()

    inputs = tokenizer(f"correct grammar: {args.text}", return_tensors="pt", truncation=True, max_length=args.max_length).to(device)
    with torch.no_grad():
        output_ids = model.generate(**inputs, max_length=args.max_length, num_beams=4)
    print(tokenizer.decode(output_ids[0], skip_special_tokens=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
