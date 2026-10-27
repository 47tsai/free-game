import json
import tempfile
import unittest

from free_game.article import normalize_store_url, parse_article
from free_game.discord import DiscordSender, format_deadline
from free_game.models import Game
from free_game.state import StateStore
from free_game.stores import EpicPromotionResolver, SteamPriceResolver


class ArticleTests(unittest.TestCase):
    def test_steam_widget_is_normalized(self):
        self.assertEqual(
            normalize_store_url("https://store.steampowered.com/widget/12345/"),
            "https://store.steampowered.com/app/12345/",
        )

    def test_iframe_store_link_is_extracted(self):
        html = b"""
        <html><body>
        <h1>Example Game</h1>
        <iframe src="https://store.steampowered.com/widget/12345/"></iframe>
        </body></html>
        """
        article = parse_article(
            html, "https://www.4gamers.com.tw/article/x", "Example"
        )
        self.assertEqual(
            article.links,
            ("https://store.steampowered.com/app/12345/",),
        )

    def test_anchor_context_is_preserved(self):
        html = b"""
        <html><body>
        <a href="https://store.epicgames.com/p/example">Example Game</a>
        </body></html>
        """
        article = parse_article(
            html, "https://www.4gamers.com.tw/article/x", "Example"
        )
        self.assertEqual(article.store_links[0].context, "Example Game")


class SteamTests(unittest.TestCase):
    def test_best_match_prefers_exact_title(self):
        items = [
            {"name": "Example Game Deluxe", "is_free": False},
            {"name": "Example Game", "is_free": True},
        ]
        best = SteamPriceResolver._best_match("Example Game", items)
        self.assertEqual(best["name"], "Example Game")

    def test_best_match_rejects_unrelated_title(self):
        items = [{"name": "Completely Different Game"}]
        self.assertEqual(
            SteamPriceResolver._best_match("Example Game", items),
            {},
        )

    def test_price_uses_original_price_when_discounted(self):
        data = {
            "price_overview": {
                "initial_formatted": "NT$ 300.00",
                "final_formatted": "NT$ 150.00",
                "discount_percent": 50,
            }
        }
        self.assertEqual(
            SteamPriceResolver._price(data),
            "NT$ 300.00",
        )

    def test_rating_uses_exact_steam_app_review_summary(self):
        class FakeHttp:
            def get(self, url):
                self.url = url
                return json.dumps({
                    "query_summary": {
                        "total_reviews": 1000,
                        "total_positive": 960,
                        "review_score_desc": "極度好評",
                    }
                }).encode(), {}

        http = FakeHttp()
        rating = SteamPriceResolver(http).resolve_rating(
            "https://store.steampowered.com/app/12345/example/"
        )
        self.assertEqual(rating, "極度好評，96% 好評（1,000 則評論）")
        self.assertIn("/appreviews/12345?", http.url)
        self.assertIn("num_per_page=0", http.url)

    def test_rating_returns_empty_when_reviews_are_missing(self):
        class FakeHttp:
            def get(self, url):
                return json.dumps({
                    "query_summary": {
                        "total_reviews": 0,
                        "total_positive": 0,
                        "review_score_desc": "無評論",
                    }
                }).encode(), {}

        self.assertEqual(
            SteamPriceResolver(FakeHttp()).resolve_rating(
                "https://store.steampowered.com/app/12345/example/"
            ),
            "",
        )

    def test_rating_does_not_search_for_non_steam_links(self):
        class FakeHttp:
            def get(self, url):
                raise AssertionError("No lookup should happen for Epic links")

        self.assertEqual(
            SteamPriceResolver(FakeHttp()).resolve_rating(
                "https://store.epicgames.com/p/example"
            ),
            "",
        )

    def test_epic_link_does_not_trigger_steam_lookup(self):
        class FakeHttp:
            def get(self, url):
                raise AssertionError("Steam API must not be called for Epic links")

        self.assertEqual(
            SteamPriceResolver(FakeHttp()).resolve(
                "Example Game", "https://store.epicgames.com/p/example"
            ),
            "",
        )

    def test_price_uses_final_price_without_discount(self):
        data = {
            "price_overview": {
                "initial_formatted": "NT$ 300.00",
                "final_formatted": "NT$ 300.00",
                "discount_percent": 0,
            }
        }
        self.assertEqual(
            SteamPriceResolver._price(data),
            "NT$ 300.00",
        )


