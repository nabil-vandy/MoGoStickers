"""
Authentication gate for MoGoStickers.

Uses Streamlit's native OIDC auth (st.login / st.user / st.logout) with Google.
This gives persistent auto-login via a signed identity cookie — the "remember who's
logged in on this device" requirement — without third-party cookie hacks.

Requires an [auth] block in .streamlit/secrets.toml (see README). The logged-in
Google email is matched to a row in the `profiles` table:
  * unknown email + valid ?invite=<code>  -> claim invite (screenname pre-filled)
  * unknown email, no invite               -> "request access" screen (pending)
  * known but not approved                 -> "pending approval" screen
  * known and approved                     -> returned as the current user
"""
import os

import streamlit as st

import db


def require_auth():
    """Gate the app. Returns the approved current-user profile dict, or st.stop()s."""
    # Dev/preview auto-login: if MOGO_DEV_EMAIL is set (local secrets.toml only —
    # never in Streamlit Cloud), skip Google OIDC and load that real profile. This
    # lets the sandboxed Claude preview, which can't complete the OAuth redirect,
    # run the full app as a real user. Absent in production, so login is unchanged.
    dev_email = os.getenv("MOGO_DEV_EMAIL")
    if dev_email and not (getattr(st, "user", None) and st.user.is_logged_in):
        profile = db.get_profile_by_email(dev_email.strip())
        if profile:
            st.session_state["_dev_login"] = True
            return profile
        # Email isn't a real profile — fall through to the normal Google flow.

    if not getattr(st, "user", None) or not st.user.is_logged_in:
        _render_login()
        st.stop()

    email = (st.user.email or "").strip()
    profile = db.get_profile_by_email(email)

    # New email — try to claim an invite (screenname is pre-filled on the invite).
    if profile is None:
        invite_code = st.query_params.get("invite")
        invite = db.get_invite(invite_code) if invite_code else None
        if invite and (not invite.get("email") or invite["email"].lower() == email.lower()):
            profile = db.claim_invite(invite, email)
        else:
            _render_request_access(email)
            st.stop()

    if profile and not profile.get("approved"):
        _render_pending(profile)
        st.stop()

    return profile


def render_account_controls(profile):
    """Sidebar: who's logged in, plus logout. Screennames are admin-managed."""
    st.markdown(
        f"<div style='font-size:11px;font-weight:bold;color:#71717a;text-transform:uppercase;"
        f"letter-spacing:.05em;margin-bottom:8px;'>Account</div>",
        unsafe_allow_html=True,
    )
    st.markdown(
        f"<div style='display:flex;align-items:center;gap:8px;margin-bottom:10px;'>"
        f"<span style='font-size:18px;'>{profile.get('emoji','👤')}</span>"
        f"<span style='font-weight:bold;color:{profile.get('color','#fff')};'>"
        f"{profile['screenname']}</span></div>",
        unsafe_allow_html=True,
    )
    if st.button("Log out", key="logout_btn", use_container_width=True):
        st.logout()


# --- gate screens -----------------------------------------------------------
def _shell(title, body_html, show_login=False, show_logout=False):
    st.markdown(
        f"""
        <div style='max-width:460px;margin:8vh auto 0;text-align:center;'>
            <div style='font-size:40px;'>🎲</div>
            <div style='font-size:26px;font-weight:800;color:#f4f4f5;margin-top:6px;'>{title}</div>
            <div style='font-size:14px;color:#a1a1aa;margin-top:10px;line-height:1.5;'>{body_html}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    cols = st.columns([1, 2, 1])
    with cols[1]:
        if show_login:
            if st.button("Continue with Google", type="primary", use_container_width=True):
                st.login("google")
        if show_logout:
            if st.button("Use a different account", use_container_width=True):
                st.logout()


def _render_login():
    _shell(
        "Monopoly GO! Sticker Share",
        "Sign in to track your stickers and coordinate trades.",
        show_login=True,
    )


def _render_request_access(email):
    _shell(
        "Request access",
        f"You're signed in as <b>{email}</b>, but you're not on the list yet.<br>"
        "Pick a screenname and an admin will approve you.",
        show_logout=True,
    )
    cols = st.columns([1, 2, 1])
    with cols[1]:
        screenname = st.text_input("Screenname", key="req_screenname",
                                   placeholder="e.g. RefinedBoot32")
        if st.button("Request access", type="primary", use_container_width=True,
                     disabled=not screenname.strip()):
            created = db.create_profile(email=email, screenname=screenname.strip(),
                                        approved=False)
            if created:
                st.success("Request submitted — you'll get in once an admin approves you.")
            st.rerun()


def _render_pending(profile):
    _shell(
        "Pending approval",
        f"Thanks, <b>{profile['screenname']}</b>! Your account is waiting for an admin "
        "to approve it. Check back soon.",
        show_logout=True,
    )
