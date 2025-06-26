import os
import pytest
from unittest.mock import patch
from pydantic import SecretStr
from dotenv import dotenv_values
from src import config
from src.config import AppSettings, get_config, reload_config, save_specific_settings_to_env, ConfigError


@pytest.fixture(autouse=True)
def cleanup_config_cache():
    """Фикстура для автоматической очистки кеша get_config перед каждым тестом."""
    get_config.cache_clear()
    yield


@pytest.fixture
def mock_env_file(tmp_path, monkeypatch):
    """Фикстура для создания временного .env файла и подмены пути к нему."""
    env_path = tmp_path / ".env"
    monkeypatch.setattr(config, "ENV_FILE_PATH", env_path)
    return env_path


def test_app_settings_default_values(mock_env_file, monkeypatch):
    """Тест, что AppSettings использует значения по умолчанию, если нет других источников."""
    monkeypatch.delenv("LOG_LEVEL", raising=False)

    settings = get_config()

    assert settings.LOG_LEVEL == "INFO"
    assert settings.LOG_TO_FILE is False


def test_app_settings_load_from_env_file(mock_env_file):
    """Тест, что AppSettings корректно загружает значения из .env файла."""
    mock_env_file.write_text(
        'LOG_LEVEL="DEBUG"\n'
        'YANDEX_DISK_TOKEN="my-secret-token"'
    )

    settings = get_config()

    assert settings.LOG_LEVEL == "DEBUG"
    assert isinstance(settings.YANDEX_DISK_TOKEN, SecretStr)
    assert settings.YANDEX_DISK_TOKEN.get_secret_value() == "my-secret-token"


def test_app_settings_env_variable_overrides_file(mock_env_file, monkeypatch):
    """Тест, что переменная окружения имеет приоритет над .env файлом."""
    mock_env_file.write_text('LOG_LEVEL="DEBUG"')
    monkeypatch.setenv("LOG_LEVEL", "WARNING")

    settings = get_config()

    assert settings.LOG_LEVEL == "WARNING"


def test_get_config_is_cached(mock_env_file):
    """Тест, что get_config() кеширует результат и возвращает один и тот же объект."""
    config1 = get_config()
    config2 = get_config()

    assert config1 is config2


def test_reload_config_clears_cache(mock_env_file, monkeypatch):
    """Тест, что reload_config() сбрасывает кеш и загружает новые значения."""
    monkeypatch.setenv("LOG_LEVEL", "INFO")
    config1 = get_config()
    assert config1.LOG_LEVEL == "INFO"

    monkeypatch.setenv("LOG_LEVEL", "DEBUG")
    config2 = get_config()
    assert config2.LOG_LEVEL == "INFO"
    assert config1 is config2

    config3 = reload_config()
    assert config3.LOG_LEVEL == "DEBUG"
    assert config1 is not config3


def test_save_settings_creates_new_file(mock_env_file):
    """Тест, что save_specific_settings_to_env создает .env, если его нет."""
    assert not mock_env_file.exists()

    save_specific_settings_to_env({"FFMPEG_PATH": "C:/ffmpeg/bin"})

    assert mock_env_file.exists()
    content = mock_env_file.read_text()
    assert 'FFMPEG_PATH' in content
    assert 'C:/ffmpeg/bin' in content


def test_save_settings_updates_existing_file(mock_env_file):
    """Тест, что save_specific_settings_to_env обновляет и добавляет значения."""
    mock_env_file.write_text(
        'LOG_LEVEL="INFO"\n'
        'PROXY_URL="http://old.proxy"\n'
    )

    settings_to_save = {
        "LOG_LEVEL": "DEBUG",
        "FFMPEG_PATH": "/usr/bin/ffmpeg"
    }
    save_specific_settings_to_env(settings_to_save)
    result = dotenv_values(mock_env_file)

    assert result["LOG_LEVEL"] == "DEBUG"
    assert result["PROXY_URL"] == "http://old.proxy"
    assert result["FFMPEG_PATH"] == "/usr/bin/ffmpeg"


@patch("src.config.set_key")
def test_save_settings_raises_config_error_on_io_error(mock_set_key, mock_env_file):
    """Тест, что save_specific_settings_to_env выбрасывает ConfigError при ошибке ввода-вывода."""
    mock_set_key.side_effect = IOError("Disk full")

    with pytest.raises(ConfigError, match="Ошибка при записи в .env файл: Disk full"):
        save_specific_settings_to_env({"LOG_LEVEL": "FAIL"})

@patch("src.config.AppSettings")
def test_get_config_raises_config_error_on_validation_error(MockAppSettings, mock_env_file):
    """Тест, что get_config выбрасывает ConfigError при ошибке валидации Pydantic."""
    MockAppSettings.side_effect = Exception("Pydantic validation failed")

    with pytest.raises(ConfigError, match="Ошибка при валидации конфигурации: Pydantic validation failed"):
        get_config()