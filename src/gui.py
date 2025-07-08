import sys
from pathlib import Path
import os
import asyncio
from asyncio import Queue, CancelledError
import json

from PySide6.QtCore import QObject, Signal, QRunnable, QThreadPool, Slot
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QTextEdit,
    QLabel,
    QLineEdit,
    QComboBox,
    QProgressBar,
    QMessageBox,
    QFileDialog,
)

from src.config import get_config, reload_config, save_specific_settings_to_env, ConfigError, BASE_DIR
from src.logger import setup_logger
from src.settings_dialog import SettingsDialog
from src.downloader import download_video, is_ffmpeg_installed
from src.uploader import UPLOADER_STRATEGIES, upload_single_file

# Константы для опций GUI
LOCAL_SAVE_OPTION = "Сохранить локально"
QUALITY_OPTIONS = {
    "Лучшее качество": "bestvideo+bestaudio/best",
    "1080p (Full HD)": "bestvideo[height<=1080]+bestaudio/best[height<=1080]",
    "720p (HD)": "bestvideo[height<=720]+bestaudio/best[height<=720]",
    "480p (SD)": "bestvideo[height<=480]+bestaudio/best[height<=480]",
    "Только аудио (лучшее)": "bestaudio/best",
}


class CancellationFlag:
    """Простой потокобезопасный флаг для запроса отмены операции."""
    def __init__(self): self._flag = False
    def set(self): self._flag = True
    def is_set(self): return self._flag
    def reset(self): self._flag = False


class WorkerSignals(QObject):
    """Сигналы для основного воркера DownloadUploadWorker."""
    finished = Signal(list, list, bool)
    error = Signal(str)
    progress = Signal(int, str)


class PreFlightCheckSignals(QObject):
    """Сигналы для воркера предполетных проверок."""
    finished = Signal(bool, str)


class PreFlightCheckWorker(QRunnable):
    """
    Выполняет предполетные проверки в фоновом потоке.

    Проверяет наличие FFMPEG и доступность выбранного хранилища.

    Args:
        cloud (str): Выбранное место назначения (например, 'Google Drive').
        path (str): Путь к папке назначения.
    """
    def __init__(self, cloud: str, path: str):
        super().__init__()
        self.signals = PreFlightCheckSignals()
        self.cloud = cloud
        self.path = path

    @Slot()
    def run(self):
        """Запускает асинхронные проверки."""
        try:
            asyncio.run(self.run_checks())
        except Exception as e:
            self.signals.finished.emit(False, f"Критическая ошибка при проверке: {e}")

    async def run_checks(self):
        """Выполняет последовательность проверок."""
        if not await asyncio.to_thread(is_ffmpeg_installed):
            msg = "FFMPEG не найден. Он необходим для скачивания видео в лучшем качестве. Установите его и добавьте в PATH."
            self.signals.finished.emit(False, msg)
            return

        strategy_class = UPLOADER_STRATEGIES.get(self.cloud)
        if not strategy_class:
            self.signals.finished.emit(False, f"Не найдена логика для '{self.cloud}'")
            return

        strategy = strategy_class()
        is_ok, error_msg = await strategy.check_connection(path=self.path)
        self.signals.finished.emit(is_ok, error_msg)


