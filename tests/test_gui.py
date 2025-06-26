import json
import pytest
from unittest.mock import patch, MagicMock

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QPushButton, QLineEdit, QDialog
from PySide6.QtGui import QCloseEvent

from src.config import AppSettings
from src.gui import VideoUploaderGUI


@pytest.fixture(scope="session")
def qapp():
    """Фикстура для создания единственного экземпляра QApplication на всю сессию."""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


@pytest.fixture
def main_window(qapp, qtbot, monkeypatch):
    """
    Фикстура для создания и настройки главного окна GUI для тестирования.
    - Мокирует конфигурацию, логгер и загрузку сессии.
    - Возвращает экземпляр VideoUploaderGUI.
    """
    config_instance = AppSettings()
    monkeypatch.setattr("src.gui.get_config", lambda: config_instance)

    mock_logger = MagicMock()
    monkeypatch.setattr("src.gui.setup_logger", lambda *args, **kwargs: mock_logger)

    with patch("src.gui.SESSION_FILE_PATH") as mock_path:
        mock_path.exists.return_value = False
        window = VideoUploaderGUI()
        qtbot.addWidget(window)
        window.show()
        qtbot.waitExposed(window)
        yield window


def test_initial_state(main_window):
    """Тест: проверяет начальное состояние виджетов при запуске."""
    assert main_window.start_btn.isEnabled() is True
    assert main_window.cancel_btn.isEnabled() is False
    assert main_window.settings_btn.isEnabled() is True
    assert main_window.progress_bar.isVisible() is False
    assert "Готов к работе" in main_window.status_label.text()


@pytest.mark.parametrize(
    "selection_text, expected_label, browse_visible",
    [
        ("Google Drive", "Папка в облаке (например, 'мое_видео/2024'):", False),
        ("Yandex.Disk", "Папка в облаке (например, 'мое_видео/2024'):", False),
        ("Сохранить локально", "Папка для сохранения:", True),
    ],
)
def test_cloud_selection_changes_ui(
        main_window, qtbot, selection_text, expected_label, browse_visible
):
    main_window.cloud_combo.setCurrentText(selection_text)
    qtbot.waitUntil(lambda: main_window.path_label.text() == expected_label)
    qtbot.waitUntil(lambda: main_window.browse_btn.isVisible() == browse_visible)
    assert main_window.path_label.text() == expected_label
    assert main_window.browse_btn.isVisible() == browse_visible


@patch("src.gui.QFileDialog.getExistingDirectory")
def test_select_local_folder_updates_line_edit(mock_get_dir, main_window, qtbot):
    """
    Тест: проверяет, что выбор локальной папки через диалог обновляет поле ввода.
    """
    main_window.cloud_combo.setCurrentText("Сохранить локально")
    qtbot.waitUntil(main_window.browse_btn.isVisible)
    expected_path = "C:/mock/path"
    mock_get_dir.return_value = expected_path
    qtbot.mouseClick(main_window.browse_btn, Qt.MouseButton.LeftButton)
    assert main_window.folder_edit.text() == expected_path
    mock_get_dir.assert_called_once()


@patch("src.gui.QMessageBox")
def test_start_processing_no_urls_shows_error(mock_qmessagebox, main_window):
    """
    Тест: вызов start_processing без URL должен показать QMessageBox и не запускать воркер.
    """
    main_window.url_edit.setText("")
    with patch.object(main_window.threadpool, 'start') as mock_start:
        main_window.start_processing()
        mock_start.assert_not_called()
        mock_qmessagebox.assert_called_once_with(main_window)
        msg_box_instance = mock_qmessagebox.return_value
        msg_box_instance.setText.assert_called_with("Пожалуйста, введите хотя бы один URL.")
        msg_box_instance.exec.assert_called_once()


@patch("src.gui.PreFlightCheckWorker")
def test_start_processing_with_urls_starts_worker(mock_preflight_worker, main_window):
    """
    Тест: вызов start_processing с URL-адресами должен запустить PreFlightCheckWorker.
    """
    main_window.url_edit.setText("https://some.url/video")
    with patch.object(main_window.threadpool, 'start') as mock_start:
        main_window.start_processing()
        assert main_window.start_btn.isEnabled() is False
        assert main_window.settings_btn.isEnabled() is False
        assert main_window.status_label.text() == "Выполнение предполетных проверок..."
        mock_preflight_worker.assert_called_once_with(
            cloud=main_window.cloud_combo.currentText(),
            path=main_window.folder_edit.text()
        )
        mock_start.assert_called_once_with(mock_preflight_worker.return_value)


