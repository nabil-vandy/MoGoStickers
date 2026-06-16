# Codex Guide

## Project Purpose

This repo tracks Monopoly GO sticker ownership for three users: `Hana`, `Jon`, and `Nabil`.

## Important Files

- `makeDatabase.py`: pulls the Google Sheet into `output/sticker_database.csv`.
- `gemini_vision.py`: processes screenshot folders and updates user counts.
- `output/sticker_database.csv`: working CSV database.
- `screenshots/processed_screenshots.json`: local history used to skip screenshots already processed.
- `tests/`: offline tests. These should never call Gemini.

## Commands

Use these commands before and after edits:

```bash
python -B -c 'source = open("gemini_vision.py").read(); compile(source, "gemini_vision.py", "exec")'
python -B -c 'source = open("makeDatabase.py").read(); compile(source, "makeDatabase.py", "exec")'
python -m unittest discover -s tests
```

Equivalent shortcuts:

```bash
make syntax
make test
```

Run the app only when the user asks or when explicitly verifying runtime behavior:

```bash
python makeDatabase.py
python gemini_vision.py
```

`gemini_vision.py` requires `GEMINI_API_KEY` and may spend Gemini quota. Prefer offline tests for normal code changes.

## Coding Notes

- Keep output paths using `output/`, not `outputs/`.
- Keep processed screenshot history in `screenshots/processed_screenshots.json`.
- Do not hard-code API keys.
- Do not move screenshot images into the repo root; process only `screenshots/Hana`, `screenshots/Jon`, and `screenshots/Nabil`.
- Once `Hana`, `Jon`, or `Nabil` has a sticker count above zero, screenshot processing must never save that sticker back to zero.
- Avoid broad rewrites. This is a small script project, so simple functions are preferred.

## Efficient Task Boundaries

- Database import tasks should usually touch only `makeDatabase.py`, `README.md`, and tests if needed.
- Screenshot/Gemini tasks should usually touch only `gemini_vision.py`, `README.md`, and tests.
- Environment or onboarding tasks should usually touch only `README.md`, `AGENTS.md`, `.env.example`, `.gitignore`, `requirements.txt`, or `Makefile`.

## Task Boundary Guides

Use these task shapes to keep future Codex work focused and cheaper:

### Update The Google Sheet Import
* **Scope:**
  * `makeDatabase.py`
  * `tests/` only if logic changes
  * `README.md` only if commands or paths change
* **Avoid:**
  * Running Gemini
  * Editing screenshot processing code
* **Check:**
  ```bash
  make syntax
  make test
  ```

### Update Screenshot Processing
* **Scope:**
  * `gemini_vision.py`
  * `tests/test_gemini_vision.py`
  * `README.md` only if behavior changes
  * `AGENTS.md` only if coding rules or invariants change
* **Avoid:**
  * Calling Gemini unless explicitly verifying live behavior
  * Changing Google Sheet import code
* **Check:**
  ```bash
  make syntax
  make test
  ```

### Refresh The Database
* **Scope:** Runtime only, no code edits unless the command fails because of code.
* **Command:**
  ```bash
  make database
  ```

### Process New Screenshots
* **Scope:** Runtime only, no code edits unless the command fails because of code.
* **Requirements:**
  * `GEMINI_API_KEY` must be set
  * Images should be inside `screenshots/Hana`, `screenshots/Jon`, or `screenshots/Nabil`
* **Command:**
  ```bash
  make process
  ```

## Communication Guidelines

To help the user work effectively:
- **Structure**: First, explain the problem or concept clearly. Then, provide clear, numbered steps on how to fix or set up the solution.
- **Pacing**: Always wait for the user to complete those steps and confirm before moving forward to implementation or the next phase. Do not rush ahead or execute steps before the user has completed their part.

