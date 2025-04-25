import os
import time
from typing import Optional, Dict, Any, List
import yadisk
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from concurrent.futures import ThreadPoolExecutor, as_completed
from auth import get_yandex_token, get_google_drive_credentials
from logger import setup_logger
from config import LOG_LEVEL, LOG_TO_FILE, LOG_FILE_PATH

logger = setup_logger("uploader", level=LOG_LEVEL, to_file=LOG_TO_FILE, file_path=LOG_FILE_PATH)

class UploadError(Exception):
    """Базовое исключение для ошибок загрузки."""
    pass

def upload_to_yandex_disk(file_path: str, folder_path: str, filename: str, max_retries: int = 3) -> str:
    """Загружает файл на Яндекс.Диск, с логированием времени и повторными попытками."""
    y = yadisk.YaDisk(token=get_yandex_token())
    if not y.check_token():
        raise UploadError("Неверный токен Яндекс.Диска")
    folder_path = folder_path.strip("/")
    remote_path = f"{folder_path}/{filename}" if folder_path else filename
    remote_path = remote_path.replace(os.sep, "/")
    if folder_path:
        try:
            y.mkdir(folder_path, exist_ok=True)
        except yadisk.exceptions.PathExistsError:
            pass
    last_exc = None
    for attempt in range(1, max_retries + 1):
        try:
            t0 = time.time()
            # Увеличиваем таймаут до 120 секунд
            with open(file_path, "rb") as f:
                y.upload(f, remote_path, overwrite=True, timeout=120)
            elapsed = time.time() - t0
            logger.info(f"Загружено на Яндекс.Диск: {remote_path} (время: {elapsed:.2f} сек, попытка {attempt})")
            return remote_path
        except Exception as e:
            logger.error(f"Ошибка загрузки на Яндекс.Диск (попытка {attempt}): {e}")
            last_exc = e
            time.sleep(2 * attempt)  # exponential backoff
    raise UploadError(f"Не удалось загрузить на Яндекс.Диск после {max_retries} попыток: {last_exc}")

def upload_to_google_drive(file_path: str, folder_id: str, folder_path: Optional[str], filename: str, max_retries: int = 3) -> str:
    """Загружает файл на Google Drive, с логированием времени и повторными попытками."""
    creds = get_google_drive_credentials()
    service = build("drive", "v3", credentials=creds)
    if folder_path:
        folder_id = create_gdrive_folders_chain(service, folder_id, folder_path)
    file_metadata = {"name": filename, "parents": [folder_id]}
    media = MediaFileUpload(file_path)
    last_exc = None
    t0 = time.time()
    for attempt in range(1, max_retries + 1):
        try:
            file = service.files().create(body=file_metadata, media_body=media, fields="id").execute()
            elapsed = time.time() - t0
            logger.info(f"Загружено на Google Drive: {file.get('id')} (время: {elapsed:.2f} сек, попытка {attempt})")
            return file.get("id")
        except Exception as e:
            logger.error(f"Ошибка загрузки на Google Drive (попытка {attempt}): {e}")
            last_exc = e
            time.sleep(2 * attempt)
    raise UploadError(f"Не удалось загрузить на Google Drive после {max_retries} попыток: {last_exc}")

def create_gdrive_folders_chain(service, parent_id: str, folder_path: str) -> str:
    """Создает цепочку вложенных папок в Google Drive и возвращает id самой вложенной."""
    folders = folder_path.strip("/").split("/")
    for folder_name in folders:
        parent_id = create_gdrive_folder(service, parent_id, folder_name)
    return parent_id

def create_gdrive_folder(service, parent_id: str, folder_name: str) -> str:
    """Создает папку в Google Drive, если она не существует."""
    query = (
        f"name='{folder_name}' and mimeType='application/vnd.google-apps.folder' and '{parent_id}' in parents and trashed=false"
    )
    results = service.files().list(q=query, fields="files(id)").execute()
    folders = results.get("files", [])
    if folders:
        return folders[0]["id"]
    folder_metadata = {
        "name": folder_name,
        "mimeType": "application/vnd.google-apps.folder",
        "parents": [parent_id],
    }
    folder = service.files().create(body=folder_metadata, fields="id").execute()
    return folder["id"]

def batch_upload_to_cloud(tasks: List[Dict[str, Any]], max_workers: int = 4, max_retries: int = 3) -> List[Dict[str, Any]]:
    """Параллельная загрузка файлов на облако (Яндекс.Диск или Google Drive)"""
    results = []
    def _upload_one(task):
        try:
            if task["cloud_storage"] == "Yandex.Disk":
                remote = upload_to_yandex_disk(task["file_path"], task.get("cloud_folder_path", ""), task["filename"], max_retries=max_retries)
                # Удаляем файл после успешной загрузки
                if os.path.exists(task["file_path"]):
                    os.remove(task["file_path"])
                return {"status": "успех", "cloud_storage": "Yandex.Disk", "remote_path": remote, "filename": task["filename"]}
            elif task["cloud_storage"] == "Google Drive":
                remote = upload_to_google_drive(task["file_path"], task["google_drive_folder_id"], task.get("cloud_folder_path"), task["filename"], max_retries=max_retries)
                # Удаляем файл после успешной загрузки
                if os.path.exists(task["file_path"]):
                    os.remove(task["file_path"])
                return {"status": "успех", "cloud_storage": "Google Drive", "remote_id": remote, "filename": task["filename"]}
            else:
                return {"status": "ошибка", "message": f"Неизвестное хранилище: {task['cloud_storage']}"}
        except Exception as e:
            return {"status": "ошибка", "message": str(e), "filename": task.get("filename")}
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_task = {executor.submit(_upload_one, t): t for t in tasks}
        for future in as_completed(future_to_task):
            results.append(future.result())
    return results