class EpicPromotionTests(unittest.TestCase):
    @staticmethod
    def response_for(slug="mafia-hotel"):
        return {
            "data": {
                "Catalog": {
                    "searchStore": {
                        "elements": [{
                            "title": "MAFIA HOTEL",
                            "offerMappings": [{"pageSlug": slug}],
                            "price": {
                                "totalPrice": {
                                    "originalPrice": 2700,
                                    "discountPrice": 0,
                                    "fmtPrice": {
                                        "originalPrice": "NT$ 27.00",
                                        "discountPrice": "NT$ 0.00",
                                    },
                                }
                            },
                            "promotions": {
                                "promotionalOffers": [{
                                    "promotionalOffers": [{
                                        "endDate": "2026-11-02T17:02:00Z"
                                    }]
                                }],
                                "upcomingPromotionalOffers": [],
                            },
                        }]
                    }
                }
            }
        }

    def test_resolves_exact_epic_slug_and_taiwan_deadline(self):
        class FakeHttp:
            def get(self, url):
                self.url = url
                return json.dumps(
                    EpicPromotionTests.response_for()
                ).encode(), {}

        http = FakeHttp()
        result = EpicPromotionResolver(http).resolve(
            "https://store.epicgames.com/zh-TW/p/mafia-hotel"
        )
        self.assertEqual(result["original_price"], "NT$ 27.00")
        self.assertEqual(result["deadline"], "2026-11-03T01:02:00+08:00")
        self.assertIn("country=TW", http.url)
        self.assertIn("locale=zh-TW", http.url)

    def test_does_not_match_a_different_epic_slug(self):
        class FakeHttp:
            def get(self, url):
                return json.dumps(
                    EpicPromotionTests.response_for("different-game")
                ).encode(), {}

        self.assertEqual(
            EpicPromotionResolver(FakeHttp()).resolve(
                "https://store.epicgames.com/p/mafia-hotel"
            ),
            {},
        )

    def test_rejects_non_epic_links_without_request(self):
        class FakeHttp:
            def get(self, url):
                raise AssertionError("No request should be made")

        self.assertEqual(
            EpicPromotionResolver(FakeHttp()).resolve(
                "https://example.com/p/mafia-hotel"
            ),
            {},
        )

    def test_missing_or_nonfree_price_is_not_reported(self):
        data = self.response_for()
        data["data"]["Catalog"]["searchStore"]["elements"][0]["price"][
            "totalPrice"
        ]["discountPrice"] = 100
        result = EpicPromotionResolver._metadata(
            data["data"]["Catalog"]["searchStore"]["elements"][0]
        )
        self.assertNotIn("original_price", result)


class StateTests(unittest.TestCase):
    def test_state_preserves_recent_insertion_order(self):
        with tempfile.TemporaryDirectory() as d:
            store = StateStore(d + "/state.json", 2)
            store.save({"old", "new"})
            store.save({"new", "latest"})
            self.assertEqual(store.load(), {"new", "latest"})


class CoreStateTests(unittest.TestCase):
    def test_game_key_and_legacy_article_key(self):
        game = Game(name="Example", link="https://store.steampowered.com/app/1/")
        key = StateStore.game_key(game)
        self.assertTrue(key.startswith("game|"))
        values = {key}
        self.assertTrue(
            StateStore.is_game_processed(
                values, "https://example.com/article", game
            )
        )
        values = {StateStore.article_key("https://example.com/article")}
        self.assertTrue(
            StateStore.is_article_processed(
                values, "https://example.com/article"
            )
        )

    def test_same_game_is_deduplicated_across_articles(self):
        game = Game(
            name="Example Game",
            link="https://store.steampowered.com/app/1/",
        )
        values = {StateStore.game_key(game)}
        self.assertTrue(
            StateStore.is_game_processed(
                values, "https://example.com/another-article", game
            )
        )

    def test_different_games_are_not_deduplicated(self):
        game = Game(
            name="Example Game",
            link="https://store.steampowered.com/app/1/",
        )
        other = Game(
            name="Another Game",
            link="https://store.steampowered.com/app/2/",
        )
        values = {StateStore.game_key(game)}
        self.assertFalse(
            StateStore.is_game_processed(
                values, "https://example.com/article", other
            )
        )


