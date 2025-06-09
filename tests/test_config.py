import pytest
import os
import logging
from pathlib import Path
from pydantic import ValidationError, SecretStr

# Импортируем то, что будем тестировать
from src.config import AppSettings, get_config, setup_logger, ConfigError


def test_get_config_creates_new_instance():
    """Проверяет, что get_config() создает новый экземпляр при каждом вызове."""
    c1 = get_config()
    c2 = get_config()
    assert c1 is not c2


def test_load_defaults(monkeypatch):
    """Проверяет, что без .env файла и переменных окружения загружаются значения по умолчанию."""
    # Гарантируем, что переменные окружения не установлены на время теста
    monkeypatch.delenv("LOG_LEVEL", raising=False)
    monkeypatch.delenv("LOG_TO_FILE", raising=False)
    config = AppSettings(_env_file=None)
    assert config.LOG_LEVEL == "INFO"
    assert config.LOG_TO_FILE is False


def test_load_from_dotenv_file(tmp_path, monkeypatch):
    """Проверяет, что настройки корректно загружаются из .env файла."""
    # Гарантируем, что переменные окружения не установлены на время теста
    monkeypatch.delenv("LOG_LEVEL", raising=False)
    monkeypatch.delenv("YANDEX_TOKEN", raising=False)
    env_content = "LOG_LEVEL=DEBUG\nLOG_TO_FILE=True\nYANDEX_TOKEN=my-secret-token"
    env_file = tmp_path / ".env.test"
    env_file.write_text(env_content)

    config = AppSettings(_env_file=env_file)
    assert config.LOG_LEVEL == "DEBUG"
    assert config.LOG_TO_FILE is True
    assert config.YANDEX_TOKEN.get_secret_value() == "my-secret-token"


def test_override_with_env_variables(monkeypatch, tmp_path):
    """Проверяет, что переменные окружения имеют приоритет над .env файлом."""
    env_content = "LOG_LEVEL=DEBUG"
    env_file = tmp_path / ".env.test"
    env_file.write_text(env_content)

    monkeypatch.setenv("LOG_LEVEL", "WARNING")

    config = AppSettings(_env_file=env_file)
    assert config.LOG_LEVEL == "WARNING"


def test_path_validation_file_exists(tmp_path):
    """Тест валидации FilePath для существующего файла."""
    ffmpeg_file = tmp_path / "ffmpeg.exe"
    ffmpeg_file.touch()

    config = AppSettings(FFMPEG_PATH=str(ffmpeg_file))
    assert config.FFMPEG_PATH == ffmpeg_file


def test_path_validation_file_not_exists(tmp_path):
    """Тест валидации FilePath для несуществующего файла (должен вызвать ошибку)."""
    ffmpeg_path = tmp_path / "ffmpeg.exe"
    with pytest.raises(ValidationError):
        AppSettings(FFMPEG_PATH=str(ffmpeg_path))


def test_save_and_reload_settings(tmp_path, monkeypatch):
    """
    Тест сохранения настроек в файл.
    Проверяет, что метод save_settings корректно записывает значения в .env файл.
    """
    # Гарантируем, что переменные окружения не будут мешать тесту
    monkeypatch.delenv("LOG_LEVEL", raising=False)
    monkeypatch.delenv("LOG_TO_FILE", raising=False)

    env_file = tmp_path / ".env.test"
    # Этот конфиг нам нужен только для вызова метода, его _env_file не важен
    config = AppSettings()

    # Сохраняем новые настройки, ЯВНО указывая путь
    new_settings = {"LOG_LEVEL": "CRITICAL", "LOG_TO_FILE": "True"}
    config.save_settings(new_settings, path=env_file)

    # Проверяем содержимое файла напрямую
    content = env_file.read_text()
    assert 'LOG_LEVEL="CRITICAL"' in content
    assert 'LOG_TO_FILE="True"' in content


def test_setup_logger(tmp_path):
    """Тест, что логгер создается и пишет в файл, если это указано."""
    log_file = tmp_path / "test.log"
    # Используем model_construct, чтобы не зависеть от существования файла при создании
    config = AppSettings.model_construct(LOG_TO_FILE=True, LOG_FILE_PATH=log_file)

    logger = setup_logger(
        "test_logger", config.LOG_LEVEL, config.LOG_TO_FILE, config.LOG_FILE_PATH
    )

    test_message = "This is a test message"
    logger.info(test_message)

    # Принудительно закрываем все обработчики, чтобы сбросить буфер в файл
    logging.shutdown()

    assert log_file.exists()
    with open(log_file, "r") as f:
        assert test_message in f.read()
