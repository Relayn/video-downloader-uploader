import pytest
from unittest.mock import patch, MagicMock
from PySide6.QtWidgets import QApplication, QPushButton
from PySide6.QtCore import Qt
from src.config import AppSettings
from src.settings_dialog import SettingsDialog
from pathlib import Path


@pytest.fixture(scope="session")
def qapp():
    """Фикстура для создания единственного экземпляра QApplication на всю сессию."""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


@pytest.fixture
def mock_config(monkeypatch):
    """Фикстура для создания и внедрения мока AppSettings."""
    config_instance = AppSettings(
        YANDEX_DISK_TOKEN="test-yandex-token",
        GOOGLE_CREDS_PATH="/path/to/creds.json",
        GOOGLE_TOKEN_PATH="/path/to/token.json",
        PROXY_URL="http://proxy.test",
        LOG_LEVEL="DEBUG",
        LOG_TO_FILE=True,
        LOG_FILE_PATH="/logs/app.log",
    )
    monkeypatch.setattr("src.settings_dialog.get_config", lambda: config_instance)
    return config_instance


def test_settings_dialog_loads_settings_correctly(qapp, qtbot, mock_config):
    """
    Тест: проверяет, что диалог корректно загружает настройки из конфига в виджеты.
    """
    dialog = SettingsDialog()
    qtbot.addWidget(dialog)

    yandex_token = mock_config.YANDEX_DISK_TOKEN.get_secret_value()
    assert dialog.yandex_token_edit.text() == yandex_token
    assert dialog.google_creds_path_edit.text() == "/path/to/creds.json"
    assert dialog.google_token_path_edit.text() == "/path/to/token.json"
    assert dialog.proxy_url_edit.text() == "http://proxy.test"
    assert dialog.log_level_combo.currentText() == "DEBUG"
    assert dialog.log_to_file_check.isChecked() is True
    assert Path(dialog.log_file_path_edit.text()) == Path("/logs/app.log")


def test_settings_dialog_gathers_settings_data_correctly(qapp, qtbot, mock_config):
    """
    Тест: проверяет, что диалог правильно собирает измененные данные из виджетов.
    """
    dialog = SettingsDialog()
    qtbot.addWidget(dialog)

    dialog.yandex_token_edit.setText("new-yandex-token")
    dialog.google_creds_path_edit.setText("/new/creds.json")
    dialog.google_token_path_edit.setText("/new/token.json")
    dialog.proxy_url_edit.setText("")
    dialog.log_level_combo.setCurrentText("INFO")
    dialog.log_to_file_check.setChecked(False)
    dialog.log_file_path_edit.setText("/new/logs/app.log")

    settings_data = dialog.get_settings_data()

    assert settings_data["YANDEX_DISK_TOKEN"] == "new-yandex-token"
    assert settings_data["GOOGLE_CREDS_PATH"] == "/new/creds.json"
    assert settings_data["GOOGLE_TOKEN_PATH"] == "/new/token.json"
    assert settings_data["PROXY_URL"] is None
    assert settings_data["LOG_LEVEL"] == "INFO"
    assert settings_data["LOG_TO_FILE"] == "False"
    assert settings_data["LOG_FILE_PATH"] == "/new/logs/app.log"


@patch("src.settings_dialog.QFileDialog.getOpenFileName")
def test_browse_google_creds_file(mock_get_open_file_name, qapp, qtbot, mock_config):
    """Тест: нажатие кнопки '...' для выбора файла учетных данных Google."""
    dialog = SettingsDialog()
    qtbot.addWidget(dialog)

    expected_path = "/mock/path/to/credentials.json"
    mock_get_open_file_name.return_value = (expected_path, "")

    browse_button = dialog.findChild(QPushButton, "browse_creds_btn")
    qtbot.mouseClick(browse_button, Qt.MouseButton.LeftButton)

    mock_get_open_file_name.assert_called_once()
    assert dialog.google_creds_path_edit.text() == expected_path


@patch("src.settings_dialog.QFileDialog.getSaveFileName")
def test_browse_log_file(mock_get_save_file_name, qapp, qtbot, mock_config):
    """Тест: нажатие кнопки '...' для выбора файла логов."""
    dialog = SettingsDialog()
    qtbot.addWidget(dialog)

    expected_path = "/mock/path/to/app.log"
    mock_get_save_file_name.return_value = (expected_path, "")

    browse_button = dialog.findChild(QPushButton, "browse_log_btn")
    qtbot.mouseClick(browse_button, Qt.MouseButton.LeftButton)

    mock_get_save_file_name.assert_called_once()
    assert dialog.log_file_path_edit.text() == expected_path