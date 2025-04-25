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
        self.gdrive_folder_id = "root"  # По умолчанию

    def run(self):
        try:
            # Импортировать здесь, чтобы избежать блокировки GUI при импорте тяжёлых модулей
            from downloader import batch_download_videos
            from uploader import batch_upload_to_cloud
            url_list = [u.strip() for u in self.urls if u.strip()]
            download_tasks = [{"video_url": url} for url in url_list]
            download_results = batch_download_videos(download_tasks, temp_dir="temp")
            self.signals.progress.emit(50)
            # Пример: batch upload
            upload_tasks = []
            for result in download_results:
                if result.get("file_path"):
                    upload_task = {
                        "file_path": result["file_path"],
                        "cloud_storage": self.cloud,
                        "cloud_folder_path": self.folder,
                        "filename": self.filename or result["title"] + "." + result["ext"]
                    }
                    if self.cloud == "Google Drive":
                        upload_task["google_drive_folder_id"] = self.gdrive_folder_id
                    upload_tasks.append(upload_task)
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
        paste_btn.clicked.connect(self.paste_from_clipboard)
        url_row = QHBoxLayout()
        url_row.addWidget(self.url_edit)
        url_row.addWidget(paste_btn)

        # Облачное хранилище
        cloud_label = QLabel("Облачное хранилище:")
        self.cloud_combo = QComboBox()
        self.cloud_combo.addItems(["Google Drive", "Yandex.Disk"])
        self.cloud_combo.currentTextChanged.connect(self.update_cloud_fields)

        # Папка в облаке
        folder_label = QLabel("Папка в облаке:")
        self.folder_edit = QLineEdit()
        folder_row = QHBoxLayout()
        folder_row.addWidget(self.folder_edit)
        folder_btn = QPushButton("Создать папку")
        folder_row.addWidget(folder_btn)

        # Новое поле: ID папки Google Drive
        gdrive_id_label = QLabel("ID папки Google Drive:")
        self.gdrive_id_edit = QLineEdit()
        self.gdrive_id_edit.setPlaceholderText("Оставьте пустым для 'root'")

        # Имя файла
        filename_label = QLabel("Имя файла:")
        self.filename_edit = QLineEdit()
        self.filename_edit.setPlaceholderText("Оставьте пустым для автоматич. (по видео)")

        # Авторизация
        auth_btn = QPushButton("Проверить подключение")
        auth_btn.clicked.connect(self.check_auth)
        self.auth_status = QLabel("Статус: не проверено")

        # Прогрессбар
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.progress_bar.setValue(0)
        self.progress_bar.setFormat("Прогресс: 0%")

        self.start_btn = QPushButton("Скачать и загрузить")
        self.start_btn.clicked.connect(self.start_download_upload)

        layout.addWidget(url_label)
        layout.addLayout(url_row)
        layout.addWidget(cloud_label)
        layout.addWidget(self.cloud_combo)
        layout.addWidget(folder_label)
        layout.addLayout(folder_row)
        layout.addWidget(gdrive_id_label)
        layout.addWidget(self.gdrive_id_edit)
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
        gdrive_id = self.gdrive_id_edit.text().strip() or "root"
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self.start_btn.setEnabled(False)
        self.worker = DownloadUploadWorker(urls, cloud, folder, filename, self.settings)
        self.worker.gdrive_folder_id = gdrive_id  # Добавим атрибут для передачи ID
        self.worker.signals.progress.connect(self.progress_bar.setValue)
        self.worker.signals.error.connect(self.show_error)
        self.worker.signals.finished.connect(self.on_task_finished)
        self.worker.signals.progress.connect(self.update_progress_label)  # Новый сигнал для текста
        self.worker.start()

    def show_error(self, msg):
        self.progress_bar.setVisible(False)
        self.start_btn.setEnabled(True)
        QMessageBox.critical(self, "Ошибка", msg)

    def on_task_finished(self, result):
        self.progress_bar.setVisible(False)
        self.start_btn.setEnabled(True)
        # Показываем детали результата
        msg = "Скачивание и загрузка завершены!\n"
        if "download" in result:
            msg += f"\nСкачано: {len(result['download'])} файлов"
        if "upload" in result:
            success = [r for r in result['upload'] if r.get('status') == 'успех']
            errors = [r for r in result['upload'] if r.get('status') != 'успех']
            msg += f"\nЗагружено: {len(success)} файлов"
            if errors:
                msg += f"\nОшибки загрузки: {len(errors)}"
                for err in errors:
                    msg += f"\n{err.get('filename', '')}: {err.get('message', '')}"
        QMessageBox.information(self, "Готово", msg)

    def update_progress_label(self, value):
        self.progress_bar.setFormat(f"Прогресс: {value}%")

    def paste_from_clipboard(self):
        clipboard = QApplication.clipboard()
        self.url_edit.setText(clipboard.text())

    def update_cloud_fields(self):
        # Можно добавить динамическое изменение полей под облако
        pass

    def check_auth(self):
        cloud = self.cloud_combo.currentText()
        try:
            if cloud == "Yandex.Disk":
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
