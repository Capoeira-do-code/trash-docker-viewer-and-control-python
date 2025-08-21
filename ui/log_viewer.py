# ui/log_viewer.py
from PyQt5.QtWidgets import QDialog, QVBoxLayout, QTextEdit
from PyQt5.QtCore import QThread, pyqtSignal
from core.ssh_client import SSHClient


class LogWorker(QThread):
    new_line = pyqtSignal(str)

    def __init__(self, ssh_client: SSHClient, container_name: str):
        super().__init__()
        self.ssh_client = ssh_client
        self.container_name = container_name
        self._running = True

    def run(self):
        command = f"docker logs -f {self.container_name}"
        stdout = self.ssh_client.exec_command(command)
        for line in iter(stdout.readline, ""):
            if not self._running:
                break
            if line:
                self.new_line.emit(line.strip())

    def stop(self):
        self._running = False
        self.terminate()


class LogViewer(QDialog):
    def __init__(self, ssh_client: SSHClient, container_name: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Logs - {container_name}")
        self.setGeometry(250, 150, 800, 500)

        layout = QVBoxLayout(self)
        self.text_edit = QTextEdit(self)
        self.text_edit.setReadOnly(True)
        layout.addWidget(self.text_edit)

        # Worker para logs
        self.worker = LogWorker(ssh_client, container_name)
        self.worker.new_line.connect(self._append_log)
        self.worker.start()

    def _append_log(self, line: str):
        self.text_edit.append(line)

    def closeEvent(self, event):
        self.worker.stop()
        event.accept()
