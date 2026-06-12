import json
import tempfile
import unittest
from pathlib import Path

import pandas as pd

import vision_test


class VisionTestHelpers(unittest.TestCase):
    def test_safe_parse_json_accepts_code_fences(self):
        parsed = vision_test.safe_parse_json(
            '```json\n{"set_name":"Test","stickers":[]}\n```'
        )

        self.assertEqual(parsed["set_name"], "Test")
        self.assertEqual(parsed["stickers"], [])

    def test_update_database_updates_user_counts_and_tracks_missing(self):
        df = pd.DataFrame(
            [
                {"Sticker_Name": "Marge", "Hana": 0},
                {"Sticker_Name": "Bart", "Hana": 0},
            ]
        )
        extracted = {
            "stickers": [
                {"name": "marge", "count": 2},
                {"name": "Lisa", "count": 1},
            ]
        }

        updated, missing = vision_test.update_database(df, "Hana", extracted)

        self.assertEqual(updated, 1)
        self.assertEqual(missing, ["Lisa"])
        self.assertEqual(int(df.loc[df["Sticker_Name"] == "Marge", "Hana"].iloc[0]), 2)
        self.assertEqual(int(df.loc[df["Sticker_Name"] == "Bart", "Hana"].iloc[0]), 0)

    def test_validate_no_zero_regressions_rejects_owned_to_zero(self):
        previous = pd.DataFrame([{"Sticker_Name": "Marge", "Hana": 1}])
        updated = pd.DataFrame([{"Sticker_Name": "Marge", "Hana": 0}])

        with self.assertRaises(ValueError) as context:
            vision_test.validate_no_zero_regressions(previous, updated, ["Hana"])

        self.assertIn("owned stickers cannot drop to 0", str(context.exception))
        self.assertIn("Hana / Marge: 1 -> 0", str(context.exception))

    def test_find_zero_regressions_allows_trade_down_to_one(self):
        previous = pd.DataFrame([{"Sticker_Name": "Marge", "Hana": 3}])
        updated = pd.DataFrame([{"Sticker_Name": "Marge", "Hana": 1}])

        regressions = vision_test.find_zero_regressions(previous, updated, ["Hana"])

        self.assertEqual(regressions, [])

    def test_find_zero_regressions_allows_zero_to_zero(self):
        previous = pd.DataFrame([{"Sticker_Name": "Marge", "Hana": 0}])
        updated = pd.DataFrame([{"Sticker_Name": "Marge", "Hana": 0}])

        regressions = vision_test.find_zero_regressions(previous, updated, ["Hana"])

        self.assertEqual(regressions, [])

    def test_validate_no_zero_regressions_reports_multiple_rows(self):
        previous = pd.DataFrame(
            [
                {"Sticker_Name": "Marge", "Hana": 1, "Jon": 0},
                {"Sticker_Name": "Bart", "Hana": 2, "Jon": 1},
            ]
        )
        updated = pd.DataFrame(
            [
                {"Sticker_Name": "Marge", "Hana": 0, "Jon": 0},
                {"Sticker_Name": "Bart", "Hana": 1, "Jon": 0},
            ]
        )

        with self.assertRaises(ValueError) as context:
            vision_test.validate_no_zero_regressions(previous, updated, ["Hana", "Jon"])

        message = str(context.exception)
        self.assertIn("Hana / Marge: 1 -> 0", message)
        self.assertIn("Jon / Bart: 1 -> 0", message)
        self.assertNotIn("Hana / Bart: 2 -> 1", message)

    def test_file_hash_changes_when_file_changes(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "sample.txt"
            path.write_text("first", encoding="utf-8")
            first_hash = vision_test.file_hash(path)

            path.write_text("second", encoding="utf-8")
            second_hash = vision_test.file_hash(path)

        self.assertNotEqual(first_hash, second_hash)

    def test_processed_log_shape_is_json_serializable(self):
        processed = {
            "Nabil/IMG_9260.PNG": {
                "sha256": "abc123",
                "model": "gemini-3.1-flash-lite",
                "set_name": "Welcome to Springfield",
                "set_number": "Bonus Set",
                "updated_rows": 4,
                "missing_stickers": [],
            }
        }

        self.assertIsInstance(json.dumps(processed), str)

    def test_chunked_splits_into_requested_sizes(self):
        chunks = list(vision_test.chunked(list(range(32)), 15))

        self.assertEqual([len(chunk) for chunk in chunks], [15, 15, 2])
        self.assertEqual(chunks[0][0], 0)
        self.assertEqual(chunks[-1][-1], 31)

    def test_pending_images_skips_already_processed_files(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            screenshot_dir = Path(tmpdir) / "screenshots"
            user_dir = screenshot_dir / "Jon"
            user_dir.mkdir(parents=True)

            first = user_dir / "first.png"
            second = user_dir / "second.jpeg"
            first.write_bytes(b"already done")
            second.write_bytes(b"new image")

            old_screenshots_dir = vision_test.SCREENSHOTS_DIR
            old_users = vision_test.USERS

            try:
                vision_test.SCREENSHOTS_DIR = screenshot_dir
                vision_test.USERS = ["Jon"]
                processed = {
                    f"Jon/{first.name}": {
                        "sha256": vision_test.file_hash(first),
                    }
                }

                pending = vision_test.pending_images(processed)
            finally:
                vision_test.SCREENSHOTS_DIR = old_screenshots_dir
                vision_test.USERS = old_users

        self.assertEqual(len(pending), 1)
        self.assertEqual(pending[0]["key"], "Jon/second.jpeg")


if __name__ == "__main__":
    unittest.main()
