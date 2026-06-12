"""Download a Google Sheet, add owner columns, and save it as a CSV."""

from pathlib import Path

import pandas as pd


DOCUMENT_ID = "1SiiB8yW18kumX7hLb-6vOciIih3gKfGSPx-VPuly0Xw"
SHEET_GID = "0"
OUTPUT_DIR = Path("output")
OUTPUT_FILE = OUTPUT_DIR / "sticker_database.csv"

OWNER_COLUMNS = ["Hana", "Jon", "Nabil"]


def google_sheet_csv_url(document_id, gid="0"):
    return (
        f"https://docs.google.com/spreadsheets/d/{document_id}/gviz/tq"
        f"?tqx=out:csv&gid={gid}"
    )


def main():
    export_url = google_sheet_csv_url(DOCUMENT_ID, SHEET_GID)

    df = pd.read_csv(export_url).iloc[:, :7] #Take only first 7 rows

    for column in OWNER_COLUMNS:
        df[column] = 0

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUTPUT_FILE, index=False)

    print(f"Saved {len(df)} rows to {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
