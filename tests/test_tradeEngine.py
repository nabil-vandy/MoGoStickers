import tempfile
import unittest
from pathlib import Path

import tradeEngine


class TradeEngineTests(unittest.TestCase):
    def test_sender_with_duplicate_can_share_with_missing_recipient(self):
        rows = [
            {
                "Set_Name": "Welcome to Springfield",
                "Sticker_Name": "My Bad",
                "Hana": "2",
                "Jon": "1",
                "Nabil": "0",
            }
        ]

        trades = tradeEngine.find_trade_rows(rows)

        self.assertEqual(len(trades), 1)
        self.assertEqual(trades[0]["sender"], "Hana")
        self.assertEqual(trades[0]["set_name"], "Welcome to Springfield")
        self.assertEqual(trades[0]["sticker_name"], "My Bad")
        self.assertEqual(trades[0]["recipient"], "Nabil")

    def test_sender_with_one_cannot_share(self):
        rows = [
            {
                "Set_Name": "The Simpsons",
                "Sticker_Name": "Marge",
                "Hana": "1",
                "Jon": "0",
                "Nabil": "0",
            }
        ]

        trades = tradeEngine.find_trade_rows(rows)

        self.assertEqual(trades, [])

    def test_recipient_with_sticker_is_not_listed_as_needing_it(self):
        rows = [
            {
                "Set_Name": "The Simpsons",
                "Sticker_Name": "Bart",
                "Hana": "2",
                "Jon": "1",
                "Nabil": "0",
            }
        ]

        trades = tradeEngine.find_trade_rows(rows)
        trade_pairs = {(trade["sender"], trade["recipient"]) for trade in trades}

        self.assertNotIn(("Hana", "Jon"), trade_pairs)
        self.assertIn(("Hana", "Nabil"), trade_pairs)

    def test_multiple_senders_and_recipients_are_included(self):
        rows = [
            {
                "Set_Name": "The Simpsons",
                "Sticker_Name": "Lisa",
                "Hana": "2",
                "Jon": "0",
                "Nabil": "0",
            },
            {
                "Set_Name": "Springfield",
                "Sticker_Name": "Donut",
                "Hana": "0",
                "Jon": "3",
                "Nabil": "2",
            },
        ]

        trades = tradeEngine.find_trade_rows(rows)
        trade_pairs = {
            (trade["sender"], trade["recipient"], trade["sticker_name"])
            for trade in trades
        }

        self.assertEqual(
            trade_pairs,
            {
                ("Hana", "Jon", "Lisa"),
                ("Hana", "Nabil", "Lisa"),
                ("Jon", "Hana", "Donut"),
                ("Nabil", "Hana", "Donut"),
            },
        )

    def test_stickers_are_sorted_by_star_number_descending(self):
        rows = [
            {
                "Set_Name": "Friends & Family",
                "Sticker_Name": "Reverend Lovejoy",
                "Star_Number": "1",
                "Hana": "0",
                "Jon": "2",
                "Nabil": "0",
            },
            {
                "Set_Name": "Friends & Family",
                "Sticker_Name": "The Hibberts",
                "Star_Number": "2",
                "Hana": "0",
                "Jon": "2",
                "Nabil": "0",
            },
        ]

        trades = tradeEngine.find_trade_rows(rows)
        jon_to_nabil = [
            trade["sticker_name"]
            for trade in trades
            if trade["sender"] == "Jon" and trade["recipient"] == "Nabil"
        ]

        self.assertEqual(jon_to_nabil, ["The Hibberts", "Reverend Lovejoy"])

    def test_gold_stickers_are_sorted_below_regular_stickers(self):
        rows = [
            {
                "Set_Name": "Event",
                "Sticker_Name": "Gold Prize",
                "Star_Number": "5",
                "Gold_Status": "True",
                "Hana": "2",
                "Jon": "0",
                "Nabil": "1",
            },
            {
                "Set_Name": "Regular",
                "Sticker_Name": "Small Prize",
                "Star_Number": "1",
                "Gold_Status": "False",
                "Hana": "2",
                "Jon": "0",
                "Nabil": "1",
            },
        ]

        trades = tradeEngine.find_trade_rows(rows)

        self.assertEqual(
            [trade["sticker_name"] for trade in trades],
            ["Small Prize", "Gold Prize"],
        )
        self.assertFalse(trades[0]["gold"])
        self.assertTrue(trades[1]["gold"])

    def test_missing_and_non_numeric_counts_are_zero(self):
        rows = [
            {
                "Set_Name": "The Simpsons",
                "Sticker_Name": "Homer",
                "Hana": "extra",
                "Jon": "2",
            }
        ]

        trades = tradeEngine.find_trade_rows(rows)
        trade_pairs = {(trade["sender"], trade["recipient"]) for trade in trades}

        self.assertEqual(trade_pairs, {("Jon", "Hana"), ("Jon", "Nabil")})

    def test_format_trade_table_prints_no_trades_message(self):
        self.assertEqual(
            tradeEngine.format_trade_table([]),
            tradeEngine.NO_TRADES_MESSAGE,
        )

    def test_format_trade_table_outputs_columns_and_gold_section(self):
        trades = [
            {
                "sender": "Hana",
                "set_name": "Regular",
                "sticker_name": "Small Prize",
                "recipient": "Jon",
                "stars": 1,
                "gold": False,
                "row_index": 1,
            },
            {
                "sender": "Hana",
                "set_name": "Event",
                "sticker_name": "Gold Prize",
                "recipient": "Jon",
                "stars": 5,
                "gold": True,
                "row_index": 0,
            },
        ]

        output = tradeEngine.format_trade_table(trades)

        self.assertIn("| Sender | Set_Name | Sticker_Name | Recipient |", output)
        self.assertIn("| Hana | Regular | Small Prize | Jon |", output)
        self.assertIn("Gold stickers (event-only trades):", output)
        self.assertLess(output.index("Small Prize"), output.index("Gold Prize"))

    def test_load_database_reads_csv_rows(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "stickers.csv"
            path.write_text(
                "Set_Name,Sticker_Name,Hana,Jon,Nabil\n"
                "The Simpsons,Marge,2,0,1\n",
                encoding="utf-8",
            )

            rows = tradeEngine.load_database(path)

        self.assertEqual(rows[0]["Sticker_Name"], "Marge")
        self.assertEqual(rows[0]["Hana"], "2")


if __name__ == "__main__":
    unittest.main()
