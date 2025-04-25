import pytest
from src.uploader import upload_to_yandex_disk, upload_to_google_drive

def test_upload_yandex_invalid_token(monkeypatch):
    monkeypatch.setattr("src.uploader.get_yandex_token", lambda: "bad_token")
    with pytest.raises(Exception):
        upload_to_yandex_disk("fake.mp4", "", "fake.mp4", max_retries=1)

def test_upload_google_invalid_creds(monkeypatch):
    monkeypatch.setattr("src.uploader.get_google_drive_credentials", lambda: None)
    with pytest.raises(Exception):
        upload_to_google_drive("fake.mp4", "root", "", "fake.mp4", max_retries=1)
