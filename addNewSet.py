"""Check the Google Sheet for new stickers and append them to the database with 0 counts."""

import os
import sys
import pandas as pd
from pathlib import Path
import subprocess

DOCUMENT_ID = "1SiiB8yW18kumX7hLb-6vOciIih3gKfGSPx-VPuly0Xw"
SHEET_GID = "0"

DATABASE_NAME = "sticker_database.csv"
OWNER_COLUMNS = ["Hana", "Jon", "Nabil"]


def google_sheet_csv_url(document_id, gid="0"):
    return (
        f"https://docs.google.com/spreadsheets/d/{document_id}/gviz/tq"
        f"?tqx=out:csv&gid={gid}"
    )


def get_database_path():
    database_path_env = os.getenv("DATABASE_PATH")
    if database_path_env:
        return Path(database_path_env)
    
    gdrive_db_path = Path("/content/drive/MyDrive/1. Personal Projects/MoGoTracker/output") / DATABASE_NAME
    if gdrive_db_path.exists():
        return gdrive_db_path
    return Path("output") / DATABASE_NAME


def main():
    export_url = google_sheet_csv_url(DOCUMENT_ID, SHEET_GID)
    output_file = get_database_path()
    
    print("Fetching current database structure from Google Sheets...")
    try:
        df_sheet = pd.read_csv(export_url).iloc[:, :7]  # Take only first 7 columns
    except Exception as e:
        print(f"Failed to fetch database from Google Sheets: {e}")
        sys.exit(1)

    if not output_file.exists():
        print(f"Local database file not found at: {output_file}")
        print("Initializing new local database with Google Sheets content and 0 counts...")
        for column in OWNER_COLUMNS:
            df_sheet[column] = 0
        output_file.parent.mkdir(parents=True, exist_ok=True)
        df_sheet.to_csv(output_file, index=False)
        print(f"Saved {len(df_sheet)} rows to {output_file}")
        return

    # Load existing local database
    print(f"Loading existing database from {output_file}...")
    df_local = pd.read_csv(output_file)

    # Standardize types for comparison
    df_sheet['MoGo_ID'] = pd.to_numeric(df_sheet['MoGo_ID'], errors='coerce')
    df_local['MoGo_ID'] = pd.to_numeric(df_local['MoGo_ID'], errors='coerce')

    existing_ids = set(df_local['MoGo_ID'].dropna().astype(int))
    existing_names = set(df_local['Sticker_Name'].str.lower().str.strip())

    new_rows = []
    for idx, row in df_sheet.iterrows():
        name = row['Sticker_Name']
        if pd.isna(name):
            continue
        name_clean = str(name).lower().strip()
        mogo_id = row['MoGo_ID']

        is_new = False
        if not pd.isna(mogo_id):
            if int(mogo_id) not in existing_ids:
                is_new = True
        else:
            if name_clean not in existing_names:
                is_new = True

        if is_new:
            new_rows.append(row)

    if not new_rows:
        print("No new stickers found in the Google Sheet. Everything is up to date!")
        return

    print(f"Found {len(new_rows)} new stickers to add:")
    for r in new_rows:
        print(f" - {r['Sticker_Name']} (Set: {r['Set_Name']}, ID: {r['MoGo_ID']})")

    # Create DataFrame for new rows and set default count for users to 0
    df_new = pd.DataFrame(new_rows)
    for col in OWNER_COLUMNS:
        df_new[col] = 0

    # Append new rows to local database
    df_updated = pd.concat([df_local, df_new], ignore_index=True)
    df_updated.to_csv(output_file, index=False)
    print(f"Successfully appended new stickers to local database '{output_file}'.")

    # Sync to Supabase if config exists
    supabase_url = os.getenv("SUPABASE_URL")
    supabase_key = os.getenv("SUPABASE_KEY")
    if supabase_url and supabase_key:
        print("Supabase config detected. Running migrate_to_supabase.py to sync new stickers...")
        python_exe = sys.executable
        try:
            result = subprocess.run([python_exe, "migrate_to_supabase.py"], capture_output=True, text=True)
            print(result.stdout)
            if result.returncode != 0:
                print(f"Sync error (return code {result.returncode}):\n{result.stderr}")
                sys.exit(result.returncode)
        except Exception as e:
            print(f"Failed to run migration script: {e}")
            sys.exit(1)


if __name__ == "__main__":
    main()
