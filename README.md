# MoGoStickers

Interactive Streamlit web dashboard for tracking Monopoly GO sticker ownership and coordinating trades for Hana, Jon, and Nabil.
The production web dashboard is deployed at [mogostickers.streamlit.app](https://mogostickers.streamlit.app).

## Features

- **Dashboard**: View stickers owned by each user and progress of their albums.
- **Trades**: Automatically calculate trade opportunities (who has duplicates of what the others need).
- **Collection**: Browse through the complete set lists and manually edit sticker counts.
- **Audit**: Upload screenshots of sticker albums to automatically update ownership counts via Gemini.
- **History & Rollbacks**: Revert the database to previous states in case of user or processing errors.

## Setup

1. **Initialize Virtual Environment & Install Dependencies**:
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   make setup
   ```

2. **Configure Environment Variables**:
   Create a `.env` file in the root directory and configure it as shown in `.env.example`:
   ```ini
   SUPABASE_URL="https://your-project.supabase.co"
   SUPABASE_KEY="your-anon-key"
   GEMINI_API_KEY="your-gemini-key"
   GEMINI_MODEL="gemini-3.1-flash-lite"
   ```

## Run

To run the Streamlit web application locally:
```bash
make run
```
