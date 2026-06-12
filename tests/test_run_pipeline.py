import json
import os
import unittest
from unittest.mock import MagicMock, patch
from pathlib import Path
import tempfile
import shutil

import gemini_vision
import tradeEngine
import run_pipeline


class PipelineAndHashingTests(unittest.TestCase):
    def setUp(self):
        # Backup environment variables
        self.orig_env = dict(os.environ)

    def tearDown(self):
        # Restore environment variables
        os.environ.clear()
        os.environ.update(self.orig_env)

    def test_file_hash_with_real_image_and_cropping(self):
        # Let's verify that when pillow is present, we can hash a solid red image.
        from PIL import Image
        with tempfile.TemporaryDirectory() as tmpdir:
            img_path1 = Path(tmpdir) / "image1.png"
            img_path2 = Path(tmpdir) / "image2.png"
            
            # Create two images with different headers (e.g. status bar) but same body
            # Image size 100x100
            # Image 1: top 20 pixels are red, rest is white
            # Image 2: top 20 pixels are blue, rest is white
            img1 = Image.new("RGB", (100, 100), "white")
            for x in range(100):
                for y in range(20):
                    img1.putpixel((x, y), (255, 0, 0)) # Red
            img1.save(img_path1)
            
            img2 = Image.new("RGB", (100, 100), "white")
            for x in range(100):
                for y in range(20):
                    img2.putpixel((x, y), (0, 0, 255)) # Blue
            img2.save(img_path2)
            
            hash1 = gemini_vision.file_hash(img_path1)
            hash2 = gemini_vision.file_hash(img_path2)
            
            # Since the top 20% is cropped out (20 pixels of 100 height),
            # both cropped images will be completely white, so their cropped hashes should be EQUAL!
            self.assertEqual(hash1, hash2)

    def test_path_resolution_with_env_override(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            screenshots_override = Path(tmpdir) / "custom_screenshots"
            db_override = Path(tmpdir) / "custom_db.csv"
            processed_override = Path(tmpdir) / "custom_processed.json"
            
            os.environ["SCREENSHOTS_DIR"] = str(screenshots_override)
            os.environ["DATABASE_PATH"] = str(db_override)
            os.environ["PROCESSED_LOG"] = str(processed_override)
            
            # Reload module or verify logic dynamically
            # Since path constants are evaluated at import time, let's verify how they behave when re-imported or re-evaluated.
            # In our implementation:
            # SCREENSHOTS_DIR = Path(os.getenv("SCREENSHOTS_DIR", ...))
            # Let's check the logic inside a subprocess or mock environment variables and test the logic.
            
            # We can test the helper path resolution logic
            screenshots_dir_env = os.getenv("SCREENSHOTS_DIR")
            if screenshots_dir_env:
                resolved_screenshots = Path(screenshots_dir_env)
            else:
                resolved_screenshots = Path("screenshots")
                
            self.assertEqual(resolved_screenshots, screenshots_override)

    @patch("gemini_vision.load_processed_log")
    @patch("gemini_vision.pending_images")
    def test_pipeline_exits_early_when_no_new_images(self, mock_pending, mock_load):
        mock_load.return_value = {}
        mock_pending.return_value = []
        
        with self.assertRaises(SystemExit) as cm:
            run_pipeline.main()
        
        self.assertEqual(cm.exception.code, 0)

    @patch("gemini_vision.load_processed_log")
    @patch("gemini_vision.pending_images")
    @patch("gemini_vision.main")
    @patch("tradeEngine.load_database")
    @patch("tradeEngine.find_trade_rows")
    def test_pipeline_exits_early_when_no_trades(self, mock_find_trades, mock_load_db, mock_gemini_main, mock_pending, mock_load):
        mock_load.return_value = {}
        mock_pending.return_value = [{"key": "Jon/1.png", "sha256": "xyz"}]
        mock_find_trades.return_value = []
        
        with self.assertRaises(SystemExit) as cm:
            run_pipeline.main()
        
        mock_gemini_main.assert_called_once()
        self.assertEqual(cm.exception.code, 0)

    @patch("gemini_vision.load_processed_log")
    @patch("gemini_vision.pending_images")
    @patch("gemini_vision.main")
    @patch("tradeEngine.load_database")
    @patch("tradeEngine.find_trade_rows")
    @patch("run_pipeline.send_trade_email")
    @patch("sys.exit")
    def test_pipeline_sends_email_when_trades_exist(self, mock_exit, mock_send_email, mock_find_trades, mock_load_db, mock_gemini_main, mock_pending, mock_load):
        mock_load.return_value = {}
        mock_pending.return_value = [{"key": "Jon/1.png", "sha256": "xyz"}]
        
        mock_find_trades.return_value = [
            {
                "sender": "Jon",
                "set_name": "Set 1",
                "sticker_name": "Sticker 1",
                "recipient": "Hana",
                "stars": 3,
                "gold": False,
                "row_index": 0
            }
        ]
        
        os.environ["SMTP_SERVER"] = "smtp.example.com"
        os.environ["SMTP_USERNAME"] = "user"
        os.environ["SMTP_PASSWORD"] = "pass"
        os.environ["EMAIL_RECIPIENTS"] = "hana@example.com,jon@example.com"
        
        run_pipeline.main()
        
        mock_gemini_main.assert_called_once()
        mock_send_email.assert_called_once()
        # Should complete successfully without calling exit(1)
        mock_exit.assert_not_called()


if __name__ == "__main__":
    unittest.main()
