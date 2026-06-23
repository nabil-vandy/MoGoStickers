import datetime
import textwrap
import time

import streamlit as st

import auth
import db
import gemini

# --- App Settings & Page Config ---
st.set_page_config(page_title="Monopoly GO! Sticker Share", page_icon="🎲", layout="wide")

if not db.config_ok():
    st.error("SUPABASE_URL and SUPABASE_SERVICE_KEY are not set. Configure them in your "
             "Streamlit secrets / environment.")
    st.stop()

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

    /* Trade row wrapper: lock icon + sticker-row side by side (gold stickers only) */
    .trade-row-wrapper {
        display: flex;
        align-items: center;
        gap: 8px;
        margin-bottom: 6px;
        width: 100%;
    }
    .trade-row-wrapper .trade-chk {
        flex: 0 0 auto;
        display: flex;
        align-items: center;
        justify-content: center;
        min-width: 28px;
    }
    .trade-row-wrapper .sticker-row {
        flex: 1 1 0%;
        min-width: 0;
    }

    @media (max-width: 768px) {
        .metrics-grid {
            grid-template-columns: repeat(2, 1fr);
            gap: 12px;
        }
    }

    /* Hide Streamlit default UI elements (keep stHeader/stToolbar for sidebar toggle/MainMenu overlay) */
    [data-testid="stFooter"], [data-testid="stAppDeployButton"], [data-testid="stDecoration"] {
        visibility: hidden;
        display: none !important;
    }
    [data-testid="stHeader"] {
        background: transparent !important;
        border: none !important;
        box-shadow: none !important;
        /* Keep header visible so the sidebar expand button remains accessible */
        min-height: 3.5rem !important;
        height: auto !important;
    }

    /* Ensure ALL sidebar toggle/expand buttons are always visible and clickable.
       Streamlit uses different data-testid values across versions, so we target all variants. */
    [data-testid="stSidebarCollapseButton"],
    [data-testid="stExpandSidebarButton"],
    [data-testid="collapsedControl"],
    [data-testid="stSidebarCollapsedControl"],
    div[data-testid="collapsedControl"],
    button[data-testid="stSidebarCollapseButton"],
    button[data-testid="stExpandSidebarButton"] {
        visibility: visible !important;
        display: inline-flex !important;
        z-index: 999999 !important;
        opacity: 1 !important;
        pointer-events: auto !important;
    }

    /* Remove big gap on top and bottom of the page */
    .block-container {
        padding-top: 1.5rem !important;
        padding-bottom: 1.5rem !important;
    }
