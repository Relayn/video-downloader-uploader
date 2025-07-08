import argparse
import sys
import asyncio
from pathlib import Path
from tempfile import TemporaryDirectory

from src.config import get_config, ConfigError
from src.logger import setup_logger
from src.downloader import download_video
from src.gui import main as show_gui
from src.uploader import upload_single_file, UPLOADER_STRATEGIES

class CliOperationError(Exception):
    """Кастомное исключение для ошибок в CLI-режиме."""
    pass

def main():
    """
    Основная точка входа в приложение.

    Анализирует аргументы командной строки. Если аргументы отсутствуют,
    запускает графический интерфейс (GUI). В противном случае, выполняет
    операцию скачивания и/или загрузки в режиме командной строки (CLI).
    """
    parser = argparse.ArgumentParser(description="Скачивание и загрузка видео.")
    parser.add_argument("--url", help="URL видео для скачивания.")
    parser.add_argument(
        "--cloud", choices=UPLOADER_STRATEGIES.keys(), help="Облачное хранилище."
    )
    parser.add_argument("--path", help="Путь для загрузки в облаке.")
    args = parser.parse_args()

    # Если URL не передан, и другие аргументы тоже, запускаем GUI
    if not args.url and len(sys.argv) == 1:
        show_gui()
        sys.exit(0)  # Выходим после закрытия GUI

    # Если переданы другие аргументы, но не URL - это ошибка
    if not args.url:
        print("Ошибка: аргумент --url обязателен для режима CLI.", file=sys.stderr)
        sys.exit(1)

    # Если аргументы переданы, выполняем логику CLI
    try:
        config = get_config()
    except ConfigError as e:
        print(f"Ошибка конфигурации: {e}", file=sys.stderr)
        sys.exit(1)

    logger = setup_logger(
        "main_cli",
        level=config.LOG_LEVEL,
        to_file=config.LOG_TO_FILE,
        file_path=config.LOG_FILE_PATH,
    )

    with TemporaryDirectory(prefix="vdu_cli_") as temp_dir_str:
        temp_dir = Path(temp_dir_str)
        logger.info(f"Временная папка создана: {temp_dir}")
        try:
            download_result = download_video(args.url, temp_dir)
            if download_result["status"] != "успех":
                raise CliOperationError(f"Скачивание не удалось: {download_result.get('error', 'Неизвестная ошибка')}")

            downloaded_file_path = download_result["path"]
            filename = downloaded_file_path.name
            cloud_path = args.path or ""

            if args.cloud:
                logger.info(f"Загрузка в '{args.cloud}'...")
                task = {
                    "file_path": str(downloaded_file_path),
                    "cloud_storage": args.cloud,
                    "cloud_folder_path": cloud_path,
                    "filename": filename,
                }
                # Запускаем асинхронную функцию
                upload_result = asyncio.run(upload_single_file(task))
                if upload_result["status"] != "успех":
                    raise CliOperationError(f"Загрузка не удалась: {upload_result.get('error', 'Неизвестная ошибка')}")
                logger.info(f"Файл успешно загружен. URL/Path: {upload_result.get('url') or upload_result.get('path')}")
            else:
                logger.warning(f"Облако не выбрано, файл только скачан и сохранен в: {downloaded_file_path}")

        except Exception as e:
            logger.critical(f"Критическая ошибка в режиме CLI: {e}", exc_info=True)
            sys.exit(1)

if __name__ == "__main__":
    main()  # pragma: no cover