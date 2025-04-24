import unittest
from unittest.mock import patch, MagicMock
import os
import sys
from src.main import download_and_upload_video  # Обновленный импорт


# --- Вспомогательные функции для тестов ---
def create_mock_gdrive_service():
    mock_service = MagicMock(name="MockGoogleDriveService")
    mock_files = MagicMock(name="MockFilesResource")
    mock_list_execute = MagicMock(name="list_execute")
    mock_files.list.return_value.execute = mock_list_execute
    mock_create = MagicMock(name="create")
    mock_files.create = mock_create

    # Создаем мок для запроса загрузки
    mock_upload_request = MagicMock(name="MediaUploadRequest")
    mock_upload_request.next_chunk.return_value = (
        None,
        {
            "id": "mock_file_id",
            "name": "mock_file.mp4",
            "webViewLink": "http://mock.link",
        },
    )

    def create_side_effect(body, media_body=None, fields=None):
        if media_body:
            return mock_upload_request
        else:
            mock_folder = MagicMock()
            mock_folder.get.return_value = "mock_folder_id"
            return mock_folder

    mock_create.side_effect = create_side_effect
    mock_service.files.return_value = mock_files
    return mock_service, mock_files, mock_upload_request


def create_mock_yadisk():
    mock_ydisk_instance = MagicMock(name="MockYaDiskInstance")
    mock_ydisk_instance.check_token.return_value = True
    mock_ydisk_instance.exists.return_value = False
    mock_ydisk_instance.mkdir = MagicMock(name="mkdir")
    mock_ydisk_instance.upload = MagicMock(name="upload")
    mock_ydisk_class = MagicMock(
        name="MockYaDiskClass", return_value=mock_ydisk_instance
    )
    return mock_ydisk_class, mock_ydisk_instance


def create_mock_ydl():
    mock_ydl_instance = MagicMock()
    mock_ydl_instance.__enter__.return_value = mock_ydl_instance
    mock_ydl_instance.extract_info.return_value = {
        "title": "Test Video",
        "ext": "mp4",
        "requested_downloads": [{"filepath": "/tmp/test.mp4"}],
    }
    return mock_ydl_instance


