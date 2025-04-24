import os
import time
from typing import Tuple, Optional, List, Dict, Any
import yt_dlp
from slugify import slugify
from concurrent.futures import ThreadPoolExecutor, as_completed
from logger import setup_logger
from config import LOG_LEVEL, LOG_TO_FILE, LOG_FILE_PATH, YTDLP_FORMAT, YTDLP_RETRIES

logger = setup_logger("downloader", level=LOG_LEVEL, to_file=LOG_TO_FILE, file_path=LOG_FILE_PATH)

class DownloadError(Exception):
    """Базовое исключение для ошибок скачивания."""
    pass

def find_downloaded_file(temp_dir: str, slug_title: str, ext: str) -> Optional[str]:
    """Оптимизированный поиск скачанного файла по slug и расширению."""
    expected_file = os.path.join(temp_dir, f"{slug_title}.{ext}")
    if os.path.exists(expected_file):
        return expected_file
    for f in os.listdir(temp_dir):
        if f.endswith(f".{ext}") and slug_title in f:
            return os.path.join(temp_dir, f)
    for f in os.listdir(temp_dir):
        if f.endswith(f".{ext}"):
            return os.path.join(temp_dir, f)
    return None

def download_video(url: str, temp_dir: str, max_filesize_mb: int = 2048) -> Tuple[str, str, str, float]:
    """Скачивает видео с помощью yt-dlp. Возвращает путь, title, ext, время скачивания."""
    ydl_opts = {
        "format": YTDLP_FORMAT,
        "noplaylist": True,
        "quiet": True,
        "outtmpl": os.path.join(temp_dir, "%(title)s.%(ext)s"),
        "retries": YTDLP_RETRIES,
        "max_filesize": max_filesize_mb * 1024 * 1024,  # Ограничение размера файла
    }
    t0 = time.time()
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            title = info.get("title", "video")
            ext = info.get("ext", "mp4")
            slug_title = slugify(title)
            file_path = find_downloaded_file(temp_dir, slug_title, ext)
            if not file_path:
                raise DownloadError(f"Файл не найден после скачивания: {slug_title}.{ext}")
            elapsed = time.time() - t0
            logger.info(f"Видео скачано: {file_path} (время: {elapsed:.2f} сек)")
            return file_path, title, ext, elapsed
    except Exception as e:
        logger.error(f"Ошибка скачивания: {e}")
        raise DownloadError(f"Ошибка скачивания: {e}")

def batch_download_videos(video_list: List[Dict[str, Any]], temp_dir: str, max_workers: int = 4, max_filesize_mb: int = 2048) -> List[Dict[str, Any]]:
    """Параллельное скачивание списка видео."""
    results = []
    def _download_one(args):
        url = args.get("video_url")
        try:
            file_path, title, ext, elapsed = download_video(url, temp_dir, max_filesize_mb=max_filesize_mb)
            return {"status": "успех", "file_path": file_path, "title": title, "ext": ext, "download_time": elapsed}
        except DownloadError as e:
            return {"status": "ошибка", "message": str(e), "video_url": url}
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_args = {executor.submit(_download_one, args): args for args in video_list}
        for future in as_completed(future_to_args):
            result = future.result()
            results.append(result)
    return results