import os
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QVBoxLayout,
    QLineEdit,
    QPushButton,
    QFileDialog,
    QCheckBox,
    QLabel,
    QGroupBox,
    QWidget,
)
from PySide6.QtCore import Qt
from src.config import get_config, AppSettings


class SettingsDialog(QDialog):
    """Диалоговое окно для редактирования настроек приложения."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Настройки")
        self.setMinimumWidth(500)
        self.config = get_config()

        # Layout
        self.layout = QVBoxLayout(self)

        # General Settings
        general_group = QGroupBox("Основные")
        general_layout = QVBoxLayout()

        # YTDLP Format
        general_layout.addWidget(QLabel("Формат загрузки (yt-dlp format string):"))
        self.ytdlp_format_edit = QLineEdit()
        general_layout.addWidget(self.ytdlp_format_edit)

        # FFMPEG Path
        general_layout.addWidget(QLabel("Путь к ffmpeg.exe (необязательно):"))
        self.ffmpeg_path_edit = self.create_file_selector()
        general_layout.addWidget(self.ffmpeg_path_edit)

        general_group.setLayout(general_layout)
        self.layout.addWidget(general_group)

        # Credentials
        creds_group = QGroupBox("Учетные данные")
        creds_layout = QVBoxLayout()

        # Google Credentials
        creds_layout.addWidget(QLabel("Путь к файлу Google 'credentials.json':"))
        self.google_credentials_edit = self.create_file_selector(is_json=True)
        creds_layout.addWidget(self.google_credentials_edit)

        # Yandex Token
        creds_layout.addWidget(QLabel("Токен Яндекс.Диска:"))
        self.yandex_token_edit = QLineEdit()
        self.yandex_token_edit.setEchoMode(QLineEdit.Password)
        creds_layout.addWidget(self.yandex_token_edit)

        creds_group.setLayout(creds_layout)
        self.layout.addWidget(creds_group)

        # Logging
        log_group = QGroupBox("Логирование")
        log_layout = QVBoxLayout()
        self.log_to_file_checkbox = QCheckBox("Включить логирование в файл")
        log_layout.addWidget(self.log_to_file_checkbox)
        log_layout.addWidget(QLabel("Путь к лог-файлу:"))
        self.log_file_path_edit = self.create_file_selector(is_save=True)
        log_layout.addWidget(self.log_file_path_edit)
        log_group.setLayout(log_layout)
        self.layout.addWidget(log_group)

        # Buttons
        self.buttonBox = QDialogButtonBox(
            QDialogButtonBox.Save | QDialogButtonBox.Cancel
        )
        self.buttonBox.accepted.connect(self.accept)
        self.buttonBox.rejected.connect(self.reject)
        self.layout.addWidget(self.buttonBox)

        self.load_settings()

    def create_file_selector(self, is_json=False, is_save=False):
        """Вспомогательная функция для создания строки с выбором файла."""
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)

        line_edit = QLineEdit()
        button = QPushButton("Выбрать...")
        layout.addWidget(line_edit)
        layout.addWidget(button)

        if is_save:
            button.clicked.connect(lambda: self.select_file_path(line_edit, save=True))
        else:
            filter = "JSON files (*.json)" if is_json else "All files (*)"
            button.clicked.connect(
                lambda: self.select_file_path(line_edit, filter=filter)
            )

        # Attach the line edit to the container for easy access
        container.line_edit = line_edit
        return container

    def select_file_path(self, line_edit, filter="All files (*)", save=False):
        """Открывает диалог выбора файла/сохранения."""
        if save:
            path, _ = QFileDialog.getSaveFileName(self, "Выбрать файл", filter=filter)
        else:
            path, _ = QFileDialog.getOpenFileName(self, "Выбрать файл", filter=filter)

        if path:
            line_edit.setText(path)

    def load_settings(self):
        """Загружает текущие настройки в поля диалога."""
        self.ytdlp_format_edit.setText(self.config.YTDLP_FORMAT)
        self.ffmpeg_path_edit.line_edit.setText(str(self.config.FFMPEG_PATH or ""))
        self.google_credentials_edit.line_edit.setText(
            str(self.config.GOOGLE_CREDENTIALS or "")
        )
        self.yandex_token_edit.setText(
            self.config.YANDEX_TOKEN.get_secret_value()
            if self.config.YANDEX_TOKEN
            else ""
        )
        self.log_to_file_checkbox.setChecked(self.config.LOG_TO_FILE)
        self.log_file_path_edit.line_edit.setText(self.config.LOG_FILE_PATH)

    def get_settings_data(self) -> dict:
        """Собирает данные из полей диалога в словарь для сохранения в .env."""
        return {
            "YTDLP_FORMAT": self.ytdlp_format_edit.text(),
            "FFMPEG_PATH": self.ffmpeg_path_edit.line_edit.text() or "",
            "GOOGLE_CREDENTIALS": self.google_credentials_edit.line_edit.text() or "",
            "YANDEX_TOKEN": self.yandex_token_edit.text() or "",
            "LOG_TO_FILE": self.log_to_file_checkbox.isChecked(),
            "LOG_FILE_PATH": self.log_file_path_edit.line_edit.text(),
        }
