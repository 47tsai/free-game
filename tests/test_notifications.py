from copy import deepcopy
from datetime import datetime, timezone, timedelta

from free_game.notifications import DiscordDeliveryError, DiscordNotificationService, DiscordWebhookSender
from free_game.writer import GitHubJsonWriter, StoredCollection


class MemoryStore:
    def __init__(self):
        self.documents = {
            GitHubJsonWriter.GAMES_PATH: {"schema_version": 1, "updated_at": "2026-11-04T00:00:00Z", "records": [{
                "id": "game_123", "title": "Example Game", "normalized_title": "example game",
                "platform": "steam", "external_product_id": "123", "store_url": "https://store.steampowered.com/app/123/",
                "article_url": "https://www.4gamers.com.tw/news/detail/123", "cover_image_url": "https://example.com/game.jpg",
                "claim_status": "unclaimed", "claimed_at": None, "claim_source": None,
                "claim_notification_pending": False, "added_at": "2026-11-01T00:00:00Z",
                "reminder_last_sent_at": None, "created_at": "2026-11-01T00:00:00Z", "updated_at": "2026-11-01T00:00:00Z"
            }]}
        }
        self.shas = {}
        self.counter = 0

    def read(self, path):
        return StoredCollection(deepcopy(self.documents.get(path, {"schema_version": 1, "updated_at": "2026-11-04T00:00:00Z", "records": []})), self.shas.get(path))

    def write(self, path, document, sha):
        self.counter += 1
        self.documents[path] = deepcopy(document)
        self.shas[path] = f"sha-{self.counter}"
        return self.shas[path]


class FakeSender:
    def __init__(self, error=None):
        self.calls = []
        self.error = error

    def send_game(self, game, kind):
        self.calls.append((game["id"], kind))
        if self.error:
            raise self.error


def test_sends_new_game_once_and_reminds_every_24_hours():
    store = MemoryStore()
    writer = GitHubJsonWriter(store)
    sender = FakeSender()
    service = DiscordNotificationService(writer, sender)
    now = datetime(2026, 11, 4, 1, tzinfo=timezone.utc)
    first = service.process_games(now=now)
    second = service.process_games(now=now + timedelta(hours=23))
    third = service.process_games(now=now + timedelta(hours=25))
    assert first.sent == 2  # new-game message and first overdue reminder
    assert second.sent == 0
    assert third.sent == 1
    assert sender.calls == [("game_123", "new"), ("game_123", "reminder"), ("game_123", "reminder")]
    records = store.documents[GitHubJsonWriter.NOTIFICATIONS_PATH]["records"]
    assert all(item["status"] == "sent" for item in records)


def test_claimed_game_sends_short_update_and_stops_reminders():
    store = MemoryStore()
    game = store.documents[GitHubJsonWriter.GAMES_PATH]["records"][0]
    game.update({"claim_status": "claimed", "claimed_at": "2026-11-04T00:00:00Z", "claim_notification_pending": True})
    sender = FakeSender()
    summary = DiscordNotificationService(GitHubJsonWriter(store), sender).process_games(now=datetime(2026, 11, 4, 2, tzinfo=timezone.utc))
    assert summary.sent == 1  # full new-game card already shows claimed
    assert sender.calls == [("game_123", "new")]
    assert store.documents[GitHubJsonWriter.GAMES_PATH]["records"][0]["claim_notification_pending"] is False


def test_delivery_failure_is_not_retried_automatically():
    store = MemoryStore()
    sender = FakeSender(DiscordDeliveryError("discord_network_error"))
    service = DiscordNotificationService(GitHubJsonWriter(store), sender)
    first = service.process_games(now=datetime(2026, 11, 4, 1, tzinfo=timezone.utc))
    second = service.process_games(now=datetime(2026, 11, 4, 1, tzinfo=timezone.utc))
    assert first.failed == 2
    assert second.sent == 0
    assert sender.calls == [("game_123", "new"), ("game_123", "reminder")]


def test_webhook_url_must_be_discord_https_endpoint():
    import pytest
    with pytest.raises(ValueError, match="discord_webhook_url_invalid"):
        DiscordWebhookSender("https://example.com/api/webhooks/123/token")
    sender = DiscordWebhookSender("https://discord.com/api/webhooks/123/token")
    assert "wait=true" in sender.webhook_url


def test_already_announced_game_sends_short_claimed_update_next_run():
    store = MemoryStore()
    writer = GitHubJsonWriter(store)
    sender = FakeSender()
    service = DiscordNotificationService(writer, sender)
    first = service.process_games(now=datetime(2026, 11, 4, 1, tzinfo=timezone.utc))
    assert first.sent == 2  # new-game embed and overdue reminder
    game = store.documents[writer.GAMES_PATH]["records"][0]
    writer.update_game(game["id"], {"claim_status": "claimed", "claimed_at": "2026-11-04T02:00:00Z", "claim_source": "manual", "claim_notification_pending": True})
    second = service.process_games(now=datetime(2026, 11, 4, 3, tzinfo=timezone.utc))
    assert second.sent == 1
    assert sender.calls[-1] == ("game_123", "claimed")
    updated = store.documents[writer.GAMES_PATH]["records"][0]
    assert updated["claim_notification_pending"] is False
