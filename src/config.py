import logging
import os
from typing import Literal, Optional
from pathlib import Path

from pydantic import field_validator, FilePath, SecretStr, Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# ==============================================================================
# Логгер
# ==============================================================================

# Словарь для кэширования логгеров, чтобы избежать дублирования хендлеров
_loggers: dict[str, logging.Logger] = {}


def setup_logger(
    name: str,
    level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO",
    to_file: bool = False,
    file_path: str = "app.log",
) -> logging.Logger:
    """Настраивает и возвращает именованный логгер."""
    if name in _loggers:
        return _loggers[name]

    logger = logging.getLogger(name)
    logger.setLevel(level)
    logger.propagate = False  # Предотвращаем двойное логирование в root логгер

    # Очищаем существующие хендлеры, чтобы избежать их накопления при перезагрузке
    if logger.hasHandlers():
        logger.handlers.clear()

    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )

    if to_file:
        file_handler = logging.FileHandler(file_path, encoding="utf-8")
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    _loggers[name] = logger
    return logger


# ==============================================================================
# Конфигурация Pydantic
# ==============================================================================


class ConfigError(Exception):
    """Пользовательское исключение для ошибок, связанных с конфигурацией."""

    pass


class AppSettings(BaseSettings):
    """Определяет все настройки приложения, загружаемые из .env и переменных окружения."""

    TEMP_DIR_PREFIX: str = "temp_"
    LOG_LEVEL: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    LOG_TO_FILE: bool = False
    LOG_FILE_PATH: str = "app.log"
    YTDLP_FORMAT: str = "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best"
    YTDLP_RETRIES: int = 3
    FFMPEG_PATH: Optional[FilePath] = None
    GOOGLE_CREDENTIALS: Optional[FilePath] = None
    YANDEX_TOKEN: Optional[SecretStr] = Field(None, alias="YANDEX_TOKEN")

    def save_settings(self, new_settings: dict, path: str | Path) -> None:
        """
        Сохраняет переданные настройки в указанный файл, перезаписывая его.
        Создает файл, если он не существует.

        Args:
            new_settings: Словарь с настройками для сохранения.
            path: Путь к файлу, в который нужно сохранить настройки.
        """
        env_path = Path(path)
        lines = [f'{key}="{value}"' for key, value in new_settings.items()]
        env_path.write_text("\n".join(lines), encoding="utf-8")

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        validate_assignment=True,
        extra="forbid",
    )

    @field_validator("LOG_LEVEL", mode="before")
    @classmethod
    def _normalize_log_level(cls, value: str) -> str:
        return value.upper() if isinstance(value, str) else value


# ==============================================================================
# Ленивая ("ленивая") инициализация и доступ к конфигурации
# ==============================================================================

logger = setup_logger("config")


def get_config() -> AppSettings:
    """
    Создает и возвращает новый экземпляр настроек AppSettings.

    Returns:
        Экземпляр конфигурации AppSettings.

    Raises:
        ConfigError: Если происходит ошибка валидации Pydantic.
    """
    try:
        return AppSettings()
    except Exception as e:
        # Логирование или обработка ошибки
        raise ConfigError(f"Ошибка при создании конфигурации: {e}") from e


def reload_config() -> AppSettings:
    """
    Перезагружает конфигурацию приложения и перенастраивает логгер.

    Returns:
        Новый экземпляр конфигурации.

    Raises:
        ConfigError: В случае ошибки при перезагрузке.
    """
    logger.info("Перезагрузка конфигурации...")
    try:
        # Создаем новый экземпляр, который перечитывает .env и переменные окружения
        new_config = AppSettings()

        # Перенастраиваем основной логгер с новыми параметрами
        setup_logger(
            "main",
            level=new_config.LOG_LEVEL,
            to_file=new_config.LOG_TO_FILE,
            file_path=new_config.LOG_FILE_PATH,
        )
        logger.info("Конфигурация успешно перезагружена.")
        return new_config
    except Exception as e:
        msg = f"Ошибка при перезагрузке конфигурации: {e}"
        logger.error(msg, exc_info=True)
        raise ConfigError(msg) from e


# ==============================================================================
# Утилиты для работы с .env
# ==============================================================================

ENV_FILE = ".env"


def save_specific_settings_to_env(settings_to_save: dict[str, str]) -> None:
    """
    Сохраняет или обновляет указанные настройки в файле .env,
    не затрагивая остальные переменные.

    Args:
        settings_to_save: Словарь с настройками для сохранения.
                          Ключ - имя переменной, значение - ее значение.
    """
    env_path = Path(ENV_FILE)
    env_vars = {}

    if env_path.exists():
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                env_vars[key.strip()] = value.strip()

    # Обновляем или добавляем переменные
    for key, value in settings_to_save.items():
        # Убираем кавычки, если они есть, и добавляем новые
        clean_value = str(value).strip("\"'")
        env_vars[key] = f'"{clean_value}"'

    # Готовим строки для записи
    lines = [f"{key}={value}" for key, value in env_vars.items()]

    try:
        env_path.write_text("\n".join(lines), encoding="utf-8")
        logger.info(f"Настройки {list(settings_to_save.keys())} сохранены в {ENV_FILE}")
    except IOError as e:
        logger.error(f"Не удалось сохранить настройки в {ENV_FILE}: {e}")
        raise
