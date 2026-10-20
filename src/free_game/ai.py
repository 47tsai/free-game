import json
import re

from .models import Game


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
                    platform=str(item.get("platform", "")).strip()[:100],
                    deadline=str(item.get("deadline", "")).strip()[:200],
                    original_price=str(item.get("original_price", "")).strip()[:100],
                    genre=str(item.get("genre", "")).strip()[:200],
                    gameplay=str(item.get("gameplay", "")).strip()[:1000],
                    rating=str(item.get("rating", "")).strip()[:300],
                    brief=str(item.get("brief", "")).strip()[:1000],
                    link=link,
                    image=article.image,
                )
            )

        return result
