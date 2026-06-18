import os
import json
import csv
import urllib.request
import urllib.error
import streamlit as st
from google import genai
from google.genai import types
from pydantic import BaseModel
import time
import textwrap

# --- Load Environment Variables ---
# Simple parser for .env if exists (runs without python-dotenv dependency)
if os.path.exists(".env"):
    with open(".env") as f:
        for line in f:
            if "=" in line and not line.startswith("#"):
                key, val = line.strip().split("=", 1)
                os.environ[key] = val.strip('"').strip("'")

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
LOCAL_MODE = os.getenv("LOCAL_MODE", "").lower() == "true" or not SUPABASE_URL or not SUPABASE_KEY

if LOCAL_MODE:
    st.info("ℹ️ Running in Local Mode (using local CSV instead of Supabase). Changes will not affect the production database.")
elif not SUPABASE_URL or not SUPABASE_KEY:
    st.error("SUPABASE_URL and SUPABASE_KEY environment variables are not set. Please configure them in your secrets/environment.")
    st.stop()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
MODEL_NAME = os.getenv("GEMINI_MODEL", "gemini-3.1-flash-lite")

# SMTP credentials for email alerts
SMTP_SERVER = os.getenv("SMTP_SERVER")
SMTP_PORT = os.getenv("SMTP_PORT", "587")
SMTP_USERNAME = os.getenv("SMTP_USERNAME")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")
SMTP_RECIPIENTS = os.getenv("SMTP_RECIPIENTS", "").split(",")

# --- Supabase Rest Headers ---
headers = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=representation"
}

# --- Pydantic Schema for Gemini ---
class StickerInfo(BaseModel):
    name: str
    count: int

class SetInfo(BaseModel):
    set_name: str
    set_number: str
    stickers: list[StickerInfo]

