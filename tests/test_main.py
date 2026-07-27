"""
Unit tests for main.py (Main Orchestrator & Scheduling implementation)
"""

import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from logging.handlers import RotatingFileHandler
from unittest.mock import MagicMock, patch

from dotenv import load_dotenv

import main

# Ensure environment variables are loaded for testing
load_dotenv()


class TestMainOrchestrator(unittest.TestCase):
    def setUp(self):
        load_dotenv()
        # Reset shutdown flag before each test
        main.SHUTDOWN_REQUESTED = False

    def test_load_dotenv_at_top(self):
        """Verify load_dotenv is imported and executed."""
        self.assertTrue(callable(load_dotenv))

    def test_setup_logging_creates_directory_and_handlers(self):
        """Verify setup_logging creates target directory and configures stdout StreamHandler + RotatingFileHandler."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            log_path = os.path.join(tmp_dir, "nested_logs", "test_bot.log")

            # Close and remove handlers from existing y2k_bot logger for clean test state
            logger = main.logging.getLogger("y2k_bot")
            for h in list(logger.handlers):
                h.close()
            logger.handlers.clear()

            configured_logger = main.setup_logging(log_file=log_path)

            # 1. Directory creation check
            self.assertTrue(os.path.exists(os.path.join(tmp_dir, "nested_logs")))

            # 2. Handlers setup check
            self.assertGreaterEqual(len(configured_logger.handlers), 2)
            has_stream_handler = any(
                isinstance(h, main.logging.StreamHandler) and not isinstance(h, RotatingFileHandler)
                for h in configured_logger.handlers
            )
            has_rotating_handler = any(
                isinstance(h, RotatingFileHandler) for h in configured_logger.handlers
            )
            self.assertTrue(has_stream_handler, "StreamHandler (stdout) must be configured")
            self.assertTrue(has_rotating_handler, "RotatingFileHandler must be configured")

    def test_is_peak_hour_inside_window(self):
        """Verify is_peak_hour returns True when given a datetime inside peak hours (8-23)."""
        with patch.dict(os.environ, {"PEAK_START_HOUR": "8", "PEAK_END_HOUR": "23"}):
            peak_time = datetime(2026, 7, 26, 14, 30, 0)
            self.assertTrue(main.is_peak_hour(peak_time))

            start_time = datetime(2026, 7, 26, 8, 0, 0)
            self.assertTrue(main.is_peak_hour(start_time))

            end_time = datetime(2026, 7, 26, 23, 0, 0)
            self.assertTrue(main.is_peak_hour(end_time))

    def test_is_peak_hour_outside_window(self):
        """Verify is_peak_hour returns False when given a datetime outside peak hours (8-23)."""
        with patch.dict(os.environ, {"PEAK_START_HOUR": "8", "PEAK_END_HOUR": "23"}):
            early_morning = datetime(2026, 7, 26, 5, 0, 0)
            self.assertFalse(main.is_peak_hour(early_morning))

            just_before_start = datetime(2026, 7, 26, 7, 59, 0)
            self.assertFalse(main.is_peak_hour(just_before_start))

    def test_is_peak_hour_default_datetime(self):
        """Verify is_peak_hour returns a boolean when no datetime argument is passed."""
        result = main.is_peak_hour()
        self.assertIsInstance(result, bool)

    def test_calculate_seconds_until_peak(self):
        """Verify calculate_seconds_until_peak correctly computes sleep duration until PEAK_START_HOUR."""
        tz = timezone(timedelta(hours=-5))
        now_dt = datetime(2026, 7, 26, 5, 0, 0, tzinfo=tz)  # 5 AM
        secs = main.calculate_seconds_until_peak(now_dt, peak_start=8)
        self.assertEqual(secs, 3 * 3600)  # 3 hours = 10800 seconds

        # When current time is past peak start (e.g. 10 PM), target should be 8 AM next day
        late_dt = datetime(2026, 7, 26, 22, 0, 0, tzinfo=tz)  # 10 PM
        secs_late = main.calculate_seconds_until_peak(late_dt, peak_start=8)
        self.assertEqual(secs_late, 10 * 3600)  # 10 hours = 36000 seconds

    @patch("main.save_listings")
    @patch("main.price_camera_listings")
    @patch("main.identify_camera_listings")
    @patch("main.check_existing_urls")
    @patch("main.scrape_ebay_listings")
    def test_run_pipeline_end_to_end_success(
        self,
        mock_scrape,
        mock_check_urls,
        mock_identify,
        mock_price,
        mock_save,
    ):
        """Verify end-to-end run_pipeline execution across all 5 stages with proper deduplication and dataset merging."""
        # 1. Scraper output
        raw_listings = [
            {"url": "http://ebay.com/itm/1", "title": "Canon Ixus 70", "price": 45.0},
            {"url": "http://ebay.com/itm/2", "title": "Sony Cyber-shot", "price": 30.0},
            {"url": "http://ebay.com/itm/3", "title": "Nikon Coolpix", "price": 25.0},
        ]
        mock_scrape.return_value = raw_listings

        # 2. Database early deduplication output (itm/1 already exists)
        mock_check_urls.return_value = {"http://ebay.com/itm/1"}

        # 3. Vision AI output (itm/2 is minor/no damage, itm/3 is major damage)
        filtered_for_pricer = [
            {"url": "http://ebay.com/itm/2", "title": "Sony Cyber-shot", "price": 30.0, "identified_model": "Sony DSC-T70", "damage_severity": "none"}
        ]
        all_enriched = [
            {"url": "http://ebay.com/itm/2", "title": "Sony Cyber-shot", "price": 30.0, "identified_model": "Sony DSC-T70", "damage_severity": "none"},
            {"url": "http://ebay.com/itm/3", "title": "Nikon Coolpix", "price": 25.0, "identified_model": "Nikon S210", "damage_severity": "major"},
        ]
        mock_identify.return_value = (filtered_for_pricer, all_enriched)

        # 4. Market Pricer output
        priced_listings = [
            {
                "url": "http://ebay.com/itm/2",
                "title": "Sony Cyber-shot",
                "price": 30.0,
                "identified_model": "Sony DSC-T70",
                "damage_severity": "none",
                "estimated_market_value": 120.0,
                "profit_margin": 75.0,
                "is_profitable_deal": True,
            }
        ]
        mock_price.return_value = priced_listings

        # 5. Database Save output
        mock_save.return_value = {"inserted": 2, "skipped": 0, "failed": 0}

        # Execute pipeline
        summary = main.run_pipeline()

        # Verification assertions
        mock_scrape.assert_called_once()
        mock_check_urls.assert_called_once_with(["http://ebay.com/itm/1", "http://ebay.com/itm/2", "http://ebay.com/itm/3"])
        mock_identify.assert_called_once_with([raw_listings[1], raw_listings[2]])
        mock_price.assert_called_once_with(filtered_for_pricer)

        # Verify merged listings passed to save_listings contain priced item + major damage item
        mock_save.assert_called_once()
        saved_arg = mock_save.call_args[0][0]
        self.assertEqual(len(saved_arg), 2)
        saved_urls = {item["url"] for item in saved_arg}
        self.assertEqual(saved_urls, {"http://ebay.com/itm/2", "http://ebay.com/itm/3"})

        # Summary dict assertion
        self.assertEqual(summary["status"], "success")
        self.assertEqual(summary["scraped"], 3)
        self.assertEqual(summary["new_items"], 2)
        self.assertEqual(summary["processed"], 2)
        self.assertEqual(summary["priced"], 1)
        self.assertEqual(summary["profitable"], 1)
        self.assertEqual(summary["inserted"], 2)

    @patch("main.scrape_ebay_listings")
    def test_run_pipeline_no_scraped_listings(self, mock_scrape):
        """Verify pipeline handles empty scraper results gracefully and exits early."""
        mock_scrape.return_value = []
        summary = main.run_pipeline()
        self.assertEqual(summary["status"], "success")
        self.assertEqual(summary["scraped"], 0)

    @patch("main.identify_camera_listings")
    @patch("main.check_existing_urls")
    @patch("main.scrape_ebay_listings")
    def test_run_pipeline_all_items_already_exist(self, mock_scrape, mock_check_urls, mock_identify):
        """Verify early deduplication prevents calling Vision AI when all items already exist in DB."""
        raw_listings = [{"url": "http://ebay.com/itm/1"}]
        mock_scrape.return_value = raw_listings
        mock_check_urls.return_value = {"http://ebay.com/itm/1"}

        summary = main.run_pipeline()
        self.assertEqual(summary["status"], "success")
        self.assertEqual(summary["new_items"], 0)
        mock_identify.assert_not_called()

    @patch("main.scrape_ebay_listings")
    def test_run_pipeline_scraper_error_handling(self, mock_scrape):
        """Verify run_pipeline catches scraper exceptions without crashing."""
        mock_scrape.side_effect = Exception("Scraper network error")
        summary = main.run_pipeline()
        self.assertEqual(summary["status"], "error")
        self.assertIn("[SCRAPER]", summary["error"])

    @patch("main.save_listings")
    @patch("main.price_camera_listings")
    @patch("main.identify_camera_listings")
    @patch("main.check_existing_urls")
    @patch("main.scrape_ebay_listings")
    def test_run_pipeline_pricer_error_resilience(
        self,
        mock_scrape,
        mock_check_urls,
        mock_identify,
        mock_price,
        mock_save,
    ):
        """Verify pricing failure logs error but allows persisting enriched listings to DB."""
        mock_scrape.return_value = [{"url": "http://ebay.com/itm/1"}]
        mock_check_urls.return_value = set()
        item = {"url": "http://ebay.com/itm/1", "identified_model": "Cam"}
        mock_identify.return_value = ([item], [item])
        mock_price.side_effect = Exception("Pricer timeout")
        mock_save.return_value = {"inserted": 1, "skipped": 0, "failed": 0}

        summary = main.run_pipeline()
        self.assertEqual(summary["status"], "success")
        self.assertEqual(summary["inserted"], 1)

    @patch("main.run_pipeline")
    def test_run_scheduler_once_mode(self, mock_pipeline):
        """Verify run_scheduler(once=True) executes pipeline once and returns summary."""
        mock_pipeline.return_value = {"status": "success", "scraped": 10}
        result = main.run_scheduler(once=True)
        mock_pipeline.assert_called_once()
        self.assertEqual(result, {"status": "success", "scraped": 10})

    @patch("main.run_scheduler")
    def test_main_cli_once_argument(self, mock_scheduler):
        """Verify CLI argument --once triggers run_scheduler with once=True."""
        test_args = ["main.py", "--once"]
        with patch.object(sys, "argv", test_args):
            main.main()
            mock_scheduler.assert_called_once_with(once=True)


if __name__ == "__main__":
    unittest.main()
