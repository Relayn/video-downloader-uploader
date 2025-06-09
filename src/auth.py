from typing import Optional
import os
import time
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from src.config import get_config
from src.logger import setup_logger

# Инициализация логгера вынесена на уровень модуля
config = get_config()
logger = setup_logger(
    "auth",
    level=config.LOG_LEVEL,
    to_file=config.LOG_TO_FILE,
    file_path=config.LOG_FILE_PATH,
)

# Кеш в памяти для учетных данных на время сессии
_yandex_token_cache: Optional[str] = None
_google_creds_cache: Optional[Credentials] = None


class AuthError(Exception):
    """Пользовательское исключение для ошибок аутентификации."""

    pass


def get_yandex_token() -> str:
    """
    Получает токен Яндекс.Диска из конфигурации с кешированием в памяти.

    Returns:
        Токен в виде строки.

    Raises:
        AuthError: Если токен не найден в конфигурации.
    """
    global _yandex_token_cache
    if _yandex_token_cache:
        logger.debug("Возврат кешированного токена Yandex.")
        return _yandex_token_cache

    logger.debug("Попытка получить токен Yandex из конфигурации.")
    yandex_token_secret = get_config().YANDEX_TOKEN

    if yandex_token_secret:
        token = yandex_token_secret.get_secret_value()
        _yandex_token_cache = token
        logger.info("Токен Яндекс.Диска успешно получен и кеширован.")
        return token

    logger.error("YANDEX_TOKEN не найден в конфигурации.")
    raise AuthError("YANDEX_TOKEN не найден в конфигурации.")


def get_google_drive_credentials() -> Credentials:
    """
    Получает и кеширует учетные данные Google Drive.

    Проверяет наличие `token.json`, и если он невалиден или отсутствует,
    запускает процесс OAuth2 авторизации.

    Returns:
        Объект `Credentials`.

    Raises:
        AuthError: Если не удалось получить учетные данные.
    """
    global _google_creds_cache
    if _google_creds_cache and _google_creds_cache.valid:
        logger.debug("Возврат кешированных учетных данных Google.")
        return _google_creds_cache

    config = get_config()
    creds_path = config.GOOGLE_CREDENTIALS

    if not creds_path or not creds_path.exists():
        raise AuthError(
            f"Файл учетных данных Google 'credentials.json' не найден по пути: {creds_path}"
        )

    SCOPES = ["https://www.googleapis.com/auth/drive.file"]
    creds = None
    token_file = "token.json"

    if os.path.exists(token_file):
        try:
            creds = Credentials.from_authorized_user_file(token_file, SCOPES)
            logger.debug(f"Учетные данные загружены из {token_file}")
        except Exception as e:
            logger.warning(
                f"Не удалось загрузить {token_file}: {e}. Потребуется новая авторизация."
            )
            creds = None

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                logger.info("Обновление истекшего токена Google Drive...")
                creds.refresh(Request())
            except Exception as e:
                logger.error(
                    f"Ошибка обновления токена: {e}. Потребуется новая авторизация."
                )
                creds = None  # Сброс для повторной аутентификации

        if not creds:  # Эта проверка нужна после попытки обновления
            logger.info("Необходима новая авторизация Google Drive.")
            try:
                flow = InstalledAppFlow.from_client_secrets_file(creds_path, SCOPES)
                creds = flow.run_local_server(port=0)
            except Exception as e:
                msg = f"Не удалось выполнить авторизацию Google Drive: {e}"
                logger.critical(msg, exc_info=True)
                raise AuthError(msg) from e

        try:
            with open(token_file, "w") as token:
                token.write(creds.to_json())
            logger.info(f"Учетные данные Google Drive сохранены в {token_file}")
        except Exception as e:
            logger.error(f"Не удалось сохранить {token_file}: {e}")

    _google_creds_cache = creds
    return creds
