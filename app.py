import os
import json
import urllib.request
import urllib.error
import streamlit as st
from google import genai
from google.genai import types
from pydantic import BaseModel
import time

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
if not SUPABASE_URL or not SUPABASE_KEY:
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
    return supabase_request("database_history?select=*&order=created_at.desc&limit=10")

def log_database_state(user_profile, action, state_snapshot):
    payload = {
        "user_profile": user_profile,
        "action": action,
        "state_snapshot": state_snapshot
    }
    supabase_request("database_history", method="POST", payload=payload)

def update_ownership(sticker_id, hana, jon, nabil):
    payload = {
        "hana": hana,
        "jon": jon,
        "nabil": nabil
    }
    # Using PATCH with ID in query string
    return supabase_request(f"ownership?sticker_id=eq.{sticker_id}", method="PATCH", payload=payload)

def apply_rollback(snapshot):
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
st.set_page_config(page_title="Monopoly GO! Sticker Share", page_icon="🎲", layout="centered")

# Custom Premium Styling
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;600;800&display=swap');
    
    html, body, [class*="css"] {
        font-family: 'Outfit', sans-serif;
    }

    /* Circles Container */
    .profile-container {
        display: flex;
        justify-content: center;
        gap: 32px;
        margin-bottom: 24px;
        padding-top: 10px;
    }

    /* Circle Avatar */
    .avatar-circle {
        width: 90px;
        height: 90px;
        border-radius: 50%;
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 32px;
        box-shadow: 0 4px 6px -1px rgba(0,0,0,0.15);
        transition: all 0.3s ease;
        border: 4px solid rgba(128, 128, 128, 0.2);
        background-color: rgba(128, 128, 128, 0.08);
    }

    .avatar-circle:hover {
        transform: scale(1.1);
        cursor: pointer;
    }

    /* Gold indicator text */
    .gold-sticker-tag {
        color: #d97706;
        font-weight: bold;
        background-color: #fef3c7;
        padding: 2px 6px;
        border-radius: 4px;
        font-size: 11px;
        border: 1px solid #fde68a;
    }
