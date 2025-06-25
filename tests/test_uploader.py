# tests/test_uploader.py

import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from pathlib import Path
import shutil
import os

from googleapiclient.errors import HttpError
# --- ИЗМЕНЕНИЕ 1: Новый импорт исключения ---
from yadisk.exceptions import YaDiskError

from src.uploader import (
    upload_single_file,
    UPLOADER_STRATEGIES,
    UploadError,
    YandexDiskUploaderStrategy,
    GoogleDriveUploaderStrategy,
    LocalSaveStrategy,
)

@pytest.fixture
def tmp_file(tmp_path):
    p = tmp_path / "test_video.mp4"
    p.write_text("dummy content")
    return p

@pytest.fixture
def mock_auth_getters(monkeypatch):
    yandex_mock = MagicMock(return_value="fake-yandex-token")
    google_mock = MagicMock(return_value=MagicMock())
    monkeypatch.setattr("src.uploader.get_yandex_token", yandex_mock)
    monkeypatch.setattr("src.uploader.get_google_drive_credentials", google_mock)
    return yandex_mock, google_mock

def test_upload_error_with_details():
    details = {"code": 500}
    err = UploadError("Test", details=details)
    assert err.details == details

# ==================================
# Тесты для YandexDiskUploaderStrategy
# ==================================
@pytest.mark.asyncio
# --- ИЗМЕНЕНИЕ 2: Обновлен путь для patch ---
@patch("src.uploader.yadisk.AsyncYaDisk")
async def test_yandex_upload_success(mock_yadisk, tmp_file, mock_auth_getters):
    mock_disk = AsyncMock()
    mock_disk.check_token.return_value = True
    mock_disk.exists.return_value = False
    mock_disk.get_download_link.return_value = "http://fake.link"
    mock_yadisk.return_value.__aenter__.return_value = mock_disk
    strategy = YandexDiskUploaderStrategy()
    result = await strategy.upload(tmp_file, "test_folder", "video.mp4")
    assert result["status"] == "успех"

@pytest.mark.asyncio
async def test_yandex_upload_no_token(mock_auth_getters):
    mock_auth_getters[0].return_value = None
    strategy = YandexDiskUploaderStrategy()
    with pytest.raises(UploadError, match="Токен Яндекс.Диска не найден"):
        await strategy.upload(MagicMock(), "folder", "file")

@pytest.mark.asyncio
@patch("src.uploader.yadisk.AsyncYaDisk")
async def test_yandex_upload_invalid_token(mock_yadisk, tmp_file, mock_auth_getters):
    mock_disk = AsyncMock()
    mock_disk.check_token.return_value = False
    mock_yadisk.return_value.__aenter__.return_value = mock_disk
    strategy = YandexDiskUploaderStrategy()
    with pytest.raises(UploadError, match="Токен Яндекс.Диска невалиден"):
        await strategy.upload(tmp_file, "folder", "video.mp4")

@pytest.mark.asyncio
@patch("src.uploader.yadisk.AsyncYaDisk")
async def test_yandex_upload_api_error(mock_yadisk, tmp_file, mock_auth_getters):
    mock_disk = AsyncMock()
    mock_disk.check_token.return_value = True
    mock_disk.upload.side_effect = YaDiskError("API limit exceeded")
    mock_yadisk.return_value.__aenter__.return_value = mock_disk
    strategy = YandexDiskUploaderStrategy()
    with pytest.raises(UploadError, match="Ошибка API Яндекс.Диска"):
        await strategy.upload(tmp_file, "folder", "video.mp4")

@pytest.mark.asyncio
@patch("src.uploader.yadisk.AsyncYaDisk")
async def test_yandex_check_connection_success(mock_yadisk, mock_auth_getters):
    mock_disk = AsyncMock()
    mock_disk.check_token.return_value = True
    mock_yadisk.return_value.__aenter__.return_value = mock_disk
    strategy = YandexDiskUploaderStrategy()
    assert (await strategy.check_connection())[0] is True

@pytest.mark.asyncio
async def test_yandex_check_connection_no_token(mock_auth_getters):
    mock_auth_getters[0].return_value = None
    strategy = YandexDiskUploaderStrategy()
    assert (await strategy.check_connection())[0] is False

@pytest.mark.asyncio
@patch("src.uploader.yadisk.AsyncYaDisk")
async def test_yandex_check_connection_invalid_token(mock_yadisk, mock_auth_getters):
    mock_disk = AsyncMock()
    mock_disk.check_token.return_value = False
    mock_yadisk.return_value.__aenter__.return_value = mock_disk
    strategy = YandexDiskUploaderStrategy()
    assert (await strategy.check_connection())[0] is False