# --- Database Operations ---
def supabase_request(endpoint, method="GET", payload=None):
    url = f"{SUPABASE_URL}/rest/v1/{endpoint}"
    data_bytes = None
    if payload is not None:
        data_bytes = json.dumps(payload).encode("utf-8")
    
    req = urllib.request.Request(
        url,
        data=data_bytes,
        headers=headers,
        method=method
    )
    try:
        with urllib.request.urlopen(req) as res:
            return json.loads(res.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        st.error(f"Supabase DB error: {e.read().decode('utf-8')}")
        return None
    except Exception as e:
        st.error(f"Network error: {e}")
        return None

def fetch_sticker_data():
    if LOCAL_MODE:
        csv_path = "output/sticker_database.csv"
        if not os.path.exists(csv_path):
            st.error(f"Local database file not found at: {csv_path}")
            return []
        flattened = []
        try:
            with open(csv_path, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    flattened.append({
                        "id": int(row["MoGo_ID"]) if row.get("MoGo_ID") else hash(row["Sticker_Name"]),
                        "name": row["Sticker_Name"],
                        "stars": int(row["Star_Number"]) if row.get("Star_Number") else 1,
                        "is_gold": row["Gold_Status"].lower() == "true",
                        "album": row["Set_Name"],
                        "hana": int(row["Hana"]) if row.get("Hana") else 0,
                        "jon": int(row["Jon"]) if row.get("Jon") else 0,
                        "nabil": int(row["Nabil"]) if row.get("Nabil") else 0
                    })
            return flattened
        except Exception as e:
            st.error(f"Error reading local database: {e}")
            return []

    # Fetch stickers with joined ownership counts
    data = supabase_request("stickers?select=id,name,stars,is_gold,album,ownership(hana,jon,nabil)")
    if not data:
        return []
    # Flatten the ownership counts
    flattened = []
    for item in data:
        ownership = item.get("ownership") or {"hana": 0, "jon": 0, "nabil": 0}
        flattened.append({
            "id": item["id"],
            "name": item["name"],
            "stars": item["stars"],
            "is_gold": item["is_gold"],
            "album": item["album"],
            "hana": ownership.get("hana", 0),
            "jon": ownership.get("jon", 0),
            "nabil": ownership.get("nabil", 0)
        })
    return flattened

def fetch_history_logs():
    if LOCAL_MODE:
        history_path = "output/local_history.json"
        if not os.path.exists(history_path):
            return []
        try:
            with open(history_path, "r", encoding="utf-8") as f:
                history = json.load(f)
            # Return last 10 entries descending
            return history[::-1][:10]
        except Exception as e:
            st.error(f"Error reading local history: {e}")
            return []
    return supabase_request("database_history?select=*&order=created_at.desc&limit=10")

def log_database_state(user_profile, action, state_snapshot):
    payload = {
        "user_profile": user_profile,
        "action": action,
        "state_snapshot": state_snapshot,
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    }
    if LOCAL_MODE:
        history_path = "output/local_history.json"
        try:
            history = []
            if os.path.exists(history_path):
                with open(history_path, "r", encoding="utf-8") as f:
                    history = json.load(f)
            history.append(payload)
            os.makedirs(os.path.dirname(history_path), exist_ok=True)
            with open(history_path, "w", encoding="utf-8") as f:
                json.dump(history, f, indent=2)
        except Exception as e:
            st.error(f"Error writing local history: {e}")
        return
    supabase_request("database_history", method="POST", payload=payload)

def update_ownership(sticker_id, hana, jon, nabil):
    payload = {
        "hana": hana,
        "jon": jon,
        "nabil": nabil
    }
    # Clear Streamlit stickers cache
    try:
        if "stickers_cache" in st.session_state:
            st.session_state.stickers_cache = None
    except Exception:
        pass

    if LOCAL_MODE:
        csv_path = "output/sticker_database.csv"
        if not os.path.exists(csv_path):
            st.error(f"Local database file not found at: {csv_path}")
            return None
        try:
            rows = []
            updated = False
            with open(csv_path, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                fieldnames = reader.fieldnames
                for row in reader:
                    row_id = row.get("MoGo_ID")
                    if row_id and int(row_id) == int(sticker_id):
                        row["Hana"] = str(hana)
                        row["Jon"] = str(jon)
                        row["Nabil"] = str(nabil)
                        updated = True
                    rows.append(row)
            if not updated:
                st.warning(f"Sticker with ID {sticker_id} not found in local database.")
                return None
            with open(csv_path, "w", encoding="utf-8", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(rows)
            return [{"sticker_id": sticker_id, "hana": hana, "jon": jon, "nabil": nabil}]
        except Exception as e:
            st.error(f"Error updating local database: {e}")
            return None

    # Using PATCH with ID in query string
    return supabase_request(f"ownership?sticker_id=eq.{sticker_id}", method="PATCH", payload=payload)

def apply_rollback(snapshot):
    # Clear Streamlit stickers cache
    try:
        if "stickers_cache" in st.session_state:
            st.session_state.stickers_cache = None
    except Exception:
        pass
    # Snapshot is a list/dictionary of sticker ownership counts
    for item in snapshot:
        update_ownership(item["id"], item["hana"], item["jon"], item["nabil"])

# --- Email Alert Helper ---
def trigger_mismatch_email(user, sticker_name, db_count, screenshot_count):
    if not SMTP_SERVER or not SMTP_USERNAME or not SMTP_PASSWORD:
        # If SMTP not configured, just log to warning in Streamlit
        st.warning(f"Email credentials not configured. Could not send alert for: '{sticker_name}' mismatch.")
        return
    
    try:
        from email.mime.multipart import MIMEMultipart
        from email.mime.text import MIMEText
        import smtplib

        msg = MIMEMultipart("alternative")
        msg["Subject"] = f"⚠️ Monopoly GO Mismatch Alert: {user} / {sticker_name}"
        msg["From"] = SMTP_USERNAME
        msg["To"] = ", ".join(SMTP_RECIPIENTS)

        body_text = f"Discrepancy detected for sticker '{sticker_name}' owned by {user}.\nDatabase expected: {db_count}\nScreenshot showed: {screenshot_count}"
        body_html = f"""
        <html>
        <body>
            <h3>⚠️ Monopoly GO Mismatch Alert</h3>
            <p>A discrepancy was detected while processing a screenshot for <strong>{user}</strong>.</p>
            <table border="1" cellpadding="6" style="border-collapse: collapse;">
                <tr><th>Sticker Name</th><td>{sticker_name}</td></tr>
                <tr><th>Expected count (DB)</th><td>{db_count}</td></tr>
                <tr><th>Actual count (Screenshot)</th><td>{screenshot_count}</td></tr>
            </table>
            <p>The database has been updated with the screenshot value. Please verify if a trade was missed.</p>
        </body>
        </html>
        """
        msg.attach(MIMEText(body_text, "plain"))
        msg.attach(MIMEText(body_html, "html"))

        port = int(SMTP_PORT)
        if port == 465:
            with smtplib.SMTP_SSL(SMTP_SERVER, port) as server:
                server.login(SMTP_USERNAME, SMTP_PASSWORD)
                server.sendmail(SMTP_USERNAME, SMTP_RECIPIENTS, msg.as_string())
        else:
            with smtplib.SMTP(SMTP_SERVER, port) as server:
                server.starttls()
                server.login(SMTP_USERNAME, SMTP_PASSWORD)
                server.sendmail(SMTP_USERNAME, SMTP_RECIPIENTS, msg.as_string())
        st.success(f"Discrepancy email alert sent successfully to {', '.join(SMTP_RECIPIENTS)}")
    except Exception as e:
        st.error(f"Failed to send email alert: {e}")

# --- Trade Calculator ---
def find_trade_rows(stickers):
    trades = []
    users = ["hana", "jon", "nabil"]
    
    # Calculate total counts for each user to see if they've initialized their profile
    totals = {u: 0 for u in users}
    for sticker in stickers:
        for u in users:
            totals[u] += sticker.get(u, 0)

    for sticker in stickers:
        counts = {u: sticker[u] for u in users}
        senders = [u for u, count in counts.items() if count > 1]
        # Only include a recipient if they have set up their profile (total count >= 10)
        recipients = [u for u, count in counts.items() if count == 0 and totals[u] >= 10]

        for sender in senders:
            available = counts[sender] - 1
            for recipient in recipients[:available]:
                trades.append({
                    "id": sticker["id"],
                    "sender": sender.capitalize(),
                    "recipient": recipient.capitalize(),
                    "sticker_name": sticker["name"],
                    "album": sticker["album"],
                    "stars": sticker["stars"],
                    "gold": sticker["is_gold"]
                })
    return trades

# --- App Settings & Page Config ---
st.set_page_config(page_title="Monopoly GO! Sticker Share", page_icon="🎲", layout="wide")

# Custom Premium Styling
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;600;800&display=swap');
    
    html, body, [class*="css"] {
        font-family: 'Outfit', sans-serif;
    }

    /* Main App Background Override */
    .stApp {
        background-color: #0b0f19 !important;
        color: #f4f4f5 !important;
    }

    /* Custom CSS Grid for Responsive Metrics */
    .metrics-grid {
        display: grid;
        grid-template-columns: repeat(4, 1fr);
        gap: 16px;
        margin-bottom: 24px;
        width: 100%;
    }

    .metric-card {
        background-color: #121824;
        border: 1px solid #1e293b;
        border-radius: 12px;
        padding: 18px;
        text-align: left;
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.15);
        transition: transform 0.2s ease, box-shadow 0.2s ease, border-color 0.2s ease;
    }
    .metric-card:hover {
        transform: translateY(-2px);
        box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.3);
        border-color: #3b82f6;
    }

    /* Sticker Row Styling */
    .sticker-row {
        display: flex;
        justify-content: flex-start;
        align-items: center;
        flex-wrap: wrap;
        gap: 6px 16px;
        padding: 10px 14px;
        border-radius: 8px;
        background-color: #121824;
        border: 1px solid #1e293b;
        margin-bottom: 6px;
        transition: background-color 0.2s ease, border-color 0.2s ease;
        width: 100%;
    }
    .sticker-row:hover {
        background-color: #1a2336;
        border-color: #3b82f6;
    }

    /* Album Overview Card Grid */
    .album-grid-card {
        background-color: #121824;
        border: 1px solid #1e293b;
        border-radius: 12px;
        padding: 14px;
        display: flex;
        align-items: center;
        gap: 14px;
        transition: transform 0.2s ease, border-color 0.2s ease;
    }
    .album-grid-card:hover {
        transform: translateY(-2px);
        border-color: #3b82f6;
    }

    .album-avatar {
        width: 46px;
        height: 46px;
        border-radius: 50%;
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 20px;
        flex-shrink: 0;
        box-shadow: 0 4px 6px rgba(0,0,0,0.15);
    }

    .album-info {
        flex-grow: 1;
        display: flex;
        flex-direction: column;
        justify-content: center;
    }

    .album-title {
        font-size: 13px;
        font-weight: bold;
        color: #f4f4f5;
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
    }

    .album-progress-text {
        font-size: 11px;
        color: #71717a;
    }

    .album-progress-container {
        display: flex;
        justify-content: space-between;
        align-items: center;
        margin-bottom: 4px;
        gap: 8px;
    }

    /* Customize input and forms to look premium */
    div[data-testid="stForm"] {
        background-color: #121824 !important;
        border: 1px solid #1e293b !important;
        border-radius: 12px !important;
    }

    /* Keep Trade columns inline on mobile (no collapse) */
    div[data-testid="stHorizontalBlock"]:has(.sticker-row) {
        display: flex !important;
        flex-direction: row !important;
        flex-wrap: nowrap !important;
        align-items: center !important;
        justify-content: flex-start !important;
        gap: 8px !important;
        width: 100% !important;
    }
    div[data-testid="stHorizontalBlock"]:has(.sticker-row) div[data-testid="column"] {
        margin: 0 !important;
        padding: 0 !important;
    }
    div[data-testid="stHorizontalBlock"]:has(.sticker-row) div[data-testid="column"]:nth-child(1) {
        width: 45px !important;
        max-width: 45px !important;
        min-width: 45px !important;
        flex: 0 0 45px !important;
        display: flex !important;
        align-items: center !important;
        justify-content: center !important;
    }
    div[data-testid="stHorizontalBlock"]:has(.sticker-row) div[data-testid="column"]:nth-child(2) {
        width: calc(100% - 53px) !important; /* 45px width + 8px gap */
        min-width: calc(100% - 53px) !important;
        flex: 1 1 auto !important;
        max-width: none !important;
    }

    /* Reset Streamlit checkbox spacing inside row */
    div[data-testid="stHorizontalBlock"]:has(.sticker-row) div[data-testid="stCheckbox"] {
        margin-top: 0 !important;
        padding-top: 0 !important;
        margin-bottom: 0 !important;
        padding-bottom: 0 !important;
        display: flex !important;
        align-items: center !important;
        justify-content: center !important;
    }
    div[data-testid="stHorizontalBlock"]:has(.sticker-row) div[data-testid="stCheckbox"] > label {
        margin: 0 !important;
        padding: 0 !important;
    }

    @media (max-width: 768px) {
        .metrics-grid {
            grid-template-columns: repeat(2, 1fr);
            gap: 12px;
        }
    }

    /* Hide Streamlit default UI elements */
    [data-testid="stHeader"], [data-testid="stFooter"], #MainMenu, [data-testid="stAppDeployButton"] {
        visibility: hidden;
        display: none !important;
    }
</style>
""", unsafe_allow_html=True)

# --- Session State Initialization ---
url_profile = st.query_params.get("profile")
if url_profile in ["Hana", "Jon", "Nabil"]:
    st.session_state.selected_profile = url_profile
elif "selected_profile" not in st.session_state:
    st.session_state.selected_profile = "Hana"

url_tab = st.query_params.get("tab")
if url_tab in ["Trades", "Collection", "Audit"]:
    st.session_state.active_tab = url_tab
elif "active_tab" not in st.session_state:
    st.session_state.active_tab = "Trades"

if "show_manual_editor" not in st.session_state:
    st.session_state.show_manual_editor = False

if "undo_backup" not in st.session_state:
    st.session_state.undo_backup = None

if "working_counts" not in st.session_state:
    st.session_state.working_counts = None

if "stickers_cache" not in st.session_state:
    st.session_state.stickers_cache = None

selected_profile = st.session_state.selected_profile

# Fetch updated dataset
if st.session_state.stickers_cache is None:
    st.session_state.stickers_cache = fetch_sticker_data()
stickers = st.session_state.stickers_cache
trades = find_trade_rows(stickers)

# Build a list of unique albums in the order they appear in the database
ordered_albums = []
for s in stickers:
    if s["album"] not in ordered_albums:
        ordered_albums.append(s["album"])

# Album Metadata Dictionary (Emojis, theme colors, gradients)
ALBUM_META = {
    "The Simpsons": {"emoji": "🍩", "color": "#fbbf24", "gradient": "linear-gradient(135deg, #fef08a, #f59e0b)"},
    "Monopoly's Training Day": {"emoji": "🎩", "color": "#60a5fa", "gradient": "linear-gradient(135deg, #93c5fd, #3b82f6)"},
    "Friends & Family": {"emoji": "👥", "color": "#f472b6", "gradient": "linear-gradient(135deg, #fbcfe8, #ec4899)"},
    "Property of Ned Flanders": {"emoji": "⛪", "color": "#34d399", "gradient": "linear-gradient(135deg, #a7f3d0, #10b981)"},
    "Taste of Springfield": {"emoji": "🍔", "color": "#f59e0b", "gradient": "linear-gradient(135deg, #fde68a, #d97706)"},
    "The Pin Pal's New Pal": {"emoji": "🎳", "color": "#a78bfa", "gradient": "linear-gradient(135deg, #c7d2fe, #818cf8)"},
    "Maggie's Big Adventure": {"emoji": "🍼", "color": "#ec4899", "gradient": "linear-gradient(135deg, #fbcfe8, #db2777)"},
    "Springfield Superheroes": {"emoji": "🦸", "color": "#10b981", "gradient": "linear-gradient(135deg, #6ee7b7, #059669)"},
    "When Homie Met Marge": {"emoji": "💑", "color": "#f43f5e", "gradient": "linear-gradient(135deg, #fecdd3, #e11d48)"},
    "Marge's Many Jobs": {"emoji": "💼", "color": "#fb923c", "gradient": "linear-gradient(135deg, #fed7aa, #ea580c)"},
    "Old School Rivals": {"emoji": "🏆", "color": "#60a5fa", "gradient": "linear-gradient(135deg, #93c5fd, #2563eb)"},
    "Springfield Elementary": {"emoji": "🏫", "color": "#c084fc", "gradient": "linear-gradient(135deg, #e9d5ff, #9333ea)"},
    "Exotic Animals": {"emoji": "🦁", "color": "#fbbf24", "gradient": "linear-gradient(135deg, #fef08a, #d97706)"},
    "Simpsons in Song": {"emoji": "🎤", "color": "#f472b6", "gradient": "linear-gradient(135deg, #fbcfe8, #db2777)"},
    "You Steam a Good Ham!": {"emoji": "🥩", "color": "#f87171", "gradient": "linear-gradient(135deg, #fca5a5, #dc2626)"},
    "Beloved Memes": {"emoji": "🐸", "color": "#4ade80", "gradient": "linear-gradient(135deg, #86efac, #16a34a)"},
    "The Itchy & Scratchy Show": {"emoji": "🐱", "color": "#f87171", "gradient": "linear-gradient(135deg, #fca5a5, #b91c1c)"},
    "Moe's Tavern": {"emoji": "🍻", "color": "#fb923c", "gradient": "linear-gradient(135deg, #fed7aa, #d97706)"},
    "Homer's Many Jobs": {"emoji": "👷", "color": "#60a5fa", "gradient": "linear-gradient(135deg, #93c5fd, #1d4ed8)"},
    "Upper Crust": {"emoji": "🏰", "color": "#fbbf24", "gradient": "linear-gradient(135deg, #fde68a, #b45309)"},
    "Iconic Moments": {"emoji": "📸", "color": "#a78bfa", "gradient": "linear-gradient(135deg, #ddd6fe, #7c3aed)"},
    "Welcome to Springfield": {"emoji": "🗺️", "color": "#10b981", "gradient": "linear-gradient(135deg, #a7f3d0, #047857)"}
}

profile_emojis = {"Hana": "🌸", "Jon": "⚡", "Nabil": "🦊"}
profile_colors = {"Hana": "#fda4af", "Jon": "#93c5fd", "Nabil": "#86efac"}
active_emoji = profile_emojis.get(selected_profile, "👤")
active_color = profile_colors.get(selected_profile, "#ffffff")

# Helper to render metric card
def render_metric_card(title, value, subtitle, color, icon):
    st.markdown(f"""
    <div class="metric-card">
        <div style="font-size: 24px; margin-bottom: 6px;">{icon}</div>
        <div style="font-size: 32px; font-weight: 800; color: {color}; line-height: 1.1;">{value}</div>
        <div style="font-size: 14px; font-weight: 600; color: #f4f4f5; margin-top: 6px;">{title}</div>
        <div style="font-size: 11px; color: #71717a; margin-top: 2px;">{subtitle}</div>
    </div>
    """, unsafe_allow_html=True)

# Helper to generate greeting based on time of day
def get_greeting(name):
    import datetime
    hour = datetime.datetime.now().hour
    if hour < 12:
        return f"Good morning, {name}! ☀️"
    elif hour < 18:
        return f"Good afternoon, {name}! 👋"
    else:
        return f"Good evening, {name}! 🌙"

# --- Sidebar Layout ---
with st.sidebar:
    st.markdown("""
    <div style='padding: 10px 0; margin-bottom: 20px;'>
        <div style='font-size: 24px; font-weight: 800; color: #f4f4f5; display: flex; align-items: center; gap: 10px;'>
            <span>🎲</span> Monopoly GO!
        </div>
        <div style='font-size: 14px; color: #3b82f6; font-weight: 600; margin-top: -4px; margin-left: 34px;'>Sticker Share <span style='color: #71717a; font-size: 0.85em; font-weight: normal; margin-left: 4px;'>v2.4.2</span></div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown("<div style='font-size: 11px; font-weight: bold; color: #71717a; text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 8px;'>Navigation</div>", unsafe_allow_html=True)
    
    for tab in ["Dashboard", "Trades", "Collection", "Audit"]:
        icon = "📊" if tab == "Dashboard" else ("⚡" if tab == "Trades" else ("📁" if tab == "Collection" else "🔍"))
        is_active = (st.session_state.active_tab == tab)
        btn_type = "primary" if is_active else "secondary"
        if st.button(f"{icon}  {tab}", key=f"nav_{tab}", use_container_width=True, type=btn_type):
            st.session_state.active_tab = tab
            st.query_params["tab"] = tab
            st.rerun()
            
    st.markdown("<div style='margin: 20px 0; border-top: 1px solid #1e293b;'></div>", unsafe_allow_html=True)
    
    st.markdown("<div style='font-size: 11px; font-weight: bold; color: #71717a; text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 8px;'>Profiles</div>", unsafe_allow_html=True)
    
    profiles_meta = [
        {"name": "Jon", "emoji": "⚡", "color": "#93c5fd"},
        {"name": "Hana", "emoji": "🌸", "color": "#fda4af"},
        {"name": "Nabil", "emoji": "🦊", "color": "#86efac"}
    ]
    
    for p in profiles_meta:
        is_selected = (selected_profile == p["name"])
        btn_type = "primary" if is_selected else "secondary"
        if st.button(f"{p['emoji']} {p['name']}", key=f"prof_btn_{p['name']}", use_container_width=True, type=btn_type):
            st.session_state.selected_profile = p["name"]
            st.query_params["profile"] = p["name"]
            st.rerun()
            
    st.markdown("""
    <div style='background-color: rgba(234, 179, 8, 0.05); border: 1px solid rgba(234, 179, 8, 0.15); border-left: 4px solid #eab308; padding: 12px; border-radius: 8px; margin-top: 40px;'>
        <div style='font-weight: bold; color: #eab308; margin-bottom: 4px; display: flex; align-items: center; gap: 6px; font-size: 13px;'>
            <span>💡</span> Tip
        </div>
        <div style='font-size: 12px; color: #a1a1aa; line-height: 1.4;'>Mark stickers as traded as you go to keep your list up to date.</div>
    </div>
    """, unsafe_allow_html=True)



# --- Main App Views ---

# 1. DASHBOARD TAB
if st.session_state.active_tab == "Dashboard":
    # Compact One-Liner Greeting
    st.markdown(f"""
    <div style="display: flex; align-items: baseline; justify-content: space-between; flex-wrap: wrap; margin-bottom: 20px; border-bottom: 1px solid #1e293b; padding-bottom: 8px; width: 100%;">
        <span style="font-size: 22px; font-weight: 800; color: #f4f4f5;">{get_greeting(selected_profile)}</span>
        <span style="font-size: 13px; color: #71717a;">Dashboard Overview</span>
    </div>
    """, unsafe_allow_html=True)
    
    # Calculate values
    user_col = selected_profile.lower()
    my_trades = [t for t in trades if t["sender"] == selected_profile]
    ready_to_send_val = len(my_trades)
    
    incoming_trades = [t for t in trades if t["recipient"] == selected_profile]
    pending_trades_val = len(incoming_trades)
    
    completed_val = sum(1 for s in stickers if s[user_col] >= 1)
    missing_val = sum(1 for s in stickers if s[user_col] == 0)
    
    # Render metrics grid with links
    st.markdown(f"""
    <div class="metrics-grid">
        <a href="/?profile={selected_profile}&tab=Trades" target="_self" style="text-decoration: none; color: inherit;">
            <div class="metric-card">
                <div style="font-size: 24px; margin-bottom: 6px;">✈️</div>
                <div style="font-size: 32px; font-weight: 800; color: #60a5fa; line-height: 1.1;">{ready_to_send_val}</div>
                <div style="font-size: 14px; font-weight: 600; color: #f4f4f5; margin-top: 6px;">Ready to Send</div>
                <div style="font-size: 11px; color: #71717a; margin-top: 2px;">Stickers ➔</div>
            </div>
        </a>
        <a href="/?profile={selected_profile}&tab=Trades" target="_self" style="text-decoration: none; color: inherit;">
            <div class="metric-card">
                <div style="font-size: 24px; margin-bottom: 6px;">🔄</div>
                <div style="font-size: 32px; font-weight: 800; color: #fb923c; line-height: 1.1;">{pending_trades_val}</div>
                <div style="font-size: 14px; font-weight: 600; color: #f4f4f5; margin-top: 6px;">Pending Trades</div>
                <div style="font-size: 11px; color: #71717a; margin-top: 2px;">Incoming ➔</div>
            </div>
        </a>
        <a href="/?profile={selected_profile}&tab=Collection" target="_self" style="text-decoration: none; color: inherit;">
            <div class="metric-card">
                <div style="font-size: 24px; margin-bottom: 6px;">✅</div>
                <div style="font-size: 32px; font-weight: 800; color: #34d399; line-height: 1.1;">{completed_val}</div>
                <div style="font-size: 14px; font-weight: 600; color: #f4f4f5; margin-top: 6px;">Completed</div>
                <div style="font-size: 11px; color: #71717a; margin-top: 2px;">Stickers ➔</div>
            </div>
        </a>
        <a href="/?profile={selected_profile}&tab=Collection" target="_self" style="text-decoration: none; color: inherit;">
            <div class="metric-card">
                <div style="font-size: 24px; margin-bottom: 6px;">📁</div>
                <div style="font-size: 32px; font-weight: 800; color: #c084fc; line-height: 1.1;">{missing_val}</div>
                <div style="font-size: 14px; font-weight: 600; color: #f4f4f5; margin-top: 6px;">Missing</div>
                <div style="font-size: 11px; color: #71717a; margin-top: 2px;">Stickers ➔</div>
            </div>
        </a>
    </div>
    """, unsafe_allow_html=True)

# 2. TRADES TAB
elif st.session_state.active_tab == "Trades":
    # Compact One-Liner Greeting
    st.markdown(f"""
    <div style="display: flex; align-items: baseline; justify-content: space-between; flex-wrap: wrap; margin-bottom: 20px; border-bottom: 1px solid #1e293b; padding-bottom: 8px; width: 100%;">
        <span style="font-size: 22px; font-weight: 800; color: #f4f4f5;">{get_greeting(selected_profile)}</span>
        <span style="font-size: 13px; color: #71717a;">Here's your trading overview.</span>
    </div>
    """, unsafe_allow_html=True)
    
    user_col = selected_profile.lower()
    my_trades = [t for t in trades if t["sender"] == selected_profile]
    
    if not my_trades:
        st.info("You don't have any tradeable duplicates to send!")
    else:
        trades_by_recipient = {}
        for t in my_trades:
            trades_by_recipient.setdefault(t["recipient"], []).append(t)
            
        selected_trades_to_apply = []
        
        for recipient, rec_trades in trades_by_recipient.items():
            r_emoji = profile_emojis.get(recipient, "👤")
            r_color = profile_colors.get(recipient, "#ffffff")
            r_bg = f"{r_color}1a"
            
            st.markdown(f"""
            <div style="display: flex; align-items: center; gap: 8px; margin-top: 20px; margin-bottom: 12px;">
                <span style="font-size: 18px;">{r_emoji}</span>
                <span style="font-size: 16px; font-weight: bold; color: {r_color};">{recipient}</span>
                <span style="background-color: {r_bg}; color: {r_color}; padding: 2px 8px; border-radius: 12px; font-size: 11px; font-weight: bold; border: 1px solid {r_color}33;">
                    {len(rec_trades)} stickers
                </span>
            </div>
            """, unsafe_allow_html=True)
            
            for idx, trade in enumerate(rec_trades):
                key = f"bulk_chk_{trade['id']}_{recipient.lower()}_{idx}"
                chk_col, details_col = st.columns([1, 25])
                
                with chk_col:
                    if trade["gold"]:
                        st.markdown("<div style='padding-top: 8px; text-align: center;'>🔒</div>", unsafe_allow_html=True)
                        is_checked = False
                    else:
                        is_checked = st.checkbox("", key=key, label_visibility="collapsed")
                        if is_checked:
                            selected_trades_to_apply.append(trade)
                            
                with details_col:
                    stars_str = '★' * trade['stars']
                    if trade["gold"]:
                        gold_label = f"<span style='color: #d97706; font-weight: bold; background-color: #fef3c7; padding: 2px 6px; border-radius: 4px; font-size: 10px; margin-left: 6px;'>Gold</span>"
                        st.markdown(f"""
                        <div class="sticker-row">
                            <div style="font-size: 14px; font-weight: bold; color: #f4f4f5;">
                                {trade['sticker_name']} {gold_label}
                            </div>
                            <div style="font-size: 12px; color: #71717a; font-style: italic;">
                                {trade['album']}
                            </div>
                        </div>
                        """, unsafe_allow_html=True)
                    else:
                        st.markdown(f"""
                        <div class="sticker-row">
                            <div style="font-size: 14px; font-weight: bold; color: #f4f4f5; display: flex; align-items: center; gap: 8px;">
                                {trade['sticker_name']} <span style="color: #fbbf24; font-size: 12px;">{stars_str}</span>
                            </div>
                            <div style="font-size: 12px; color: #71717a; font-style: italic;">
                                {trade['album']}
                            </div>
                        </div>
                        """, unsafe_allow_html=True)
                        
        st.markdown("<div style='margin-top: 16px;'></div>", unsafe_allow_html=True)
        action_col_info, action_col_btn = st.columns([4, 1])
        with action_col_info:
            st.markdown(f"<div style='font-size: 14px; color: #a1a1aa; padding-top: 8px;'>{len(selected_trades_to_apply)} selected</div>", unsafe_allow_html=True)
        with action_col_btn:
            if st.button("Mark Selected", type="primary", use_container_width=True, disabled=len(selected_trades_to_apply) == 0):
                snapshot = [{"id": s["id"], "hana": s["hana"], "jon": s["jon"], "nabil": s["nabil"]} for s in stickers]
                log_database_state(selected_profile, f"Marked {len(selected_trades_to_apply)} trade(s) as completed", snapshot)
                
                for trade in selected_trades_to_apply:
                    sender_col = trade["sender"].lower()
                    recipient_col = trade["recipient"].lower()
                    
                    sticker_row = next(s for s in stickers if s["id"] == trade["id"])
                    new_sender_count = max(0, sticker_row[sender_col] - 1)
                    new_recipient_count = sticker_row[recipient_col] + 1
                    
                    update_ownership(trade["id"], **{
                        "hana": new_sender_count if sender_col == "hana" else (new_recipient_count if recipient_col == "hana" else sticker_row["hana"]),
                        "jon": new_sender_count if sender_col == "jon" else (new_recipient_count if recipient_col == "jon" else sticker_row["jon"]),
                        "nabil": new_sender_count if sender_col == "nabil" else (new_recipient_count if recipient_col == "nabil" else sticker_row["nabil"])
                    })
                
                st.success(f"Successfully applied {len(selected_trades_to_apply)} trade(s)!")
                time.sleep(1)
                st.rerun()

elif st.session_state.active_tab == "Collection":
    user_col = selected_profile.lower()
    
    album_progress = {}
    for album in ordered_albums:
        album_stickers = [s for s in stickers if s["album"] == album]
        owned_count = sum(1 for s in album_stickers if s[user_col] >= 1)
        album_progress[album] = {
            "owned": owned_count,
            "total": len(album_stickers) if album_stickers else 9,
            "pct": int((owned_count / (len(album_stickers) if album_stickers else 9)) * 100)
        }
        
    st.markdown("## 📁 Sticker Collection")
    st.markdown("Browse all albums and view ownership counts. Toggle Edit Mode to manually adjust counts.")
    
    st.markdown("<div style='margin-bottom: 24px;'></div>", unsafe_allow_html=True)
    
    if st.session_state.show_manual_editor:
        if st.session_state.working_counts is None:
            st.session_state.working_counts = {s["id"]: {"hana": s["hana"], "jon": s["jon"], "nabil": s["nabil"]} for s in stickers}
        if st.session_state.undo_backup is None:
            st.session_state.undo_backup = [{"id": s["id"], "hana": s["hana"], "jon": s["jon"], "nabil": s["nabil"]} for s in stickers]
            
        col_undo, col_save = st.columns([1, 1])
        with col_undo:
            if st.button("Undo Current Changes", use_container_width=True):
                st.session_state.undo_backup = None
                st.session_state.working_counts = None
                st.success("Changes reverted successfully!")
                time.sleep(1)
                st.rerun()
        with col_save:
            if st.button("Confirm & Commit", type="primary", use_container_width=True):
                changed_stickers = []
                for s in stickers:
                    orig = next(item for item in st.session_state.undo_backup if item["id"] == s["id"])
                    curr = st.session_state.working_counts[s["id"]]
                    if curr["hana"] != orig["hana"] or curr["jon"] != orig["jon"] or curr["nabil"] != orig["nabil"]:
                        changed_stickers.append((s["id"], curr))
                        
                if changed_stickers:
                    for sticker_id, curr in changed_stickers:
                        update_ownership(sticker_id, hana=curr["hana"], jon=curr["jon"], nabil=curr["nabil"])
                    log_database_state(selected_profile, "Manual adjustments", st.session_state.undo_backup)
                    st.success(f"Changes committed to database! (Updated {len(changed_stickers)} sticker(s))")
                else:
                    st.info("No changes to commit.")
                    
                st.session_state.undo_backup = None
                st.session_state.working_counts = None
                time.sleep(1)
                st.rerun()
                
        search_query = st.text_input("🔍 Filter stickers by name or album", "")
        
        filtered_stickers = []
        for sticker in stickers:
            if not search_query or search_query.lower() in sticker["name"].lower() or search_query.lower() in sticker["album"].lower():
                filtered_stickers.append(sticker)
                
        stickers_by_album = {}
        for s in filtered_stickers:
            stickers_by_album.setdefault(s["album"], []).append(s)
            
        def render_album_rows(stickers_list, user_col):
            for sticker in stickers_list:
                col_name, col_minus, col_val, col_plus = st.columns([3, 1, 1, 1])
                with col_name:
                    stars_str = '★' * sticker['stars']
                    if sticker["is_gold"]:
                        st.markdown(
                            f"<div style='font-size: 16px; line-height: 38px; vertical-align: middle;'><strong>{sticker['name']}</strong> <span style='color: #d97706; font-weight: bold;'>({stars_str}Gold)</span></div>",
                            unsafe_allow_html=True
                        )
                    else:
                        st.markdown(
                            f"<div style='font-size: 16px; line-height: 38px; vertical-align: middle;'><strong>{sticker['name']}</strong> {stars_str}</div>",
                            unsafe_allow_html=True
                        )
                with col_minus:
                    if st.button("➖", key=f"minus_{sticker['id']}", use_container_width=True):
                        current_val = st.session_state.working_counts[sticker["id"]][user_col]
                        orig_val = next(item for item in st.session_state.undo_backup if item["id"] == sticker["id"])[user_col]
                        min_val = 1 if orig_val > 0 else 0
                        new_val = max(min_val, current_val - 1)
                        if new_val != current_val:
                            st.session_state.working_counts[sticker["id"]][user_col] = new_val
                            st.rerun()
                with col_val:
                    current_val = st.session_state.working_counts[sticker["id"]][user_col]
                    st.markdown(f"<div style='text-align: center; font-size: 18px; font-weight: bold; line-height: 38px;'>{current_val}</div>", unsafe_allow_html=True)
                with col_plus:
                    if st.button("➕", key=f"plus_{sticker['id']}", use_container_width=True):
                        current_val = st.session_state.working_counts[sticker["id"]][user_col]
                        st.session_state.working_counts[sticker["id"]][user_col] = current_val + 1
                        st.rerun()
                        
        for album in ordered_albums:
            if album in stickers_by_album:
                album_stickers = stickers_by_album[album]
                completed_by_all = all(
                    (st.session_state.working_counts[s["id"]]["hana"] >= 1 and
                     st.session_state.working_counts[s["id"]]["jon"] >= 1 and
                     st.session_state.working_counts[s["id"]]["nabil"] >= 1)
                    for s in album_stickers
                )
                
                meta = ALBUM_META.get(album, {"emoji": "📁", "color": "#3b82f6"})
                if completed_by_all:
                    with st.expander(f"{meta['emoji']} {album.upper()} — :green[Completed by All]", expanded=False):
                        render_album_rows(album_stickers, user_col)
                else:
                    st.markdown(f"#### <u>{album.upper()}</u>", unsafe_allow_html=True)
                    render_album_rows(album_stickers, user_col)
                    
    else:
        stickers_by_album = {}
        for s in stickers:
            stickers_by_album.setdefault(s["album"], []).append(s)
            
        for album in ordered_albums:
            if album in stickers_by_album:
                album_stickers = stickers_by_album[album]
                progress = album_progress[album]
                meta = ALBUM_META.get(album, {"emoji": "📁", "color": "#3b82f6"})
                
                completed_by_all = all(
                    (s["hana"] >= 1 and s["jon"] >= 1 and s["nabil"] >= 1)
                    for s in album_stickers
                )
                
                comp_badge = "✅ All Done" if completed_by_all else f"{progress['owned']}/{progress['total']}"
                expander_title = f"{meta['emoji']} {album.upper()} — {comp_badge}"
                
                with st.expander(expander_title, expanded=not completed_by_all):
                    table_html = textwrap.dedent(f"""
                    <table style="width: 100%; border-collapse: collapse; margin-top: 8px;">
                        <thead>
                            <tr style="border-bottom: 1px solid #1e293b; color: #71717a; font-size: 13px;">
                                <th style="text-align: left; padding: 8px 0;">Sticker</th>
                                <th style="text-align: center; padding: 8px 0; width: 80px;">🌸 Hana</th>
                                <th style="text-align: center; padding: 8px 0; width: 80px;">⚡ Jon</th>
                                <th style="text-align: center; padding: 8px 0; width: 80px;">🦊 Nabil</th>
                            </tr>
                        </thead>
                        <tbody>
                    """)
                    
                    for sticker in album_stickers:
                        stars_str = '★' * sticker['stars']
                        sticker_display = f"<strong>{sticker['name']}</strong> <span style='color: #fbbf24;'>{stars_str}</span>"
                        if sticker["is_gold"]:
                            sticker_display += " <span style='color: #d97706; font-size: 11px; font-weight: bold;'>[Gold]</span>"
                            
                        h_style = "font-weight: bold; color: #fda4af;" if selected_profile == "Hana" else ""
                        j_style = "font-weight: bold; color: #93c5fd;" if selected_profile == "Jon" else ""
                        n_style = "font-weight: bold; color: #86efac;" if selected_profile == "Nabil" else ""
                        
                        h_val = f"<span style='color: #4b5563;'>0</span>" if sticker['hana'] == 0 else f"<span style='color: #f4f4f5; {h_style}'>{sticker['hana']}</span>"
                        j_val = f"<span style='color: #4b5563;'>0</span>" if sticker['jon'] == 0 else f"<span style='color: #f4f4f5; {j_style}'>{sticker['jon']}</span>"
                        n_val = f"<span style='color: #4b5563;'>0</span>" if sticker['nabil'] == 0 else f"<span style='color: #f4f4f5; {n_style}'>{sticker['nabil']}</span>"
                        
                        row_html = f"""
                        <tr style="border-bottom: 1px solid rgba(30, 41, 59, 0.4); font-size: 14px;">
                            <td style="padding: 10px 0; text-align: left;">{sticker_display}</td>
                            <td style="padding: 10px 0; text-align: center; width: 80px;">{h_val}</td>
                            <td style="padding: 10px 0; text-align: center; width: 80px;">{j_val}</td>
                            <td style="padding: 10px 0; text-align: center; width: 80px;">{n_val}</td>
                        </tr>
                        """
                        table_html += textwrap.dedent(row_html)
                        
                    table_html += "</tbody></table>"
                    st.markdown(table_html, unsafe_allow_html=True)

    st.markdown("<hr style='margin: 32px 0 24px 0; border: 0; border-top: 1px solid #1e293b;'>", unsafe_allow_html=True)
    col_tgl_info, col_tgl_btn = st.columns([3, 1])
    with col_tgl_info:
        if st.session_state.show_manual_editor:
            st.markdown("<div style='padding-top: 8px; font-weight: bold; color: #fb923c;'>⚠️ MANUAL EDITING ACTIVE</div>", unsafe_allow_html=True)
        else:
            st.markdown("<div style='padding-top: 8px; color: #a1a1aa;'>View ownership across all users.</div>", unsafe_allow_html=True)
    with col_tgl_btn:
        if st.session_state.show_manual_editor:
            if st.button("Close Manual Editor ✕", key="btn_close_editor", use_container_width=True):
                st.session_state.show_manual_editor = False
                st.session_state.working_counts = None
                st.session_state.undo_backup = None
                st.rerun()
        else:
            if st.button("✏️ Open Manual Editor", key="btn_open_editor", type="primary", use_container_width=True):
                st.session_state.show_manual_editor = True
                st.rerun()

elif st.session_state.active_tab == "Audit":
    st.markdown("## 🔍 Audit & Upload Center")
    st.markdown("Manage screenshot processing, manual audits, and database rollbacks.")
    
    audit_mode = st.radio("Choose Audit Sub-tab", ["Upload Screenshots", "Screenshot Audit Panel", "History & Rollbacks"], horizontal=True)
    
    st.divider()
    
    if audit_mode == "Upload Screenshots":
        st.markdown("### 📸 Upload Screenshots & Process")
        st.write("Upload screenshot images of your album pages. They will be archived in history and processed by Gemini.")
        
        uploaded_files = st.file_uploader("Select screenshots", type=["png", "jpg", "jpeg"], accept_multiple_files=True)
        
        if uploaded_files:
            if st.button("Process Uploads", type="primary", use_container_width=True):
                if not GEMINI_API_KEY:
                    st.error("GEMINI_API_KEY is not set. Please configure it to process screenshots.")
                else:
                    import datetime
                    from pathlib import Path
                    
                    client = genai.Client(api_key=GEMINI_API_KEY)
                    progress_bar = st.progress(0)
                    status_text = st.empty()
                    
                    snapshot = [{"id": s["id"], "hana": s["hana"], "jon": s["jon"], "nabil": s["nabil"]} for s in stickers]
                    mismatches = []
                    total_files = len(uploaded_files)
                    
                    for idx, file in enumerate(uploaded_files):
                        progress_val = int((idx / total_files) * 100)
                        progress_bar.progress(progress_val)
                        status_text.write(f"Processing image {idx+1} of {total_files}: *{file.name}*...")
                        
                        image_bytes = file.read()
                        
                        try:
                            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                            dest_dir = Path("screenshots/uploaded_history") / selected_profile
                            dest_dir.mkdir(parents=True, exist_ok=True)
                            safe_filename = f"{timestamp}_{file.name}"
                            saved_path = dest_dir / safe_filename
                            with open(saved_path, "wb") as f:
                                f.write(image_bytes)
                        except Exception as e:
                            st.warning(f"Could not archive screenshot locally: {e}")
                            
                        prompt = """
                        Extract the Monopoly GO stickers visible in this screenshot.
                        Rules:
                        - Include only stickers the user owns or has copies of in the image.
                        - "count" should be the total number shown for that sticker in the image.
                        - If the image shows a duplicate count such as +1, return 2 total.
                        - Keep sticker names exactly as they appear when possible.
                        """
                        
                        try:
                            response = client.models.generate_content(
                                model=MODEL_NAME,
                                contents=[
                                    {"role": "user", "parts": [
                                        {"text": prompt},
                                        {"inline_data": {"mime_type": file.type, "data": image_bytes}}
                                    ]}
                                ],
                                config=types.GenerateContentConfig(
                                    response_mime_type="application/json",
                                    response_schema=SetInfo,
                                )
                            )
                            extracted = json.loads(response.text)
                            user_col = selected_profile.lower()
                            
                            for detected_sticker in extracted.get("stickers", []):
                                name = detected_sticker.get("name", "").strip()
                                count = int(detected_sticker.get("count", 0))
                                
                                db_sticker = next((s for s in stickers if s["name"].lower().strip() == name.lower().strip()), None)
                                if db_sticker:
                                    expected_count = db_sticker[user_col]
                                    if expected_count != count:
                                        mismatches.append((db_sticker["name"], expected_count, count))
                                        
                                    if count == 0 and expected_count > 0:
                                        continue
                                        
                                    db_sticker[user_col] = count
                                    update_ownership(
                                        db_sticker["id"],
                                        hana=db_sticker["hana"],
                                        jon=db_sticker["jon"],
                                        nabil=db_sticker["nabil"]
                                    )
                        except Exception as e:
                            st.error(f"Error processing image {file.name}: {e}")
                            
                    progress_bar.progress(100)
                    status_text.write("Screenshot processing complete!")
                    log_database_state(selected_profile, f"Uploaded {total_files} screenshot(s)", snapshot)
                    
                    if mismatches:
                        st.info("Discrepancies found between database expectation and screenshot. Sending warning email...")
                        for m_name, db_c, ss_c in mismatches:
                            trigger_mismatch_email(selected_profile, m_name, db_c, ss_c)
                            
                    st.success("Successfully processed images and updated counts!")
                    time.sleep(2)
                    st.rerun()
                    
    elif audit_mode == "Screenshot Audit Panel":
        st.markdown("### 🔍 Screenshot Viewer & Database Sync")
        
        from pathlib import Path
        user_col = selected_profile.lower()
        
        archive_dir = Path("screenshots/uploaded_history") / selected_profile
        if not archive_dir.exists() or not any(archive_dir.iterdir()):
            st.info(f"No archived screenshots found for {selected_profile}. Try uploading some screenshots first!")
        else:
            image_files = sorted(
                [f for f in archive_dir.iterdir() if f.is_file() and f.suffix.lower() in [".png", ".jpg", ".jpeg"]],
                key=lambda x: x.name,
                reverse=True
            )
            
            if not image_files:
                st.info("No images found in history directory.")
            else:
                file_options = {f.name: f for f in image_files}
                def format_label(filename):
                    try:
                        parts = filename.split("_", 2)
                        date_part = parts[0]
                        time_part = parts[1]
                        orig_name = parts[2] if len(parts) > 2 else ""
                        formatted_time = f"{date_part[:4]}-{date_part[4:6]}-{date_part[6:8]} {time_part[:2]}:{time_part[2:4]}:{time_part[4:6]}"
                        return f"{formatted_time} - {orig_name}"
                    except Exception:
                        return filename
                        
                selected_filename = st.selectbox(
                    "Select screenshot to view/audit",
                    options=list(file_options.keys()),
                    format_func=format_label
                )
                
                selected_file_path = file_options[selected_filename]
                
                col_img, col_audit = st.columns([5, 4])
                
                with col_img:
                    st.image(str(selected_file_path), caption=format_label(selected_filename), use_container_width=True)
                    
                with col_audit:
                    st.markdown("#### Audit & Adjust Counts")
                    st.write("Adjust counts below if any stickers in the screenshot were missed or incorrect:")
                    
                    audit_search = st.text_input("🔍 Quick sticker search", "", key="audit_search_input")
                    filtered_stickers = [
                        s for s in stickers 
                        if not audit_search or audit_search.lower() in s["name"].lower() or audit_search.lower() in s["album"].lower()
                    ]
                    
                    audit_by_album = {}
                    for s in filtered_stickers:
                        audit_by_album.setdefault(s["album"], []).append(s)
                        
                    with st.container(height=500, border=True):
                        for album in ordered_albums:
                            if album in audit_by_album:
                                st.markdown(f"**{album.upper()}**")
                                for sticker in audit_by_album[album]:
                                    col_name, col_minus, col_val, col_plus = st.columns([4, 1.5, 1, 1.5])
                                    with col_name:
                                        if sticker["is_gold"]:
                                            st.markdown(f"<span style='font-size:14px; font-weight:bold;'>{sticker['name']} 👑</span>", unsafe_allow_html=True)
                                        else:
                                            st.markdown(f"<span style='font-size:14px;'>{sticker['name']}</span>", unsafe_allow_html=True)
                                    with col_minus:
                                        if st.button("➖", key=f"audit_minus_{sticker['id']}", use_container_width=True):
                                            min_val = 1 if sticker[user_col] > 0 else 0
                                            new_val = max(min_val, sticker[user_col] - 1)
                                            if new_val != sticker[user_col]:
                                                snapshot = [{"id": s["id"], "hana": s["hana"], "jon": s["jon"], "nabil": s["nabil"]} for s in stickers]
                                                log_database_state(selected_profile, f"Audit decrement: {sticker['name']}", snapshot)
                                                
                                                sticker[user_col] = new_val
                                                update_ownership(sticker["id"], hana=sticker["hana"], jon=sticker["jon"], nabil=sticker["nabil"])
                                                st.rerun()
                                    with col_val:
                                        st.markdown(f"<div style='text-align:center; font-size:14px; font-weight:bold; padding-top:2px;'>{sticker[user_col]}</div>", unsafe_allow_html=True)
                                    with col_plus:
                                        if st.button("➕", key=f"audit_plus_{sticker['id']}", use_container_width=True):
                                            snapshot = [{"id": s["id"], "hana": s["hana"], "jon": s["jon"], "nabil": s["nabil"]} for s in stickers]
                                            log_database_state(selected_profile, f"Audit increment: {sticker['name']}", snapshot)
                                            
                                            sticker[user_col] = sticker[user_col] + 1
                                            update_ownership(sticker["id"], hana=sticker["hana"], jon=sticker["jon"], nabil=sticker["nabil"])
                                            st.rerun()
                                            
    elif audit_mode == "History & Rollbacks":
        st.markdown("### 📜 Database History & Rollbacks")
        st.write("Revert the entire database to a previous state to fix user errors (e.g. uploading out-of-date screenshots).")
        
        history = fetch_history_logs()
        if not history:
            st.info("No history actions logged yet.")
        else:
            for entry in history:
                col_info, col_rev = st.columns([3, 1])
                with col_info:
                    st.markdown(
                        f"**{entry['user_profile']}**: {entry['action']}\n"
                        f"*Logged at {entry['created_at']}*"
                    )
                with col_rev:
                    if st.button("Revert", key=f"rev_{entry['id']}", use_container_width=True):
                        curr_stickers = fetch_sticker_data()
                        curr_snapshot = [{"id": s["id"], "hana": s["hana"], "jon": s["jon"], "nabil": s["nabil"]} for s in curr_stickers]
                        
                        apply_rollback(entry["state_snapshot"])
                        
                        log_database_state(selected_profile, f"Reverted database to version logged at {entry['created_at']}", curr_snapshot)
                        st.success("Database reverted successfully!")
                        time.sleep(1)
                        st.rerun()

st.divider()
st.markdown("<div style='text-align: center; color: #4b5563; font-size: 12px; padding: 20px 0;'>v2.2.0 • Made with ❤️ for sticker collectors</div>", unsafe_allow_html=True)
