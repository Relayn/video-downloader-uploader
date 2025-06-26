import logging
import sys
from typing import Optional
from logging.handlers import RotatingFileHandler
from pathlib import Path


def setup_logger(name: str, level: str = "INFO", to_file: bool = False, file_path: Optional[str] = None,
                 max_bytes: int = 5 * 1024 * 1024, backup_count: int = 3) -> logging.Logger:
    """
    Настраивает логгер с выводом в stdout и/или файл с поддержкой ротации,
    расширенного форматирования и динамического изменения уровня логирования.
    """
    logger = logging.getLogger(name)
    if logger.hasHandlers():
        logger.handlers.clear()
    formatter = logging.Formatter(
        "%(asctime)s - %(levelname)s - %(name)s - %(module)s.%(funcName)s:%(lineno)d - %(message)s"
    )
    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(formatter)
    logger.addHandler(stream_handler)

    if to_file and file_path:
        try:
            log_dir = Path(file_path).parent
            log_dir.mkdir(parents=True, exist_ok=True)

            file_handler = RotatingFileHandler(file_path, maxBytes=max_bytes, backupCount=backup_count,
                                               encoding="utf-8")
            file_handler.setFormatter(formatter)
            logger.addHandler(file_handler)
        except (OSError, IOError) as e:
            # Добавим вывод в консоль, если логгер еще не полностью настроен
            print(f"CRITICAL: Не удалось создать файловый логгер для '{file_path}': {e}")
            logger.critical(f"Не удалось создать файловый логгер: {e}")

    logger.setLevel(getattr(logging, level.upper(), logging.INFO))
    logger.propagate = False
    return logger


def set_logger_level(name: str, level: str):
    """Динамически меняет уровень логирования для указанного логгера."""
    logger = logging.getLogger(name)
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))