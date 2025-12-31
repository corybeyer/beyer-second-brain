---
description: "Review recent code for errors and correct folder placement"
---

Review the files I just created or modified in this session.

## Check 1: Folder Placement

Is each file in the correct location per our structure?

| Folder | Should Contain |
|--------|----------------|
| `pipeline/` | PDF parsing, chunking, embeddings, graph building — batch ETL code |
| `app/` | Streamlit UI — models/, views/, controllers/ — MVC pattern |
| `shared/` | Database connection, config, utilities used by both |
| `scripts/` | One-off CLI tools, setup scripts |
| `infrastructure/` | Azure setup, IaC templates |

## Check 2: Code Errors

For each file, check:
- Syntax errors
- Import errors (missing dependencies)
- Type mismatches
- Obvious logic bugs

## Check 3: Standards

Per CLAUDE.md:
- Python 3.11+ with type hints
- Docstrings on public functions
- Files under 300 lines
- No hardcoded secrets

## Response Format

For each file reviewed:
```
path/to/file.py
  Placement: ✓ PASS or ✗ FAIL (reason)
  Errors:    ✓ PASS or ✗ FAIL (list issues)
  Standards: ✓ PASS or ✗ FAIL (list issues)
```

Then summarize: "X files reviewed, Y issues found"
