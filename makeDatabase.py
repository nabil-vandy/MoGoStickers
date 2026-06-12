"""Download a Google Sheet, add owner columns, and save it as a CSV."""

import os
from pathlib import Path
import pandas as pd

DOCUMENT_ID = "1SiiB8yW18kumX7hLb-6vOciIih3gKfGSPx-VPuly0Xw"
SHEET_GID = "0"

DATABASE_NAME = "sticker_database.csv"
DATABASE_PATH_ENV = os.getenv("DATABASE_PATH")
if DATABASE_PATH_ENV:
    OUTPUT_FILE = Path(DATABASE_PATH_ENV)
else:
    GDRIVE_DB_PATH = Path("/content/drive/MyDrive/1. Personal Projects/MoGoTracker/output") / DATABASE_NAME
    if GDRIVE_DB_PATH.exists():
        OUTPUT_FILE = GDRIVE_DB_PATH
    else:
        OUTPUT_FILE = Path("output") / DATABASE_NAME

OWNER_COLUMNS = ["Hana", "Jon", "Nabil"]


def google_sheet_csv_url(document_id, gid="0"):
    return (
        f"https://docs.google.com/spreadsheets/d/{document_id}/gviz/tq"
        f"?tqx=out:csv&gid={gid}"
    )


def main():
    export_url = google_sheet_csv_url(DOCUMENT_ID, SHEET_GID)

    try:
        df = pd.read_csv(export_url).iloc[:, :7]  # Take only first 7 columns
        print("Successfully fetched database from Google Sheets.")
    except Exception as e:
        print(f"Failed to fetch database from Google Sheets: {e}")
        fallback_path = Path("tests/makeDatabase_fallback.csv")
        if fallback_path.exists():
            print(f"Using local fallback file: {fallback_path}")
            df = pd.read_csv(fallback_path)
        else:
            raise RuntimeError("Could not fetch database and no local fallback file found.") from e

    for column in OWNER_COLUMNS:
        df[column] = 0

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUTPUT_FILE, index=False)

    print(f"Saved {len(df)} rows to {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
