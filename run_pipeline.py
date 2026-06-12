"""Orchestrate the Monopoly GO sticker tracking daily execution pipeline."""

import os
import sys
from pathlib import Path

# Ensure absolute import path resolves correctly
ROOT_DIR = Path(__file__).parent.resolve()
sys.path.append(str(ROOT_DIR))

import gemini_vision
import tradeEngine
from email_helper import send_trade_email


def main():
    print("--- Pipeline Started ---")
    processed = gemini_vision.load_processed_log()
    images_to_process = gemini_vision.pending_images(processed)

    if not images_to_process:
        print("No new screenshots to process. Pipeline ending early.")
        sys.exit(0)

    print(f"Found {len(images_to_process)} new screenshot(s) to process.")

    # Execute Gemini Vision processing
    print("Running Gemini Vision processing...")
    gemini_vision.main()

    # Determine trades from the updated database
    print("Running Trade Engine...")
    try:
        rows = tradeEngine.load_database()
    except FileNotFoundError as e:
        print(f"Database error: {e}")
        sys.exit(1)

    trades = tradeEngine.find_trade_rows(rows)

    if not trades:
        print("No trades found. Pipeline ending early.")
        sys.exit(0)

    print(f"Found {len(trades)} active trade(s). Sending email alerts...")

    # Fetch SMTP details from environment
    smtp_server = os.getenv("SMTP_SERVER")
    smtp_port = os.getenv("SMTP_PORT", "587")
    smtp_username = os.getenv("SMTP_USERNAME")
    smtp_password = os.getenv("SMTP_PASSWORD")
    email_recipients_str = os.getenv("EMAIL_RECIPIENTS")

    if not email_recipients_str:
        print("Error: EMAIL_RECIPIENTS is not configured. Cannot send email.")
        sys.exit(1)

    recipients = [r.strip() for r in email_recipients_str.split(",") if r.strip()]
    if not recipients:
        print("Error: EMAIL_RECIPIENTS contains no valid email addresses.")
        sys.exit(1)

    if not smtp_server or not smtp_username or not smtp_password:
        print("Error: SMTP configuration is missing. Cannot send email.")
        sys.exit(1)

    try:
        send_trade_email(
            trades=trades,
            recipients=recipients,
            smtp_server=smtp_server,
            smtp_port=smtp_port,
            smtp_username=smtp_username,
            smtp_password=smtp_password
        )
        print("--- Email Sent Successfully. Pipeline Completed. ---")
    except Exception as e:
        print(f"Failed to send email: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
