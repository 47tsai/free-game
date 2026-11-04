import json

from free_game.fgc import parse_fgc_messages


def test_parses_fgc_claim_message():
    payload = json.dumps({"message": "**Steam** (Chi):\n• **[Hexologic](https://store.steampowered.com/app/785890/Hexologic/)**: claimed"})
    claims = parse_fgc_messages(payload)
    assert claims == [{"platform": "steam", "external_product_id": "785890", "title": "Hexologic", "store_url": "https://store.steampowered.com/app/785890/Hexologic/"}]


def test_ignores_unclaimed_and_unrecognized_messages():
    payload = json.dumps({"message": "**Steam** (Chi):\n• **[Example](https://store.steampowered.com/app/1/Example/)**: available"})
    assert parse_fgc_messages(payload) == []
