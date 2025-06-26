import pytest
from unittest.mock import patch, MagicMock
from pathlib import Path

# Тестируемый модуль
from src.downloader import download_video, is_ffmpeg_installed, DEFAULT_FILENAME_TEMPLATE


@patch('src.downloader.shutil.which')
def test_is_ffmpeg_installed(mock_which):
    """Тест для is_ffmpeg_installed."""
    # Сценарий 1: ffmpeg найден
    mock_which.return_value = '/usr/bin/ffmpeg'
    assert is_ffmpeg_installed() is True
    mock_which.assert_called_once_with("ffmpeg")

    # Сценарий 2: ffmpeg не найден
    mock_which.reset_mock()
    mock_which.return_value = None
    assert is_ffmpeg_installed() is False
    mock_which.assert_called_once_with("ffmpeg")


@patch('src.downloader.YoutubeDL')
def test_download_video_success(mock_youtube_dl, tmp_path):
    """Тест успешного скачивания видео."""
    url = "https://example.com/video"
    download_dir = tmp_path
    expected_filename = "test_video.mp4"
    expected_filepath = download_dir / expected_filename

    # Настраиваем мок для контекстного менеджера
    mock_ydl_instance = MagicMock()
    mock_youtube_dl.return_value.__enter__.return_value = mock_ydl_instance

    # Настраиваем мок для методов yt-dlp
    info_dict = {'title': 'test_video', 'ext': 'mp4'}
    mock_ydl_instance.extract_info.return_value = info_dict
    mock_ydl_instance.prepare_filename.return_value = str(expected_filepath)

    result = download_video(url, download_dir)

    # Проверяем, что YoutubeDL был вызван с правильными базовыми опциями
    mock_youtube_dl.assert_called_once()

    args, kwargs = mock_youtube_dl.call_args
    options_dict = args[0]
    assert options_dict['outtmpl'] == str(download_dir / DEFAULT_FILENAME_TEMPLATE)

    # Проверяем, что результат корректен
    assert result['status'] == 'успех'
    assert result['url'] == url
    assert result['path'] == expected_filepath


@patch('src.downloader.YoutubeDL')
def test_download_video_with_options(mock_youtube_dl, tmp_path):
    """Тест, что кастомные опции (качество, прокси, шаблон) правильно передаются."""
    quality = "best"
    proxy = "http://proxy.url"
    template = "%(id)s.%(ext)s"

    # Настраиваем мок, чтобы он не делал ничего, кроме проверки вызова
    mock_ydl_instance = MagicMock()
    mock_ydl_instance.extract_info.return_value = {}
    mock_ydl_instance.prepare_filename.return_value = "dummy_file.mp4"
    mock_youtube_dl.return_value.__enter__.return_value = mock_ydl_instance

    download_video(
        "url",
        tmp_path,
        quality_format=quality,
        proxy=proxy,
        filename_template=template
    )

    mock_youtube_dl.assert_called_once()
    args, kwargs = mock_youtube_dl.call_args
    options_dict = args[0]
    # Проверяем, что все опции были добавлены в словарь
    assert options_dict['format'] == quality
    assert options_dict['proxy'] == proxy
    assert options_dict['outtmpl'] == str(tmp_path / template)


@patch('src.downloader.YoutubeDL')
def test_download_video_failure(mock_youtube_dl, tmp_path):
    """Тест обработки ошибки при скачивании."""
    url = "https://example.com/broken_video"
    error_message = "Video unavailable"

    # Настраиваем мок на выброс исключения
    mock_youtube_dl.return_value.__enter__.side_effect = Exception(error_message)

    result = download_video(url, tmp_path)

    # Проверяем, что функция вернула словарь с ошибкой
    assert result['status'] == 'ошибка'
    assert result['url'] == url
    assert result['error'] == error_message