class DiscordTests(unittest.TestCase):
    def test_format_deadline_uses_taiwan_timezone_timestamp(self):
        formatted = format_deadline("2026-11-03T00:00:00+08:00")
        self.assertTrue(formatted.startswith("2026 年 11 月 3 日（週二） 00:00"))
        self.assertIn("（約 ", formatted)

    def test_date_without_time_is_not_guessed(self):
        self.assertEqual(format_deadline("2026年11月3日"), "2026年11月3日")

    def _send(self, game):
        class FakeHttp:
            def post_json(self, url, payload):
                self.url = url
                self.payload = payload
                return 204, b"", {}

        http = FakeHttp()
        DiscordSender(http, "https://discord.example/webhook").send(
            game, "Article", "https://example.com/article"
        )
        return http

    def test_sender_uses_simplified_embed_layout(self):
        game = Game(
            name="Example",
            platform="Steam",
            deadline="2026年11月3日 0點前",
            genre="生態模擬",
            rating="None",
            brief="建立並維持一個完整的生態系統。",
            link="https://store.steampowered.com/app/1/",
            image="https://example.com/image.jpg",
            steam_price="",
            original_price="$52",
        )

        embed = self._send(game).payload["embeds"][0]
        self.assertEqual(embed["title"], "Example")
        self.assertEqual(embed["url"], game.link)
        self.assertIn("💰 **原價**　~~US$52.00（約 NT$1,638）~~ 免費", embed["description"])
        self.assertIn("⏳ **期限**　2026 年 11 月 3 日（週二） 00:00", embed["description"])
        self.assertIn("🎮 **平台**　Steam", embed["description"])
        self.assertIn("🧩 **遊戲類型**　生態模擬", embed["description"])
        self.assertIn("📝 **介紹**　建立並維持一個完整的生態系統。", embed["description"])
        self.assertIn("⭐ **玩家評價**　暫無資料", embed["description"])
        self.assertEqual(embed["image"]["url"], game.image)
        self.assertEqual(embed["footer"]["text"], "Free Game Notifier")
        self.assertNotIn("fields", embed)
        self.assertEqual(embed["color"], 0x57F287)

    def test_sender_adds_two_link_buttons(self):
        game = Game(
            name="Example",
            link="https://store.steampowered.com/app/1/",
        )

        http = self._send(game)
        self.assertEqual(http.url, "https://discord.example/webhook?with_components=true")
        buttons = http.payload["components"][0]["components"]
        self.assertEqual(len(buttons), 2)
        self.assertEqual(buttons[0]["label"], "4Gamers")
        self.assertEqual(buttons[0]["emoji"], {"name": "🔗"})
        self.assertEqual(buttons[0]["url"], "https://example.com/article")
        self.assertEqual(buttons[0]["style"], 5)
        self.assertEqual(buttons[1]["label"], "商店頁")
        self.assertEqual(buttons[1]["emoji"], {"name": "🛒"})
        self.assertEqual(buttons[1]["url"], game.link)
        self.assertEqual(buttons[1]["style"], 5)

    def test_sender_disables_mentions(self):
        game = Game(name="Example", link="https://store.steampowered.com/app/1/")
        payload = self._send(game).payload
        self.assertEqual(payload["allowed_mentions"], {"parse": []})


class AITests(unittest.TestCase):
    def test_markdown_json_fence_is_removed(self):
        from free_game.ai import GeminiExtractor

        class FakeHttp:
            def post_json(self, url, payload, timeout=45, headers=None):
                body = json.dumps({
                    "candidates": [{"content": {"parts": [{
                        "text": "```json\n[{\"name\":\"Example\",\"store_index\":1}]\n```"
                    }]}}]
                }).encode()
                return 200, body, {}

        article = parse_article(
            b'<html><body><a href="https://store.steampowered.com/app/1/">Example</a></body></html>',
            "https://example.com/article", "Example",
        )
        games = GeminiExtractor(FakeHttp(), "key", "gemini-test").extract(article)
        self.assertEqual(games[0].name, "Example")

    def test_store_index_maps_to_candidate_url(self):
        from free_game.ai import GeminiExtractor

        class FakeHttp:
            def post_json(self, url, payload, timeout=45, headers=None):
                body = json.dumps({
                    "candidates": [{"content": {"parts": [{
                        "text": "[{\"name\":\"Example\",\"original_price\":\"$52\",\"deadline\":\"2026-11-03T00:00:00+08:00\",\"store_index\":2}]"
                    }]}}]
                }).encode()
                return 200, body, {}

        article = parse_article(
            b'<html><body>'
            b'<a href="https://store.steampowered.com/app/1/">One</a>'
            b'<a href="https://store.epicgames.com/p/example">Example</a>'
            b'</body></html>',
            "https://example.com/article", "Example",
        )
        games = GeminiExtractor(FakeHttp(), "key", "gemini-test").extract(article)
        self.assertEqual(games[0].link, "https://store.epicgames.com/p/example")
        self.assertEqual(games[0].original_price, "")
        self.assertEqual(games[0].deadline, "")

    def test_invalid_store_link_is_rejected(self):
        from free_game.ai import GeminiExtractor

        class FakeHttp:
            def post_json(self, url, payload, timeout=45, headers=None):
                body = json.dumps({
                    "candidates": [{"content": {"parts": [{
                        "text": "[{\"name\":\"Example\",\"store_index\":99}]"
                    }]}}]
                }).encode()
                return 200, body, {}

        article = parse_article(
            b'<html><body><a href="https://store.steampowered.com/app/1/">Example</a></body></html>',
            "https://example.com/article", "Example",
        )
        self.assertEqual(
            GeminiExtractor(FakeHttp(), "key", "gemini-test").extract(article),
            [],
        )

if __name__ == "__main__":
    unittest.main()