</style>
""", unsafe_allow_html=True)

st.title("🎲 Monopoly GO! Sticker Share")
st.markdown("Easily coordinate sticker sharing and view trades in real-time.")

# --- Session State Initialization ---
# Auto-load profile from query parameters if present, else fallback
url_profile = st.query_params.get("profile")
if url_profile in ["Hana", "Jon", "Nabil"]:
    st.session_state.selected_profile = url_profile
elif "selected_profile" not in st.session_state:
    st.session_state.selected_profile = "Hana"

# Local undo backup state
if "undo_backup" not in st.session_state:
    st.session_state.undo_backup = None

selected_profile = st.session_state.selected_profile

# --- Header Circle Selector ---
st.markdown("### Select Active Profile")
col1, col2, col3 = st.columns(3)

profiles_meta = [
    {"name": "Hana", "emoji": "🌸", "color": "#fda4af", "col": col1},
    {"name": "Jon", "emoji": "⚡", "color": "#93c5fd", "col": col2},
    {"name": "Nabil", "emoji": "🦊", "color": "#86efac", "col": col3}
]

for p in profiles_meta:
    with p["col"]:
        is_selected = (selected_profile == p["name"])
        border_style = f"border: 4px solid {p['color']}; box-shadow: 0 10px 15px -3px {p['color']}66; transform: scale(1.05);" if is_selected else ""
        bg_style = f"background-color: {p['color']}22;" if is_selected else ""
        
        st.markdown(f"""
        <div class="profile-container">
            <a href="/?profile={p['name']}" target="_self" style="text-decoration: none; color: inherit;">
                <div class="avatar-circle" style="{border_style} {bg_style}">
                    {p['emoji']}
                </div>
            </a>
        </div>
        """, unsafe_allow_html=True)
        
        if st.button(f"Active: {p['name']}" if is_selected else f"Select {p['name']}", key=f"btn_{p['name']}", use_container_width=True):
            st.session_state.selected_profile = p["name"]
            st.query_params["profile"] = p["name"]
            st.rerun()

st.divider()

# Fetch updated dataset
stickers = fetch_sticker_data()
trades = find_trade_rows(stickers)

# Build a list of unique albums in the order they appear in the database
ordered_albums = []
for s in stickers:
    if s["album"] not in ordered_albums:
        ordered_albums.append(s["album"])

# --- Active User Panel ---
profile_emojis = {"Hana": "🌸", "Jon": "⚡", "Nabil": "🦊"}
profile_colors = {"Hana": "#fda4af", "Jon": "#93c5fd", "Nabil": "#86efac"}
active_emoji = profile_emojis.get(selected_profile, "👤")
active_color = profile_colors.get(selected_profile, "#ffffff")
st.markdown(
    f'## <span style="color: {active_color};">{active_emoji} {selected_profile}\'s</span> Stickers to Send',
    unsafe_allow_html=True
)

# Calculate trades where active profile is sender
my_trades = [t for t in trades if t["sender"] == selected_profile]

with st.container(border=True):
    if not my_trades:
        st.info("You don't have any tradeable duplicates to send!")
    else:
        # Group trades by album/set
        trades_by_album = {}
        for t in my_trades:
            trades_by_album.setdefault(t["album"], []).append(t)
            
        for album in ordered_albums:
            if album in trades_by_album:
                st.markdown(f"#### <u>{album.upper()}</u>", unsafe_allow_html=True)
                for idx, trade in enumerate(trades_by_album[album]):
                    # Gold format: Monorail Conductor (★★★★★Gold) without recipient text or Mark Traded button
                    if trade["gold"]:
                        st.markdown(
                            f"<div style='font-size: 20px; line-height: 38px; vertical-align: middle;'>• <strong>{trade['sticker_name']}</strong> <span style='color: #d97706; font-weight: bold;'>({'★' * trade['stars']}Gold)</span></div>",
                            unsafe_allow_html=True
                        )
                    else:
                        # Regular format: Marge ★ send to Jon
                        col_text, col_btn = st.columns([3, 1])
                        with col_text:
                            r_emoji = profile_emojis.get(trade['recipient'], "👤")
                            r_color = profile_colors.get(trade['recipient'], "#ffffff")
                            st.markdown(
                                f"<div style='font-size: 20px; line-height: 38px; vertical-align: middle;'>• <strong>{trade['sticker_name']}</strong> {'★' * trade['stars']} send to {r_emoji} <span style='color: {r_color}; font-weight: bold;'>{trade['recipient']}</span></div>",
                                unsafe_allow_html=True
                            )
                        with col_btn:
                            if st.button("Mark Traded", key=f"trade_{trade['id']}_{trade['recipient']}_{idx}", use_container_width=True):
                                # Save snapshot to history first
                                snapshot = [{"id": s["id"], "hana": s["hana"], "jon": s["jon"], "nabil": s["nabil"]} for s in stickers]
                                log_database_state(selected_profile, f"Marked trade: {trade['sticker_name']} to {trade['recipient']}", snapshot)
                                
                                # Find sender / recipient counts
                                sender_col = trade["sender"].lower()
                                recipient_col = trade["recipient"].lower()
                                
                                sticker_row = next(s for s in stickers if s["id"] == trade["id"])
                                new_sender_count = max(0, sticker_row[sender_col] - 1)
                                new_recipient_count = sticker_row[recipient_col] + 1
                                
                                # Update
                                update_ownership(trade["id"], **{
                                    "hana": new_sender_count if sender_col == "hana" else (new_recipient_count if recipient_col == "hana" else sticker_row["hana"]),
                                    "jon": new_sender_count if sender_col == "jon" else (new_recipient_count if recipient_col == "jon" else sticker_row["jon"]),
                                    "nabil": new_sender_count if sender_col == "nabil" else (new_recipient_count if recipient_col == "nabil" else sticker_row["nabil"])
                                })
                                
                                st.success(f"Applied trade! Sent '{trade['sticker_name']}' to {trade['recipient']}.")
                                time.sleep(1)
                                st.rerun()

# Section Selector (Screenshots vs Manual Mode vs Database Audit)
mode = st.radio("Choose Action", ["Upload Screenshots", "Manual Edit Mode", "Database Audit"], horizontal=True)

if mode == "Upload Screenshots":
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
                
                # Store pre-upload state snapshot
                snapshot = [{"id": s["id"], "hana": s["hana"], "jon": s["jon"], "nabil": s["nabil"]} for s in stickers]
                
                mismatches = []
                total_files = len(uploaded_files)
                
                for idx, file in enumerate(uploaded_files):
                    progress_val = int((idx / total_files) * 100)
                    progress_bar.progress(progress_val)
                    status_text.write(f"Processing image {idx+1} of {total_files}: *{file.name}*...")
                    
                    image_bytes = file.read()
                    
                    # 1. Archive the screenshot locally
                    try:
                        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                        dest_dir = Path("screenshots/uploaded_history") / selected_profile
                        dest_dir.mkdir(parents=True, exist_ok=True)
                        # Avoid filename collisions
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
                        
                        # Apply updates
                        user_col = selected_profile.lower()
                        for detected_sticker in extracted.get("stickers", []):
                            name = detected_sticker.get("name", "").strip()
                            count = int(detected_sticker.get("count", 0))
                            
                            # Find in stickers list
                            db_sticker = next((s for s in stickers if s["name"].lower().strip() == name.lower().strip()), None)
                            if db_sticker:
                                # Mismatch/Verification logic
                                expected_count = db_sticker[user_col]
                                if expected_count != count:
                                    mismatches.append((db_sticker["name"], expected_count, count))
                                
                                # Prevent zero regressions
                                if count == 0 and expected_count > 0:
                                    # Skip setting to zero to preserve ownership invariant
                                    continue
                                
                                # Update counts in local copy for database sync
                                db_sticker[user_col] = count
                                
                                # Save to Supabase
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
                
                # Log state change
                log_database_state(selected_profile, f"Uploaded {total_files} screenshot(s)", snapshot)
                
                # Trigger emails if mismatches found
                if mismatches:
                    st.info("Discrepancies found between database expectation and screenshot. Sending warning email...")
                    for m_name, db_c, ss_c in mismatches:
                        trigger_mismatch_email(selected_profile, m_name, db_c, ss_c)
                
                st.success("Successfully processed images and updated counts!")
                time.sleep(2)
                st.rerun()

elif mode == "Manual Edit Mode":
    # Manual Edit Mode
    st.markdown("### ✏️ Manual Edit Mode")
    st.write("Edit sticker counts manually. A local undo option is available to revert recent changes.")
    
    # Save snapshot for undo backup if not set
    if st.session_state.undo_backup is None:
        st.session_state.undo_backup = [{"id": s["id"], "hana": s["hana"], "jon": s["jon"], "nabil": s["nabil"]} for s in stickers]
    
    col_undo, col_save = st.columns([1, 1])
    with col_undo:
        if st.button("Undo Current Changes", use_container_width=True):
            if st.session_state.undo_backup:
                # Apply backup
                apply_rollback(st.session_state.undo_backup)
                st.session_state.undo_backup = None
                st.success("Changes reverted successfully!")
                time.sleep(1)
                st.rerun()
    with col_save:
        if st.button("Confirm & Commit", type="primary", use_container_width=True):
            # Save snapshot to database history
            log_database_state(selected_profile, "Manual adjustments", st.session_state.undo_backup)
            st.session_state.undo_backup = None
            st.success("Changes committed to database history!")
            time.sleep(1)
            st.rerun()
    
    search_query = st.text_input("🔍 Filter stickers by name or album", "")
    
    user_col = selected_profile.lower()
    
    # Filter stickers first
    filtered_stickers = []
    for sticker in stickers:
        if not search_query or search_query.lower() in sticker["name"].lower() or search_query.lower() in sticker["album"].lower():
            filtered_stickers.append(sticker)
            
    # Group by album
    stickers_by_album = {}
    for s in filtered_stickers:
        stickers_by_album.setdefault(s["album"], []).append(s)
        
    # Display grouped manual edit mode
    for album in ordered_albums:
        if album in stickers_by_album:
            st.markdown(f"#### <u>{album.upper()}</u>", unsafe_allow_html=True)
            for sticker in stickers_by_album[album]:
                col_name, col_minus, col_val, col_plus = st.columns([3, 1, 1, 1])
                with col_name:
                    # Gold Format: Monorail Conductor (★★★★★Gold)
                    # Regular Format: Marge ★
                    if sticker["is_gold"]:
                        st.markdown(
                            f"<div style='font-size: 20px; line-height: 38px; vertical-align: middle;'><strong>{sticker['name']}</strong> <span style='color: #d97706; font-weight: bold;'>({'★' * sticker['stars']}Gold)</span></div>",
                            unsafe_allow_html=True
                        )
                    else:
                        st.markdown(
                            f"<div style='font-size: 20px; line-height: 38px; vertical-align: middle;'><strong>{sticker['name']}</strong> {'★' * sticker['stars']}</div>",
                            unsafe_allow_html=True
                        )
                
                with col_minus:
                    if st.button("➖", key=f"minus_{sticker['id']}", use_container_width=True):
                        # Ensure count doesn't drop to 0 if it was owned (>0)
                        min_val = 1 if sticker[user_col] > 0 else 0
                        new_val = max(min_val, sticker[user_col] - 1)
                        if new_val != sticker[user_col]:
                            sticker[user_col] = new_val
                            update_ownership(sticker["id"], hana=sticker["hana"], jon=sticker["jon"], nabil=sticker["nabil"])
                            st.rerun()
                
                with col_val:
                    st.markdown(f"<div style='text-align: center; font-size: 20px; font-weight: bold; line-height: 38px;'>{sticker[user_col]}</div>", unsafe_allow_html=True)
                
                with col_plus:
                    if st.button("➕", key=f"plus_{sticker['id']}", use_container_width=True):
                        new_val = sticker[user_col] + 1
                        sticker[user_col] = new_val
                        update_ownership(sticker["id"], hana=sticker["hana"], jon=sticker["jon"], nabil=sticker["nabil"])
                        st.rerun()

elif mode == "Database Audit":
    st.markdown("### 🔍 Database Audit & Screenshot Viewer")
    st.write("Compare your database counts against previously uploaded screenshots to verify and correct any missing stickers.")
    
    from pathlib import Path
    
    user_col = selected_profile.lower()
    
    # 1. Locate archived screenshots
    archive_dir = Path("screenshots/uploaded_history") / selected_profile
    if not archive_dir.exists() or not any(archive_dir.iterdir()):
        st.info(f"No archived screenshots found for {selected_profile}. Try uploading some screenshots first!")
    else:
        # Get all files and sort them (most recent first)
        image_files = sorted(
            [f for f in archive_dir.iterdir() if f.is_file() and f.suffix.lower() in [".png", ".jpg", ".jpeg"]],
            key=lambda x: x.name,
            reverse=True
        )
        
        if not image_files:
            st.info("No images found in history directory.")
        else:
            # Let the user select a file to audit
            file_options = {f.name: f for f in image_files}
            # Make a user-friendly label showing date/time
            def format_label(filename):
                try:
                    # Filename is formatted like YYYYMMDD_HHMMSS_original_name
                    parts = filename.split("_", 2)
                    date_part = parts[0]
                    time_part = parts[1]
                    orig_name = parts[2] if len(parts) > 2 else ""
                    # Format: YYYY-MM-DD HH:MM:SS (orig_name)
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
            
            # Display image and adjustment panel in columns
            col_img, col_audit = st.columns([5, 4])
            
            with col_img:
                st.image(str(selected_file_path), caption=format_label(selected_filename), use_container_width=True)
            
            with col_audit:
                st.markdown("#### Audit & Adjust Counts")
                st.write("Adjust counts below if any stickers in the screenshot were missed or incorrect:")
                
                # Search filter for stickers inside audit
                audit_search = st.text_input("🔍 Quick sticker search", "", key="audit_search_input")
                
                # Filter stickers
                filtered_stickers = [
                    s for s in stickers 
                    if not audit_search or audit_search.lower() in s["name"].lower() or audit_search.lower() in s["album"].lower()
                ]
                
                # Group by album
                audit_by_album = {}
                for s in filtered_stickers:
                    audit_by_album.setdefault(s["album"], []).append(s)
                
                # Scrollable/compact container for manual adjustments in audit mode
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
                                        # Ensure count doesn't drop to 0 if it was owned (>0)
                                        min_val = 1 if sticker[user_col] > 0 else 0
                                        new_val = max(min_val, sticker[user_col] - 1)
                                        if new_val != sticker[user_col]:
                                            # Save snapshot before change
                                            snapshot = [{"id": s["id"], "hana": s["hana"], "jon": s["jon"], "nabil": s["nabil"]} for s in stickers]
                                            log_database_state(selected_profile, f"Audit decrement: {sticker['name']}", snapshot)
                                            
                                            sticker[user_col] = new_val
                                            update_ownership(sticker["id"], hana=sticker["hana"], jon=sticker["jon"], nabil=sticker["nabil"])
                                            st.rerun()
                                with col_val:
                                    st.markdown(f"<div style='text-align:center; font-size:14px; font-weight:bold; padding-top:2px;'>{sticker[user_col]}</div>", unsafe_allow_html=True)
                                with col_plus:
                                    if st.button("➕", key=f"audit_plus_{sticker['id']}", use_container_width=True):
                                        # Save snapshot before change
                                        snapshot = [{"id": s["id"], "hana": s["hana"], "jon": s["jon"], "nabil": s["nabil"]} for s in stickers]
                                        log_database_state(selected_profile, f"Audit increment: {sticker['name']}", snapshot)
                                        
                                        sticker[user_col] = sticker[user_col] + 1
                                        update_ownership(sticker["id"], hana=sticker["hana"], jon=sticker["jon"], nabil=sticker["nabil"])
                                        st.rerun()

st.divider()

# --- Collapsed Database History & Rollbacks ---
with st.expander("📜 View Database History & Rollbacks"):
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
                    # Save current state as history snapshot before reverting
                    curr_stickers = fetch_sticker_data()
                    curr_snapshot = [{"id": s["id"], "hana": s["hana"], "jon": s["jon"], "nabil": s["nabil"]} for s in curr_stickers]
                    
                    # Apply target rollback
                    apply_rollback(entry["state_snapshot"])
                    
                    # Log revert action
                    log_database_state(selected_profile, f"Reverted database to version logged at {entry['created_at']}", curr_snapshot)
                    
                    st.success("Database reverted successfully!")
                    time.sleep(1)
                    st.rerun()
