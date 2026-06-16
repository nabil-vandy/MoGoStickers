# MoGoStickers

Local helper scripts for building and updating a Monopoly GO sticker tracker.

## What The Scripts Do

- `makeDatabase.py` downloads the master Google Sheet, keeps the first 7 columns, adds `Hana`, `Jon`, and `Nabil`, then saves `output/sticker_database.csv`.
- `gemini_vision.py` processes new screenshots and updates each user's sticker counts in `output/sticker_database.csv`.
  * **Direct Ingest (Primary)**: If `google_creds.json` is present, it reads the Google Form response spreadsheet, extracts Google Drive image links, downloads the screenshots in-memory, maps them to users based on email, and updates the database.
  * **Local Folder Ingest (Fallback)**: If credentials are not present, it falls back to reading screenshots from `screenshots/Jon`, `screenshots/Hana`, and `screenshots/Nabil`.
  * Records all completed uploads (using Google Drive File ID or local filename hash) in `screenshots/processed_screenshots.json`.
  * Validates the final counts before saving: once a user's sticker count is above zero, screenshot processing cannot save that sticker back to zero.

## Setup

1. **Initialize Virtual Environment & Install Dependencies**:
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   python -m pip install --upgrade pip
   python -m pip install -r requirements.txt
   ```
2. **Setup Credentials**:
   * Put your Google service account credentials file in the root folder as `google_creds.json`.
3. **Set your Gemini API key**:
   ```bash
   export GEMINI_API_KEY="your_api_key_here"
   ```
4. **Set Google Ingest sheet ID (Optional)**:
   ```bash
   export INGEST_SHEET_ID="1lRwalTc96V1-VkECfoh3xWOo4gcVY5qctMzH5Q0_aUY"
   ```

## Run

All execution commands automatically detect and run inside the virtual environment `.venv`.

1. **Create or refresh the base database**:
   ```bash
   make database
   ```
2. **Process new screenshots and update counts**:
   ```bash
   make process
   ```
3. **Find grouped sticker sharing opportunities**:
   * Check matches directly in the terminal:
     ```bash
     .venv/bin/python tradeEngine.py
     ```
   * Or run the orchestrated pipeline (updates database, checks matches, and sends email alerts):
     ```bash
     .venv/bin/python run_pipeline.py
     ```

## Folder Contract

```text
google_creds.json           # Private service account key (git-ignored)
screenshots/
  processed_screenshots.json # Tracking history of processed images
output/
  sticker_database.csv       # Working database output
```

## Tests

The tests are offline and do not call Gemini.

```bash
make test
```

