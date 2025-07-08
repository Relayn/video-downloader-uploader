import logging
import pytest
from unittest.mock import patch, MagicMock
from src.logger import setup_logger, set_logger_level
from pathlib import Path


@pytest.fixture(autouse=True)
def cleanup_loggers():
    """Фикстура для очистки логгеров после каждого теста."""
    yield
    # Удаляем все обработчики из всех логгеров, чтобы тесты не влияли друг на друга
    for name in logging.root.manager.loggerDict:
        if name.startswith("test_"):
            logging.getLogger(name).handlers.clear()


def test_setup_logger_stdout_only():
    """Тест: логгер создается только с выводом в stdout по умолчанию."""
    logger = setup_logger("test_stdout", level="DEBUG")

    assert isinstance(logger, logging.Logger)
    assert logger.name == "test_stdout"
    assert logger.level == logging.DEBUG
    assert len(logger.handlers) == 1
    assert isinstance(logger.handlers[0], logging.StreamHandler)
    assert not logger.propagate


def test_setup_logger_with_file_logging(tmp_path):
    """Тест: логгер корректно настраивает логирование в файл."""
    log_file = tmp_path / "test.log"
    logger = setup_logger("test_file", to_file=True, file_path=log_file)

    assert len(logger.handlers) == 2
    file_handler = logger.handlers[1]
    assert isinstance(file_handler, logging.handlers.RotatingFileHandler)
    assert file_handler.baseFilename == str(log_file)

    # Проверяем, что в файл что-то пишется
    logger.info("Test message")
    assert log_file.exists()
    assert "Test message" in log_file.read_text(encoding="utf-8")


def test_setup_logger_creates_log_directory(tmp_path):
    """Тест: setup_logger создает родительскую директорию для файла лога."""
    log_dir = tmp_path / "new_logs_dir"
    log_file = log_dir / "app.log"

    assert not log_dir.exists()
    setup_logger("test_dir_creation", to_file=True, file_path=log_file)
    assert log_dir.exists()
    assert log_dir.is_dir()


@patch("src.logger.RotatingFileHandler")
def test_setup_logger_handles_io_error_on_file_creation(mock_handler, capsys):
    """Тест: обработка ошибки IOError при создании файлового обработчика."""
    mock_handler.side_effect = IOError("Permission denied")
    from pathlib import Path
    log_path = Path("/protected/path.log")

    # Используем patch на print, чтобы проверить вывод в консоль
    with patch("builtins.print") as mock_print:
        logger = setup_logger("test_io_error", to_file=True, file_path=log_path)

        # Логгер должен быть создан, но только с одним (консольным) обработчиком
        assert len(logger.handlers) == 1
        # Проверяем, что было вызвано логирование критической ошибки
        expected_message = f"CRITICAL: Не удалось создать файловый логгер для '{log_path}': Permission denied"
        mock_print.assert_called_with(expected_message)


def test_setup_logger_clears_existing_handlers():
    """Тест: повторный вызов setup_logger очищает старые обработчики."""
    logger_name = "test_reconfig"
    # Первый вызов
    logger1 = setup_logger(logger_name, level="INFO")
    assert len(logger1.handlers) == 1

    # Второй вызов
    logger2 = setup_logger(logger_name, level="DEBUG")
    assert logger1 is logger2  # Должен быть тот же самый объект логгера
    assert len(logger2.handlers) == 1  # А не 2
    assert logger2.level == logging.DEBUG


def test_set_logger_level():
    """Тест: функция set_logger_level корректно меняет уровень логгера."""
    logger_name = "test_level_change"
    logger = setup_logger(logger_name, level="INFO")
    assert logger.level == logging.INFO

    set_logger_level(logger_name, "WARNING")
    assert logger.level == logging.WARNING


def test_set_logger_level_with_invalid_level():
    """Тест: set_logger_level использует INFO при некорректном уровне."""
    logger_name = "test_invalid_level"
    logger = setup_logger(logger_name, level="DEBUG")
    assert logger.level == logging.DEBUG

    set_logger_level(logger_name, "BOGUS_LEVEL")
    assert logger.level == logging.INFO  # Должен вернуться к INFO по умолчанию