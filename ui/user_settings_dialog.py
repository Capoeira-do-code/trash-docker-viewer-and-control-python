# ui/user_settings_dialog.py
from PyQt5.QtWidgets import (
    QDialog, QWidget, QLabel, QLineEdit, QPushButton, QVBoxLayout, QHBoxLayout,
    QFileDialog, QGridLayout, QColorDialog, QComboBox, QFrame, QSizePolicy
)
from PyQt5.QtGui import QPixmap, QColor
from PyQt5.QtCore import Qt
import os, json

class UserSettingsDialog(QDialog):
    """
    Panel de usuario tipo tarjeta:
    - Avatar circular grande a la izquierda
    - A la derecha: título, perfil activo (solo lectura), detalles de conexión (solo lectura),
      selector de Tema (Claro/Oscuro) y Editor de Colores (bg/surface/text/muted/accent)
    - Botones para cambiar avatar, abrir perfiles de conexión y aplicar colores
    - Vista previa inmediata del tema/colores en el propio diálogo
    """
    def __init__(self, parent, prefs: dict, on_change_theme, on_open_profiles, on_apply_colors, get_active_profile):
        super().__init__(parent)
        self.setWindowTitle("Ajustes de usuario")
        self.resize(760, 520)

        self.prefs = prefs
        self.on_change_theme = on_change_theme
        self.on_open_profiles = on_open_profiles
        self.on_apply_colors = on_apply_colors
        self.get_active_profile = get_active_profile

        # Valores por defecto si faltan
        self.prefs.setdefault("theme", "light")
        self.prefs.setdefault("theme_colors", {
            "bg": "#fafbfd", "surface": "#ffffff", "text": "#1a1d21", "muted": "#6b7785", "accent": "#4b9fff"
        })

        # ---------- LAYOUT PRINCIPAL (dos columnas) ----------
        root = QHBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(18)

        # ===== Columna izquierda: avatar circular grande =====
        left = QVBoxLayout()
        left.setSpacing(12)

        self.avatar_wrap = QFrame()
        self.avatar_wrap.setObjectName("avatarWrap")
        self.avatar_wrap.setFixedSize(180, 180)
        self.avatar_wrap.setStyleSheet("""
            QFrame#avatarWrap {
                border-radius: 90px;
                background: #2db6a3;   /* color de relleno por defecto si no hay avatar */
            }
        """)
        avatar_layout = QVBoxLayout(self.avatar_wrap)
        avatar_layout.setContentsMargins(0, 0, 0, 0)
        avatar_layout.setSpacing(0)

        self.lbl_avatar = QLabel()
        self.lbl_avatar.setAlignment(Qt.AlignCenter)
        self.lbl_avatar.setScaledContents(True)
        self.lbl_avatar.setFixedSize(180, 180)
        avatar_layout.addWidget(self.lbl_avatar)

        self._load_avatar(self.prefs.get("user_avatar"))

        btn_avatar = QPushButton("Cambiar avatar…")
        btn_avatar.setMinimumHeight(34)
        btn_avatar.clicked.connect(self._pick_avatar)

        left.addWidget(self.avatar_wrap, alignment=Qt.AlignHCenter)
        left.addWidget(btn_avatar, alignment=Qt.AlignHCenter)
        left.addStretch(1)

        # ===== Columna derecha: tarjeta con contenidos =====
        right = QVBoxLayout()
        right.setSpacing(12)

        card = QFrame()
        card.setObjectName("card")
        card.setStyleSheet("""
            QFrame#card {
                background: #fff;
                border-radius: 16px;
                border: 1px solid #e8eef7;
            }
            QDialog[theme="dark"] QFrame#card {
                background: #252a32;
                border: 1px solid #3b4252;
            }
            QLabel { font-size: 14px; }
            QLineEdit { padding: 10px 12px; border: 1px solid #dfe3ea; border-radius: 10px; }
            QDialog[theme="dark"] QLineEdit { background: #1f2329; color: #e6e6e6; border: 1px solid #3b4252; }
            QPushButton { padding: 6px 12px; }
        """)
        card_l = QVBoxLayout(card)
        card_l.setContentsMargins(18, 18, 18, 18)
        card_l.setSpacing(12)

        # Título grande
        title = QLabel("<div style='font-size:28px;font-weight:800'>Profile name</div>")
        title.setTextFormat(Qt.RichText)

        # Subtítulo con perfil activo
        active = self.get_active_profile() if callable(self.get_active_profile) else None
        active_name = active.get("name") if active else "—"
        sub = QLabel(f"<div style='color:#6b7785'>Active profile: <u>{active_name}</u></div>")
        sub.setTextFormat(Qt.RichText)

        # "Connection details" (solo lectura)
        conn_box = QFrame()
        conn_box.setObjectName("connBox")
        conn_box.setStyleSheet("""
            QFrame#connBox {
                background: rgba(75,159,255,0.06);
                border: 1px dashed #c8d6f4;
                border-radius: 12px;
            }
        """)
        conn_l = QGridLayout(conn_box)
        conn_l.setContentsMargins(12, 12, 12, 12)
        conn_l.setHorizontalSpacing(10); conn_l.setVerticalSpacing(8)

        host_edit = QLineEdit(); user_edit = QLineEdit(); port_edit = QLineEdit()
        for e in (host_edit, user_edit, port_edit):
            e.setReadOnly(True)

        if active:
            host_edit.setText(str(active.get("host", "")))
            user_edit.setText(str(active.get("user", "")))
            port_edit.setText(str(active.get("port", "")))
        conn_l.addWidget(QLabel("Connection details:"), 0, 0, 1, 3)
        conn_l.addWidget(host_edit, 1, 0)
        conn_l.addWidget(user_edit, 1, 1)
        conn_l.addWidget(port_edit, 1, 2)

        # Selector de tema
        theme_row = QHBoxLayout()
        theme_row.setSpacing(8)
        theme_row.addWidget(QLabel("<b>Tema:</b>"))
        self.cmb_theme = QComboBox()
        self.cmb_theme.addItems(["Claro", "Oscuro"])
        self.cmb_theme.setCurrentIndex(1 if self.prefs.get("theme") == "dark" else 0)
        self.cmb_theme.currentIndexChanged.connect(self._theme_changed)
        theme_row.addWidget(self.cmb_theme)
        theme_row.addStretch(1)

        # Editor de colores
        colors = self.prefs.get("theme_colors", {})
        self.color_buttons = {}
        color_grid = QGridLayout()
        color_grid.setHorizontalSpacing(10); color_grid.setVerticalSpacing(10)
        row = 0
        for key, label in [("bg","Fondo"), ("surface","Superficie"), ("text","Texto"), ("muted","Muted"), ("accent","Acento")]:
            btn = QPushButton(f"{label}: {colors.get(key, '')}")
            btn.setMinimumHeight(32)
            btn.clicked.connect(lambda _=None, k=key: self._pick_color(k))
            self._style_color_btn(btn, colors.get(key, "#ffffff"))
            self.color_buttons[key] = btn
            color_grid.addWidget(btn, row // 2, row % 2)
            row += 1

        # Botones inferiores
        foot = QHBoxLayout()
        foot.addStretch(1)
        btn_profiles = QPushButton("Perfiles…")
        btn_profiles.clicked.connect(self._open_profiles)
        btn_apply_colors = QPushButton("Aplicar colores")
        btn_apply_colors.clicked.connect(self._apply_colors)
        btn_close = QPushButton("Cerrar")
        btn_close.clicked.connect(self.accept)
        for b in (btn_profiles, btn_apply_colors, btn_close):
            b.setMinimumHeight(34)
        foot.addWidget(btn_profiles)
        foot.addWidget(btn_apply_colors)
        foot.addWidget(btn_close)

        # Montaje derecha
        card_l.addWidget(title)
        card_l.addWidget(sub)
        card_l.addWidget(conn_box)
        card_l.addLayout(theme_row)
        card_l.addLayout(color_grid)
        card_l.addStretch(1)
        card_l.addLayout(foot)

        right.addWidget(card)

        # Añadir columnas al root
        root.addLayout(left)
        right_wrap = QVBoxLayout()
        right_wrap.addWidget(card)
        root.addLayout(right_wrap)

        # aplicar tema inicial al diálogo
        self._apply_preview_theme()

    # ---------- helpers ----------
    def _style_color_btn(self, btn: QPushButton, hexcolor: str):
        btn.setStyleSheet(f"QPushButton {{ background:{hexcolor}; border: 1px solid #d0d6e1; }}")

    def _load_avatar(self, path: str):
        if path and os.path.exists(path):
            pix = QPixmap(path).scaled(180, 180, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
        else:
            pix = QPixmap()  # dejamos visible el color de fondo circular
        self.lbl_avatar.setPixmap(pix)

    def _pick_avatar(self):
        fn, _ = QFileDialog.getOpenFileName(self, "Selecciona imagen", os.path.expandUser("~"), "Imágenes (*.png *.jpg *.jpeg *.webp)")
        if not fn: return
        self.prefs["user_avatar"] = fn
        self._save_prefs()
        self._load_avatar(fn)
        if self.parent() and hasattr(self.parent(), "_reload_user_button_icon"):
            self.parent()._reload_user_button_icon()

    def _pick_color(self, key: str):
        current = self.prefs.get("theme_colors", {}).get(key, "#ffffff")
        col = QColorDialog.getColor(QColor(current), self, "Elige un color")
        if not col.isValid(): return
        hexc = col.name()
        self.prefs.setdefault("theme_colors", {})[key] = hexc
        self._save_prefs()
        btn = self.color_buttons[key]
        btn.setText(f"{btn.text().split(':')[0]}: {hexc}")
        self._style_color_btn(btn, hexc)
        self._apply_preview_theme()  # refresco visual del propio diálogo

    def _theme_changed(self, idx: int):
        self.prefs["theme"] = "dark" if idx == 1 else "light"
        self._save_prefs()
        self.on_change_theme(self.prefs["theme"])
        self._apply_preview_theme()

    def _apply_colors(self):
        self.on_apply_colors(self.prefs.get("theme_colors", {}))
        self._apply_preview_theme()

    def _open_profiles(self):
        self.on_open_profiles()

    def _apply_preview_theme(self):
        # Previsualiza el tema en el propio diálogo (sin tocar app completa)
        theme = self.prefs.get("theme", "light")
        c = self.prefs.get("theme_colors", {})
        bg = "#1f2329" if theme == "dark" else c.get("bg", "#fafbfd")
        text = "#e6e6e6" if theme == "dark" else c.get("text", "#1a1d21")
        self.setProperty("theme", theme)
        self.setStyleSheet(f"""
            QDialog[theme="{theme}"] {{
                background: {bg}; color: {text};
            }}
        """)

    def _save_prefs(self):
        # Al ser un diálogo standalone, el guardado lo delega al parent si quiere; pero aquí guardamos directo por conveniencia
        try:
            os.makedirs(os.path.dirname(self._config_path()), exist_ok=True)
            with open(self._config_path(), "w", encoding="utf-8") as f:
                json.dump(self.prefs, f, indent=2)
        except Exception:
            pass

    def _config_path(self) -> str:
        return os.path.expanduser("~/.helo_wrlod/ui_prefs.json")