class DownloadUploadWorker(QRunnable):
    """
    Основной воркер, управляющий конвейером скачивания и загрузки.

    Args:
        urls (list[str]): Список URL для обработки.
        cloud (str): Выбранное место назначения.
        folder (str): Папка назначения.
        filename_template (str): Шаблон для имен файлов.
        quality_format (str): Строка формата качества для yt-dlp.
        cancellation_flag (CancellationFlag): Флаг для отмены операции.
        proxy (str | None): URL прокси-сервера.
    """
    def __init__(
            self,
            urls: list[str],
            cloud: str,
            folder: str,
            filename_template: str,
            quality_format: str,
            cancellation_flag: CancellationFlag,
            proxy: str | None,
    ):
        super().__init__()
        self.signals = WorkerSignals()
        self.urls = urls
        self.cloud = cloud
        self.folder = folder
        self.filename_template = filename_template
        self.quality_format = quality_format
        self.cancellation_flag = cancellation_flag
        self.proxy = proxy
        self.logger = setup_logger("Worker")

    @Slot()
    def run(self):
        """Запускает основной асинхронный pipeline и обрабатывает исключения."""
        try:
            asyncio.run(self.main_pipeline())
        except CancelledError:
            self.logger.warning("Основной pipeline был отменен.")
            self.signals.finished.emit([], [], True)
        except Exception as e:
            self.logger.error(f"Критическая ошибка в воркере: {e}", exc_info=True)
            self.signals.error.emit(str(e))

    async def main_pipeline(self):
        """Организует асинхронный конвейер: скачивание -> очередь -> загрузка."""
        from tempfile import TemporaryDirectory

        is_local_save = self.cloud == LOCAL_SAVE_OPTION
        temp_dir_manager = None if is_local_save else TemporaryDirectory(prefix="vdu_")
        target_dir = Path(self.folder) if is_local_save else Path(temp_dir_manager.name)

        try:
            self.signals.progress.emit(5, f"Рабочая папка: {target_dir}")
            queue = Queue()
            downloader = asyncio.create_task(self.downloader_task(target_dir, queue))
            uploader = None if is_local_save else asyncio.create_task(self.uploader_task(queue))

            tasks_to_monitor = [t for t in [downloader, uploader] if t]
            while not all(t.done() for t in tasks_to_monitor):
                if self.cancellation_flag.is_set():
                    self.logger.info("Получен флаг отмены. Отменяем задачи...")
                    for t in tasks_to_monitor: t.cancel()
                    await asyncio.gather(*tasks_to_monitor, return_exceptions=True)
                    raise CancelledError("Операция отменена")
                await asyncio.sleep(0.1)

            download_results = downloader.result()
            upload_results = uploader.result() if uploader else []
            self.signals.finished.emit(download_results, upload_results, False)
        finally:
            if temp_dir_manager:
                temp_dir_manager.cleanup()

    async def downloader_task(self, temp_dir: Path, queue: Queue):
        """Асинхронная задача, которая скачивает видео и кладет их в очередь."""
        results = []
        total = len(self.urls)
        for i, url in enumerate(self.urls):
            self.signals.progress.emit(int(5 + (i / (total * 2)) * 95), f"Скачивание {i + 1}/{total}: {url}")
            result = await asyncio.to_thread(
                download_video, url, temp_dir, self.quality_format, self.proxy, self.filename_template
            )
            results.append(result)
            if result["status"] == "успех":
                await queue.put(result)
            else:
                self.signals.error.emit(f"Ошибка скачивания {url}: {result['error']}")
        await queue.put(None)
        return results

    async def uploader_task(self, queue: Queue):
        """Асинхронная задача, которая берет файлы из очереди и загружает их."""
        results = []
        total = len(self.urls)
        uploaded_count = 0
        while True:
            download_result = await queue.get()
            if download_result is None:
                queue.task_done()
                break
            uploaded_count += 1
            self.signals.progress.emit(
                int(5 + ((total + uploaded_count) / (total * 2)) * 95),
                f"Загрузка {uploaded_count}/{total}: {download_result['path'].name}",
            )
            task = {
                "file_path": str(download_result["path"]),
                "cloud_storage": self.cloud,
                "cloud_folder_path": self.folder,
                "filename": download_result["path"].name,
            }
            upload_result = await upload_single_file(task)
            results.append(upload_result)
            if upload_result["status"] == "ошибка":
                self.signals.error.emit(f"Ошибка загрузки: {upload_result['error']}")
            queue.task_done()
        return results


SESSION_FILE_PATH = BASE_DIR / "session.json"


