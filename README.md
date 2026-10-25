# Normie

**Normie** is an AI-assisted relational database schema normalizer. Give it a plain-English domain description or a denormalized `CREATE TABLE` statement, and it produces a normalized schema, SQL DDL, an explanation of every split, and an ER-diagram description.

The AI extracts likely entities and functional dependencies; the normalization decisions themselves are deterministic Python code. This makes the result explainable and suitable for an Advanced SQL course demonstration.

## Features

- Accepts either natural-language requirements or existing SQL DDL.
- Parses existing `CREATE TABLE` columns with `sqlparse` before LLM extraction.
- Validates Groq JSON output with Pydantic and retries invalid responses.
- Uses fallback Groq models when the configured model is unavailable or rejects JSON mode.
- Computes closures, candidate keys, normal-form findings, and decompositions locally.
- Generates 3NF by default, with an optional BCNF mode.
- Produces relation cards, SQL `CREATE TABLE` statements, a plain-text report, and Mermaid ERD text.
- Includes a web interface, FastAPI/Swagger endpoints, CLI demos, and automated tests.

## Architecture

```text
Prose or SQL DDL
      │
      ▼
Input detection + DDL parser
      │
      ▼
Groq extraction + Pydantic validation
      │
      ▼
Deterministic normalization engine
closure → candidate keys → 1NF/2NF/3NF/BCNF → decomposition
      │
      ▼
Optional semantic verifier → SQL + report + Mermaid ERD
```

## Project layout

```text
Normie/
├── app/
│   ├── models.py             # Pydantic contracts between all stages
│   ├── normalization.py      # Deterministic closure, keys, 3NF/BCNF logic
│   ├── input_layer.py        # CREATE TABLE vs prose detection
│   ├── ddl_parser.py         # sqlparse-backed CREATE TABLE column parser
│   ├── extraction.py         # Groq JSON mode + validation/retry
│   ├── groq_config.py        # Model default and fallback policy
│   ├── verifier.py           # Optional semantic Groq review
│   ├── output.py             # CREATE TABLE and text-report formatting
│   ├── pipeline.py           # End-to-end orchestration
│   └── api.py                # FastAPI endpoints
├── tests/                    # Normalization, API, and pipeline tests
├── main.py                   # Terminal demo for both sample inputs
├── .env.example
└── requirements.txt
```

## Setup

Use Python 3.11.

After cloning the repository, run:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

## Final demo

Start the application and open the local interface:

```powershell
uvicorn app.api:app --reload
```

Open `http://127.0.0.1:8000/`, choose **Load text demo** or **Load SQL demo**, and click **Normalize schema**. The result includes relation cards, SQL DDL, a normalization explanation, and Mermaid ERD text. Swagger remains available at `http://127.0.0.1:8000/docs` for the API-level demonstration.

Edit `.env` and set `GROQ_API_KEY=gsk_...`. `python-dotenv` loads it inside the extraction and verifier services. Do not commit `.env`.

```env
GROQ_API_KEY=gsk_your_key_here
GROQ_MODEL=openai/gpt-oss-20b
```

If the selected Groq model is unavailable or cannot satisfy JSON mode, Normie tries a supported fallback model. Your `.env` is already excluded by `.gitignore`.

For a live Groq run, create the file from the example and add your own key locally:

```powershell
Copy-Item .env.example .env
notepad .env
```

The browser interface shows **Groq connected** when it detects the key. With a key, custom natural-language and SQL DDL inputs use Groq extraction; enabling the verifier permits one bounded extraction-and-normalization refinement pass.

Run the two offline-safe demos (they use curated, validated demo extractions so no API key is needed):

```powershell
python main.py --sample free-text
python main.py --sample sql
pytest -q
```

Start the API:

```powershell
uvicorn app.api:app --reload
```

Open `http://127.0.0.1:8000/docs` for FastAPI's interactive endpoint tester. The base URL opens the browser interface.

`GET /examples` returns the two offline-safe sample inputs. `POST /analyze` returns extraction only. `POST /normalize` returns all stages, including SQL, report, and a Mermaid ER diagram. `POST /report` returns the final rendered output. For arbitrary input, configure `GROQ_API_KEY`; use `allow_demo_fallback: true` only for the built-in samples.

