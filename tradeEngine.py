"""Find sticker sharing opportunities from the local sticker database."""

import csv
import os
from pathlib import Path

DATABASE_NAME = "sticker_database.csv"
DATABASE_PATH_ENV = os.getenv("DATABASE_PATH")
if DATABASE_PATH_ENV:
    DATABASE_PATH = Path(DATABASE_PATH_ENV)
else:
    GDRIVE_DB_PATH = Path("/content/drive/MyDrive/1. Personal Projects/MoGoTracker/output") / DATABASE_NAME
    if GDRIVE_DB_PATH.exists():
        DATABASE_PATH = GDRIVE_DB_PATH
    else:
        DATABASE_PATH = Path("output") / DATABASE_NAME

USERS = ["Hana", "Jon", "Nabil"]
NO_TRADES_MESSAGE = "No sticker trades available."


def parse_count(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def is_gold_sticker(row):
    value = str(row.get("Gold_Status", "")).strip().casefold()
    return value in {"true", "1", "yes"}


def clean_field(row, field_name):
    return str(row.get(field_name, "")).strip()


def star_number(row):
    return parse_count(row.get("Star_Number"))


def load_database(path=DATABASE_PATH):
    if not path.exists():
        raise FileNotFoundError(
            f"Could not find {path}. Run makeDatabase.py and gemini_vision.py first."
        )

    with path.open(newline="", encoding="utf-8") as file:
        return list(csv.DictReader(file))


def find_trade_rows(rows, users=USERS):
    trades = []

    for row_index, row in enumerate(rows):
        sticker_name = clean_field(row, "Sticker_Name")
        if not sticker_name:
            continue

        set_name = clean_field(row, "Set_Name")
        stars = star_number(row)
        gold = is_gold_sticker(row)
        counts = {user: parse_count(row.get(user)) for user in users}
        senders = [user for user, count in counts.items() if count > 1]
        recipients = [user for user, count in counts.items() if count == 0]

        for sender in senders:
            available = counts[sender] - 1
            for recipient in recipients[:available]:
                trades.append(
                    {
                        "sender": sender,
                        "set_name": set_name,
                        "sticker_name": sticker_name,
                        "recipient": recipient,
                        "stars": stars,
                        "gold": gold,
                        "row_index": row_index,
                    }
                )

    return sorted(
        trades,
        key=lambda trade: (
            trade["gold"],
            -trade["stars"],
            trade["sender"],
            trade["recipient"],
            trade["row_index"],
        ),
    )


def markdown_table(trades):
    lines = [
        "| Sender | Set_Name | Sticker_Name | Recipient |",
        "| --- | --- | --- | --- |",
    ]

    for trade in trades:
        lines.append(
            "| {sender} | {set_name} | {sticker_name} | {recipient} |".format(
                sender=escape_table_cell(trade["sender"]),
                set_name=escape_table_cell(trade["set_name"]),
                sticker_name=escape_table_cell(trade["sticker_name"]),
                recipient=escape_table_cell(trade["recipient"]),
            )
        )

    return "\n".join(lines)


def escape_table_cell(value):
    return str(value).replace("|", "\\|")


def format_trade_table(trades):
    if not trades:
        return NO_TRADES_MESSAGE

    regular_trades = [trade for trade in trades if not trade["gold"]]
    gold_trades = [trade for trade in trades if trade["gold"]]
    sections = []

    if regular_trades:
        sections.append(markdown_table(regular_trades))

    if gold_trades:
        sections.append("Gold stickers (event-only trades):\n" + markdown_table(gold_trades))

    return "\n\n".join(sections)


def main():
    rows = load_database()
    trades = find_trade_rows(rows)
    print(format_trade_table(trades))


if __name__ == "__main__":
    main()
