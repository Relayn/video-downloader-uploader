import logging
import sys
from typing import Optional
from logging.handlers import RotatingFileHandler
from pathlib import Path


def setup_logger(name: str, level: str = "INFO", to_file: bool = False, file_path: Optional[Path] = None,
                 max_bytes: int = 5 * 1024 * 1024, backup_count: int = 3) -> logging.Logger:
    """
    Настраивает и возвращает логгер с заданными параметрами.

    Очищает существующие обработчики для предотвращения дублирования.
    Поддерживает вывод в stdout и/или в ротируемый файл.

    Args:
        name (str): Имя логгера.
        level (str): Уровень логирования (например, "INFO", "DEBUG").
        to_file (bool): Если True, логи будут записываться в файл.
        file_path (Optional[Path]): Путь к файлу логов. Обязателен, если to_file=True.
        max_bytes (int): Максимальный размер файла лога в байтах перед ротацией.
        backup_count (int): Количество хранимых архивных файлов лога.

    Returns:
        logging.Logger: Настроенный экземпляр логгера.
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
            log_dir = file_path.parent
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
    """
    Динамически изменяет уровень логирования для указанного логгера.

    Args:
        name (str): Имя логгера, уровень которого нужно изменить.
        level (str): Новый уровень логирования (например, "INFO", "DEBUG").
    """
    logger = logging.getLogger(name)
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))