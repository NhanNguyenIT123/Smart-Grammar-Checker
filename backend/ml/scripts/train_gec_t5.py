from __future__ import annotations

import argparse
import inspect
import json
from pathlib import Path

import torch
from torch.utils.data import Dataset
from transformers import (
    AutoModelForSeq2SeqLM,
    AutoTokenizer,
    DataCollatorForSeq2Seq,
    Seq2SeqTrainer,
    Seq2SeqTrainingArguments,
)


class GecJsonlDataset(Dataset):
    def __init__(self, path: Path, tokenizer, max_source_length: int, max_target_length: int, limit: int = 0) -> None:
        self.rows = load_rows(path, limit)
        self.tokenizer = tokenizer
        self.max_source_length = max_source_length
        self.max_target_length = max_target_length

    def __len__(self) -> int:
        return len(self.rows)

    def __getitem__(self, index: int) -> dict:
        row = self.rows[index]
        source = f"correct grammar: {row['source']}"
        model_inputs = self.tokenizer(
            source,
            max_length=self.max_source_length,
            truncation=True,
        )
        labels = self.tokenizer(
            text_target=row["target"],
            max_length=self.max_target_length,
            truncation=True,
        )
        model_inputs["labels"] = labels["input_ids"]
        return model_inputs


def load_rows(path: Path, limit: int = 0) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    with path.open("r", encoding="utf-8") as file:
        for line in file:
            if not line.strip():
                continue
            row = json.loads(line)
            if row.get("source") and row.get("target"):
                rows.append({"source": str(row["source"]), "target": str(row["target"])})
            if limit and len(rows) >= limit:
                break
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description="Fine-tune a small T5 grammar correction model.")
    parser.add_argument("--model-name", default="t5-small")
    parser.add_argument("--train-file", type=Path, default=Path("backend/ml/datasets/processed/train.jsonl"))
    parser.add_argument("--val-file", type=Path, default=Path("backend/ml/datasets/processed/val.jsonl"))
    parser.add_argument("--output-dir", type=Path, default=Path("backend/ml/models/gec_t5_small"))
    parser.add_argument("--max-source-length", type=int, default=128)
    parser.add_argument("--max-target-length", type=int, default=128)
    parser.add_argument("--train-limit", type=int, default=0)
    parser.add_argument("--val-limit", type=int, default=0)
    parser.add_argument("--epochs", type=float, default=2.0)
    parser.add_argument("--batch-size", type=int, default=1)
    parser.add_argument("--gradient-accumulation-steps", type=int, default=8)
    parser.add_argument("--learning-rate", type=float, default=5e-5)
    parser.add_argument("--no-fp16", action="store_true")
    args = parser.parse_args()

    tokenizer = AutoTokenizer.from_pretrained(args.model_name)
    model = AutoModelForSeq2SeqLM.from_pretrained(args.model_name)
    model.config.use_cache = False
    if hasattr(model, "gradient_checkpointing_enable"):
        model.gradient_checkpointing_enable()

    train_dataset = GecJsonlDataset(
        args.train_file,
        tokenizer,
        args.max_source_length,
        args.max_target_length,
        args.train_limit,
    )
    val_dataset = GecJsonlDataset(
        args.val_file,
        tokenizer,
        args.max_source_length,
        args.max_target_length,
        args.val_limit,
    )

    use_fp16 = torch.cuda.is_available() and not args.no_fp16
    training_kwargs = {
        "output_dir": str(args.output_dir),
        "num_train_epochs": args.epochs,
        "per_device_train_batch_size": args.batch_size,
        "per_device_eval_batch_size": 1,
        "gradient_accumulation_steps": args.gradient_accumulation_steps,
        "learning_rate": args.learning_rate,
        "fp16": use_fp16,
        "save_strategy": "epoch",
        "save_total_limit": 1,
        "logging_steps": 25,
        "predict_with_generate": True,
        "report_to": [],
    }
    strategy_arg = "eval_strategy" if "eval_strategy" in inspect.signature(Seq2SeqTrainingArguments).parameters else "evaluation_strategy"
    training_kwargs[strategy_arg] = "epoch"
    training_args = Seq2SeqTrainingArguments(**training_kwargs)
    trainer_kwargs = {
        "model": model,
        "args": training_args,
        "train_dataset": train_dataset,
        "eval_dataset": val_dataset,
        "data_collator": DataCollatorForSeq2Seq(tokenizer=tokenizer, model=model),
    }
    trainer_tokenizer_arg = "processing_class" if "processing_class" in inspect.signature(Seq2SeqTrainer).parameters else "tokenizer"
    trainer_kwargs[trainer_tokenizer_arg] = tokenizer
    trainer = Seq2SeqTrainer(**trainer_kwargs)
    trainer.train()
    trainer.save_model(str(args.output_dir))
    tokenizer.save_pretrained(str(args.output_dir))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