@patch("src.gui.QMessageBox")
def test_on_pre_flight_finished_failure(mock_qmessagebox, main_window):
    """
    Тест: слот on_pre_flight_finished при ошибке (is_ok=False)
    восстанавливает GUI и показывает сообщение.
    """
    main_window.start_btn.setEnabled(False)
    main_window.settings_btn.setEnabled(False)
    error_message = "FFMPEG не найден."
    main_window.on_pre_flight_finished(False, error_message)
    assert main_window.start_btn.isEnabled() is True
    assert main_window.settings_btn.isEnabled() is True
    assert main_window.status_label.text() == "Готов к работе."
    mock_qmessagebox.assert_called_once()
    msg_box_instance = mock_qmessagebox.return_value
    msg_box_instance.setText.assert_called_with(error_message)
    msg_box_instance.exec.assert_called_once()


@patch("src.gui.DownloadUploadWorker")
def test_on_pre_flight_finished_success_starts_main_worker(mock_main_worker, main_window, qtbot):
    """
    Тест: слот on_pre_flight_finished при успехе (is_ok=True)
    запускает основной воркер DownloadUploadWorker.
    """
    main_window.url_edit.setText("https://some.url/video")
    with patch.object(main_window.threadpool, 'start') as mock_start:
        main_window.on_pre_flight_finished(True, "")
        qtbot.waitUntil(main_window.progress_bar.isVisible, timeout=1000)
        assert main_window.status_label.text() == "Проверки пройдены. Запуск основной задачи..."
        assert main_window.cancel_btn.isEnabled() is True
        assert main_window.progress_bar.isVisible() is True
        assert main_window.progress_bar.value() == 0
        mock_main_worker.assert_called_once()
        mock_start.assert_called_once_with(mock_main_worker.return_value)


def test_update_progress(main_window):
    """Тест: слот update_progress корректно обновляет прогресс-бар и статус."""
    test_percent = 67
    test_message = "Скачивание видео 2/3..."
    main_window.update_progress(test_percent, test_message)
    assert main_window.progress_bar.value() == test_percent
    assert main_window.status_label.text() == test_message
    assert "color: black;" in main_window.status_label.styleSheet()


def test_on_error(main_window):
    """Тест: слот on_error корректно отображает сообщение об ошибке."""
    error_message = "Не удалось подключиться к серверу."
    main_window.on_error(error_message)
    assert main_window.status_label.text() == f"Ошибка: {error_message}"
    assert "color: red;" in main_window.status_label.styleSheet()


@patch("src.gui.QMessageBox")
def test_on_finished_success(mock_qmessagebox, main_window):
    """
    Тест: слот on_finished при успешном завершении восстанавливает GUI
    и показывает информационное сообщение.
    """
    main_window.start_btn.setEnabled(False)
    main_window.settings_btn.setEnabled(False)
    main_window.cancel_btn.setEnabled(True)
    main_window.progress_bar.setVisible(True)
    download_results = [{'status': 'успех'}, {'status': 'ошибка'}]
    upload_results = [{'status': 'успех'}]
    main_window.on_finished(download_results, upload_results, is_cancelled=False)
    assert main_window.start_btn.isEnabled() is True
    assert main_window.settings_btn.isEnabled() is True
    assert main_window.cancel_btn.isEnabled() is False
    assert main_window.progress_bar.isVisible() is False
    assert main_window.status_label.text() == "Готово!"
    assert "color: green;" in main_window.status_label.styleSheet()
    mock_qmessagebox.information.assert_called_once()
    args, _ = mock_qmessagebox.information.call_args
    report_text = args[2]
    assert "Скачано файлов: 1 из 2" in report_text
    assert "Загружено в облако: 1 из 1" in report_text


@patch("src.gui.QMessageBox")
def test_on_finished_cancelled(mock_qmessagebox, main_window):
    """
    Тест: слот on_finished при отмене операции восстанавливает GUI
    и показывает сообщение об отмене.
    """
    main_window.start_btn.setEnabled(False)
    main_window.settings_btn.setEnabled(False)
    main_window.cancel_btn.setEnabled(True)
    main_window.progress_bar.setVisible(True)
    main_window.on_finished([], [], is_cancelled=True)
    assert main_window.start_btn.isEnabled() is True
    assert main_window.settings_btn.isEnabled() is True
    assert main_window.cancel_btn.isEnabled() is False
    assert main_window.progress_bar.isVisible() is False
    assert main_window.status_label.text() == "Операция отменена."
    assert "color: orange;" in main_window.status_label.styleSheet()
    mock_qmessagebox.warning.assert_called_once_with(
        main_window, "Отменено", "Операция была отменена пользователем."
    )


