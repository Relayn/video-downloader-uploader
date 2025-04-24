# Video Downloader & Uploader

## Описание
**Video Downloader & Uploader** — это инструмент для скачивания видео с популярных платформ (например, YouTube, Vimeo) и последующей загрузки их в облачные хранилища (Google Drive, Яндекс.Диск и др.). Проект ориентирован на простоту использования, расширяемость и безопасность.

## Основные возможности

Скачивание видео: Поддержка YouTube, TikTok, Instagram Reels через библиотеку yt-dlp с минимальным перекодированием.
Загрузка в облако: Автоматическая загрузка в Яндекс.Диск или Google Drive с поддержкой создания папок.
Обработка имен файлов: Генерация безопасных имен файлов на основе метаданных видео или пользовательского ввода.
Безопасная аутентификация: Поддержка OAuth2 для Google Drive и токенов для Яндекс.Диска через переменные окружения.
Логирование: Детализированное логирование для диагностики и отладки.
Модульная архитектура: Легко добавить новые платформы или хранилища.

## Структура проекта
```
video-downloader-uploader/
├── src/
│   ├── downloader.py    # Логика скачивания видео
│   ├── uploader.py      # Логика загрузки в облако
│   ├── auth.py          # Управление аутентификацией
│   ├── logger.py        # Настройка логирования
│   └── main.py          # Основной модуль
├── tests/
│   └── test_main.py     # Юнит-тесты
├── .env                 # Переменные окружения (токены)
├── requirements.txt     # Зависимости
├── PLANNING.md          # Планирование
└── README.md            # Инструкции
```

## Быстрый старт
1. Клонируйте репозиторий:
   ```sh
   git clone https://github.com/yourusername/video-downloader-uploader.git
   cd video-downloader-uploader
   ```
2. Установите зависимости:
   ```sh
   pip install -r requirements.txt
   ```
3. Создайте и заполните файл `.env` своими токенами и ключами.
4. Запустите основной модуль:
   ```sh
   python src/main.py
   ```

## Использование
- Настройте параметры скачивания и загрузки в файле конфигурации или через переменные окружения.
- Поддерживаются различные облачные сервисы (расширяемо).
- Логирование и обработка ошибок реализованы для удобства отладки.

## Параметры
Параметр | Тип | Описание
---------|-----|---------
video_url | str | Обязательный. URL видео (YouTube, TikTok, Instagram).
cloud_storage | str | Обязательный. Хранилище: "Yandex.Disk" или "Google Drive".
yandex_token | str | Токен для Яндекс.Диска (или использовать .env).
google_drive_folder_id | str | ID папки Google Drive (или "root" для корневой папки).
cloud_folder_path | str | Путь к папке в облаке (создается, если не существует).
upload_filename | str | Желаемое имя файла (без расширения, опционально).

## Примеры
Загрузка на Яндекс.Диск
```python
args = {
    "video_url": "https://www.instagram.com/reel/abc123",
    "cloud_storage": "Yandex.Disk",
    "cloud_folder_path": "/MyVideos/Downloads",
}
result = download_and_upload_video(args)
print(result)
```

Загрузка на Google Drive
```python
args = {
    "video_url": "https://www.youtube.com/watch?v=XfTWgMgknpY",
    "cloud_storage": "Google Drive",
    "google_drive_folder_id": "your_folder_id_here",
    "cloud_folder_path": "Videos",
}
result = download_and_upload_video(args)
print(result)
```

## Тестирование
Для запуска тестов используйте:
```sh
pytest tests/
```

## Вклад и поддержка
Будем рады вашим предложениям и pull request'ам! Открыты к сотрудничеству.

## Лицензия
Проект распространяется под MIT License.

## Контакты
Если у вас есть вопросы или предложения, создайте issue или свяжитесь через email@example.com.

Сделано с ❤️ для автоматизации задач скачивания и загрузки видео!
