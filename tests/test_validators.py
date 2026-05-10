"""Tests for input validation utilities."""

import pytest

from core.validators import (
    ValidationResult,
    URLValidator,
    DateValidator,
    APIKeyValidator,
    MinLikesValidator,
    MaxCommentsValidator,
    WordsFilterValidator,
)


# =============================================================================
# VALIDATION RESULT
# =============================================================================

class TestValidationResult:
    def test_valid_is_truthy(self):
        assert bool(ValidationResult(True)) is True

    def test_invalid_is_falsy(self):
        assert bool(ValidationResult(False, "error")) is False

    def test_error_message(self):
        r = ValidationResult(False, "something wrong")
        assert r.error_message == "something wrong"


# =============================================================================
# URL VALIDATOR
# =============================================================================

class TestURLValidator:
    def test_standard_url(self):
        vid = URLValidator.extract_video_id("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
        assert vid == "dQw4w9WgXcQ"

    def test_short_url(self):
        vid = URLValidator.extract_video_id("https://youtu.be/dQw4w9WgXcQ")
        assert vid == "dQw4w9WgXcQ"

    def test_embed_url(self):
        vid = URLValidator.extract_video_id("https://www.youtube.com/embed/dQw4w9WgXcQ")
        assert vid == "dQw4w9WgXcQ"

    def test_shorts_url(self):
        vid = URLValidator.extract_video_id("https://www.youtube.com/shorts/dQw4w9WgXcQ")
        assert vid == "dQw4w9WgXcQ"

    def test_no_protocol(self):
        vid = URLValidator.extract_video_id("youtube.com/watch?v=dQw4w9WgXcQ")
        assert vid == "dQw4w9WgXcQ"

    def test_invalid_url(self):
        assert URLValidator.extract_video_id("https://example.com") is None

    def test_empty_url(self):
        assert URLValidator.extract_video_id("") is None

    def test_none_url(self):
        assert URLValidator.extract_video_id(None) is None

    def test_is_valid(self):
        assert URLValidator.is_valid_youtube_url("https://youtu.be/dQw4w9WgXcQ") is True
        assert URLValidator.is_valid_youtube_url("not a url") is False

    def test_validate_valid(self):
        result = URLValidator.validate("https://youtu.be/dQw4w9WgXcQ")
        assert result.is_valid is True

    def test_validate_empty(self):
        result = URLValidator.validate("")
        assert result.is_valid is False

    def test_validate_invalid(self):
        result = URLValidator.validate("https://example.com")
        assert result.is_valid is False
        assert result.error_message is not None

    def test_parse_url_list(self):
        text = "https://youtu.be/dQw4w9WgXcQ\nnot-a-url\nhttps://youtu.be/abc12345678"
        valid, invalid = URLValidator.parse_url_list(text)
        assert len(valid) == 2
        assert len(invalid) == 1

    def test_parse_url_list_empty(self):
        valid, invalid = URLValidator.parse_url_list("")
        assert valid == []
        assert invalid == []

    def test_validation_summary_all_valid(self):
        text = "https://youtu.be/dQw4w9WgXcQ"
        count_v, count_i, msg = URLValidator.get_validation_summary(text)
        assert count_v == 1
        assert count_i == 0
        assert "valid" in msg.lower()

    def test_validation_summary_none_valid(self):
        text = "not a url"
        count_v, count_i, msg = URLValidator.get_validation_summary(text)
        assert count_v == 0
        assert count_i == 1

    def test_validation_summary_mixed(self):
        text = "https://youtu.be/dQw4w9WgXcQ\nnot-a-url"
        count_v, count_i, msg = URLValidator.get_validation_summary(text)
        assert count_v == 1
        assert count_i == 1


# =============================================================================
# DATE VALIDATOR
# =============================================================================

class TestDateValidator:
    def test_valid_date(self):
        assert DateValidator.validate("2024-01-15").is_valid is True

    def test_empty_date_is_valid(self):
        assert DateValidator.validate("").is_valid is True
        assert DateValidator.validate(None).is_valid is True

    def test_bad_format(self):
        result = DateValidator.validate("01-15-2024")
        assert result.is_valid is False

    def test_impossible_date(self):
        result = DateValidator.validate("2024-02-30")
        assert result.is_valid is False

    def test_valid_range(self):
        result = DateValidator.validate_range("2024-01-01", "2024-12-31")
        assert result.is_valid is True

    def test_reversed_range(self):
        result = DateValidator.validate_range("2024-12-31", "2024-01-01")
        assert result.is_valid is False

    def test_open_range(self):
        assert DateValidator.validate_range(None, "2024-12-31").is_valid is True
        assert DateValidator.validate_range("2024-01-01", None).is_valid is True

    def test_parse_valid(self):
        assert DateValidator.parse("2024-01-15") == "2024-01-15"

    def test_parse_empty(self):
        assert DateValidator.parse("") is None
        assert DateValidator.parse(None) is None

    def test_parse_invalid(self):
        assert DateValidator.parse("not-a-date") is None


# =============================================================================
# API KEY VALIDATOR
# =============================================================================

class TestAPIKeyValidator:
    def test_valid_key(self):
        key = "AIzaSyA" + "a" * 30
        assert APIKeyValidator.validate(key).is_valid is True

    def test_empty_key(self):
        result = APIKeyValidator.validate("")
        assert result.is_valid is False

    def test_none_key(self):
        result = APIKeyValidator.validate(None)
        assert result.is_valid is False

    def test_short_key(self):
        result = APIKeyValidator.validate("short")
        assert result.is_valid is False

    def test_invalid_chars(self):
        key = "a" * 25 + "!@#$%"
        result = APIKeyValidator.validate(key)
        assert result.is_valid is False


# =============================================================================
# MIN LIKES VALIDATOR
# =============================================================================

class TestMinLikesValidator:
    def test_valid_number(self):
        value, warning = MinLikesValidator.parse("10")
        assert value == 10
        assert warning is None

    def test_empty_string(self):
        value, warning = MinLikesValidator.parse("")
        assert value == 0
        assert warning is None

    def test_negative(self):
        value, warning = MinLikesValidator.parse("-5")
        assert value == 0
        assert warning is not None

    def test_non_numeric(self):
        value, warning = MinLikesValidator.parse("abc")
        assert value == 0
        assert warning is not None


# =============================================================================
# MAX COMMENTS VALIDATOR
# =============================================================================

class TestMaxCommentsValidator:
    def test_valid_number(self):
        value, warning = MaxCommentsValidator.parse("100")
        assert value == 100
        assert warning is None

    def test_empty_is_unlimited(self):
        value, warning = MaxCommentsValidator.parse("")
        assert value is None
        assert warning is None

    def test_zero_is_unlimited(self):
        value, warning = MaxCommentsValidator.parse("0")
        assert value is None
        assert warning is not None

    def test_negative_is_unlimited(self):
        value, warning = MaxCommentsValidator.parse("-1")
        assert value is None
        assert warning is not None

    def test_non_numeric(self):
        value, warning = MaxCommentsValidator.parse("abc")
        assert value is None
        assert warning is not None


# =============================================================================
# WORDS FILTER VALIDATOR
# =============================================================================

class TestWordsFilterValidator:
    def test_parse_words(self):
        words = WordsFilterValidator.parse("python, tutorial, beginner")
        assert words == ["python", "tutorial", "beginner"]

    def test_parse_empty(self):
        assert WordsFilterValidator.parse("") == []

    def test_parse_whitespace(self):
        assert WordsFilterValidator.parse("  ") == []

    def test_parse_trailing_comma(self):
        words = WordsFilterValidator.parse("python, tutorial,")
        assert words == ["python", "tutorial"]

    def test_matches_any_whole_word(self):
        assert WordsFilterValidator.matches_any("I love python programming", ["python"]) is True
        assert WordsFilterValidator.matches_any("I love pythonic code", ["python"]) is False

    def test_matches_any_case_insensitive(self):
        assert WordsFilterValidator.matches_any("PYTHON is great", ["python"]) is True

    def test_matches_any_empty_words(self):
        assert WordsFilterValidator.matches_any("anything", []) is True

    def test_matches_any_no_match(self):
        assert WordsFilterValidator.matches_any("hello world", ["python", "java"]) is False

    def test_compile_pattern(self):
        pattern = WordsFilterValidator.compile_pattern(["python", "java"])
        assert pattern is not None
        assert pattern.search("I love python") is not None
        assert pattern.search("I love javascript") is None

    def test_compile_pattern_empty(self):
        assert WordsFilterValidator.compile_pattern([]) is None

    def test_matches_any_with_precompiled(self):
        words = ["python", "java"]
        pattern = WordsFilterValidator.compile_pattern(words)
        assert WordsFilterValidator.matches_any("I love python", words, pattern) is True
        assert WordsFilterValidator.matches_any("I love ruby", words, pattern) is False
