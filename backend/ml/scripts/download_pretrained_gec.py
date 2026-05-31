"""
Download a pretrained GEC (Grammar Error Correction) T5 model from HuggingFace
and save it locally so the backend can use it without internet access.

Model: vennify/t5-base-grammar-correction
  - Fine-tuned T5-base on JFLEG + other GEC corpora
  - Uses prompt format: "correct grammar: <sentence>"
  - ~900 MB on disk
  - Compatible with local_ml.py out of the box

Usage:
    backend\.venv\Scripts\python.exe backend\ml\scripts\download_pretrained_gec.py
"""
import sys
from pathlib import Path

OUTPUT_DIR = Path(__file__).resolve().parents[2] / "models" / "gec_t5_small"
HF_MODEL_ID = "vennify/t5-base-grammar-correction"

def main():
    print("=" * 60)
    print("  GEC Model Downloader")
    print(f"  Source : {HF_MODEL_ID}")
    print(f"  Target : {OUTPUT_DIR}")
    print("=" * 60)

    try:
        from transformers import AutoTokenizer, AutoModelForSeq2SeqLM
    except ImportError:
        print("[ERROR] transformers is not installed.")
        print("  Run: pip install transformers")
        sys.exit(1)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # Check if already downloaded
    if (OUTPUT_DIR / "config.json").exists():
        print("[INFO] Model already exists at target directory.")
        print("  Delete the folder and re-run to force re-download.")
        _quick_test()
        return

    print("\n[1/2] Downloading tokenizer...")
    tokenizer = AutoTokenizer.from_pretrained(HF_MODEL_ID)
    tokenizer.save_pretrained(str(OUTPUT_DIR))
    print("      Tokenizer saved.")

    print("\n[2/2] Downloading model weights (~900 MB, please wait)...")
    model = AutoModelForSeq2SeqLM.from_pretrained(HF_MODEL_ID)
    model.save_pretrained(str(OUTPUT_DIR))
    print("      Model saved.")

    print(f"\n[OK] Model saved to: {OUTPUT_DIR}")
    _quick_test()


def _quick_test():
    """Run a quick smoke-test to confirm the model works."""
    print("\n--- Quick smoke test ---")
    try:
        import torch
        from transformers import AutoTokenizer, AutoModelForSeq2SeqLM

        tokenizer = AutoTokenizer.from_pretrained(str(OUTPUT_DIR), local_files_only=True)
        model = AutoModelForSeq2SeqLM.from_pretrained(str(OUTPUT_DIR), local_files_only=True)
        model.eval()

        test_cases = [
            "She go to school every day.",
            "He have been wait for the bus.",
            "They is very happy about the result.",
        ]

        for sentence in test_cases:
            inputs = tokenizer(
                f"correct grammar: {sentence}",
                return_tensors="pt",
                truncation=True,
                max_length=128,
            )
            with torch.no_grad():
                output_ids = model.generate(**inputs, max_length=128, num_beams=4)
            corrected = tokenizer.decode(output_ids[0], skip_special_tokens=True)
            status = "OK " if corrected.strip() != sentence else "---"
            print(f"  [{status}] {sentence}")
            print(f"       --> {corrected}")

        print("\n[PASS] Model is working correctly.")
        print("\nTo enable in the backend, run start_backend_with_ml.bat")
        print("or set the env variable before starting:")
        print("  set GRAMMAR_CHECK_ENABLE_LOCAL_ML=1")

    except Exception as e:
        print(f"[ERROR] Smoke test failed: {e}")


if __name__ == "__main__":
    main()
