# tests/test_main.py

import pytest
from unittest.mock import patch, MagicMock, AsyncMock

from src.main import main
# --- ИЗМЕНЕНИЕ: Добавлен недостающий импорт ---
from src.config import ConfigError


@pytest.fixture
def mock_cli_config(monkeypatch):
    """Фикстура для мокирования get_config для CLI-тестов."""
    mock_config_instance = MagicMock()
    mock_config_instance.LOG_LEVEL = "INFO"
    mock_config_instance.LOG_TO_FILE = False
    mock_config_instance.LOG_FILE_PATH = "/tmp/test.log"
    monkeypatch.setattr("src.main.get_config", lambda: mock_config_instance)
    return mock_config_instance


@patch('src.main.sys.argv', ['vdu-cli'])
@patch('src.main.show_gui')
def test_main_no_args_calls_gui(mock_show_gui):
    """Тест: вызов без аргументов запускает GUI."""
    with pytest.raises(SystemExit):
        main()
    mock_show_gui.assert_called_once()


@patch('src.main.sys.argv', ['vdu-cli', '--help'])
def test_main_with_help_arg_exits():
    """Тест: вызов с --help должен завершать программу."""
    with pytest.raises(SystemExit) as e:
        main()
    assert e.value.code == 0


@patch('src.main.sys.argv', ['vdu-cli', '--url', 'test_url'])
@patch('src.main.download_video')
@patch('src.main.upload_single_file')
def test_main_cli_no_cloud_only_downloads(mock_upload, mock_download, mock_cli_config, tmp_path):
    """Тест: CLI без --cloud только скачивает файл."""
    mock_download.return_value = {"status": "успех", "path": tmp_path / "video.mp4"}
    main()
    mock_download.assert_called_once()
    mock_upload.assert_not_called()


@patch('src.main.sys.argv', ['vdu-cli', '--url', 'test_url', '--cloud', 'Google Drive', '--path', 'gdrive_folder'])
@patch('src.main.download_video')
@patch('src.main.upload_single_file', new_callable=AsyncMock)
@patch('asyncio.run')
def test_main_cli_with_cloud_calls_uploader(mock_asyncio_run, mock_upload, mock_download, mock_cli_config, tmp_path):
    """Тест: CLI с --cloud вызывает единый загрузчик."""
    video_file = tmp_path / "video.mp4"
    video_file.touch()
    mock_download.return_value = {"status": "успех", "path": video_file}
    mock_asyncio_run.return_value = {"status": "успех"}

    main()

    mock_download.assert_called_once()
    mock_upload.assert_called_once_with({
        "file_path": str(video_file),
        "cloud_storage": "Google Drive",
        "cloud_folder_path": "gdrive_folder",
        "filename": "video.mp4",
    })
    mock_asyncio_run.assert_called_once()


@patch('src.main.sys.argv', ['vdu-cli', '--cloud', 'Google Drive'])
def test_main_cli_missing_url_exits():
    """Тест: CLI без --url должен завершаться с ошибкой."""
    with pytest.raises(SystemExit) as e:
        main()
    assert e.value.code == 1


@patch('src.main.sys.argv', ['vdu-cli', '--url', 'test_url'])
@patch('src.main.download_video')
def test_main_cli_handles_download_exception(mock_download, mock_cli_config):
    """Тест: CLI корректно обрабатывает исключение при скачивании."""
    mock_download.return_value = {"status": "ошибка", "error": "Download failed"}
    with pytest.raises(SystemExit) as e:
        main()
    assert e.value.code == 1


@patch('src.main.sys.argv', ['vdu-cli', '--url', 'test_url', '--cloud', 'Google Drive'])
@patch('src.main.download_video')
@patch('asyncio.run')
def test_main_cli_handles_upload_exception(mock_asyncio_run, mock_download, mock_cli_config, tmp_path):
    """Тест: CLI корректно обрабатывает исключение при загрузке."""
    video_file = tmp_path / "video.mp4"
    video_file.touch()
    mock_download.return_value = {"status": "успех", "path": video_file}
    mock_asyncio_run.return_value = {"status": "ошибка", "error": "Upload failed"}

    with pytest.raises(SystemExit) as e:
        main()
    assert e.value.code == 1


@patch('src.main.sys.argv', ['vdu-cli', '--url', 'test_url'])
@patch('src.main.get_config')
def test_main_cli_handles_config_error(mock_get_config):
    """Тест: CLI корректно обрабатывает ошибку конфигурации."""
    mock_get_config.side_effect = ConfigError("Test config error")
    with pytest.raises(SystemExit) as e:
        main()
    assert e.value.code == 1