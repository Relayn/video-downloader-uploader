import logging
from pathlib import Path
from yt_dlp import YoutubeDL
import shutil

logger = logging.getLogger(__name__)

DEFAULT_FILENAME_TEMPLATE = "%(title)s.%(ext)s"

def is_ffmpeg_installed() -> bool:
    """
    Проверяет, доступна ли утилита ffmpeg в системной переменной PATH.

    Returns:
        bool: True, если ffmpeg найден, иначе False.
    """
    return shutil.which("ffmpeg") is not None


def download_video(
        url: str,
        download_dir: Path,
        quality_format: str | None = None,
        proxy: str | None = None,
        filename_template: str | None = None,
) -> dict:
    """
    Скачивает видео с указанного URL с помощью yt-dlp.

    Args:
        url (str): URL видео для скачивания.
        download_dir (Path): Директория для сохранения скачанного файла.
        quality_format (str | None): Строка формата качества для yt-dlp
            (например, 'bestvideo+bestaudio/best').
        proxy (str | None): URL прокси-сервера для использования.
        filename_template (str | None): Шаблон для имени выходного файла,
            использующий плейсхолдеры yt-dlp.

    Returns:
        dict: Словарь с результатом операции.
              В случае успеха: {'status': 'успех', 'url': str, 'path': Path}.
              В случае ошибки: {'status': 'ошибка', 'url': str, 'error': str}.
    """
    logger.info(f"Начало скачивания: {url}")
    try:
        final_template = filename_template or DEFAULT_FILENAME_TEMPLATE

        ydl_opts = {
            "outtmpl": str(download_dir / final_template),
            "noplaylist": True,
            "progress_hooks": [lambda d: logger.debug(f"yt-dlp hook: {d['status']}")],
            "logger": logger,
        }
        if quality_format:
            ydl_opts["format"] = quality_format
        if proxy:
            ydl_opts["proxy"] = proxy
            logger.info(f"Используется прокси: {proxy}")

        with YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = Path(ydl.prepare_filename(info))
            logger.info(f"Видео успешно скачано: {filename.name}")
            return {"status": "успех", "url": url, "path": filename}

    except Exception as e:
        logger.error(f"Ошибка при скачивании {url}: {e}", exc_info=True)
        return {"status": "ошибка", "url": url, "error": str(e)}