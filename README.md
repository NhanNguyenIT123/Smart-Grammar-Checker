# Smart Grammar Checker using DSL and Rule-Based Parsing

GrammarDSL is a **DSL-driven grammar learning platform** built around:

- an ANTLR lexer/parser for command input
- a rule-based grammar checker
- a local exercise generator with a vast bank of millions of permutations
- tutor/student classroom flows backed by SQLite

It supports grammar checking, personalized revision history, exercise generation, quiz creation, quiz submission, and tutor scorebook queries.

## What the system does

- `check grammar <paragraph>` checks spelling, grammar, and semantic collocations, then returns a corrected rewrite.
- `generate ...` creates local practice exercises from feature expressions such as `present simple AND affirmative`.
- tutors can create classes and quizzes
- students can join classes and submit quiz answers
- tutors can query scorebook rows with DSL filters such as `show students with score > 8 AND submitted`

## Architecture

```mermaid
flowchart LR
    Sources["Raw Sources<br/>rules + lexical packs + exercise blueprints"] --> Preprocess["Preprocessing Compiler"]
    Preprocess --> KB["Compiled Knowledge Base<br/>+ exercise artifacts"]

    User["Tutor / Student"] --> UI["React Workspace"]
    UI --> API["Python HTTP API"]
    API --> Parser["ANTLR Lexer + Parser"]
    Parser --> AST["AST Builder / Visitor"]
    AST --> Service["CommandService"]
    KB --> Service
    Service --> Checker["Grammar / Spelling / Synonym / Verb Engines"]
    Service --> Generator["Exercise Generator"]
    Service --> Grader["Quiz Grader"]
    Service --> Store["SQLite Store"]
    Store --> UI
    Checker --> UI
    Generator --> UI
    Grader --> UI
```

## Technology stack

| Layer | Tech |
|---|---|
| Frontend | React + Vite |
| Backend API | Python `BaseHTTPRequestHandler` / `ThreadingHTTPServer` |
| Parsing | ANTLR 4 |
| Persistence | SQLite |
| Grammar analysis | Rule-based heuristics + compiled knowledge packs, optional spaCy/local ML enrichment |
| Exercise generation | Local template + lexical-pool + morphology pipeline |

## Supported DSL commands

### Common commands

- `help`
- `check grammar <paragraph>`
- `generate exercise with <feature-expr>`
- `generate <N> exercises with <feature-expr>`
- `revision plan`
- `history`
- `reset history`
- `spell <word>`
- `verb <word>`
- `synonym <word>`

### Tutor-only commands

- `create quiz "Title" generate <N> exercises with <feature-expr>`
- `show students with <filter-expr>`
- `show class <class-id>`
- `show quiz <quiz-id>`
- `show results for student <username>`

### Student-only commands

- `submit answers for quiz <quiz-id> { 1 = "..." ; 2 = "..." }`

## Feature expressions

V2 exercise generation supports **all 12 English tenses** and advanced grammatical conditions:

- **Tenses**: `present simple`, `past simple`, `future simple`, `present continuous`, `past continuous`, `future continuous`, `present perfect`, `past perfect`, `future perfect`, `present perfect continuous`, `past perfect continuous`, `future perfect continuous`
- **Grammar**: `subject-verb agreement`, `object pronoun`, `verb-preposition`, `svo`
- **Sentence Forms**: `affirmative`, `negative`, `interrogative`

Boolean composition is supported with `AND`, `OR`, and parentheses.

Examples:

- `generate exercise with present simple`
- `generate 10 exercises with present perfect AND negative`
- `generate 10 exercises with (past simple AND interrogative) OR (present perfect continuous AND affirmative)`

## Running the project

Run everything from the **project root**:

```powershell
cd C:\GITHUB\Smart-Grammar-Checker-using-DSL-and-Rule-Based-Parsing
```

### 1. Install backend and frontend dependencies

```powershell
python -m pip install -e backend
npm install
```

### 2. Generate ANTLR artifacts

Only needed when the grammar changes:

```powershell
python backend/run.py gen
```

### 3. Compile the knowledge base

**CRITICAL**: Run this to refresh the exercise bank and grammar rules.

```powershell
python backend/run.py compile
```

### 4. Start the backend

```powershell
python backend/run.py serve --host 127.0.0.1 --port 8000
```

### 5. Start the frontend

Open a second terminal:

```powershell
cd C:\GITHUB\Smart-Grammar-Checker-using-DSL-and-Rule-Based-Parsing
npm run dev
```

Then open:

- [http://localhost:5173/grammar](http://localhost:5173/grammar)

## Demo accounts

Tutor accounts:

- `brian / brian123`
- `emma / emma123`

Student accounts:

- `alice / alice123`
- `clara / clara123`
- `david / david123`

You can also create a new **demo student** from the register page.

## Suggested demo flow

1. `help`
2. `check grammar The teacher have some book.`
3. `generate 10 exercises with (present simple AND affirmative) OR (past simple AND negative)`
4. tutor creates a class and runs `create quiz "Final Exam" generate 20 exercises with present perfect`
5. student joins the class and submits answers
6. tutor runs `show students with score > 80% AND submitted`

## Current scope notes

- The platform is intentionally **rule-based and local-first**.
- No external LLM or API is required for exercise generation.
- The exercise generator uses a **lexical pool of 280+ verbs and 120+ objects** creating millions of unique sentence permutations to prevent repetition.
- Quiz grading is **answer-key first**; grammar checking is used as feedback support.

## Optional NLP / PyTorch upgrade

The repository includes a lightweight, opt-in grammar error correction pipeline under `backend/ml/`.

- `backend/ml/scripts/prepare_gec_dataset.py` normalizes local `.jsonl`, `.csv`, or `.m2` sentence-pair datasets.
- `backend/ml/scripts/train_gec_t5.py` fine-tunes a small T5 model with PyTorch/Hugging Face.
- `backend/ml/scripts/evaluate_gec.py` reports lightweight exact-match and changed-rate metrics.
- `backend/src/grammar_dsl/services/local_ml.py` connects a trained local model to the existing grammar check flow.

The local ML backend is disabled by default. Enable it only after training or placing a model at `backend/ml/models/gec_t5_small`:

```powershell
$env:GRAMMAR_CHECK_ENABLE_LOCAL_ML="1"
python backend/run.py serve --host 127.0.0.1 --port 8000
```

For RTX 3050 6GB-class machines, start with `t5-small`, `batch-size=1`, `gradient-accumulation-steps=8`, `max_length=128`, and 5k-10k sentence pairs.
