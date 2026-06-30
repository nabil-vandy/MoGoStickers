import os
import csv
import json
import urllib.request
import urllib.error
from pathlib import Path

# --- Load Environment Variables from secrets.toml or .env ---
SUPABASE_URL = None
SUPABASE_KEY = None

# Try loading from .streamlit/secrets.toml first (most likely to have the secret service-role key)
secrets_path = Path(".streamlit/secrets.toml")
if secrets_path.exists():
    with open(secrets_path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                key, val = line.split("=", 1)
                key = key.strip()
                val = val.strip().strip('"').strip("'")
                if key == "SUPABASE_URL":
                    SUPABASE_URL = val
                elif key in ("SUPABASE_SERVICE_KEY", "SUPABASE_KEY"):
                    SUPABASE_KEY = val

# Fallback to .env
if not SUPABASE_URL or not SUPABASE_KEY:
    env_path = Path(".env")
    if env_path.exists():
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    key, val = line.split("=", 1)
                    key = key.strip()
                    val = val.strip().strip('"').strip("'")
                    if key == "SUPABASE_URL" and not SUPABASE_URL:
                        SUPABASE_URL = val
                    elif key in ("SUPABASE_SERVICE_KEY", "SUPABASE_KEY") and not SUPABASE_KEY:
                        SUPABASE_KEY = val

# Also fallback to OS environment variables
SUPABASE_URL = SUPABASE_URL or os.getenv("SUPABASE_URL")
SUPABASE_KEY = SUPABASE_KEY or os.getenv("SUPABASE_SERVICE_KEY") or os.getenv("SUPABASE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    print("Error: SUPABASE_URL and SUPABASE_KEY/SUPABASE_SERVICE_KEY are not set. Check your secrets.toml or .env file.")
    exit(1)

csv_path = "output/sticker_database.csv"

if not os.path.exists(csv_path):
    print(f"Error: Local database file not found at: {csv_path}")
    exit(1)

print("Starting robust migration/sync to Supabase...")

# Read local CSV rows
rows = []
with open(csv_path, "r", encoding="utf-8") as f:
    reader = csv.DictReader(f)
    for row in reader:
        rows.append(row)

# Get headers for authentication
headers = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json"
}

# 1. Fetch all existing stickers in Supabase
fetch_url = f"{SUPABASE_URL}/rest/v1/stickers?select=id,name"
req = urllib.request.Request(fetch_url, headers=headers, method="GET")
try:
    with urllib.request.urlopen(req) as res:
        existing_stickers = json.loads(res.read().decode("utf-8"))
except Exception as e:
    print(f"Error fetching existing stickers: {e}")
    exit(1)

existing_map = {s["name"].lower().strip(): s["id"] for s in existing_stickers}

# 2. Check if there are any new stickers to insert
new_stickers = []
for row in rows:
    name = row["Sticker_Name"].strip()
    if name.lower().strip() not in existing_map:
        new_stickers.append({
            "name": name,
            "stars": int(row["Star_Number"]),
            "is_gold": row["Gold_Status"].lower() == "true",
            "album": row["Set_Name"].strip()
        })

if new_stickers:
    print(f"Found {len(new_stickers)} new stickers to insert...")
    stickers_url = f"{SUPABASE_URL}/rest/v1/stickers"
    req = urllib.request.Request(
        stickers_url,
        data=json.dumps(new_stickers).encode("utf-8"),
        headers={**headers, "Prefer": "return=representation"},
        method="POST"
    )
    try:
        with urllib.request.urlopen(req) as res:
            inserted = json.loads(res.read().decode("utf-8"))
            print(f"Successfully inserted {len(inserted)} new stickers into Supabase.")
    except urllib.error.HTTPError as e:
        print(f"Error inserting new stickers: {e.read().decode('utf-8')}")
        exit(1)
else:
    print("All stickers already exist in database metadata. No new inserts needed.")

print("Sync completed successfully!")
