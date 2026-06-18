import os
import unittest
from unittest.mock import patch
import tempfile
import pandas as pd
from pathlib import Path
import addNewSet

# Keep a reference to the original read_csv to avoid recursion in mocks
original_read_csv = pd.read_csv


class TestAddNewSet(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "temp_sticker_db.csv"
        # Set environment variable so addNewSet uses our temp db
        os.environ["DATABASE_PATH"] = str(self.db_path)

        # Write initial stickers to local database
        self.initial_data = pd.DataFrame([
            {
                "Set_Name": "The Simpsons",
                "Set_Number": 1,
                "Sticker_Name": "Marge",
                "Album_Position": 1,
                "Star_Number": 1,
                "Gold_Status": False,
                "MoGo_ID": 11,
                "Hana": 3,
                "Jon": 2,
                "Nabil": 1
            },
            {
                "Set_Name": "The Simpsons",
                "Set_Number": 1,
                "Sticker_Name": "Bart",
                "Album_Position": 2,
                "Star_Number": 1,
                "Gold_Status": False,
                "MoGo_ID": 12,
                "Hana": 0,
                "Jon": 4,
                "Nabil": 0
            }
        ])
        self.initial_data.to_csv(self.db_path, index=False)

    def tearDown(self):
        if "DATABASE_PATH" in os.environ:
            del os.environ["DATABASE_PATH"]
        self.temp_dir.cleanup()

    @patch("pandas.read_csv")
    @patch("subprocess.run")
    def test_add_new_stickers(self, mock_run, mock_read_csv):
        # Mock Google Sheet DataFrame (first 7 columns)
        sheet_df = pd.DataFrame([
            {"Set_Name": "The Simpsons", "Set_Number": 1, "Sticker_Name": "Marge", "Album_Position": 1, "Star_Number": 1, "Gold_Status": False, "MoGo_ID": 11},
            {"Set_Name": "The Simpsons", "Set_Number": 1, "Sticker_Name": "Bart", "Album_Position": 2, "Star_Number": 1, "Gold_Status": False, "MoGo_ID": 12},
            {"Set_Name": "Monopoly's Training Day", "Set_Number": 2, "Sticker_Name": "Weee!", "Album_Position": 1, "Star_Number": 1, "Gold_Status": False, "MoGo_ID": 21},
            {"Set_Name": "Monopoly's Training Day", "Set_Number": 2, "Sticker_Name": "Payday", "Album_Position": 2, "Star_Number": 1, "Gold_Status": True, "MoGo_ID": 22}
        ])

        def read_csv_side_effect(filepath_or_buffer, *args, **kwargs):
            if isinstance(filepath_or_buffer, str) and filepath_or_buffer.startswith("https://"):
                return sheet_df
            else:
                return original_read_csv(filepath_or_buffer, *args, **kwargs)

        mock_read_csv.side_effect = read_csv_side_effect

        # Run main
        addNewSet.main()

        # Read back database and verify using original read_csv to bypass mock if needed
        df_result = original_read_csv(self.db_path)

        # Verify length (initial 2 stickers + 2 new stickers)
        self.assertEqual(len(df_result), 4)

        # Verify old stickers counts are preserved
        marge = df_result[df_result["MoGo_ID"] == 11].iloc[0]
        self.assertEqual(marge["Hana"], 3)
        self.assertEqual(marge["Jon"], 2)
        self.assertEqual(marge["Nabil"], 1)

        bart = df_result[df_result["MoGo_ID"] == 12].iloc[0]
        self.assertEqual(bart["Hana"], 0)
        self.assertEqual(bart["Jon"], 4)
        self.assertEqual(bart["Nabil"], 0)

        # Verify new stickers are added with 0 counts
        weee = df_result[df_result["MoGo_ID"] == 21].iloc[0]
        self.assertEqual(weee["Set_Name"], "Monopoly's Training Day")
        self.assertEqual(weee["Hana"], 0)
        self.assertEqual(weee["Jon"], 0)
        self.assertEqual(weee["Nabil"], 0)

        payday = df_result[df_result["MoGo_ID"] == 22].iloc[0]
        self.assertEqual(payday["Set_Name"], "Monopoly's Training Day")
        self.assertEqual(payday["Gold_Status"], True)
        self.assertEqual(payday["Hana"], 0)
        self.assertEqual(payday["Jon"], 0)
        self.assertEqual(payday["Nabil"], 0)

    @patch("pandas.read_csv")
    @patch("subprocess.run")
    def test_no_new_stickers(self, mock_run, mock_read_csv):
        sheet_df = pd.DataFrame([
            {"Set_Name": "The Simpsons", "Set_Number": 1, "Sticker_Name": "Marge", "Album_Position": 1, "Star_Number": 1, "Gold_Status": False, "MoGo_ID": 11},
            {"Set_Name": "The Simpsons", "Set_Number": 1, "Sticker_Name": "Bart", "Album_Position": 2, "Star_Number": 1, "Gold_Status": False, "MoGo_ID": 12}
        ])

        def read_csv_side_effect(filepath_or_buffer, *args, **kwargs):
            if isinstance(filepath_or_buffer, str) and filepath_or_buffer.startswith("https://"):
                return sheet_df
            else:
                return original_read_csv(filepath_or_buffer, *args, **kwargs)

        mock_read_csv.side_effect = read_csv_side_effect

        addNewSet.main()

        df_result = original_read_csv(self.db_path)
        self.assertEqual(len(df_result), 2)
        # Verify no changes or resets
        marge = df_result[df_result["MoGo_ID"] == 11].iloc[0]
        self.assertEqual(marge["Hana"], 3)


if __name__ == "__main__":
    unittest.main()
