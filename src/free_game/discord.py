from datetime import datetime, timezone
from zoneinfo import ZoneInfo
import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from .models import Game


TAIPEI = ZoneInfo("Asia/Taipei")
WEEKDAYS_ZH = ("週一", "週二", "週三", "週四", "週五", "週六", "週日")
USD_TO_TWD_ESTIMATE = 31.5


def clip(value, n):
    value = str(value or "").strip()
    return value if len(value) <= n else value[: n - 1] + "…"


def format_price(value):
    """Show an estimated TWD equivalent for USD prices and localize the free label."""
    value = str(value or "").strip()
    if not value:
        return "原價未查到"
    if value in ("免費", "Free"):
        return "免費"

    match = re.fullmatch(r"(?:US)?\$\s*([\d,]+(?:\.\d{1,2})?)", value, re.IGNORECASE)
    if match:
        usd = float(match.group(1).replace(",", ""))
        twd = round(usd * USD_TO_TWD_ESTIMATE)
        return f"~~US${usd:.2f}（約 NT${twd:,}）~~ 免費"

    return f"~~{clip(value, 180)}~~ 免費"


def format_deadline(value, now=None):
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
                parsed = datetime(year, month, day, hour, minute, tzinfo=TAIPEI)
            except ValueError:
                pass

    if parsed is None:
        return value
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=TAIPEI)
    local_deadline = parsed.astimezone(TAIPEI)
    date_text = (
        f"{local_deadline.year} 年 {local_deadline.month} 月 {local_deadline.day} 日"
        f"（{WEEKDAYS_ZH[local_deadline.weekday()]}） {local_deadline:%H:%M}"
    )

    current = now or datetime.now(TAIPEI)
    if current.tzinfo is None:
        current = current.replace(tzinfo=TAIPEI)
    seconds = int((local_deadline - current.astimezone(TAIPEI)).total_seconds())
    if seconds <= 0:
        relative = "（已截止）"
    elif seconds >= 86400:
        days = seconds // 86400
        relative = f"（約 {days} 天後）"
    else:
        hours = max(1, (seconds + 3599) // 3600)
        relative = f"（約 {hours} 小時後）"
    return f"{date_text}{relative}"


def enable_components(url):
    parts = urlsplit(url)
    query = parse_qsl(parts.query, keep_blank_values=True)
    query.append(("with_components", "true"))
    query.append(("wait", "true"))
    return urlunsplit(
        (parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment)
    )


class DiscordSender:
    def __init__(self, http, webhook):
        self.http, self.webhook = http, webhook

    def send(self, game, article_title, article_url):
        original_price = game.original_price or game.steam_price
        price_text = format_price(original_price)
        deadline = format_deadline(game.deadline)
        platform = game.platform or "未知"
        genre = game.genre or "未知"
        brief = game.brief or "限時免費活動"
        rating = game.rating or "暫無資料"
        if rating.strip().lower() in ("none", "null", "n/a", "na", "-"):
            rating = "暫無資料"

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

        self.http.post_json(
            enable_components(self.webhook),
            payload,
            # Discord may have accepted a message even if the response is lost.
            # Retry only explicit rate-limit rejection, never ambiguous transport
            # failures or 5xx responses that could produce duplicate messages.
            retry_status={429},
            retry_transport_errors=False,
        )
