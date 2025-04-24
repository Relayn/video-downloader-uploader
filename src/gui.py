from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QTextEdit, QLabel, QLineEdit,
    QComboBox, QFileDialog, QProgressBar, QMessageBox, QGroupBox
)
from PySide6.QtCore import Qt, QThread, Signal, QObject, QEvent
import sys
from settings_dialog import SettingsDialog

# --- Асинхронные задачи ---
class WorkerSignals(QObject):
    finished = Signal(object)
    error = Signal(str)
    progress = Signal(int)

class DownloadUploadWorker(QThread):
    def __init__(self, urls, cloud, folder, filename, settings):
        super().__init__()
        self.urls = urls
        self.cloud = cloud
        self.folder = folder
        self.filename = filename
        self.settings = settings
        self.signals = WorkerSignals()

    def run(self):
        try:
            # Импортировать здесь, чтобы избежать блокировки GUI при импорте тяжёлых модулей
            from downloader import batch_download_videos
            from uploader import batch_upload_to_cloud
            # Пример: batch download
            url_list = [u.strip() for u in self.urls if u.strip()]
            download_tasks = [{"video_url": url} for url in url_list]
            download_results = batch_download_videos(download_tasks, temp_dir="temp")
            self.signals.progress.emit(50)
            # Пример: batch upload
            upload_tasks = []
            for result in download_results:
                if result["status"] == "успех":
                    upload_tasks.append({
                        "file_path": result["file_path"],
                        "cloud_storage": self.cloud,
                        "cloud_folder_path": self.folder,
                        "filename": self.filename or result["title"] + "." + result["ext"]
                    })
            upload_results = batch_upload_to_cloud(upload_tasks)
            self.signals.progress.emit(100)
            self.signals.finished.emit({
                "download": download_results,
                "upload": upload_results
            })
        except Exception as e:
            self.signals.error.emit(str(e))

