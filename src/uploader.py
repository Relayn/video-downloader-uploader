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

# Константы для статусов операции
STATUS_SUCCESS = "успех"
STATUS_ERROR = "ошибка"


class UploadError(Exception):
    """
    Кастомное исключение для ошибок, возникающих в процессе загрузки файлов.

    Attributes:
        details (Any): Дополнительная информация об ошибке, например,
                       оригинальное исключение от API.
    """
    def __init__(self, message: str, details: Any = None):
        super().__init__(message)
        self.details = details


class UploaderStrategy(ABC):
    """Абстрактный базовый класс, определяющий интерфейс для стратегий загрузки."""

    @abstractmethod
    async def upload(self, file_path: Path, cloud_folder_path: str, filename: str) -> Dict[str, Any]:
        """
        Асинхронно загружает файл в соответствии с выбранной стратегией.

        Args:
            file_path (Path): Путь к локальному файлу для загрузки.
            cloud_folder_path (str): Путь к папке назначения в облаке или локально.
            filename (str): Имя, которое будет присвоено файлу в месте назначения.

        Returns:
            Dict[str, Any]: Словарь с результатом операции.
        """
        pass

    @abstractmethod
    async def check_connection(self, **kwargs) -> Tuple[bool, str]:
        """
        Проверяет доступность сервиса и корректность настроек.

        Args:
            **kwargs: Дополнительные аргументы, специфичные для стратегии (например, path).

        Returns:
            Tuple[bool, str]: Кортеж, где первый элемент - True при успехе,
                              а второй - сообщение об ошибке в случае неудачи.
        """
        pass


class YandexDiskUploaderStrategy(UploaderStrategy):
    """Стратегия для загрузки файлов на Яндекс.Диск."""

    async def upload(self, file_path: Path, cloud_folder_path: str, filename: str) -> Dict[str, Any]:
        token = get_yandex_token()
        if not token:
            raise UploadError("Токен Яндекс.Диска не найден.")

        remote_path = f"/{cloud_folder_path.strip('/')}/{filename}"
        try:
            async with yadisk.AsyncYaDisk(token=token) as disk:
                if not await disk.check_token():
                    raise UploadError("Токен Яндекс.Диска невалиден.")
                if cloud_folder_path and not await disk.exists(f"/{cloud_folder_path.strip('/')}"):
                    await disk.mkdir(f"/{cloud_folder_path.strip('/')}")
                await disk.upload(str(file_path), remote_path, overwrite=True)
                link = await disk.get_download_link(remote_path)
                return {"status": STATUS_SUCCESS, "url": link}
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
    """Стратегия для загрузки файлов на Google Drive."""

    def _find_or_create_folder(self, service, parent_id: str, folder_name: str) -> str:
        """Находит папку по имени или создает ее, если она не существует."""
        query = f"'{parent_id}' in parents and name='{folder_name}' and mimeType='application/vnd.google-apps.folder' and trashed=false"
        try:
            response = service.files().list(q=query, fields="files(id, name)").execute()
            if response.get("files"):
                return response["files"][0]["id"]
        except HttpError as e:
            raise UploadError(f"Ошибка API Google Drive при поиске папки '{folder_name}'", details=e) from e

        file_metadata = {"name": folder_name, "mimeType": "application/vnd.google-apps.folder", "parents": [parent_id]}
        try:
            folder = service.files().create(body=file_metadata, fields="id").execute()
            return folder.get("id")
        except HttpError as e:
            raise UploadError(f"Ошибка API Google Drive при создании папки '{folder_name}'", details=e) from e

    def _create_folders_chain(self, service, root_id: str, path: str) -> str:
        """Создает всю цепочку вложенных папок и возвращает ID последней."""
        parent_id = root_id
        for folder_name in path.strip("/").split("/"):
            if folder_name:
                parent_id = self._find_or_create_folder(service, parent_id, folder_name)
        return parent_id

    def _upload_sync(self, file_path: Path, cloud_folder_path: str, filename: str) -> Dict[str, Any]:
        """Синхронная часть логики загрузки в Google Drive."""
        creds = get_google_drive_credentials()
        if not creds:
            raise UploadError("Не удалось получить учетные данные Google Drive.")

        try:
            service = build("drive", "v3", credentials=creds)
            folder_id = self._create_folders_chain(service, "root", cloud_folder_path)
            file_metadata = {"name": filename, "parents": [folder_id]}
            media = MediaFileUpload(str(file_path), resumable=True)
            file = service.files().create(body=file_metadata, media_body=media, fields="id, webViewLink").execute()
            return {"status": STATUS_SUCCESS, "id": file.get("id"), "url": file.get("webViewLink")}
        except HttpError as e:
            raise UploadError(f"Ошибка API Google Drive: {e}", details=e) from e

    async def upload(self, file_path: Path, cloud_folder_path: str, filename: str) -> Dict[str, Any]:
        return await asyncio.to_thread(self._upload_sync, file_path, cloud_folder_path, filename)

    async def check_connection(self, **kwargs) -> Tuple[bool, str]:
        try:
            creds = get_google_drive_credentials()
            service = build("drive", "v3", credentials=creds)
            service.about().get(fields="user").execute()
            return True, ""
        except Exception as e:
            logger.error(f"Ошибка при проверке соединения с Google Drive: {e}")
            return False, f"Ошибка API или аутентификации Google Drive: {e}"


class LocalSaveStrategy(UploaderStrategy):
    """Стратегия для сохранения файлов в локальную файловую систему."""

    async def upload(self, file_path: Path, cloud_folder_path: str, filename: str) -> Dict[str, Any]:
        destination_path = Path(cloud_folder_path)
        destination_file = destination_path / filename
        try:
            destination_path.mkdir(parents=True, exist_ok=True)
            shutil.copy2(file_path, destination_file)
            return {"status": STATUS_SUCCESS, "path": str(destination_file)}
        except OSError as e:
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
    """
    Выбирает и запускает нужную стратегию загрузки для одной задачи.

    Является единой точкой входа для всей логики загрузки.

    Args:
        task (Dict[str, Any]): Словарь, описывающий задачу на загрузку.
            Должен содержать ключи 'cloud_storage', 'file_path',
            'cloud_folder_path', 'filename'.

    Returns:
        Dict[str, Any]: Словарь с результатом операции.
    """
    storage_name = task.get("cloud_storage")
    strategy_class = UPLOADER_STRATEGIES.get(storage_name)

    if not strategy_class:
        error_msg = f"Не найдена стратегия для хранилища '{storage_name}'."
        logger.error(error_msg)
        return {"status": STATUS_ERROR, "filename": task.get("filename"), "error": error_msg}

    strategy = strategy_class()
    try:
        result = await strategy.upload(
            file_path=Path(task["file_path"]),
            cloud_folder_path=task["cloud_folder_path"],
            filename=task["filename"],
        )
        logger.info(f"Файл '{task['filename']}' успешно загружен в '{storage_name}'.")
        return {**result, "filename": task["filename"]}
    except Exception as e:
        logger.error(f"Не удалось загрузить '{task['filename']}' в '{storage_name}': {e}", exc_info=True)
        return {"status": STATUS_ERROR, "filename": task.get("filename"), "error": str(e)}