import sys
from pathlib import Path

from PySide6.QtCore import QObject, Signal, QRunnable, QThreadPool, Slot, QThread
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
)

from src.config import (
    get_config,
    reload_config,
    save_specific_settings_to_env,
    setup_logger,
    ConfigError,
)
from src.settings_dialog import SettingsDialog
from src.downloader import batch_download_videos
from src.uploader import batch_upload_to_cloud
import asyncio


class WorkerSignals(QObject):
    """Сигналы для фонового обработчика."""

    finished = Signal(object)
    error = Signal(str)
    progress = Signal(int, str)  # процент, сообщение


class DownloadUploadWorker(QRunnable):
    """Фоновый обработчик для скачивания и загрузки."""

    def __init__(
        self, urls: list[str], cloud: str, folder: str, filename_template: str
    ):
        super().__init__()
        self.signals = WorkerSignals()
        self.urls = urls
        self.cloud = cloud
        self.folder = folder
        self.filename_template = filename_template

    @Slot()
    def run(self):
        try:
            from tempfile import TemporaryDirectory

            with TemporaryDirectory(prefix="vdu_") as temp_dir_str:
                temp_dir = Path(temp_dir_str)
                self.signals.progress.emit(
                    10, f"Создана временная папка: {temp_dir_str}"
                )

                # --- Этап 1: Скачивание ---
                self.signals.progress.emit(20, "Начало скачивания видео...")
                download_results = batch_download_videos(self.urls, temp_dir)

                successful_downloads = [
                    res for res in download_results if res["status"] == "успех"
                ]
                if not successful_downloads:
                    raise IOError("Ни один файл не был успешно скачан.")

                self.signals.progress.emit(
                    50, f"Скачано {len(successful_downloads)} видео. Начало загрузки..."
                )

                # --- Этап 2: Загрузка ---
                upload_tasks = []
                for res in successful_downloads:
                    file_path = res["path"]
                    # Если шаблон имени не задан, используем имя скачанного файла
                    filename = self.filename_template or file_path.name
                    task = {
                        "file_path": str(file_path),
                        "cloud_storage": self.cloud,
                        "cloud_folder_path": self.folder,
                        "filename": filename,
                    }
                    upload_tasks.append(task)

                self.signals.progress.emit(
                    75, f"Загрузка {len(upload_tasks)} файлов в облако..."
                )
                # Пакетная загрузка
                try:
                    upload_results = asyncio.run(batch_upload_to_cloud(upload_tasks))
                    for res in upload_results:
                        if res["status"] == "ошибка":
                            self.signals.error.emit(f"Ошибка при загрузке: {res}")
                        else:
                            storage = res.get("storage", "Неизвестно")
                            path = res.get("path") or res.get("id")
                            self.signals.progress.emit(
                                100, f"Успешно загружено в {storage}: {path}"
                            )

                except Exception as e:
                    self.signals.error.emit(
                        f"Критическая ошибка при пакетной загрузке: {e}"
                    )

                self.signals.finished.emit(
                    {"downloads": download_results, "uploads": upload_results}
                )

        except Exception as e:
            self.signals.error.emit(str(e))


