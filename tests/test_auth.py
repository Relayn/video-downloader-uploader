import pytest
from src.auth import get_yandex_token, get_google_drive_credentials

def test_yandex_token(monkeypatch):
    monkeypatch.setattr("src.auth.get_yandex_token", lambda: "test_token")
    assert get_yandex_token() == "test_token"

def test_google_drive_credentials(monkeypatch):
    monkeypatch.setattr("src.auth.get_google_drive_credentials", lambda: "test_creds")
    assert get_google_drive_credentials() == "test_creds"
