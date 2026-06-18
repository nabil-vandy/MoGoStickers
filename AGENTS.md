# Codex Guide

## Project Purpose

This repo tracks Monopoly GO sticker ownership for three users: `Hana`, `Jon`, and `Nabil`.
The production web dashboard is deployed at [mogostickers.streamlit.app](https://mogostickers.streamlit.app).

## Important Files

- `app.py`: Real-time interactive Streamlit web dashboard and database editor.
- `screenshots/uploaded_history/`: Archives of user-uploaded screenshots.

## Commands

Check python syntax:
```bash
make syntax
```

Start the Streamlit web app:
```bash
make run
```

## Coding Notes

- Keep the Streamlit UI extremely premium and fast.
- Do not hard-code API keys.
- Once a sticker count is above zero for a user, screenshot processing in `app.py` must never overwrite it back to zero.
- Avoid broad rewrites. Simple, clean, well-commented functions are preferred.

## Task Boundary Guides

### Update Web Application Layout/Styling/Logic
* **Scope:**
  * `app.py`
  * `AGENTS.md` only if coding rules change
  * `README.md` only if config instructions change
* **Check:**
  ```bash
  make syntax
  ```
