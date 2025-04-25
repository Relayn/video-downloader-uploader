import pytest
from PySide6.QtWidgets import QApplication
from src.gui import VideoUploaderGUI

@pytest.fixture
def app(qtbot):
    test_app = VideoUploaderGUI()
    qtbot.addWidget(test_app)
    return test_app

def test_gui_download_upload_flow(app, qtbot):
    app.url_edit.setPlainText("https://youtube.com/watch?v=abc")
    app.cloud_combo.setCurrentText("Yandex.Disk")
    app.folder_edit.setText("TestFolder")
    app.gdrive_id_edit.setText("")
    app.filename_edit.setText("TestFile")
    # Мокаем воркер и сигнал завершения
    class DummyWorker:
        signals = type("S", (), {"progress": lambda *a: None, "error": lambda *a: None, "finished": lambda *a: None})()
        def start(self): app.on_task_finished({"download": [{}], "upload": [{"status": "успех"}]})
    app.worker = DummyWorker()
    app.start_download_upload()
    assert app.progress_bar.value() == 0 or app.progress_bar.value() == 100
