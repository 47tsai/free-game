"""Conservative Steam storefront price assessment.

This is deliberately not a free-to-keep verifier. Steam price data can
confirm a zero-price discount, but does not by itself prove permanent
license entitlement rather than temporary access such as a Free Weekend.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class SteamPriceStatus(StrEnum):
    FREE_TO_PLAY = "free_to_play"
    PAID = "paid"
    ZERO_PRICE_DISCOUNT = "zero_price_discount"
    INCONCLUSIVE = "inconclusive"
    UNAVAILABLE = "unavailable"
    INVALID = "invalid"


@dataclass(frozen=True, slots=True)
class SteamPriceAssessment:
    app_id: str
    status: SteamPriceStatus
    title: str | None = None
    is_free: bool | None = None
    currency: str | None = None
    initial_price_minor: int | None = None
    final_price_minor: int | None = None
    discount_percent: int | None = None
    evidence_url: str | None = None
    reason: str = ""

    @property
    def claimability_confirmed(self) -> bool:
        """Price assessment alone never proves a permanent claim entitlement."""
        return False

    @property
    def may_create_verified_offer(self) -> bool:
        return False


class SteamAppDetailsAssessor:
    """Assess one Steam appdetails response without promoting it to an Offer."""

    def assess(self, app_id: str, payload: bytes | str) -> SteamPriceAssessment:
        normalized_id = self._normalize_app_id(app_id)
        if normalized_id is None:
            return SteamPriceAssessment(
                app_id=str(app_id),
                status=SteamPriceStatus.INVALID,
                reason="invalid_expected_app_id",
            )

        try:
            text = payload.decode("utf-8-sig") if isinstance(payload, bytes) else payload
            document: Any = json.loads(text)
        except (UnicodeDecodeError, json.JSONDecodeError):
            return self._result(normalized_id, SteamPriceStatus.INVALID, "invalid_json")

        if not isinstance(document, dict):
            return self._result(normalized_id, SteamPriceStatus.INVALID, "response_not_object")

        entry = document.get(normalized_id)
        if not isinstance(entry, dict):
            return self._result(normalized_id, SteamPriceStatus.UNAVAILABLE, "app_id_missing")
        if entry.get("success") is not True:
            return self._result(normalized_id, SteamPriceStatus.UNAVAILABLE, "storefront_lookup_unsuccessful")

        data = entry.get("data")
        if not isinstance(data, dict):
            return self._result(normalized_id, SteamPriceStatus.INVALID, "app_data_missing")

        returned_id = self._normalize_app_id(data.get("steam_appid"))
        if returned_id != normalized_id:
            return self._result(normalized_id, SteamPriceStatus.INVALID, "app_id_mismatch")

        if data.get("type") != "game":
            return self._result(normalized_id, SteamPriceStatus.INVALID, "not_a_game_app")

        title = data.get("name")
        if not isinstance(title, str) or not title.strip():
            return self._result(normalized_id, SteamPriceStatus.INVALID, "missing_title")

        is_free = data.get("is_free")
        if is_free is True:
            return self._result(
                normalized_id,
                SteamPriceStatus.FREE_TO_PLAY,
                "storefront_marks_app_free_to_play",
                title=title.strip(),
                is_free=True,
            )
        if is_free is not False:
            return self._result(
                normalized_id,
                SteamPriceStatus.INCONCLUSIVE,
                "is_free_flag_missing_or_invalid",
                title=title.strip(),
            )

        price = data.get("price_overview")
        if not isinstance(price, dict):
            return self._result(
                normalized_id,
                SteamPriceStatus.INCONCLUSIVE,
                "price_overview_missing",
                title=title.strip(),
                is_free=False,
            )

        currency = price.get("currency")
        initial = self._non_negative_int(price.get("initial"))
        final = self._non_negative_int(price.get("final"))
        discount = self._non_negative_int(price.get("discount_percent"))

        if (
            not isinstance(currency, str)
            or len(currency) != 3
            or not currency.isalpha()
            or initial is None
            or final is None
            or discount is None
            or discount > 100
            or final > initial
        ):
            return self._result(
                normalized_id,
                SteamPriceStatus.INVALID,
                "price_overview_invalid",
                title=title.strip(),
                is_free=False,
            )

        if initial > 0 and final == 0 and discount == 100:
            return self._result(
                normalized_id,
                SteamPriceStatus.ZERO_PRICE_DISCOUNT,
                "zero_price_discount_seen_claimability_unconfirmed",
                title=title.strip(),
                is_free=False,
                currency=currency.upper(),
                initial_price_minor=initial,
                final_price_minor=final,
                discount_percent=discount,
            )

        return self._result(
            normalized_id,
            SteamPriceStatus.PAID,
            "storefront_price_is_not_zero",
            title=title.strip(),
            is_free=False,
            currency=currency.upper(),
            initial_price_minor=initial,
            final_price_minor=final,
            discount_percent=discount,
        )

    @staticmethod
    def _normalize_app_id(value: Any) -> str | None:
        if isinstance(value, bool):
            return None
        try:
            number = int(value)
        except (TypeError, ValueError):
            return None
        if number <= 0 or str(number) != str(value).strip():
            return None
        return str(number)

    @staticmethod
    def _non_negative_int(value: Any) -> int | None:
        if isinstance(value, bool):
            return None
        try:
            number = int(value)
        except (TypeError, ValueError):
            return None
        if number < 0 or str(number) != str(value).strip():
            return None
        return number

    @staticmethod
    def _result(
        app_id: str,
        status: SteamPriceStatus,
        reason: str,
        **fields: Any,
    ) -> SteamPriceAssessment:
        return SteamPriceAssessment(
            app_id=app_id,
            status=status,
            evidence_url=f"https://store.steampowered.com/app/{app_id}/",
            reason=reason,
            **fields,
        )
