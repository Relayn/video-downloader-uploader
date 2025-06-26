import asyncio
import logging
import os
import shutil
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Dict, Tuple

import yadisk
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload
from yadisk.exceptions import YaDiskError

from .auth import get_google_drive_credentials, get_yandex_token

logger = logging.getLogger(__name__)


class UploadError(Exception):
    """Кастомное исключение для ошибок загрузки."""
    def __init__(self, message: str, details: Any = None):
        super().__init__(message)
        self.details = details


class UploaderStrategy(ABC):
    @abstractmethod
    async def upload(self, file_path: Path, cloud_folder_path: str, filename: str) -> Dict[str, Any]:
        pass

    @abstractmethod
    async def check_connection(self, **kwargs) -> Tuple[bool, str]:
        pass


class YandexDiskUploaderStrategy(UploaderStrategy):
    async def upload(self, file_path: Path, cloud_folder_path: str, filename: str) -> Dict[str, Any]:
        token = get_yandex_token()
        if not token:
            raise UploadError("Токен Яндекс.Диска не найден.") # pragma: no cover

        remote_path = f"/{cloud_folder_path}/{filename}"
        try:
            async with yadisk.AsyncYaDisk(token=token) as disk:
                if not await disk.check_token():
                    raise UploadError("Токен Яндекс.Диска невалиден.") # pragma: no cover
                if not await disk.exists(f"/{cloud_folder_path}"):
                    await disk.mkdir(f"/{cloud_folder_path}")
                await disk.upload(str(file_path), remote_path, overwrite=True)
                link = await disk.get_download_link(remote_path)
                return {"status": "успех", "url": link}
        except YaDiskError as e:
            logger.error(f"Ошибка API Яндекс.Диска: {e}")
            raise UploadError(f"Ошибка API Яндекс.Диска: {e}", details=e) from e

    async def check_connection(self, **kwargs) -> Tuple[bool, str]:
        token = get_yandex_token()
        if not token:
            return False, "Токен Яндекс.Диска не найден."
        try:
            async with yadisk.AsyncYaDisk(token=token) as disk:
                if await disk.check_token():
                    return True, ""
                return False, "Токен Яндекс.Диска невалиден."
        except Exception as e:
            logger.error(f"Ошибка при проверке токена Яндекс.Диска: {e}")
            return False, f"Ошибка сети или API: {e}"


