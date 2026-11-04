from __future__ import annotations

import json

from free_game.steam_price import SteamAppDetailsAssessor, SteamPriceStatus


def response(app_id="12345", **data):
    payload = {
        "type": "game",
        "name": "Example Game",
        "steam_appid": int(app_id),
        "is_free": False,
    }
    payload.update(data)
    return json.dumps({
        app_id: {
            "success": True,
            "data": payload,
        }
    })


def test_zero_price_100_percent_discount_is_not_claimability_verified() -> None:
    result = SteamAppDetailsAssessor().assess("12345", response(
        price_overview={
            "currency": "TWD",
            "initial": 120000,
            "final": 0,
            "discount_percent": 100,
        }
    ))

    assert result.status is SteamPriceStatus.ZERO_PRICE_DISCOUNT
    assert result.initial_price_minor == 120000
    assert result.final_price_minor == 0
    assert result.discount_percent == 100
    assert result.currency == "TWD"
    assert result.claimability_confirmed is False
    assert result.may_create_verified_offer is False


def test_free_to_play_app_is_not_a_promotion() -> None:
    result = SteamAppDetailsAssessor().assess("12345", response(is_free=True))

    assert result.status is SteamPriceStatus.FREE_TO_PLAY
    assert result.reason == "storefront_marks_app_free_to_play"


def test_paid_app_is_not_a_free_offer() -> None:
    result = SteamAppDetailsAssessor().assess("12345", response(
        price_overview={
            "currency": "USD",
            "initial": 1999,
            "final": 999,
            "discount_percent": 50,
        }
    ))

    assert result.status is SteamPriceStatus.PAID
    assert result.final_price_minor == 999


def test_missing_price_overview_is_inconclusive() -> None:
    result = SteamAppDetailsAssessor().assess("12345", response())

    assert result.status is SteamPriceStatus.INCONCLUSIVE
    assert result.reason == "price_overview_missing"


def test_unsuccessful_app_lookup_is_unavailable() -> None:
    result = SteamAppDetailsAssessor().assess(
        "12345",
        json.dumps({"12345": {"success": False}}),
    )

    assert result.status is SteamPriceStatus.UNAVAILABLE


def test_wrong_app_id_or_non_game_is_rejected() -> None:
    assessor = SteamAppDetailsAssessor()
    wrong_id = assessor.assess("12345", response(steam_appid=777))
    non_game = assessor.assess("12345", response(type="dlc"))

    assert wrong_id.status is SteamPriceStatus.INVALID
    assert wrong_id.reason == "app_id_mismatch"
    assert non_game.status is SteamPriceStatus.INVALID
    assert non_game.reason == "not_a_game_app"


def test_invalid_price_fields_are_rejected() -> None:
    result = SteamAppDetailsAssessor().assess("12345", response(
        price_overview={
            "currency": "TWD",
            "initial": 0,
            "final": -1,
            "discount_percent": 100,
        }
    ))

    assert result.status is SteamPriceStatus.INVALID
    assert result.reason == "price_overview_invalid"


def test_invalid_expected_id_and_json_are_handled() -> None:
    assessor = SteamAppDetailsAssessor()

    assert assessor.assess("0123", "{}").status is SteamPriceStatus.INVALID
    assert assessor.assess("12345", b"not-json").status is SteamPriceStatus.INVALID
