import os
import sys
from typing import Optional, Tuple

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from pydantic import SecretStr

from src.config import get_config, AppSettings
from src.logger import setup_logger

logger = setup_logger("auth")

# Кеш для учетных данных, чтобы не пересоздавать их при каждом вызове
_yandex_token_cache: Optional[str] = None
_google_creds_cache: Optional[Credentials] = None


class AuthError(Exception):
    """Пользовательское исключение для ошибок аутентификации."""
    pass


def get_yandex_token() -> str:
    """
    Возвращает токен Яндекс.Диска из конфигурации.

    Кеширует результат для последующих вызовов, чтобы избежать повторного
    чтения конфигурации.

    Returns:
        str: Токен Яндекс.Диска.

    Raises:
        AuthError: Если токен не найден в конфигурации.
    """
    global _yandex_token_cache
    if _yandex_token_cache:
        return _yandex_token_cache

    config = get_config()
    token_secret = config.YANDEX_DISK_TOKEN
    if not token_secret:
        raise AuthError("YANDEX_DISK_TOKEN не найден в конфигурации (.env).")

    token = token_secret.get_secret_value()
    _yandex_token_cache = token
    logger.info("Токен Яндекс.Диска успешно загружен.")
    return token


def _load_creds_from_token_file(token_path: str) -> Optional[Credentials]:
    """Пытается загрузить учетные данные из файла token.json."""
    if os.path.exists(token_path):
        try:
            return Credentials.from_authorized_user_file(token_path, scopes=["https://www.googleapis.com/auth/drive"])
        except Exception as e:
            logger.warning(f"Не удалось загрузить {token_path}: {e}. Потребуется повторная авторизация.")
    return None


def _refresh_creds(creds: Credentials, token_path: str) -> Optional[Credentials]:
    """Обновляет истекший токен и возвращает обновленные учетные данные."""
    logger.info("Токен Google истек, обновляем...")
    try:
        creds.refresh(Request())
        return creds
    except Exception as e:
        logger.error(f"Не удалось обновить токен Google: {e}", exc_info=True)
        # Если обновление не удалось, удаляем старый токен, чтобы инициировать полный цикл OAuth
        if os.path.exists(token_path):
            os.remove(token_path)
    return None


def _run_oauth_flow(creds_path: str, token_path: str) -> Optional[Credentials]:
    """Запускает полный цикл OAuth 2.0 для получения новых учетных данных."""
    logger.info("Требуется авторизация Google Drive...")
    try:
        flow = InstalledAppFlow.from_client_secrets_file(creds_path, scopes=["https://www.googleapis.com/auth/drive"])
        creds = flow.run_local_server(port=0)
        # Сохраняем учетные данные для следующего запуска
        with open(token_path, "w") as token_file:
            token_file.write(creds.to_json())
        logger.info(f"Учетные данные Google сохранены в {token_path}")
        return creds
    except Exception as e:
        logger.error(f"Ошибка в процессе авторизации Google: {e}", exc_info=True)
    return None


def get_google_drive_credentials() -> Credentials:
    """
    Управляет получением учетных данных Google Drive с кешированием.

    Выполняет следующие шаги:
    1. Возвращает валидные учетные данные из кеша, если они есть.
    2. Пытается загрузить учетные данные из файла `token.json`.
    3. Если токен истек, пытается его обновить.
    4. Если ничего не помогло, запускает полный цикл OAuth 2.0.
    5. В случае успеха кеширует результат.

    Returns:
        Credentials: Валидные учетные данные Google Drive.

    Raises:
        AuthError: Если файл `credentials.json` не найден или не удалось
                   пройти аутентификацию.
    """
    global _google_creds_cache
    if _google_creds_cache and _google_creds_cache.valid:
        return _google_creds_cache

    config = get_config()
    creds_path = config.GOOGLE_CREDS_PATH
    token_path = "token.json"  # Путь к файлу с токеном

    if not creds_path or not os.path.exists(creds_path):
        raise AuthError(
            f"Файл учетных данных Google 'credentials.json' не найден по пути: {creds_path}"
        )

    creds = _load_creds_from_token_file(token_path)

    if creds and creds.valid:
        _google_creds_cache = creds
        return creds

    if creds and creds.expired and creds.refresh_token:
        refreshed_creds = _refresh_creds(creds, token_path)
        if refreshed_creds:
            _google_creds_cache = refreshed_creds
            return refreshed_creds

    # Если ничего не помогло, запускаем полный цикл авторизации
    new_creds = _run_oauth_flow(creds_path, token_path)
    if not new_creds:
        raise AuthError("Не удалось получить учетные данные Google Drive после прохождения авторизации.")

    _google_creds_cache = new_creds
    return new_creds