class GoogleDriveUploaderStrategy(UploaderStrategy):
    def _find_or_create_folder(self, service, parent_id: str, folder_name: str) -> str:
        query = f"'{parent_id}' in parents and name='{folder_name}' and mimeType='application/vnd.google-apps.folder' and trashed=false"
        try:
            response = service.files().list(q=query, fields="files(id, name)").execute()
            existing_folders = response.get("files", [])
            if existing_folders:
                logger.info(f"[Gdrive] Найдена папка '{folder_name}' с ID: {existing_folders[0]['id']}")
                return existing_folders[0]["id"]
        except HttpError as e:
            logger.error(f"[Gdrive] Ошибка API при поиске папки '{folder_name}': {e}")
            raise UploadError(f"Ошибка API Google Drive при поиске папки '{folder_name}'", details=e) from e

        logger.info(f"[Gdrive] Создание папки '{folder_name}' в {parent_id}")
        file_metadata = {"name": folder_name, "mimeType": "application/vnd.google-apps.folder", "parents": [parent_id]}
        try:
            folder = service.files().create(body=file_metadata, fields="id").execute()
            return folder.get("id")
        except HttpError as e:
            logger.error(f"[Gdrive] Ошибка API при создании папки '{folder_name}': {e}")
            raise UploadError(f"Ошибка API Google Drive при создании папки '{folder_name}'", details=e) from e

    def _create_folders_chain(self, service, root_id: str, path: str) -> str:
        parent_id = root_id
        for folder_name in path.strip("/").split("/"):
            if folder_name:
                parent_id = self._find_or_create_folder(service, parent_id, folder_name)
        return parent_id

    def _upload_sync(self, file_path: Path, cloud_folder_path: str, filename: str) -> Dict[str, Any]:
        creds = get_google_drive_credentials()
        if not creds:
            raise UploadError("Не удалось получить учетные данные Google Drive.") # pragma: no cover
        try:
            service = build("drive", "v3", credentials=creds)
            folder_id = self._create_folders_chain(service, "root", cloud_folder_path)
            file_metadata = {"name": filename, "parents": [folder_id]}
            media = MediaFileUpload(str(file_path), resumable=True)
            file = service.files().create(body=file_metadata, media_body=media, fields="id, webViewLink").execute()
            return {"status": "успех", "id": file.get("id"), "url": file.get("webViewLink")}
        except HttpError as e:
            logger.error(f"Ошибка API Google Drive: {e}")
            raise UploadError(f"Ошибка API Google Drive: {e}", details=e) from e

    async def upload(self, file_path: Path, cloud_folder_path: str, filename: str) -> Dict[str, Any]:
        return await asyncio.to_thread(self._upload_sync, file_path, cloud_folder_path, filename) # pragma: no cover

    async def check_connection(self, **kwargs) -> Tuple[bool, str]:
        creds = get_google_drive_credentials()
        if not creds:
            return False, "Учетные данные Google Drive не найдены."
        try:
            service = build("drive", "v3", credentials=creds)
            service.about().get(fields="user").execute()
            return True, ""
        except Exception as e:
            logger.error(f"Ошибка при проверке соединения с Google Drive: {e}")
            return False, f"Ошибка API Google Drive: {e}"


class LocalSaveStrategy(UploaderStrategy):
    async def upload(self, file_path: Path, cloud_folder_path: str, filename: str) -> Dict[str, Any]:
        destination_path = Path(cloud_folder_path)
        destination_file = destination_path / filename
        try:
            os.makedirs(destination_path, exist_ok=True)
            shutil.copy2(file_path, destination_file)
            return {"status": "успех", "path": str(destination_file)}
        except (OSError, shutil.Error) as e:
            logger.error(f"Ошибка при локальном копировании файла: {e}")
            raise UploadError(f"Ошибка при локальном копировании файла: {e}", details=e) from e

    async def check_connection(self, **kwargs) -> Tuple[bool, str]:
        path_str = kwargs.get("path")
        if not path_str:
            return False, "Путь для локального сохранения не указан."
        path = Path(path_str)
        if not path.exists():
            return False, f"Путь не существует: {path}"
        if not path.is_dir():
            return False, f"Путь не является папкой: {path}"
        if not os.access(path, os.W_OK):
            return False, f"Нет прав на запись в папку: {path}"
        return True, ""


UPLOADER_STRATEGIES = {
    "Google Drive": GoogleDriveUploaderStrategy,
    "Yandex.Disk": YandexDiskUploaderStrategy,
    "Сохранить локально": LocalSaveStrategy,
}


async def upload_single_file(task: Dict[str, Any]) -> Dict[str, Any]:
    storage_name = task.get("cloud_storage")
    strategy_class = UPLOADER_STRATEGIES.get(storage_name)

    if not strategy_class:
        error_msg = f"Не найдена стратегия для хранилища '{storage_name}'."
        logger.error(error_msg)
        return {"status": "ошибка", "filename": task.get("filename"), "error": error_msg}

    strategy = strategy_class()
    try:
        result = await strategy.upload(
            file_path=task["file_path"],
            cloud_folder_path=task["cloud_folder_path"],
            filename=task["filename"],
        )
        logger.info(f"Файл '{task['filename']}' успешно загружен в '{storage_name}'.")
        return {**result, "filename": task["filename"]}
    except (UploadError, Exception) as e:
        logger.error(f"Не удалось загрузить '{task['filename']}' в '{storage_name}': {e}")
        return {"status": "ошибка", "filename": task.get("filename"), "error": str(e)}