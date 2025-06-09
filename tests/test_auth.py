import pytest
from unittest.mock import patch, MagicMock
from pathlib import Path
import re

# Импортируем тестируемые функции и классы
from src.auth import get_yandex_token, get_google_drive_credentials, AuthError
from src.config import AppSettings
from pydantic import SecretStr


# Очистка кеша перед каждым тестом, чтобы избежать влияния одного теста на другой
@pytest.fixture(autouse=True)
def clear_auth_caches():
    """Фикстура для автоматической очистки кеша в src.auth перед каждым тестом."""
    with patch("src.auth._yandex_token_cache", None), patch(
        "src.auth._google_creds_cache", None
    ):
        yield


@pytest.fixture
def mock_app_settings():
    """Фабрика для создания моков AppSettings с нужными параметрами."""

    def _factory(**kwargs):
        # Используем model_construct для создания экземпляра без валидации,
        # так как нам не нужны реальные файлы для путей в большинстве тестов.
        mock_settings = AppSettings.model_construct(**kwargs)

        # Мокаем get_config в модуле auth, чтобы он возвращал наш объект настроек
        patcher = patch("src.auth.get_config", return_value=mock_settings)
        patcher.start()
        # Возвращаем patcher, чтобы можно было его остановить после теста
        return patcher

    yield _factory
    # Убираем все патчи после завершения теста, чтобы не влиять на другие тесты
    patch.stopall()


# ==============================================================================
# Тесты для get_yandex_token
# ==============================================================================


def test_get_yandex_token_success(mock_app_settings):
    """Тест успешного получения токена Yandex."""
    mock_app_settings(YANDEX_TOKEN=SecretStr("test_token_123"))
    token = get_yandex_token()
    assert token == "test_token_123"


def test_get_yandex_token_cached(mock_app_settings):
    """Тест, что токен Yandex кешируется после первого вызова."""
    mock_settings_provider = mock_app_settings(YANDEX_TOKEN=SecretStr("test_token_123"))

    # Первый вызов - должен получить из "конфига"
    assert get_yandex_token() == "test_token_123"

    # Второй вызов - должен быть из кеша. Мы меняем конфиг, чтобы это проверить.
    mock_settings_provider.stop()  # останавливаем старый патч
    mock_app_settings(YANDEX_TOKEN=SecretStr("new_token_456"))
    assert get_yandex_token() == "test_token_123"  # Проверяем, что значение старое


def test_get_yandex_token_failure_not_set(mock_app_settings):
    """Тест ошибки, когда YANDEX_TOKEN не установлен."""
    mock_app_settings(YANDEX_TOKEN=None)
    with pytest.raises(AuthError, match="YANDEX_TOKEN не найден в конфигурации"):
        get_yandex_token()


# ==============================================================================
# Тесты для get_google_drive_credentials
# ==============================================================================


@patch("src.auth.Credentials")
@patch("src.auth.os.path.exists")
def test_get_google_drive_credentials_from_valid_token_file(
    mock_exists, MockCredentials, mock_app_settings, tmp_path
):
    """Успешное получение учетных данных из существующего и валидного token.json."""
    creds_file = tmp_path / "credentials.json"
    creds_file.touch()
    mock_app_settings(GOOGLE_CREDENTIALS=creds_file)

    mock_exists.return_value = True  # token.json существует
    mock_creds_instance = MagicMock(valid=True)
    MockCredentials.from_authorized_user_file.return_value = mock_creds_instance

    creds = get_google_drive_credentials()

    assert creds == mock_creds_instance
    MockCredentials.from_authorized_user_file.assert_called_once_with(
        "token.json", ["https://www.googleapis.com/auth/drive.file"]
    )


@patch("src.auth.Credentials")
@patch("src.auth.os.path.exists")
def test_get_google_drive_credentials_expired_token_refresh_success(
    mock_exists, MockCredentials, mock_app_settings, tmp_path
):
    """Тест успешного обновления истекшего токена."""
    creds_file = tmp_path / "credentials.json"
    creds_file.touch()
    mock_app_settings(GOOGLE_CREDENTIALS=creds_file)

    mock_exists.return_value = True  # token.json существует
    mock_creds_instance = MagicMock(
        valid=False, expired=True, refresh_token="some_refresh_token"
    )
    MockCredentials.from_authorized_user_file.return_value = mock_creds_instance

    creds = get_google_drive_credentials()

    assert creds == mock_creds_instance
    mock_creds_instance.refresh.assert_called_once()


@patch("builtins.open")
@patch("src.auth.InstalledAppFlow")
@patch("src.auth.os.path.exists", return_value=False)  # token.json не существует
def test_get_google_drive_credentials_oauth_flow(
    mock_exists, mock_flow, mock_open, mock_app_settings, tmp_path
):
    """Тест полного цикла OAuth, когда токен отсутствует."""
    creds_file = tmp_path / "credentials.json"
    creds_file.touch()
    mock_app_settings(GOOGLE_CREDENTIALS=creds_file)

    mock_flow_instance = mock_flow.from_client_secrets_file.return_value
    mock_creds = MagicMock()
    mock_flow_instance.run_local_server.return_value = mock_creds

    returned_creds = get_google_drive_credentials()

    assert returned_creds == mock_creds
    mock_flow.from_client_secrets_file.assert_called_once_with(
        creds_file, ["https://www.googleapis.com/auth/drive.file"]
    )
    mock_flow_instance.run_local_server.assert_called_once_with(port=0)
    mock_open.assert_called_once_with("token.json", "w")
    mock_creds.to_json.assert_called_once()


def test_get_google_drive_credentials_no_creds_file(mock_app_settings):
    """Тест ошибки, если файл credentials.json не найден."""
    non_existent_path = Path("/path/to/non_existent_credentials.json")
    mock_app_settings(GOOGLE_CREDENTIALS=non_existent_path)

    with pytest.raises(
        AuthError,
        match=re.escape(
            f"Файл учетных данных Google 'credentials.json' не найден по пути: {non_existent_path}"
        ),
    ):
        get_google_drive_credentials()
