"""
Input validation utilities.

Provides reusable validation for URLs, dates, API keys, and other user input.
All validators follow a consistent pattern returning (is_valid, error_message).
"""

import re
from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional, Tuple

from core.constants import (
    API_KEY_MIN_LENGTH,
    API_KEY_PATTERN,
    VIDEO_ID_PATTERN,
    YOUTUBE_URL_PATTERNS,
)


@dataclass
class ValidationResult:
    """Result of a validation check."""
    is_valid: bool
    error_message: Optional[str] = None

    def __bool__(self) -> bool:
        return self.is_valid


class URLValidator:
    """Validates and parses YouTube URLs."""

    # Pre-compile patterns for performance
    _compiled_patterns = [re.compile(pattern) for pattern in YOUTUBE_URL_PATTERNS]

    @classmethod
    def extract_video_id(cls, url: str) -> Optional[str]:
        """
        Extract video ID from a YouTube URL.

        Args:
            url: YouTube URL in any supported format

        Returns:
            11-character video ID or None if invalid
        """
        if not url:
            return None

        url = url.strip()

        for pattern in cls._compiled_patterns:
            match = pattern.search(url)
            if match:
                return match.group(1)

        return None

    @classmethod
    def is_valid_youtube_url(cls, url: str) -> bool:
        """Check if URL is a valid YouTube video URL."""
        return cls.extract_video_id(url) is not None

    @classmethod
    def validate(cls, url: str) -> ValidationResult:
        """
        Validate a YouTube URL.

        Args:
            url: URL to validate

        Returns:
            ValidationResult with is_valid and optional error message
        """
        if not url or not url.strip():
            return ValidationResult(False, "URL cannot be empty")

        video_id = cls.extract_video_id(url)
        if video_id is None:
            return ValidationResult(
                False,
                f"Invalid YouTube URL format: {url[:50]}..."
                if len(url) > 50 else f"Invalid YouTube URL format: {url}"
            )

        return ValidationResult(True)

    @classmethod
    def parse_url_list(cls, text: str) -> Tuple[List[str], List[str]]:
        """
        Parse multiple URLs from text input.

        Args:
            text: Multi-line text containing URLs

        Returns:
            Tuple of (valid_urls, invalid_lines)
        """
        if not text:
            return [], []

        valid_urls: List[str] = []
        invalid_lines: List[str] = []

        for line in text.strip().split('\n'):
            line = line.strip()
            if not line:
                continue

            if cls.is_valid_youtube_url(line):
                valid_urls.append(line)
            else:
                invalid_lines.append(line)

        return valid_urls, invalid_lines

    @classmethod
    def get_validation_summary(cls, text: str) -> Tuple[int, int, str]:
        """
        Get a summary of URL validation for display.

        Args:
            text: Multi-line text containing URLs

        Returns:
            Tuple of (valid_count, invalid_count, status_message)
        """
        valid_urls, invalid_lines = cls.parse_url_list(text)
        valid_count = len(valid_urls)
        invalid_count = len(invalid_lines)

        if valid_count == 0 and invalid_count == 0:
            return 0, 0, ""
        elif valid_count == 0:
            return 0, invalid_count, "⚠ No valid URLs detected"
        elif invalid_count == 0:
            plural = "s" if valid_count != 1 else ""
            return valid_count, 0, f"✓ {valid_count} valid URL{plural}"
        else:
            return valid_count, invalid_count, f"✓ {valid_count} valid, {invalid_count} invalid"