class VideoUploaderGUI(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Video Downloader & Uploader")
        self.setMinimumWidth(600)
        self.init_ui()
        self.settings = {
            'ffmpeg_path': '',
            'log_to_file': False,
            'log_file_path': ''
        }
        self.worker = None

    def init_ui(self):
        layout = QVBoxLayout()

        # Ссылки на видео
        url_label = QLabel("Ссылки на видео:")
        self.url_edit = QTextEdit()
        self.url_edit.setPlaceholderText("Введите одну или несколько ссылок (по одной на строку)...\nИли перетащите текстовый файл/ссылки сюда.")
        self.url_edit.setAcceptDrops(True)
        self.url_edit.installEventFilter(self)
        paste_btn = QPushButton("Вставить из буфера обмена")
        paste_btn.setToolTip("Вставить ссылки из буфера обмена")
        paste_btn.clicked.connect(self.paste_from_clipboard)

        url_row = QHBoxLayout()
        url_row.addWidget(self.url_edit)
        url_row.addWidget(paste_btn)

        # Облачное хранилище
        cloud_label = QLabel("Облачное хранилище:")
        self.cloud_combo = QComboBox()
        self.cloud_combo.addItems(["Яндекс.Диск", "Google Drive"])
        self.cloud_combo.setToolTip("Выберите облако для загрузки видео")
        self.cloud_combo.currentIndexChanged.connect(self.update_cloud_fields)

        # Путь к папке в облаке
        folder_label = QLabel("Папка в облаке:")
        self.folder_edit = QLineEdit()
        self.folder_edit.setPlaceholderText("/Путь/к/папке (например, /Видео/YouTube)")
        self.folder_edit.setToolTip("Путь к папке в облаке. Оставьте пустым для загрузки в корень.")
        folder_btn = QPushButton("Создать папку")
        folder_btn.setToolTip("Создать новую папку в облаке")
        # TODO: folder_btn.clicked.connect(self.create_cloud_folder)

        folder_row = QHBoxLayout()
        folder_row.addWidget(self.folder_edit)
        folder_row.addWidget(folder_btn)

        # Имя файла
        filename_label = QLabel("Имя файла:")
        self.filename_edit = QLineEdit()
        self.filename_edit.setPlaceholderText("Оставьте пустым для автоимени (по видео)")
        self.filename_edit.setToolTip("Имя итогового файла. Можно оставить пустым.")

        # Авторизация
        auth_btn = QPushButton("Проверить подключение")
        auth_btn.setToolTip("Проверить авторизацию в облаке")
        self.auth_status = QLabel("Статус: не проверено")
        auth_btn.clicked.connect(self.check_auth)

        # Прогрессбар
        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        self.progress_bar.setVisible(False)

        # Кнопка запуска
        self.start_btn = QPushButton("Скачать и загрузить")
        self.start_btn.clicked.connect(self.start_download_upload)

        layout.addWidget(url_label)
        layout.addLayout(url_row)
        layout.addWidget(cloud_label)
        layout.addWidget(self.cloud_combo)
        layout.addWidget(folder_label)
        layout.addLayout(folder_row)
        layout.addWidget(filename_label)
        layout.addWidget(self.filename_edit)
        layout.addWidget(auth_btn)
        layout.addWidget(self.auth_status)
        layout.addWidget(self.progress_bar)
        layout.addWidget(self.start_btn)
        self.setLayout(layout)

    def start_download_upload(self):
        urls = self.url_edit.toPlainText().splitlines()
        cloud = self.cloud_combo.currentText()
        folder = self.folder_edit.text()
        filename = self.filename_edit.text()
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self.start_btn.setEnabled(False)
        self.worker = DownloadUploadWorker(urls, cloud, folder, filename, self.settings)
        self.worker.signals.progress.connect(self.progress_bar.setValue)
        self.worker.signals.error.connect(self.show_error)
        self.worker.signals.finished.connect(self.on_task_finished)
        self.worker.start()

    def show_error(self, msg):
        self.progress_bar.setVisible(False)
        self.start_btn.setEnabled(True)
        QMessageBox.critical(self, "Ошибка", msg)

    def on_task_finished(self, result):
        self.progress_bar.setVisible(False)
        self.start_btn.setEnabled(True)
        QMessageBox.information(self, "Готово", "Скачивание и загрузка завершены!\nСм. лог для деталей.")
        # Можно добавить отображение подробностей result

    def paste_from_clipboard(self):
        clipboard = QApplication.clipboard()
        self.url_edit.setText(clipboard.text())

    def update_cloud_fields(self):
        # Можно добавить динамическое изменение полей под облако
        pass

    def check_auth(self):
        cloud = self.cloud_combo.currentText()
        try:
            if cloud == "Яндекс.Диск":
                from auth import get_yandex_token
                token = get_yandex_token()
                if token:
                    self.auth_status.setText("Статус: авторизация Яндекс.Диск успешна")
                else:
                    self.auth_status.setText("Статус: нет токена Яндекс.Диск")
            elif cloud == "Google Drive":
                from auth import get_google_drive_credentials
                creds = get_google_drive_credentials()
                if creds and creds.valid:
                    self.auth_status.setText("Статус: авторизация Google Drive успешна")
                else:
                    self.auth_status.setText("Статус: ошибка авторизации Google Drive")
            else:
                self.auth_status.setText("Статус: неизвестное облако")
        except Exception as e:
            self.auth_status.setText(f"Статус: ошибка — {e}")
            QMessageBox.critical(self, "Ошибка авторизации", str(e))

    def eventFilter(self, obj, event):
        # Drag-and-drop файлов
        if obj == self.url_edit and event.type() == QEvent.DragEnter:
            if event.mimeData().hasUrls() or event.mimeData().hasText():
                event.acceptProposedAction()
                return True
        if obj == self.url_edit and event.type() == QEvent.Drop:
            if event.mimeData().hasUrls():
                for url in event.mimeData().urls():
                    if url.isLocalFile() and url.toLocalFile().endswith('.txt'):
                        with open(url.toLocalFile(), encoding='utf-8') as f:
                            self.url_edit.append(f.read())
            elif event.mimeData().hasText():
                self.url_edit.append(event.mimeData().text())
            return True
        return super().eventFilter(obj, event)

def main():
    app = QApplication(sys.argv)
    window = VideoUploaderGUI()
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
