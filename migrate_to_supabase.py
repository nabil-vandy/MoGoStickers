import os
import csv
import json
import urllib.request
import urllib.error

SUPABASE_URL = "https://nikilnudvxrzxlcrwugq.supabase.co"
SUPABASE_KEY = "sb_publishable_y2JNpZruuo6OOm_h7fodEQ_xcL4G-or"

csv_path = "output/sticker_database.csv"

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
            for s in inserted:
                existing_map[s["name"].lower().strip()] = s["id"]
            print(f"Inserted {len(inserted)} new stickers.")
    except urllib.error.HTTPError as e:
        print(f"Error inserting new stickers: {e.read().decode('utf-8')}")
        exit(1)
else:
    print("All stickers already exist in database metadata. No new inserts needed.")

# 3. Prepare ownership data
ownership_payload = []
for row in rows:
    name = row["Sticker_Name"].strip()
    sticker_id = existing_map.get(name.lower().strip())
    if not sticker_id:
        print(f"Warning: could not find ID for sticker '{name}'")
        continue
    ownership_payload.append({
        "sticker_id": sticker_id,
        "hana": int(row["Hana"]),
        "jon": int(row["Jon"]),
        "nabil": int(row["Nabil"])
    })

# Post ownership to Supabase using POST with resolution=merge-duplicates (Upsert)
ownership_url = f"{SUPABASE_URL}/rest/v1/ownership"
req = urllib.request.Request(
    ownership_url,
    data=json.dumps(ownership_payload).encode("utf-8"),
    headers={
        **headers,
        "Prefer": "resolution=merge-duplicates",
    },
    method="POST"
)

try:
    with urllib.request.urlopen(req) as res:
        print("Successfully synced ownership counts to Supabase!")
except urllib.error.HTTPError as e:
    print(f"Error syncing ownership counts: {e.read().decode('utf-8')}")
    exit(1)

print("Sync completed successfully!")
