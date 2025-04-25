import pytest
from src.downloader import download_video
from src.uploader import upload_to_yandex_disk

def test_download_and_upload(monkeypatch, tmp_path):
    monkeypatch.setattr("src.downloader.download_video", lambda url, path: (str(tmp_path / "test.mp4"), "Test", "mp4"))
    monkeypatch.setattr("src.uploader.upload_to_yandex_disk", lambda fp, folder, fn, max_retries=3: "disk:/Test.mp4")
    file_path, title, ext = download_video("https://youtube.com/watch?v=abc", str(tmp_path))
    remote_path = upload_to_yandex_disk(file_path, "", "Test.mp4")
    assert remote_path == "disk:/Test.mp4"
