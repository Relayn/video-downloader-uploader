import pytest
from src.downloader import download_video

def test_download_invalid_url(tmp_path):
    with pytest.raises(Exception):
        download_video("not_a_url", str(tmp_path))

# Для ускорения: мокать yt-dlp при необходимости
