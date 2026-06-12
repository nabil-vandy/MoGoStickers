# Scoped Tasks

Use these task shapes to keep future Codex work focused and cheaper.

## Update The Google Sheet Import

Scope:
- `makeDatabase.py`
- `tests/` only if logic changes
- `README.md` only if commands or paths change

Avoid:
- Running Gemini
- Editing screenshot processing code

Check:

```bash
make syntax
make test
```

## Update Screenshot Processing

Scope:
- `vision_test.py`
- `tests/test_vision_test.py`
- `README.md` only if behavior changes
- `AGENTS.md` only if coding rules or invariants change

Avoid:
- Calling Gemini unless explicitly verifying live behavior
- Changing Google Sheet import code

Check:

```bash
make syntax
make test
```

## Refresh The Database

Scope:
- Runtime only, no code edits unless the command fails because of code

Command:

```bash
make database
```

## Process New Screenshots

Scope:
- Runtime only, no code edits unless the command fails because of code

Requirements:
- `GEMINI_API_KEY` must be set
- Images should be inside `screenshots/Hana`, `screenshots/Jon`, or `screenshots/Nabil`

Command:

```bash
make process
```
