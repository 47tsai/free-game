from datetime import datetime, timezone
from zoneinfo import ZoneInfo
import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from .models import Game


def clip(value, n):
    value = str(value or "").strip()
    return value if len(value) <= n else value[: n - 1] + "…"


def format_deadline(value):
    value = str(value or "").strip()
    if not value:
        return "期限未提供"

    parsed = None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        # Fallback for Chinese dates such as 2026年11月3日 0點前.
        match = re.search(
            r"(\d{4})年\s*(\d{1,2})月\s*(\d{1,2})日"
            r"(?:\s*(\d{1,2})\s*(?:點|時)(?:\s*(\d{1,2})分?)?)?",
            value,
        )
        if match and match.group(4) is not None:
            year, month, day = map(int, match.group(1, 2, 3))
            hour = int(match.group(4) or 0)
            minute = int(match.group(5) or 0)
            try:
                parsed = datetime(year, month, day, hour, minute, tzinfo=ZoneInfo("Asia/Taipei"))
            except ValueError:
                pass

    if parsed is None:
        return value
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=ZoneInfo("Asia/Taipei"))
    timestamp = int(parsed.timestamp())
    return f"<t:{timestamp}:F> (<t:{timestamp}:R>)"


def enable_components(url):
    parts = urlsplit(url)
    query = parse_qsl(parts.query, keep_blank_values=True)
    query.append(("with_components", "true"))
    return urlunsplit(
        (parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment)
    )


class DiscordSender:
    def __init__(self, http, webhook):
        self.http, self.webhook = http, webhook

    def send(self, game, article_title, article_url):
        original_price = game.original_price or game.steam_price
        price_text = f"~~{clip(original_price, 180)}~~ Free" if original_price and original_price != "免費" else "原價未查到"
        deadline = format_deadline(game.deadline)
        platform = game.platform or "未知"
        genre = game.genre or "未知"
        brief = game.brief or "限時免費活動"
        rating = game.rating or "None"

        description = (
            f"💰 **原價**　{price_text}\n"
            f"⏳ **期限**　{clip(deadline, 200)}\n"
            f"🎮 **平台**　{clip(platform, 200)}\n"
            f"🧩 **遊戲類型**　{clip(genre, 200)}\n"
            f"📝 **介紹**　{clip(brief, 80)}\n"
            f"⭐ **玩家評價**　{clip(rating, 300)}"
        )

        embed = {
            "title": clip(game.name, 256),
            "url": game.link,
            "description": clip(description, 4096),
            "color": 0x57F287,
            "footer": {"text": "Free Game Notifier"},
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        if game.image:
            embed["image"] = {"url": game.image}

        payload = {
            "allowed_mentions": {"parse": []},
            "embeds": [embed],
            "components": [
                {
                    "type": 1,
                    "components": [
                        {
                            "type": 2,
                            "style": 5,
                            "label": "4Gamers",
                            "emoji": {"name": "🔗"},
                            "url": article_url,
                        },
                        {
                            "type": 2,
                            "style": 5,
                            "label": "商店頁",
                            "emoji": {"name": "🛒"},
                            "url": game.link,
                        },
                    ],
                }
            ],
        }

        self.http.post_json(enable_components(self.webhook), payload)
