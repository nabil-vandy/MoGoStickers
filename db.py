"""
Data-access layer for MoGoStickers.

Talks to Supabase over its REST + Storage APIs using the SERVICE-ROLE key (kept
server-side in Streamlit secrets / env — never sent to the browser). Row-Level
Security denies the anon key, so all reads/writes go through here.

Sticker shape returned by fetch_stickers():
    {
        "id", "name", "stars", "is_gold", "album",
        "ownership": { user_id: {"owned": bool, "extras": int}, ... }
    }
Total count for a user is derived via total_for(owned, extras).
"""
import json
import os
import urllib.error
import urllib.parse
import urllib.request

import streamlit as st


def _q(value):
    """URL-encode a value for use in a PostgREST filter."""
    return urllib.parse.quote(str(value), safe="")

# --- Config -----------------------------------------------------------------
# Local .env fallback (Streamlit Cloud uses st.secrets / real env vars).
if os.path.exists(".env"):
    with open(".env") as f:
        for line in f:
            if "=" in line and not line.startswith("#"):
                k, v = line.strip().split("=", 1)
                os.environ.setdefault(k, v.strip('"').strip("'"))

SUPABASE_URL = (os.getenv("SUPABASE_URL") or "").rstrip("/")
# Prefer the service-role key; fall back to SUPABASE_KEY for backwards-compat.
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_KEY") or os.getenv("SUPABASE_KEY")

_HEADERS = {
    "apikey": SUPABASE_KEY or "",
    "Authorization": f"Bearer {SUPABASE_KEY or ''}",
    "Content-Type": "application/json",
}


def total_for(owned, extras):
    """owned ? 1 + extras : 0 — the in-game total for a sticker."""
    return (1 + int(extras or 0)) if owned else 0


def config_ok():
    return bool(SUPABASE_URL and SUPABASE_KEY)


# --- Low-level REST ---------------------------------------------------------
def _request(endpoint, method="GET", payload=None, prefer=None):
    url = f"{SUPABASE_URL}/rest/v1/{endpoint}"
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    headers = dict(_HEADERS)
    if prefer:
        headers["Prefer"] = prefer
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req) as res:
            body = res.read().decode("utf-8")
            return json.loads(body) if body else []
    except urllib.error.HTTPError as e:
        st.error(f"Supabase DB error: {e.read().decode('utf-8')}")
        return None
    except Exception as e:
        st.error(f"Network error: {e}")
        return None


def _invalidate_sticker_cache():
    try:
        if "stickers_cache" in st.session_state:
            st.session_state.stickers_cache = None
    except Exception:
        pass


# --- Profiles ---------------------------------------------------------------
def get_profile_by_email(email):
    rows = _request(f"profiles?email=eq.{_q(email)}&select=*")
    return rows[0] if rows else None


def get_pool_profiles():
    """All approved users — the shared trading pool, ordered by screenname."""
    return _request("profiles?approved=eq.true&select=*&order=screenname.asc") or []


def list_pending_profiles():
    return _request("profiles?approved=eq.false&select=*&order=created_at.asc") or []


def create_profile(email, screenname, real_name=None, emoji="👤",
                   color="#93c5fd", is_admin=False, approved=False):
    payload = {
        "email": email, "screenname": screenname, "real_name": real_name,
        "emoji": emoji, "color": color, "is_admin": is_admin, "approved": approved,
    }
    rows = _request("profiles", method="POST", payload=payload, prefer="return=representation")
    return rows[0] if rows else None


def update_profile(profile_id, **fields):
    return _request(f"profiles?id=eq.{profile_id}", method="PATCH", payload=fields,
                    prefer="return=representation")


def set_screenname(profile_id, screenname):
    """Returns (ok, error). Enforces uniqueness via the DB constraint."""
    res = update_profile(profile_id, screenname=screenname)
    return (res is not None), (None if res is not None else "Screenname taken or invalid")


# --- Invites ----------------------------------------------------------------
def create_invite(code, screenname, email=None, emoji="👤", color="#93c5fd",
                  is_admin=False, auto_approve=True):
    payload = {
        "code": code, "screenname": screenname, "email": email, "emoji": emoji,
        "color": color, "is_admin": is_admin, "auto_approve": auto_approve,
    }
    rows = _request("invites", method="POST", payload=payload, prefer="return=representation")
    return rows[0] if rows else None


def get_invite(code):
    rows = _request(f"invites?code=eq.{_q(code)}&used_by=is.null&select=*")
    return rows[0] if rows else None


def list_invites():
    return _request("invites?select=*&order=created_at.desc") or []


def claim_invite(invite, email):
    """Create the invited profile and mark the invite used. Returns the profile."""
    profile = create_profile(
        email=email, screenname=invite["screenname"], emoji=invite.get("emoji", "👤"),
        color=invite.get("color", "#93c5fd"), is_admin=invite.get("is_admin", False),
        approved=invite.get("auto_approve", True),
    )
    if profile:
        _request(f"invites?id=eq.{invite['id']}", method="PATCH",
                 payload={"used_by": profile["id"], "used_at": _now()})
    return profile


