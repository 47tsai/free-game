"""Discord notifications for new games, claim changes, and 24-hour reminders."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse
from urllib.request import Request, urlopen

from free_game.writer import GitHubJsonWriter, _stable_id


class DiscordDeliveryError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class NotificationSummary:
    sent: int
    skipped: int
    failed: int
    status: str


class DiscordWebhookSender:
    def __init__(self, webhook_url: str, *, timeout_seconds: float = 20.0) -> None:
        parsed = urlparse(webhook_url)
        if parsed.scheme != "https" or parsed.hostname not in {"discord.com", "discordapp.com"} or not parsed.path.startswith("/api/webhooks/"):
            raise ValueError("discord_webhook_url_invalid")
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds_must_be_positive")
        query = parse_qsl(parsed.query, keep_blank_values=True)
        query.extend((("wait", "true"), ("with_components", "true")))
        self.webhook_url = urlunparse(parsed._replace(query=urlencode(query)))
        self.timeout_seconds = timeout_seconds

    def send_game(self, game: dict, kind: str) -> None:
        title = str(game.get("title") or "免費遊戲")[:256]
        claimed = game.get("claim_status") == "claimed"
        if kind == "new":
            description = f"**平台**　{game.get('platform') or '未知'}\n**領取狀態**　{'已領取' if claimed else '尚未領取'}"
            deadline = _parse_time(game.get("offer_end_at"))
            if deadline:
                local_deadline = deadline.astimezone(timezone(timedelta(hours=8)))
                description += "\n**領取期限**　" + local_deadline.strftime("%Y/%m/%d %H:%M") + "（台灣時間）"
            color = 0x2ECC71 if claimed else 0x5865F2
        elif kind == "claimed":
            description = f"**{title}** 已領取。"
            color = 0x2ECC71
        else:
            description = f"**{title}** 尚未領取，已加入超過 24 小時。"
            color = 0xF1C40F
        embed = {"title": title, "description": description, "color": color, "footer": {"text": "Free Game"}, "timestamp": datetime.now(timezone.utc).isoformat()}
        if kind == "new" and game.get("cover_image_url"):
            embed["image"] = {"url": game["cover_image_url"]}
        buttons = []
        for label, url in (("📰 文章", game.get("article_url")), ("🌐 網站", f"https://fg.chi.qzz.io/?game={game.get('id', '')}"), ("🎮 領取", game.get("store_url"))):
            if isinstance(url, str) and url.startswith("https://"):
                buttons.append({"type": 2, "style": 5, "label": label, "url": url})
        payload = {"allowed_mentions": {"parse": []}, "embeds": [embed]}
        if kind == "new" and buttons:
            payload["components"] = [{"type": 1, "components": buttons}]
        request = Request(self.webhook_url, data=json.dumps(payload, ensure_ascii=False).encode("utf-8"), method="POST", headers={"Content-Type": "application/json", "User-Agent": "FreeGameAggregator/0.1"})
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                if response.status < 200 or response.status >= 300:
                    raise DiscordDeliveryError(f"discord_http_{response.status}")
        except HTTPError as exc:
            raise DiscordDeliveryError(f"discord_http_{exc.code}") from None
        except URLError:
            raise DiscordDeliveryError("discord_network_error") from None


class DiscordNotificationService:
    def __init__(self, writer: GitHubJsonWriter, sender: DiscordWebhookSender) -> None:
        self.writer = writer
        self.sender = sender

    def process_games(self, *, now: datetime | None = None) -> NotificationSummary:
        current = now or datetime.now(timezone.utc)
        games = self.writer.store.read(GitHubJsonWriter.GAMES_PATH).document.get("records")
        notifications = self.writer.store.read(GitHubJsonWriter.NOTIFICATIONS_PATH).document.get("records")
        if not isinstance(games, list) or not isinstance(notifications, list):
            raise ValueError("game_or_notification_records_invalid")
        notification_by_key = {item.get("idempotency_key"): item for item in notifications if isinstance(item, dict)}
        known = set(notification_by_key)
        sent = skipped = failed = 0

        def deliver(game: dict, kind: str, key: str, notification_type: str) -> bool:
            nonlocal sent, skipped, failed
            if key in known:
                skipped += 1
                return False
            record = {"id": _stable_id("notification", game["id"], key), "game_id": game["id"], "notification_type": notification_type, "channel": "discord", "idempotency_key": key, "status": "pending", "attempt_count": 1, "created_at": current.isoformat().replace("+00:00", "Z"), "sent_at": None, "last_error": None}
            self.writer.write_notification(record)
            known.add(key)
            notification_by_key[key] = record
            try:
                self.sender.send_game(game, kind)
            except Exception as exc:
                record["status"] = "failed"
                record["last_error"] = str(exc)[:200] if isinstance(exc, DiscordDeliveryError) else "discord_delivery_outcome_unknown"
                self.writer.write_notification(record)
                notification_by_key[key] = record
                failed += 1
                return False
            record["status"] = "sent"
            record["sent_at"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
            self.writer.write_notification(record)
            notification_by_key[key] = record
            sent += 1
            return True

        for game in games:
            if not isinstance(game, dict) or not game.get("article_url"):
                continue
            game_id = game.get("id")
            if not isinstance(game_id, str):
                continue
            new_key = f"new_game:{game_id}:discord"
            was_announced = notification_by_key.get(new_key, {}).get("status") == "sent"
            sent_new_now = False
            if not was_announced and new_key not in known:
                sent_new_now = deliver(game, "new", new_key, "new_offer")
            if game.get("claim_notification_pending"):
                if was_announced:
                    claim_key = f"claimed:{game_id}:{game.get('claimed_at') or 'claimed'}:discord"
                    claim_sent = notification_by_key.get(claim_key, {}).get("status") == "sent"
                    if not claim_sent and claim_key not in known:
                        claim_sent = deliver(game, "claimed", claim_key, "offer_updated")
                    if claim_sent:
                        self.writer.update_game(game_id, {"claim_notification_pending": False})
                elif sent_new_now:
                    self.writer.update_game(game_id, {"claim_notification_pending": False})
            if game.get("claim_status", "unclaimed") != "claimed":
                added = _parse_time(game.get("added_at") or game.get("created_at"))
                last = _parse_time(game.get("reminder_last_sent_at"))
                if added and current >= added + timedelta(hours=24) and (last is None or current >= last + timedelta(hours=24)):
                    reminder_number = int((current - added).total_seconds() // 86400)
                    key = f"reminder:{game_id}:{reminder_number}:discord"
                    if deliver(game, "reminder", key, "deadline_reminder"):
                        self.writer.update_game(game_id, {"reminder_last_sent_at": current.isoformat().replace("+00:00", "Z")})
        return NotificationSummary(sent, skipped, failed, "success" if not failed else "partial_failure")


def _parse_time(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.astimezone(timezone.utc) if parsed.tzinfo else None
