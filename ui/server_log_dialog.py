# ui/server_log_dialog.py
from PyQt5.QtWidgets import QDialog, QVBoxLayout, QPlainTextEdit, QHBoxLayout, QPushButton, QSpinBox, QLabel
from PyQt5.QtCore import Qt, QMetaObject, Q_ARG
import threading, time

class ServerLogDialog(QDialog):
    """
    Intenta en orden:
      1) journalctl -u docker -n N -f
      2) tail -n N -f /var/log/docker.log
      3) docker events (como mínimo)
    """
    def __init__(self, ssh_client, parent=None):
        super().__init__(parent)
        self.ssh = ssh_client
        self.setWindowTitle("Log del servidor")
        self.resize(1100, 720)

        lay = QVBoxLayout(self); lay.setContentsMargins(12,12,12,12); lay.setSpacing(8)

        ctrl = QHBoxLayout(); ctrl.setSpacing(8)
        ctrl.addWidget(QLabel("Líneas:"))
        self.tail = QSpinBox(); self.tail.setRange(100, 100000); self.tail.setValue(1500)
        ctrl.addWidget(self.tail)
        self.btn_start = QPushButton("Iniciar"); self.btn_stop = QPushButton("Parar")
        ctrl.addStretch(1); ctrl.addWidget(self.btn_start); ctrl.addWidget(self.btn_stop)
        lay.addLayout(ctrl)

        self.text = QPlainTextEdit(); self.text.setReadOnly(True)
        f = self.text.font(); f.setPointSize(f.pointSize()+1); self.text.setFont(f)
        lay.addWidget(self.text, 1)

        self._stop = threading.Event()
        self._chan = None

        self.btn_start.clicked.connect(self.start_stream)
        self.btn_stop.clicked.connect(self.stop_stream)

    def closeEvent(self, e):
        self.stop_stream()
        super().closeEvent(e)

    def start_stream(self):
        self.stop_stream()
        self._stop.clear()
        t = threading.Thread(target=self._run, daemon=True)
        t.start()

    def stop_stream(self):
        self._stop.set()
        try:
            if self._chan: self._chan.close()
        except Exception:
            pass
        self._chan = None

    def _emit(self, text: str):
        QMetaObject.invokeMethod(self.text, "appendPlainText", Qt.QueuedConnection, Q_ARG(str, text))

    def _run(self):
        n = int(self.tail.value())
        cmds = [
            f"journalctl -u docker -n {n} -f",
            f"tail -n {n} -f /var/log/docker.log",
            "docker events --format '{{.Time}} {{.Type}} {{.Action}} {{.Actor.Attributes.name}}'"
        ]
        for cmd in cmds:
            try:
                transport = self.ssh.client.get_transport()
                chan = transport.open_session(); chan.get_pty(); chan.exec_command(cmd)
                self._chan = chan
                self._emit(f"→ {cmd}\n")
                while not self._stop.is_set():
                    if chan.recv_ready():
                        data = chan.recv(4096).decode("utf-8", errors="replace")
                        if data: self._emit(data.rstrip("\n"))
                    if chan.recv_stderr_ready():
                        data = chan.recv_stderr(4096).decode("utf-8", errors="replace")
                        if data: self._emit(data.rstrip("\n"))
                    if chan.exit_status_ready():
                        break
                    time.sleep(0.05)
                chan.close()
                return
            except Exception:
                continue
        self._emit("No se pudieron leer logs del host.")
