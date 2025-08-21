# ui/settings_dialog.py
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QListWidget, QMessageBox
)
from core.config import load_profiles, save_profiles, encrypt_password, decrypt_password


class SettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Perfiles SSH - Helo Wrlod")
        self.setGeometry(300, 200, 400, 300)

        layout = QVBoxLayout(self)

        # Lista de perfiles
        self.list_profiles = QListWidget()
        self.list_profiles.addItems([p["name"] for p in load_profiles()])
        layout.addWidget(self.list_profiles)

        # Campos de texto
        self.name = QLineEdit(); self.name.setPlaceholderText("Nombre perfil")
        self.host = QLineEdit(); self.host.setPlaceholderText("Host")
        self.user = QLineEdit(); self.user.setPlaceholderText("Usuario")
        self.password = QLineEdit(); self.password.setPlaceholderText("Contraseña")
        self.password.setEchoMode(QLineEdit.Password)

        for w in (self.name, self.host, self.user, self.password):
            layout.addWidget(w)

        # Botones
        btns = QHBoxLayout()
        self.btn_save = QPushButton("Guardar")
        self.btn_delete = QPushButton("Eliminar")
        self.btn_cancel = QPushButton("Cerrar")
        btns.addWidget(self.btn_save)
        btns.addWidget(self.btn_delete)
        btns.addWidget(self.btn_cancel)
        layout.addLayout(btns)

        self.btn_save.clicked.connect(self._save_profile)
        self.btn_delete.clicked.connect(self._delete_profile)
        self.btn_cancel.clicked.connect(self.close)

    def _save_profile(self):
        profiles = load_profiles()
        encrypted_pass = encrypt_password(self.password.text())
        profile = {
            "name": self.name.text(),
            "host": self.host.text(),
            "user": self.user.text(),
            "password": encrypted_pass
        }
        # Reemplazar si ya existe
        profiles = [p for p in profiles if p["name"] != profile["name"]]
        profiles.append(profile)
        save_profiles(profiles)
        self.list_profiles.clear()
        self.list_profiles.addItems([p["name"] for p in profiles])
        QMessageBox.information(self, "Guardado", "Perfil guardado correctamente")

    def _delete_profile(self):
        profiles = load_profiles()
        selected = self.list_profiles.currentItem()
        if not selected:
            return
        profiles = [p for p in profiles if p["name"] != selected.text()]
        save_profiles(profiles)
        self.list_profiles.clear()
        self.list_profiles.addItems([p["name"] for p in profiles])
        QMessageBox.information(self, "Eliminado", "Perfil eliminado")
