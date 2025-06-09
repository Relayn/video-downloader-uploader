import pytest
import logging
import os
import time
from pathlib import Path
from unittest.mock import patch, mock_open

from src.logger import setup_logger, set_logger_level

TEST_LOGGER_NAME = "test_app_logger"
TEST_LOG_FILE = "test_app_log.log"


@pytest.fixture
def cleanup_logger():
    """Очищает логгер после теста, чтобы избежать влияния на другие тесты."""
    logger = logging.getLogger(TEST_LOGGER_NAME)
    original_handlers = list(logger.handlers)
    original_level = logger.level
    original_propagate = logger.propagate
    yield
    logger.handlers = original_handlers
    logger.setLevel(original_level)
    logger.propagate = original_propagate
    if hasattr(logging.Logger.manager, "loggerDict"):
        if TEST_LOGGER_NAME in logging.Logger.manager.loggerDict:
            # Это удаляет логгер из словаря logging,
            # так что при следующем getLogger он будет создан заново (без старых хендлеров/уровня)
            del logging.Logger.manager.loggerDict[TEST_LOGGER_NAME]
    if os.path.exists(TEST_LOG_FILE):
        try:
            os.remove(TEST_LOG_FILE)
        except (
            PermissionError
        ):  # Может возникнуть на Windows, если файл еще используется
            time.sleep(0.1)
            try:
                os.remove(TEST_LOG_FILE)
            except Exception as e:
                print(f"Не удалось удалить тестовый лог-файл {TEST_LOG_FILE}: {e}")


@pytest.fixture(autouse=True)
def ensure_logging_fully_configured():
    """
    Эта фикстура гарантирует, что глобальное состояние logging полностью сконфигурировано.
    Без этого, первый вызов getLogger может сконфигурировать root логгер с базовыми настройками,
    что может помешать некоторым тестам, особенно если они ожидают определенного поведения
    от "чистой" системы логирования.
    """
    logging.basicConfig(
        force=True
    )  # Перезаписывает любую существующую конфигурацию root логгера
    # Очистим handlers у root логгера, чтобы они не мешали
    logging.getLogger().handlers.clear()
    yield


def test_setup_logger_basic(cleanup_logger):
    """Тест базовой настройки логгера (только stdout)."""
    logger = setup_logger(TEST_LOGGER_NAME, level="INFO")
    assert logger.name == TEST_LOGGER_NAME
    assert logger.level == logging.INFO
    assert len(logger.handlers) == 1
    assert isinstance(logger.handlers[0], logging.StreamHandler)
    assert logger.propagate is False
    # Проверка формата (частичная, проверяем наличие ключевых элементов)
    formatter_str = logger.handlers[0].formatter._fmt
    assert "%(asctime)s" in formatter_str
    assert "%(levelname)s" in formatter_str
    assert "%(name)s" in formatter_str
    assert "%(module)s.%(funcName)s:%(lineno)d" in formatter_str
    assert "%(message)s" in formatter_str


def test_setup_logger_with_file(tmp_path, cleanup_logger):
    """Тест настройки логгера с выводом в файл."""
    log_file = tmp_path / "test_app.log"
    logger = setup_logger(
        TEST_LOGGER_NAME,
        level="DEBUG",
        to_file=True,
        file_path=str(log_file),
        max_bytes=1024,
        backup_count=2,
    )

    assert logger.level == logging.DEBUG
    assert len(logger.handlers) == 2  # StreamHandler + RotatingFileHandler

    file_handler = None
    for handler in logger.handlers:
        if isinstance(handler, logging.handlers.RotatingFileHandler):
            file_handler = handler
            break

    assert file_handler is not None
    assert file_handler.baseFilename == str(log_file)
    assert file_handler.maxBytes == 1024
    assert file_handler.backupCount == 2
    assert file_handler.encoding == "utf-8"


def test_setup_logger_handler_clearing(cleanup_logger):
    """Тест очистки обработчиков при повторном вызове setup_logger."""
    logger1 = setup_logger(TEST_LOGGER_NAME, level="INFO")
    assert len(logger1.handlers) == 1
    # Добавим "мусорный" обработчик вручную
    logger1.addHandler(logging.NullHandler())
    assert len(logger1.handlers) == 2

    # Повторный вызов setup_logger должен очистить старые и добавить свои
    logger2 = setup_logger(TEST_LOGGER_NAME, level="DEBUG")
    assert len(logger2.handlers) == 1  # Только новый StreamHandler
    assert logger2.level == logging.DEBUG


def test_set_logger_level(cleanup_logger):
    """Тест динамического изменения уровня логирования."""
    logger = setup_logger(TEST_LOGGER_NAME, level="INFO")
    assert logger.level == logging.INFO

    set_logger_level(TEST_LOGGER_NAME, "DEBUG")
    assert logger.level == logging.DEBUG

    set_logger_level(TEST_LOGGER_NAME, "WARNING")
    assert logger.level == logging.WARNING

    # Тест с невалидным уровнем (должен установиться INFO по умолчанию в getattr)
    set_logger_level(TEST_LOGGER_NAME, "INVALID_LEVEL_XYZ")
    assert logger.level == logging.INFO  # Проверяем, что установился INFO


