import pytest
import os
import time
from unittest.mock import patch, MagicMock, call
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from src import downloader
from src.config import AppSettings

from src.downloader import (
    download_video,
    batch_download_videos,
    DownloadError,
    find_downloaded_file,
)

# --- Тесты для find_downloaded_file ---


def test_find_downloaded_file_exact_match(tmp_path):
    slug = "test-video"
    ext = "mp4"
    expected_file = tmp_path / f"{slug}.{ext}"
    expected_file.touch()
    assert find_downloaded_file(str(tmp_path), slug, ext) == str(expected_file)


def test_find_downloaded_file_slug_in_name_match(tmp_path):
    slug = "test-video"
    ext = "mp4"
    target_file = tmp_path / f"some_prefix-{slug}-some_suffix.{ext}"
    target_file.touch()
    (tmp_path / f"other_video.{ext}").touch()
    assert find_downloaded_file(str(tmp_path), slug, ext) == str(target_file)


def test_find_downloaded_file_only_ext_match(tmp_path):
    slug = "non-existent-slug"
    ext = "mp4"
    target_file = tmp_path / f"some_video.{ext}"
    target_file.touch()
    (tmp_path / "other_video.mkv").touch()
    assert find_downloaded_file(str(tmp_path), slug, ext) == str(target_file)


def test_find_downloaded_file_multiple_ext_match_returns_first(tmp_path):
    slug = "non-existent-slug"
    ext = "mp4"
    file_a = tmp_path / "aaa_video.mp4"
    file_b = tmp_path / "bbb_video.mp4"
    file_a.touch()
    file_b.touch()
    with patch(
        "src.downloader.os.listdir", return_value=["aaa_video.mp4", "bbb_video.mp4"]
    ):
        assert find_downloaded_file(str(tmp_path), slug, ext) == str(file_a)
    with patch(
        "src.downloader.os.listdir", return_value=["bbb_video.mp4", "aaa_video.mp4"]
    ):
        assert find_downloaded_file(str(tmp_path), slug, ext) == str(file_b)


def test_find_downloaded_file_not_found(tmp_path):
    assert find_downloaded_file(str(tmp_path), "any-slug", "mp4") is None


def test_find_downloaded_file_empty_dir(tmp_path):
    assert find_downloaded_file(str(tmp_path), "any-slug", "mp4") is None


# --- Тесты для download_video ---


@pytest.fixture
def mock_config(monkeypatch):
    """Фикстура для мокирования get_config в модуле downloader."""
    settings = AppSettings.model_construct(
        YTDLP_FORMAT="best", YTDLP_RETRIES=3, FFMPEG_PATH=None
    )
    # Поскольку get_config больше не синглтон, мы должны патчить сам AppSettings
    # чтобы при его вызове возвращался наш настроенный экземпляр
    monkeypatch.setattr(downloader, "get_config", lambda: settings)
    return settings


@patch("src.downloader.yt_dlp.YoutubeDL")
def test_download_video_success(mock_youtube_dl, mock_config, tmp_path):
    """Тест успешного скачивания видео."""
    mock_downloader_instance = MagicMock()
    mock_downloader_instance.download.return_value = 0
    mock_youtube_dl.return_value.__enter__.return_value = mock_downloader_instance

    # Моделируем, что yt-dlp создал файл
    # yt-dlp может создавать имена файлов, которые мы не контролируем,
    # поэтому используем find_downloaded_file для поиска
    expected_file = tmp_path / "test_video.mp4"
    expected_file.touch()

    with patch("src.downloader.find_downloaded_file", return_value=str(expected_file)):
        result_path = download_video("some_url", "some-slug", str(tmp_path))

    assert result_path == str(expected_file)
    mock_youtube_dl.assert_called_once()
    # Проверяем, что outtmpl использует slug, а не title
    slug_used_in_call = "some-slug"
    expected_outtmpl = os.path.join(str(tmp_path), f"{slug_used_in_call}.%(ext)s")
    assert mock_youtube_dl.call_args[0][0]["outtmpl"] == expected_outtmpl


@patch("src.downloader.yt_dlp.YoutubeDL")
def test_download_video_failure(mock_youtube_dl, mock_config, tmp_path):
    """Тест ошибки при скачивании (yt-dlp вернул ошибку)."""
    mock_downloader_instance = MagicMock()
    mock_downloader_instance.download.return_value = 1
    mock_youtube_dl.return_value.__enter__.return_value = mock_downloader_instance

    with pytest.raises(DownloadError):
        download_video("some_url", "some-slug", str(tmp_path))


# --- Тесты для batch_download_videos ---


@patch("src.downloader.download_video")
def test_batch_download(mock_download_video, tmp_path):
    """Тест успешного пакетного скачивания."""
    urls = ["http://test.com/1", "http://test.com/2"]
    # Мокаем результат для каждого вызова
    mock_download_video.side_effect = [
        str(tmp_path / "video1.mp4"),
        str(tmp_path / "video2.mp4"),
    ]

    results = batch_download_videos(urls, str(tmp_path))

    assert len(results) == 2
    assert mock_download_video.call_count == 2
    # Проверяем, что результаты корректны
    assert all(r["status"] == "успех" for r in results)
    assert results[0]["url"] in urls
    assert results[1]["url"] in urls


@patch("src.downloader.download_video", side_effect=DownloadError("Test error"))
def test_batch_download_with_failures(mock_download_video, tmp_path):
    """Тест пакетного скачивания с ошибками."""
    urls = ["http://test.com/1", "http://test.com/2"]

    results = batch_download_videos(urls, str(tmp_path))

    assert len(results) == 2
    assert all(r["status"] == "ошибка" for r in results)
    assert results[0]["message"] == "Test error"
