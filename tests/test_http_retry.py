import io
import unittest
from email.message import Message
from unittest.mock import patch

from free_game.http import HttpClient, HttpError


def http_error(status, retry_after=None):
    headers = Message()
    if retry_after is not None:
        headers["Retry-After"] = str(retry_after)
    return __import__("urllib.error", fromlist=["HTTPError"]).HTTPError(
        "https://example.com/api", status, "temporary failure", headers, None
    )


class FakeResponse:
    status = 200
    headers = {"Content-Type": "application/json"}

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        return b'{"ok":true}'


class HttpRetryTests(unittest.TestCase):
    @patch("free_game.http.time.sleep")
    @patch("free_game.http.urllib.request.urlopen")
    def test_post_json_retries_503_then_succeeds(self, urlopen, sleep):
        urlopen.side_effect = [http_error(503), FakeResponse()]

        result = HttpClient("test-agent", retries=3).post_json(
            "https://example.com/api", {"test": True}
        )

        self.assertEqual(result[0], 200)
        self.assertEqual(result[1], b'{"ok":true}')
        self.assertEqual(urlopen.call_count, 2)
        sleep.assert_called_once_with(1)

    @patch("free_game.http.time.sleep")
    @patch("free_game.http.urllib.request.urlopen")
    def test_post_json_stops_after_retry_limit(self, urlopen, sleep):
        urlopen.side_effect = [http_error(503)] * 4

        with self.assertRaisesRegex(HttpError, "HTTP 503"):
            HttpClient("test-agent", retries=3).post_json(
                "https://example.com/api", {"test": True}
            )

        self.assertEqual(urlopen.call_count, 4)
        self.assertEqual(sleep.call_count, 3)

    @patch("free_game.http.time.sleep")
    @patch("free_game.http.urllib.request.urlopen")
    def test_post_json_does_not_retry_nontransient_400(self, urlopen, sleep):
        urlopen.side_effect = http_error(400)

        with self.assertRaisesRegex(HttpError, "HTTP 400"):
            HttpClient("test-agent", retries=3).post_json(
                "https://example.com/api", {"test": True}
            )

        urlopen.assert_called_once()
        sleep.assert_not_called()


if __name__ == "__main__":
    unittest.main()
