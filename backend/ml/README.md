# Lightweight NLP Upgrade

This folder contains the optional grammar error correction (GEC) pipeline. It is designed for a laptop-class GPU such as an RTX 3050 6GB:

- dataset files stay out of Git by default
- model checkpoints stay out of Git
- training uses small batches and gradient accumulation
- the production backend only loads the model when explicitly enabled

## Data Shape

The ML pipeline expects sentence pairs:

```json
{"source":"She go to school every day.","target":"She goes to school every day."}
```

Supported prepare inputs:

- `.jsonl` with `source`/`target`, `incorrect`/`correct`, or `input`/`output`
- `.csv` with equivalent columns
- `.m2` files from grammatical error correction benchmarks

Keep full third-party datasets under `backend/ml/datasets/raw/`. Commit only tiny samples or scripts unless the dataset license explicitly allows redistribution.

## Small-Machine Workflow

Create a lightweight CPU smoke-test environment:

```powershell
python -m venv backend/.venv
backend/.venv/Scripts/python.exe -m pip install torch --index-url https://download.pytorch.org/whl/cpu
backend/.venv/Scripts/python.exe -m pip install transformers accelerate sentencepiece antlr4-python3-runtime==4.13.2
```

Prepare a small subset:

```powershell
python backend/ml/scripts/prepare_gec_dataset.py `
  --input backend/ml/datasets/raw/train.m2 `
  --output-dir backend/ml/datasets/processed `
  --limit 10000
```

Or download and prepare the small JFLEG benchmark directly:

```powershell
python backend/ml/scripts/download_jfleg.py
```

Smoke-test training without keeping the checkpoint:

```powershell
backend/.venv/Scripts/python.exe backend/ml/scripts/train_gec_t5.py `
  --train-file backend/ml/datasets/processed/train.jsonl `
  --val-file backend/ml/datasets/processed/val.jsonl `
  --output-dir backend/ml/runs/smoke_t5_small `
  --train-limit 32 `
  --val-limit 8 `
  --epochs 1 `
  --batch-size 1 `
  --gradient-accumulation-steps 8
```

Fine-tune `t5-small`:

```powershell
python backend/ml/scripts/train_gec_t5.py `
  --train-file backend/ml/datasets/processed/train.jsonl `
  --val-file backend/ml/datasets/processed/val.jsonl `
  --output-dir backend/ml/models/gec_t5_small `
  --batch-size 1 `
  --gradient-accumulation-steps 8 `
  --epochs 2
```

Evaluate:

```powershell
python backend/ml/scripts/evaluate_gec.py `
  --model-dir backend/ml/models/gec_t5_small `
  --test-file backend/ml/datasets/processed/test.jsonl `
  --limit 500
```

Run one inference:

```powershell
python backend/ml/scripts/infer_gec.py "She go to school every day." `
  --model-dir backend/ml/models/gec_t5_small
```

Enable the model inside the app:

```powershell
$env:GRAMMAR_CHECK_ENABLE_LOCAL_ML="1"
$env:GRAMMAR_CHECK_LOCAL_ML_MODEL="D:\GITHUB\Smart-Grammar-Checker\backend\ml\models\gec_t5_small"
python backend/run.py serve --host 127.0.0.1 --port 8000
```

Leave `GRAMMAR_CHECK_ENABLE_LOCAL_ML` unset during normal development to keep startup fast and avoid GPU memory use.

## Recommended First Datasets

Start small. A good first target is 5k-10k sentence pairs, then 20k-30k if the first run is stable.

Useful GEC-style sources to prepare locally:

- JFLEG-style sentence pairs for fluency correction
- FCE-style learner English pairs
- BEA/W&I+LOCNESS subsets
- CoNLL `.m2` files for test/evaluation

Avoid large Lang-8 style dumps until the pipeline and evaluation are stable.
