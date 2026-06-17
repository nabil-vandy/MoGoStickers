# Codex Guide

## Project Purpose

This repo tracks Monopoly GO sticker ownership for three users: `Hana`, `Jon`, and `Nabil`.
The production web dashboard is deployed at [mogostickers.streamlit.app](https://mogostickers.streamlit.app).


## Important Files

- `app.py`: Real-time interactive Streamlit web dashboard.
- `migrate_to_supabase.py`: Migration script that pushes local CSV counts database to Supabase.
- `makeDatabase.py`: pulls the Google Sheet into `output/sticker_database.csv`.
- `gemini_vision.py`: processes screenshot folders and updates user counts.
- `output/sticker_database.csv`: working CSV database.
- `screenshots/processed_screenshots.json`: local history used to skip screenshots already processed.
- `tests/`: offline tests. These should never call Gemini.

## Commands

Use these commands before and after edits:

```bash
make syntax
make test
```

Start the Streamlit web app:
```bash
make run
```

Run the pipeline only when the user asks or when explicitly verifying runtime behavior:
```bash
python makeDatabase.py
python gemini_vision.py
```

## Coding Notes

- Keep output paths using `output/`, not `outputs/`.
- Keep processed screenshot history in `screenshots/processed_screenshots.json`.
- Do not hard-code API keys.
- Do not move screenshot images into the repo root; process only `screenshots/Hana`, `screenshots/Jon`, and `screenshots/Nabil`.
- Once `Hana`, `Jon`, or `Nabil` has a sticker count above zero, screenshot processing must never save that sticker back to zero.
- Avoid broad rewrites. This is a small project, so simple functions are preferred.

## Token Efficiency Guidelines

To optimize token usage and context window efficiency:
- **Avoid broad file reads**: Do not call `view_file` on entire source files unless necessary. Always target specific line ranges using `StartLine` and `EndLine`.
- **Prefer targeted file replacements**: Use `replace_file_content` to edit single contiguous blocks. Avoid `write_to_file` on existing files as full-file rewrites waste token quota.
- **Minimize command executions**: Do not repeatedly run informational commands (like `ls`, `pwd`, or `git diff`) if you can remember the structure or state.
- **Response Conciseness**: Keep your conversational outputs structured, short, and to the point. Rely on the walkthrough and implementation plan artifacts to convey detailed technical specifications.

## Task Boundary Guides

Use these task shapes to keep future Codex work focused and cheaper:

### Update Web Application Layout/Styling
* **Scope:**
  * `app.py`
  * `AGENTS.md` only if coding rules change
  * `README.md` only if config instructions change
* **Avoid:**
  * Editing backend scripts (`gemini_vision.py`, `makeDatabase.py`)
* **Check:**
  ```bash
  make syntax
  ```

### Sync Database to Supabase
* **Scope:**
  * `migrate_to_supabase.py`
* **Command:**
  ```bash
  .venv/bin/python migrate_to_supabase.py
  ```

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

## Communication Guidelines

To help the user work effectively:
- **Structure**: First, explain the problem or concept clearly. Then, provide clear, numbered steps on how to fix or set up the solution.
- **Pacing**: Always wait for the user to complete those steps and confirm before moving forward to implementation or the next phase. Do not rush ahead or execute steps before the user has completed their part.
