import pytest
from unittest.mock import patch, MagicMock
from pydantic import SecretStr
from src import auth
from src.auth import get_yandex_token, get_google_drive_credentials, AuthError, _load_creds_from_token_file, _refresh_creds, _run_oauth_flow
from src.config import AppSettings


@pytest.fixture(autouse=True)
def clear_caches():
    """Фикстура для автоматической очистки кеша в src.auth перед каждым тестом."""
    auth._yandex_token_cache = None
    auth._google_creds_cache = None
    yield


@pytest.fixture
def mock_config(monkeypatch):
    """Фабрика для создания и внедрения мока AppSettings."""
    def _factory(**kwargs):
        if 'GOOGLE_CREDS_PATH' not in kwargs:
            kwargs['GOOGLE_CREDS_PATH'] = 'dummy_creds.json'
        settings = AppSettings.model_construct(**kwargs)
        monkeypatch.setattr(auth, "get_config", lambda: settings)
        return settings
    return _factory

# ==================================
# Тесты для get_yandex_token
# ==================================

def test_get_yandex_token_success(mock_config):
    mock_config(YANDEX_DISK_TOKEN=SecretStr("test-token"))
    assert get_yandex_token() == "test-token"


def test_get_yandex_token_not_set_raises_error(mock_config):
    mock_config(YANDEX_DISK_TOKEN=None)
    with pytest.raises(AuthError, match="YANDEX_DISK_TOKEN не найден"):
        get_yandex_token()


def test_get_yandex_token_is_cached(mock_config):
    mock_config(YANDEX_DISK_TOKEN=SecretStr("first-call-token"))
    token1 = get_yandex_token()
    assert token1 == "first-call-token"
    mock_config(YANDEX_DISK_TOKEN=SecretStr("second-call-token"))
    token2 = get_yandex_token()
    assert token2 == "first-call-token"


# ==================================
# Тесты для get_google_drive_credentials (оркестратор)
# ==================================

def test_get_google_creds_cache_hit(mock_config):
    """Тест: если в кеше есть валидные учетные данные, они возвращаются немедленно."""
    mock_creds = MagicMock(valid=True)
    auth._google_creds_cache = mock_creds
    with patch("src.auth._load_creds_from_token_file") as mock_load:
        creds = get_google_drive_credentials()
        assert creds is mock_creds
        mock_load.assert_not_called()


@patch("src.auth._run_oauth_flow", return_value=MagicMock(valid=True))
@patch("src.auth._refresh_creds", return_value=None)
@patch("src.auth._load_creds_from_token_file")
@patch("src.auth.os.path.exists", return_value=True)
def test_get_google_creds_full_flow(mock_path_exists, mock_load, mock_refresh, mock_run_flow, mock_config):
    """Тест полного цикла: загрузка не удалась, обновление не удалось, запускается OAuth."""
    mock_config()
    mock_load.return_value = MagicMock(valid=False, expired=True, refresh_token="token")
    get_google_drive_credentials()
    mock_load.assert_called_once()
    mock_refresh.assert_called_once()
    mock_run_flow.assert_called_once()


@patch("src.auth._run_oauth_flow", return_value=None)
@patch("src.auth._load_creds_from_token_file", return_value=None)
@patch("src.auth.os.path.exists", return_value=True)
def test_get_google_creds_oauth_flow_fails_raises_error(mock_path_exists, mock_load, mock_run_flow, mock_config):
    """Тест: если полный цикл OAuth не возвращает учетные данные, выбрасывается ошибка."""
    mock_config()
    with pytest.raises(AuthError, match="Не удалось получить учетные данные Google Drive"):
        get_google_drive_credentials()


@patch("src.auth.os.path.exists", return_value=False)
def test_get_google_creds_no_creds_file_raises_error(mock_path_exists, mock_config):
    """Тест: если файл credentials.json не найден, выбрасывается ошибка."""
    mock_config(GOOGLE_CREDS_PATH="non-existent.json")
    with pytest.raises(AuthError, match="Файл учетных данных Google 'credentials.json' не найден"):
        get_google_drive_credentials()

# ==================================
# Тесты для вспомогательных функций
# ==================================

@patch("src.auth.Credentials")
@patch("src.auth.os.path.exists", return_value=True)
def test_load_creds_from_token_file_success(mock_path_exists, mock_credentials):
    """Тест успешной загрузки из token.json."""
    mock_creds_instance = MagicMock()
    mock_credentials.from_authorized_user_file.return_value = mock_creds_instance
    creds = _load_creds_from_token_file("token.json")
    assert creds is mock_creds_instance
    mock_credentials.from_authorized_user_file.assert_called_once_with("token.json", scopes=["https://www.googleapis.com/auth/drive"])


@patch("src.auth.os.path.exists", return_value=False)
def test_load_creds_from_token_file_not_exists(mock_path_exists):
    """Тест: если token.json не существует, возвращается None."""
    assert _load_creds_from_token_file("token.json") is None


@patch("src.auth.Credentials.from_authorized_user_file", side_effect=Exception("Corrupted"))
@patch("src.auth.os.path.exists", return_value=True)
def test_load_creds_from_token_file_corrupted(mock_path_exists, mock_from_file):
    """Тест: если token.json поврежден, возвращается None."""
    assert _load_creds_from_token_file("token.json") is None


def test_refresh_creds_success():
    """Тест успешного обновления токена."""
    mock_creds = MagicMock()
    refreshed = _refresh_creds(mock_creds, "token.json")
    assert refreshed is mock_creds
    mock_creds.refresh.assert_called_once()


@patch("src.auth.os.remove")
@patch("src.auth.os.path.exists", return_value=True)
def test_refresh_creds_failure(mock_path_exists, mock_os_remove):
    """Тест: если обновление не удалось, старый токен удаляется и возвращается None."""
    mock_creds = MagicMock()
    mock_creds.refresh.side_effect = Exception("Refresh failed")
    refreshed = _refresh_creds(mock_creds, "token.json")
    assert refreshed is None
    mock_os_remove.assert_called_once_with("token.json")


@patch("builtins.open")
@patch("src.auth.InstalledAppFlow")
def test_run_oauth_flow_success(mock_flow, mock_open):
    """Тест успешного прохождения OAuth 2.0."""
    mock_flow_instance = mock_flow.from_client_secrets_file.return_value
    mock_creds = MagicMock()
    mock_creds.to_json.return_value = "{}"
    mock_flow_instance.run_local_server.return_value = mock_creds
    creds = _run_oauth_flow("creds.json", "token.json")
    assert creds is mock_creds
    mock_flow.from_client_secrets_file.assert_called_once_with("creds.json", scopes=["https://www.googleapis.com/auth/drive"])
    mock_flow_instance.run_local_server.assert_called_once_with(port=0)
    mock_open.assert_called_once_with("token.json", "w")


@patch("src.auth.InstalledAppFlow.from_client_secrets_file", side_effect=Exception("Flow error"))
def test_run_oauth_flow_failure(mock_from_file):
    """Тест: если в процессе OAuth возникает ошибка, возвращается None."""
    creds = _run_oauth_flow("creds.json", "token.json")
    assert creds is None