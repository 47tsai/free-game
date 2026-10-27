import json
import re
from urllib.parse import urlparse

from .models import Game


def extract_original_price(text):
    match = re.search(
        r"(?:原價|原售價|原本售價|定價)\s*(?:為|是|約)?\s*(新台幣|台幣|NT\s*\$|US\s*\$|USD\s*\$|\$)\s*([\d,]+(?:\.\d{1,2})?)\s*(?:元|新台幣)?",
        str(text or ""),
        re.IGNORECASE,
    )
    if not match:
        return ""
    currency, amount = match.groups()
    amount = amount.replace(",", "")
    if currency in ("新台幣", "台幣") or re.match(r"NT", currency, re.I):
        return f"NT${amount}"
    if re.match(r"USD", currency, re.I):
        return f"US${amount}"
    return f"${amount}"


def extract_deadline(text):
    pattern = (
        r"(?:期限至|期限為|免費至|限免至|截止至|領取期限(?:至|為)?)"
        r"\s*(?:(?:台灣|臺灣)時間\s*)?"
        r"(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日"
        r"\s*(凌晨|上午|早上|中午|下午|晚上)?\s*(\d{1,2})\s*(?:點|時)(?:\s*(\d{1,2})\s*分)?"
    )
    match = re.search(pattern, str(text or ""))
    if not match:
        return ""
    year, month, day = map(int, match.group(1, 2, 3))
    period, hour, minute = match.group(4) or "", int(match.group(5)), int(match.group(6) or 0)
    if period == "凌晨" and hour == 12:
        hour = 0
    elif period in ("下午", "晚上") and hour < 12:
        hour += 12
    elif period == "中午" and hour < 11:
        hour += 12
    try:
        from datetime import datetime
        datetime(year, month, day, hour, minute)
    except ValueError:
        return ""
    return f"{year:04d}-{month:02d}-{day:02d}T{hour:02d}:{minute:02d}:00+08:00"


def platform_from_url(url):
    host = urlparse(str(url or "")).netloc.lower().split("@")[-1].split(":")[0]
    if host == "store.epicgames.com" or host.endswith(".store.epicgames.com"):
        return "Epic Games Store"
    if host == "store.steampowered.com" or host.endswith(".steampowered.com"):
        return "Steam"
    return ""


class GeminiExtractor:
    def __init__(self, http, api_key, model):
        self.http, self.api_key, self.model = http, api_key, model

    def extract(self, article):
        if not self.api_key:
            raise RuntimeError("GEMINI_API_KEY is not configured")
        if not article.store_links:
            return []

        candidates = [
            f"[{i}] {item.url} | {item.context}"
            for i, item in enumerate(article.store_links, 1)
        ]
        prompt = (
            "你是遊戲資訊結構化助手。只根據文章內容判斷哪些遊戲正在限時免費。"
            "輸出 JSON 陣列，不要 Markdown。欄位為 name, platform, original_price, deadline, genre, gameplay, rating, brief, store_index。original_price 是本次免費活動開始前的原價，只能使用文章明確提供的價格，保留原幣別與格式（例如 $52、NT$ 300）；不可把「免費」或折扣後的 $0 當成原價，文章沒有提供就輸出空字串。deadline 請輸出 ISO 8601 日期時間並使用台灣時區 +08:00，例如 2026-11-03T00:00:00+08:00；若文章未提供具體時間，不可自行猜測，輸出原文或空字串。brief 只寫一句 20 字內的超短遊戲特色介紹。"
            "store_index 必須是候選商店連結前面的整數編號，不可自行產生 URL。每個候選連結最多配對一款遊戲；"
            "若文章有多個遊戲，分別配對最合理的候選連結。若無法可靠配對，省略該遊戲。"
            f"\n標題：{article.title}\n文章：{article.text}"
            f"\n候選商店連結：{json.dumps(candidates, ensure_ascii=False)}"
        )
        url = (
            "https://generativelanguage.googleapis.com/v1beta/models/"
            + self.model
            + ":generateContent"
        )
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": 0.1,
                "responseMimeType": "application/json",
            },
        }
        _, body, _ = self.http.post_json(
            url, payload, timeout=45, headers={"x-goog-api-key": self.api_key}
        )

        try:
            response = json.loads(body)
            raw = response["candidates"][0]["content"]["parts"][0]["text"].strip()
        except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
            raise RuntimeError("Gemini returned an invalid response") from exc

        raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw, flags=re.I)
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise RuntimeError("Gemini returned invalid JSON") from exc

        if not isinstance(data, list):
            raise RuntimeError("Gemini JSON is not a list")

        source_price = extract_original_price(article.text)
        source_deadline = extract_deadline(article.text)

        result = []
        seen = set()
        used_indexes = set()

        for item in data:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name", "")).strip()
            index = item.get("store_index")
            if isinstance(index, bool) or not isinstance(index, int):
                continue
            if not name or not 1 <= index <= len(article.store_links):
                continue
            if index in used_indexes:
                continue
            link = article.store_links[index - 1].url
            key = (name.casefold(), link)
            if key in seen:
                continue
            seen.add(key)
            used_indexes.add(index)
            result.append(
                Game(
                    name=name[:200],
                    platform=platform_from_url(link) or str(item.get("platform", "")).strip()[:100],
                    deadline=(source_deadline or str(item.get("deadline", "")).strip())[:200],
                    original_price=(source_price or str(item.get("original_price", "")).strip())[:100],
                    genre=str(item.get("genre", "")).strip()[:200],
                    gameplay=str(item.get("gameplay", "")).strip()[:1000],
                    rating=str(item.get("rating", "")).strip()[:300],
                    brief=str(item.get("brief", "")).strip()[:1000],
                    link=link,
                    image=article.image,
                )
            )

        return result
