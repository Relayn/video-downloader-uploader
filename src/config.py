import os
from dotenv import load_dotenv
from typing import Optional
from src.logger import setup_logger

logger = setup_logger("config", level=os.getenv("LOG_LEVEL", "INFO"), to_file=os.getenv("LOG_TO_FILE", "False").lower() in ("1", "true", "yes"), file_path=os.getenv("LOG_FILE_PATH", "app.log"))

class ConfigError(Exception):
    pass

class AppConfig:
    _instance = None
    _loaded = False

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance.reload()
        return cls._instance

    def reload(self):
        load_dotenv(override=True)
        self.TEMP_DIR_PREFIX = os.getenv("TEMP_DIR_PREFIX", "temp_")
        self.LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
        self.LOG_TO_FILE = os.getenv("LOG_TO_FILE", "False").lower() in ("1", "true", "yes")
        self.LOG_FILE_PATH = os.getenv("LOG_FILE_PATH", "app.log")
        self.YTDLP_FORMAT = os.getenv("YTDLP_FORMAT", "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best")
        try:
            self.YTDLP_RETRIES = int(os.getenv("YTDLP_RETRIES", "3"))
        except ValueError:
            logger.error("YTDLP_RETRIES должно быть целым числом. Используется значение по умолчанию 3.")
            self.YTDLP_RETRIES = 3
        self.GOOGLE_CREDENTIALS = os.getenv("GOOGLE_CREDENTIALS", "../credentials.json")
        self.YANDEX_TOKEN = os.getenv("YANDEX_TOKEN", None)
        AppConfig._loaded = True

    @classmethod
    def get(cls) -> 'AppConfig':
        if not cls._instance or not cls._loaded:
            cls._instance = AppConfig()
        return cls._instance

    def validate(self):
        errors = []
        if not self.GOOGLE_CREDENTIALS or not os.path.exists(self.GOOGLE_CREDENTIALS):
            errors.append(f"GOOGLE_CREDENTIALS не найден: {self.GOOGLE_CREDENTIALS}")
        if not self.YTDLP_FORMAT:
            errors.append("YTDLP_FORMAT не задан")
        if errors:
            for err in errors:
                logger.error(err)
            raise ConfigError("Ошибки конфигурации: " + "; ".join(errors))

# Для совместимости с текущим кодом:
config = AppConfig.get()
TEMP_DIR_PREFIX = config.TEMP_DIR_PREFIX
LOG_LEVEL = config.LOG_LEVEL
LOG_TO_FILE = config.LOG_TO_FILE
LOG_FILE_PATH = config.LOG_FILE_PATH
YTDLP_FORMAT = config.YTDLP_FORMAT
YTDLP_RETRIES = config.YTDLP_RETRIES
GOOGLE_CREDENTIALS = config.GOOGLE_CREDENTIALS
YANDEX_TOKEN = config.YANDEX_TOKEN
