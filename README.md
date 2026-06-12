# MoGoStickers

Local helper scripts for building and updating a Monopoly GO sticker tracker.

## What The Scripts Do

- `makeDatabase.py` downloads the Google Sheet, keeps the first 7 columns, adds `Hana`, `Jon`, and `Nabil`, then saves `output/sticker_database.csv`.
- `gemini_vision.py` reads screenshots from `screenshots/Jon`, `screenshots/Hana`, and `screenshots/Nabil`, sends only new screenshots to Gemini, updates each user's sticker counts in `output/sticker_database.csv`, and records processed images in `screenshots/processed_screenshots.json`.
- `gemini_vision.py` validates the final counts before saving: once a user's sticker count is above zero, screenshot processing cannot save that sticker back to zero.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Set your Gemini API key:

```bash
export GEMINI_API_KEY="your_api_key_here"
```

Optional: override the model if needed.

```bash
export GEMINI_MODEL="gemini-2.5-flash-lite"
```

## Run

Create or refresh the base database:

```bash
python makeDatabase.py
```

Process screenshots and update counts:

```bash
python gemini_vision.py
```

Find grouped sticker sharing opportunities:

```bash
python tradeEngine.py
```

Trade recommendations print as a table with sender, set name, sticker name, and recipient. Gold stickers are separated at the bottom because they can only be traded during special events.

If screenshot processing would change any `Hana`, `Jon`, or `Nabil` sticker count from a positive value to `0`, the script halts with a validation error before saving `output/sticker_database.csv` or `screenshots/processed_screenshots.json`. Trade-downs such as `3` to `1` are allowed because the user still owns the sticker.

## Folder Contract

```text
screenshots/
  Hana/
  Jon/
  Nabil/
  processed_screenshots.json
output/
  sticker_database.csv
```

Only screenshots inside the user subfolders are processed. Files already present in `processed_screenshots.json` with the same SHA-256 hash are skipped.

## Tests

The tests are offline and do not call Gemini.

```bash
python -m unittest discover -s tests
```

Or use the project shortcuts:

```bash
make syntax
make test
```

If you are using the included virtual environment directly:

```bash
make test PYTHON=.venv/bin/python
```
