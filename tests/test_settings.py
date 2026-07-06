"""Tests for settings persistence and API-key storage fallback."""

import json

import pytest

import core.settings as settings_module
from core.settings import AppSettings, SettingsManager


class FakeKeyring:
    """Keyring stand-in whose set_password always fails (e.g. headless Linux)."""

    class errors:
        class PasswordDeleteError(Exception):
            pass

    def set_password(self, service, name, value):
        raise RuntimeError("No keyring daemon available")

    def get_password(self, service, name):
        raise RuntimeError("No keyring daemon available")


class TestApiKeyFallback:
    def test_key_saved_to_file_when_keyring_write_fails(self, tmp_path, monkeypatch):
        """If keyring is available but the write fails, the API key must be
        persisted in the settings file instead of being silently lost."""
        settings_file = tmp_path / "settings.json"
        manager = SettingsManager(settings_file=str(settings_file))

        # Simulate: keyring importable, but writes fail at runtime
        monkeypatch.setattr(settings_module, "keyring", FakeKeyring(), raising=False)
        manager._use_keyring = True

        settings = AppSettings(api_key="AIza" + "x" * 30)
        assert manager.save(settings) is True

        data = json.loads(settings_file.read_text(encoding="utf-8"))
        assert data.get("api_key") == settings.api_key

        # And it must round-trip through load()
        loaded = manager.load()
        assert loaded.api_key == settings.api_key

    def test_key_not_in_file_when_keyring_write_succeeds(self, tmp_path, monkeypatch):
        settings_file = tmp_path / "settings.json"
        manager = SettingsManager(settings_file=str(settings_file))

        stored = {}

        class WorkingKeyring(FakeKeyring):
            def set_password(self, service, name, value):
                stored[(service, name)] = value

        monkeypatch.setattr(settings_module, "keyring", WorkingKeyring(), raising=False)
        manager._use_keyring = True

        settings = AppSettings(api_key="AIza" + "x" * 30)
        assert manager.save(settings) is True

        data = json.loads(settings_file.read_text(encoding="utf-8"))
        assert "api_key" not in data
        assert stored  # key went to the keyring

    def test_stale_keyring_key_does_not_shadow_new_file_key(self, tmp_path, monkeypatch):
        """A key left in the keyring from an earlier save must not shadow a
        newer key that fell back to file storage after a transient failure."""
        store = {}

        class FlakyKeyring(FakeKeyring):
            fail_set = False

            def set_password(self, service, name, value):
                if self.fail_set:
                    raise RuntimeError("transient keyring failure")
                store[(service, name)] = value

            def get_password(self, service, name):
                return store.get((service, name))

            def delete_password(self, service, name):
                store.pop((service, name), None)

        fk = FlakyKeyring()
        monkeypatch.setattr(settings_module, "keyring", fk, raising=False)
        settings_file = tmp_path / "settings.json"
        manager = SettingsManager(settings_file=str(settings_file))
        manager._use_keyring = True

        manager.save(AppSettings(api_key="K1_OLD_KEY"))   # stored in keyring
        fk.fail_set = True
        manager.save(AppSettings(api_key="K2_NEW_KEY"))   # falls back to file

        assert manager.load().api_key == "K2_NEW_KEY"

    def test_key_saved_to_file_without_keyring(self, tmp_path):
        settings_file = tmp_path / "settings.json"
        manager = SettingsManager(settings_file=str(settings_file))
        manager._use_keyring = False

        settings = AppSettings(api_key="AIza" + "x" * 30)
        assert manager.save(settings) is True

        data = json.loads(settings_file.read_text(encoding="utf-8"))
        assert data.get("api_key") == settings.api_key


class TestSettingsRoundTrip:
    def test_non_key_settings_round_trip(self, tmp_path):
        settings_file = tmp_path / "settings.json"
        manager = SettingsManager(settings_file=str(settings_file))
        manager._use_keyring = False

        settings = AppSettings(
            api_key="AIza" + "x" * 30,
            filter_spam=False,
            spam_threshold=0.65,
            min_likes=5,
            max_comments=250,
            filter_words="python, tutorial",
            window_width=1024,
            window_height=768,
        )
        manager.save(settings)

        loaded = manager.load()
        assert loaded.filter_spam is False
        assert loaded.spam_threshold == 0.65
        assert loaded.min_likes == 5
        assert loaded.max_comments == 250
        assert loaded.filter_words == "python, tutorial"
        assert loaded.window_width == 1024
        assert loaded.window_height == 768

    def test_unknown_fields_ignored(self, tmp_path):
        settings_file = tmp_path / "settings.json"
        settings_file.write_text(
            json.dumps({"filter_spam": True, "some_future_field": 42}),
            encoding="utf-8",
        )
        manager = SettingsManager(settings_file=str(settings_file))
        manager._use_keyring = False

        loaded = manager.load()
        assert loaded.filter_spam is True
