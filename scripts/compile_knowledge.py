from __future__ import annotations

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_SRC = PROJECT_ROOT / "backend" / "src"

if str(BACKEND_SRC) not in sys.path:
    sys.path.insert(0, str(BACKEND_SRC))

from grammar_dsl.preprocessing.compiler import compile_knowledge_base  # noqa: E402


def main() -> None:
    knowledge_base = compile_knowledge_base(write_legacy=True)
    summary = knowledge_base["pipeline_summary"]
    print("Knowledge compiler completed successfully.")
    print(f' - Pipeline version: {summary["pipeline_version"]}')
    print(f' - Verb entries: {summary["knowledge_stats"]["verb_entries"]}')
    print(f' - Synonym entries: {summary["knowledge_stats"]["synonym_entries"]}')
    print(f' - Dictionary entries: {summary["knowledge_stats"]["dictionary_entries"]}')
    print(f' - Phrase index entries: {summary["knowledge_stats"]["phrase_index_entries"]}')


if __name__ == "__main__":
    main()
