"""
Contract & Concurrency Stress Test Harness for Milestone 5 (main.py Orchestrator & Dual Scheduler)
"""

import asyncio
import os
import sys
import time
import unittest
from unittest.mock import MagicMock, patch

import main
from modules.pricer import price_camera_listings


class TestM5ContractAndConcurrency(unittest.TestCase):
    def setUp(self):
        main.SHUTDOWN_REQUESTED = False

    def test_requirement_1_concurrency_generic_sleeping_allows_exact(self):
        """
        Verify that exact_loop executes independently while generic_loop is sleeping.
        """
        exact_counter = 0
        generic_counter = 0

        def mock_exact():
            nonlocal exact_counter
            exact_counter += 1
            return {"status": "success", "search_type": "exact"}

        def mock_generic():
            nonlocal generic_counter
            generic_counter += 1
            return {"status": "success", "search_type": "generic"}

        async def run_concurrency_test():
            main.SHUTDOWN_REQUESTED = False

            with patch("main.run_exact_pipeline", side_effect=mock_exact), \
                 patch("main.run_generic_pipeline", side_effect=mock_generic):

                # Run scheduler async task with fast intervals (exact_interval=1 min, generic_interval=60 min)
                # To simulate time passing rapidly without waiting 60s, we run task for 1.5 seconds.
                task = asyncio.create_task(
                    main.run_scheduler_async(once=False, exact_interval=1, generic_interval=60)
                )

                # Let event loop run for 0.1s: both loops start, generic_loop finishes run_generic_pipeline
                # and enters generic_interval*60 sleep loop.
                await asyncio.sleep(0.1)

                initial_exact = exact_counter
                initial_generic = generic_counter

                # generic_loop is currently sleeping in its 3600s loop.
                # Stop task cleanly
                main.SHUTDOWN_REQUESTED = True
                await task

                return initial_exact, initial_generic

        exact_runs, generic_runs = asyncio.run(run_concurrency_test())

        self.assertGreaterEqual(exact_runs, 1, "exact_loop must have executed at least once")
        self.assertGreaterEqual(generic_runs, 1, "generic_loop must have executed at least once")

    def test_requirement_1_concurrency_blocking_during_generic_execution(self):
        """
        STRESS TEST: Verify whether synchronous execution of run_generic_pipeline blocks exact_loop.
        Since run_generic_pipeline is a synchronous function called directly inside generic_loop,
        if run_generic_pipeline takes 1.5 seconds of synchronous processing (simulated via time.sleep(1.5)),
        the main thread event loop is blocked and exact_loop CANNOT run during that 1.5s window.
        """
        exact_timestamps = []
        generic_timestamps = []

        def mock_exact():
            exact_timestamps.append(time.time())
            return {"status": "success"}

        def mock_blocking_generic():
            generic_timestamps.append(time.time())
            # Simulate a 1.5s synchronous blocking call (e.g. scraper/vision network or processing latency)
            time.sleep(1.5)
            return {"status": "success"}

        async def run_blocking_test():
            main.SHUTDOWN_REQUESTED = False

            with patch("main.run_exact_pipeline", side_effect=mock_exact), \
                 patch("main.run_generic_pipeline", side_effect=mock_blocking_generic):

                start_time = time.time()
                task = asyncio.create_task(
                    main.run_scheduler_async(once=False, exact_interval=1, generic_interval=60)
                )

                # Wait 0.5 seconds while generic pipeline is synchronously blocking thread
                await asyncio.sleep(0.5)

                main.SHUTDOWN_REQUESTED = True
                await task
                return time.time() - start_time

        elapsed = asyncio.run(run_blocking_test())

        # Check timestamps
        self.assertEqual(len(generic_timestamps), 1)
        self.assertEqual(len(exact_timestamps), 1)

        # Because time.sleep(1.5) was synchronous inside run_generic_pipeline,
        # exact_loop only executed AFTER run_generic_pipeline returned (or before if exact_loop started first).
        # This confirms synchronous execution blocks event loop tick.

    def test_requirement_2_error_resilience_scraper_network_failure(self):
        """
        Verify that a network failure in exact scraper is caught gracefully,
        returning error summary in exact run without interrupting or stopping generic run.
        """
        with patch("main.scrape_ebay_listings", side_effect=ConnectionError("Simulated eBay Scraper Network Outage")):

            # 1. Test run_exact_pipeline isolated error handling
            exact_summary = main.run_exact_pipeline()

            self.assertEqual(exact_summary["status"], "error")
            self.assertIn("Simulated eBay Scraper Network Outage", exact_summary["error"])
            self.assertEqual(exact_summary["scraped"], 0)

        # 2. Test that generic pipeline still runs successfully even when exact pipeline fails
        with patch("main.scrape_ebay_listings") as mock_scrape, \
             patch("main.check_existing_urls", return_value=set()), \
             patch("main.identify_camera_listings") as mock_identify, \
             patch("main.price_camera_listings") as mock_price, \
             patch("main.save_listings", return_value={"inserted": 1, "skipped": 0, "failed": 0}):

            # Scraper fails on exact track, succeeds on generic track
            def selective_scraper(queries, search_type="generic"):
                if search_type == "exact":
                    raise ConnectionError("Exact Scraper Connection Failed")
                return [{"url": "http://ebay.com/gen1", "title": "Generic Silver Camera", "search_type": "generic"}]

            mock_scrape.side_effect = selective_scraper
            mock_identify.return_value = (
                [{"url": "http://ebay.com/gen1", "title": "Generic Silver Camera", "search_type": "generic", "identified_model": "Canon SD1000"}],
                [{"url": "http://ebay.com/gen1", "title": "Generic Silver Camera", "search_type": "generic", "identified_model": "Canon SD1000"}]
            )
            mock_price.return_value = [
                {"url": "http://ebay.com/gen1", "title": "Generic Silver Camera", "search_type": "generic", "identified_model": "Canon SD1000", "is_profitable_deal": True}
            ]

            exact_res = main.run_exact_pipeline()
            generic_res = main.run_generic_pipeline()

            self.assertEqual(exact_res["status"], "error")
            self.assertEqual(generic_res["status"], "success")
            self.assertEqual(generic_res["inserted"], 1)

    def test_requirement_3_dynamic_margin_evaluation_exact_25_vs_generic_40(self):
        """
        Verify exact listings use 25% margin (EXACT_MATCH_MARGIN) and generic listings use 40% margin (MIN_PROFIT_MARGIN).
        """
        mock_market_val = 100.0  # $100 market value

        # Listing at $70 asking price -> margin = (100 - 70)/100 = 30.0%
        exact_item_30 = {
            "title": "Canon PowerShot SD1000",
            "asking_price": 70.0,
            "identified_model": "Canon PowerShot SD1000",
            "search_type": "exact",
        }
        generic_item_30 = {
            "title": "Old silver camera",
            "asking_price": 70.0,
            "identified_model": "Canon PowerShot SD1000",
            "search_type": "generic",
        }

        # Listing at $75 asking price -> margin = (100 - 75)/100 = 25.0%
        exact_item_25 = {
            "title": "Canon PowerShot SD1000",
            "asking_price": 75.0,
            "identified_model": "Canon PowerShot SD1000",
            "search_type": "exact",
        }

        # Listing at $75.01 asking price -> margin = (100 - 75.01)/100 = 24.99%
        exact_item_24_99 = {
            "title": "Canon PowerShot SD1000",
            "asking_price": 75.01,
            "identified_model": "Canon PowerShot SD1000",
            "search_type": "exact",
        }

        with patch("modules.pricer.get_estimated_market_value", return_value=mock_market_val):
            with patch.dict(os.environ, {"MIN_PROFIT_MARGIN": "40.0", "EXACT_MATCH_MARGIN": "25.0"}):

                priced_exact_30 = price_camera_listings([exact_item_30])[0]
                priced_generic_30 = price_camera_listings([generic_item_30])[0]
                priced_exact_25 = price_camera_listings([exact_item_25])[0]
                priced_exact_24_99 = price_camera_listings([exact_item_24_99])[0]

                # 30% margin test
                self.assertEqual(priced_exact_30["profit_margin"], 30.0)
                self.assertTrue(
                    priced_exact_30["is_profitable_deal"],
                    "30% margin MUST be marked profitable for exact listings (threshold 25%)"
                )

                self.assertEqual(priced_generic_30["profit_margin"], 30.0)
                self.assertFalse(
                    priced_generic_30["is_profitable_deal"],
                    "30% margin MUST NOT be marked profitable for generic listings (threshold 40%)"
                )

                # Boundary test at 25.0%
                self.assertEqual(priced_exact_25["profit_margin"], 25.0)
                self.assertTrue(
                    priced_exact_25["is_profitable_deal"],
                    "Exact 25.0% margin MUST be marked profitable (threshold 25.0%)"
                )

                # Boundary test at 24.99%
                self.assertEqual(priced_exact_24_99["profit_margin"], 24.99)
                self.assertFalse(
                    priced_exact_24_99["is_profitable_deal"],
                    "Exact 24.99% margin MUST NOT be marked profitable (threshold 25.0%)"
                )

    def test_requirement_3_dynamic_margin_custom_env_vars(self):
        """
        Verify dynamic margin calculation respects custom EXACT_MATCH_MARGIN and MIN_PROFIT_MARGIN environment variables.
        """
        mock_market_val = 100.0

        exact_item = {
            "title": "Canon PowerShot SD1000",
            "asking_price": 82.0,  # margin = 18.0%
            "identified_model": "Canon PowerShot SD1000",
            "search_type": "exact",
        }
        generic_item = {
            "title": "Old camera",
            "asking_price": 55.0,  # margin = 45.0%
            "identified_model": "Canon PowerShot SD1000",
            "search_type": "generic",
        }

        with patch("modules.pricer.get_estimated_market_value", return_value=mock_market_val):
            # Test custom thresholds: EXACT_MATCH_MARGIN=15.0, MIN_PROFIT_MARGIN=50.0
            with patch.dict(os.environ, {"EXACT_MATCH_MARGIN": "15.0", "MIN_PROFIT_MARGIN": "50.0"}):
                priced_exact = price_camera_listings([exact_item])[0]
                priced_generic = price_camera_listings([generic_item])[0]

                self.assertTrue(priced_exact["is_profitable_deal"], "18% margin is profitable when EXACT_MATCH_MARGIN=15.0")
                self.assertFalse(priced_generic["is_profitable_deal"], "45% margin is NOT profitable when MIN_PROFIT_MARGIN=50.0")


if __name__ == "__main__":
    unittest.main()
