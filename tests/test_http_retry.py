import io
import urllib.error
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
    def test_post_json_can_retry_only_explicitly_allowed_statuses(self, urlopen, sleep):
        urlopen.side_effect = [http_error(503), FakeResponse()]

        with self.assertRaisesRegex(HttpError, "HTTP 503"):
            HttpClient("test-agent", retries=3).post_json(
                "https://discord.example/webhook",
                {"test": True},
                retry_status={429},
                retry_transport_errors=False,
            )

        urlopen.assert_called_once()
        sleep.assert_not_called()

    @patch("free_game.http.time.sleep")
    @patch("free_game.http.urllib.request.urlopen")
    def test_post_json_can_disable_ambiguous_transport_retries(self, urlopen, sleep):
        urlopen.side_effect = urllib.error.URLError("connection timed out")

        with self.assertRaisesRegex(HttpError, "request failed"):
            HttpClient("test-agent", retries=3).post_json(
                "https://discord.example/webhook",
                {"test": True},
                retry_status={429},
                retry_transport_errors=False,
            )

        urlopen.assert_called_once()
        sleep.assert_not_called()

    @patch("free_game.http.time.sleep")
    @patch("free_game.http.urllib.request.urlopen")
    def test_post_json_retries_explicit_429_when_allowed(self, urlopen, sleep):
        urlopen.side_effect = [http_error(429, retry_after=2), FakeResponse()]

        result = HttpClient("test-agent", retries=3).post_json(
            "https://discord.example/webhook",
            {"test": True},
            retry_status={429},
            retry_transport_errors=False,
        )

        self.assertEqual(result[0], 200)
        self.assertEqual(urlopen.call_count, 2)
        sleep.assert_called_once_with(2)

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
