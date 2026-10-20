from dataclasses import dataclass, field


@dataclass(frozen=True)
class StoreLink:
    url: str
    context: str = ""


@dataclass(frozen=True)
class Game:
    name: str
    platform: str = ""
    deadline: str = ""
    genre: str = ""
    gameplay: str = ""
    rating: str = ""
    brief: str = ""
    link: str = ""
    image: str = ""
    steam_price: str = ""
    original_price: str = ""


@dataclass(frozen=True)
class Article:
    title: str
    url: str
    summary: str = ""
    published: str = ""
    image: str = ""
    text: str = ""
    links: tuple[str, ...] = field(default_factory=tuple)
    store_links: tuple[StoreLink, ...] = field(default_factory=tuple)
