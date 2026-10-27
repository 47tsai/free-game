import json
import unicodedata
from pathlib import Path


class StateStore:
    def __init__(self, path, limit):
        self.path, self.limit = Path(path), limit
        self._order = []

    def load(self):
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(data, list):
                return set()
            self._order = list(dict.fromkeys(str(item) for item in data))
            return set(self._order)
        except (OSError, json.JSONDecodeError):
            return set()

    def save(self, values):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        current = set(values)
        ordered = [item for item in self._order if item in current]
        known = set(ordered)
        ordered.extend(item for item in current if item not in known)
        data = ordered[-self.limit:]
        # Write beside the destination, then atomically replace it. If the
        # process stops mid-write, the previous valid state file survives.
        temporary_path = self.path.with_name(self.path.name + ".tmp")
        temporary_path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        temporary_path.replace(self.path)
        self._order = data

    @staticmethod
    def _normalize(value):
        value = unicodedata.normalize("NFKC", str(value or "")).strip().casefold()
        return " ".join(value.split())

    @staticmethod
    def game_key(game):
        name = StateStore._normalize(game.name)
        link = StateStore._normalize(game.link)
        return "game|" + link + "|" + name

    @staticmethod
    def legacy_game_key(article_url, game):
        return "game|" + article_url + "|" + game.link + "|" + game.name

    @staticmethod
    def article_key(article_url):
        return "article|" + article_url

    @staticmethod
    def is_game_processed(values, article_url, game):
        return (
            StateStore.game_key(game) in values
            or StateStore.legacy_game_key(article_url, game) in values
        )

    @staticmethod
    def is_article_processed(values, article_url):
        return article_url in values or StateStore.article_key(article_url) in values