def test_cancel_processing(main_window):
    """Тест: метод cancel_processing устанавливает флаг и блокирует кнопку."""
    main_window.cancel_btn.setEnabled(True)
    main_window.cancellation_flag.reset()

    main_window.cancel_processing()

    assert main_window.cancellation_flag.is_set() is True
    assert main_window.cancel_btn.isEnabled() is False
    assert "Отмена операции..." in main_window.status_label.text()


@patch("src.gui.save_specific_settings_to_env")
@patch("src.gui.reload_config")
@patch("src.gui.setup_logger")
@patch("src.gui.SettingsDialog")
def test_open_settings_accepted(mock_dialog_class, mock_setup_logger, mock_reload_config, mock_save_settings, main_window):
    """Тест: открытие и принятие диалога настроек вызывает сохранение и перезагрузку."""
    mock_dialog_instance = mock_dialog_class.return_value
    mock_dialog_instance.exec.return_value = QDialog.Accepted
    mock_dialog_instance.get_settings_data.return_value = {"LOG_LEVEL": "DEBUG"}

    main_window.open_settings()

    mock_dialog_class.assert_called_once_with(main_window)
    mock_save_settings.assert_called_once_with({"LOG_LEVEL": "DEBUG"})
    mock_reload_config.assert_called_once()
    mock_setup_logger.assert_called_once()


@patch("src.gui.save_specific_settings_to_env")
@patch("src.gui.reload_config")
@patch("src.gui.SettingsDialog")
def test_open_settings_rejected(mock_dialog_class, mock_reload_config, mock_save_settings, main_window):
    """Тест: отклонение диалога настроек не вызывает никаких действий."""
    mock_dialog_instance = mock_dialog_class.return_value
    mock_dialog_instance.exec.return_value = QDialog.Rejected

    main_window.open_settings()

    mock_dialog_class.assert_called_once_with(main_window)
    mock_save_settings.assert_not_called()
    mock_reload_config.assert_not_called()


def test_save_session_state(main_window, monkeypatch, tmp_path):
    """Тест: save_session_state корректно сохраняет состояние GUI в JSON."""
    session_file = tmp_path / "session.json"
    monkeypatch.setattr("src.gui.SESSION_FILE_PATH", session_file)

    main_window.url_edit.setText("url1\nurl2")
    main_window.cloud_combo.setCurrentIndex(1)
    main_window.quality_combo.setCurrentIndex(2)
    main_window.folder_edit.setText("/my/path")
    main_window.filename_edit.setText("template")

    main_window.save_session_state()

    assert session_file.exists()
    with open(session_file, "r") as f:
        data = json.load(f)

    assert data["urls"] == "url1\nurl2"
    assert data["cloud_index"] == 1
    assert data["quality_index"] == 2
    assert data["path_text"] == "/my/path"
    assert data["template_text"] == "template"


def test_load_session_state(main_window, monkeypatch, tmp_path):
    """Тест: load_session_state корректно загружает состояние из JSON в GUI."""
    session_file = tmp_path / "session.json"
    monkeypatch.setattr("src.gui.SESSION_FILE_PATH", session_file)

    state = {
        "urls": "url3\nurl4",
        "cloud_index": 2,
        "quality_index": 3,
        "path_text": "/another/path",
        "template_text": "new_template",
    }
    session_file.write_text(json.dumps(state))

    main_window.load_session_state()

    assert main_window.url_edit.toPlainText() == state["urls"]
    assert main_window.cloud_combo.currentIndex() == state["cloud_index"]
    assert main_window.quality_combo.currentIndex() == state["quality_index"]
    assert main_window.folder_edit.text() == state["path_text"]
    assert main_window.filename_edit.text() == state["template_text"]


def test_close_event_triggers_save(main_window):
    """Тест: событие закрытия окна вызывает сохранение сессии."""
    with patch.object(main_window, 'save_session_state', wraps=main_window.save_session_state) as spy_save:
        close_event = QCloseEvent()
        close_event.ignore()

        main_window.closeEvent(close_event)

        spy_save.assert_called_once()