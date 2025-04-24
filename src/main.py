import os
import shutil
import uuid
import time
from typing import Dict, Any, List
from concurrent.futures import ThreadPoolExecutor, as_completed
from dotenv import load_dotenv
from downloader import download_video
from uploader import upload_to_yandex_disk, upload_to_google_drive
from logger import setup_logger
from config import LOG_LEVEL, LOG_TO_FILE, LOG_FILE_PATH, TEMP_DIR_PREFIX

logger = setup_logger("main", level=LOG_LEVEL, to_file=LOG_TO_FILE, file_path=LOG_FILE_PATH)

class DownloadUploadError(Exception):
    """Базовое исключение для ошибок скачивания/загрузки."""
    pass

def validate_args(args: Dict[str, Any]) -> None:
    required = ["video_url", "cloud_storage"]
    for key in required:
        if not args.get(key):
            raise DownloadUploadError(f"Параметр {key} обязателен.")
    # Можно добавить дополнительные проверки типов и формата URL

def process_single_video(args: Dict[str, Any]) -> Dict[str, Any]:
    """Обработка одного видео: скачивание и загрузка."""
    load_dotenv()
    temp_dir = f"{TEMP_DIR_PREFIX}{uuid.uuid4().hex[:8]}"
    os.makedirs(temp_dir, exist_ok=True)
    t0 = time.time()
    try:
        validate_args(args)
        video_url = args["video_url"]
        cloud_storage = args["cloud_storage"]
        # Скачивание
        t_download = time.time()
        file_path, title, ext = download_video(video_url, temp_dir)
        download_time = time.time() - t_download
        filename = args.get("upload_filename", title) + f".{ext}"
        # Загрузка
        t_upload = time.time()
        if cloud_storage == "Yandex.Disk":
            folder_path = args.get("cloud_folder_path", "")
            cloud_id = upload_to_yandex_disk(file_path, folder_path, filename)
        elif cloud_storage == "Google Drive":
            folder_id = args.get("google_drive_folder_id", "root")
            folder_path = args.get("cloud_folder_path")
            cloud_id = upload_to_google_drive(file_path, folder_id, folder_path, filename)
        else:
            raise DownloadUploadError(f"Неизвестное хранилище: {cloud_storage}")
        upload_time = time.time() - t_upload
        if not cloud_id:
            raise DownloadUploadError("Загрузка не удалась: cloud_id не получен")
        return {
            "status": "успех",
            "message": f"Видео загружено: {cloud_id}",
            "cloud_identifier": cloud_id,
            "cloud_filename": filename,
            "download_time": download_time,
            "upload_time": upload_time,
            "total_time": time.time() - t0,
        }
    except DownloadUploadError as e:
        logger.error(f"Ошибка: {e}")
        return {"status": "ошибка", "message": str(e)}
    except Exception as e:
        logger.error(f"Неизвестная ошибка: {e}")
        return {"status": "ошибка", "message": f"Неизвестная ошибка: {e}"}
    finally:
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir)
            logger.info(f"Очищена временная директория: {temp_dir}")

def batch_download_and_upload(videos: List[Dict[str, Any]], max_workers: int = 4) -> List[Dict[str, Any]]:
    """Параллельная обработка списка видео."""
    results = []
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_args = {executor.submit(process_single_video, args): args for args in videos}
        for future in as_completed(future_to_args):
            result = future.result()
            results.append(result)
    return results

def download_and_upload_video(args: Dict[str, Any]) -> Dict[str, Any]:
    """Для обратной совместимости: обработка одного видео."""
    return process_single_video(args)

if __name__ == "__main__":
    # Пример batch-обработки
    videos = [
        {
            "video_url": "https://www.youtube.com/watch?v=XfTWgMgknpY",
            "cloud_storage": "Google Drive",
            "google_drive_folder_id": "root",
            "cloud_folder_path": "Videos",
        },
        # Можно добавить больше задач
    ]
    results = batch_download_and_upload(videos, max_workers=2)
    for r in results:
        print(r)
# Основной модуль
