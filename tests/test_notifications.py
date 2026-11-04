from copy import deepcopy

from free_game.notifications import (
    DiscordDeliveryError,
    DiscordNotificationService,
    DiscordWebhookSender,
)
from free_game.writer import GitHubJsonWriter, StoredCollection


class MemoryStore:
    def __init__(self):
        self.documents = {
            GitHubJsonWriter.OFFERS_PATH: {
                "schema_version": 1,
                "updated_at": "2026-11-04T00:00:00Z",
                "records": [{
                    "id": "offer_123",
                    "product_id": "product_123",
                    "platform": "epic",
                    "source_record_ids": ["source_123"],
                    "title": "Example Game",
                    "claim_url": "https://store.epicgames.com/p/example",
                    "starts_at": None,
                    "ends_at": "2026-11-10T00:00:00Z",
                    "deadline_status": "known",
                    "status": "active",
                    "verification_status": "verified",
                    "region": "TW",
                    "terms": None,
                    "first_seen_at": "2026-11-04T00:00:00Z",
                    "last_seen_at": "2026-11-04T00:00:00Z",
                    "created_at": "2026-11-04T00:00:00Z",
                    "updated_at": "2026-11-04T00:00:00Z",
                }],
            }
        }
        self.shas = {}
        self.counter = 0

    def read(self, path):
        return StoredCollection(
            deepcopy(self.documents.get(path, {
                "schema_version": 1,
                "updated_at": "2026-11-04T00:00:00Z",
                "records": [],
            })),
            self.shas.get(path),
        )

    def write(self, path, document, sha):
        if self.shas.get(path) != sha:
            raise AssertionError("unexpected stale SHA in test store")
        self.counter += 1
        self.documents[path] = deepcopy(document)
        self.shas[path] = f"sha-{self.counter}"
        return self.shas[path]


class FakeSender:
    def __init__(self, error=None):
        self.calls = []
        self.error = error

    def send_offer(self, offer):
        self.calls.append(offer["id"])
        if self.error:
            raise self.error


def test_sends_each_verified_active_offer_only_once() -> None:
    store = MemoryStore()
    sender = FakeSender()
    service = DiscordNotificationService(GitHubJsonWriter(store), sender)

    first = service.send_new_active_offers()
    second = service.send_new_active_offers()

    assert first.sent == 1
    assert second.sent == 0
    assert second.skipped == 1
    assert sender.calls == ["offer_123"]
    notifications = store.documents[GitHubJsonWriter.NOTIFICATIONS_PATH]["records"]
    assert notifications[0]["status"] == "sent"
    assert notifications[0]["attempt_count"] == 1


def test_failed_or_ambiguous_delivery_is_not_resent_automatically() -> None:
    store = MemoryStore()
    sender = FakeSender(DiscordDeliveryError("discord_network_error"))
    service = DiscordNotificationService(GitHubJsonWriter(store), sender)

    first = service.send_new_active_offers()
    second = service.send_new_active_offers()

    assert first.failed == 1
    assert second.skipped == 1
    assert sender.calls == ["offer_123"]
    notifications = store.documents[GitHubJsonWriter.NOTIFICATIONS_PATH]["records"]
    assert notifications[0]["status"] == "failed"
    assert notifications[0]["last_error"] == "discord_network_error"


def test_inactive_or_unverified_offers_are_not_sent() -> None:
    store = MemoryStore()
    offer = store.documents[GitHubJsonWriter.OFFERS_PATH]["records"][0]
    offer["verification_status"] = "needs_review"
    sender = FakeSender()

    summary = DiscordNotificationService(
        GitHubJsonWriter(store), sender
    ).send_new_active_offers()

    assert summary.sent == 0
    assert sender.calls == []


def test_webhook_url_must_be_discord_https_endpoint() -> None:
    import pytest

    with pytest.raises(ValueError, match="discord_webhook_url_invalid"):
        DiscordWebhookSender("https://example.com/api/webhooks/123/token")

    sender = DiscordWebhookSender("https://discord.com/api/webhooks/123/token")
    assert "wait=true" in sender.webhook_url
