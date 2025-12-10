"""
Application constants and configuration values.

Centralized location for all magic numbers, strings, and configuration values.
"""

from enum import Enum
from typing import Dict


# =============================================================================
# APPLICATION METADATA
# =============================================================================

APP_NAME = "YouTube Comment Extractor"
APP_VERSION = "2.0.0"
APP_DESCRIPTION = "Extract and analyze YouTube comments with ease"


# =============================================================================
# UI THEME CONFIGURATION
# =============================================================================

COLORS: Dict[str, str] = {
    "bg_dark": "#1a1a2e",
    "bg_card": "#16213e",
    "bg_input": "#0f0f1a",
    "accent": "#e94560",
    "accent_hover": "#ff6b6b",
    "accent_secondary": "#0f3460",
    "text_primary": "#ffffff",
    "text_secondary": "#a0a0a0",
    "text_muted": "#6c6c6c",
    "success": "#4ecca3",
    "warning": "#ffc107",
    "error": "#ff6b6b",
    "border": "#2a2a4a",
}


# =============================================================================
# API CONFIGURATION
# =============================================================================

# YouTube API settings
YOUTUBE_API_SERVICE_NAME = "youtube"
YOUTUBE_API_VERSION = "v3"
YOUTUBE_COMMENTS_PER_PAGE = 100

# Rate limiting
API_DELAY_BETWEEN_PAGES = 0.5  # seconds
API_DELAY_BETWEEN_VIDEOS_MIN = 2.0  # seconds
API_DELAY_BETWEEN_VIDEOS_MAX = 5.0  # seconds

# API Key validation
API_KEY_MIN_LENGTH = 20
API_KEY_PATTERN = r"^[A-Za-z0-9_-]+$"


# =============================================================================
# YOUTUBE URL PATTERNS
# =============================================================================

# Video ID is always 11 characters: alphanumeric, underscore, hyphen
VIDEO_ID_LENGTH = 11
VIDEO_ID_PATTERN = r"[a-zA-Z0-9_-]{11}"

# Supported YouTube URL formats
YOUTUBE_URL_PATTERNS = [
    rf"(?:https?://)?(?:www\.)?youtube\.com/watch\?v=({VIDEO_ID_PATTERN})",
    rf"(?:https?://)?(?:www\.)?youtube\.com/v/({VIDEO_ID_PATTERN})",
    rf"(?:https?://)?(?:www\.)?youtube\.com/embed/({VIDEO_ID_PATTERN})",
    rf"(?:https?://)?(?:www\.)?youtube\.com/shorts/({VIDEO_ID_PATTERN})",
    rf"(?:https?://)?youtu\.be/({VIDEO_ID_PATTERN})",
]


# =============================================================================
# SETTINGS CONFIGURATION
# =============================================================================

SETTINGS_FILE = "settings.json"
KEYRING_SERVICE_NAME = "yt-comments-extractor"
KEYRING_API_KEY_NAME = "youtube_api_key"


# =============================================================================
# ENUMS
# =============================================================================

class SortOption(Enum):
    """Comment sorting options."""
    LIKES = "likes"
    DATE_NEWEST = "date_desc"
    DATE_OLDEST = "date_asc"

    @classmethod
    def from_display_name(cls, name: str) -> "SortOption":
        """Convert display name to enum value."""
        mapping = {
            "Likes": cls.LIKES,
            "Date (Newest)": cls.DATE_NEWEST,
            "Date (Oldest)": cls.DATE_OLDEST,
        }
        return mapping.get(name, cls.LIKES)

    @property
    def display_name(self) -> str:
        """Get human-readable display name."""
        mapping = {
            SortOption.LIKES: "Likes",
            SortOption.DATE_NEWEST: "Date (Newest)",
            SortOption.DATE_OLDEST: "Date (Oldest)",
        }
        return mapping[self]


class SpamFilterStrength(Enum):
    """Preset spam filter sensitivity levels."""
    LIGHT = 0.65       # Only catch obvious spam
    MODERATE = 0.5     # Balanced (default)
    AGGRESSIVE = 0.4   # Catch more spam, slight risk of false positives
    STRICT = 0.3       # Maximum filtering


class LogLevel(Enum):
    """Log message severity levels."""
    INFO = "info"
    SUCCESS = "success"
    WARNING = "warning"
    ERROR = "error"
    MUTED = "muted"


# =============================================================================
# LOG STYLING
# =============================================================================

LOG_ICONS: Dict[str, str] = {
    "info": "→",
    "success": "✓",
    "warning": "⚠",
    "error": "✗",
    "muted": "·",
}

LOG_COLORS: Dict[str, str] = {
    "info": COLORS["text_secondary"],
    "success": COLORS["success"],
    "warning": COLORS["warning"],
    "error": COLORS["error"],
    "muted": COLORS["text_muted"],
}


# =============================================================================
# WINDOW CONFIGURATION
# =============================================================================

WINDOW_DEFAULT_WIDTH = 950
WINDOW_DEFAULT_HEIGHT = 900
WINDOW_MIN_WIDTH = 800
WINDOW_MIN_HEIGHT = 600

# Dialog dimensions
DIALOG_WIDTH = 500
DIALOG_HEIGHT = 400