class VideoUploaderGUI(QMainWindow):
    """Основной класс GUI."""

    def __init__(self):
        super().__init__()
        try:
            self.config = get_config()
        except ConfigError as e:
            QMessageBox.critical(self, "Критическая ошибка конфигурации", str(e))
            sys.exit(1)

        self.logger = setup_logger(
            "GUI",
            level=self.config.LOG_LEVEL,
            to_file=self.config.LOG_TO_FILE,
            file_path=self.config.LOG_FILE_PATH,
        )
        self.threadpool = QThreadPool()
        self.logger.info(
            f"GUI запущен. Макс. потоков: {self.threadpool.maxThreadCount()}"
        )

        self.setWindowTitle("Video Downloader & Uploader")
        self.setGeometry(100, 100, 700, 500)
        self.setup_ui()

    def setup_ui(self):
        # ... (UI setup code will be similar, just cleaner)
        # Main layout
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)

        # URLs
        main_layout.addWidget(QLabel("Ссылки на видео (каждая с новой строки):"))
        self.url_edit = QTextEdit()
        self.url_edit.setPlaceholderText("https://www.youtube.com/watch?v=...")
        main_layout.addWidget(self.url_edit)

        # Cloud options
        cloud_layout = QHBoxLayout()
        cloud_layout.addWidget(QLabel("Облако:"))
        self.cloud_combo = QComboBox()
        self.cloud_combo.addItems(["Google Drive", "Yandex.Disk"])
        cloud_layout.addWidget(self.cloud_combo)
        main_layout.addLayout(cloud_layout)

        # Cloud folder
        main_layout.addWidget(QLabel("Папка в облаке (например, 'мое_видео/2024'):"))
        self.folder_edit = QLineEdit()
        main_layout.addWidget(self.folder_edit)

        # Filename template
        main_layout.addWidget(QLabel("Шаблон имени файла (оставьте пустым для авто):"))
        self.filename_edit = QLineEdit()
        main_layout.addWidget(self.filename_edit)

        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        main_layout.addWidget(self.progress_bar)

        # Status label
        self.status_label = QLabel("Готов к работе.")
        self.status_label.setStyleSheet("color: grey;")
        main_layout.addWidget(self.status_label)

        # Buttons
        button_layout = QHBoxLayout()
        self.start_btn = QPushButton("▶️ Начать")
        self.start_btn.clicked.connect(self.start_processing)
        self.settings_btn = QPushButton("⚙️ Настройки")
        self.settings_btn.clicked.connect(self.open_settings)
        button_layout.addWidget(self.start_btn)
        button_layout.addWidget(self.settings_btn)
        main_layout.addLayout(button_layout)

    def start_processing(self):
        urls = [
            url.strip()
            for url in self.url_edit.toPlainText().splitlines()
            if url.strip()
        ]
        if not urls:
            self.show_message(
                "Ошибка", "Пожалуйста, введите хотя бы один URL.", "warning"
            )
            return

        self.start_btn.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)

        worker = DownloadUploadWorker(
            urls=urls,
            cloud=self.cloud_combo.currentText(),
            folder=self.folder_edit.text(),
            filename_template=self.filename_edit.text(),
        )
        worker.signals.progress.connect(self.update_progress)
        worker.signals.finished.connect(self.on_finished)
        worker.signals.error.connect(self.on_error)
        self.threadpool.start(worker)

    def update_progress(self, percent, message):
        self.progress_bar.setValue(percent)
        self.status_label.setText(message)
        self.logger.info(f"Прогресс ({percent}%): {message}")

    def on_finished(self, results):
        self.start_btn.setEnabled(True)
        self.progress_bar.setVisible(False)
        self.status_label.setText("Готово!")
        self.logger.info("Задача успешно завершена.")
        # Тут можно показать детальный отчет по results
        QMessageBox.information(
            self, "Завершено", f"Задача выполнена.\nСм. детали в логах."
        )

    def on_error(self, error_message):
        self.start_btn.setEnabled(True)
        self.progress_bar.setVisible(False)
        self.status_label.setText("Ошибка!")
        self.show_message("Ошибка выполнения", error_message, "critical")
        self.logger.error(f"Ошибка в воркере: {error_message}")

    def open_settings(self):
        dialog = SettingsDialog(self)
        if dialog.exec():  # exec() returns true if accepted
            try:
                save_specific_settings_to_env(dialog.get_settings_data())
                self.config = reload_config()
                # Re-setup logger with new settings
                self.logger = setup_logger(
                    "GUI",
                    level=self.config.LOG_LEVEL,
                    to_file=self.config.LOG_TO_FILE,
                    file_path=self.config.LOG_FILE_PATH,
                )
                self.show_message("Успех", "Настройки сохранены и применены.")
            except Exception as e:
                self.show_message(
                    "Ошибка", f"Не удалось сохранить настройки:\n{e}", "critical"
                )

    def show_message(self, title, text, level="info"):
        msg_box = QMessageBox(self)
        msg_box.setWindowTitle(title)
        msg_box.setText(text)
        if level == "warning":
            msg_box.setIcon(QMessageBox.Warning)
        elif level == "critical":
            msg_box.setIcon(QMessageBox.Critical)
        else:
            msg_box.setIcon(QMessageBox.Information)
        msg_box.exec()


def main():
    app = QApplication(sys.argv)
    window = VideoUploaderGUI()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
