import unittest

from src.free_game.ai import extract_deadline, extract_original_price, platform_from_url


class ArticleMetadataTests(unittest.TestCase):
    def test_extract_twd_original_price(self):
        self.assertEqual(extract_original_price("本作原價新台幣 27 元"), "NT$27")

    def test_extract_taiwan_deadline(self):
        article = "期限至台灣時間 2026 年 11 月 2 日凌晨 1 點 2 分"
        self.assertEqual(
            extract_deadline(article),
            "2026-11-02T01:02:00+08:00",
        )

    def test_epic_platform_from_store_url(self):
        self.assertEqual(
            platform_from_url("https://store.epicgames.com/zh-TW/p/mafia-hotel"),
            "Epic Games Store",
        )

    def test_missing_values_stay_missing(self):
        self.assertEqual(extract_original_price("免費領取"), "")
        self.assertEqual(extract_deadline("期限未提供"), "")


if __name__ == "__main__":
    unittest.main()
