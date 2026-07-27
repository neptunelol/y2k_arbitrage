"""
Unit tests for modules/vision_ai.py
"""

import os
import unittest
from unittest.mock import MagicMock, patch

from dotenv import load_dotenv

import modules.vision_ai as vision_ai


class TestVisionAIModule(unittest.TestCase):
    def setUp(self):
        load_dotenv()

    def test_function_signature_and_callable(self):
        """Verify identify_camera_listings function exists and is callable with default args."""
        self.assertTrue(hasattr(vision_ai, "identify_camera_listings"))
        self.assertTrue(callable(vision_ai.identify_camera_listings))

    def test_empty_or_none_listings(self):
        """Verify empty or None inputs return ([], [])."""
        res_none = vision_ai.identify_camera_listings(None)
        self.assertEqual(res_none, ([], []))

        res_empty = vision_ai.identify_camera_listings([])
        self.assertEqual(res_empty, ([], []))

    def test_placeholder_credential_fallback(self):
        """Verify placeholder API key produces non-crashing fallback dicts with confidence 0.0."""
        listings = [
            {
                "title": "Sony Cyber-shot DSC-T700",
                "url": "https://www.ebay.com/itm/111",
                "price": 50.0,
                "image_urls": ["https://img.ebay.com/1.jpg"],
                "seller_description": "Untested camera",
            }
        ]
        with patch.dict(os.environ, {"OPENAI_API_KEY": "your_openai_api_key_here"}):
            filtered, all_db = vision_ai.identify_camera_listings(listings, api_key="your_openai_api_key_here")
            self.assertEqual(len(all_db), 1)
            self.assertEqual(len(filtered), 1)
            item = all_db[0]
            self.assertEqual(item["confidence_score"], 0.0)
            self.assertEqual(item["identified_model"], "Sony Cyber-shot DSC-T700")
            self.assertEqual(item["damage_severity"], "none")
            self.assertIn("Fallback", item["damage_notes"])

    def test_image_truncation_to_three(self):
        """Verify that at most 3 image URLs are sent to OpenAI API even if listing has 5 images."""
        listings = [
            {
                "title": "Canon PowerShot SD1000",
                "url": "https://www.ebay.com/itm/222",
                "price": 35.0,
                "image_urls": [
                    "https://img.ebay.com/1.jpg",
                    "https://img.ebay.com/2.jpg",
                    "https://img.ebay.com/3.jpg",
                    "https://img.ebay.com/4.jpg",
                    "https://img.ebay.com/5.jpg",
                ],
                "seller_description": "Good condition",
            }
        ]

        mock_openai_instance = MagicMock()
        mock_response = MagicMock()
        mock_response.choices = [
            MagicMock(
                message=MagicMock(
                    content='{"identified_model": "Canon PowerShot SD1000", "damage_severity": "none", "damage_notes": "Clean", "confidence_score": 0.9}'
                )
            )
        ]
        mock_openai_instance.chat.completions.create.return_value = mock_response

        with patch("openai.OpenAI", return_value=mock_openai_instance):
            filtered, all_db = vision_ai.identify_camera_listings(listings, api_key="sk-real-test-key")

            mock_openai_instance.chat.completions.create.assert_called_once()
            call_kwargs = mock_openai_instance.chat.completions.create.call_args[1]
            messages = call_kwargs["messages"]

            user_msg = None
            for msg in messages:
                if msg["role"] == "user":
                    user_msg = msg
                    break

            self.assertIsNotNone(user_msg)
            content = user_msg["content"]

            image_blocks = [c for c in content if isinstance(c, dict) and c.get("type") == "image_url"]
            self.assertEqual(len(image_blocks), 3)
            self.assertEqual(image_blocks[0]["image_url"]["url"], "https://img.ebay.com/1.jpg")
            self.assertEqual(image_blocks[1]["image_url"]["url"], "https://img.ebay.com/2.jpg")
            self.assertEqual(image_blocks[2]["image_url"]["url"], "https://img.ebay.com/3.jpg")

    def test_damage_gating_and_all_item_db_inclusion(self):
        """Verify major damage items are excluded from filtered_for_pricer but retained in all_enriched_for_db."""
        listings = [
            {
                "title": "Sony DSC-T700 Cracked Screen",
                "url": "https://www.ebay.com/itm/major1",
                "price": 20.0,
                "image_urls": ["https://img.ebay.com/1.jpg"],
                "seller_description": "Cracked screen",
            },
            {
                "title": "Nikon Coolpix S210 Scratched",
                "url": "https://www.ebay.com/itm/minor1",
                "price": 30.0,
                "image_urls": ["https://img.ebay.com/2.jpg"],
                "seller_description": "Light scratches",
            },
            {
                "title": "Olympus FE-230 Mint",
                "url": "https://www.ebay.com/itm/none1",
                "price": 50.0,
                "image_urls": ["https://img.ebay.com/3.jpg"],
                "seller_description": "Mint condition",
            },
        ]

        def mock_completion(model, messages, response_format, max_tokens, temperature):
            user_content = messages[1]["content"]
            text_part = user_content[0]["text"]
            mock_resp = MagicMock()
            if "Cracked Screen" in text_part:
                mock_resp.choices = [
                    MagicMock(
                        message=MagicMock(
                            content='{"identified_model": "Sony Cyber-shot DSC-T700", "damage_severity": "major", "damage_notes": "Cracked LCD display", "confidence_score": 0.95}'
                        )
                    )
                ]
            elif "Scratched" in text_part:
                mock_resp.choices = [
                    MagicMock(
                        message=MagicMock(
                            content='{"identified_model": "Nikon Coolpix S210", "damage_severity": "minor", "damage_notes": "Body scratches", "confidence_score": 0.85}'
                        )
                    )
                ]
            else:
                mock_resp.choices = [
                    MagicMock(
                        message=MagicMock(
                            content='{"identified_model": "Olympus FE-230", "damage_severity": "none", "damage_notes": "No damage", "confidence_score": 0.98}'
                        )
                    )
                ]
            return mock_resp

        mock_openai_instance = MagicMock()
        mock_openai_instance.chat.completions.create.side_effect = mock_completion

        with patch("openai.OpenAI", return_value=mock_openai_instance):
            filtered, all_db = vision_ai.identify_camera_listings(listings, api_key="sk-real-test-key")

            self.assertEqual(len(all_db), 3)
            self.assertEqual(len(filtered), 2)

            filtered_titles = [item["title"] for item in filtered]
            self.assertNotIn("Sony DSC-T700 Cracked Screen", filtered_titles)
            self.assertIn("Nikon Coolpix S210 Scratched", filtered_titles)
            self.assertIn("Olympus FE-230 Mint", filtered_titles)

            all_db_models = [item["identified_model"] for item in all_db]
            self.assertEqual(all_db_models, ["Sony Cyber-shot DSC-T700", "Nikon Coolpix S210", "Olympus FE-230"])

    def test_api_exception_fallback(self):
        """Verify API exception produces warning log and fallback dict with confidence 0.0."""
        listings = [
            {
                "title": "Failing API Camera",
                "url": "https://www.ebay.com/itm/fail",
                "price": 10.0,
                "image_urls": [],
                "seller_description": "Test",
            }
        ]
        mock_openai_instance = MagicMock()
        mock_openai_instance.chat.completions.create.side_effect = Exception("API connection error")

        with patch("openai.OpenAI", return_value=mock_openai_instance):
            filtered, all_db = vision_ai.identify_camera_listings(listings, api_key="sk-real-test-key")

            self.assertEqual(len(all_db), 1)
            self.assertEqual(len(filtered), 1)
            item = all_db[0]
            self.assertEqual(item["confidence_score"], 0.0)
            self.assertIn("Fallback", item["damage_notes"])

    def test_vlm_json_parsing(self):
        """Verify parse_vlm_json_response handles raw JSON, markdown codeblocks, and out-of-range fields."""
        # 1. Clean JSON
        raw1 = '{"identified_model": "Sony Cyber-shot DSC-W55", "damage_severity": "minor", "damage_notes": "Scratches on lens rim", "confidence_score": 0.88}'
        res1 = vision_ai.parse_vlm_json_response(raw1)
        self.assertEqual(res1["identified_model"], "Sony Cyber-shot DSC-W55")
        self.assertEqual(res1["damage_severity"], "minor")
        self.assertEqual(res1["damage_notes"], "Scratches on lens rim")
        self.assertEqual(res1["confidence_score"], 0.88)

        # 2. Markdown fenced JSON block with uppercase enum and out-of-bounds confidence
        raw2 = '```json\n{"identified_model": "Canon PowerShot A590", "damage_severity": "MAJOR", "damage_notes": "Corroded battery bay", "confidence_score": 1.5}\n```'
        res2 = vision_ai.parse_vlm_json_response(raw2)
        self.assertEqual(res2["identified_model"], "Canon PowerShot A590")
        self.assertEqual(res2["damage_severity"], "major")
        self.assertEqual(res2["confidence_score"], 1.0)

        # 3. Invalid/malformed JSON falls back safely
        raw3 = "Sorry I cannot identify this."
        res3 = vision_ai.parse_vlm_json_response(raw3, fallback_title="Fallback Title Camera")
        self.assertEqual(res3["identified_model"], "Fallback Title Camera")
        self.assertEqual(res3["damage_severity"], "none")
        self.assertEqual(res3["confidence_score"], 0.5)


if __name__ == "__main__":
    unittest.main()
