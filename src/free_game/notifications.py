"""Idempotent Discord delivery for newly verified active offers."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse
from urllib.request import Request, urlopen

from free_game.writer import GitHubJsonWriter, _stable_id


class DiscordDeliveryError(RuntimeError):
    """Safe Discord delivery failure without leaking the webhook URL."""


@dataclass(frozen=True, slots=True)
class NotificationSummary:
    sent: int
    skipped: int
    failed: int
    status: str


class DiscordWebhookSender:
    """Send a single Discord embed through a configured webhook."""

    def __init__(self, webhook_url: str, *, timeout_seconds: float = 20.0) -> None:
        parsed = urlparse(webhook_url)
        if (
            parsed.scheme != "https"
            or parsed.hostname not in {"discord.com", "discordapp.com"}
            or not parsed.path.startswith("/api/webhooks/")
        ):
            raise ValueError("discord_webhook_url_invalid")
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds_must_be_positive")
        query = parse_qsl(parsed.query, keep_blank_values=True)
        query.append(("wait", "true"))
        self.webhook_url = urlunparse(parsed._replace(query=urlencode(query)))
        self.timeout_seconds = timeout_seconds

    def send_offer(self, offer: dict) -> None:
        embed = {
            "title": str(offer.get("title") or "免費遊戲")[:256],
            "url": offer.get("claim_url"),
            "description": f"**平台**　{str(offer.get('platform') or '未知')[:100]}",
            "color": 0x5865F2,
            "footer": {"text": "Free Game"},
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        fields = []
        if offer.get("region"):
            fields.append({"name": "地區", "value": str(offer["region"])[:100], "inline": True})
        if offer.get("ends_at"):
            fields.append({"name": "領取期限", "value": str(offer["ends_at"]), "inline": True})
        if fields:
            embed["fields"] = fields
        payload = json.dumps({
            "allowed_mentions": {"parse": []},
            "embeds": [embed],
        }, ensure_ascii=False).encode("utf-8")
        request = Request(
            self.webhook_url,
            data=payload,
            method="POST",
            headers={
                "Content-Type": "application/json",
                "User-Agent": "FreeGameAggregator/0.1",
            },
        )
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                if response.status < 200 or response.status >= 300:
                    raise DiscordDeliveryError(f"discord_http_{response.status}")
        except HTTPError as exc:
            raise DiscordDeliveryError(f"discord_http_{exc.code}") from None
        except URLError:
            raise DiscordDeliveryError("discord_network_error") from None


class DiscordNotificationService:
    """Queue before sending, then persist the delivery result.

    A pending or failed idempotency key is not sent again automatically. This
    deliberately favors avoiding duplicate posts when a delivery outcome is
    ambiguous, including a process crash after Discord accepted the request.
    """

    def __init__(self, writer: GitHubJsonWriter, sender: DiscordWebhookSender) -> None:
        self.writer = writer
        self.sender = sender

    def send_new_active_offers(self) -> NotificationSummary:
        offers = self.writer.store.read(GitHubJsonWriter.OFFERS_PATH).document.get("records")
        notifications = self.writer.store.read(GitHubJsonWriter.NOTIFICATIONS_PATH).document.get("records")
        if not isinstance(offers, list) or not isinstance(notifications, list):
            raise ValueError("catalog_or_notification_records_invalid")

        known_keys = {
            item.get("idempotency_key")
            for item in notifications
            if isinstance(item, dict)
        }
        sent = skipped = failed = 0
        for offer in offers:
            if not isinstance(offer, dict):
                continue
            if offer.get("verification_status") != "verified" or offer.get("status") != "active":
                continue
            offer_id = offer.get("id")
            if not isinstance(offer_id, str) or not offer_id:
                continue
            key = f"new_offer:{offer_id}:discord"
            if key in known_keys:
                skipped += 1
                continue

            now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
            notification_id = _stable_id("notification", offer_id, "new_offer", "discord")
            record = {
                "id": notification_id,
                "offer_id": offer_id,
                "notification_type": "new_offer",
                "channel": "discord",
                "idempotency_key": key,
                "status": "pending",
                "attempt_count": 1,
                "created_at": now,
                "sent_at": None,
                "last_error": None,
            }
            # Persist the idempotency key before the external side effect.
            self.writer.write_notification(record)
            known_keys.add(key)
            try:
                self.sender.send_offer(offer)
            except Exception as exc:
                record["status"] = "failed"
                record["last_error"] = (
                    str(exc) if isinstance(exc, DiscordDeliveryError)
                    else "discord_delivery_outcome_unknown"
                )[:200]
                self.writer.write_notification(record)
                failed += 1
                continue

            record["status"] = "sent"
            record["sent_at"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
            self.writer.write_notification(record)
            sent += 1

        return NotificationSummary(sent, skipped, failed, "success" if not failed else "partial_failure")
