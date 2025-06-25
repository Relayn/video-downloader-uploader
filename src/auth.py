import os
import sys
from typing import Optional

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from pydantic import SecretStr

from src.config import get_config
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
    Кеширует результат для последующих вызовов.
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


def get_google_drive_credentials() -> Credentials:
    """
    Управляет получением учетных данных Google Drive.
    - Пытается загрузить из token.json.
    - Если токен истек, обновляет его.
    - Если token.json нет, запускает полный цикл OAuth 2.0.
    - Кеширует результат.
    """
    global _google_creds_cache
    if _google_creds_cache and _google_creds_cache.valid:
        return _google_creds_cache

    config = get_config()
    creds = None
    token_path = "token.json"
    creds_path = config.GOOGLE_CREDS_PATH

    if not creds_path or not os.path.exists(creds_path):
        raise AuthError(
            f"Файл учетных данных Google 'credentials.json' не найден по пути: {creds_path}"
        )

    # Файл token.json хранит access и refresh токены пользователя.
    # Он создается автоматически при первом успешном входе.
    if os.path.exists(token_path):
        try:
            creds = Credentials.from_authorized_user_file(token_path, scopes=["https://www.googleapis.com/auth/drive"])
        except Exception as e:
            logger.warning(f"Не удалось загрузить token.json: {e}. Потребуется повторная авторизация.")
            creds = None

    # Если учетных данных нет или они невалидны, позволяем пользователю войти.
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            logger.info("Токен Google истек, обновляем...")
            try:
                creds.refresh(Request())
            except Exception as e:
                logger.error(f"Не удалось обновить токен Google: {e}", exc_info=True)
                # Если обновление не удалось, удаляем старый токен и проходим авторизацию заново
                os.remove(token_path)
                return get_google_drive_credentials()
        else:
            logger.info("Требуется авторизация Google Drive...")
            flow = InstalledAppFlow.from_client_secrets_file(creds_path, scopes=["https://www.googleapis.com/auth/drive"])
            creds = flow.run_local_server(port=0)

        # Сохраняем учетные данные для следующего запуска
        with open(token_path, "w") as token_file:
            token_file.write(creds.to_json())
        logger.info("Учетные данные Google сохранены в token.json")

    _google_creds_cache = creds
    return creds