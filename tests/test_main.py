import os
import tempfile
import unittest

os.environ.setdefault("DISCORD_WEBHOOK_URL", "https://discord.example/webhook")
os.environ.setdefault("GEMINI_API_KEY", "test-key")

from free_game.models import Article, Game
from free_game.state import StateStore
from main import process_article, select_articles


class MainFlowTests(unittest.TestCase):
    def setUp(self):
        self.article = Article(title="Free Game", url="https://example.com/article")
        self.games = [
            Game(name="First", link="https://store.steampowered.com/app/1/"),
            Game(name="Second", link="https://store.steampowered.com/app/2/"),
        ]

    def test_backfill_article_is_selected_when_missing_from_rss(self):
        with tempfile.TemporaryDirectory() as d:
            state = StateStore(d + "/state.json", 100)
            processed = state.load()
            selected = select_articles([], state, processed, (self.article,))
            self.assertEqual([item.url for item in selected], [self.article.url])

    def test_processed_backfill_article_is_not_selected_again(self):
        with tempfile.TemporaryDirectory() as d:
            state = StateStore(d + "/state.json", 100)
            processed = {state.article_key(self.article.url)}
            selected = select_articles([], state, processed, (self.article,))
            self.assertEqual(selected, [])

    def test_empty_extraction_does_not_mark_article_processed(self):
        class FakeHttp:
            def get(self, url):
                return b"<html><body>Example</body></html>", {}

        class FakeAI:
            def extract(self, article):
                return []

        class FakeSteam:
            def resolve(self, name, link):
                return ""

        class FakeDiscord:
            def send(self, game, article_title, article_url):
                pass

        with tempfile.TemporaryDirectory() as d:
            state = StateStore(d + "/state.json", 100)
            processed = state.load()
            success = process_article(
                self.article, FakeHttp(), state, FakeAI(), FakeDiscord(),
                FakeSteam(), processed,
            )
            self.assertTrue(success)
            self.assertNotIn(state.article_key(self.article.url), processed)

    def test_partial_failure_keeps_successful_game(self):
        class FakeHttp:
            def get(self, url):
                return b"<html><body>Example</body></html>", {}

        games = self.games

        class FakeAI:
            def extract(self, article):
                return games

        class FakeSteam:
            def resolve(self, name, link):
                return ""

        class FakeDiscord:
            def __init__(self):
                self.sent = []

            def send(self, game, article_title, article_url):
                if game.name == "Second":
                    raise RuntimeError("discord failed")
                self.sent.append(game.name)

        with tempfile.TemporaryDirectory() as d:
            state = StateStore(d + "/state.json", 100)
            processed = state.load()
            discord = FakeDiscord()
            success = process_article(
                self.article, FakeHttp(), state, FakeAI(), discord,
                FakeSteam(), processed,
            )
            first_key = state.game_key(self.games[0])
            article_key = state.article_key(self.article.url)
            self.assertFalse(success)
            self.assertEqual(discord.sent, ["First"])
            self.assertIn(first_key, processed)
            self.assertNotIn(article_key, processed)

    def test_successful_article_gets_article_key(self):
        class FakeHttp:
            def get(self, url):
                return b"<html><body>Example</body></html>", {}

        games = self.games

        class FakeAI:
            def extract(self, article):
                return [games[0]]

        class FakeSteam:
            def resolve(self, name, link):
                return ""

        class FakeDiscord:
            def send(self, game, article_title, article_url):
                pass

        with tempfile.TemporaryDirectory() as d:
            state = StateStore(d + "/state.json", 100)
            processed = state.load()
            success = process_article(
                self.article, FakeHttp(), state, FakeAI(), FakeDiscord(),
                FakeSteam(), processed,
            )
            self.assertTrue(success)
            self.assertIn(state.article_key(self.article.url), processed)


if __name__ == "__main__":
    unittest.main()
