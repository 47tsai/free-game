from free_game.ai import GeminiExtractor
from free_game.article import parse_article
from free_game.config import (
    GEMINI_API_KEY,
    GEMINI_MODEL,
    MAX_PROCESSED,
    RSS_URL,
    STATE_FILE,
    USER_AGENT,
    WEBHOOK_URL,
)
from free_game.discord import DiscordSender
from free_game.http import HttpClient
from free_game.rss import is_free_game_article, parse_rss
from free_game.state import StateStore
from free_game.stores import SteamPriceResolver


def process_article(item, http, state, ai, discord, steam, processed):
    html, _ = http.get(item.url)
    article = parse_article(html, item.url, item.title, item.summary, item.published)
    games = ai.extract(article)

    article_failed = False
    seen_games = set()

    for game in games:
        key = state.game_key(game)
        if key in seen_games or state.is_game_processed(processed, item.url, game):
            continue
        seen_games.add(key)

        try:
            price = steam.resolve(game.name, game.link)
            original_price = game.original_price or price
            game = game.__class__(
                name=game.name, platform=game.platform, deadline=game.deadline,
                genre=game.genre, gameplay=game.gameplay, rating=game.rating,
                brief=game.brief, link=game.link, image=game.image,
                steam_price=price, original_price=original_price,
            )
            discord.send(game, article.title, article.url)
            processed.add(key)
        except Exception as exc:
            article_failed = True
            seen_games.discard(key)
            print(f"[ERROR] {item.url} | {game.name}: {exc}")

    if not article_failed:
        processed.add(state.article_key(item.url))
    return not article_failed


def main():
    http = HttpClient(USER_AGENT)
    state = StateStore(STATE_FILE, MAX_PROCESSED)
    processed = state.load()
    data, _ = http.get(RSS_URL)
    articles = [
        a for a in parse_rss(data)
        if is_free_game_article(a) and not state.is_article_processed(processed, a.url)
    ]
    ai = GeminiExtractor(http, GEMINI_API_KEY, GEMINI_MODEL)
    discord = DiscordSender(http, WEBHOOK_URL)
    steam = SteamPriceResolver(http)
    failures = 0

    for item in articles:
        try:
            if not process_article(item, http, state, ai, discord, steam, processed):
                failures += 1
        except Exception as exc:
            failures += 1
            print(f"[ERROR] {item.url}: {exc}")
        finally:
            # Persist partial progress. A state-write failure is fatal because it
            # can cause duplicate notifications on the next run.
            state.save(processed)

    if failures:
        raise RuntimeError(f"{failures} article(s) failed")


if __name__ == "__main__":
    main()
