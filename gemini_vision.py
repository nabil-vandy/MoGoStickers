"""Process user screenshot folders and update the sticker database CSV."""

from pathlib import Path
import gc
import hashlib
import json
import mimetypes
import os
import time
import io
from urllib.parse import urlparse, parse_qs

import pandas as pd
from google.genai import types
from pydantic import BaseModel
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload



class StickerInfo(BaseModel):
    name: str
    count: int


class SetInfo(BaseModel):
    set_name: str
    set_number: str
    stickers: list[StickerInfo]


SCREENSHOTS_DIR_ENV = os.getenv("SCREENSHOTS_DIR")
if SCREENSHOTS_DIR_ENV:
    SCREENSHOTS_DIR = Path(SCREENSHOTS_DIR_ENV)
else:
    GDRIVE_PATH = Path("/content/drive/MyDrive/1. Personal Projects/MoGoTracker/screenshots")
    if GDRIVE_PATH.exists():
        SCREENSHOTS_DIR = GDRIVE_PATH
    else:
        SCREENSHOTS_DIR = Path("screenshots")

OUTPUT_DIR = Path("output")
DATABASE_NAME = "sticker_database.csv"

DATABASE_PATH_ENV = os.getenv("DATABASE_PATH")
if DATABASE_PATH_ENV:
    DATABASE_PATH = Path(DATABASE_PATH_ENV)
else:
    GDRIVE_DB_PATH = Path("/content/drive/MyDrive/1. Personal Projects/MoGoTracker/output") / DATABASE_NAME
    if GDRIVE_DB_PATH.exists():
        DATABASE_PATH = GDRIVE_DB_PATH
    else:
        DATABASE_PATH = OUTPUT_DIR / DATABASE_NAME

PROCESSED_LOG_ENV = os.getenv("PROCESSED_LOG")
if PROCESSED_LOG_ENV:
    PROCESSED_LOG = Path(PROCESSED_LOG_ENV)
else:
    PROCESSED_LOG = SCREENSHOTS_DIR / "processed_screenshots.json"

USERS = ["Jon", "Hana", "Nabil"]
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg"}

MODEL_NAME = os.getenv("GEMINI_MODEL", "gemini-3.1-flash-lite")
MAX_ATTEMPTS = 3
IMAGE_CHUNK_SIZE = 15
CHUNK_PAUSE_SECONDS = 65

EMAIL_TO_USER = {
    "jonlucc@gmail.com": "Jon",
    "salehn1@gmail.com": "Nabil",
    "hana.m.priscu@gmail.com": "Hana",
}


def extract_drive_file_id(url):
    url = url.strip()
    if not url:
        return None
    try:
        parsed = urlparse(url)
        if "open" in parsed.path or "file" in parsed.path:
            queries = parse_qs(parsed.query)
            if "id" in queries:
                return queries["id"][0]
        path_parts = parsed.path.split("/")
        if "d" in path_parts:
            d_idx = path_parts.index("d")
            if d_idx + 1 < len(path_parts):
                return path_parts[d_idx + 1]
    except Exception:
        pass
    return None


def download_drive_file(file_id):
    creds_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "google_creds.json")
    if not os.path.exists(creds_path):
        raise FileNotFoundError(f"Credentials file not found at {creds_path}")
        
    creds = service_account.Credentials.from_service_account_file(
        creds_path,
        scopes=["https://www.googleapis.com/auth/drive.readonly"]
    )
    drive_service = build("drive", "v3", credentials=creds)
    
    request = drive_service.files().get_media(fileId=file_id)
    fh = io.BytesIO()
    downloader = MediaIoBaseDownload(fh, request)
    done = False
    while not done:
        _, done = downloader.next_chunk()
        
    return fh.getvalue()



def find_database_path():
    if DATABASE_PATH.exists():
        return DATABASE_PATH
    raise FileNotFoundError(
        f"Could not find {DATABASE_PATH.name} at {DATABASE_PATH}. "
        "Run makeDatabase.py first."
    )


