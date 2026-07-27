"""
Unit tests for modules/pricer.py
"""

import os
import unittest
from unittest.mock import MagicMock, patch

from dotenv import load_dotenv

import modules.pricer as pricer

load_dotenv()


class TestPricerModule(unittest.TestCase):
    def setUp(self):
        load_dotenv()

    def test_importability_and_signature(self):
        """Verify pricer module exports price_camera_listings and core helpers."""
        self.assertTrue(hasattr(pricer, "price_camera_listings"))
        self.assertTrue(callable(pricer.price_camera_listings))
        self.assertTrue(hasattr(pricer, "calculate_market_value"))
        self.assertTrue(hasattr(pricer, "calculate_profit_margin"))

    def test_extract_asking_price(self):
        """Verify asking price extraction from 'asking_price' and 'price' aliases."""
        self.assertEqual(pricer.extract_asking_price({"asking_price": 50.0}), 50.0)
        self.assertEqual(pricer.extract_asking_price({"price": 35.5}), 35.5)
        self.assertEqual(pricer.extract_asking_price({"asking_price": "$45.50"}), 45.50)
        self.assertEqual(pricer.extract_asking_price({"price": "  12.99 "}), 12.99)
        self.assertIsNone(pricer.extract_asking_price({"asking_price": 0}))
        self.assertIsNone(pricer.extract_asking_price({"asking_price": -10.0}))
        self.assertIsNone(pricer.extract_asking_price({"price": "invalid"}))
        self.assertIsNone(pricer.extract_asking_price({}))

    def test_calculate_market_value(self):
        """Verify market value calculation averages up to 5 valid sold prices."""
        # 5 prices
        self.assertEqual(pricer.calculate_market_value([100.0, 200.0, 300.0, 400.0, 500.0]), 300.0)
        # More than 5 prices -> takes first 5
        self.assertEqual(pricer.calculate_market_value([10.0, 20.0, 30.0, 40.0, 50.0, 60.0]), 30.0)
        # Fewer than 5 prices
        self.assertEqual(pricer.calculate_market_value([50.0, 60.0]), 55.0)
        # Non-positive values filtered out
        self.assertEqual(pricer.calculate_market_value([0, -10, 50.0, None, "bad", 70.0]), 60.0)
        # Empty or None input
        self.assertIsNone(pricer.calculate_market_value([]))
        self.assertIsNone(pricer.calculate_market_value(None))

    def test_calculate_profit_margin(self):
        """Verify profit margin calculation formula: ((market - asking) / market) * 100."""
        # Market 100, Asking 50 -> 50%
        self.assertEqual(pricer.calculate_profit_margin(50.0, 100.0), 50.0)
        # Market 100, Asking 70 -> 30%
        self.assertEqual(pricer.calculate_profit_margin(70.0, 100.0), 30.0)
        # Market 100, Asking 100 -> 0%
        self.assertEqual(pricer.calculate_profit_margin(100.0, 100.0), 0.0)
        # Market 100, Asking 120 -> -20%
        self.assertEqual(pricer.calculate_profit_margin(120.0, 100.0), -20.0)
        # Invalid / missing values return None
        self.assertIsNone(pricer.calculate_profit_margin(None, 100.0))
        self.assertIsNone(pricer.calculate_profit_margin(50.0, None))
        self.assertIsNone(pricer.calculate_profit_margin(0.0, 100.0))
        self.assertIsNone(pricer.calculate_profit_margin(50.0, 0.0))

    def test_get_min_profit_margin(self):
        """Verify loading MIN_PROFIT_MARGIN with default fallback."""
        with patch.dict(os.environ, {"MIN_PROFIT_MARGIN": "45.0"}):
            self.assertEqual(pricer.get_min_profit_margin(), 45.0)

        with patch.dict(os.environ, {"MIN_PROFIT_MARGIN": "invalid_val"}):
            self.assertEqual(pricer.get_min_profit_margin(), 40.0)

    @patch("modules.pricer.requests.get")
    @patch("modules.pricer.fetch_oauth_token")
    def test_tier1_marketplace_insights_success(self, mock_oauth, mock_get):
        """Verify Tier 1 Marketplace Insights API pricing calculation."""
        mock_oauth.return_value = "mock_access_token_insights"

        mock_insights_resp = MagicMock()
        mock_insights_resp.status_code = 200
        mock_insights_resp.json.return_value = {
            "itemSales": [
                {"price": {"value": "100.00"}},
                {"price": {"value": "110.00"}},
                {"price": {"value": "90.00"}},
            ]
        }
        mock_get.return_value = mock_insights_resp

        listings = [
            {
                "title": "Canon PowerShot SD1000",
                "price": 50.0,
                "identified_model": "Canon PowerShot SD1000",
            }
        ]

        with patch.dict(os.environ, {"EBAY_APP_ID": "real_app_id", "EBAY_CERT_ID": "real_cert_id"}):
            results = pricer.price_camera_listings(listings)

            self.assertEqual(len(results), 1)
            item = results[0]
            # Average sold comps = (100 + 110 + 90) / 3 = 100.0
            self.assertEqual(item["estimated_market_value"], 100.0)
            # Profit margin = (100 - 50) / 100 * 100 = 50.0%
            self.assertEqual(item["profit_margin"], 50.0)
            self.assertTrue(item["is_profitable_deal"])

    @patch("modules.pricer.requests.get")
    @patch("modules.pricer.fetch_oauth_token")
    def test_tier2_browse_api_active_comps_fallback(self, mock_oauth, mock_get):
        """Verify Tier 2 Browse API fallback when Insights API fails/403."""
        mock_oauth.return_value = "mock_access_token_browse"

        # First call (Insights) fails with 403 Forbidden
        mock_insights_resp = MagicMock()
        mock_insights_resp.status_code = 403

        # Second call (Browse API) succeeds
        mock_browse_resp = MagicMock()
        mock_browse_resp.status_code = 200
        mock_browse_resp.json.return_value = {
            "itemSummaries": [
                {"price": {"value": "100.00"}},
                {"price": {"value": "100.00"}},
            ]
        }
        mock_get.side_effect = [mock_insights_resp, mock_browse_resp]

        listings = [
            {
                "title": "Sony Cyber-shot DSC-W55",
                "asking_price": 40.0,
                "identified_model": "Sony Cyber-shot DSC-W55",
            }
        ]

        with patch.dict(os.environ, {"EBAY_APP_ID": "real_app_id", "EBAY_CERT_ID": "real_cert_id"}):
            results = pricer.price_camera_listings(listings)

            self.assertEqual(len(results), 1)
            item = results[0]
            # Active avg 100.0 * 0.85 = 85.0
            self.assertEqual(item["estimated_market_value"], 85.0)
            # Margin = (85 - 40) / 85 * 100 = 52.94%
            self.assertEqual(item["profit_margin"], 52.94)
            self.assertTrue(item["is_profitable_deal"])

    def test_tier3_benchmark_lookup_fallback(self):
        """Verify Tier 3 Benchmark lookup fallback on placeholder credentials."""
        listings = [
            {
                "title": "Canon PowerShot SD1000 Silver",
                "price": 40.0,
                "identified_model": "Canon PowerShot SD1000",
            },
            {
                "title": "Unknown Vintage Camera",
                "price": 30.0,
                "identified_model": "Unknown Camera",
            },
        ]

        with patch.dict(os.environ, {"EBAY_APP_ID": "your_ebay_app_id_here", "EBAY_CERT_ID": "your_ebay_cert_id_here"}):
            results = pricer.price_camera_listings(listings)

            self.assertEqual(len(results), 2)

            # Item 1: Known model Canon PowerShot SD1000 -> benchmark $85.00
            item1 = results[0]
            self.assertEqual(item1["estimated_market_value"], 85.0)
            # Margin = (85 - 40) / 85 * 100 = 52.94% >= 40% -> True
            self.assertEqual(item1["profit_margin"], 52.94)
            self.assertTrue(item1["is_profitable_deal"])

            # Item 2: Unknown model -> default benchmark $45.00
            item2 = results[1]
            self.assertEqual(item2["estimated_market_value"], 45.0)
            # Margin = (45 - 30) / 45 * 100 = 33.33% < 40% -> False
            self.assertEqual(item2["profit_margin"], 33.33)
            self.assertFalse(item2["is_profitable_deal"])

    def test_requirement_r3_unprofitable_deals_retained(self):
        """Verify Requirement R3: All input listings retained and enriched (not discarded)."""
        listings = [
            {"title": "Cheap Deal", "asking_price": 20.0, "identified_model": "Canon PowerShot SD1000"},  # Margin ~76%
            {"title": "Expensive Deal", "asking_price": 80.0, "identified_model": "Canon PowerShot SD1000"},  # Margin ~5.88%
        ]

        with patch.dict(os.environ, {"EBAY_APP_ID": "your_ebay_app_id_here", "EBAY_CERT_ID": "your_ebay_cert_id_here"}):
            results = pricer.price_camera_listings(listings)

            # Assert count matches input list
            self.assertEqual(len(results), 2)
            self.assertTrue(results[0]["is_profitable_deal"])
            self.assertFalse(results[1]["is_profitable_deal"])

            # Check required enriched keys present on all items
            for item in results:
                self.assertIn("estimated_market_value", item)
                self.assertIn("profit_margin", item)
                self.assertIn("is_profitable_deal", item)

    def test_empty_and_none_inputs(self):
        """Verify behavior with empty/None/malformed inputs."""
        self.assertEqual(pricer.price_camera_listings(None), [])
        self.assertEqual(pricer.price_camera_listings([]), [])

        # Listing with missing price key
        results = pricer.price_camera_listings([{"title": "No price camera"}])
        self.assertEqual(len(results), 1)
        item = results[0]
        self.assertEqual(item["estimated_market_value"], 45.0)  # Default fallback
        self.assertIsNone(item["profit_margin"])
        self.assertFalse(item["is_profitable_deal"])

    @patch("modules.pricer.requests.get")
    @patch("modules.pricer.fetch_oauth_token")
    def test_network_exceptions_handled_gracefully(self, mock_oauth, mock_get):
        """Verify network exceptions (timeouts, connection errors) do not crash execution."""
        mock_oauth.return_value = "mock_token"
        mock_get.side_effect = Exception("Connection refused / Timeout")

        listings = [
            {"title": "Nikon Coolpix S210", "price": 25.0, "identified_model": "Nikon Coolpix S210"}
        ]

        with patch.dict(os.environ, {"EBAY_APP_ID": "real_app_id", "EBAY_CERT_ID": "real_cert_id"}):
            results = pricer.price_camera_listings(listings)

            self.assertEqual(len(results), 1)
            item = results[0]
            # Graceful fallback to Tier 3 benchmark ($55.00 for Nikon Coolpix S210)
            self.assertEqual(item["estimated_market_value"], 55.0)
            # Margin = (55 - 25) / 55 * 100 = 54.55%
            self.assertEqual(item["profit_margin"], 54.55)
            self.assertTrue(item["is_profitable_deal"])


if __name__ == "__main__":
    unittest.main()
