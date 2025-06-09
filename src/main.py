import argparse
import sys
from pathlib import Path

from src.config import get_config, setup_logger, ConfigError
from src.downloader import download_video
from src.gui import main as show_gui
from src.uploader import upload_to_google_drive, upload_to_yandex_disk


def main():
    """Основная функция, обрабатывающая аргументы командной строки или запускающая GUI."""
    parser = argparse.ArgumentParser(description="Скачивание и загрузка видео.")
    parser.add_argument("--url", help="URL видео для скачивания.")
    parser.add_argument(
        "--cloud", choices=["google", "yandex"], help="Облачное хранилище."
    )
    parser.add_argument("--path", help="Путь для загрузки в облаке.")
    args = parser.parse_args()

    if not any(vars(args).values()):
        # Если аргументы не переданы, запускаем GUI
        show_gui()
        sys.exit()

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

    if not args.url:
        logger.error("Аргумент --url обязателен для режима CLI.")
        sys.exit(1)

    from tempfile import TemporaryDirectory

    with TemporaryDirectory(prefix=config.TEMP_DIR_PREFIX) as temp_dir:
        logger.info(f"Временная папка создана: {temp_dir}")
        try:
            downloaded_file = download_video(args.url, Path(temp_dir))
            if not downloaded_file:
                raise Exception("Скачивание не удалось, файл не был получен.")

            filename = downloaded_file.name
            cloud_path = args.path or ""

            if args.cloud == "google":
                logger.info("Загрузка на Google Drive...")
                upload_to_google_drive(downloaded_file, cloud_path, filename)
            elif args.cloud == "yandex":
                logger.info("Загрузка на Яндекс.Диск...")
                # Запускаем асинхронную функцию
                import asyncio

                asyncio.run(
                    upload_to_yandex_disk(downloaded_file, cloud_path, filename)
                )
            else:
                logger.warning("Облако не выбрано, файл только скачан.")

        except Exception as e:
            logger.critical(f"Критическая ошибка в режиме CLI: {e}", exc_info=True)
            sys.exit(1)


if __name__ == "__main__":
    main()