def load_processed_log():
    if not PROCESSED_LOG.exists():
        return {}

    with PROCESSED_LOG.open("r", encoding="utf-8") as file:
        return json.load(file)


def save_processed_log(processed):
    PROCESSED_LOG.parent.mkdir(parents=True, exist_ok=True)
    with PROCESSED_LOG.open("w", encoding="utf-8") as file:
        json.dump(processed, file, indent=2, sort_keys=True)


def file_hash(path):
    try:
        from PIL import Image
        with Image.open(path) as img:
            width, height = img.size
            top = int(height * 0.20)
            bottom = int(height * (1.0 - 0.12))
            cropped = img.crop((0, top, width, bottom))
            
            digest = hashlib.sha256()
            digest.update(cropped.tobytes())
            return digest.hexdigest()
    except Exception:
        digest = hashlib.sha256()
        with path.open("rb") as file:
            for chunk in iter(lambda: file.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()


def safe_parse_json(text):
    text = text.strip().replace("```json", "").replace("```", "")

    start = text.find("{")
    end = text.rfind("}") + 1

    if start == -1 or end == 0:
        raise ValueError(f"No JSON object found in Gemini response: {text}")

    return json.loads(text[start:end])


def extract_stickers_from_image(client, image_data):
    if isinstance(image_data, bytes):
        image_bytes = image_data
        mime_type = "image/png"
    else:
        mime_type = mimetypes.guess_type(image_data.name)[0] or "image/png"
        with image_data.open("rb") as file:
            image_bytes = file.read()

    prompt = """
Extract the Monopoly GO stickers visible in this screenshot.

Rules:
- Include only stickers the user owns or has copies of in the image.
- "count" should be the total number shown for that sticker in the image.
- If the image shows a duplicate count such as +1, return 2 total.
- Keep sticker names exactly as they appear when possible.
"""

    try:
        for attempt in range(1, MAX_ATTEMPTS + 1):
            try:
                response = client.models.generate_content(
                    model=MODEL_NAME,
                    contents=[
                        {
                            "role": "user",
                            "parts": [
                                {"text": prompt},
                                {
                                    "inline_data": {
                                        "mime_type": mime_type,
                                        "data": image_bytes,
                                    }
                                },
                            ],
                        }
                    ],
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                        response_schema=SetInfo,
                    ),
                )
                return json.loads(response.text)
            except Exception as error:
                error_str = str(error)
                if ("429" in error_str or "503" in error_str) and attempt < MAX_ATTEMPTS:
                    print(f"Gemini API returned transient error (Rate limit / High demand). Waiting {CHUNK_PAUSE_SECONDS}s before retrying (Attempt {attempt} of {MAX_ATTEMPTS})...")
                    time.sleep(CHUNK_PAUSE_SECONDS)
                    continue
                raise

    finally:
        del image_bytes



def normalize_name(value):
    return str(value).strip().casefold()


def update_database(df, user, extracted_data):
    if user not in df.columns:
        df[user] = 0

    updated = 0
    missing = []

    for sticker in extracted_data.get("stickers", []):
        sticker_name = str(sticker.get("name", "")).strip()
        if not sticker_name:
            continue

        try:
            count = int(sticker.get("count", 0))
        except (TypeError, ValueError):
            count = 0

        mask = df["Sticker_Name"].map(normalize_name) == normalize_name(sticker_name)

        if mask.any():
            df.loc[mask, user] = count
            updated += int(mask.sum())
        else:
            missing.append(sticker_name)

    return updated, missing


