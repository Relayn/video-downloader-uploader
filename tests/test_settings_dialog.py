import pytest
from unittest.mock import patch, MagicMock
from pathlib import Path
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QPushButton

from src.config import AppSettings
from src.settings_dialog import SettingsDialog


@pytest.fixture
def mock_dialog_config(monkeypatch, tmp_path):
    """
    Фикстура для мокирования get_config в модуле settings_dialog.
    Она также создает временные файлы, чтобы валидация Pydantic проходила успешно.
    """

    def _setup_mock_config(**kwargs):
        # Если FFMPEG_PATH передан и это не None, создаем временный файл
        if "FFMPEG_PATH" in kwargs and kwargs["FFMPEG_PATH"]:
            ffmpeg_file = tmp_path / kwargs["FFMPEG_PATH"]
            ffmpeg_file.touch()
            # Обновляем значение в kwargs на полный путь
            kwargs["FFMPEG_PATH"] = str(ffmpeg_file)

        # Создаем экземпляр с валидацией, так как виджеты ожидают рабочую конфигурацию
        settings = AppSettings(_env_file=None, **kwargs)

        # Мокаем get_config, чтобы он возвращал наши созданные настройки
        monkeypatch.setattr("src.settings_dialog.get_config", lambda: settings)
        return settings

    return _setup_mock_config


def test_dialog_loads_settings(qtbot, mock_dialog_config, tmp_path):
    """Тест, что диалог корректно загружает настройки при инициализации."""
    # Создаем фейковый ffmpeg, чтобы валидация пути прошла
    ffmpeg_exe = tmp_path / "ffmpeg.exe"
    ffmpeg_exe.touch()

    # Настраиваем мок конфигурации
    mock_dialog_config(
        FFMPEG_PATH=str(ffmpeg_exe),
        LOG_TO_FILE=True,
        LOG_FILE_PATH="/test/app.log",
        YANDEX_TOKEN="test_token",
        YTDLP_FORMAT="best",
    )

    dialog = SettingsDialog()
    qtbot.addWidget(dialog)

    assert dialog.ffmpeg_path_edit.line_edit.text() == str(ffmpeg_exe)
    assert dialog.log_to_file_checkbox.isChecked()
    assert dialog.log_file_path_edit.line_edit.text() == "/test/app.log"
    assert dialog.yandex_token_edit.text() == "test_token"
    assert dialog.ytdlp_format_edit.text() == "best"


def test_dialog_gathers_data(qtbot, mock_dialog_config):
    """Тест, что get_settings_data корректно собирает данные из полей."""
    # Загружаем с настройками по умолчанию
    mock_dialog_config()
    dialog = SettingsDialog()
    qtbot.addWidget(dialog)

    # Имитируем ввод пользователя
    new_ffmpeg = "/new/ffmpeg"
    new_log_path = "/new/log.txt"
    new_yandex_token = "new_token"

    dialog.ffmpeg_path_edit.line_edit.setText(new_ffmpeg)
    dialog.log_to_file_checkbox.setChecked(True)
    dialog.log_file_path_edit.line_edit.setText(new_log_path)
    dialog.yandex_token_edit.setText(new_yandex_token)

    data = dialog.get_settings_data()

    assert data["FFMPEG_PATH"] == new_ffmpeg
    assert data["LOG_TO_FILE"] is True
    assert data["LOG_FILE_PATH"] == new_log_path
    assert data["YANDEX_TOKEN"] == new_yandex_token


@patch("PySide6.QtWidgets.QFileDialog.getOpenFileName")
def test_select_ffmpeg_path_dialog(mock_get_open_file_name, qtbot, mock_dialog_config):
    """Тест работы диалога выбора файла для ffmpeg."""
    mock_dialog_config()
    dialog = SettingsDialog()
    qtbot.addWidget(dialog)

    expected_path = "/path/to/ffmpeg"
    mock_get_open_file_name.return_value = (expected_path, "All files (*)")

    # Нажимаем на кнопку выбора файла
    button = dialog.ffmpeg_path_edit.findChild(QPushButton)
    qtbot.mouseClick(button, Qt.LeftButton)

    mock_get_open_file_name.assert_called_once()
    assert dialog.ffmpeg_path_edit.line_edit.text() == expected_path
