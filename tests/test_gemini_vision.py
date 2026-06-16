import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

import pandas as pd

import gemini_vision



class GeminiVisionTestHelpers(unittest.TestCase):
    def setUp(self):
        import os
        self.orig_env = dict(os.environ)
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = "nonexistent_file_for_tests.json"

    def tearDown(self):
        import os
        os.environ.clear()
        os.environ.update(self.orig_env)

    def test_safe_parse_json_accepts_code_fences(self):

        parsed = gemini_vision.safe_parse_json(
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

        updated, missing = gemini_vision.update_database(df, "Hana", extracted)

        self.assertEqual(updated, 1)
        self.assertEqual(missing, ["Lisa"])
        self.assertEqual(int(df.loc[df["Sticker_Name"] == "Marge", "Hana"].iloc[0]), 2)
        self.assertEqual(int(df.loc[df["Sticker_Name"] == "Bart", "Hana"].iloc[0]), 0)

    def test_validate_no_zero_regressions_rejects_owned_to_zero(self):
        previous = pd.DataFrame([{"Sticker_Name": "Marge", "Hana": 1}])
        updated = pd.DataFrame([{"Sticker_Name": "Marge", "Hana": 0}])

        with self.assertRaises(ValueError) as context:
            gemini_vision.validate_no_zero_regressions(previous, updated, ["Hana"])

        self.assertIn("owned stickers cannot drop to 0", str(context.exception))
        self.assertIn("Hana / Marge: 1 -> 0", str(context.exception))

    def test_find_zero_regressions_allows_trade_down_to_one(self):
        previous = pd.DataFrame([{"Sticker_Name": "Marge", "Hana": 3}])
        updated = pd.DataFrame([{"Sticker_Name": "Marge", "Hana": 1}])

        regressions = gemini_vision.find_zero_regressions(previous, updated, ["Hana"])

        self.assertEqual(regressions, [])

    def test_find_zero_regressions_allows_zero_to_zero(self):
        previous = pd.DataFrame([{"Sticker_Name": "Marge", "Hana": 0}])
        updated = pd.DataFrame([{"Sticker_Name": "Marge", "Hana": 0}])

        regressions = gemini_vision.find_zero_regressions(previous, updated, ["Hana"])

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
            gemini_vision.validate_no_zero_regressions(previous, updated, ["Hana", "Jon"])

        message = str(context.exception)
        self.assertIn("Hana / Marge: 1 -> 0", message)
        self.assertIn("Jon / Bart: 1 -> 0", message)
        self.assertNotIn("Hana / Bart: 2 -> 1", message)

    def test_file_hash_changes_when_file_changes(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "sample.txt"
            path.write_text("first", encoding="utf-8")
            first_hash = gemini_vision.file_hash(path)

            path.write_text("second", encoding="utf-8")
            second_hash = gemini_vision.file_hash(path)

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
        chunks = list(gemini_vision.chunked(list(range(32)), 15))

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

            old_screenshots_dir = gemini_vision.SCREENSHOTS_DIR
            old_users = gemini_vision.USERS

            try:
                gemini_vision.SCREENSHOTS_DIR = screenshot_dir
                gemini_vision.USERS = ["Jon"]
                processed = {
                    f"Jon/{first.name}": {
                        "sha256": gemini_vision.file_hash(first),
                    }
                }

                pending = gemini_vision.pending_images(processed)
            finally:
                gemini_vision.SCREENSHOTS_DIR = old_screenshots_dir
                gemini_vision.USERS = old_users

        self.assertEqual(len(pending), 1)
        self.assertEqual(pending[0]["key"], "Jon/second.jpeg")

    def test_extract_drive_file_id_various_formats(self):
        # open?id=... format
        self.assertEqual(
            gemini_vision.extract_drive_file_id("https://drive.google.com/open?id=1spTE2jH5GB8qtdtQbJ80fuhEDP0oa2-y"),
            "1spTE2jH5GB8qtdtQbJ80fuhEDP0oa2-y"
        )
        # file/d/.../view format
        self.assertEqual(
            gemini_vision.extract_drive_file_id("https://drive.google.com/file/d/1spTE2jH5GB8qtdtQbJ80fuhEDP0oa2-y/view?usp=drivesdk"),
            "1spTE2jH5GB8qtdtQbJ80fuhEDP0oa2-y"
        )
        # Invalid url
        self.assertIsNone(gemini_vision.extract_drive_file_id("https://google.com"))
        self.assertIsNone(gemini_vision.extract_drive_file_id(""))

    @patch("gemini_vision.build")
    @patch("google.oauth2.service_account.Credentials.from_service_account_file")
    @patch("os.path.exists")
    def test_pending_images_from_google_success(self, mock_exists, mock_creds, mock_build):
        # Force exists to return True for any check in this test
        mock_exists.return_value = True

        # Mock Sheets API client and responses

        mock_service = MagicMock()
        mock_build.return_value = mock_service

        # Values returned from sheets.values().get().execute()
        mock_values = [
            ["Timestamp", "Email Address", "Select screenshots to upload (First 10)"],
            ["6/16/2026 15:03:05", "salehn1@gmail.com", "https://drive.google.com/open?id=1spTE2jH5GB8qtdtQbJ80fuhEDP0oa2-y, https://drive.google.com/open?id=1HN6S1D4oKFnFXmh3Yeg-2ETDSSAnGNVg"],
            ["6/16/2026 15:04:00", "jonlucc@gmail.com", "https://drive.google.com/open?id=1Zxvwj4v9LZUU-VJbtMXQ3mh3o1hdSsyT"],
            ["6/16/2026 15:05:00", "unknown@gmail.com", "https://drive.google.com/open?id=invalid"]
        ]

        mock_service.spreadsheets().values().get().execute.return_value = {"values": mock_values}

        # If the first file is already processed
        processed = {
            "1spTE2jH5GB8qtdtQbJ80fuhEDP0oa2-y": {"sha256": "somehash"}
        }

        # Call pending_images - because mock_exists says credentials exist, this will invoke pending_images_from_google
        pending = gemini_vision.pending_images(processed)

        # We expect:
        # 1. 1spTE2jH5GB8qtdtQbJ80fuhEDP0oa2-y is skipped because it is in processed.
        # 2. 1HN6S1D4oKFnFXmh3Yeg-2ETDSSAnGNVg from salehn1@gmail.com (Nabil) is returned.
        # 3. 1Zxvwj4v9LZUU-VJbtMXQ3mh3o1hdSsyT from jonlucc@gmail.com (Jon) is returned.
        # 4. unknown@gmail.com is skipped since it is not in EMAIL_TO_USER.

        self.assertEqual(len(pending), 2)
        self.assertEqual(pending[0]["user"], "Nabil")
        self.assertEqual(pending[0]["file_id"], "1HN6S1D4oKFnFXmh3Yeg-2ETDSSAnGNVg")
        self.assertEqual(pending[0]["timestamp"], "6/16/2026 15:03:05")

        self.assertEqual(pending[1]["user"], "Jon")
        self.assertEqual(pending[1]["file_id"], "1Zxvwj4v9LZUU-VJbtMXQ3mh3o1hdSsyT")


if __name__ == "__main__":
    unittest.main()