def find_zero_regressions(previous_df, updated_df, users):
    regressions = []

    for user in users:
        if user not in updated_df.columns:
            continue

        if user in previous_df.columns:
            previous_values = previous_df[user]
        else:
            previous_values = pd.Series(0, index=updated_df.index)

        previous_counts = pd.to_numeric(previous_values, errors="coerce")
        previous_counts = previous_counts.reindex(updated_df.index, fill_value=0).fillna(0)
        updated_counts = pd.to_numeric(updated_df[user], errors="coerce").fillna(0)

        regressed_rows = (previous_counts > 0) & (updated_counts == 0)

        for index in updated_df.index[regressed_rows]:
            regressions.append(
                {
                    "user": user,
                    "sticker": str(updated_df.loc[index, "Sticker_Name"]),
                    "previous": int(previous_counts.loc[index]),
                    "updated": int(updated_counts.loc[index]),
                }
            )

    return regressions


def validate_no_zero_regressions(previous_df, updated_df, users):
    regressions = find_zero_regressions(previous_df, updated_df, users)
    if not regressions:
        return

    details = "; ".join(
        (
            f"{regression['user']} / {regression['sticker']}: "
            f"{regression['previous']} -> {regression['updated']}"
        )
        for regression in regressions
    )
    raise ValueError(
        "Sticker count validation failed: owned stickers cannot drop to 0. "
        f"{details}"
    )


def image_files_for_user(user):
    user_dir = SCREENSHOTS_DIR / user
    if not user_dir.exists():
        print(f"Skipping {user}: missing folder {user_dir}")
        return []

    return sorted(
        path
        for path in user_dir.iterdir()
        if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS
    )


def chunked(items, size):
    for start in range(0, len(items), size):
        yield items[start : start + size]


def pending_images_from_google(processed):
    sheet_id = os.getenv("INGEST_SHEET_ID", "1lRwalTc96V1-VkECfoh3xWOo4gcVY5qctMzH5Q0_aUY")
    creds_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "google_creds.json")
    
    if not os.path.exists(creds_path):
        print(f"Credentials not found at {creds_path}. Cannot use direct pipeline.")
        return []

    try:
        creds = service_account.Credentials.from_service_account_file(
            creds_path,
            scopes=[
                "https://www.googleapis.com/auth/spreadsheets.readonly",
                "https://www.googleapis.com/auth/drive.readonly"
            ]
        )
        sheets_service = build("sheets", "v4", credentials=creds)
        
        result = sheets_service.spreadsheets().values().get(
            spreadsheetId=sheet_id,
            range="A:Z"
        ).execute()
        
        values = result.get("values", [])
        if not values:
            return []
            
        header = values[0]
        timestamp_idx = -1
        email_idx = -1
        upload_indices = []
        
        for idx, col in enumerate(header):
            col_lower = col.lower()
            if "timestamp" in col_lower:
                timestamp_idx = idx
            elif "email" in col_lower:
                email_idx = idx
            elif "upload" in col_lower or "screenshot" in col_lower or "image" in col_lower:
                upload_indices.append(idx)
                
        if timestamp_idx == -1 or email_idx == -1 or not upload_indices:
            print("Could not find required columns in the ingestion sheet.")
            return []
            
        images = []
        for row in values[1:]:
            if len(row) <= max(timestamp_idx, email_idx):
                continue
                
            email = row[email_idx].strip().lower()
            user = EMAIL_TO_USER.get(email)
            if not user:
                continue
                
            timestamp = row[timestamp_idx]
            
            urls = []
            for idx in upload_indices:
                if idx < len(row):
                    cell_value = row[idx]
                    if cell_value:
                        parts = [p.strip() for p in cell_value.split(",")]
                        urls.extend(parts)
                        
            for url in urls:
                file_id = extract_drive_file_id(url)
                if not file_id:
                    continue
                    
                if file_id in processed:
                    continue
                    
                images.append({
                    "user": user,
                    "file_id": file_id,
                    "url": url,
                    "timestamp": timestamp,
                    "key": file_id
                })
                
        return images
    except Exception as e:
        print(f"Error fetching pending images from Google Sheets: {e}")
        return []


