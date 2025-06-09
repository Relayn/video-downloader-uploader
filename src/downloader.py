import time
import os
from pathlib import Path
from typing import Optional, List, Dict, Any

import yt_dlp
from concurrent.futures import ThreadPoolExecutor, as_completed

from src.config import get_config, setup_logger, ConfigError


class DownloadError(Exception):
    """Базовое исключение для ошибок скачивания."""

    pass


def find_downloaded_file(directory: str, slug: str, ext: str) -> str | None:
    """
    Ищет скачанный файл в директории по разным критериям.

    1.  Ищет точное совпадение: `slug.ext`.
    2.  Ищет файл, содержащий `slug` в имени: `*slug*.ext`.
    3.  Если ничего не найдено, возвращает первый попавшийся файл с расширением `ext`.

    Args:
        directory: Директория для поиска.
        slug: Уникальный идентификатор видео.
        ext: Ожидаемое расширение файла.

    Returns:
        Полный путь к найденному файлу или None.
    """
    # 1. Точное совпадение
    exact_path = Path(directory) / f"{slug}.{ext}"
    if exact_path.exists():
        return str(exact_path)

    files_in_dir = os.listdir(directory)

    # 2. Поиск по slug в имени
    for filename in files_in_dir:
        if slug in filename and filename.endswith(f".{ext}"):
            return os.path.join(directory, filename)

    # 3. Поиск любого файла с нужным расширением
    for filename in files_in_dir:
        if filename.endswith(f".{ext}"):
            return os.path.join(directory, filename)

    return None


def download_video(url: str, slug: str, temp_dir: str) -> str:
    """
    Скачивает видео с YouTube с помощью yt-dlp.

    Args:
        url: URL видео.
        slug: Уникальный идентификатор для имени файла.
        temp_dir: Временная директория для сохранения файла.

    Returns:
        Путь к скачанному файлу.

    Raises:
        DownloadError: В случае любой ошибки скачивания.
    """
    config = get_config()
    logger = setup_logger("downloader", level=config.LOG_LEVEL)

    # Используем slug для имени файла, чтобы избежать проблем со спецсимволами из title
    output_template = os.path.join(temp_dir, f"{slug}.%(ext)s")

    ydl_opts = {
        "format": config.YTDLP_FORMAT,
        "outtmpl": output_template,
        "retries": config.YTDLP_RETRIES,
        "fragment_retries": config.YTDLP_RETRIES,
        "quiet": True,
        "noprogress": True,
        "logtostderr": False,
        # Передаем путь к ffmpeg, если он указан
        "ffmpeg_location": (
            str(config.FFMPEG_PATH)
            if config.FFMPEG_PATH and config.FFMPEG_PATH.exists()
            else None
        ),
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            retcode = ydl.download([url])
            if retcode != 0:
                raise DownloadError(f"yt-dlp вернул код ошибки {retcode} для URL {url}")

    except Exception as e:
        logger.error(f"Ошибка при скачивании {url}: {e}")
        raise DownloadError(f"Не удалось скачать видео: {url}") from e

    # yt-dlp мог сохранить файл с немного другим расширением (webm вместо mp4 и т.д.)
    # Поэтому ищем файл по slug
    downloaded_file = find_downloaded_file(
        temp_dir, slug, "mp4"
    )  # Ищем mp4 по умолчанию
    if not downloaded_file:
        downloaded_file = find_downloaded_file(temp_dir, slug, "webm")  # или webm

    if not downloaded_file:
        raise DownloadError(f"Скачанный файл для slug '{slug}' не найден в {temp_dir}")

    logger.info(f"Видео успешно скачано: {downloaded_file}")
    return downloaded_file


def batch_download_videos(
    urls: List[str], temp_dir: str, max_workers: int = 4
) -> List[Dict[str, Any]]:
    """
    Параллельно скачивает список видео.

    Args:
        urls: Список URL для скачивания.
        temp_dir: Временная директория для сохранения файлов.
        max_workers: Максимальное количество потоков.

    Returns:
        Список словарей с результатами для каждого URL.
    """
    results = []
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Для каждого URL генерируем простой slug на основе времени и хэша
        future_to_url = {
            executor.submit(
                download_video,
                url,
                f"vid_{abs(hash(url))}_{int(time.time())}",
                temp_dir,
            ): url
            for url in urls
        }

        for future in as_completed(future_to_url):
            url = future_to_url[future]
            try:
                file_path = future.result()
                results.append({"status": "успех", "url": url, "path": Path(file_path)})
            except Exception as e:
                results.append({"status": "ошибка", "url": url, "message": str(e)})
    return results
