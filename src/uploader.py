import asyncio
import os
import time
from pathlib import Path
from typing import Optional, List, Dict, Any
from concurrent.futures import ThreadPoolExecutor, as_completed
import yadisk
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload as GoogleMediaFileUpload
import httpx
from tenacity import retry, stop_after_attempt, wait_exponential, RetryError
import yadisk_async
from slugify import slugify

from src.auth import get_yandex_token, get_google_drive_credentials
from src.config import get_config, setup_logger, ConfigError


# Инициализация при импорте
try:
    config = get_config()
    logger = setup_logger(
        "uploader",
        level=config.LOG_LEVEL,
        to_file=config.LOG_TO_FILE,
        file_path=config.LOG_FILE_PATH,
    )
except ConfigError as e:
    logger = setup_logger("uploader_fallback")
    logger.critical(f"Ошибка загрузки конфигурации в uploader: {e}")


class UploadError(Exception):
    """Пользовательское исключение для ошибок загрузки."""

    pass


def slugify_filename(filename: str) -> str:
    """
    Очищает имя файла, заменяя пробелы и спецсимволы, и транслитерирует.
    Пример: 'Пример видео файла.mp4' -> 'primer-video-faila.mp4'
    """
    name, ext = os.path.splitext(filename)
    return f"{slugify(name, max_length=200, word_boundary=True)}{ext}"


def get_file_size_and_mimetype(file_path: Path) -> (int, Optional[str]):
    """Возвращает размер файла в байтах и его MIME-тип."""
    try:
        size = file_path.stat().st_size
        import mimetypes

        mimetype, _ = mimetypes.guess_type(file_path)
        return size, mimetype
    except FileNotFoundError:
        return 0, None


async def upload_to_yandex_disk(
    file_path: Path, folder_path: str, filename: str
) -> str:
    """Асинхронно загружает файл на Яндекс.Диск с повторными попытками."""
    token = get_yandex_token()
    if not token:
        raise UploadError("Токен Яндекс.Диска не найден.")

    remote_folder = folder_path.strip("/")
    if remote_folder:
        remote_path = f"/{remote_folder}/{filename}"
    else:
        remote_path = f"/{filename}"

    logger.info(f"Начало загрузки на Яндекс.Диск: {remote_path}")

    try:
        async with yadisk_async.YaDisk(token=token) as disk:
            if not await disk.check_token():
                raise UploadError("Токен Яндекс.Диска невалиден.")

            if remote_folder:
                if not await disk.exists(f"/{remote_folder}"):
                    await disk.mkdir(f"/{remote_folder}")

            await disk.upload(str(file_path), remote_path, overwrite=True)
            logger.info(f"Файл успешно загружен: {remote_path}")
            return remote_path
    except yadisk_async.exceptions.YaDiskError as e:
        msg = f"Ошибка API Яндекс.Диска: {e}"
        logger.error(msg)
        raise UploadError(msg) from e


def upload_to_google_drive(
    file_path: Path, folder_path: Optional[str], filename: str
) -> Optional[str]:
    """Загружает файл на Google Drive, создавая папки по пути."""
    creds = get_google_drive_credentials()
    if not creds:
        raise UploadError("Не удалось получить учетные данные Google Drive.")

    try:
        service = build("drive", "v3", credentials=creds)

        parent_folder_id = "root"
        if folder_path:
            parent_folder_id = create_gdrive_folders_chain(service, "root", folder_path)

        file_metadata = {"name": filename, "parents": [parent_folder_id]}
        media = MediaFileUpload(str(file_path), resumable=True)

        logger.info(
            f"Начало загрузки на Google Drive: {filename} в папку {parent_folder_id}"
        )

        file = (
            service.files()
            .create(body=file_metadata, media_body=media, fields="id")
            .execute()
        )

        file_id = file.get("id")
        logger.info(f"Успешно загружено на Google Drive. File ID: {file_id}")
        return file_id

    except HttpError as error:
        logger.error(
            f"Ошибка HTTP при загрузке на Google Drive: {error}", exc_info=True
        )
        raise UploadError(f"Ошибка API Google Drive: {error}") from error
    except Exception as e:
        logger.error(
            f"Непредвиденная ошибка при загрузке на Google Drive: {e}", exc_info=True
        )
        raise UploadError(f"Непредвиденная ошибка Google Drive: {e}") from e


def create_gdrive_folders_chain(service, parent_id: str, folder_path: str) -> str:
    """Создает цепочку папок в Google Drive и возвращает ID последней."""
    folder_names = [name for name in folder_path.strip("/").split("/") if name]
    current_parent_id = parent_id
    for folder_name in folder_names:
        current_parent_id = _find_or_create_gdrive_folder(
            service, folder_name, current_parent_id
        )
    return current_parent_id


def _find_or_create_gdrive_folder(service, folder_name: str, parent_id: str) -> str:
    """Ищет папку, и если не находит - создает ее."""
    query = (
        f"name='{folder_name}' and mimeType='application/vnd.google-apps.folder' "
        f"and '{parent_id}' in parents and trashed=false"
    )
    response = service.files().list(q=query, fields="files(id, name)").execute()
    found_folders = response.get("files", [])

    if found_folders:
        return found_folders[0].get("id")

    logger.info(f"Создание папки '{folder_name}' в родительской папке {parent_id}")
    folder_metadata = {
        "name": folder_name,
        "mimeType": "application/vnd.google-apps.folder",
        "parents": [parent_id],
    }
    folder = service.files().create(body=folder_metadata, fields="id").execute()
    return folder.get("id")


async def _run_async_upload(tasks: list[dict]) -> list[dict]:
    """Вспомогательная функция для запуска асинхронных загрузок."""
    async_tasks = []
    for task in tasks:
        # Оборачиваем upload_to_yandex_disk в tenacity retry
        retrying_upload = retry(
            stop=stop_after_attempt(3),
            wait=wait_exponential(multiplier=1, min=2, max=10),
        )(upload_to_yandex_disk)
        async_tasks.append(
            retrying_upload(
                Path(task["file_path"]),
                task["cloud_folder_path"],
                task["filename"],
            )
        )
    return await asyncio.gather(*[t for t in async_tasks], return_exceptions=True)


async def batch_upload_to_cloud(tasks: list[dict]) -> list[dict]:
    """
    Пакетная загрузка файлов в облачные хранилища.
    Обрабатывает синхронные (Google) и асинхронные (Yandex) задачи.
    """
    google_tasks = [t for t in tasks if t["cloud_storage"] == "Google Drive"]
    yandex_tasks = [t for t in tasks if t["cloud_storage"] == "Yandex.Disk"]

    results = []
    # Обработка синхронных задач
    for task in google_tasks:
        try:
            file_id = upload_to_google_drive(
                Path(task["file_path"]),
                task["cloud_folder_path"],
                task["filename"],
            )
            results.append(
                {"storage": "Google Drive", "status": "успех", "id": file_id}
            )
        except Exception as e:
            results.append({"storage": "Google Drive", "status": "ошибка", "error": e})

    # Обработка асинхронных задач
    if yandex_tasks:
        yandex_results = await _run_async_upload(yandex_tasks)
        for i, res in enumerate(yandex_results):
            if isinstance(res, Exception):
                results.append(
                    {"storage": "Yandex.Disk", "status": "ошибка", "error": res}
                )
            else:
                results.append(
                    {"storage": "Yandex.Disk", "status": "успех", "path": res}
                )

    return results