@pytest.mark.asyncio
@patch("src.uploader.yadisk.AsyncYaDisk", side_effect=Exception("Network error"))
async def test_yandex_check_connection_network_error(mock_yadisk, mock_auth_getters):
    strategy = YandexDiskUploaderStrategy()
    assert (await strategy.check_connection())[0] is False

# ==================================
# Тесты для GoogleDriveUploaderStrategy
# ==================================
@patch("src.uploader.build")
def test_google_upload_sync_success_new_folder(mock_build, tmp_file, mock_auth_getters):
    mock_service = MagicMock()
    mock_build.return_value = mock_service
    mock_files_resource = mock_service.files.return_value
    mock_files_resource.list.return_value.execute.return_value = {"files": []}
    mock_files_resource.create.return_value.execute.side_effect = [
        {"id": "fake_folder_id"},
        {"id": "fake_file_id", "webViewLink": "http://fake.link"}
    ]
    strategy = GoogleDriveUploaderStrategy()
    result = strategy._upload_sync(tmp_file, "new_folder", "video.mp4")
    assert result["status"] == "успех"
    assert mock_files_resource.create.call_count == 2

@patch("src.uploader.build")
def test_google_upload_sync_folder_exists(mock_build, tmp_file, mock_auth_getters):
    mock_service = MagicMock()
    mock_build.return_value = mock_service
    mock_files_resource = mock_service.files.return_value
    mock_files_resource.list.return_value.execute.return_value = {"files": [{"id": "existing_folder_id"}]}
    mock_files_resource.create.return_value.execute.return_value = {"id": "fake_file_id"}
    strategy = GoogleDriveUploaderStrategy()
    strategy._upload_sync(tmp_file, "existing_folder", "video.mp4")
    mock_files_resource.list.assert_called_once()
    mock_files_resource.create.assert_called_once()

@patch("src.uploader.build")
def test_google_upload_sync_empty_path(mock_build, tmp_file, mock_auth_getters):
    mock_service = MagicMock()
    mock_build.return_value = mock_service
    mock_files_resource = mock_service.files.return_value
    mock_files_resource.create.return_value.execute.return_value = {"id": "fake_file_id"}
    strategy = GoogleDriveUploaderStrategy()
    strategy._upload_sync(tmp_file, "", "video.mp4")
    mock_files_resource.list.assert_not_called()
    assert mock_files_resource.create.call_args.kwargs['body']['parents'] == ['root']

@patch("src.uploader.build")
def test_google_upload_sync_create_folder_error(mock_build, tmp_file, mock_auth_getters):
    mock_service = MagicMock()
    mock_build.return_value = mock_service
    mock_files_resource = mock_service.files.return_value
    mock_files_resource.list.return_value.execute.return_value = {"files": []}
    http_error = HttpError(resp=MagicMock(status=403), content=b"Forbidden")
    mock_files_resource.create.return_value.execute.side_effect = http_error
    strategy = GoogleDriveUploaderStrategy()
    with pytest.raises(UploadError, match="Ошибка API Google Drive при создании папки"):
        strategy._upload_sync(tmp_file, "new_folder", "video.mp4")

@patch("src.uploader.build")
def test_google_upload_sync_upload_file_error(mock_build, tmp_file, mock_auth_getters):
    mock_service = MagicMock()
    mock_build.return_value = mock_service
    mock_files_resource = mock_service.files.return_value
    mock_files_resource.list.return_value.execute.return_value = {"files": [{"id": "id_A"}]}
    http_error = HttpError(resp=MagicMock(status=403), content=b"Forbidden")
    mock_files_resource.create.return_value.execute.side_effect = http_error
    strategy = GoogleDriveUploaderStrategy()
    with pytest.raises(UploadError, match="Ошибка API Google Drive:"):
        strategy._upload_sync(tmp_file, "existing_folder", "video.mp4")

def test_google_upload_sync_no_creds(mock_auth_getters, tmp_file):
    mock_auth_getters[1].return_value = None
    strategy = GoogleDriveUploaderStrategy()
    with pytest.raises(UploadError, match="Не удалось получить учетные данные Google Drive"):
        strategy._upload_sync(tmp_file, "folder", "video.mp4")

@pytest.mark.asyncio
@patch("src.uploader.build")
async def test_google_check_connection_success(mock_build, mock_auth_getters):
    mock_service = MagicMock()
    mock_build.return_value = mock_service
    strategy = GoogleDriveUploaderStrategy()
    assert (await strategy.check_connection())[0] is True

