from __future__ import annotations

import argparse
import csv
import json
import random
from pathlib import Path
from typing import Iterable


SOURCE_KEYS = ("source", "src", "incorrect", "input", "original", "error")
TARGET_KEYS = ("target", "tgt", "correct", "output", "corrected", "gold")


def normalize_text(value: object) -> str:
    return " ".join(str(value or "").strip().split())


def read_jsonl(path: Path) -> Iterable[dict[str, str]]:
    with path.open("r", encoding="utf-8") as file:
        for line_number, line in enumerate(file, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                row = json.loads(stripped)
            except json.JSONDecodeError as error:
                raise ValueError(f"{path}:{line_number} is not valid JSONL: {error}") from error
            source = first_present(row, SOURCE_KEYS)
            target = first_present(row, TARGET_KEYS)
            if source and target:
                yield {"source": normalize_text(source), "target": normalize_text(target)}


def read_csv(path: Path) -> Iterable[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as file:
        reader = csv.DictReader(file)
        for row in reader:
            source = first_present(row, SOURCE_KEYS)
            target = first_present(row, TARGET_KEYS)
            if source and target:
                yield {"source": normalize_text(source), "target": normalize_text(target)}


def read_m2(path: Path) -> Iterable[dict[str, str]]:
    sentence: str | None = None
    edits: list[tuple[int, int, str]] = []
    with path.open("r", encoding="utf-8") as file:
        for raw_line in file:
            line = raw_line.rstrip("\n")
            if not line:
                yield from flush_m2_sentence(sentence, edits)
                sentence = None
                edits = []
                continue
            if line.startswith("S "):
                yield from flush_m2_sentence(sentence, edits)
                sentence = line[2:].strip()
                edits = []
                continue
            if line.startswith("A ") and sentence is not None:
                parsed = parse_m2_edit(line)
                if parsed is not None:
                    edits.append(parsed)
        yield from flush_m2_sentence(sentence, edits)


def parse_m2_edit(line: str) -> tuple[int, int, str] | None:
    # Format: A start end|||TYPE|||replacement|||REQUIRED|||-NONE-|||0
    try:
        span, error_type, replacement, *_rest = line[2:].split("|||")
        if error_type in {"noop", "UNK", "Um"}:
            return None
        start_text, end_text = span.split()
        return int(start_text), int(end_text), replacement.strip()
    except ValueError:
        return None


def flush_m2_sentence(sentence: str | None, edits: list[tuple[int, int, str]]) -> Iterable[dict[str, str]]:
    if not sentence:
        return
    source_tokens = sentence.split()
    target_tokens = list(source_tokens)
    for start, end, replacement in sorted(edits, key=lambda item: item[0], reverse=True):
        replacement_tokens = [] if replacement in {"", "-NONE-"} else replacement.split()
        target_tokens[start:end] = replacement_tokens
    target = " ".join(target_tokens)
    source = " ".join(source_tokens)
    if source and target and source != target:
        yield {"source": source, "target": target}


def first_present(row: dict, keys: tuple[str, ...]) -> object | None:
    lowered = {str(key).lower(): value for key, value in row.items()}
    for key in keys:
        value = lowered.get(key)
        if value not in {None, ""}:
            return value
    return None


def read_pairs(path: Path) -> Iterable[dict[str, str]]:
    suffix = path.suffix.lower()
    if suffix == ".jsonl":
        yield from read_jsonl(path)
    elif suffix == ".csv":
        yield from read_csv(path)
    elif suffix == ".m2":
        yield from read_m2(path)
    else:
        raise ValueError(f"Unsupported dataset format: {path}. Use .jsonl, .csv, or .m2.")


def dedupe_pairs(pairs: Iterable[dict[str, str]]) -> list[dict[str, str]]:
    seen: set[tuple[str, str]] = set()
    deduped: list[dict[str, str]] = []
    for pair in pairs:
        source = normalize_text(pair["source"])
        target = normalize_text(pair["target"])
        if not source or not target or source == target:
            continue
        key = (source.lower(), target.lower())
        if key in seen:
            continue
        seen.add(key)
        deduped.append({"source": source, "target": target})
    return deduped


def write_jsonl(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file:
        for row in rows:
            file.write(json.dumps(row, ensure_ascii=False) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(description="Prepare small GEC sentence-pair datasets for local fine-tuning.")
    parser.add_argument("--input", nargs="+", type=Path, required=True, help="Input .jsonl, .csv, or .m2 files.")
    parser.add_argument("--output-dir", type=Path, default=Path("backend/ml/datasets/processed"))
    parser.add_argument("--limit", type=int, default=10000, help="Maximum pairs to keep after shuffling.")
    parser.add_argument("--seed", type=int, default=13)
    parser.add_argument("--train-ratio", type=float, default=0.9)
    parser.add_argument("--val-ratio", type=float, default=0.05)
    args = parser.parse_args()

    pairs = dedupe_pairs(pair for path in args.input for pair in read_pairs(path))
    random.Random(args.seed).shuffle(pairs)
    if args.limit > 0:
        pairs = pairs[: args.limit]

    train_end = int(len(pairs) * args.train_ratio)
    val_end = train_end + int(len(pairs) * args.val_ratio)
    splits = {
        "train": pairs[:train_end],
        "val": pairs[train_end:val_end],
        "test": pairs[val_end:],
    }

    for split, rows in splits.items():
        write_jsonl(args.output_dir / f"{split}.jsonl", rows)

    print(
        json.dumps(
            {
                "total": len(pairs),
                "train": len(splits["train"]),
                "val": len(splits["val"]),
                "test": len(splits["test"]),
                "output_dir": str(args.output_dir),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