</style>
""", unsafe_allow_html=True)

# --- Authentication gate ---
current_user = auth.require_auth()
my_id = current_user["id"]
my_name = current_user["screenname"]

# --- Session State Initialization ---
TABS = ["Dashboard", "Trades", "Upload", "Manifest"]
if current_user.get("is_admin"):
    TABS.append("Admin")

url_tab = st.query_params.get("tab")
if url_tab in TABS:
    st.session_state.active_tab = url_tab
elif "active_tab" not in st.session_state:
    st.session_state.active_tab = "Dashboard"

st.session_state.setdefault("undo_backup", None)
st.session_state.setdefault("working_counts", None)
st.session_state.setdefault("stickers_cache", None)
st.session_state.setdefault("pending_review", None)

# Fetch shared data
pool = db.get_pool_profiles()
if st.session_state.stickers_cache is None:
    st.session_state.stickers_cache = db.fetch_stickers()
stickers = st.session_state.stickers_cache

# Album order as it appears in the database
ordered_albums = []
for s in stickers:
    if s["album"] not in ordered_albums:
        ordered_albums.append(s["album"])


# --- Trade Calculator -------------------------------------------------------
def find_trade_rows(stickers, pool):
    """A user can GIVE a sticker when extras>=1; a user WANTS it when not owned.
    Recipients must have started their collection (own >= 10 stickers) to cut noise."""
    trades = []
    user_ids = [p["id"] for p in pool]
    name_by_id = {p["id"]: p["screenname"] for p in pool}

    owned_counts = {uid: 0 for uid in user_ids}
    for s in stickers:
        for uid in user_ids:
            if db.ownership_for(s, uid)["owned"]:
                owned_counts[uid] += 1

    for s in stickers:
        o = {uid: db.ownership_for(s, uid) for uid in user_ids}
        senders = [uid for uid in user_ids if o[uid]["extras"] >= 1]
        recipients = [uid for uid in user_ids
                      if not o[uid]["owned"] and owned_counts[uid] >= 10]
        for sender in senders:
            available = o[sender]["extras"]
            for recipient in recipients[:available]:
                trades.append({
                    "sticker_id": s["id"],
                    "sender_id": sender, "sender": name_by_id[sender],
                    "recipient_id": recipient, "recipient": name_by_id[recipient],
                    "sticker_name": s["name"], "album": s["album"],
                    "stars": s["stars"], "gold": s["is_gold"],
                })
    return trades


trades = find_trade_rows(stickers, pool)

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


def get_greeting(name):
    hour = datetime.datetime.now().hour
    if hour < 12:
        return f"Good morning, {name}! ☀️"
    elif hour < 18:
        return f"Good afternoon, {name}! 👋"
    else:
        return f"Good evening, {name}! 🌙"


def albums_needing_upload(stickers, user_id):
    """Albums where the user still has an unowned sticker — the only ones worth uploading."""
    needed = []
    for album in ordered_albums:
        album_stickers = [s for s in stickers if s["album"] == album]
        if any(not db.ownership_for(s, user_id)["owned"] for s in album_stickers):
            needed.append(album)
    return needed


# --- Sidebar Layout ---
with st.sidebar:
    st.markdown("""
    <div style='padding: 10px 0; margin-bottom: 20px;'>
        <div style='font-size: 24px; font-weight: 800; color: #f4f4f5; display: flex; align-items: center; gap: 10px;'>
            <span>🎲</span> Monopoly GO!
        </div>
        <div style='font-size: 14px; color: #3b82f6; font-weight: 600; margin-top: -4px; margin-left: 34px;'>Sticker Share <span style='color: #71717a; font-size: 0.85em; font-weight: normal; margin-left: 4px;'>v3.0.2</span></div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown("<div style='font-size: 11px; font-weight: bold; color: #71717a; text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 8px;'>Navigation</div>", unsafe_allow_html=True)

    tab_icons = {"Dashboard": "📊", "Trades": "⚡", "Upload": "🔍", "Manifest": "📁", "Admin": "🛠️"}
    for tab in TABS:
        is_active = (st.session_state.active_tab == tab)
        btn_type = "primary" if is_active else "secondary"
        if st.button(f"{tab_icons.get(tab, '•')}  {tab}", key=f"nav_{tab}",
                     use_container_width=True, type=btn_type):
            st.session_state.active_tab = tab
            st.query_params["tab"] = tab
            st.rerun()

    st.markdown("<div style='margin: 20px 0; border-top: 1px solid #1e293b;'></div>", unsafe_allow_html=True)

    auth.render_account_controls(current_user)

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
    st.markdown(f"""
    <div style="display: flex; align-items: baseline; justify-content: space-between; flex-wrap: wrap; margin-bottom: 20px; border-bottom: 1px solid #1e293b; padding-bottom: 8px; width: 100%;">
        <span style="font-size: 22px; font-weight: 800; color: #f4f4f5;">{get_greeting(my_name)}</span>
        <span style="font-size: 13px; color: #71717a;">Dashboard Overview</span>
    </div>
    """, unsafe_allow_html=True)

    ready_to_send_val = sum(1 for t in trades if t["sender_id"] == my_id)
    pending_trades_val = sum(1 for t in trades if t["recipient_id"] == my_id)
    completed_val = sum(1 for s in stickers if db.ownership_for(s, my_id)["owned"])
    missing_val = sum(1 for s in stickers if not db.ownership_for(s, my_id)["owned"])

    st.markdown(f"""
    <div class="metrics-grid">
        <a href="/?tab=Trades" target="_self" style="text-decoration: none; color: inherit;">
            <div class="metric-card">
                <div style="font-size: 24px; margin-bottom: 6px;">✈️</div>
                <div style="font-size: 32px; font-weight: 800; color: #60a5fa; line-height: 1.1;">{ready_to_send_val}</div>
                <div style="font-size: 14px; font-weight: 600; color: #f4f4f5; margin-top: 6px;">Ready to Send</div>
                <div style="font-size: 11px; color: #71717a; margin-top: 2px;">Stickers ➔</div>
            </div>
        </a>
        <a href="/?tab=Trades" target="_self" style="text-decoration: none; color: inherit;">
            <div class="metric-card">
                <div style="font-size: 24px; margin-bottom: 6px;">🔄</div>
                <div style="font-size: 32px; font-weight: 800; color: #fb923c; line-height: 1.1;">{pending_trades_val}</div>
                <div style="font-size: 14px; font-weight: 600; color: #f4f4f5; margin-top: 6px;">Pending Trades</div>
                <div style="font-size: 11px; color: #71717a; margin-top: 2px;">Incoming ➔</div>
            </div>
        </a>
        <a href="/?tab=Manifest" target="_self" style="text-decoration: none; color: inherit;">
            <div class="metric-card">
                <div style="font-size: 24px; margin-bottom: 6px;">✅</div>
                <div style="font-size: 32px; font-weight: 800; color: #34d399; line-height: 1.1;">{completed_val}</div>
                <div style="font-size: 14px; font-weight: 600; color: #f4f4f5; margin-top: 6px;">Completed</div>
                <div style="font-size: 11px; color: #71717a; margin-top: 2px;">Stickers ➔</div>
            </div>
        </a>
        <a href="/?tab=Manifest" target="_self" style="text-decoration: none; color: inherit;">
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
    st.markdown(f"""
    <div style="display: flex; align-items: baseline; justify-content: space-between; flex-wrap: wrap; margin-bottom: 20px; border-bottom: 1px solid #1e293b; padding-bottom: 8px; width: 100%;">
        <span style="font-size: 22px; font-weight: 800; color: #f4f4f5;">{get_greeting(my_name)}</span>
        <span style="font-size: 13px; color: #71717a;">Here's your trading overview.</span>
    </div>
    """, unsafe_allow_html=True)

    name_by_id = {p["id"]: p for p in pool}
    my_trades = [t for t in trades if t["sender_id"] == my_id]

    if not my_trades:
        st.info("You don't have any tradeable duplicates to send!")
    else:
        trades_by_recipient = {}
        for t in my_trades:
            trades_by_recipient.setdefault(t["recipient_id"], []).append(t)

        selected_trades_to_apply = []

        for recipient_id, rec_trades in trades_by_recipient.items():
            rp = name_by_id.get(recipient_id, {})
            r_emoji = rp.get("emoji", "👤")
            r_color = rp.get("color", "#ffffff")
            r_name = rp.get("screenname", "Unknown")
            r_bg = f"{r_color}1a"

            st.markdown(f"""
            <div style="display: flex; align-items: center; gap: 8px; margin-top: 20px; margin-bottom: 12px;">
                <span style="font-size: 18px;">{r_emoji}</span>
                <span style="font-size: 16px; font-weight: bold; color: {r_color};">{r_name}</span>
                <span style="background-color: {r_bg}; color: {r_color}; padding: 2px 8px; border-radius: 12px; font-size: 11px; font-weight: bold; border: 1px solid {r_color}33;">
                    {len(rec_trades)} stickers
                </span>
            </div>
            """, unsafe_allow_html=True)

            for idx, trade in enumerate(rec_trades):
                key = f"bulk_chk_{trade['sticker_id']}_{recipient_id}_{idx}"
                stars_str = '★' * trade['stars']

                if trade["gold"]:
                    gold_label = "<span style='color: #d97706; font-weight: bold; background-color: #fef3c7; padding: 2px 6px; border-radius: 4px; font-size: 10px; margin-left: 6px;'>Gold</span>"
                    sticker_label = f"{trade['sticker_name']} {gold_label}"
                    st.markdown(f"""
                    <div class="trade-row-wrapper">
                        <div class="trade-chk">🔒</div>
                        <div class="sticker-row">
                            <div style="font-size: 14px; font-weight: bold; color: #f4f4f5;">{sticker_label}</div>
                            <div style="font-size: 12px; color: #71717a; font-style: italic;">{trade['album']}</div>
                        </div>
                    </div>
                    """, unsafe_allow_html=True)
                else:
                    if st.checkbox(f"{trade['sticker_name']}  {stars_str}  —  {trade['album']}", key=key):
                        selected_trades_to_apply.append(trade)

        st.markdown("<div style='margin-top: 16px;'></div>", unsafe_allow_html=True)
        action_col_info, action_col_btn = st.columns([4, 1])
        with action_col_info:
            st.markdown(f"<div style='font-size: 14px; color: #a1a1aa; padding-top: 8px;'>{len(selected_trades_to_apply)} selected</div>", unsafe_allow_html=True)
        with action_col_btn:
            if st.button("Mark Selected", type="primary", use_container_width=True,
                         disabled=len(selected_trades_to_apply) == 0):
                db.log_history(my_id, f"Marked {len(selected_trades_to_apply)} trade(s) as completed",
                               db.snapshot_ownership(stickers, pool))
                for trade in selected_trades_to_apply:
                    s = next(s for s in stickers if s["id"] == trade["sticker_id"])
                    snd = db.ownership_for(s, trade["sender_id"])
                    rcv = db.ownership_for(s, trade["recipient_id"])
                    # sender gives one duplicate; recipient now owns it
                    db.upsert_ownership(trade["sender_id"], trade["sticker_id"],
                                        owned=True, extras=max(0, snd["extras"] - 1))
                    db.upsert_ownership(trade["recipient_id"], trade["sticker_id"],
                                        owned=True, extras=rcv["extras"])
                st.success(f"Successfully applied {len(selected_trades_to_apply)} trade(s)!")
                time.sleep(1)
                st.rerun()

# 3. UPLOAD TAB
elif st.session_state.active_tab == "Upload":
    st.markdown("## 🔍 Upload Center")
    st.markdown("Upload screenshots, review what the analysis found, and edit **your** counts manually.")

    audit_mode = st.radio("Choose Upload Sub-tab",
                          ["Upload Screenshots", "Review Last Upload", "Manual Edit"],
                          horizontal=True)
    st.divider()

    # ---- Upload Screenshots ----
    if audit_mode == "Upload Screenshots":
        needed = albums_needing_upload(stickers, my_id)
        if needed:
            st.markdown("#### 📋 You only need to upload these sets")
            st.caption("Sets you've already completed are skipped — no need to screenshot them.")
            chips = " ".join(
                f"<span style='display:inline-block;background:#121824;border:1px solid #1e293b;"
                f"border-radius:12px;padding:4px 10px;margin:3px;font-size:12px;'>"
                f"{ALBUM_META.get(a, {}).get('emoji', '📁')} {a}</span>"
                for a in needed
            )
            st.markdown(chips, unsafe_allow_html=True)
        else:
            st.success("🎉 You own every sticker — nothing to upload!")
        st.markdown("<div style='margin-bottom:16px;'></div>", unsafe_allow_html=True)

        st.markdown("### 📸 Upload & Analyze")
        st.write("Upload album page screenshots. They're analyzed and shown for review — "
                 "**nothing is saved until you confirm.**")

        if not gemini.GEMINI_API_KEY:
            st.error("GEMINI_API_KEY is not set. Configure it to analyze screenshots.")
        else:
            uploaded_files = st.file_uploader("Select screenshots",
                                              type=["png", "jpg", "jpeg"],
                                              accept_multiple_files=True)
            if uploaded_files and st.button("Analyze (no changes yet)", type="primary",
                                            use_container_width=True):
                progress = st.progress(0)
                status = st.empty()
                review_rows = []
                for idx, file in enumerate(uploaded_files):
                    status.write(f"Analyzing {idx + 1} of {len(uploaded_files)}: *{file.name}*…")
                    image_bytes = file.read()
                    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                    path = f"{my_id}/{ts}_{file.name}"
                    stored = db.upload_screenshot(path, image_bytes, file.type)
                    try:
                        raw, detected = gemini.analyze(image_bytes, file.type, stickers)
                    except Exception as e:
                        st.error(f"Error analyzing {file.name}: {e}")
                        continue
                    upload = db.create_upload(my_id, stored, file.name, gemini.MODEL_NAME, raw)
                    items_payload = []
                    for d in detected:
                        match_sticker, method = gemini.match(d["name"], stickers)
                        prev = db.ownership_for(match_sticker, my_id) if match_sticker else {"owned": False, "extras": 0}
                        row = {
                            "upload_id": upload["id"] if upload else None,
                            "image_path": stored,
                            "detected_name": d["name"],
                            "detected_owned": d["owned"],
                            "detected_extras": d["extras"],
                            "matched_sticker_id": match_sticker["id"] if match_sticker else None,
                            "matched_name": match_sticker["name"] if match_sticker else None,
                            "match_method": method,
                            "prev_owned": prev["owned"],
                            "prev_extras": prev["extras"],
                            "new_owned": d["owned"] if match_sticker else None,
                            "new_extras": d["extras"] if match_sticker else None,
                        }
                        review_rows.append(row)
                        items_payload.append({
                            "upload_id": upload["id"] if upload else None,
                            "detected_name": d["name"], "detected_owned": d["owned"],
                            "detected_extras": d["extras"],
                            "matched_sticker_id": match_sticker["id"] if match_sticker else None,
                            "match_method": method,
                            "previous_owned": prev["owned"], "previous_extras": prev["extras"],
                            "new_owned": d["owned"] if match_sticker else None,
                            "new_extras": d["extras"] if match_sticker else None,
                            "applied": False,
                        })
                    db.add_upload_items(items_payload)
                    progress.progress(int(((idx + 1) / len(uploaded_files)) * 100))
                st.session_state.pending_review = review_rows
                status.write("Analysis complete — review below.")
                st.rerun()

        # Review-before-commit panel
        if st.session_state.pending_review:
            st.markdown("### 🧐 Review before saving")
            st.caption("Compare against the in-game '+N'. Edit any row, then confirm. "
                       "Unmatched names are skipped.")
            matched = [r for r in st.session_state.pending_review if r["matched_sticker_id"]]
            unmatched = [r for r in st.session_state.pending_review if not r["matched_sticker_id"]]

            editable = [{
                "Sticker": r["matched_name"],
                "Detected as": r["detected_name"],
                "Match": r["match_method"],
                "Own": bool(r["new_owned"]),
                "+N": int(r["new_extras"] or 0),
                "Was": f"{'own' if r['prev_owned'] else '—'} +{r['prev_extras']}",
            } for r in matched]

            edited = st.data_editor(
                editable, use_container_width=True, hide_index=True, key="review_editor",
                column_config={
                    "Sticker": st.column_config.TextColumn(disabled=True),
                    "Detected as": st.column_config.TextColumn(disabled=True),
                    "Match": st.column_config.TextColumn(disabled=True),
                    "Was": st.column_config.TextColumn(disabled=True),
                    "Own": st.column_config.CheckboxColumn(),
                    "+N": st.column_config.NumberColumn(min_value=0, step=1),
                },
            )

            if unmatched:
                with st.expander(f"⚠️ {len(unmatched)} unmatched detection(s) — not saved"):
                    for r in unmatched:
                        st.write(f"• **{r['detected_name']}** (own={r['detected_owned']}, +{r['detected_extras']})")

            col_a, col_b = st.columns([1, 1])
            with col_a:
                if st.button("Discard", use_container_width=True):
                    st.session_state.pending_review = None
                    st.rerun()
            with col_b:
                if st.button("✅ Confirm & Save", type="primary", use_container_width=True):
                    db.log_history(my_id, "Applied screenshot upload",
                                   db.snapshot_ownership(stickers, pool))
                    applied = 0
                    upload_ids = set()
                    for r, e in zip(matched, edited):
                        new_owned = bool(e["Own"])
                        new_extras = int(e["+N"] or 0)
                        # Safeguard: don't silently un-own a known sticker.
                        if r["prev_owned"] and not new_owned:
                            new_owned = True
                        db.upsert_ownership(my_id, r["matched_sticker_id"], new_owned, new_extras)
                        if r["upload_id"]:
                            upload_ids.add(r["upload_id"])
                        applied += 1
                    for uid in upload_ids:
                        db.set_upload_status(uid, "applied")
                    st.session_state.pending_review = None
                    st.success(f"Saved {applied} sticker update(s)!")
                    time.sleep(1)
                    st.rerun()

    # ---- Review Last Upload ----
    elif audit_mode == "Review Last Upload":
        st.markdown("### 🔎 Review Last Upload")
        st.write("Exactly what the analysis detected, how each line was matched, and what changed.")
        uploads = db.latest_uploads(my_id)
        if not uploads:
            st.info("No uploads yet. Process some screenshots first!")
        else:
            labels = {u["id"]: f"{u['created_at']} — {u.get('original_name', '')}" for u in uploads}
            chosen = st.selectbox("Select an upload", options=[u["id"] for u in uploads],
                                  format_func=lambda i: labels.get(i, i))
            upload = next(u for u in uploads if u["id"] == chosen)
            items = db.get_upload_items(chosen)

            col_img, col_tbl = st.columns([5, 6])
            with col_img:
                if upload.get("image_path"):
                    url = db.signed_screenshot_url(upload["image_path"])
                    if url:
                        st.image(url, use_container_width=True)
                    else:
                        st.caption("(image unavailable)")
            with col_tbl:
                sticker_name = {s["id"]: s["name"] for s in stickers}
                table = [{
                    "Detected": it["detected_name"],
                    "Matched": sticker_name.get(it["matched_sticker_id"], "— unmatched —"),
                    "How": it["match_method"],
                    "Owned": it["new_owned"],
                    "+N": it["new_extras"],
                    "Was": f"{'own' if it['previous_owned'] else '—'} +{it['previous_extras'] or 0}",
                } for it in items]
                st.dataframe(table, use_container_width=True, hide_index=True)

            with st.expander("🔬 Raw Gemini response (why the count was chosen)"):
                st.json(upload.get("raw_response") or {})

    # ---- Manual Edit ----
    elif audit_mode == "Manual Edit":
        st.markdown("### ✏️ Manual Edit")
        st.write("Adjust **your** owned stickers and extra (+N) counts directly. "
                 "Nothing is saved until you Confirm & Commit.")

        # Edit only the current user's owned/extras.
        if st.session_state.working_counts is None:
            st.session_state.working_counts = {
                s["id"]: dict(db.ownership_for(s, my_id)) for s in stickers
            }
        if st.session_state.undo_backup is None:
            st.session_state.undo_backup = {
                s["id"]: dict(db.ownership_for(s, my_id)) for s in stickers
            }

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
                changed = []
                for s in stickers:
                    orig = st.session_state.undo_backup[s["id"]]
                    curr = st.session_state.working_counts[s["id"]]
                    if curr["owned"] != orig["owned"] or curr["extras"] != orig["extras"]:
                        changed.append((s["id"], curr))
                if changed:
                    db.log_history(my_id, "Manual adjustments", db.snapshot_ownership(stickers, pool))
                    for sticker_id, curr in changed:
                        db.upsert_ownership(my_id, sticker_id, curr["owned"], curr["extras"])
                    st.success(f"Committed {len(changed)} change(s) to the database!")
                else:
                    st.info("No changes to commit.")
                st.session_state.undo_backup = None
                st.session_state.working_counts = None
                time.sleep(1)
                st.rerun()

        search_query = st.text_input("🔍 Filter stickers by name or album", "")
        filtered = [s for s in stickers if not search_query
                    or search_query.lower() in s["name"].lower()
                    or search_query.lower() in s["album"].lower()]
        by_album = {}
        for s in filtered:
            by_album.setdefault(s["album"], []).append(s)

        def render_edit_rows(rows):
            for sticker in rows:
                wc = st.session_state.working_counts[sticker["id"]]
                col_name, col_own, col_minus, col_val, col_plus = st.columns([3, 1.4, 1, 1, 1])
                with col_name:
                    stars_str = '★' * sticker['stars']
                    gold = " <span style='color:#d97706;font-weight:bold;'>(Gold)</span>" if sticker["is_gold"] else ""
                    st.markdown(
                        f"<div style='font-size:16px;line-height:38px;'><strong>{sticker['name']}</strong> {stars_str}{gold}</div>",
                        unsafe_allow_html=True)
                with col_own:
                    owned = st.checkbox("Own", value=wc["owned"], key=f"own_{sticker['id']}")
                    if owned != wc["owned"]:
                        wc["owned"] = owned
                        if not owned:
                            wc["extras"] = 0
                        st.rerun()
                with col_minus:
                    if st.button("➖", key=f"minus_{sticker['id']}", use_container_width=True,
                                 disabled=not wc["owned"]):
                        if wc["extras"] > 0:
                            wc["extras"] -= 1
                            st.rerun()
                with col_val:
                    badge = f"+{wc['extras']}" if wc["owned"] else "—"
                    st.markdown(f"<div style='text-align:center;font-size:18px;font-weight:bold;line-height:38px;'>{badge}</div>", unsafe_allow_html=True)
                with col_plus:
                    if st.button("➕", key=f"plus_{sticker['id']}", use_container_width=True,
                                 disabled=not wc["owned"]):
                        wc["extras"] += 1
                        st.rerun()

        for album in ordered_albums:
            if album in by_album:
                meta = ALBUM_META.get(album, {"emoji": "📁", "color": "#3b82f6"})
                st.markdown(f"#### <u>{meta['emoji']} {album.upper()}</u>", unsafe_allow_html=True)
                render_edit_rows(by_album[album])

# 4. MANIFEST TAB
elif st.session_state.active_tab == "Manifest":
    album_progress = {}
    for album in ordered_albums:
        album_stickers = [s for s in stickers if s["album"] == album]
        owned_count = sum(1 for s in album_stickers if db.ownership_for(s, my_id)["owned"])
        total = len(album_stickers) if album_stickers else 9
        album_progress[album] = {"owned": owned_count, "total": total,
                                 "pct": int((owned_count / total) * 100)}

    st.markdown("## 📁 Manifest")
    st.markdown("Browse all albums and view ownership across every member.")
    st.markdown("<div style='margin-bottom: 24px;'></div>", unsafe_allow_html=True)

    # Read-only totals for every pool member (dynamic columns).
    by_album = {}
    for s in stickers:
        by_album.setdefault(s["album"], []).append(s)

    for album in ordered_albums:
        if album not in by_album:
            continue
        album_stickers = by_album[album]
        progress = album_progress[album]
        meta = ALBUM_META.get(album, {"emoji": "📁", "color": "#3b82f6"})

        completed_by_all = all(
            all(db.ownership_for(s, p["id"])["owned"] for p in pool)
            for s in album_stickers
        ) if pool else False

        comp_badge = "✅ All Done" if completed_by_all else f"{progress['owned']}/{progress['total']}"
        with st.expander(f"{meta['emoji']} {album.upper()} — {comp_badge}", expanded=not completed_by_all):
            header_cells = "".join(
                f"<th style='text-align:center;padding:8px 0;width:90px;'>{p.get('emoji','👤')} {p['screenname']}</th>"
                for p in pool
            )
            table_html = textwrap.dedent(f"""
            <table style="width: 100%; border-collapse: collapse; margin-top: 8px;">
                <thead>
                    <tr style="border-bottom: 1px solid #1e293b; color: #71717a; font-size: 13px;">
                        <th style="text-align: left; padding: 8px 0;">Sticker</th>
                        {header_cells}
                    </tr>
                </thead>
                <tbody>
            """)
            for sticker in album_stickers:
                stars_str = '★' * sticker['stars']
                disp = f"<strong>{sticker['name']}</strong> <span style='color: #fbbf24;'>{stars_str}</span>"
                if sticker["is_gold"]:
                    disp += " <span style='color: #d97706; font-size: 11px; font-weight: bold;'>[Gold]</span>"
                cells = ""
                for p in pool:
                    o = db.ownership_for(sticker, p["id"])
                    total = db.total_for(o["owned"], o["extras"])
                    hl = f"font-weight:bold;color:{p.get('color','#f4f4f5')};" if p["id"] == my_id else "color:#f4f4f5;"
                    val = "<span style='color:#4b5563;'>0</span>" if total == 0 else f"<span style='{hl}'>{total}</span>"
                    cells += f"<td style='padding:10px 0;text-align:center;width:90px;'>{val}</td>"
                table_html += textwrap.dedent(f"""
                <tr style="border-bottom: 1px solid rgba(30, 41, 59, 0.4); font-size: 14px;">
                    <td style="padding: 10px 0; text-align: left;">{disp}</td>
                    {cells}
                </tr>
                """)
            table_html += "</tbody></table>"
            st.markdown(table_html, unsafe_allow_html=True)

# 5. ADMIN TAB
elif st.session_state.active_tab == "Admin":
    st.markdown("## 🛠️ Admin")
    st.markdown("Approve new members and create invites.")

    st.markdown("### ⏳ Pending approvals")
    pending = db.list_pending_profiles()
    if not pending:
        st.info("No one is waiting for approval.")
    else:
        for p in pending:
            c1, c2, c3 = st.columns([3, 2, 1])
            with c1:
                st.markdown(f"**{p['screenname']}** · {p['email']}")
            with c2:
                new_sn = st.text_input("Screenname", value=p["screenname"],
                                       key=f"pend_sn_{p['id']}", label_visibility="collapsed")
            with c3:
                if st.button("Approve", key=f"approve_{p['id']}", use_container_width=True):
                    if new_sn.strip() and new_sn.strip() != p["screenname"]:
                        db.update_profile(p["id"], screenname=new_sn.strip())
                    db.update_profile(p["id"], approved=True)
                    st.success(f"Approved {new_sn.strip() or p['screenname']}.")
                    st.rerun()

    st.divider()
    st.markdown("### ✉️ Create an invite")
    st.caption("Set the screenname now; it's pre-filled when they sign in.")
    with st.form("invite_form"):
        inv_sn = st.text_input("Screenname *", placeholder="e.g. RefinedBoot32")
        inv_email = st.text_input("Lock to email (optional)")
        c1, c2 = st.columns(2)
        with c1:
            inv_emoji = st.text_input("Emoji", value="👤")
        with c2:
            inv_color = st.color_picker("Color", value="#93c5fd")
        inv_admin = st.checkbox("Grant admin")
        inv_auto = st.checkbox("Auto-approve (skip pending queue)", value=True)
        submitted = st.form_submit_button("Generate invite", type="primary",
                                          use_container_width=True)
        if submitted and inv_sn.strip():
            import secrets
            code = secrets.token_urlsafe(8)
            created = db.create_invite(code, inv_sn.strip(), inv_email.strip() or None,
                                       inv_emoji or "👤", inv_color, inv_admin, inv_auto)
            if created:
                st.success(f"Invite for **{inv_sn.strip()}** created!")
                st.code(f"?invite={code}", language="text")
                st.caption("Share your app URL with `?invite=<code>` appended, e.g. "
                           "`https://mogostickers.streamlit.app/?invite=" + code + "`")

    invites = db.list_invites()
    if invites:
        with st.expander("Existing invites"):
            for inv in invites:
                used = "✅ used" if inv.get("used_by") else "🟢 open"
                st.write(f"`{inv['code']}` → **{inv['screenname']}** ({used})")

st.divider()
st.markdown(
    "<div style='text-align: center; color: #71717a; font-size: 12px; padding: 8px 0;'>"
    "Monopoly GO! Sticker Share · v3.0.2</div>",
    unsafe_allow_html=True,
)