# --- Stickers + ownership ---------------------------------------------------
def fetch_stickers():
    data = _request(
        "stickers?select=id,name,stars,is_gold,album,ownership(user_id,owned,extras)"
    )
    if not data:
        return []
    out = []
    for item in data:
        ownership = {}
        for o in (item.get("ownership") or []):
            ownership[o["user_id"]] = {"owned": o.get("owned", False),
                                       "extras": int(o.get("extras", 0) or 0)}
        out.append({
            "id": item["id"], "name": item["name"], "stars": item["stars"],
            "is_gold": item["is_gold"], "album": item["album"], "ownership": ownership,
        })
    return out


def ownership_for(sticker, user_id):
    """{'owned', 'extras'} for a user on a sticker (defaults to not owned)."""
    return sticker["ownership"].get(user_id, {"owned": False, "extras": 0})


def upsert_ownership(user_id, sticker_id, owned, extras):
    _invalidate_sticker_cache()
    payload = {"user_id": user_id, "sticker_id": sticker_id,
               "owned": bool(owned), "extras": int(extras), "updated_at": _now()}
    return _request("ownership?on_conflict=user_id,sticker_id", method="POST",
                    payload=payload, prefer="resolution=merge-duplicates,return=minimal")


# --- History / rollback -----------------------------------------------------
def log_history(user_id, action, snapshot):
    _request("database_history", method="POST", payload={
        "user_id": user_id, "action": action,
        "state_snapshot": snapshot, "created_at": _now(),
    })


def fetch_history(limit=10):
    return _request(f"database_history?select=*&order=created_at.desc&limit={limit}") or []


def apply_rollback(snapshot):
    """Snapshot is a list of {user_id, sticker_id, owned, extras}.
    Pre-migration snapshots (legacy hana/jon/nabil format) are skipped."""
    _invalidate_sticker_cache()
    applied = 0
    for item in snapshot or []:
        if "user_id" in item and "sticker_id" in item:
            upsert_ownership(item["user_id"], item["sticker_id"],
                             item.get("owned", False), item.get("extras", 0))
            applied += 1
    if applied == 0 and snapshot:
        st.warning("This history entry predates the schema migration and can't be rolled back.")


def snapshot_ownership(stickers, pool):
    """Capture current owned/extras for every (user, sticker) for history/rollback."""
    snap = []
    for s in stickers:
        for p in pool:
            o = ownership_for(s, p["id"])
            snap.append({"user_id": p["id"], "sticker_id": s["id"],
                         "owned": o["owned"], "extras": o["extras"]})
    return snap


# --- Uploads (screenshot analysis records) ----------------------------------
def create_upload(user_id, image_path, original_name, model_name, raw_response):
    rows = _request("uploads", method="POST", prefer="return=representation", payload={
        "user_id": user_id, "image_path": image_path, "original_name": original_name,
        "model_name": model_name, "raw_response": raw_response, "status": "pending",
    })
    return rows[0] if rows else None


def add_upload_items(items):
    if not items:
        return
    _request("upload_items", method="POST", payload=items, prefer="return=minimal")


def set_upload_status(upload_id, status):
    _request(f"uploads?id=eq.{upload_id}", method="PATCH", payload={"status": status})


def latest_uploads(user_id, limit=20):
    return _request(
        f"uploads?user_id=eq.{user_id}&select=*&order=created_at.desc&limit={limit}"
    ) or []


def get_upload_items(upload_id):
    return _request(
        f"upload_items?upload_id=eq.{upload_id}&select=*&order=id.asc"
    ) or []


# --- Storage (screenshots bucket) -------------------------------------------
def upload_screenshot(path, image_bytes, content_type):
    """Upload bytes to the private 'screenshots' bucket; returns the object path."""
    url = f"{SUPABASE_URL}/storage/v1/object/screenshots/{path}"
    headers = {
        "apikey": SUPABASE_KEY or "",
        "Authorization": f"Bearer {SUPABASE_KEY or ''}",
        "Content-Type": content_type or "application/octet-stream",
        "x-upsert": "true",
    }
    req = urllib.request.Request(url, data=image_bytes, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req):
            return path
    except Exception as e:
        st.warning(f"Could not store screenshot: {e}")
        return None


def signed_screenshot_url(path, expires_in=3600):
    """Create a temporary signed URL to display a private screenshot."""
    url = f"{SUPABASE_URL}/storage/v1/object/sign/screenshots/{path}"
    headers = dict(_HEADERS)
    data = json.dumps({"expiresIn": expires_in}).encode()
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req) as res:
            signed = json.loads(res.read().decode()).get("signedURL", "")
            return f"{SUPABASE_URL}/storage/v1{signed}" if signed else None
    except Exception:
        return None


# --- small helpers ----------------------------------------------------------
def _now():
    import time
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
