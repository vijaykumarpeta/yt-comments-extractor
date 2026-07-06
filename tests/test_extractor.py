"""Tests for the YouTube extractor's error handling.

These tests require google-api-python-client and pandas; they are skipped
automatically when those dependencies are not installed.
"""

import pytest

googleapiclient = pytest.importorskip("googleapiclient")
pytest.importorskip("pandas")

from googleapiclient.errors import HttpError

from extractor import (
    YouTubeCommentExtractor,
    CommentsDisabledError,
    QuotaExceededError,
    VideoNotFoundError,
    YouTubeAPIError,
)


class FakeResponse:
    """Minimal stand-in for httplib2.Response."""

    def __init__(self, status: int):
        self.status = status
        self.reason = ""


def make_http_error(status: int, content: str) -> HttpError:
    return HttpError(FakeResponse(status), content.encode("utf-8"))


class TestHandleHttpError:
    def setup_method(self):
        self.extractor = YouTubeCommentExtractor(api_key="x" * 30)

    def test_quota_exceeded_raises_typed_error(self):
        # Google returns camelCase "quotaExceeded" in the error body
        error = make_http_error(
            403, '{"error": {"errors": [{"reason": "quotaExceeded"}]}}'
        )
        with pytest.raises(QuotaExceededError):
            self.extractor._handle_http_error(error, "test")

    def test_comments_disabled_raises_typed_error(self):
        error = make_http_error(
            403, '{"error": {"errors": [{"reason": "commentsDisabled"}]}}'
        )
        with pytest.raises(CommentsDisabledError):
            self.extractor._handle_http_error(error, "test")

    def test_other_403_raises_generic_error(self):
        error = make_http_error(
            403, '{"error": {"errors": [{"reason": "forbidden"}]}}'
        )
        with pytest.raises(YouTubeAPIError):
            self.extractor._handle_http_error(error, "test")

    def test_404_raises_video_not_found(self):
        error = make_http_error(404, '{"error": {}}')
        with pytest.raises(VideoNotFoundError):
            self.extractor._handle_http_error(error, "test")

    def test_500_raises_generic_error(self):
        error = make_http_error(500, "server error")
        with pytest.raises(YouTubeAPIError):
            self.extractor._handle_http_error(error, "test")