# --- Класс Интеграционных Тестов ---
@patch("shutil.rmtree")
@patch("os.makedirs")
@patch("os.path.exists")
@patch("yt_dlp.YoutubeDL")
@patch("yadisk.YaDisk")
@patch("googleapiclient.discovery.build")
@patch("googleapiclient.http.MediaFileUpload")
class TestMainFunctionIntegrationStrict(unittest.TestCase):
    """Интеграционные тесты для основной функции (строгое соответствие документации)."""

    def setUp(self):
        self.default_args_gdrive = {
            "video_url": "...",
            "cloud_storage": "Google Drive",
            "google_drive_folder_id": "root_strict",
            "cloud_folder_path": None,
            "upload_filename": None,
        }
        self.default_args_yandex = {
            "video_url": "...",
            "cloud_storage": "Yandex.Disk",
            "yandex_token": "mock_yandex_token",  # Изменено, так как USE_SECRET не используется
            "cloud_folder_path": "/Strict/Tests",
            "upload_filename": "strict_video",
        }
        self.created_temp_dir = None

    def tearDown(self):
        self.created_temp_dir = None

    def configure_os_path_exists(self, mock_os_path_exists, downloaded_file_path):
        def exists_side_effect(path):
            if downloaded_file_path and path == downloaded_file_path:
                return True
            if self.created_temp_dir and path == self.created_temp_dir:
                return True
            if path in ["/tmp", "/content"]:
                return True
            return False

        mock_os_path_exists.side_effect = exists_side_effect

    def configure_os_makedirs(self, mock_os_makedirs):
        def makedirs_side_effect(path, exist_ok=False):
            self.created_temp_dir = path
            return None

        mock_os_makedirs.side_effect = makedirs_side_effect

    # Аргументы соответствуют декораторам снизу вверх
    def test_gdrive_success(
        self,
        mock_MediaFileUpload_class,
        mock_build_func,
        mock_YaDisk_class,
        mock_YoutubeDL_class,
        mock_os_path_exists,
        mock_os_makedirs,
        mock_shutil_rmtree,
    ):
        """Тест: Успех YouTube -> GDrive (строгий)."""
        args = self.default_args_gdrive
        args["video_url"] = (
            "https://www.youtube.com/watch?v=test_gdrive_ok"  # Уникальный URL
        )
        downloaded_file_path = (
            "/mock_tmp/video_downloads_mock/strict-gdrive-video.webm"  # Пример пути
        )

        self.configure_os_makedirs(mock_os_makedirs)
        self.configure_os_path_exists(mock_os_path_exists, downloaded_file_path)

        mock_ydl_instance = mock_YoutubeDL_class.return_value.__enter__.return_value
        mock_ydl_instance.extract_info.side_effect = [
            {"title": "Strict GDrive Video", "ext": "webm", "id": "strict_g"},
            {"requested_downloads": [{"filepath": downloaded_file_path}]},
        ]
        mock_gdrive_service, mock_gdrive_files, mock_upload_request = (
            create_mock_gdrive_service()
        )
        mock_build_func.return_value = mock_gdrive_service
        mock_MediaFileUpload_instance = MagicMock(
            name="MockMediaFileUploadInstance_Strict"
        )
        mock_MediaFileUpload_class.return_value = mock_MediaFileUpload_instance
        mock_upload_request.next_chunk.return_value = (
            None,
            {
                "id": "strict_gdrive_id",
                "name": "Strict GDrive Video.webm",
                "webViewLink": "http://strict.link",
            },
        )

        def create_side_effect(body, media_body=None, fields=None):
            if media_body == mock_MediaFileUpload_instance:
                return mock_upload_request
            else:
                mock_folder = MagicMock()
                mock_folder.get.return_value = "strict_folder_id"
                return mock_folder

        mock_gdrive_files.create.side_effect = create_side_effect
        mock_gdrive_service.files.return_value.create = mock_gdrive_files.create

        result = download_and_upload_video(args)

        self.assertEqual(result["status"], "успех")
        self.assertEqual(result["cloud_identifier"], "strict_gdrive_id")
        self.assertEqual(result["cloud_filename"], "Strict GDrive Video.webm")
        mock_os_makedirs.assert_called_once()
        self.assertIsNotNone(self.created_temp_dir)
        mock_shutil_rmtree.assert_called_once_with(self.created_temp_dir)

    def test_yandex_success(
        self,
        mock_MediaFileUpload_class,
        mock_build_func,
        mock_YaDisk_class,
        mock_YoutubeDL_class,
        mock_os_path_exists,
        mock_os_makedirs,
        mock_shutil_rmtree,
    ):
        """Тест: Успех YouTube -> Yandex (строгий)."""
        args = self.default_args_yandex
        args["video_url"] = (
            "https://www.youtube.com/watch?v=test_yandex_ok"  # Уникальный URL
        )
        downloaded_file_path = (
            "/mock_tmp/video_downloads_mock/strict_video.mp4"  # Пример пути
        )

        self.configure_os_makedirs(mock_os_makedirs)
        self.configure_os_path_exists(mock_os_path_exists, downloaded_file_path)

        mock_ydl_instance = mock_YoutubeDL_class.return_value.__enter__.return_value
        mock_ydl_instance.extract_info.side_effect = [
            {"title": "Strict Яндекс", "ext": "mp4", "id": "strict_y"},
            {"requested_downloads": [{"filepath": downloaded_file_path}]},
        ]
        mock_yadisk_instance = mock_YaDisk_class.return_value
        mock_yadisk_instance.check_token.return_value = True
        mock_yadisk_instance.exists.return_value = False
        mock_yadisk_instance.upload.return_value = None

        result = download_and_upload_video(args)

        self.assertEqual(result["status"], "успех")
        self.assertEqual(result["cloud_identifier"], "/Strict/Tests/strict_video.mp4")
        self.assertEqual(result["cloud_filename"], "strict_video.mp4")
        mock_YaDisk_class.assert_called_once_with(token="mock_yandex_token")
        mock_yadisk_instance.upload.assert_called_once()
        self.assertIsNotNone(self.created_temp_dir)
        mock_shutil_rmtree.assert_called_once_with(self.created_temp_dir)

    def test_error_missing_video_url(
        self,
        mock_MediaFileUpload_class,
        mock_build_func,
        mock_YaDisk_class,
        mock_YoutubeDL_class,
        mock_os_path_exists,
        mock_os_makedirs,
        mock_shutil_rmtree,
    ):
        args = {"cloud_storage": "Google Drive", "google_drive_folder_id": "some_id"}
        result = download_and_upload_video(args)
        self.assertEqual(result["status"], "ошибка")
        self.assertIn("video_url и cloud_storage обязательны", result["message"])
        mock_shutil_rmtree.assert_not_called()
        mock_os_makedirs.assert_not_called()

    def test_error_download_fails(
        self,
        mock_MediaFileUpload_class,
        mock_build_func,
        mock_YaDisk_class,
        mock_YoutubeDL_class,
        mock_os_path_exists,
        mock_os_makedirs,
        mock_shutil_rmtree,
    ):
        """Тест: Ошибка на этапе скачивания (строгий)."""
        args = self.default_args_gdrive
        args["video_url"] = (
            "https://www.youtube.com/watch?v=test_dl_fail"  # Уникальный URL
        )

        self.configure_os_makedirs(mock_os_makedirs)
        self.configure_os_path_exists(mock_os_path_exists, None)

        mock_ydl_instance = mock_YoutubeDL_class.return_value.__enter__.return_value
        mock_ydl_instance.extract_info.side_effect = Exception("Generic download error")

        result = download_and_upload_video(args)

        self.assertEqual(result["status"], "ошибка")
        self.assertIn("Generic download error", result["message"])
        mock_os_makedirs.assert_called_once()
        self.assertIsNotNone(self.created_temp_dir)
        mock_shutil_rmtree.assert_called_once_with(self.created_temp_dir)

    def test_error_invalid_cloud_storage(self, *args):
        """Тест: Неверное значение cloud_storage"""
        args = self.default_args_gdrive.copy()
        args["cloud_storage"] = "Invalid Storage"
        result = download_and_upload_video(args)
        self.assertEqual(result["status"], "ошибка")
        self.assertIn("Неизвестное хранилище", result["message"])

    def test_error_missing_google_drive_folder_id(self, *args):
        """Тест: Отсутствие google_drive_folder_id для Google Drive"""
        args = self.default_args_gdrive.copy()
        del args["google_drive_folder_id"]
        result = download_and_upload_video(args)
        self.assertEqual(result["status"], "ошибка")
        self.assertIn("video_url и cloud_storage обязательны", result["message"])

    def test_special_characters_in_filename(self, *args):
        """Тест: Обработка специальных символов в имени файла"""
        args = self.default_args_gdrive.copy()
        args["upload_filename"] = "Video with special chars: *?<>|"
        mock_ydl = create_mock_ydl()
        mock_gdrive_service, mock_gdrive_files, mock_upload_request = (
            create_mock_gdrive_service()
        )

        with patch("yt_dlp.YoutubeDL", return_value=mock_ydl), patch(
            "googleapiclient.discovery.build", return_value=mock_gdrive_service
        ):
            result = download_and_upload_video(args)

        self.assertEqual(result["status"], "успех")
        self.assertNotIn("*", result["cloud_filename"])
        self.assertNotIn("?", result["cloud_filename"])
        self.assertNotIn("<", result["cloud_filename"])
        self.assertNotIn(">", result["cloud_filename"])
        self.assertNotIn("|", result["cloud_filename"])

    def test_long_filename_handling(self, *args):
        """Тест: Обработка длинных имен файлов"""
        args = self.default_args_gdrive.copy()
        args["upload_filename"] = "a" * 196  # Только имя без расширения
        mock_ydl = create_mock_ydl()
        mock_gdrive_service, mock_gdrive_files, mock_upload_request = (
            create_mock_gdrive_service()
        )

        mock_upload_request.next_chunk.return_value = (
            None,
            {
                "id": "long_filename_id",
                "name": "a" * 196 + ".mp4",
                "webViewLink": "http://mock.link",
            },
        )

        with patch("yt_dlp.YoutubeDL", return_value=mock_ydl), patch(
            "googleapiclient.discovery.build", return_value=mock_gdrive_service
        ):
            result = download_and_upload_video(args)

            self.assertEqual(result["status"], "успех")
            self.assertLessEqual(len(result["cloud_filename"]), 200)
            self.assertEqual(result["cloud_identifier"], "long_filename_id")

    def test_nested_folder_creation_gdrive(self, *args):
        """Тест: Создание вложенных папок в Google Drive"""
        args = self.default_args_gdrive.copy()
        args["cloud_folder_path"] = "Parent/Child/Grandchild"
        mock_ydl = create_mock_ydl()
        mock_gdrive_service, mock_gdrive_files, mock_upload_request = (
            create_mock_gdrive_service()
        )

        mock_list_execute = MagicMock()
        mock_list_execute.get.return_value = [{"id": "parent_id", "name": "Parent"}]
        mock_gdrive_files.list.return_value.execute = mock_list_execute

        with patch("yt_dlp.YoutubeDL", return_value=mock_ydl), patch(
            "googleapiclient.discovery.build", return_value=mock_gdrive_service
        ):
            result = download_and_upload_video(args)

        self.assertEqual(result["status"], "успех")

    def test_nested_folder_creation_yandex(self, *args):
        """Тест: Создание вложенных папок в Яндекс.Диске"""
        args = self.default_args_yandex.copy()
        args["cloud_folder_path"] = "/Parent/Child/Grandchild"
        mock_ydl = create_mock_ydl()
        mock_yadisk = MagicMock()
        mock_yadisk.exists.return_value = False
        mock_yadisk.mkdir.return_value = None
        with patch("yt_dlp.YoutubeDL", return_value=mock_ydl), patch(
            "yadisk.YaDisk", return_value=mock_yadisk
        ):
            result = download_and_upload_video(args)
        self.assertEqual(result["status"], "успех")

    def test_yandex_token_expired(self, *args):
        """Тест: Просроченный токен Яндекс.Диска"""
        args = self.default_args_yandex.copy()
        mock_ydl = create_mock_ydl()
        mock_yadisk = MagicMock()
        mock_yadisk.check_token.return_value = False
        with patch("yt_dlp.YoutubeDL", return_value=mock_ydl), patch(
            "yadisk.YaDisk", return_value=mock_yadisk
        ):
            result = download_and_upload_video(args)
        self.assertEqual(result["status"], "ошибка")
        self.assertIn("Неверный токен Яндекс.Диска", result["message"])

    def test_gdrive_upload_retry(self, *args):
        """Тест: Повторные попытки загрузки в Google Drive при ошибках"""
        args = self.default_args_gdrive.copy()
        mock_ydl = create_mock_ydl()
        mock_gdrive_service, mock_gdrive_files, mock_upload_request = (
            create_mock_gdrive_service()
        )

        from googleapiclient.errors import HttpError
        mock_upload_request.next_chunk.side_effect = [
            HttpError(MagicMock(status=503), b"Service Unavailable"),
            (None, {"id": "retry_success_id", "name": "retry_success.mp4"}),
        ]

        with patch("yt_dlp.YoutubeDL", return_value=mock_ydl), patch(
            "googleapiclient.discovery.build", return_value=mock_gdrive_service
        ):
            result = download_and_upload_video(args)

        self.assertEqual(result["status"], "успех")
        self.assertEqual(result["cloud_identifier"], "retry_success_id")

    def test_temp_dir_cleanup_on_error(self, *args):
        """Тест: Очистка временных файлов при ошибке"""
        args = self.default_args_gdrive.copy()
        mock_ydl = create_mock_ydl()
        mock_ydl.extract_info.side_effect = Exception("Test error")
        with patch("yt_dlp.YoutubeDL", return_value=mock_ydl):
            result = download_and_upload_video(args)
        self.assertEqual(result["status"], "ошибка")
        self.assertIn("Test error", result["message"])

    def test_large_file_handling(self, *args):
        """Тест: Обработка больших файлов"""
        args = self.default_args_gdrive.copy()
        mock_ydl = create_mock_ydl()
        mock_gdrive_service, mock_gdrive_files, mock_upload_request = (
            create_mock_gdrive_service()
        )

        mock_upload_request.next_chunk.side_effect = [
            (MagicMock(progress=lambda: 0.5), None),
            (None, {"id": "large_file_id", "name": "large_file.mp4"}),
        ]

        with patch("yt_dlp.YoutubeDL", return_value=mock_ydl), patch(
            "googleapiclient.discovery.build", return_value=mock_gdrive_service
        ):
            result = download_and_upload_video(args)

        self.assertEqual(result["status"], "успех")
        self.assertEqual(result["cloud_identifier"], "large_file_id")


if __name__ == "__main__":
    unittest.main()