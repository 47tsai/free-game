import json
from datetime import datetime, timezone

from free_game.adapters.base import NormalizedCandidate
from free_game.verification import EpicPromotionVerifier


def candidate(url="https://store.epicgames.com/p/example-game"):
    return NormalizedCandidate(
        source_key="4gamers:latest-news",
        platform="epic",
        external_product_id="example-game",
        title="Example Game",
        product_url=url,
        observed_at=datetime(2026, 11, 4, tzinfo=timezone.utc),
        source_external_id="article-1:abc",
    )


def payload(*, active=True, discount=0, slug="example-game", end="2026-11-10T00:00:00Z"):
    promotions = {
        "promotionalOffers": [{
            "promotionalOffers": [{
                "startDate": "2026-11-01T00:00:00Z",
                "endDate": end,
            }]
        }] if active else [],
        "upcomingPromotionalOffers": [],
    }
    return json.dumps({
        "data": {"Catalog": {"searchStore": {"elements": [{
            "productSlug": slug,
            "price": {"totalPrice": {"originalPrice": 1999, "discountPrice": discount}},
            "promotions": promotions,
        }]}}}
    })


def test_verifies_exact_epic_product_with_active_zero_price_offer() -> None:
    result = EpicPromotionVerifier().verify(
        candidate(), payload(), now=datetime(2026, 11, 4, tzinfo=timezone.utc)
    )

    assert result.status == "verified"
    assert result.reason == "epic_exact_product_active_zero_price"
    assert result.region == "TW"
    assert result.ends_at == datetime(2026, 11, 10, tzinfo=timezone.utc)


def test_does_not_match_a_different_epic_product() -> None:
    result = EpicPromotionVerifier().verify(candidate(), payload(slug="another-game"))

    assert result.status == "needs_review"
    assert result.reason == "epic_exact_product_not_found"


def test_rejects_active_epic_offer_that_is_not_free() -> None:
    result = EpicPromotionVerifier().verify(candidate(), payload(discount=999))

    assert result.status == "rejected"
    assert result.reason == "epic_active_offer_not_free"


def test_rejects_expired_epic_offer() -> None:
    result = EpicPromotionVerifier().verify(
        candidate(), payload(end="2026-11-03T00:00:00Z"),
        now=datetime(2026, 11, 4, tzinfo=timezone.utc),
    )

    assert result.status == "rejected"
    assert result.reason == "epic_offer_expired"


def test_upcoming_epic_offer_is_not_verified_as_active() -> None:
    doc = json.loads(payload(active=False))
    doc["data"]["Catalog"]["searchStore"]["elements"][0]["promotions"]["upcomingPromotionalOffers"] = [{}]
    result = EpicPromotionVerifier().verify(candidate(), json.dumps(doc))

    assert result.status == "needs_review"
    assert result.reason == "epic_offer_not_active_yet"


def test_malformed_or_wrong_url_remains_for_review() -> None:
    verifier = EpicPromotionVerifier()
    assert verifier.verify(candidate(), "not-json").status == "needs_review"
    assert verifier.verify(candidate("https://example.com/p/example-game"), "{}").status == "needs_review"


def test_future_epic_promotion_is_not_verified_early() -> None:
    doc = json.loads(payload())
    doc["data"]["Catalog"]["searchStore"]["elements"][0]["promotions"]["promotionalOffers"][0]["promotionalOffers"][0]["startDate"] = "2026-11-05T00:00:00Z"
    result = EpicPromotionVerifier().verify(
        candidate(), json.dumps(doc),
        now=datetime(2026, 11, 4, tzinfo=timezone.utc),
    )

    assert result.status == "needs_review"
    assert result.reason == "epic_offer_not_active_yet"
