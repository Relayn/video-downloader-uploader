from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QFormLayout,
    QLineEdit,
    QPushButton,
    QDialogButtonBox,
    QLabel,
    QComboBox,
    QCheckBox,
    QFileDialog,
    QWidget,
    QHBoxLayout,
)
from src.config import get_config


class SettingsDialog(QDialog):
    """
    Модальное диалоговое окно для редактирования настроек приложения.

    Предоставляет пользователю интерфейс для ввода и изменения ключевых
    параметров, таких как API-токены, пути к файлам и настройки
    логгирования. Загружает текущие значения при открытии и собирает
    новые данные для сохранения.

    Args:
        parent (QWidget, optional): Родительский виджет. Defaults to None.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Настройки")
        self.config = get_config()

        layout = QVBoxLayout(self)
        form_layout = QFormLayout()

        # Поля настроек
        self.yandex_token_edit = QLineEdit()
        self.google_creds_path_edit = QLineEdit()
        self.google_token_path_edit = QLineEdit()
        self.proxy_url_edit = QLineEdit()
        self.proxy_url_edit.setPlaceholderText("http://user:pass@host:port")
        self.log_level_combo = QComboBox()
        self.log_level_combo.addItems(["DEBUG", "INFO", "WARNING", "ERROR"])
        self.log_to_file_check = QCheckBox("Включить логирование в файл")
        self.log_file_path_edit = QLineEdit()

        # Добавление виджетов в форму с уникальными именами для кнопок
        form_layout.addRow("Токен Яндекс.Диска:", self.yandex_token_edit)
        form_layout.addRow("Путь к Google creds.json:", self._create_file_selector(self.google_creds_path_edit, "browse_creds_btn"))
        form_layout.addRow("Путь к Google token.json:", self._create_file_selector(self.google_token_path_edit, "browse_token_btn"))
        form_layout.addRow("URL прокси-сервера:", self.proxy_url_edit)
        form_layout.addRow("Уровень логгирования:", self.log_level_combo)
        form_layout.addRow(self.log_to_file_check)
        form_layout.addRow("Путь к файлу логов:", self._create_file_selector(self.log_file_path_edit, "browse_log_btn", is_save=True))

        layout.addLayout(form_layout)

        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

        self.load_settings()

    def _create_file_selector(self, line_edit: QLineEdit, button_object_name: str, is_save: bool = False) -> QWidget:
        """
        Создает и возвращает составной виджет для выбора файла.

        Состоит из поля ввода (QLineEdit) и кнопки "..." (QPushButton).

        Args:
            line_edit (QLineEdit): Поле ввода, которое будет частью виджета.
            button_object_name (str): Уникальное имя для объекта кнопки,
                                      используемое для тестирования.
            is_save (bool): Если True, будет открываться диалог сохранения файла,
                            иначе - диалог открытия.

        Returns:
            QWidget: Контейнерный виджет с полем ввода и кнопкой.
        """
        container = QWidget()
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(line_edit)
        browse_btn = QPushButton("...")
        browse_btn.setObjectName(button_object_name)  # Устанавливаем имя объекта
        browse_btn.clicked.connect(lambda: self._browse_file(line_edit, is_save))
        layout.addWidget(browse_btn)
        return container

    def _browse_file(self, line_edit: QLineEdit, is_save: bool):
        """
        Открывает диалог выбора файла и устанавливает выбранный путь в QLineEdit.

        Args:
            line_edit (QLineEdit): Поле ввода, в которое будет вставлен путь.
            is_save (bool): Определяет, какой диалог открывать (сохранения или открытия).
        """
        if is_save:
            path, _ = QFileDialog.getSaveFileName(self, "Сохранить файл как...")
        else:
            path, _ = QFileDialog.getOpenFileName(self, "Выбрать файл")
        if path:
            line_edit.setText(path)

    def load_settings(self):
        """Загружает текущие настройки из объекта конфигурации в виджеты диалога."""
        yandex_token = self.config.YANDEX_DISK_TOKEN.get_secret_value() if self.config.YANDEX_DISK_TOKEN else ""
        self.yandex_token_edit.setText(yandex_token)
        self.google_creds_path_edit.setText(self.config.GOOGLE_CREDS_PATH or "")
        self.google_token_path_edit.setText(self.config.GOOGLE_TOKEN_PATH or "")
        self.proxy_url_edit.setText(self.config.PROXY_URL or "")
        self.log_level_combo.setCurrentText(self.config.LOG_LEVEL)
        self.log_to_file_check.setChecked(self.config.LOG_TO_FILE)
        self.log_file_path_edit.setText(str(self.config.LOG_FILE_PATH))

    def get_settings_data(self) -> dict:
        """
        Собирает данные из полей ввода диалога в словарь.

        Returns:
            dict: Словарь с настройками, готовый для сохранения.
                  Значения `None` используются для пустых необязательных полей.
        """
        return {
            "YANDEX_DISK_TOKEN": self.yandex_token_edit.text(),
            "GOOGLE_CREDS_PATH": self.google_creds_path_edit.text(),
            "GOOGLE_TOKEN_PATH": self.google_token_path_edit.text(),
            "PROXY_URL": self.proxy_url_edit.text() or None,
            "LOG_LEVEL": self.log_level_combo.currentText(),
            "LOG_TO_FILE": str(self.log_to_file_check.isChecked()),
            "LOG_FILE_PATH": self.log_file_path_edit.text(),
        }