from __future__ import annotations

import argparse
import json
import random
import urllib.request
from pathlib import Path


BASE_URL = "https://raw.githubusercontent.com/keisks/jfleg/master"
SPLITS = {
    "dev": {
        "source": "dev/dev.src",
        "references": [f"dev/dev.ref{index}" for index in range(4)],
    },
    "test": {
        "source": "test/test.src",
        "references": [f"test/test.ref{index}" for index in range(4)],
    },
}


def download_text(relative_path: str) -> str:
    url = f"{BASE_URL}/{relative_path}"
    with urllib.request.urlopen(url, timeout=30) as response:
        return response.read().decode("utf-8")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def read_lines(path: Path) -> list[str]:
    return [" ".join(line.strip().split()) for line in path.read_text(encoding="utf-8").splitlines()]


def write_jsonl(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file:
        for row in rows:
            file.write(json.dumps(row, ensure_ascii=False) + "\n")


def build_pairs(source_file: Path, reference_files: list[Path]) -> list[dict[str, str]]:
    sources = read_lines(source_file)
    references_by_file = [read_lines(path) for path in reference_files]
    pairs: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for index, source in enumerate(sources):
        for references in references_by_file:
            if index >= len(references):
                continue
            target = references[index]
            if not source or not target or source == target:
                continue
            key = (source.lower(), target.lower())
            if key in seen:
                continue
            seen.add(key)
            pairs.append({"source": source, "target": target})
    return pairs


def main() -> int:
    parser = argparse.ArgumentParser(description="Download and prepare the small JFLEG GEC dataset.")
    parser.add_argument("--raw-dir", type=Path, default=Path("backend/ml/datasets/raw/jfleg"))
    parser.add_argument("--output-dir", type=Path, default=Path("backend/ml/datasets/processed"))
    parser.add_argument("--seed", type=int, default=13)
    parser.add_argument("--train-ratio", type=float, default=0.9)
    args = parser.parse_args()

    for split, files in SPLITS.items():
        write_text(args.raw_dir / files["source"], download_text(files["source"]))
        for reference in files["references"]:
            write_text(args.raw_dir / reference, download_text(reference))

    dev_pairs = build_pairs(
        args.raw_dir / SPLITS["dev"]["source"],
        [args.raw_dir / reference for reference in SPLITS["dev"]["references"]],
    )
    test_pairs = build_pairs(
        args.raw_dir / SPLITS["test"]["source"],
        [args.raw_dir / reference for reference in SPLITS["test"]["references"]],
    )

    random.Random(args.seed).shuffle(dev_pairs)
    train_end = int(len(dev_pairs) * args.train_ratio)
    train_pairs = dev_pairs[:train_end]
    val_pairs = dev_pairs[train_end:]

    write_jsonl(args.output_dir / "train.jsonl", train_pairs)
    write_jsonl(args.output_dir / "val.jsonl", val_pairs)
    write_jsonl(args.output_dir / "test.jsonl", test_pairs)

    manifest = {
        "dataset": "JFLEG",
        "source": "https://github.com/keisks/jfleg",
        "license": "CC BY-NC-SA 4.0",
        "raw_dir": str(args.raw_dir),
        "output_dir": str(args.output_dir),
        "train_pairs": len(train_pairs),
        "val_pairs": len(val_pairs),
        "test_pairs": len(test_pairs),
    }
    write_text(args.output_dir / "jfleg_manifest.json", json.dumps(manifest, indent=2))
    print(json.dumps(manifest, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
