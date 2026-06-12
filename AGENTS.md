# Codex Guide

## Project Purpose

This repo tracks Monopoly GO sticker ownership for three users: `Hana`, `Jon`, and `Nabil`.

## Important Files

- `makeDatabase.py`: pulls the Google Sheet into `output/sticker_database.csv`.
- `vision_test.py`: processes screenshot folders and updates user counts.
- `output/sticker_database.csv`: working CSV database.
- `screenshots/processed_screenshots.json`: local history used to skip screenshots already processed.
- `tests/`: offline tests. These should never call Gemini.

## Commands

Use these commands before and after edits:

```bash
python -B -c 'source = open("vision_test.py").read(); compile(source, "vision_test.py", "exec")'
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
python vision_test.py
```

`vision_test.py` requires `GEMINI_API_KEY` and may spend Gemini quota. Prefer offline tests for normal code changes.

## Coding Notes

- Keep output paths using `output/`, not `outputs/`.
- Keep processed screenshot history in `screenshots/processed_screenshots.json`.
- Do not hard-code API keys.
- Do not move screenshot images into the repo root; process only `screenshots/Hana`, `screenshots/Jon`, and `screenshots/Nabil`.
- Once `Hana`, `Jon`, or `Nabil` has a sticker count above zero, screenshot processing must never save that sticker back to zero.
- Avoid broad rewrites. This is a small script project, so simple functions are preferred.

## Efficient Task Boundaries

- Database import tasks should usually touch only `makeDatabase.py`, `README.md`, and tests if needed.
- Screenshot/Gemini tasks should usually touch only `vision_test.py`, `README.md`, and tests.
- Environment or onboarding tasks should usually touch only `README.md`, `AGENTS.md`, `.env.example`, `.gitignore`, `requirements.txt`, or `Makefile`.
