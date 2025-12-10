"""
Settings management with secure credential storage.

Provides persistent settings storage with optional keyring integration
for secure API key storage.
"""

import json
import logging
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional

from core.constants import (
    SETTINGS_FILE,
    KEYRING_SERVICE_NAME,
    KEYRING_API_KEY_NAME,
    SortOption,
    SpamFilterStrength,
)

logger = logging.getLogger(__name__)

# Try to import keyring for secure storage
try:
    import keyring
    KEYRING_AVAILABLE = True
except ImportError:
    KEYRING_AVAILABLE = False
    logger.warning(
        "keyring package not installed. API key will be stored in plaintext. "
        "Install with: pip install keyring"
    )


@dataclass
class AppSettings:
    """Application settings data class."""

    # API settings
    api_key: str = ""

    # Filter settings
    filter_spam: bool = True
    spam_threshold: float = SpamFilterStrength.MODERATE.value
    exclude_creator: bool = False
    min_likes: int = 0
    max_comments: Optional[int] = None  # Maximum comments per video (None = unlimited)
    filter_words: str = ""  # Comma-separated words to filter comments

    # Custom spam patterns
    blacklist_patterns: str = ""  # Newline-separated patterns to always flag as spam
    whitelist_patterns: str = ""  # Newline-separated patterns to always allow

    # Sort settings
    sort_by: str = SortOption.LIKES.value

    # Date filter (optional)
    date_from: Optional[str] = None
    date_to: Optional[str] = None

    # UI preferences
    window_width: int = 950
    window_height: int = 970

    def to_dict(self, include_api_key: bool = False) -> dict:
        """
        Convert settings to dictionary.

        Args:
            include_api_key: Whether to include the API key (for non-secure storage)
        """
        data = asdict(self)
        if not include_api_key:
            del data["api_key"]
        # Remove None values for cleaner JSON
        return {k: v for k, v in data.items() if v is not None}

    @classmethod
    def from_dict(cls, data: dict) -> "AppSettings":
        """Create settings from dictionary."""
        # Filter to only known fields
        known_fields = {f.name for f in cls.__dataclass_fields__.values()}
        filtered = {k: v for k, v in data.items() if k in known_fields}
        return cls(**filtered)


class SettingsManager:
    """
    Manages application settings with secure credential storage.

    Settings are stored in a JSON file, but the API key is stored
    securely using the system keyring when available.

    Usage:
        manager = SettingsManager()
        settings = manager.load()

        settings.api_key = "new_key"
        settings.filter_spam = True

        manager.save(settings)
    """

    def __init__(self, settings_file: Optional[str] = None):
        """
        Initialize the settings manager.

        Args:
            settings_file: Path to settings file. Defaults to SETTINGS_FILE constant.
        """
        self.settings_file = Path(settings_file or SETTINGS_FILE)
        self._use_keyring = KEYRING_AVAILABLE

    @property
    def keyring_available(self) -> bool:
        """Check if secure keyring storage is available."""
        return self._use_keyring

    def load(self) -> AppSettings:
        """
        Load settings from file and keyring.

        Returns:
            AppSettings with loaded values, or defaults if no settings exist
        """
        settings = AppSettings()

        # Load from JSON file
        if self.settings_file.exists():
            try:
                with open(self.settings_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    settings = AppSettings.from_dict(data)

                    # Handle legacy sort_by values
                    if settings.sort_by == "date_desc":
                        settings.sort_by = SortOption.DATE_NEWEST.value
                    elif settings.sort_by == "date_asc":
                        settings.sort_by = SortOption.DATE_OLDEST.value

            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse settings file: {e}")
            except Exception as e:
                logger.error(f"Failed to load settings: {e}")

        # Load API key from keyring (if available) or from file
        api_key = self._load_api_key()
        if api_key:
            settings.api_key = api_key

        return settings

    def save(self, settings: AppSettings) -> bool:
        """
        Save settings to file and keyring.

        Args:
            settings: AppSettings to save

        Returns:
            True if saved successfully
        """
        try:
            # Save API key securely
            self._save_api_key(settings.api_key)

            # Save other settings to JSON (without API key if using keyring)
            include_api_key = not self._use_keyring
            data = settings.to_dict(include_api_key=include_api_key)

            with open(self.settings_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2)

            return True

        except Exception as e:
            logger.error(f"Failed to save settings: {e}")
            return False

    def _load_api_key(self) -> Optional[str]:
        """Load API key from keyring or settings file."""
        # Try keyring first
        if self._use_keyring:
            try:
                api_key = keyring.get_password(
                    KEYRING_SERVICE_NAME,
                    KEYRING_API_KEY_NAME
                )
                if api_key:
                    return api_key
            except Exception as e:
                logger.warning(f"Failed to load API key from keyring: {e}")

        # Fall back to settings file
        if self.settings_file.exists():
            try:
                with open(self.settings_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    return data.get('api_key', '')
            except Exception:
                pass

        return None

    def _save_api_key(self, api_key: str) -> None:
        """Save API key to keyring or settings file."""
        if not api_key:
            return

        if self._use_keyring:
            try:
                keyring.set_password(
                    KEYRING_SERVICE_NAME,
                    KEYRING_API_KEY_NAME,
                    api_key
                )
                return
            except Exception as e:
                logger.warning(f"Failed to save API key to keyring: {e}")
                # Fall through to file storage

        # If keyring unavailable or failed, it will be saved with other settings
        logger.debug("API key will be stored in settings file (less secure)")

    def delete_api_key(self) -> bool:
        """
        Delete the stored API key from keyring.

        Returns:
            True if deleted successfully
        """
        if self._use_keyring:
            try:
                keyring.delete_password(
                    KEYRING_SERVICE_NAME,
                    KEYRING_API_KEY_NAME
                )
                return True
            except keyring.errors.PasswordDeleteError:
                # Key didn't exist
                return True
            except Exception as e:
                logger.error(f"Failed to delete API key from keyring: {e}")
                return False
        return True

    def get_storage_info(self) -> str:
        """Get information about how the API key is stored."""
        if self._use_keyring:
            return "API key stored securely in system keyring"
        else:
            return "API key stored in settings.json (install 'keyring' for secure storage)"
