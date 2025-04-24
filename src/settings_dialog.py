from PySide6.QtWidgets import QDialog, QVBoxLayout, QLabel, QLineEdit, QPushButton, QFileDialog, QCheckBox, QHBoxLayout

class SettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Настройки")
        self.setMinimumWidth(400)
        layout = QVBoxLayout()

        # Путь к ffmpeg
        self.ffmpeg_label = QLabel("Путь к ffmpeg:")
        self.ffmpeg_path = QLineEdit()
        self.ffmpeg_btn = QPushButton("Выбрать...")
        self.ffmpeg_btn.clicked.connect(self.select_ffmpeg)
        ffmpeg_row = QHBoxLayout()
        ffmpeg_row.addWidget(self.ffmpeg_path)
        ffmpeg_row.addWidget(self.ffmpeg_btn)

        # Логирование в файл
        self.log_to_file = QCheckBox("Включить логирование в файл")
        self.log_file_label = QLabel("Путь к лог-файлу:")
        self.log_file_path = QLineEdit()
        self.log_file_btn = QPushButton("Выбрать...")
        self.log_file_btn.clicked.connect(self.select_log_file)
        log_row = QHBoxLayout()
        log_row.addWidget(self.log_file_path)
        log_row.addWidget(self.log_file_btn)

        # Кнопки
        self.save_btn = QPushButton("Сохранить")
        self.cancel_btn = QPushButton("Отмена")
        btn_row = QHBoxLayout()
        btn_row.addWidget(self.save_btn)
        btn_row.addWidget(self.cancel_btn)

        layout.addWidget(self.ffmpeg_label)
        layout.addLayout(ffmpeg_row)
        layout.addWidget(self.log_to_file)
        layout.addWidget(self.log_file_label)
        layout.addLayout(log_row)
        layout.addLayout(btn_row)
        self.setLayout(layout)

        self.cancel_btn.clicked.connect(self.reject)
        self.save_btn.clicked.connect(self.accept)
        self.log_to_file.toggled.connect(self.update_log_fields)
        self.update_log_fields()

    def select_ffmpeg(self):
        path, _ = QFileDialog.getOpenFileName(self, "Выбрать ffmpeg", filter="ffmpeg.exe (*.exe);;Все файлы (*)")
        if path:
            self.ffmpeg_path.setText(path)

    def select_log_file(self):
        path, _ = QFileDialog.getSaveFileName(self, "Выбрать лог-файл", filter="*.log")
        if path:
            self.log_file_path.setText(path)

    def update_log_fields(self):
        enabled = self.log_to_file.isChecked()
        self.log_file_label.setEnabled(enabled)
        self.log_file_path.setEnabled(enabled)
        self.log_file_btn.setEnabled(enabled)
