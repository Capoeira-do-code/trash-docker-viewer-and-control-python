# ui/profile_selector.py
from PyQt5.QtWidgets import QDialog, QVBoxLayout, QListWidget, QListWidgetItem, QPushButton
from PyQt5.QtGui import QIcon
import os
from core.config import load_profiles


class ProfileSelector(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Seleccionar perfil")
        self.setGeometry(250, 200, 300, 400)

        layout = QVBoxLayout(self)

        self.list = QListWidget()
        profiles = load_profiles()
        for profile in profiles:
            item = QListWidgetItem(QIcon(os.path.join("ui", "resources", "host.png")), profile["name"])
            item.setData(1000, profile)  # guardamos el diccionario completo
            self.list.addItem(item)
            
        layout.addWidget(self.list)

        self.btn_ok = QPushButton("Conectar")
        self.btn_ok.clicked.connect(self.accept)
        layout.addWidget(self.btn_ok)

    def get_selected_profile(self):
        item = self.list.currentItem()
        if item:
            return item.data(1000)
        return None