class VideoUploaderGUI(QMainWindow):
    """Основной класс GUI, представляющий главное окно приложения."""
    def __init__(self):
        super().__init__()
        self.cancellation_flag = CancellationFlag()
        try:
            self.config = get_config()
        except ConfigError as e:
            QMessageBox.critical(self, "Критическая ошибка конфигурации", str(e))
            sys.exit(1)

        self.logger = setup_logger("GUI", level=self.config.LOG_LEVEL, to_file=self.config.LOG_TO_FILE, file_path=self.config.LOG_FILE_PATH)
        self.threadpool = QThreadPool()
        self.setWindowTitle("Video Downloader & Uploader")
        self.setGeometry(100, 100, 700, 550)
        self.setup_ui()
        self.load_session_state()

    def setup_ui(self):
        """Инициализирует и размещает все виджеты в главном окне."""
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.addWidget(QLabel("Ссылки на видео (каждая с новой строки):"))
        self.url_edit = QTextEdit()
        self.url_edit.setPlaceholderText("https://www.youtube.com/watch?v=...")
        main_layout.addWidget(self.url_edit)
        options_layout = QHBoxLayout()
        cloud_v_layout = QVBoxLayout()
        cloud_v_layout.addWidget(QLabel("Место назначения:"))
        self.cloud_combo = QComboBox()
        self.cloud_combo.addItems(UPLOADER_STRATEGIES.keys())
        self.cloud_combo.currentIndexChanged.connect(self._on_cloud_selection_changed)
        cloud_v_layout.addWidget(self.cloud_combo)
        options_layout.addLayout(cloud_v_layout)
        quality_v_layout = QVBoxLayout()
        quality_v_layout.addWidget(QLabel("Качество:"))
        self.quality_combo = QComboBox()
        self.quality_combo.addItems(QUALITY_OPTIONS.keys())
        quality_v_layout.addWidget(self.quality_combo)
        options_layout.addLayout(quality_v_layout)
        main_layout.addLayout(options_layout)
        self.path_label = QLabel("Папка в облаке (например, 'мое_видео/2024'):")
        main_layout.addWidget(self.path_label)
        self.folder_selector = self._create_folder_selector()
        main_layout.addWidget(self.folder_selector)
        main_layout.addWidget(QLabel("Шаблон имени файла (плейсхолдеры yt-dlp):"))
        self.filename_edit = QLineEdit()
        self.filename_edit.setPlaceholderText("%(title)s - %(uploader)s [%(upload_date)s].%(ext)s")
        main_layout.addWidget(self.filename_edit)
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        main_layout.addWidget(self.progress_bar)
        self.status_label = QLabel("Готов к работе.")
        self.status_label.setStyleSheet("color: grey;")
        main_layout.addWidget(self.status_label)
        button_layout = QHBoxLayout()
        self.start_btn = QPushButton("▶️ Начать")
        self.start_btn.clicked.connect(self.start_processing)
        self.cancel_btn = QPushButton("❌ Отмена")
        self.cancel_btn.clicked.connect(self.cancel_processing)
        self.cancel_btn.setEnabled(False)
        self.settings_btn = QPushButton("⚙️ Настройки")
        self.settings_btn.clicked.connect(self.open_settings)
        button_layout.addWidget(self.start_btn)
        button_layout.addWidget(self.cancel_btn)
        button_layout.addWidget(self.settings_btn)
        main_layout.addLayout(button_layout)
        self._on_cloud_selection_changed()

    def start_processing(self):
        """Запускает процесс обработки: валидация -> проверки -> запуск воркера."""
        urls = [url.strip() for url in self.url_edit.toPlainText().splitlines() if url.strip()]
        if not urls:
            self.show_message("Ошибка", "Пожалуйста, введите хотя бы один URL.", "warning")
            return

        self.start_btn.setEnabled(False)
        self.settings_btn.setEnabled(False)
        self.status_label.setText("Выполнение предполетных проверок...")
        self.status_label.setStyleSheet("color: blue;")

        check_worker = PreFlightCheckWorker(cloud=self.cloud_combo.currentText(), path=self.folder_edit.text())
        check_worker.signals.finished.connect(self.on_pre_flight_finished)
        self.threadpool.start(check_worker)

    @Slot(bool, str)
    def on_pre_flight_finished(self, is_ok: bool, message: str):
        """Слот, обрабатывающий результат предполетных проверок."""
        if not is_ok:
            self.show_message("Ошибка проверки", message, "critical")
            self._reset_ui_to_idle()
            return

        self.status_label.setText("Проверки пройдены. Запуск основной задачи...")
        self.cancel_btn.setEnabled(True)
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self.cancellation_flag.reset()

        worker = DownloadUploadWorker(
            urls=[url.strip() for url in self.url_edit.toPlainText().splitlines() if url.strip()],
            cloud=self.cloud_combo.currentText(),
            folder=self.folder_edit.text(),
            filename_template=self.filename_edit.text(),
            quality_format=QUALITY_OPTIONS[self.quality_combo.currentText()],
            cancellation_flag=self.cancellation_flag,
            proxy=self.config.PROXY_URL,
        )
        worker.signals.progress.connect(self.update_progress)
        worker.signals.finished.connect(self.on_finished)
        worker.signals.error.connect(self.on_error)
        self.threadpool.start(worker)

    def _create_folder_selector(self) -> QWidget:
        """Создает составной виджет для выбора локальной папки."""
        container = QWidget()
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        self.folder_edit = QLineEdit()
        layout.addWidget(self.folder_edit)
        self.browse_btn = QPushButton("Выбрать...")
        self.browse_btn.clicked.connect(self._select_local_folder)
        layout.addWidget(self.browse_btn)
        return container

    def _on_cloud_selection_changed(self):
        """Обновляет UI в зависимости от выбора места назначения."""
        is_local = self.cloud_combo.currentText() == LOCAL_SAVE_OPTION
        if is_local:
            self.path_label.setText("Папка для сохранения:")
            self.folder_edit.setPlaceholderText("Выберите локальную папку...")
        else:
            self.path_label.setText("Папка в облаке (например, 'мое_видео/2024'):")
            self.folder_edit.setPlaceholderText("Оставьте пустым для корня диска")
        self.browse_btn.setVisible(is_local)

    def _select_local_folder(self):
        """Открывает диалог выбора папки и обновляет поле ввода."""
        path = QFileDialog.getExistingDirectory(self, "Выберите папку для сохранения")
        if path:
            self.folder_edit.setText(path)

    def _reset_ui_to_idle(self):
        """Сбрасывает состояние UI к исходному (ожидание)."""
        self.start_btn.setEnabled(True)
        self.settings_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)
        self.progress_bar.setVisible(False)
        self.status_label.setText("Готов к работе.")
        self.status_label.setStyleSheet("color: grey;")

    def cancel_processing(self):
        """Инициирует отмену текущей операции."""
        self.logger.info("Нажата кнопка отмены.")
        self.status_label.setText("Отмена операции...")
        self.status_label.setStyleSheet("color: orange;")
        self.cancellation_flag.set()
        self.cancel_btn.setEnabled(False)

    @Slot(int, str)
    def update_progress(self, percent: int, message: str):
        """Обновляет прогресс-бар и текстовый статус."""
        self.progress_bar.setValue(percent)
        self.status_label.setText(message)
        self.status_label.setStyleSheet("color: black;")

    @Slot(list, list, bool)
    def on_finished(self, download_results: list, upload_results: list, is_cancelled: bool):
        """Обрабатывает завершение основной задачи."""
        self._reset_ui_to_idle()
        if is_cancelled:
            self.status_label.setText("Операция отменена.")
            self.status_label.setStyleSheet("color: orange;")
            self.logger.warning("Процесс был успешно отменен.")
            QMessageBox.warning(self, "Отменено", "Операция была отменена пользователем.")
            return

        self.status_label.setText("Готово!")
        self.status_label.setStyleSheet("color: green;")
        self.logger.info("Задача успешно завершена.")

        success_downloads = sum(1 for d in download_results if d['status'] == 'успех')
        success_uploads = sum(1 for u in upload_results if u['status'] == 'успех')
        report = f"Задача выполнена.\n\nСкачано файлов: {success_downloads} из {len(download_results)}."
        if self.cloud_combo.currentText() != LOCAL_SAVE_OPTION:
            report += f"\nЗагружено в облако: {success_uploads} из {len(upload_results)}."
        QMessageBox.information(self, "Завершено", report)

    @Slot(str)
    def on_error(self, error_message: str):
        """Отображает сообщение об ошибке в строке статуса."""
        self.status_label.setText(f"Ошибка: {error_message}")
        self.status_label.setStyleSheet("color: red;")
        self.logger.error(f"Ошибка в воркере: {error_message}")

    def open_settings(self):
        """Открывает диалог настроек и обрабатывает результат."""
        dialog = SettingsDialog(self)
        if dialog.exec():
            try:
                save_specific_settings_to_env(dialog.get_settings_data())
                self.config = reload_config()
                self.logger = setup_logger("GUI", level=self.config.LOG_LEVEL, to_file=self.config.LOG_TO_FILE, file_path=self.config.LOG_FILE_PATH)
                self.show_message("Успех", "Настройки сохранены и применены.")
            except Exception as e:
                self.show_message("Ошибка", f"Не удалось сохранить настройки:\n{e}", "critical")

    def show_message(self, title: str, text: str, level: str = "info"):
        """Отображает стандартизированное информационное сообщение."""
        msg_box = QMessageBox(self)
        msg_box.setWindowTitle(title)
        msg_box.setText(text)
        if level == "warning": msg_box.setIcon(QMessageBox.Warning)
        elif level == "critical": msg_box.setIcon(QMessageBox.Critical)
        else: msg_box.setIcon(QMessageBox.Information)
        msg_box.exec()

    def load_session_state(self):
        """Загружает состояние виджетов из файла сессии."""
        try:
            if not SESSION_FILE_PATH.exists(): return
            with open(SESSION_FILE_PATH, "r", encoding="utf-8") as f: state = json.load(f)
            self.url_edit.setText(state.get("urls", ""))
            self.cloud_combo.setCurrentIndex(state.get("cloud_index", 0))
            self.quality_combo.setCurrentIndex(state.get("quality_index", 0))
            self.folder_edit.setText(state.get("path_text", ""))
            self.filename_edit.setText(state.get("template_text", ""))
            self.logger.info("Состояние сессии успешно загружено.")
        except (json.JSONDecodeError, IOError) as e:
            self.logger.warning(f"Не удалось загрузить состояние сессии: {e}")

    def save_session_state(self):
        """Сохраняет текущее состояние виджетов в файл сессии."""
        state = {
            "urls": self.url_edit.toPlainText(),
            "cloud_index": self.cloud_combo.currentIndex(),
            "quality_index": self.quality_combo.currentIndex(),
            "path_text": self.folder_edit.text(),
            "template_text": self.filename_edit.text(),
        }
        try:
            with open(SESSION_FILE_PATH, "w", encoding="utf-8") as f: json.dump(state, f, indent=4)
            self.logger.info("Состояние сессии успешно сохранено.")
        except IOError as e:
            self.logger.error(f"Не удалось сохранить состояние сессии: {e}")

    def closeEvent(self, event: QCloseEvent):
        """Перехватывает событие закрытия окна для сохранения сессии."""
        self.logger.info("Приложение закрывается, сохраняем сессию...")
        self.save_session_state()
        super().closeEvent(event)


def main():
    """Основная функция для запуска GUI."""
    app = QApplication(sys.argv)
    window = VideoUploaderGUI()
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()