from typing import Optional
import os
import time
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from logger import setup_logger
from config import LOG_LEVEL, LOG_TO_FILE, LOG_FILE_PATH, GOOGLE_CREDENTIALS

logger = setup_logger("auth", level=LOG_LEVEL, to_file=LOG_TO_FILE, file_path=LOG_FILE_PATH)

# Кеш токенов на время работы процесса
_yandex_token_cache = None
_google_creds_cache = None

class AuthError(Exception):
    pass

def get_yandex_token(retries: int = 3) -> str:
    """Получает токен Яндекс.Диска из переменной окружения с кешированием, логированием времени и повторными попытками."""
    global _yandex_token_cache
    if _yandex_token_cache:
        return _yandex_token_cache
    last_exc = None
    t0 = time.time()
    for attempt in range(1, retries + 1):
        try:
            token = os.getenv("YANDEX_TOKEN")
            if not token:
                raise AuthError("YANDEX_TOKEN не задан в .env")
            _yandex_token_cache = token
            elapsed = time.time() - t0
            logger.info(f"Токен Яндекс.Диска получен (время: {elapsed:.2f} сек, попытка {attempt})")
            return token
        except Exception as e:
            logger.error(f"Ошибка получения токена Яндекс.Диска (попытка {attempt}): {e}")
            last_exc = e
            time.sleep(2 * attempt)
    raise AuthError(f"Не удалось получить токен Яндекс.Диска после {retries} попыток: {last_exc}")

def get_google_drive_credentials(retries: int = 3) -> Credentials:
    """Получает учетные данные Google Drive с кешированием, логированием времени и повторными попытками."""
    global _google_creds_cache
    if _google_creds_cache:
        return _google_creds_cache
    last_exc = None
    t0 = time.time()
    for attempt in range(1, retries + 1):
        try:
            creds = None
            if os.path.exists("token.json"):
                creds = Credentials.from_authorized_user_file("token.json", ["https://www.googleapis.com/auth/drive.file"])
            if not creds or not creds.valid:
                flow = InstalledAppFlow.from_client_secrets_file(GOOGLE_CREDENTIALS, ["https://www.googleapis.com/auth/drive.file"])
                creds = flow.run_local_server(port=0)
                with open("token.json", "w") as token_file:
                    token_file.write(creds.to_json())
            _google_creds_cache = creds
            elapsed = time.time() - t0
            logger.info(f"Токен Google Drive получен (время: {elapsed:.2f} сек, попытка {attempt})")
            return creds
        except Exception as e:
            logger.error(f"Ошибка получения токена Google Drive (попытка {attempt}): {e}")
            last_exc = e
            time.sleep(2 * attempt)
    raise AuthError(f"Не удалось получить токен Google Drive после {retries} попыток: {last_exc}")