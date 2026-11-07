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


def test_article_without_store_link_is_not_a_game_candidate():
    html = '<html><head><meta property="og:image" content="https://cdn.example.com/cover.jpg"></head><body>No storefront link</body></html>'
    analyzer = FourGamersArticleAnalyzer()
    result = analyzer.analyze(observation(), html)
    assert result == ()
    assert analyzer.diagnostics(observation(), html) == {
        "html_bytes": len(html.encode("utf-8")),
        "external_links_found": 0,
        "storefront_links_found": 0,
        "raw_storefront_domain_mentions": 0,
        "href_attributes_found": 0,
        "body_tag_present": True,
        "anchor_tags_seen": 0,
        "anchor_tags_with_href": 0,
        "anchor_tags_skipped_by_context": 0,
        "max_skip_depth": 0,
        "active_skip_tags": "",
        "skipped_anchor_contexts": "",
    }


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



def test_extracts_slash_date_and_24_hour_clock_deadline():
    html = """
    <html><body>
      <p>免費領取期限至 11/10 23:59。</p>
      <a href="https://store.steampowered.com/app/12345/example/">Example Game</a>
    </body></html>
    """
    result = FourGamersArticleAnalyzer().analyze(observation(), html)

    assert len(result) == 1
    assert result[0].offer_end_at.isoformat() == "2026-11-10T23:59:00+08:00"


def test_extracts_chinese_date_with_colon_clock():
    html = """
    <html><body>
      <p>領取截止至 2026 年 11 月 10 日 21:30。</p>
      <a href="https://store.steampowered.com/app/12345/example/">Example Game</a>
    </body></html>
    """
    result = FourGamersArticleAnalyzer().analyze(observation(), html)

    assert len(result) == 1
    assert result[0].offer_end_at.isoformat() == "2026-11-10T21:30:00+08:00"


def test_does_not_treat_bare_number_after_date_as_clock():
    html = """
    <html><body>
      <p>免費領取期限至 11 月 10 日，活動編號 21。</p>
      <a href="https://store.steampowered.com/app/12345/example/">Example Game</a>
    </body></html>
    """
    result = FourGamersArticleAnalyzer().analyze(observation(), html)

    assert len(result) == 1
    assert result[0].offer_end_at is None

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



def test_diagnostics_report_anchors_inside_unclosed_svg_context():
    html = """
    <html><body>
      <svg>
      <a href="https://store.epicgames.com/p/example">Example Game</a>
    </body></html>
    """
    diagnostics = FourGamersArticleAnalyzer().diagnostics(observation(), html)

    assert diagnostics["anchor_tags_seen"] == 1
    assert diagnostics["anchor_tags_with_href"] == 1
    assert diagnostics["anchor_tags_skipped_by_context"] == 1
    assert diagnostics["max_skip_depth"] == 1
    assert diagnostics["active_skip_tags"] == "svg"
    assert diagnostics["skipped_anchor_contexts"] == "svg:1"
    assert diagnostics["external_links_found"] == 0
