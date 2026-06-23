#!/usr/bin/env python3
"""
One-time data migration for MoGoStickers (run AFTER migrations/001_normalize_and_auth.sql).

What it does
------------
1. Seeds `profiles` rows for the 3 original users with their screennames:
       Hana  -> "Hana"        (legacy column: hana)
       Nabil -> "Nabs"        (legacy column: nabil)
       Jon   -> "RefinedBoot32" (legacy column: jon)
2. Copies every `ownership_legacy(sticker_id, hana, jon, nabil)` row into the new
   normalized `ownership(user_id, sticker_id, owned, extras)` table, converting:
       owned  = (legacy_total > 0)
       extras = max(legacy_total - 1, 0)
3. Prints a verification report: for each user, the recomputed total
   (owned ? 1 + extras : 0) summed across stickers must equal the legacy column sum.

Usage
-----
    # Point at a Supabase BRANCH/COPY first, not prod.
    export SUPABASE_URL="https://<ref>.supabase.co"
    export SUPABASE_SERVICE_KEY="<service-role key>"   # service role, NOT the anon key
    # Set the real Google login emails for the 3 originals:
    export HANA_EMAIL="hana@example.com"
    export NABIL_EMAIL="nabs@example.com"
    export JON_EMAIL="jon@example.com"
    export ADMIN_EMAIL="$JON_EMAIL"   # which of them is the admin (defaults to Jon)

    python scripts/migrate_ownership.py            # dry run: report only, writes profiles
    python scripts/migrate_ownership.py --apply    # actually write ownership rows

This script is idempotent for profiles (upsert by email) and refuses to duplicate
ownership rows (it upserts on the unique (user_id, sticker_id) constraint).
"""
import json
import os
import sys
import urllib.error
import urllib.request

SUPABASE_URL = os.environ["SUPABASE_URL"].rstrip("/")
SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_KEY") or os.environ.get("SUPABASE_KEY")
if not SERVICE_KEY:
    sys.exit("Set SUPABASE_SERVICE_KEY (service-role key) before running.")

APPLY = "--apply" in sys.argv

# Map each original user: legacy ownership column -> profile to create.
SEED_PROFILES = [
    {"legacy_col": "hana",  "screenname": "Hana",          "real_name": "Hana",
     "email": os.environ.get("HANA_EMAIL"),  "emoji": "🌸", "color": "#fda4af"},
    {"legacy_col": "nabil", "screenname": "Nabs",          "real_name": "Nabil",
     "email": os.environ.get("NABIL_EMAIL"), "emoji": "🦊", "color": "#86efac"},
    {"legacy_col": "jon",   "screenname": "RefinedBoot32", "real_name": "Jon",
     "email": os.environ.get("JON_EMAIL"),   "emoji": "⚡", "color": "#93c5fd"},
]
ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL") or os.environ.get("JON_EMAIL")

BASE_HEADERS = {
    "apikey": SERVICE_KEY,
    "Authorization": f"Bearer {SERVICE_KEY}",
    "Content-Type": "application/json",
}


def request(endpoint, method="GET", payload=None, extra_headers=None):
    url = f"{SUPABASE_URL}/rest/v1/{endpoint}"
    data = json.dumps(payload).encode() if payload is not None else None
    headers = dict(BASE_HEADERS)
    if extra_headers:
        headers.update(extra_headers)
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req) as res:
            body = res.read().decode()
            return json.loads(body) if body else []
    except urllib.error.HTTPError as e:
        sys.exit(f"Supabase error {e.code} on {method} {endpoint}: {e.read().decode()}")


def seed_profiles():
    """Upsert the 3 original profiles by email; returns {legacy_col: profile_id}."""
    missing = [p["legacy_col"] for p in SEED_PROFILES if not p["email"]]
    if missing:
        sys.exit(f"Missing login emails for: {missing}. Set HANA_EMAIL/NABIL_EMAIL/JON_EMAIL.")

    rows = []
    for p in SEED_PROFILES:
        rows.append({
            "email": p["email"],
            "screenname": p["screenname"],
            "real_name": p["real_name"],
            "emoji": p["emoji"],
            "color": p["color"],
            "approved": True,
            "is_admin": (p["email"] == ADMIN_EMAIL),
        })
    # Upsert on the unique email column.
    result = request(
        "profiles?on_conflict=email",
        method="POST",
        payload=rows,
        extra_headers={"Prefer": "resolution=merge-duplicates,return=representation"},
    )
    by_email = {r["email"]: r["id"] for r in result}
    mapping = {p["legacy_col"]: by_email[p["email"]] for p in SEED_PROFILES}
    print("Seeded/updated profiles:")
    for p in SEED_PROFILES:
        print(f"  {p['screenname']:<14} <- {p['email']}  (id={mapping[p['legacy_col']]})")
    return mapping


def fetch_legacy():
    return request("ownership_legacy?select=sticker_id,hana,jon,nabil")


def to_owned_extras(total):
    total = int(total or 0)
    return (total > 0, max(total - 1, 0))


def migrate(mapping):
    legacy = fetch_legacy()
    legacy_totals = {col: 0 for col in mapping}
    new_totals = {col: 0 for col in mapping}
    rows = []
    for row in legacy:
        sticker_id = row["sticker_id"]
        for col, user_id in mapping.items():
            owned, extras = to_owned_extras(row.get(col, 0))
            legacy_totals[col] += int(row.get(col, 0) or 0)
            new_totals[col] += (1 + extras) if owned else 0
            rows.append({
                "user_id": user_id,
                "sticker_id": sticker_id,
                "owned": owned,
                "extras": extras,
            })

    print(f"\nLegacy ownership rows: {len(legacy)}  ->  new ownership rows: {len(rows)}")
    print("Verification (legacy total must equal recomputed total):")
    ok = True
    for col in mapping:
        match = "OK" if legacy_totals[col] == new_totals[col] else "MISMATCH"
        if legacy_totals[col] != new_totals[col]:
            ok = False
        print(f"  {col:<6} legacy={legacy_totals[col]:<5} new={new_totals[col]:<5} {match}")

    if not ok:
        sys.exit("\nTotals do not match — aborting. No ownership rows written.")

    if not APPLY:
        print("\nDRY RUN — re-run with --apply to write the ownership rows above.")
        return

    # Upsert in chunks on the unique (user_id, sticker_id) constraint.
    CHUNK = 500
    for i in range(0, len(rows), CHUNK):
        request(
            "ownership?on_conflict=user_id,sticker_id",
            method="POST",
            payload=rows[i:i + CHUNK],
            extra_headers={"Prefer": "resolution=merge-duplicates,return=minimal"},
        )
    print(f"\nApplied {len(rows)} ownership rows. ✅")
    print("Next: spot-check the app, then run migrations/002_drop_legacy.sql.")


if __name__ == "__main__":
    print(f"Target: {SUPABASE_URL}  (apply={APPLY})\n")
    mapping = seed_profiles()
    migrate(mapping)
