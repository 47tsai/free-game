import json

from free_game.fgc import parse_fgc_messages


def test_parses_fgc_claim_message():
    payload = json.dumps({"message": "**Steam** (Chi):\n• **[Hexologic](https://store.steampowered.com/app/785890/Hexologic/)**: claimed"})
    claims = parse_fgc_messages(payload)
    assert claims == [{"platform": "steam", "external_product_id": "785890", "title": "Hexologic", "store_url": "https://store.steampowered.com/app/785890/Hexologic/"}]


def test_ignores_unclaimed_and_unrecognized_messages():
    payload = json.dumps({"message": "**Steam** (Chi):\n• **[Example](https://store.steampowered.com/app/1/Example/)**: available"})
    assert parse_fgc_messages(payload) == []


def test_unknown_platform_uses_store_url_host_as_identity():
    payload = json.dumps({"message": "**Mystery Store** (Chi):\n• **[Mystery Game](https://new-store.example/products/abc)**: claimed"})
    claims = parse_fgc_messages(payload)
    assert claims[0]["platform"] == "new-store.example"
    assert claims[0]["external_product_id"] == "abc"


def test_parse_includes_claim_time():
    payload = json.dumps({"time": 1795792237, "message": "**GOG** (Chi):\n• **[Dead Age 2](https://www.gog.com/en)**: claimed"})
    claims = parse_fgc_messages(payload)
    assert claims == [{"platform": "gog", "external_product_id": None, "title": "Dead Age 2", "store_url": "https://www.gog.com/en", "claimed_at": "2026-11-27T15:10:37Z"}]


def test_gog_homepage_link_has_no_product_id():
    # Regression: the Dead Age 2 FGC message linked to
    # https://www.gog.com/en, whose last path segment "en" was used as
    # the product id and created a duplicate record.
    payload = json.dumps({"message": "**GOG** (Chi):\n• **[Dead Age 2](https://www.gog.com/en)**: claimed"})
    claims = parse_fgc_messages(payload)
    assert claims == [{"platform": "gog", "external_product_id": None, "title": "Dead Age 2", "store_url": "https://www.gog.com/en"}]
