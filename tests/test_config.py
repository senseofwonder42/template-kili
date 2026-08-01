from kili_examples.config import Settings, get_settings


def test_settings_are_loaded_from_a_dotenv_file(tmp_path):
    """Values defined in a .env file end up in the settings."""
    env_file = tmp_path / ".env"
    env_file.write_text("RANDOM_SEED=1234\n")

    settings = Settings(_env_file=env_file)

    assert settings.random_seed == 1234


def test_settings_fall_back_to_their_defaults():
    """Without a .env file, the declared defaults apply."""
    settings = Settings(_env_file=None)

    assert settings.random_seed == 42
    assert settings.log_level == "INFO"


def test_get_settings_is_cached():
    """The accessor does not rebuild the settings on every call."""
    assert get_settings() is get_settings()
