"""
Changelog for MoGoStickers — drives the "What's new" welcome-back popup.

Streamlit Cloud has no git available, so the release history is maintained here
as plain data. Entries are newest-first. Each entry is one dated release:

    {"id": "3.2.0", "version": "3.2.0", "date": "2026-06-24",
     "changes": ["bullet", ...]}

`id` is the stable marker stored per-user in profiles.last_seen_changelog. A user
sees the popup whenever there is at least one entry newer than their stored id;
all unseen entries are shown together as a single combined set.
"""

# Newest first. Bump this list (and app version) when shipping user-facing changes.
CHANGELOG = [
    {
        "id": "3.2.0",
        "version": "3.2.0",
        "date": "2026-06-24",
        "changes": [
            "Trades: new \"Mark received\" button — tap the stickers a friend "
            "already sent you and they instantly drop off everyone's send list, "
            "so no one re-sends them.",
            "Trades: cleaner layout — \"⚡ Trade Center\" heading, a \"👯 Send to "
            "friends\" section, and aligned 🔒 / 📥 icons.",
            "Admins can now switch into another player's view from the sidebar to "
            "see and manage their account.",
            "Consistent headings and styling across every page.",
            "This \"What's new\" popup, so you always know what changed.",
        ],
    },
    {
        "id": "3.1.1",
        "version": "3.1.1",
        "date": "2026-06-22",
        "changes": [
            "Faster screenshot uploads — multiple images are analyzed in parallel.",
            "Screenshots are auto-cropped to trim the game's UI before analysis.",
            "Upload review now shows only the stickers whose counts changed.",
            "Various navigation and layout fixes.",
        ],
    },
    {
        "id": "3.0.0",
        "version": "3.0.0",
        "date": "2026-06-21",
        "changes": [
            "Brand-new navigation: Dashboard, Trades, Upload, and Manifest pages.",
            "Personal accounts with Google sign-in and per-player sticker tracking.",
        ],
    },
]


def latest_id():
    """The newest changelog id, or None if the changelog is empty."""
    return CHANGELOG[0]["id"] if CHANGELOG else None


def entries_since(last_seen_id):
    """All entries newer than `last_seen_id` (newest first).

    With no marker (None), returns the full changelog. When `last_seen_id` matches
    the newest entry the user is caught up and this returns an empty list.
    """
    if not last_seen_id:
        return list(CHANGELOG)
    out = []
    for entry in CHANGELOG:
        if entry["id"] == last_seen_id:
            break
        out.append(entry)
    return out