def pending_images_from_local(processed):
    images = []

    for user in USERS:
        for image_path in image_files_for_user(user):
            image_key = f"{user}/{image_path.name}"
            current_hash = file_hash(image_path)

            if processed.get(image_key, {}).get("sha256") == current_hash:
                print(f"Skipping already processed image: {image_key}")
                continue

            images.append(
                {
                    "user": user,
                    "path": image_path,
                    "key": image_key,
                    "sha256": current_hash,
                }
            )

    return images


def pending_images(processed):
    creds_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "google_creds.json")
    if os.path.exists(creds_path):
        return pending_images_from_google(processed)
    else:
        return pending_images_from_local(processed)



def main():
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY is not set in your environment variables.")

    database_path = find_database_path()
    df = pd.read_csv(database_path)

    for user in USERS:
        if user not in df.columns:
            df[user] = 0
    previous_df = df.copy(deep=True)

    from google import genai

    client = genai.Client(api_key=api_key)
    processed = load_processed_log()
    images_to_process = pending_images(processed)

    for chunk_number, image_chunk in enumerate(
        chunked(images_to_process, IMAGE_CHUNK_SIZE),
        start=1,
    ):
        print(
            f"Processing image chunk {chunk_number} "
            f"({len(image_chunk)} image(s), max {IMAGE_CHUNK_SIZE} per minute)"
        )

        for image in image_chunk:
            user = image["user"]
            image_key = image["key"]

            image_backup_df = df.copy(deep=True)

            print(f"Processing {image_key} with {MODEL_NAME}")
            
            try:
                if "file_id" in image:
                    image_data = download_drive_file(image["file_id"])
                    import hashlib
                    current_hash = hashlib.sha256(image_data).hexdigest()
                else:
                    image_path = image["path"]
                    with image_path.open("rb") as f:
                        image_data = f.read()
                    current_hash = file_hash(image_path)
            except Exception as e:
                print(f"Failed to download/load image {image_key}: {e}")
                continue

            extracted_data = extract_stickers_from_image(client, image_data)
            updated, missing = update_database(df, user, extracted_data)

            # Check if this update introduced a regression against baseline
            regressions = find_zero_regressions(previous_df, df, USERS)
            if regressions:
                print(f"Validation failed for image {image_key}. Rolling back changes for this image and saving progress.")
                df = image_backup_df
                OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
                df.to_csv(DATABASE_PATH, index=False)
                save_processed_log(processed)
                validate_no_zero_regressions(previous_df, df, USERS)  # Will raise ValueError and halt

            processed[image_key] = {
                "sha256": current_hash,
                "model": MODEL_NAME,
                "set_name": extracted_data.get("set_name", ""),
                "set_number": extracted_data.get("set_number", ""),
                "updated_rows": updated,
                "missing_stickers": missing,
            }
            if "timestamp" in image:
                processed[image_key]["timestamp"] = image["timestamp"]

            print(f"Updated {updated} database row(s) for {user}.")
            if missing:
                print(f"Could not match: {', '.join(missing)}")

            # Save progress progressively to prevent losing work if standard exit or interruption happens
            OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
            df.to_csv(DATABASE_PATH, index=False)
            save_processed_log(processed)

            del extracted_data

        gc.collect()

        if chunk_number * IMAGE_CHUNK_SIZE < len(images_to_process):
            print(
                f"Finished {IMAGE_CHUNK_SIZE} Gemini prompt(s). "
                f"Waiting {CHUNK_PAUSE_SECONDS}s before the next chunk..."
            )
            time.sleep(CHUNK_PAUSE_SECONDS)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    validate_no_zero_regressions(previous_df, df, USERS)
    df.to_csv(DATABASE_PATH, index=False)
    save_processed_log(processed)

    print(f"Saved updated database to {DATABASE_PATH}")
    print(f"Saved processed image log to {PROCESSED_LOG}")


if __name__ == "__main__":
    main()
