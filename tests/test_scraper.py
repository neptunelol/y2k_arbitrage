"""
Unit tests for modules/scraper.py
"""

import os
import unittest
from unittest.mock import MagicMock, patch

from dotenv import load_dotenv

import modules.scraper as scraper


class TestScraperModule(unittest.TestCase):
    def setUp(self):
        load_dotenv()

    def test_importability_and_aliases(self):
        """Verify scraper module exports scrape_ebay_listings and fetch_ebay_listings alias."""
        self.assertTrue(hasattr(scraper, "scrape_ebay_listings"))
        self.assertTrue(callable(scraper.scrape_ebay_listings))
        self.assertTrue(hasattr(scraper, "fetch_ebay_listings"))
        self.assertEqual(scraper.scrape_ebay_listings, scraper.fetch_ebay_listings)

    def test_default_queries_count_and_content(self):
        """Verify the 10 fallback query terms."""
        self.assertEqual(len(scraper.DEFAULT_SEARCH_QUERIES), 10)
        expected_queries = [
            "Old silver camera",
            "Untested digital camera",
            "Vintage point and shoot",
            "Digital camera lot",
            "Old camera estate sale",
            "Retro digital camera",
            "Early digital camera",
            "Y2K camera",
            "Old compact camera",
            "Grandma camera digital",
        ]
        self.assertEqual(scraper.DEFAULT_SEARCH_QUERIES, expected_queries)

    def test_environment_endpoint_resolution(self):
        """Verify endpoint URL resolution for sandbox vs production."""
        token_sb, base_sb = scraper.get_ebay_endpoints("sandbox")
        self.assertEqual(token_sb, "https://api.sandbox.ebay.com/identity/v1/oauth2/token")
        self.assertEqual(base_sb, "https://api.sandbox.ebay.com")

        token_prod, base_prod = scraper.get_ebay_endpoints("PRODUCTION")
        self.assertEqual(token_prod, "https://api.ebay.com/identity/v1/oauth2/token")
        self.assertEqual(base_prod, "https://api.ebay.com")

    def test_placeholder_credentials_returns_empty_list(self):
        """Verify that placeholder credentials return empty list [] without crashing."""
        with patch.dict(os.environ, {"EBAY_APP_ID": "your_ebay_app_id_here", "EBAY_CERT_ID": "your_ebay_cert_id_here"}):
            results = scraper.scrape_ebay_listings()
            self.assertIsInstance(results, list)
            self.assertEqual(results, [])

    @patch("modules.scraper.requests.get")
    @patch("modules.scraper.requests.post")
    def test_successful_scrape_and_schema_validation(self, mock_post, mock_get):
        """Verify successful OAuth token fetch, Browse API call, deduplication, and schema structure."""
        # Mock OAuth token response
        mock_token_resp = MagicMock()
        mock_token_resp.status_code = 200
        mock_token_resp.json.return_value = {
            "access_token": "mock_access_token_12345",
            "expires_in": 7200,
        }
        mock_post.return_value = mock_token_resp

        # Mock Browse API search response
        mock_browse_resp = MagicMock()
        mock_browse_resp.status_code = 200
        mock_browse_resp.json.return_value = {
            "itemSummaries": [
                {
                    "title": "Canon PowerShot SD1000 Silver",
                    "itemWebUrl": "https://www.ebay.com/itm/123456789",
                    "price": {"value": "45.50", "currency": "USD"},
                    "image": {"imageUrl": "https://img.ebay.com/1.jpg"},
                    "additionalImages": [{"imageUrl": "https://img.ebay.com/2.jpg"}],
                    "shortDescription": "Tested working vintage camera",
                },
                {
                    "title": "Canon PowerShot SD1000 Silver Duplicate",
                    "itemWebUrl": "https://www.ebay.com/itm/123456789",  # Duplicate URL
                    "price": {"value": "45.50", "currency": "USD"},
                    "image": {"imageUrl": "https://img.ebay.com/1.jpg"},
                },
                {
                    "title": "Sony Cyber-shot DSC-W55 Blue",
                    "itemWebUrl": "https://www.ebay.com/itm/987654321",
                    "price": {"value": "29.99", "currency": "USD"},
                    "image": {"imageUrl": "https://img.ebay.com/3.jpg"},
                    "condition": "Used - Good",
                },
            ]
        }
        mock_get.return_value = mock_browse_resp

        with patch.dict(os.environ, {"EBAY_APP_ID": "real_app_id_test", "EBAY_CERT_ID": "real_cert_id_test"}):
            results = scraper.scrape_ebay_listings(queries=["Canon PowerShot"], max_results=5)

            # Assert 2 deduplicated items returned
            self.assertEqual(len(results), 2)

            # Check schema of first item
            item1 = results[0]
            self.assertIn("title", item1)
            self.assertIn("url", item1)
            self.assertIn("price", item1)
            self.assertIn("image_urls", item1)
            self.assertIn("seller_description", item1)

            self.assertIsInstance(item1["title"], str)
            self.assertIsInstance(item1["url"], str)
            self.assertIsInstance(item1["price"], float)
            self.assertIsInstance(item1["image_urls"], list)
            self.assertIsInstance(item1["seller_description"], str)

            self.assertEqual(item1["title"], "Canon PowerShot SD1000 Silver")
            self.assertEqual(item1["url"], "https://www.ebay.com/itm/123456789")
            self.assertEqual(item1["price"], 45.50)
            self.assertEqual(item1["image_urls"], ["https://img.ebay.com/1.jpg", "https://img.ebay.com/2.jpg"])
            self.assertEqual(item1["seller_description"], "Tested working vintage camera")

            # Check seller description fallback to condition on second item
            item2 = results[1]
            self.assertEqual(item2["seller_description"], "Used - Good")

            # Verify Browse API request headers and marketplace ID
            mock_get.assert_called()
            called_headers = mock_get.call_args[1]["headers"]
            self.assertEqual(called_headers["X-EBAY-C-MARKETPLACE-ID"], "EBAY_US")
            self.assertEqual(called_headers["Authorization"], "Bearer mock_access_token_12345")

    @patch("modules.scraper.requests.get")
    @patch("modules.scraper.requests.post")
    def test_null_payload_fields_handling(self, mock_post, mock_get):
        """Verify handling of null title, null image, and null additionalImages from API JSON response."""
        mock_token_resp = MagicMock()
        mock_token_resp.status_code = 200
        mock_token_resp.json.return_value = {"access_token": "mock_token"}
        mock_post.return_value = mock_token_resp

        mock_browse_resp = MagicMock()
        mock_browse_resp.status_code = 200
        mock_browse_resp.json.return_value = {
            "itemSummaries": [
                {
                    "title": None,
                    "itemWebUrl": "https://www.ebay.com/itm/nulltest123",
                    "price": None,
                    "image": None,
                    "additionalImages": None,
                    "shortDescription": None,
                }
            ]
        }
        mock_get.return_value = mock_browse_resp

        with patch.dict(os.environ, {"EBAY_APP_ID": "real_app_id", "EBAY_CERT_ID": "real_cert_id"}):
            results = scraper.scrape_ebay_listings(queries=["null test"], max_results=1)

            self.assertEqual(len(results), 1)
            item = results[0]
            self.assertEqual(item["title"], "")
            self.assertNotEqual(item["title"], "None")
            self.assertEqual(item["image_urls"], [])
            self.assertEqual(item["price"], 0.0)
            self.assertEqual(item["seller_description"], "")


if __name__ == "__main__":
    unittest.main()

