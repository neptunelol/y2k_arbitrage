"""
Unit tests for modules/database.py
"""

import os
import unittest
from unittest.mock import MagicMock, patch

from dotenv import load_dotenv

import modules.database as database

load_dotenv()


class TestDatabaseModule(unittest.TestCase):
    def setUp(self):
        load_dotenv()

    def test_is_placeholder_credential(self):
        """Verify placeholder credential detection logic."""
        # Placeholders / missing
        self.assertTrue(database.is_placeholder_credential(None, None))
        self.assertTrue(database.is_placeholder_credential("", ""))
        self.assertTrue(
            database.is_placeholder_credential(
                "https://your-supabase-project.supabase.co", "your_supabase_anon_or_service_role_key"
            )
        )
        self.assertTrue(database.is_placeholder_credential("https://my-app.supabase.co", "your_key"))
        self.assertTrue(database.is_placeholder_credential("https://your-supabase.co", "eyJhbGciOi..."))

        # Valid credentials
        self.assertFalse(
            database.is_placeholder_credential(
                "https://xyz12345.supabase.co", "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.validkey"
            )
        )

    @patch.dict(
        os.environ,
        {
            "SUPABASE_URL": "https://your-supabase-project.supabase.co",
            "SUPABASE_KEY": "your_supabase_anon_or_service_role_key",
        },
    )
    def test_get_supabase_client_placeholder_credentials(self):
        """Verify get_supabase_client returns None when credentials are placeholders."""
        client = database.get_supabase_client()
        self.assertIsNone(client)

    @patch("modules.database.create_client")
    @patch.dict(
        os.environ,
        {
            "SUPABASE_URL": "https://validproject.supabase.co",
            "SUPABASE_KEY": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.validkey",
        },
    )
    def test_get_supabase_client_valid_credentials(self, mock_create_client):
        """Verify get_supabase_client returns client instance when valid credentials exist."""
        mock_client = MagicMock()
        mock_create_client.return_value = mock_client

        client = database.get_supabase_client()
        self.assertEqual(client, mock_client)
        mock_create_client.assert_called_once_with(
            "https://validproject.supabase.co", "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.validkey"
        )

    def test_format_listing_for_db_alias_transformation(self):
        """Verify field alias transformations (url->listing_url, identified_model->model_name, price->asking_price, estimated_market_value->market_value)."""
        input_listing = {
            "url": "https://ebay.com/itm/123456",
            "title": "Canon IXY Digital 50",
            "identified_model": "Canon IXY Digital 50",
            "price": 45.00,
            "estimated_market_value": 110.00,
            "profit_margin": 59.09,
            "is_profitable_deal": True,
            "confidence_score": 0.95,
            "damage_severity": "none",
            "damage_notes": "Minor scratches",
            "image_urls": ["https://img.com/1.jpg"],
        }

        formatted = database.format_listing_for_db(input_listing)

        self.assertEqual(formatted["listing_url"], "https://ebay.com/itm/123456")
        self.assertEqual(formatted["title"], "Canon IXY Digital 50")
        self.assertEqual(formatted["model_name"], "Canon IXY Digital 50")
        self.assertEqual(formatted["asking_price"], 45.00)
        self.assertEqual(formatted["market_value"], 110.00)
        self.assertEqual(formatted["profit_margin"], 59.09)
        self.assertTrue(formatted["is_profitable_deal"])
        self.assertEqual(formatted["confidence_score"], 0.95)
        self.assertEqual(formatted["damage_severity"], "none")
        self.assertEqual(formatted["image_urls"], ["https://img.com/1.jpg"])

    def test_format_listing_for_db_major_damage_null_handling(self):
        """Verify major damage listings reset market_value and profit_margin to None and is_profitable_deal to False."""
        input_listing = {
            "url": "https://ebay.com/itm/7890",
            "title": "Broken Sony Cyber-shot",
            "identified_model": "Sony Cyber-shot DSC-W55",
            "price": 20.00,
            "estimated_market_value": 80.00,
            "profit_margin": 75.00,
            "is_profitable_deal": True,
            "confidence_score": 0.90,
            "damage_severity": "major",
            "damage_notes": "Cracked lens element",
        }

        formatted = database.format_listing_for_db(input_listing)

        self.assertIsNone(formatted["market_value"])
        self.assertIsNone(formatted["profit_margin"])
        self.assertFalse(formatted["is_profitable_deal"])
        self.assertEqual(formatted["damage_severity"], "major")

    def test_format_listing_for_db_image_urls_formatting(self):
        """Verify image_urls formatting handles lists, JSON strings, and None."""
        res_list = database.format_listing_for_db({"url": "https://e.com/1", "image_urls": ["a", "b"]})
        self.assertEqual(res_list["image_urls"], ["a", "b"])

        res_json = database.format_listing_for_db({"url": "https://e.com/1", "image_urls": '["c", "d"]'})
        self.assertEqual(res_json["image_urls"], ["c", "d"])

        res_none = database.format_listing_for_db({"url": "https://e.com/1", "image_urls": None})
        self.assertEqual(res_none["image_urls"], [])

    def test_check_existing_urls_chunking(self):
        """Verify check_existing_urls queries in 100-item chunks and aggregates results."""
        mock_client = MagicMock()
        mock_query = MagicMock()
        mock_client.table.return_value = mock_query
        mock_query.select.return_value = mock_query
        mock_query.in_.return_value = mock_query

        # Generate 150 test URLs
        urls = [f"https://ebay.com/itm/{i}" for i in range(150)]

        # Response 1 for first 100, Response 2 for next 50
        res1 = MagicMock()
        res1.data = [{"listing_url": f"https://ebay.com/itm/{i}"} for i in range(10)]
        res2 = MagicMock()
        res2.data = [{"listing_url": f"https://ebay.com/itm/{i}"} for i in range(100, 105)]

        mock_query.execute.side_effect = [res1, res2]

        existing = database.check_existing_urls(urls, client=mock_client)

        self.assertEqual(len(existing), 15)
        self.assertIn("https://ebay.com/itm/0", existing)
        self.assertIn("https://ebay.com/itm/104", existing)
        self.assertEqual(mock_query.in_.call_count, 2)

    def test_check_existing_urls_empty_or_none(self):
        """Verify check_existing_urls handles empty list or missing client gracefully."""
        self.assertEqual(database.check_existing_urls([]), set())
        self.assertEqual(database.check_existing_urls(["https://ebay.com/1"], client=None), set())

    def test_save_listings_dry_run_fallback(self):
        """Verify save_listings in dry-run mode (client=None) counts valid items as skipped."""
        listings = [
            {"url": "https://ebay.com/itm/1", "title": "Camera 1"},
            {"url": "https://ebay.com/itm/2", "title": "Camera 2"},
            {"title": "Invalid No URL"},
        ]

        result = database.save_listings(listings, client=None)

        self.assertEqual(result, {"inserted": 0, "skipped": 2, "failed": 1})

    def test_save_listings_deduplication_and_insert(self):
        """Verify save_listings intra-batch deduplication and DB insertion counting."""
        mock_client = MagicMock()
        mock_query = MagicMock()
        mock_client.table.return_value = mock_query
        mock_query.insert.return_value = mock_query

        # Mock check_existing_urls to return existing URL 'https://ebay.com/itm/db_exists'
        with patch.object(database, "check_existing_urls", return_value={"https://ebay.com/itm/db_exists"}):
            mock_res = MagicMock()
            mock_res.data = [{"listing_url": "https://ebay.com/itm/new_1"}, {"listing_url": "https://ebay.com/itm/new_2"}]
            mock_query.execute.return_value = mock_res

            listings = [
                {"url": "https://ebay.com/itm/new_1", "title": "New 1"},
                {"url": "https://ebay.com/itm/new_2", "title": "New 2"},
                {"url": "https://ebay.com/itm/new_1", "title": "Batch Duplicate"},
                {"url": "https://ebay.com/itm/db_exists", "title": "DB Exists"},
                {"no_url": "invalid"},
            ]

            res = database.save_listings(listings, client=mock_client)

            # Total = 5:
            # 2 new inserted
            # 1 intra-batch duplicate skipped + 1 DB existing skipped = 2 skipped
            # 1 invalid failed
            self.assertEqual(res["inserted"], 2)
            self.assertEqual(res["skipped"], 2)
            self.assertEqual(res["failed"], 1)

    def test_save_listings_network_exception_fallback(self):
        """Verify network exception fallback during bulk insertion tries item-by-item insertion."""
        mock_client = MagicMock()
        mock_table = MagicMock()
        mock_client.table.return_value = mock_table

        # Bulk insert fails with Exception
        mock_bulk_query = MagicMock()
        mock_bulk_query.execute.side_effect = Exception("Network timeout")

        # Single row inserts: 1st succeeds, 2nd fails
        mock_single_query1 = MagicMock()
        mock_single_res1 = MagicMock()
        mock_single_res1.data = [{"listing_url": "https://ebay.com/itm/1"}]
        mock_single_query1.execute.return_value = mock_single_res1

        mock_single_query2 = MagicMock()
        mock_single_query2.execute.side_effect = Exception("DB error on row 2")

        mock_table.insert.side_effect = [mock_bulk_query, mock_single_query1, mock_single_query2]

        with patch.object(database, "check_existing_urls", return_value=set()):
            listings = [
                {"url": "https://ebay.com/itm/1", "title": "Camera 1"},
                {"url": "https://ebay.com/itm/2", "title": "Camera 2"},
            ]

            res = database.save_listings(listings, client=mock_client)

            self.assertEqual(res["inserted"], 1)
            self.assertEqual(res["skipped"], 0)
            self.assertEqual(res["failed"], 1)


    def test_format_listing_for_db_alias_resolution_with_none_primary(self):
        """Verify field alias resolution when primary field is None but fallback field is populated."""
        input_listing = {
            "listing_url": None,
            "url": "https://ebay.com/itm/alias_test",
            "model_name": None,
            "identified_model": "Canon IXY Digital 50",
            "asking_price": None,
            "price": 19.99,
            "market_value": None,
            "estimated_market_value": 49.99,
        }
        formatted = database.format_listing_for_db(input_listing)
        self.assertEqual(formatted["listing_url"], "https://ebay.com/itm/alias_test")
        self.assertEqual(formatted["model_name"], "Canon IXY Digital 50")
        self.assertEqual(formatted["asking_price"], 19.99)
        self.assertEqual(formatted["market_value"], 49.99)

    def test_format_listing_for_db_malformed_image_urls(self):
        """Verify malformed image_urls (e.g. non-list, non-string integer or dict) is handled gracefully without TypeError."""
        res_int = database.format_listing_for_db({"url": "https://e.com/1", "image_urls": 123})
        self.assertEqual(res_int["image_urls"], [])

        res_dict = database.format_listing_for_db({"url": "https://e.com/1", "image_urls": {"url": "http://img.com"}})
        self.assertEqual(res_dict["image_urls"], [])

        res_str = database.format_listing_for_db({"url": "https://e.com/1", "image_urls": "https://img.com/single.jpg"})
        self.assertEqual(res_str["image_urls"], ["https://img.com/single.jpg"])

    def test_check_existing_urls_per_chunk_exception_isolation(self):
        """Verify chunk query exception on 1st chunk does not abort 2nd chunk in check_existing_urls."""
        mock_client = MagicMock()
        mock_query = MagicMock()
        mock_client.table.return_value = mock_query
        mock_query.select.return_value = mock_query
        mock_query.in_.return_value = mock_query

        # Generate 150 test URLs
        urls = [f"https://ebay.com/itm/{i}" for i in range(150)]

        # Chunk 1 (0..99) raises Exception, Chunk 2 (100..149) returns 5 items
        res2 = MagicMock()
        res2.data = [{"listing_url": f"https://ebay.com/itm/{i}"} for i in range(100, 105)]
        mock_query.execute.side_effect = [Exception("Chunk 1 DB failure"), res2]

        existing = database.check_existing_urls(urls, client=mock_client)

        self.assertEqual(len(existing), 5)
        self.assertIn("https://ebay.com/itm/100", existing)
        self.assertIn("https://ebay.com/itm/104", existing)
        self.assertEqual(mock_query.in_.call_count, 2)

    def test_format_listing_for_db_string_boolean_parsing(self):
        """Verify robust string boolean conversion for is_profitable_deal."""
        res_false_str = database.format_listing_for_db({"url": "https://e.com/1", "is_profitable_deal": "false"})
        self.assertFalse(res_false_str["is_profitable_deal"])

        res_false_zero = database.format_listing_for_db({"url": "https://e.com/1", "is_profitable_deal": "0"})
        self.assertFalse(res_false_zero["is_profitable_deal"])

        res_true_str = database.format_listing_for_db({"url": "https://e.com/1", "is_profitable_deal": "True"})
        self.assertTrue(res_true_str["is_profitable_deal"])

        res_true_one = database.format_listing_for_db({"url": "https://e.com/1", "is_profitable_deal": "1"})
        self.assertTrue(res_true_one["is_profitable_deal"])

    def test_save_listings_format_listing_exception_isolation(self):
        """Verify format_listing_for_db exception inside save_listings increments failed count and continues."""
        mock_client = MagicMock()
        with patch.object(database, "format_listing_for_db") as mock_format:
            # 1st item succeeds, 2nd item raises Exception, 3rd item succeeds
            rec1 = {"listing_url": "https://e.com/1", "title": "1"}
            rec3 = {"listing_url": "https://e.com/3", "title": "3"}
            mock_format.side_effect = [rec1, Exception("Formatting error"), rec3]

            with patch.object(database, "check_existing_urls", return_value=set()):
                mock_query = MagicMock()
                mock_client.table.return_value = mock_query
                mock_query.insert.return_value = mock_query
                mock_res = MagicMock()
                mock_res.data = [rec1, rec3]
                mock_query.execute.return_value = mock_res

                listings = [
                    {"url": "https://e.com/1", "title": "1"},
                    {"url": "https://e.com/2", "title": "2"},
                    {"url": "https://e.com/3", "title": "3"},
                ]
                res = database.save_listings(listings, client=mock_client)
                self.assertEqual(res["inserted"], 2)
                self.assertEqual(res["failed"], 1)
                self.assertEqual(res["skipped"], 0)


if __name__ == "__main__":
    unittest.main()

