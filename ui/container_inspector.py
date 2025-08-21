# ui/container_inspector.py
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QPlainTextEdit, QMessageBox, QWidget, QGridLayout
)
from PyQt5.QtCore import Qt, QMetaObject, Q_ARG
from PyQt5.QtGui import QIcon
import threading, json, time


class ContainerInspector(QDialog):
    """
    Ventana para inspeccionar un contenedor:
    - Cabecera con icono + datos
    - Botones de acción: Start / Stop / Restart / Abrir en navegador / Exec / Inspect
    - Log en tiempo real (abajo) con / sin follow
    """
    def __init__(self, ssh_client, profile_host, name, image, status, ports, icon: QIcon, parent=None):
        super().__init__(parent)
        self.ssh = ssh_client
        self.profile_host = profile_host
        self.name = name
        self.image = image
        self.status = status
        self.ports = ports
        self.icon = icon

        self.setWindowTitle(f"Inspector — {name}")
        self.resize(1100, 760)

        root = QVBoxLayout(self); root.setContentsMargins(14,14,14,14); root.setSpacing(10)

        # Header grid (web-like)
        header = QGridLayout(); header.setHorizontalSpacing(20); header.setVerticalSpacing(6)
        icon_lbl = QLabel(); icon_lbl.setPixmap(icon.pixmap(72, 72))
        title = QLabel(f"<div style='font-size:18px;font-weight:700'>{name}</div>"
                       f"<div style='color:#6b7785'>{image}</div>")
        title.setTextFormat(Qt.RichText)

        status_lbl = QLabel(f"Estado: {status or '-'}")
        ports_lbl = QLabel(f"Puertos: {self.ports or '-'}")
        host_lbl = QLabel(f"Host: {self.profile_host}")

        header.addWidget(icon_lbl, 0, 0, 3, 1, alignment=Qt.AlignTop)
        header.addWidget(title, 0, 1, 1, 2)
        header.addWidget(status_lbl, 1, 1)
        header.addWidget(ports_lbl, 1, 2)
        header.addWidget(host_lbl, 2, 1)

        # Actions
        actions = QHBoxLayout(); actions.setSpacing(8)
        btn_start = QPushButton("Iniciar"); btn_stop = QPushButton("Parar"); btn_restart = QPushButton("Reiniciar")
        btn_open = QPushButton("Abrir en navegador"); btn_exec = QPushButton("Exec"); btn_inspect = QPushButton("Inspect JSON")
        for b in (btn_start, btn_stop, btn_restart, btn_open, btn_exec, btn_inspect):
            b.setMinimumHeight(34)
        actions.addStretch(1)
        actions.addWidget(btn_start); actions.addWidget(btn_stop); actions.addWidget(btn_restart)
        actions.addSpacing(10)
        actions.addWidget(btn_open); actions.addWidget(btn_exec); actions.addWidget(btn_inspect)
        actions.addStretch(1)

        # Logs
        log_bar = QHBoxLayout(); log_bar.setSpacing(8)
        self.btn_tail = QPushButton("Cargar últimas 500"); self.btn_follow = QPushButton("Seguir"); self.btn_stop = QPushButton("Parar")
        for b in (self.btn_tail, self.btn_follow, self.btn_stop): b.setMinimumHeight(30)
        log_bar.addStretch(1); log_bar.addWidget(self.btn_tail); log_bar.addWidget(self.btn_follow); log_bar.addWidget(self.btn_stop)

        self.logs = QPlainTextEdit(); self.logs.setReadOnly(True)
        f = self.logs.font(); f.setPointSize(f.pointSize()+1); self.logs.setFont(f)

        # Assemble
        hwrap = QWidget(); hwrap.setLayout(header); root.addWidget(hwrap)
        root.addLayout(actions)
        root.addSpacing(4)
        root.addLayout(log_bar)
        root.addWidget(self.logs, 1)

        # Signals
        btn_start.clicked.connect(lambda: self._action("start"))
        btn_stop.clicked.connect(lambda: self._action("stop"))
        btn_restart.clicked.connect(lambda: self._action("restart"))
        btn_open.clicked.connect(self._open_browser)
        btn_exec.clicked.connect(self._exec_small)
        btn_inspect.clicked.connect(self._inspect_json)
        self.btn_tail.clicked.connect(self.load_tail)
        self.btn_follow.clicked.connect(self.start_follow)
        self.btn_stop.clicked.connect(self.stop_follow)

        # state
        self._stop = threading.Event()
        self._chan = None

        # initial load
        self.load_tail()

    def closeEvent(self, e):
        self.stop_follow()
        super().closeEvent(e)

    # ---------- Actions ----------
    def _action(self, action: str):
        try:
            self.ssh.exec_command(f"docker {action} {self.name}")
            self._append(f"[{action.upper()}] ejecutado en {self.name}")
            time.sleep(0.4)
            self.load_tail()
        except Exception as ex:
            QMessageBox.critical(self, "Error", str(ex))

    def _open_browser(self):
        try:
            if not self.ports:
                QMessageBox.warning(self, "Navegador", "Este contenedor no expone puertos"); return
            first_map = self.ports.split(",")[0].strip()
            host_port = first_map.split(":")[1].split("->")[0]
            import webbrowser
            webbrowser.open(f"http://{self.profile_host}:{host_port}")
        except Exception:
            QMessageBox.warning(self, "Navegador", "No se pudo abrir la URL")

    def _exec_small(self):
        from PyQt5.QtWidgets import QInputDialog
        cmd, ok = QInputDialog.getText(self, "Exec", "sh -lc «comando»:")
        if not ok or not cmd.strip():
            return
        full = f"docker exec {self.name} sh -lc {json.dumps(cmd.strip())}"
        try:
            stdout = self.ssh.exec_command(full)
            out = "".join(list(stdout))
            self._append(f"$ {cmd}\n{out}")
        except Exception as ex:
            QMessageBox.critical(self, "Error", str(ex))

    def _inspect_json(self):
        try:
            stdout = self.ssh.exec_command(f"docker inspect {self.name}")
            out = "".join(list(stdout))
            self._append(out)
        except Exception as ex:
            QMessageBox.critical(self, "Error", str(ex))

    # ---------- Logs ----------
    def _append(self, text: str):
        QMetaObject.invokeMethod(self.logs, "appendPlainText", Qt.QueuedConnection, Q_ARG(str, text))

    def load_tail(self, n: int = 500):
        try:
            stdout = self.ssh.exec_command(f"docker logs --tail {n} {self.name}")
            out = "".join(list(stdout))
            self.logs.setPlainText(out)
        except Exception as ex:
            self.logs.setPlainText(str(ex))

    def start_follow(self, n: int = 200):
        self.stop_follow()
        self._stop.clear()
        t = threading.Thread(target=self._follow_thread, args=(n,), daemon=True)
        t.start()

    def stop_follow(self):
        self._stop.set()
        try:
            if self._chan:
                self._chan.close()
        except Exception:
            pass
        self._chan = None

    def _follow_thread(self, n: int):
        cmd = f"docker logs --tail {n} -f {self.name}"
        try:
            transport = self.ssh.client.get_transport()
            chan = transport.open_session(); chan.get_pty(); chan.exec_command(cmd)
            self._chan = chan
            self._append("— siguiendo logs —")
            while not self._stop.is_set():
                if chan.recv_ready():
                    data = chan.recv(4096).decode("utf-8", errors="replace")
                    if data: self._append(data.rstrip("\n"))
                if chan.recv_stderr_ready():
                    data = chan.recv_stderr(4096).decode("utf-8", errors="replace")
                    if data: self._append(data.rstrip("\n"))
                if chan.exit_status_ready():
                    break
                time.sleep(0.05)
            chan.close()
        except Exception as ex:
            self._append(f"Error: {ex}")
