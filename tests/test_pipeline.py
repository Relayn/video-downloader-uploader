import asyncio
from asyncio import CancelledError
from pathlib import Path
from unittest.mock import patch, MagicMock, AsyncMock

import pytest
from src.gui import DownloadUploadWorker, CancellationFlag, WorkerSignals


@pytest.fixture
def cancellation_flag():
    """Фикстура для флага отмены."""
    return CancellationFlag()


@pytest.fixture
def worker_signals():
    """Фикстура для сигналов воркера."""
    # В реальном GUI это объекты PySide, здесь нам достаточно моков
    signals = MagicMock(spec=WorkerSignals)
    signals.finished = MagicMock()
    signals.error = MagicMock()
    signals.progress = MagicMock()
    return signals


@pytest.fixture
def base_worker_params(cancellation_flag):
    """Базовые параметры для инициализации воркера."""
    return {
        "urls": ["http://test.url/1"],
        "cloud": "Google Drive",
        "folder": "test_folder",
        "filename_template": "",
        "quality_format": "best",
        "cancellation_flag": cancellation_flag,
        "proxy": None,
    }


# ============================================
# Тесты для логики runner'а (метода run)
# ============================================

@patch("src.gui.DownloadUploadWorker.main_pipeline", new_callable=AsyncMock)
def test_run_method_calls_main_pipeline(mock_main_pipeline, base_worker_params, worker_signals):
    """Тест: метод run() успешно вызывает main_pipeline."""
    worker = DownloadUploadWorker(**base_worker_params)
    worker.signals = worker_signals

    worker.run()
    mock_main_pipeline.assert_awaited_once()
    worker.signals.error.emit.assert_not_called()
    worker.signals.finished.emit.assert_not_called()


@patch("src.gui.DownloadUploadWorker.main_pipeline", new_callable=AsyncMock)
def test_run_method_handles_cancellation(mock_main_pipeline, base_worker_params, worker_signals):
    """Тест: метод run() ловит CancelledError и испускает 'finished' сигнал."""
    # Настраиваем мок, чтобы он выбрасывал ошибку отмены
    mock_main_pipeline.side_effect = CancelledError

    worker = DownloadUploadWorker(**base_worker_params)
    worker.signals = worker_signals

    worker.run()

    # Проверяем, что был вызван сигнал finished с флагом отмены
    worker.signals.finished.emit.assert_called_once_with([], [], True)
    worker.signals.error.emit.assert_not_called()


@patch("src.gui.DownloadUploadWorker.main_pipeline", new_callable=AsyncMock)
def test_run_method_handles_general_exception(mock_main_pipeline, base_worker_params, worker_signals):
    """Тест: метод run() ловит общие исключения и испускает 'error' сигнал."""
    # Настраиваем мок, чтобы он выбрасывал обычную ошибку
    mock_main_pipeline.side_effect = ValueError("Test Error")

    worker = DownloadUploadWorker(**base_worker_params)
    worker.signals = worker_signals

    worker.run()

    # Проверяем, что был вызван сигнал error с текстом ошибки
    worker.signals.error.emit.assert_called_once_with("Test Error")
    worker.signals.finished.emit.assert_not_called()


# ============================================
# Тесты для логики самого pipeline (main_pipeline)
# ============================================

@pytest.mark.asyncio
@patch("src.gui.upload_single_file", new_callable=AsyncMock)
@patch("src.gui.download_video")
@patch("tempfile.TemporaryDirectory")
async def test_pipeline_success(mock_temp_dir, mock_download, mock_upload, base_worker_params, worker_signals, tmp_path):
    """Тест успешного выполнения всего конвейера: скачивание + загрузка."""
    mock_temp_dir.return_value.__enter__.return_value = str(tmp_path)
    mock_download.return_value = {"status": "успех", "url": "http://test.url/1", "path": tmp_path / "video.mp4"}
    mock_upload.return_value = {"status": "успех", "url": "http://cloud.url/video.mp4"}

    worker = DownloadUploadWorker(**base_worker_params)
    worker.signals = worker_signals

    await worker.main_pipeline()

    mock_download.assert_called_once()
    mock_upload.assert_called_once()

    # Проверяем, что сигнал finished был вызван с корректными результатами
    worker.signals.finished.emit.assert_called_once()
    args, _ = worker.signals.finished.emit.call_args
    download_results, upload_results, is_cancelled = args
    assert len(download_results) == 1
    assert download_results[0]["status"] == "успех"
    assert len(upload_results) == 1
    assert upload_results[0]["status"] == "успех"
    assert not is_cancelled


@pytest.mark.asyncio
@patch("src.gui.upload_single_file", new_callable=AsyncMock)
@patch("src.gui.download_video")
@patch("tempfile.TemporaryDirectory")
async def test_pipeline_download_failure(mock_temp_dir, mock_download, mock_upload, base_worker_params, worker_signals, tmp_path):
    """Тест: конвейер останавливается, если скачивание не удалось."""
    mock_temp_dir.return_value.__enter__.return_value = str(tmp_path)
    mock_download.return_value = {"status": "ошибка", "url": "http://test.url/1", "error": "Download failed"}

    worker = DownloadUploadWorker(**base_worker_params)
    worker.signals = worker_signals

    await worker.main_pipeline()

    mock_download.assert_called_once()
    mock_upload.assert_not_called()
    worker.signals.error.emit.assert_called_with("Ошибка скачивания http://test.url/1: Download failed")


@pytest.mark.asyncio
@patch("src.gui.upload_single_file", new_callable=AsyncMock)
@patch("src.gui.download_video")
@patch("tempfile.TemporaryDirectory")
async def test_pipeline_upload_failure(mock_temp_dir, mock_download, mock_upload, base_worker_params, worker_signals, tmp_path):
    """Тест: ошибка на этапе загрузки корректно обрабатывается."""
    mock_temp_dir.return_value.__enter__.return_value = str(tmp_path)
    mock_download.return_value = {"status": "успех", "url": "http://test.url/1", "path": tmp_path / "video.mp4"}
    mock_upload.return_value = {"status": "ошибка", "error": "Upload failed"}

    worker = DownloadUploadWorker(**base_worker_params)
    worker.signals = worker_signals

    await worker.main_pipeline()

    mock_download.assert_called_once()
    mock_upload.assert_called_once()
    worker.signals.error.emit.assert_called_with("Ошибка загрузки: Upload failed")


@pytest.mark.asyncio
async def test_pipeline_cancellation_propagates(base_worker_params):
    """Тест: установка флага отмены приводит к выбросу CancelledError."""
    worker = DownloadUploadWorker(**base_worker_params)
    worker.cancellation_flag.set()

    with pytest.raises(CancelledError, match="Операция отменена"):
        await worker.main_pipeline()