@pytest.mark.asyncio
@patch("src.uploader.build")
async def test_google_check_connection_failure(mock_build, mock_auth_getters):
    mock_service = MagicMock()
    mock_service.about().get().execute.side_effect = Exception("API Error")
    mock_build.return_value = mock_service
    strategy = GoogleDriveUploaderStrategy()
    assert (await strategy.check_connection())[0] is False

@patch("src.uploader.build")
def test_google_upload_sync_find_folder_error(mock_build, tmp_file, mock_auth_getters):
    """Тест: ошибка API при поиске папки в Google Drive."""
    mock_service = MagicMock()
    mock_build.return_value = mock_service
    mock_files_resource = mock_service.files.return_value
    http_error = HttpError(resp=MagicMock(status=404), content=b"Not Found")
    mock_files_resource.list.return_value.execute.side_effect = http_error

    strategy = GoogleDriveUploaderStrategy()

    with pytest.raises(UploadError, match="Ошибка API Google Drive при поиске папки"):
        strategy._upload_sync(tmp_file, "non_existent_folder", "video.mp4")

# ==================================
# Тесты для LocalSaveStrategy
# ==================================
@pytest.mark.asyncio
async def test_local_upload_success(tmp_file):
    strategy = LocalSaveStrategy()
    new_filename = f"copy_of_{tmp_file.name}"
    result = await strategy.upload(tmp_file, str(tmp_file.parent), new_filename)
    assert result["status"] == "успех"

@pytest.mark.asyncio
@patch("shutil.copy2", side_effect=shutil.Error("Disk full"))
async def test_local_upload_failure(mock_copy, tmp_file):
    strategy = LocalSaveStrategy()
    with pytest.raises(UploadError, match="Ошибка при локальном копировании файла"):
        await strategy.upload(tmp_file, str(tmp_file.parent), "new_name.mp4")

@pytest.mark.asyncio
@pytest.mark.parametrize("path_exists, is_dir, can_write, expected_ok, expected_msg_part, path_kwarg", [
    (True, True, True, True, "", {"path": "dummy"}),
    (False, True, True, False, "Путь не существует", {"path": "dummy"}),
    (True, False, True, False, "Путь не является папкой", {"path": "dummy"}),
    (True, True, False, False, "Нет прав на запись", {"path": "dummy"}),
    (True, True, True, False, "Путь для локального сохранения не указан", {"path": ""}),
])
async def test_local_check_connection_scenarios(
    path_exists, is_dir, can_write, expected_ok, expected_msg_part, path_kwarg, tmp_path, monkeypatch
):
    if "path" in path_kwarg and path_kwarg["path"] == "dummy":
        path_kwarg["path"] = str(tmp_path)
    monkeypatch.setattr("pathlib.Path.exists", lambda self: path_exists)
    monkeypatch.setattr("pathlib.Path.is_dir", lambda self: is_dir)
    monkeypatch.setattr("os.access", lambda path, mode: can_write)
    strategy = LocalSaveStrategy()
    is_ok, msg = await strategy.check_connection(**path_kwarg)
    assert is_ok is expected_ok
    if not expected_ok:
        assert expected_msg_part in msg

# ==================================
# Тесты для диспетчера upload_single_file
# ==================================
@pytest.mark.asyncio
@pytest.mark.parametrize("storage_name, strategy_class", UPLOADER_STRATEGIES.items())
async def test_dispatcher_selects_correct_strategy(storage_name, strategy_class, tmp_file):
    task = {"file_path": str(tmp_file), "cloud_storage": storage_name, "cloud_folder_path": "folder", "filename": "video.mp4"}
    with patch.object(strategy_class, "upload", new_callable=AsyncMock) as mock_upload:
        mock_upload.return_value = {"status": "успех"}
        await upload_single_file(task)
        mock_upload.assert_called_once()

@pytest.mark.asyncio
async def test_dispatcher_strategy_not_found(tmp_file):
    task = {"cloud_storage": "Invalid Storage", "filename": "video.mp4", "file_path": "dummy", "cloud_folder_path": ""}
    result = await upload_single_file(task)
    assert result["status"] == "ошибка"
    assert "Не найдена стратегия" in result["error"]

@pytest.mark.asyncio
async def test_dispatcher_handles_general_exception(tmp_file, mock_auth_getters):
    task = {"file_path": str(tmp_file), "cloud_storage": "Google Drive", "cloud_folder_path": "folder", "filename": "video.mp4"}
    with patch.object(GoogleDriveUploaderStrategy, "upload", new_callable=AsyncMock) as mock_upload:
        mock_upload.side_effect = ValueError("Some unexpected error")
        result = await upload_single_file(task)
        assert result["status"] == "ошибка"
        assert "Some unexpected error" in result["error"]