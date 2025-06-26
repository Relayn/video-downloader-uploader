import pytest
from unittest.mock import patch, MagicMock, call
from pydantic import SecretStr
from src import auth
from src.auth import get_yandex_token, get_google_drive_credentials, AuthError
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
# Тесты для get_google_drive_credentials
# ==================================

def test_get_google_creds_no_creds_file_raises_error(mock_config, tmp_path):
    mock_config(GOOGLE_CREDS_PATH=tmp_path / "non-existent.json")
    with pytest.raises(AuthError, match="Файл учетных данных Google 'credentials.json' не найден"):
        get_google_drive_credentials()


@patch("src.auth.os.path.exists", return_value=True)
@patch("src.auth.Credentials")
def test_get_google_creds_from_valid_token_file(MockCredentials, mock_os_exists, mock_config, tmp_path):
    creds_file = tmp_path / "credentials.json"
    creds_file.touch()
    mock_config(GOOGLE_CREDS_PATH=creds_file)
    mock_creds_instance = MagicMock(valid=True)
    MockCredentials.from_authorized_user_file.return_value = mock_creds_instance
    creds = get_google_drive_credentials()
    assert creds == mock_creds_instance
    mock_os_exists.assert_any_call("token.json")
    MockCredentials.from_authorized_user_file.assert_called_once()


@patch("src.auth.os.path.exists", return_value=True)
@patch("src.auth.Credentials")
@patch("builtins.open")
def test_get_google_creds_expired_token_refresh_success(mock_open, MockCredentials, mock_os_exists, mock_config, tmp_path):
    creds_file = tmp_path / "credentials.json"
    creds_file.touch()
    mock_config(GOOGLE_CREDS_PATH=creds_file)
    mock_creds_instance = MagicMock(valid=False, expired=True, refresh_token="some-token")
    mock_creds_instance.refresh = MagicMock()
    mock_creds_instance.to_json.return_value = '{"token": "refreshed"}'
    MockCredentials.from_authorized_user_file.return_value = mock_creds_instance
    get_google_drive_credentials()
    mock_creds_instance.refresh.assert_called_once()


@patch("src.auth.os.path.exists")
@patch("src.auth.InstalledAppFlow")
@patch("builtins.open")
def test_get_google_creds_full_oauth_flow(mock_open, MockFlow, mock_os_exists, mock_config, tmp_path):
    creds_file = tmp_path / "credentials.json"
    creds_file.touch()
    mock_config(GOOGLE_CREDS_PATH=creds_file)
    def exists_side_effect(path):
        return path == creds_file
    mock_os_exists.side_effect = exists_side_effect
    mock_flow_instance = MockFlow.from_client_secrets_file.return_value
    mock_creds = MagicMock()
    mock_creds.to_json.return_value = "{}"
    mock_flow_instance.run_local_server.return_value = mock_creds
    returned_creds = get_google_drive_credentials()
    assert returned_creds == mock_creds
    MockFlow.from_client_secrets_file.assert_called_once()
    mock_flow_instance.run_local_server.assert_called_once_with(port=0)
    mock_open.assert_called_once_with("token.json", "w")
    mock_creds.to_json.assert_called_once()


@patch("src.auth.os.path.exists")
@patch("src.auth.InstalledAppFlow")
@patch("builtins.open")
def test_get_google_creds_is_cached_simple(mock_open, MockFlow, mock_os_exists, mock_config, tmp_path):
    creds_file = tmp_path / "credentials.json"
    creds_file.touch()
    mock_config(GOOGLE_CREDS_PATH=creds_file)
    def exists_side_effect(path):
        return path == creds_file
    mock_os_exists.side_effect = exists_side_effect
    mock_flow_instance = MockFlow.from_client_secrets_file.return_value
    mock_creds = MagicMock(valid=True)
    mock_creds.to_json.return_value = "{}"
    mock_flow_instance.run_local_server.return_value = mock_creds
    creds1 = get_google_drive_credentials()
    assert creds1 == mock_creds
    assert mock_flow_instance.run_local_server.call_count == 1
    creds2 = get_google_drive_credentials()
    assert creds2 == mock_creds
    assert mock_flow_instance.run_local_server.call_count == 1

# ==================================
# Тесты для покрытия пропущенных строк
# ==================================

@patch("src.auth.os.path.exists")
@patch("src.auth.Credentials")
@patch("builtins.open")
def test_get_google_creds_corrupted_token_file(mock_open, MockCredentials, mock_os_exists, mock_config, tmp_path):
    creds_file = tmp_path / "credentials.json"
    creds_file.touch()
    mock_config(GOOGLE_CREDS_PATH=creds_file)
    def exists_side_effect(path):
        return True
    mock_os_exists.side_effect = exists_side_effect
    MockCredentials.from_authorized_user_file.side_effect = Exception("Corrupted file")
    with patch("src.auth.InstalledAppFlow") as MockFlow:
        mock_flow_instance = MockFlow.from_client_secrets_file.return_value
        mock_creds = MagicMock(valid=True)
        mock_creds.to_json.return_value = "{}"
        mock_flow_instance.run_local_server.return_value = mock_creds
        get_google_drive_credentials()
        mock_flow_instance.run_local_server.assert_called_once()


@patch("src.auth.os.path.exists")
@patch("src.auth.Credentials")
@patch("src.auth.os.remove")
@patch("builtins.open")
def test_get_google_creds_refresh_failure(mock_open, mock_os_remove, MockCredentials, mock_os_exists, mock_config, tmp_path):
    """Тест ошибки при обновлении токена (покрывает строки 82-86)."""
    creds_file = tmp_path / "credentials.json"
    creds_file.touch()
    mock_config(GOOGLE_CREDS_PATH=creds_file)

    def exists_side_effect(path):
        if path == creds_file:
            return True
        if path == "token.json":
            return not mock_os_remove.called
        return False
    mock_os_exists.side_effect = exists_side_effect

    mock_creds_instance = MagicMock(valid=False, expired=True, refresh_token="some-token")
    mock_creds_instance.refresh.side_effect = Exception("Refresh failed")
    MockCredentials.from_authorized_user_file.return_value = mock_creds_instance

    with patch("src.auth.InstalledAppFlow") as MockFlow:
        mock_flow_instance = MockFlow.from_client_secrets_file.return_value
        mock_creds = MagicMock(valid=True)
        mock_creds.to_json.return_value = "{}"
        mock_flow_instance.run_local_server.return_value = mock_creds

        get_google_drive_credentials()

        mock_creds_instance.refresh.assert_called_once()
        mock_os_remove.assert_called_once_with("token.json")
        mock_flow_instance.run_local_server.assert_called_once()