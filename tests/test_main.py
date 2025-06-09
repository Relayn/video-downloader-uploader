import asyncio
from pathlib import Path
from unittest.mock import patch, MagicMock, ANY

import pytest

from src.config import ConfigError
from src.main import main


@pytest.fixture
def mock_config():
    """Фикстура для мока конфигурации."""
    config = MagicMock()
    config.LOG_LEVEL = "INFO"
    config.LOG_TO_FILE = False
    config.LOG_FILE_PATH = "test.log"
    config.TEMP_DIR_PREFIX = "test_downloader"
    return config


class TestMain:
    """Тесты для функции main в src/main.py."""

    @patch("src.main.show_gui")
    @patch("sys.argv", ["main.py"])
    def test_main_launches_gui_without_args(self, mock_show_gui):
        """
        Проверяет, что при запуске без аргументов вызывается GUI.
        """
        with pytest.raises(SystemExit):
            main()
        mock_show_gui.assert_called_once()

    @patch("src.main.upload_to_yandex_disk")
    @patch("src.main.upload_to_google_drive")
    @patch("src.main.download_video")
    @patch("src.main.setup_logger")
    @patch("src.main.get_config")
    @patch("tempfile.TemporaryDirectory")
    @patch(
        "sys.argv",
        [
            "main.py",
            "--url",
            "http://test.video",
            "--cloud",
            "google",
            "--path",
            "/test/path",
        ],
    )
    def test_cli_google_drive_success(
        self,
        mock_temp_dir,
        mock_get_config,
        mock_setup_logger,
        mock_download_video,
        mock_upload_google,
        mock_upload_yandex,
        mock_config,
    ):
        """
        Тестирует успешный сценарий CLI с загрузкой на Google Drive.
        """
        mock_get_config.return_value = mock_config
        mock_temp_dir.return_value.__enter__.return_value = "/tmp/testdir"
        mock_download_video.return_value = Path("/tmp/testdir/video.mp4")

        main()

        mock_download_video.assert_called_once_with(
            "http://test.video", Path("/tmp/testdir")
        )
        mock_upload_google.assert_called_once_with(
            Path("/tmp/testdir/video.mp4"), "/test/path", "video.mp4"
        )
        mock_upload_yandex.assert_not_called()

    @patch("asyncio.run")
    @patch("src.main.upload_to_yandex_disk", new_callable=MagicMock)
    @patch("src.main.upload_to_google_drive")
    @patch("src.main.download_video")
    @patch("src.main.setup_logger")
    @patch("src.main.get_config")
    @patch("tempfile.TemporaryDirectory")
    @patch(
        "sys.argv",
        [
            "main.py",
            "--url",
            "http://test.video",
            "--cloud",
            "yandex",
            "--path",
            "/test/path",
        ],
    )
    def test_cli_yandex_disk_success(
        self,
        mock_temp_dir,
        mock_get_config,
        mock_setup_logger,
        mock_download_video,
        mock_upload_google,
        mock_upload_yandex,
        mock_asyncio_run,
        mock_config,
    ):
        """
        Тестирует успешный сценарий CLI с загрузкой на Яндекс.Диск.
        """
        mock_get_config.return_value = mock_config
        mock_temp_dir.return_value.__enter__.return_value = "/tmp/testdir"
        mock_download_video.return_value = Path("/tmp/testdir/video.mp4")

        # Мокируем асинхронную функцию
        async def dummy_upload(*args, **kwargs):
            return "http://yandex.disk/link"

        mock_upload_yandex.return_value = dummy_upload()

        main()

        mock_download_video.assert_called_once_with(
            "http://test.video", Path("/tmp/testdir")
        )
        # Проверяем, что asyncio.run был вызван с нужным корутином
        mock_asyncio_run.assert_called_once()
        # Проверяем, что сама функция была вызвана с нужными параметрами внутри run
        mock_upload_yandex.assert_called_once_with(
            Path("/tmp/testdir/video.mp4"), "/test/path", "video.mp4"
        )
        mock_upload_google.assert_not_called()

    @patch("src.main.setup_logger")
    @patch("src.main.get_config")
    @patch("sys.argv", ["main.py", "--url", "http://test.video"])
    def test_cli_no_url_fails(self, mock_get_config, mock_setup_logger, mock_config):
        """
        Тестирует, что CLI падает, если не указан --url.
        """
        # Этот тест на самом деле проверяет отсутствие --url, но sys.argv мокает его наличие.
        # Изменим argv, чтобы он соответствовал цели теста.
        with patch("sys.argv", ["main.py", "--cloud", "google"]):
            mock_get_config.return_value = mock_config
            mock_logger = MagicMock()
            mock_setup_logger.return_value = mock_logger

            with pytest.raises(SystemExit) as e:
                main()

            assert e.value.code == 1
            mock_logger.error.assert_called_with(
                "Аргумент --url обязателен для режима CLI."
            )

    @patch("src.main.get_config")
    @patch("sys.argv", ["main.py", "--url", "http://test.video"])
    def test_cli_config_error_fails(self, mock_get_config):
        """
        Тестирует, что CLI падает при ошибке конфигурации.
        """
        mock_get_config.side_effect = ConfigError("Test config error")
        with pytest.raises(SystemExit) as e:
            main()
        assert e.value.code == 1

    @patch("src.main.download_video")
    @patch("src.main.setup_logger")
    @patch("src.main.get_config")
    @patch("tempfile.TemporaryDirectory")
    @patch("sys.argv", ["main.py", "--url", "http://test.video"])
    def test_cli_download_failure_fails(
        self,
        mock_temp_dir,
        mock_get_config,
        mock_setup_logger,
        mock_download_video,
        mock_config,
    ):
        """
        Тестирует, что CLI падает, если скачивание видео не удалось.
        """
        mock_get_config.return_value = mock_config
        mock_temp_dir.return_value.__enter__.return_value = "/tmp/testdir"
        mock_download_video.return_value = None  # Симулируем ошибку скачивания
        mock_logger = MagicMock()
        mock_setup_logger.return_value = mock_logger

        with pytest.raises(SystemExit) as e:
            main()

        assert e.value.code == 1
        mock_logger.critical.assert_called_with(
            "Критическая ошибка в режиме CLI: Скачивание не удалось, файл не был получен.",
            exc_info=True,
        )