def test_log_messages_stdout(caplog, cleanup_logger):
    """Тест записи сообщений в stdout в соответствии с уровнем INFO.
    DEBUG сообщения не должны попадать в вывод, INFO и WARNING должны.
    """
    logger = setup_logger(
        TEST_LOGGER_NAME, level="INFO", to_file=False
    )  # Устанавливаем уровень INFO, не пишем в файл
    logger.propagate = True  # Для корректной работы caplog

    # caplog по умолчанию захватывает то, что производит логгер с учетом его уровня
    logger.debug("Это debug сообщение")
    logger.info("Это info сообщение")
    logger.warning("Это warning сообщение")
    logger.error("Это error сообщение")
    logger.critical("Это critical сообщение")

    assert "Это debug сообщение" not in caplog.text
    assert "Это info сообщение" in caplog.text
    assert "Это warning сообщение" in caplog.text
    assert "Это error сообщение" in caplog.text
    assert "Это critical сообщение" in caplog.text

    # Проверим также записи caplog.records
    debug_records = [r for r in caplog.records if r.levelname == "DEBUG"]
    info_records = [r for r in caplog.records if r.levelname == "INFO"]
    warning_records = [r for r in caplog.records if r.levelname == "WARNING"]

    assert not debug_records
    assert len(info_records) == 1
    assert info_records[0].message == "Это info сообщение"
    assert len(warning_records) == 1
    assert warning_records[0].message == "Это warning сообщение"


def test_log_messages_to_file(tmp_path, cleanup_logger):
    """Тест записи сообщений в файл."""
    log_file = tmp_path / "app.log"
    logger = setup_logger(
        TEST_LOGGER_NAME, level="DEBUG", to_file=True, file_path=str(log_file)
    )

    logger.debug("Файловое debug сообщение")
    logger.info("Файловое info сообщение")

    # Закрываем обработчики, чтобы убедиться, что все записалось на диск
    for handler in logger.handlers:
        handler.close()

    assert log_file.exists()
    content = log_file.read_text(encoding="utf-8")

    assert "Файловое debug сообщение" in content
    assert "Файловое info сообщение" in content
    assert f"DEBUG - {TEST_LOGGER_NAME} - " in content
    assert f"INFO - {TEST_LOGGER_NAME} - " in content


def test_log_rotation(tmp_path, cleanup_logger):
    """Тест ротации лог-файлов."""
    log_file_base = "rotate.log"
    log_file = tmp_path / log_file_base
    # Маленький max_bytes для быстрой ротации, достаточно для одного сообщения + формат
    # Формат: "%(asctime)s - %(levelname)s - %(name)s - %(module)s.%(funcName)s:%(lineno)d - %(message)s"
    # Длина формата примерно 80-100 символов. Сообщение ~20 символов.
    # Пусть max_bytes будет 150, чтобы одно сообщение влезло, а второе вызвало ротацию.
    logger = setup_logger(
        TEST_LOGGER_NAME,
        level="INFO",
        to_file=True,
        file_path=str(log_file),
        max_bytes=150,
        backup_count=2,
    )

    # Сообщение, которое точно поместится
    msg1 = "Сообщение для ротации 1"
    logger.info(msg1)
    for handler in logger.handlers:  # Закрываем, чтобы гарантировать запись
        if isinstance(handler, logging.handlers.RotatingFileHandler):
            handler.flush()
            handler.close()

    assert log_file.exists()
    # logger = setup_logger(TEST_LOGGER_NAME, level="INFO", to_file=True, file_path=str(log_file),
    #                       max_bytes=150, backup_count=2) # Переоткрываем логгер или просто продолжаем с тем же

    # Сообщение, которое вызовет ротацию
    msg2 = "Сообщение для ротации 2, которое длиннее"
    logger.info(msg2)  # Это сообщение должно пойти в новый файл
    for handler in logger.handlers:  # Закрываем, чтобы гарантировать запись
        if isinstance(handler, logging.handlers.RotatingFileHandler):
            handler.flush()
            handler.close()

    # Проверяем наличие основного файла и бэкапа
    assert (tmp_path / f"{log_file_base}.1").exists()

    # Содержимое текущего файла (должно быть msg2)
    content_current = log_file.read_text(encoding="utf-8")
    assert msg2 in content_current
    assert msg1 not in content_current  # msg1 должен быть в бэкапе

    # Содержимое бэкапа (должно быть msg1)
    content_backup = (tmp_path / f"{log_file_base}.1").read_text(encoding="utf-8")
    assert msg1 in content_backup
    assert msg2 not in content_backup

    # Еще одно сообщение для проверки backup_count
    msg3 = "Сообщение для ротации 3"
    logger.info(msg3)
    for handler in logger.handlers:
        if isinstance(handler, logging.handlers.RotatingFileHandler):
            handler.flush()
            handler.close()

    assert (tmp_path / f"{log_file_base}.2").exists()  # msg1 должен быть тут
    content_backup2 = (tmp_path / f"{log_file_base}.2").read_text(encoding="utf-8")
    assert msg1 in content_backup2

    # Старый log_file_base.1 (теперь должен содержать msg2)
    content_backup1_new = (tmp_path / f"{log_file_base}.1").read_text(encoding="utf-8")
    assert msg2 in content_backup1_new

    # Текущий файл (должен содержать msg3)
    content_current_new = log_file.read_text(encoding="utf-8")
    assert msg3 in content_current_new


# Убран лишний тег </rewritten_file> отсюда