class DateValidator:
    """Validates date strings in YYYY-MM-DD format."""

    DATE_FORMAT = "%Y-%m-%d"
    DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")

    @classmethod
    def validate(cls, date_str: Optional[str]) -> ValidationResult:
        """
        Validate a date string.

        Args:
            date_str: Date string in YYYY-MM-DD format, or None/empty

        Returns:
            ValidationResult (empty/None dates are considered valid)
        """
        if not date_str or not date_str.strip():
            return ValidationResult(True)

        date_str = date_str.strip()

        # Check format
        if not cls.DATE_PATTERN.match(date_str):
            return ValidationResult(
                False,
                f"Invalid date format: '{date_str}'. Use YYYY-MM-DD"
            )

        # Check if it's a real date
        try:
            datetime.strptime(date_str, cls.DATE_FORMAT)
            return ValidationResult(True)
        except ValueError:
            return ValidationResult(False, f"Invalid date: '{date_str}'")

    @classmethod
    def validate_range(
        cls,
        from_date: Optional[str],
        to_date: Optional[str]
    ) -> ValidationResult:
        """
        Validate a date range.

        Args:
            from_date: Start date (YYYY-MM-DD) or None
            to_date: End date (YYYY-MM-DD) or None

        Returns:
            ValidationResult for the entire range
        """
        # Validate individual dates
        from_result = cls.validate(from_date)
        if not from_result:
            return from_result

        to_result = cls.validate(to_date)
        if not to_result:
            return to_result

        # Check range logic
        if from_date and to_date and from_date > to_date:
            return ValidationResult(
                False,
                "From date cannot be after To date"
            )

        return ValidationResult(True)

    @classmethod
    def parse(cls, date_str: Optional[str]) -> Optional[str]:
        """
        Parse and normalize a date string.

        Args:
            date_str: Date string or None

        Returns:
            Normalized date string (YYYY-MM-DD) or None if empty/invalid
        """
        if not date_str or not date_str.strip():
            return None

        date_str = date_str.strip()

        if cls.validate(date_str):
            return date_str

        return None


class APIKeyValidator:
    """Validates YouTube Data API v3 keys."""

    _pattern = re.compile(API_KEY_PATTERN)

    @classmethod
    def validate(cls, api_key: Optional[str]) -> ValidationResult:
        """
        Validate a YouTube API key format.

        Note: This only validates the format, not whether the key is actually valid.
        API key validity is confirmed when making the first API call.

        Args:
            api_key: API key string

        Returns:
            ValidationResult with format validation
        """
        if not api_key:
            return ValidationResult(False, "API key is required")

        api_key = api_key.strip()

        if len(api_key) < API_KEY_MIN_LENGTH:
            return ValidationResult(
                False,
                f"API key appears too short (minimum {API_KEY_MIN_LENGTH} characters)"
            )

        if not cls._pattern.match(api_key):
            return ValidationResult(
                False,
                "API key contains invalid characters"
            )

        return ValidationResult(True)


class MinLikesValidator:
    """Validates minimum likes threshold."""

    @classmethod
    def parse(cls, value: str) -> Tuple[int, Optional[str]]:
        """
        Parse and validate minimum likes value.

        Args:
            value: String value from input field

        Returns:
            Tuple of (parsed_value, warning_message)
            Returns 0 with warning if invalid
        """
        if not value or not value.strip():
            return 0, None

        try:
            parsed = int(value.strip())
            if parsed < 0:
                return 0, "Min likes cannot be negative, using 0"
            return parsed, None
        except ValueError:
            return 0, "Invalid min likes value, using 0"


class MaxCommentsValidator:
    """Validates maximum comments limit."""

    @classmethod
    def parse(cls, value: str) -> Tuple[Optional[int], Optional[str]]:
        """
        Parse and validate maximum comments value.

        Args:
            value: String value from input field

        Returns:
            Tuple of (parsed_value, warning_message)
            Returns None for unlimited if empty/invalid
        """
        if not value or not value.strip():
            return None, None

        try:
            parsed = int(value.strip())
            if parsed <= 0:
                return None, "Max comments must be positive, using unlimited"
            return parsed, None
        except ValueError:
            return None, "Invalid max comments value, using unlimited"


class WordsFilterValidator:
    """Validates and parses words filter input."""

    @classmethod
    def parse(cls, text: str) -> List[str]:
        """
        Parse comma-separated words into a list.

        Args:
            text: Comma-separated words string

        Returns:
            List of cleaned, non-empty words
        """
        if not text or not text.strip():
            return []

        words = []
        for word in text.split(','):
            cleaned = word.strip()
            if cleaned:
                words.append(cleaned)
        return words

    @classmethod
    def matches_any(cls, text: str, words: List[str]) -> bool:
        """
        Check if text contains any of the specified words.

        Uses whole-word matching (word boundaries) and case-insensitive comparison.

        Args:
            text: The text to search in (e.g., comment text)
            words: List of words to search for

        Returns:
            True if text contains any word, False otherwise.
            Returns True if words list is empty (no filter applied).
        """
        if not words:
            return True  # No filter = all comments pass

        text_lower = text.lower()
        for word in words:
            # Use word boundaries for whole-word matching
            pattern = r'\b' + re.escape(word.lower()) + r'\b'
            if re.search(pattern, text_lower):
                return True
        return False