| Method | Endpoint | Purpose |
| --- | --- | --- |
| `GET` | `/` | Browser interface |
| `GET` | `/health` | Service and Groq configuration status |
| `GET` | `/examples` | Built-in text and SQL examples |
| `POST` | `/analyze` | Extraction stage only |
| `POST` | `/normalize` | Full normalization pipeline |
| `POST` | `/report` | SQL and report output |
| `GET` | `/docs` | Swagger UI |

```powershell
curl.exe -X POST http://127.0.0.1:8000/normalize -H "Content-Type: application/json" -d '{"text":"Students enroll in courses each semester. A student has a name and email. Each course has a title and is taught by one instructor. An instructor has a name. For each student, course, and semester, store the final grade.","allow_demo_fallback":true}'
```

## How the deterministic engine works

**Attribute closure.** For a starting set `X`, `attribute_closure` repeatedly applies every FD whose left side is already contained in the closure. It stops when a full pass adds nothing. If `X+` contains every relation attribute, `X` is a superkey.

**Candidate keys.** Attributes that never appear on an FD right-hand side cannot be derived, so every key must contain them. The engine adds combinations of the remaining attributes from smallest to largest, retains a set only when its closure covers all attributes, and skips every superset of a key already found. Therefore every returned superkey is minimal.

**Normal-form checks.** A multi-valued attribute is a 1NF finding. For every composite candidate key, an FD from a proper subset of that key to a non-prime attribute is a 2NF partial dependency. An FD whose determinant is not a superkey and whose dependent is non-prime is a 3NF violation and, by definition, a BCNF violation.

**3NF decomposition.** The engine first computes a minimal cover: split each RHS into singleton attributes, minimize determinant sides, then remove redundant dependencies. It creates one relation for every remaining `X ∪ Y`, discards subset relations, and adds a candidate-key relation if none contains one. This is the standard dependency-preserving, lossless 3NF synthesis pattern.

**BCNF option.** With `--bcnf` or `target_normal_form: "BCNF"`, it repeatedly finds a violating `X -> Y` and splits `R` into `X ∪ Y` and `R - (Y - X)`. BCNF can lose dependency preservation, so 3NF remains the default for the course demo.

## Groq safety boundary

The extractor sends parsed DDL columns to Groq whenever input is SQL, uses `response_format={"type": "json_object"}`, validates the response with Pydantic, rejects invented DDL columns, and re-prompts once if parsing or validation fails. JSON mode guarantees JSON syntax rather than schema adherence, which is why the local validation/retry remains necessary. The verifier is advisory in this pass: it flags semantic concerns but does not silently modify the FD set. A reviewer or user must confirm changed business rules before re-running deterministic normalization.

## Example result

For the built-in enrolment example, Normie identifies the dependencies below:

```text
student_id -> student_name, student_email
course_id -> course_title, instructor_id
instructor_id -> instructor_name
student_id, course_id, semester -> grade
```

It then separates the original wide relation into these typical relations:

```text
students(student_id PK, student_name, student_email)
instructors(instructor_id PK, instructor_name)
courses(course_id PK, course_title, instructor_id FK)
enrollment_record(student_id PK/FK, course_id PK/FK, semester PK, grade)
```

The report explains that student, course, and instructor facts are split out because they depend on only part of the composite enrolment key—or on another non-key attribute.

## Testing

Run the automated suite after installation:

```powershell
python -m pytest -q
```

The test suite covers closure computation, candidate-key detection, 1NF/2NF/3NF behavior, DDL parsing, endpoint contracts, refinement flow, and model fallback logic.

## Limitations

- Functional dependencies inferred from prose are hypotheses and should be checked against real business rules.
- The verifier is advisory and refinement is capped to avoid endless loops.
- SQL types, table names, and foreign-key choices use practical heuristics and may need domain-specific adjustments.
- This is a course-project prototype, so it intentionally has no user authentication, persistence, or production deployment setup.


## Tech stack

Python 3.11 · FastAPI · Pydantic · Groq SDK · sqlparse · python-dotenv · pytest
