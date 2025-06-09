import pytest
from unittest.mock import patch
from PySide6.QtWidgets import QApplication
from src.config import AppSettings


# Фикстура для QApplication, нужна для любых тестов с виджетами
@pytest.fixture(scope="session")
def qt_app():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


@patch("src.gui.get_config")
def test_gui_initialization(mock_get_config, qt_app):
    """
    Простой тест, который проверяет, что GUI инициализируется без ошибок.
    """
    # Возвращаем "чистый" конфиг, чтобы избежать проблем с .env
    mock_get_config.return_value = AppSettings(_env_file=None)

    from src.gui import VideoUploaderGUI

    # Пытаемся создать экземпляр GUI
    try:
        window = VideoUploaderGUI()
        # Если мы дошли сюда, значит, __init__ отработал без падений.
        assert window is not None
        assert window.windowTitle() == "Video Downloader & Uploader"
    except Exception as e:
        pytest.fail(f"Не удалось инициализировать VideoUploaderGUI: {e}")
