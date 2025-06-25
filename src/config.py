# src/config.py

import os
from pathlib import Path
from typing import Optional
from functools import lru_cache

from pydantic import SecretStr # <-- ДОБАВИТЬ ИМПОРТ
from pydantic_settings import BaseSettings, SettingsConfigDict
# python-dotenv нужен для set_key
from dotenv import set_key


class ConfigError(Exception):
    """Пользовательское исключение для ошибок конфигурации."""
    pass

# Определяем базовую директорию проекта
BASE_DIR = Path(__file__).resolve().parent.parent
# Путь к файлу .env
ENV_FILE_PATH = BASE_DIR / ".env"


class AppSettings(BaseSettings):
    """Модель настроек приложения с использованием Pydantic."""

    model_config = SettingsConfigDict(
        env_file_encoding="utf-8", extra="ignore"
    )

    # Настройки логгирования
    LOG_LEVEL: str = "INFO"
    LOG_TO_FILE: bool = False
    LOG_FILE_PATH: str = str(BASE_DIR / "logs" / "app.log")

    # Токены API
    # --- ИЗМЕНЕНИЕ: Используем SecretStr для безопасности ---
    YANDEX_DISK_TOKEN: Optional[SecretStr] = None

    # Пути к файлам аутентификации Google
    GOOGLE_CREDS_PATH: str = str(BASE_DIR / "credentials" / "google_creds.json")
    GOOGLE_TOKEN_PATH: str = str(BASE_DIR / "credentials" / "google_token.json")

    # Настройки прокси
    PROXY_URL: Optional[str] = None
    # Добавляем поле, которое было в тестах
    FFMPEG_PATH: Optional[str] = None


@lru_cache
def get_config() -> AppSettings:
    """
    Загружает конфигурацию и возвращает единственный экземпляр AppSettings.
    Использует кеширование для предотвращения повторного чтения .env файла.
    """
    try:
        # Передаем путь к .env файлу при создании экземпляра
        return AppSettings(_env_file=ENV_FILE_PATH)
    except Exception as e:
        raise ConfigError(f"Ошибка при валидации конфигурации: {e}") from e


def reload_config() -> AppSettings:
    """Перезагружает конфигурацию, очищая кеш, и возвращает новый экземпляр."""
    get_config.cache_clear()
    return get_config()


def save_specific_settings_to_env(settings_to_save: dict):
    """Сохраняет или обновляет указанные настройки в .env файле."""
    try:
        # --- ИЗМЕНЕНИЕ: Работаем с ENV_FILE_PATH, который можно подменить в тестах ---
        # Создаем файл, если его нет
        if not ENV_FILE_PATH.exists():
            ENV_FILE_PATH.touch()

        for key, value in settings_to_save.items():
            if value is not None:
                # set_key из python-dotenv корректно обработает кавычки и обновит файл
                set_key(str(ENV_FILE_PATH), key, str(value))

    except IOError as e:
        raise ConfigError(f"Ошибка при записи в .env файл: {e}") from e