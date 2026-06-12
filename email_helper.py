"""Helper for formatting and sending trade alert emails via SMTP."""

from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import smtplib


def build_html_body(trades):
    regular_trades = [t for t in trades if not t["gold"]]
    gold_trades = [t for t in trades if t["gold"]]

    def row_html(t):
        return f"""
        <tr>
            <td style="padding: 12px 16px; border-bottom: 1px solid #e2e8f0; font-weight: 600; color: #1e293b;">{t['sender']}</td>
            <td style="padding: 12px 16px; border-bottom: 1px solid #e2e8f0; color: #475569;">{t['set_name']}</td>
            <td style="padding: 12px 16px; border-bottom: 1px solid #e2e8f0; font-weight: 500; color: #334155;">{t['sticker_name']}</td>
            <td style="padding: 12px 16px; border-bottom: 1px solid #e2e8f0; font-weight: 600; color: #0f766e;">{t['recipient']}</td>
            <td style="padding: 12px 16px; border-bottom: 1px solid #e2e8f0; text-align: center;"><span style="background-color: #f1f5f9; color: #475569; padding: 4px 8px; border-radius: 12px; font-size: 12px; font-weight: 700;">★ {t['stars']}</span></td>
        </tr>
        """

    def table_html(trade_list):
        rows = "\n".join(row_html(t) for t in trade_list)
        return f"""
        <div style="overflow-x: auto; margin-bottom: 24px; border-radius: 12px; border: 1px solid #e2e8f0; box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05);">
            <table style="width: 100%; border-collapse: collapse; text-align: left; font-size: 14px;">
                <thead>
                    <tr style="background-color: #f8fafc; border-bottom: 1px solid #e2e8f0;">
                        <th style="padding: 12px 16px; font-weight: 700; color: #475569; text-transform: uppercase; font-size: 11px; letter-spacing: 0.05em;">Sender</th>
                        <th style="padding: 12px 16px; font-weight: 700; color: #475569; text-transform: uppercase; font-size: 11px; letter-spacing: 0.05em;">Set Name</th>
                        <th style="padding: 12px 16px; font-weight: 700; color: #475569; text-transform: uppercase; font-size: 11px; letter-spacing: 0.05em;">Sticker Name</th>
                        <th style="padding: 12px 16px; font-weight: 700; color: #475569; text-transform: uppercase; font-size: 11px; letter-spacing: 0.05em;">Recipient</th>
                        <th style="padding: 12px 16px; font-weight: 700; color: #475569; text-transform: uppercase; font-size: 11px; letter-spacing: 0.05em; text-align: center;">Stars</th>
                    </tr>
                </thead>
                <tbody>
                    {rows}
                </tbody>
            </table>
        </div>
        """

    content = ""
    if regular_trades:
        content += '<h2 style="color: #4f46e5; font-size: 18px; margin-top: 0; margin-bottom: 12px; font-weight: 700;">Standard Sticker Trades</h2>'
        content += table_html(regular_trades)

    if gold_trades:
        content += '<h2 style="color: #d97706; font-size: 18px; margin-top: 24px; margin-bottom: 12px; font-weight: 700;">Gold Sticker Trades (Special Events Only)</h2>'
        content += table_html(gold_trades)

    html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
            background-color: #f3f4f6;
            margin: 0;
            padding: 20px 10px;
        }}
    </style>
</head>
<body>
    <div style="max-width: 650px; margin: 0 auto; background-color: #ffffff; border-radius: 16px; overflow: hidden; box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.1);">
        <!-- Header -->
        <div style="background: linear-gradient(135deg, #4f46e5 0%, #7c3aed 100%); padding: 32px 24px; text-align: center; color: #ffffff;">
            <span style="background-color: rgba(255, 255, 255, 0.2); padding: 6px 12px; border-radius: 9999px; font-size: 12px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.05em;">Sticker Exchange</span>
            <h1 style="margin: 12px 0 0 0; font-size: 26px; font-weight: 800; letter-spacing: -0.025em;">Monopoly GO! Trades Ready</h1>
            <p style="margin: 8px 0 0 0; font-size: 14px; color: #e0e7ff; font-weight: 500;">New sticker sharing opportunities have been detected.</p>
        </div>
        
        <!-- Content -->
        <div style="padding: 24px;">
            {content}
            
            <div style="margin-top: 32px; padding-top: 20px; border-top: 1px solid #f1f5f9; text-align: center; color: #94a3b8; font-size: 12px;">
                <p style="margin: 0;">This email was sent automatically by the MoGoTracker pipeline running on GitHub Actions.</p>
            </div>
        </div>
    </div>
</body>
</html>
"""
    return html


def build_text_body(trades):
    regular_trades = [t for t in trades if not t["gold"]]
    gold_trades = [t for t in trades if t["gold"]]

    def list_trades(trade_list):
        lines = []
        for t in trade_list:
            lines.append(f"- {t['sender']} has duplicate '{t['sticker_name']}' ({t['set_name']}, {t['stars']}★) -> send to {t['recipient']}")
        return "\n".join(lines)

    body = "Monopoly GO! Trades Ready\n==========================\n\n"
    if regular_trades:
        body += "Standard Sticker Trades:\n"
        body += list_trades(regular_trades)
        body += "\n\n"
    if gold_trades:
        body += "Gold Sticker Trades (Special Events Only):\n"
        body += list_trades(gold_trades)
        body += "\n\n"

    return body


def send_trade_email(trades, recipients, smtp_server, smtp_port, smtp_username, smtp_password):
    if not smtp_server or not smtp_username or not smtp_password:
        raise ValueError("SMTP configuration (server, username, password) is incomplete.")

    msg = MIMEMultipart("alternative")
    msg["Subject"] = "Monopoly GO! Trades Available"
    msg["From"] = smtp_username
    msg["To"] = ", ".join(recipients)

    text_content = build_text_body(trades)
    html_content = build_html_body(trades)

    msg.attach(MIMEText(text_content, "plain"))
    msg.attach(MIMEText(html_content, "html"))

    # Select SMTP connection protocol based on port
    port = int(smtp_port) if smtp_port else 587
    if port == 465:
        # SSL/TLS connection
        with smtplib.SMTP_SSL(smtp_server, port) as server:
            server.login(smtp_username, smtp_password)
            server.sendmail(smtp_username, recipients, msg.as_string())
    else:
        # STARTTLS connection (usually 587 or 25)
        with smtplib.SMTP(smtp_server, port) as server:
            server.starttls()
            server.login(smtp_username, smtp_password)
            server.sendmail(smtp_username, recipients, msg.as_string())
