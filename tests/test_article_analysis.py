from datetime import datetime, timezone

from free_game.adapters.base import SourceObservation
from free_game.article_analysis import FourGamersArticleAnalyzer


def observation(title="限時免費《Example Game》", url="https://www.4gamers.com.tw/news/detail/123"):
    return SourceObservation(
        source_key="4gamers:latest-news",
        external_id="article-123",
        observed_at=datetime(2026, 11, 4, tzinfo=timezone.utc),
        source_url=url,
        raw_title=title,
        raw_description="本週限免",
    )


def test_extracts_steam_product_from_article_anchor() -> None:
    html = """
    <html><body>
      <a href="https://store.steampowered.com/app/12345/example/">
        Example Game
      </a>
    </body></html>
    """
    result = FourGamersArticleAnalyzer().analyze(observation(), html)

    assert len(result) == 1
    assert result[0].platform == "steam"
    assert result[0].external_product_id == "12345"
    assert result[0].title == "Example Game"
    assert result[0].verification_status == "candidate"


def test_uses_single_quoted_headline_when_anchor_is_generic() -> None:
    html = '<html><body><a href="https://store.epicgames.com/p/example">立即領取</a></body></html>'
    result = FourGamersArticleAnalyzer().analyze(observation(), html)

    assert len(result) == 1
    assert result[0].platform == "epic"
    assert result[0].external_product_id == "example"
    assert result[0].title == "Example Game"


def test_ignores_non_store_links_and_duplicate_links() -> None:
    html = """
    <html><body>
      <a href="https://www.youtube.com/watch?v=trailer">Example Game</a>
      <a href="https://store.steampowered.com/app/12345/example/">Example Game</a>
      <a href="https://store.steampowered.com/app/12345/example/">Example Game</a>
    </body></html>
    """
    result = FourGamersArticleAnalyzer().analyze(observation(), html)

    assert len(result) == 1
    assert result[0].external_product_id == "12345"


def test_unresolved_store_product_id_remains_discovery_candidate() -> None:
    html = '<html><body><a href="https://store.steampowered.com/">Example Game</a></body></html>'
    result = FourGamersArticleAnalyzer().analyze(observation(), html)

    assert len(result) == 1
    assert result[0].platform is None
    assert result[0].external_product_id is None
    assert "store_product_id_unresolved" in result[0].warnings


def test_unknown_storefront_is_preserved_as_discovery_candidate() -> None:
    html = """
    <html><body>
      <a href="https://new-store.example/products/abc">Mystery Game</a>
      <a href="https://www.4gamers.com.tw/news/detail/other">Related article</a>
      <a href="https://www.youtube.com/watch?v=abc">Trailer</a>
    </body></html>
    """
    result = FourGamersArticleAnalyzer().analyze(observation(), html)

    assert len(result) == 1
    assert result[0].platform == "new-store.example"
    assert result[0].external_product_id == "abc"
    assert result[0].title == "Mystery Game"


def test_article_without_store_link_keeps_og_image_and_game_title():
    html = '<html><head><meta property="og:image" content="https://cdn.example.com/cover.jpg"></head><body>No storefront link</body></html>'
    result = FourGamersArticleAnalyzer().analyze(observation(), html)
    assert len(result) == 1
    assert result[0].title == "Example Game"
    assert result[0].article_url == observation().source_url
    assert result[0].image_url == "https://cdn.example.com/cover.jpg"


def test_extracts_explicit_taiwan_deadline_from_article_body():
    html = """
    <html><body>
      <p>《Example Game》現正開放免費領取，期限至台灣時間 11 月 10 日晚間 9 點為止。</p>
      <a href="https://store.steampowered.com/app/12345/example/">Example Game</a>
    </body></html>
    """
    result = FourGamersArticleAnalyzer().analyze(observation(), html)

    assert len(result) == 1
    assert result[0].offer_end_at.isoformat() == "2026-11-10T21:00:00+08:00"


def test_shared_deadline_is_applied_to_each_game_in_multi_game_article():
    html = """
    <html><body>
      <p>以下兩款遊戲皆可免費領取至台灣時間 11 月 10 日晚間 9 點。</p>
      <a href="https://store.steampowered.com/app/12345/one/">Game One</a>
      <a href="https://store.epicgames.com/p/game-two">Game Two</a>
    </body></html>
    """
    result = FourGamersArticleAnalyzer().analyze(observation(), html)

    assert len(result) == 2
    assert all(item.offer_end_at.isoformat() == "2026-11-10T21:00:00+08:00" for item in result)


def test_single_game_deadline_is_not_applied_to_other_games_in_same_article():
    html = """
    <html><body>
      <p>《Game One》免費領取至台灣時間 11 月 10 日晚間 9 點。</p>
      <a href="https://store.steampowered.com/app/12345/one/">Game One</a>
      <a href="https://store.epicgames.com/p/game-two">Game Two</a>
    </body></html>
    """
    result = FourGamersArticleAnalyzer().analyze(observation(), html)

    assert len(result) == 2
    assert all(item.offer_end_at is None for item in result)


def test_ambiguous_or_date_only_deadline_is_not_guessed():
    html = """
    <html><body>
      <p>遊戲 A 領取期限至 11 月 10 日，遊戲 B 領取期限至 11 月 12 日下午。</p>
      <a href="https://store.steampowered.com/app/12345/one/">Game One</a>
    </body></html>
    """
    result = FourGamersArticleAnalyzer().analyze(observation(), html)

    assert len(result) == 1
    assert result[0].offer_end_at is None
