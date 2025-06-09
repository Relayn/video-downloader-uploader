import pytest
import asyncio
from unittest.mock import patch, MagicMock, AsyncMock, call, ANY
from pathlib import Path
from src import uploader
from src.uploader import (
    upload_to_yandex_disk,
    upload_to_google_drive,
    slugify_filename,
    UploadError,
    create_gdrive_folders_chain,
    batch_upload_to_cloud,
)
from src.config import AppSettings


@pytest.fixture
def mock_config(monkeypatch):
    """Мокает get_config для uploader'а."""
    settings = AppSettings.model_construct()  # Создаем модель без валидации
    monkeypatch.setattr(uploader, "get_config", lambda: settings)
    return settings


# --- Тесты для slugify_filename ---


def test_slugify_filename():
    assert slugify_filename("Тестовое видео (1).mp4") == "testovoe-video-1.mp4"
    assert slugify_filename("  a b c  .txt") == "a-b-c.txt"


# --- Тесты для Yandex.Disk ---


@pytest.mark.asyncio
@patch("src.uploader.get_yandex_token", return_value="fake_token")
@patch("src.uploader.yadisk_async.YaDisk")
async def test_upload_yandex_disk_success(mock_yadisk, mock_get_token, tmp_path):
    """Тест успешной загрузки на Яндекс.Диск."""
    file_path = tmp_path / "video.mp4"
    file_path.touch()

    mock_disk_instance = AsyncMock()
    mock_disk_instance.check_token.return_value = True
    mock_disk_instance.exists.return_value = False  # Папка не существует
    # Настроим __aenter__ для возврата нашего асинхронного мока
    mock_yadisk.return_value.__aenter__.return_value = mock_disk_instance

    remote_path = await upload_to_yandex_disk(file_path, "test/folder", "video.mp4")

    expected_path = "/test/folder/video.mp4"
    assert remote_path == expected_path
    mock_disk_instance.exists.assert_called_once_with("/test/folder")
    mock_disk_instance.mkdir.assert_called_once_with("/test/folder")
    mock_disk_instance.upload.assert_called_once_with(
        str(file_path), expected_path, overwrite=True
    )


@pytest.mark.asyncio
@patch("src.uploader.get_yandex_token", return_value=None)
async def test_upload_yandex_disk_no_token(mock_get_token, tmp_path):
    """Тест ошибки, если токен Yandex отсутствует."""
    file_path = tmp_path / "video.mp4"
    file_path.touch()
    with pytest.raises(UploadError, match="Токен Яндекс.Диска не найден"):
        await upload_to_yandex_disk(file_path, "folder", "video.mp4")


# --- Тесты для Google Drive ---


@patch("src.uploader.get_google_drive_credentials")
@patch("src.uploader.build")
@patch("src.uploader.create_gdrive_folders_chain", return_value="final_folder_id")
def test_upload_google_drive_success(
    mock_create_folders, mock_build, mock_get_creds, tmp_path
):
    """Тест успешной загрузки на Google Drive."""
    file_path = tmp_path / "video.mp4"
    file_path.touch()

    mock_service = MagicMock()
    mock_build.return_value = mock_service
    mock_create_method = mock_service.files().create
    mock_create_method.return_value.execute.return_value = {"id": "gdrive_file_id"}

    file_id = upload_to_google_drive(file_path, "Test/Videos", "video.mp4")

    assert file_id == "gdrive_file_id"
    mock_create_folders.assert_called_once_with(mock_service, "root", "Test/Videos")

    # Проверяем вызов create с правильными параметрами, игнорируя media_body
    mock_create_method.assert_called_once_with(
        body={"name": "video.mp4", "parents": ["final_folder_id"]},
        media_body=ANY,
        fields="id",
    )
    mock_create_method.return_value.execute.assert_called_once()

    # Проверяем, что метод create был вызван с правильными параметрами
    mock_service.files().create.assert_called_once_with(
        body={"name": "video.mp4", "parents": ["final_folder_id"]},
        media_body=ANY,  # Используем ANY, т.к. объект MediaFileUpload сложно мокать
        fields="id",
    )


def test_create_gdrive_folders_chain(monkeypatch):
    """Тест создания цепочки папок."""
    mock_service = MagicMock()
    # Мокируем внутреннюю функцию, которую рекурсивно вызывает create_gdrive_folders_chain
    mock_find_or_create = MagicMock(side_effect=["id_A", "id_B", "id_C"])
    monkeypatch.setattr(uploader, "_find_or_create_gdrive_folder", mock_find_or_create)

    final_id = create_gdrive_folders_chain(
        mock_service, "root", "FolderA/FolderB/FolderC"
    )

    assert final_id == "id_C"
    assert mock_find_or_create.call_count == 3
    mock_find_or_create.assert_has_calls(
        [
            call(mock_service, "FolderA", "root"),
            call(mock_service, "FolderB", "id_A"),
            call(mock_service, "FolderC", "id_B"),
        ]
    )


# --- Тесты для batch_upload_to_cloud ---


@pytest.mark.asyncio
@patch("src.uploader.upload_to_google_drive", return_value="gdrive_id")
@patch(
    "src.uploader.upload_to_yandex_disk",
    new_callable=AsyncMock,
    return_value="/yandex/path",
)
async def test_batch_upload_mixed(mock_yandex_upload, mock_gdrive_upload, tmp_path):
    """Тест пакетной загрузки в разные облака."""
    # Создаем фиктивные файлы
    file1 = tmp_path / "gdrive.mp4"
    file1.touch()
    file2 = tmp_path / "yandex.mp4"
    file2.touch()

    tasks = [
        {
            "cloud_storage": "Google Drive",
            "file_path": file1,
            "cloud_folder_path": "Google",
            "filename": "gdrive.mp4",
        },
        {
            "cloud_storage": "Yandex.Disk",
            "file_path": file2,
            "cloud_folder_path": "Yandex",
            "filename": "yandex.mp4",
        },
    ]

    results = await batch_upload_to_cloud(tasks)

    # Проверяем, что оба результата успешны
    assert len(results) == 2
    gdrive_result = next(r for r in results if r["storage"] == "Google Drive")
    yandex_result = next(r for r in results if r["storage"] == "Yandex.Disk")

    assert gdrive_result["status"] == "успех"
    assert gdrive_result["id"] == "gdrive_id"
    assert yandex_result["status"] == "успех"
    assert yandex_result["path"] == "/yandex/path"

    mock_gdrive_upload.assert_called_once_with(file1, "Google", "gdrive.mp4")
    mock_yandex_upload.assert_called_once_with(file2, "Yandex", "yandex.mp4")
