"""
Unit tests for main.py (Main Orchestrator & Non-blocking Scheduler)
"""

import asyncio
import os
import sys
import tempfile
import unittest
from logging.handlers import RotatingFileHandler
from unittest.mock import MagicMock, patch

from dotenv import load_dotenv

import main
from modules.pricer import price_camera_listings
from modules.scraper import EXACT_SEARCH_QUERIES, GENERIC_SEARCH_QUERIES, scrape_ebay_listings

# Load environment variables for testing
load_dotenv()


class TestMainOrchestrator(unittest.TestCase):
    def setUp(self):
        load_dotenv()
        main.SHUTDOWN_REQUESTED = False

    def test_setup_logging_creates_directory_and_handlers(self):
        """Verify setup_logging auto-creates logs/ directory and configures stdout StreamHandler + RotatingFileHandler."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            log_path = os.path.join(tmp_dir, "custom_logs", "bot.log")

            logger = main.logging.getLogger("y2k_bot")
            for h in list(logger.handlers):
                h.close()
            logger.handlers.clear()

            configured_logger = main.setup_logging(log_file=log_path)

            # 1. Directory creation check
            self.assertTrue(os.path.exists(os.path.join(tmp_dir, "custom_logs")))

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

    @patch("modules.scraper.requests.get")
    @patch("modules.scraper.requests.post")
    def test_scraper_search_type_and_model_injection(self, mock_post, mock_get):
        """Verify scraper injects search_type and identified_model for exact listings."""
        mock_token_resp = MagicMock()
        mock_token_resp.status_code = 200
        mock_token_resp.json.return_value = {"access_token": "mock_token"}
        mock_post.return_value = mock_token_resp

        mock_browse_resp = MagicMock()
        mock_browse_resp.status_code = 200
        mock_browse_resp.json.return_value = {
            "itemSummaries": [
                {
                    "title": "Canon PowerShot SD1000",
                    "itemWebUrl": "https://www.ebay.com/itm/exact123",
                    "price": {"value": "50.00"},
                }
            ]
        }
        mock_get.return_value = mock_browse_resp

        with patch.dict(os.environ, {"EBAY_APP_ID": "test_app", "EBAY_CERT_ID": "test_cert"}):
            # Test exact track
            exact_results = scrape_ebay_listings(queries=["Canon PowerShot SD1000"], search_type="exact")
            self.assertEqual(len(exact_results), 1)
            self.assertEqual(exact_results[0]["search_type"], "exact")
            self.assertEqual(exact_results[0]["identified_model"], "Canon PowerShot SD1000")

            # Test generic track
            generic_results = scrape_ebay_listings(queries=["Old silver camera"], search_type="generic")
            self.assertEqual(len(generic_results), 1)
            self.assertEqual(generic_results[0]["search_type"], "generic")
            self.assertNotIn("identified_model", generic_results[0])

    @patch("modules.pricer.get_estimated_market_value")
    def test_pricer_dynamic_margin_thresholds(self, mock_market_val):
        """Verify dynamic profit margin thresholds (25% exact vs 40% generic)."""
        # Asking price $70, market value $100 -> Profit margin = (100 - 70)/100 = 30%
        mock_market_val.return_value = 100.0

        exact_item = {
            "title": "Canon SD1000",
            "asking_price": 70.0,
            "identified_model": "Canon PowerShot SD1000",
            "search_type": "exact",
        }
        generic_item = {
            "title": "Old camera",
            "asking_price": 70.0,
            "identified_model": "Canon PowerShot SD1000",
            "search_type": "generic",
        }

        with patch.dict(os.environ, {"MIN_PROFIT_MARGIN": "40.0", "EXACT_MATCH_MARGIN": "25.0"}):
            priced_exact = price_camera_listings([exact_item])
            priced_generic = price_camera_listings([generic_item])

            self.assertEqual(priced_exact[0]["profit_margin"], 30.0)
            self.assertTrue(priced_exact[0]["is_profitable_deal"], "30% margin should be profitable for exact (threshold 25%)")

            self.assertEqual(priced_generic[0]["profit_margin"], 30.0)
            self.assertFalse(priced_generic[0]["is_profitable_deal"], "30% margin should NOT be profitable for generic (threshold 40%)")

    @patch("main.save_listings")
    @patch("main.price_camera_listings")
    @patch("main.identify_camera_listings")
    @patch("main.check_existing_urls")
    @patch("main.scrape_ebay_listings")
    def test_run_generic_pipeline_executes_vision_ai(
        self, mock_scrape, mock_check_urls, mock_identify, mock_price, mock_save
    ):
        """Verify generic pipeline executes Vision AI stage and filters major damage."""
        item1 = {"url": "http://ebay.com/1", "title": "Silver camera", "search_type": "generic"}
        item2 = {"url": "http://ebay.com/2", "title": "Untested camera", "search_type": "generic"}
        mock_scrape.return_value = [item1, item2]
        mock_check_urls.return_value = set()

        enriched1 = dict(item1, identified_model="Canon SD1000", damage_severity="none")
        enriched2 = dict(item2, identified_model="Unknown", damage_severity="major")
        mock_identify.return_value = ([enriched1], [enriched1, enriched2])

        priced1 = dict(enriched1, estimated_market_value=85.0, profit_margin=50.0, is_profitable_deal=True)
        mock_price.return_value = [priced1]
        mock_save.return_value = {"inserted": 2, "skipped": 0, "failed": 0}

        summary = main.run_generic_pipeline()

        mock_scrape.assert_called_once_with(queries=GENERIC_SEARCH_QUERIES, search_type="generic")
        mock_identify.assert_called_once_with([item1, item2])
        mock_price.assert_called_once_with([enriched1])
        mock_save.assert_called_once()
        self.assertEqual(summary["status"], "success")
        self.assertEqual(summary["processed"], 2)
        self.assertEqual(summary["priced"], 1)

    @patch("main.save_listings")
    @patch("main.price_camera_listings")
    @patch("main.identify_camera_listings")
    @patch("main.check_existing_urls")
    @patch("main.scrape_ebay_listings")
    def test_run_exact_pipeline_skips_vision_ai(
        self, mock_scrape, mock_check_urls, mock_identify, mock_price, mock_save
    ):
        """Verify exact pipeline SKIPS vision_ai.py entirely and routes directly to pricer."""
        exact_item = {
            "url": "http://ebay.com/exact1",
            "title": "Canon PowerShot SD1000",
            "search_type": "exact",
            "identified_model": "Canon PowerShot SD1000",
        }
        mock_scrape.return_value = [exact_item]
        mock_check_urls.return_value = set()

        priced_item = dict(exact_item, estimated_market_value=85.0, profit_margin=30.0, is_profitable_deal=True)
        mock_price.return_value = [priced_item]
        mock_save.return_value = {"inserted": 1, "skipped": 0, "failed": 0}

        summary = main.run_exact_pipeline()

        mock_scrape.assert_called_once_with(queries=EXACT_SEARCH_QUERIES, search_type="exact")
        mock_identify.assert_not_called()  # MUST SKIP VISION AI
        mock_price.assert_called_once_with([exact_item])
        mock_save.assert_called_once_with([priced_item])
        self.assertEqual(summary["status"], "success")

    @patch("main.run_generic_pipeline")
    @patch("main.run_exact_pipeline")
    def test_run_scheduler_once_mode(self, mock_exact, mock_generic):
        """Verify run_scheduler(once=True) executes exact and generic pipelines once sequentially."""
        mock_exact.return_value = {"status": "success", "scraped": 5}
        mock_generic.return_value = {"status": "success", "scraped": 10}

        result = main.run_scheduler(once=True)

        mock_exact.assert_called_once()
        mock_generic.assert_called_once()
        self.assertEqual(result["scraped"], 15)

    @patch("main.run_generic_pipeline")
    @patch("main.run_exact_pipeline")
    def test_non_blocking_scheduler_execution(self, mock_exact, mock_generic):
        """Verify non-blocking dual scheduler runs loops concurrently."""
        mock_exact.return_value = {"status": "success"}
        mock_generic.return_value = {"status": "success"}

        async def test_scheduler():
            # Set shutdown after short delay
            main.SHUTDOWN_REQUESTED = False
            task = asyncio.create_task(main.run_scheduler_async(once=False, exact_interval=1, generic_interval=1))
            await asyncio.sleep(0.1)
            main.SHUTDOWN_REQUESTED = True
            await task

        asyncio.run(test_scheduler())
        self.assertTrue(mock_exact.called)
        self.assertTrue(mock_generic.called)

    @patch("main.run_scheduler")
    @patch("main.validate_environment")
    def test_main_cli_once_flag(self, mock_validate, mock_scheduler):
        """Verify CLI argument --once triggers validate_environment and run_scheduler with once=True."""
        test_args = ["main.py", "--once"]
        with patch.object(sys, "argv", test_args):
            main.main()
            mock_validate.assert_called_once()
            mock_scheduler.assert_called_once_with(once=True)

    @patch("main.load_dotenv")
    def test_environment_validation_missing_env(self, mock_load_dotenv):
        """Verify validate_environment exits with code 1 when required env vars are missing."""
        with patch.dict(os.environ, {}, clear=True):
            with patch("sys.stderr.write") as mock_stderr:
                with self.assertRaises(SystemExit) as cm:
                    main.validate_environment()
                self.assertEqual(cm.exception.code, 1)
                self.assertTrue(mock_stderr.called)

    @patch("main.run_exact_pipeline")
    @patch("main.run_generic_pipeline")
    def test_fastapi_scan_endpoints(self, mock_generic, mock_exact):
        """Verify FastAPI /api/scan/fast and /api/scan/slow trigger respective pipelines."""
        from fastapi.testclient import TestClient
        mock_exact.return_value = {"status": "success", "search_type": "exact"}
        mock_generic.return_value = {"status": "success", "search_type": "generic"}

        client = TestClient(main.app)
        
        resp_fast = client.get("/api/scan/fast")
        self.assertEqual(resp_fast.status_code, 200)
        self.assertEqual(resp_fast.json()["status"], "success")
        mock_exact.assert_called_once()

        resp_slow = client.get("/api/scan/slow")
        self.assertEqual(resp_slow.status_code, 200)
        self.assertEqual(resp_slow.json()["status"], "success")
        mock_generic.assert_called_once()


if __name__ == "__main__":
    unittest.main()

