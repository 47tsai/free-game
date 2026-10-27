import time
import urllib.error
import urllib.request

RETRY_STATUS = {408, 425, 429, 500, 502, 503, 504}


class HttpError(RuntimeError):
    pass


class HttpClient:
    def __init__(self, user_agent, retries=3):
        self.user_agent, self.retries = user_agent, retries

    def get(self, url, timeout=20):
        for attempt in range(self.retries + 1):
            req = urllib.request.Request(
                url,
                headers={"User-Agent": self.user_agent, "Accept": "*/*"},
            )
            try:
                with urllib.request.urlopen(req, timeout=timeout) as r:
                    return r.read(), dict(r.headers.items())
            except urllib.error.HTTPError as e:
                if e.code not in RETRY_STATUS or attempt == self.retries:
                    raise HttpError(f"HTTP {e.code}: {url}") from e
                time.sleep(self._retry_delay(e, attempt))
            except (urllib.error.URLError, TimeoutError) as e:
                if attempt == self.retries:
                    raise HttpError(f"request failed: {url}") from e
                time.sleep(min(2 ** attempt, 15))
        raise HttpError(f"request failed: {url}")

    def post_json(
        self,
        url,
        payload,
        timeout=20,
        headers=None,
        retry_status=None,
        retry_transport_errors=True,
    ):
        import json

        body = json.dumps(payload, ensure_ascii=False).encode()
        request_headers = {
            "User-Agent": self.user_agent,
            "Content-Type": "application/json",
        }
        if headers:
            request_headers.update(headers)

        retryable_status = RETRY_STATUS if retry_status is None else set(retry_status)

        for attempt in range(self.retries + 1):
            req = urllib.request.Request(
                url,
                data=body,
                method="POST",
                headers=request_headers,
            )
            try:
                with urllib.request.urlopen(req, timeout=timeout) as r:
                    return r.status, r.read(), dict(r.headers.items())
            except urllib.error.HTTPError as e:
                if e.code not in retryable_status or attempt == self.retries:
                    raise HttpError(f"HTTP {e.code}: {url}") from e
                time.sleep(self._retry_delay(e, attempt))
            except (urllib.error.URLError, TimeoutError) as e:
                if not retry_transport_errors or attempt == self.retries:
                    raise HttpError(f"request failed: {url}") from e
                time.sleep(min(2 ** attempt, 15))
        raise HttpError(f"request failed: {url}")

    @staticmethod
    def _retry_delay(error, attempt):
        retry_after = error.headers.get("Retry-After")
        if retry_after:
            try:
                return min(float(retry_after), 30)
            except ValueError:
                pass
        return min(2 ** attempt, 30)
