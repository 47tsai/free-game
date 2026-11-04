from __future__ import annotations

from free_game.adapters.fourgamers import FourGamersAdapter


RSS = b"""<?xml version="1.0"?>
<rss version="2.0"><channel>
  <item><title>Steam 限時免費遊戲《Example》</title><link>https://www.4gamers.com.tw/news/detail/123</link><guid>article-123</guid><description>限免至本週末</description></item>
  <item><title>新遊戲上市消息</title><link>https://www.4gamers.com.tw/news/detail/456</link><guid>article-456</guid><description>遊戲上市資訊</description></item>
  <item><title>紳士限免情報</title><link>https://www.4gamers.com.tw/news/detail/789</link><guid>article-789</guid><description>本週限免</description></item>
</channel></rss>"""


def test_only_free_game_articles_are_selected() -> None:
    adapter = FourGamersAdapter("https://www.4gamers.com.tw/rss/latest-news")
    observations = adapter.parse(RSS)

    assert [item.external_id for item in observations] == ["article-123", "article-789"]


def test_selected_articles_become_unverified_discovery_candidates() -> None:
    adapter = FourGamersAdapter("https://www.4gamers.com.tw/rss/latest-news")
    observations = adapter.parse(RSS)
    candidates = adapter.normalize(observations)

    assert len(candidates) == 2
    assert candidates[0].title == "Steam 限時免費遊戲《Example》"
    assert candidates[0].product_url == "https://www.4gamers.com.tw/news/detail/123"
    assert candidates[0].platform is None
    assert candidates[0].verification_status == "candidate"
