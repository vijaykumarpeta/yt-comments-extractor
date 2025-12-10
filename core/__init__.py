"""
Core modules for YouTube Comment Extractor.

This package contains shared utilities, configuration, and logic.
"""

from core.constants import (
    APP_NAME,
    APP_VERSION,
    COLORS,
    LOG_COLORS,
    LOG_ICONS,
    WINDOW_DEFAULT_WIDTH,
    WINDOW_DEFAULT_HEIGHT,
    WINDOW_MIN_WIDTH,
    WINDOW_MIN_HEIGHT,
    DIALOG_WIDTH,
    DIALOG_HEIGHT,
    SpamFilterStrength,
    SortOption,
    LogLevel,
)
from core.validators import (
    ValidationResult,
    URLValidator,
    DateValidator,
    APIKeyValidator,
    MinLikesValidator,
)
from core.settings import SettingsManager, AppSettings

__all__ = [
    # Constants
    "APP_NAME",
    "APP_VERSION",
    "COLORS",
    "LOG_COLORS",
    "LOG_ICONS",
    "WINDOW_DEFAULT_WIDTH",
    "WINDOW_DEFAULT_HEIGHT",
    "WINDOW_MIN_WIDTH",
    "WINDOW_MIN_HEIGHT",
    "DIALOG_WIDTH",
    "DIALOG_HEIGHT",
    # Enums
    "SpamFilterStrength",
    "SortOption",
    "LogLevel",
    # Validators
    "ValidationResult",
    "URLValidator",
    "DateValidator",
    "APIKeyValidator",
    "MinLikesValidator",
    # Settings
    "SettingsManager",
    "AppSettings",
]
