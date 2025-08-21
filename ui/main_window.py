# ui/main_window.py
from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QTableWidget, QTableWidgetItem, QToolBar, QAction, QStatusBar,
    QMessageBox, QAbstractItemView, QDialog, QLabel,
    QGridLayout, QFrame, QApplication, QLineEdit, QMenu, QToolButton,
    QFileDialog, QPushButton, QSizePolicy, QColorDialog, QHeaderView, QComboBox, QTextEdit, QSplitter, QStyle
)
from PyQt5.QtGui import QIcon, QPixmap, QColor, QMouseEvent, QKeyEvent
from PyQt5.QtCore import Qt, QPoint, QSize, QTimer, QObject, QEvent
import os, webbrowser, re, json, threading, time
import sys
from typing import Dict, Any

# Dependencias del proyecto (deben existir)
from ui.profile_selector import ProfileSelector
from ui.container_inspector import ContainerInspector
from core.ssh_client import SSHClient
from core.config import decrypt_password

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

CONFIG_UI = os.path.expanduser("~/.helo_wrlod/ui_prefs.json")

def _load_prefs():
    try:
        with open(CONFIG_UI, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def _save_prefs(d: dict):
    os.makedirs(os.path.dirname(CONFIG_UI), exist_ok=True)
    with open(CONFIG_UI, "w", encoding="utf-8") as f:
        json.dump(d, f, indent=2)


# ===================== Ajustes de Usuario (embebido) =====================
class UserSettingsDialog(QDialog):
    """
    - Tema Claro/Oscuro (presets cerrados; no editables).
    - Editor de colores => siempre guarda como nuevo tema personalizado (con nombre).
    - Desplegable de temas personalizados (carga como "tema claro" personalizado).
    - Nombre visible del perfil editable, con Enter sin disparar botones.
    - Control de altura de filas y botón para resetear anchos de columnas.
    """
    def __init__(self, parent, prefs: dict, on_change_theme, on_open_profiles, on_create_profile, on_apply_colors, on_reset_col_widths, get_active_profile):
        super().__init__(parent)
        self.setWindowTitle("Ajustes de usuario")
        self.resize(800, 600)

        self.prefs = prefs
        self.on_change_theme = on_change_theme
        self.on_open_profiles = on_open_profiles
        self.on_create_profile = on_create_profile
        self.on_apply_colors = on_apply_colors
        self.on_reset_col_widths = on_reset_col_widths
        self.get_active_profile = get_active_profile

        # Defaults
        self.prefs.setdefault("theme", "light")
        self.prefs.setdefault("theme_colors", {
            "bg": "#fafbfd", "surface": "#ffffff", "text": "#1a1d21", "muted": "#6b7785", "accent": "#4b9fff"
        })
        self.prefs.setdefault("custom_themes", {})  # name -> colors dict
        self.prefs.setdefault("profile_display_name", "")
        self.prefs.setdefault("row_height", 80)

        root = QVBoxLayout(self); root.setContentsMargins(16,16,16,16); root.setSpacing(14)

        # --- Cabecera ---
        head = QHBoxLayout(); head.setSpacing(14)
        self.lbl_avatar = QLabel(); self.lbl_avatar.setFixedSize(96, 96)
        self.lbl_avatar.setStyleSheet("border-radius: 48px; background:#E7EDF6;")
        self._load_avatar(self.prefs.get("user_avatar"))
        head.addWidget(self.lbl_avatar, alignment=Qt.AlignTop)

        title_box = QVBoxLayout(); title_box.setSpacing(6)
        # Título editable
        self.lbl_title = QLabel(); self.lbl_title.setStyleSheet("font-size:26px; font-weight:800;")
        self.edit_title = QLineEdit(); self.edit_title.setVisible(False); self.edit_title.setMaxLength(60)
        self.edit_title.setPlaceholderText("Nombre visible del perfil")
        self._sync_profile_title_text()
        self.lbl_title.installEventFilter(_ClickToEditFilter(self._start_edit_title))
        self.edit_title.installEventFilter(_EnterCommitFilter(self._commit_profile_title))
        subtitle = QLabel("<span style='color:#6b7785'>Configuración del usuario y apariencia</span>")
        subtitle.setTextFormat(Qt.RichText)

        btn_row = QHBoxLayout(); btn_row.setSpacing(8)
        btn_avatar = QPushButton("Cambiar avatar…"); btn_avatar.setMinimumHeight(32); btn_avatar.setAutoDefault(False); btn_avatar.setDefault(False)
        btn_avatar.clicked.connect(self._pick_avatar)
        btn_profiles = QPushButton("Perfiles…"); btn_profiles.setMinimumHeight(32); btn_profiles.setAutoDefault(False); btn_profiles.setDefault(False)
        btn_profiles.clicked.connect(self.on_open_profiles)
        btn_new_profile = QPushButton("Nuevo perfil…"); btn_new_profile.setMinimumHeight(32); btn_new_profile.setAutoDefault(False); btn_new_profile.setDefault(False)
        btn_new_profile.clicked.connect(self.on_create_profile)
        btn_row.addWidget(btn_avatar); btn_row.addWidget(btn_profiles); btn_row.addWidget(btn_new_profile); btn_row.addStretch(1)

        title_box.addWidget(self.lbl_title)
        title_box.addWidget(subtitle)   # << justo debajo del nombre
        title_box.addWidget(self.edit_title)
        title_box.addLayout(btn_row)

        head.addLayout(title_box); head.addStretch(1)

        # --- Tarjeta principal ---
        card = QFrame(); card.setObjectName("card")
        card.setStyleSheet("""
            QFrame#card { background:#fff; border-radius:16px; border:1px solid #e8eef7; }
            QDialog[theme="dark"] QFrame#card { background:#252a32; border:1px solid #3b4252; }
            QLabel { font-size:14px; }
            QLineEdit { padding: 10px 12px; border: 1px solid #dfe3ea; border-radius: 10px; }
            QDialog[theme="dark"] QLineEdit { background:#1f2329; color:#e6e6e6; border:1px solid #3b4252; }
            QPushButton { padding:6px 12px; }
        """)
        card_l = QVBoxLayout(card); card_l.setContentsMargins(18,18,18,18); card_l.setSpacing(12)

        # Tema (presets) + personalizados
        theme_row = QHBoxLayout(); theme_row.setSpacing(8)
        theme_row.addWidget(QLabel("<b>Tema:</b>"))
        self.btn_light = QPushButton("Claro"); self.btn_light.setMinimumHeight(30); self.btn_light.setAutoDefault(False); self.btn_light.setDefault(False)
        self.btn_dark  = QPushButton("Oscuro"); self.btn_dark.setMinimumHeight(30); self.btn_dark.setAutoDefault(False); self.btn_dark.setDefault(False)
        self.btn_light.clicked.connect(lambda: self._set_theme("light"))
        self.btn_dark.clicked.connect(lambda: self._set_theme("dark"))
        theme_row.addWidget(self.btn_light); theme_row.addWidget(self.btn_dark)
        theme_row.addSpacing(8)
        theme_row.addWidget(QLabel("Temas personalizados:"))
        self.cmb_custom = QComboBox(); self.cmb_custom.setMinimumWidth(220)
        self._reload_custom_themes()
        self.cmb_custom.currentIndexChanged.connect(self._load_selected_custom_theme_as_light)
        theme_row.addWidget(self.cmb_custom); theme_row.addStretch(1)

        # Editor de colores (siempre guarda como tema nuevo)
        colors = self.prefs.get("theme_colors", {})
        grid = QGridLayout(); grid.setHorizontalSpacing(10); grid.setVerticalSpacing(10)
        self.color_buttons = {}
        row = 0
        for key, label in [("bg","Fondo"), ("surface","Superficie"), ("text","Texto"), ("muted","Muted"), ("accent","Acento")]:
            btn = QPushButton(f"{label}: {colors.get(key, '')}")
            btn.setMinimumHeight(30); btn.setAutoDefault(False); btn.setDefault(False)
            btn.clicked.connect(lambda _=None, k=key: self._pick_color(k))
            self._style_color_btn(btn, colors.get(key, "#ffffff"))
            self.color_buttons[key] = btn
            grid.addWidget(btn, row // 2, row % 2); row += 1

        name_row = QHBoxLayout()
        name_row.addWidget(QLabel("Nombre del tema:"))
        self.edt_theme_name = QLineEdit(self.prefs.get("last_custom_theme_name", "Mi tema"))
        self.edt_theme_name.setPlaceholderText("Mi tema")
        name_row.addWidget(self.edt_theme_name, 1)

        actions_row = QHBoxLayout(); actions_row.addStretch(1)
        btn_save_theme = QPushButton("Guardar tema"); btn_save_theme.setMinimumHeight(32); btn_save_theme.setAutoDefault(False); btn_save_theme.setDefault(False)
        btn_del_theme  = QPushButton("Eliminar tema"); btn_del_theme.setMinimumHeight(32); btn_del_theme.setAutoDefault(False); btn_del_theme.setDefault(False)
        btn_apply_cols = QPushButton("Aplicar colores"); btn_apply_cols.setMinimumHeight(32); btn_apply_cols.setAutoDefault(False); btn_apply_cols.setDefault(False)
        btn_reset_cols = QPushButton("Reset anchos columnas"); btn_reset_cols.setMinimumHeight(32); btn_reset_cols.setAutoDefault(False); btn_reset_cols.setDefault(False)
        btn_save_theme.clicked.connect(self._save_custom_theme)
        btn_del_theme.clicked.connect(self._delete_selected_theme)
        btn_apply_cols.clicked.connect(self.on_apply_colors)
        btn_reset_cols.clicked.connect(self.on_reset_col_widths)
        actions_row.addWidget(btn_save_theme); actions_row.addWidget(btn_del_theme); actions_row.addWidget(btn_apply_cols); actions_row.addWidget(btn_reset_cols)

        # Altura de filas
        size_row = QHBoxLayout()
        size_row.addWidget(QLabel("Altura de filas:"))
        self.row_height_edit = QLineEdit(str(self.prefs.get("row_height", 80))); self.row_height_edit.setFixedWidth(80)
        btn_apply_row_h = QPushButton("Aplicar"); btn_apply_row_h.setMinimumHeight(28); btn_apply_row_h.setAutoDefault(False); btn_apply_row_h.setDefault(False)
        btn_apply_row_h.clicked.connect(self._apply_row_height)
        size_row.addWidget(self.row_height_edit)
        size_row.addWidget(btn_apply_row_h)
        size_row.addStretch(1)

        card_l.addLayout(theme_row)
        card_l.addLayout(grid)
        card_l.addLayout(name_row)
        card_l.addLayout(actions_row)
        card_l.addLayout(size_row)

        footer = QHBoxLayout(); footer.addStretch(1)
        btn_close = QPushButton("Cerrar"); btn_close.setMinimumHeight(34); btn_close.setAutoDefault(False); btn_close.setDefault(False)
        btn_close.clicked.connect(self.accept)
        footer.addWidget(btn_close)

        root.addLayout(head)
        root.addWidget(card)
        root.addLayout(footer)
        self._apply_preview_theme()

    # ---- helpers ----
    def _start_edit_title(self):
        self.lbl_title.hide(); self.edit_title.show(); self.edit_title.setText(self.lbl_title.text()); self.edit_title.setFocus(); self.edit_title.selectAll()

    def _commit_profile_title(self):
        text = self.edit_title.text().strip() or "Perfil"
        self.prefs["profile_display_name"] = text
        _save_prefs(self.prefs)
        self.lbl_title.setText(text)
        self.edit_title.hide(); self.lbl_title.show()
        if hasattr(self.parent(), "_reload_user_button_icon"):
            self.parent()._reload_user_button_icon()

    def _sync_profile_title_text(self):
        active = self.get_active_profile() if callable(self.get_active_profile) else None
        default_name = (active or {}).get("name") or (active or {}).get("host") or "Perfil"
        current = self.prefs.get("profile_display_name") or default_name
        self.lbl_title.setText(current)

    def _style_color_btn(self, btn: QPushButton, hexcolor: str):
        btn.setStyleSheet(f"QPushButton {{ background:{hexcolor}; border:1px solid #d0d6e1; }}")

    def _load_avatar(self, path: str):
        pix = QPixmap()
        if path and os.path.exists(path):
            pix = QPixmap(path)
        else:
            default_path = os.path.join("ui", "resources", "docker.png")
            if os.path.exists(default_path):
                pix = QPixmap(default_path)
        if not pix.isNull():
            pix = pix.scaled(96, 96, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
        else:
            # Fallback seguro si no hay imagen en disco
            icon = self.style().standardIcon(QStyle.SP_ComputerIcon)
            pix = icon.pixmap(96, 96)
        self.lbl_avatar.setPixmap(pix)
        self.lbl_avatar.setScaledContents(True)

    def _pick_avatar(self):
        fn, _ = QFileDialog.getOpenFileName(self, "Selecciona imagen", os.path.expanduser("~"), "Imágenes (*.png *.jpg *.jpeg *.webp)")
        if not fn: return
        self.prefs["user_avatar"] = fn
        _save_prefs(self.prefs)
        self._load_avatar(fn)
        if hasattr(self.parent(), "_reload_user_button_icon"):
            self.parent()._reload_user_button_icon()

    def _set_theme(self, mode: str):
        if mode == "dark":
            # Default values for the dark theme
            self.theme = "dark"
            self.theme_colors = {
                "bg": "#1f2329",
                "surface": "#252a32",
                "text": "#e6e6e6",
                "muted": "#6b7785",
                "accent": "#569cd6"
            }
        elif mode == "light":
            # Default values for the light theme
            self.theme = "light"
            self.theme_colors = {
                "bg": "#fafbfd",
                "surface": "#ffffff",
                "text": "#1a1d21",
                "muted": "#6b7785",
                "accent": "#4b9fff"
            }
        # Notify the main window to apply the theme
        if callable(self.on_change_theme):
            self.on_change_theme(self.theme)

    def _pick_color(self, key: str):
        # Personalizar colores => se preparan para guardar como tema nuevo
        current = self.prefs.get("theme_colors", {}).get(key, "#ffffff")
        col = QColorDialog.getColor(QColor(current), self, "Elige un color")
        if not col.isValid(): return
        hexc = col.name()
        self.prefs.setdefault("theme_colors", {})[key] = hexc
        _save_prefs(self.prefs)
        btn = self.color_buttons[key]
        btn.setText(f"{btn.text().split(':')[0]}: {hexc}")
        self._style_color_btn(btn, hexc)
        self._apply_preview_theme()

    def _reload_custom_themes(self):
        self.cmb_custom.blockSignals(True)
        self.cmb_custom.clear()
        self.cmb_custom.addItem("— Selecciona tema —")
        for name in sorted(self.prefs.get("custom_themes", {}).keys()):
            self.cmb_custom.addItem(name)
        self.cmb_custom.blockSignals(False)

    def _save_custom_theme(self):
        name = self.edt_theme_name.text().strip() or "Mi tema"
        colors = dict(self.prefs.get("theme_colors", {}))
        self.prefs.setdefault("custom_themes", {})[name] = colors
        self.prefs["last_custom_theme_name"] = name
        _save_prefs(self.prefs)
        self._reload_custom_themes()
        # Al guardar, aplica como tema CLARO personalizado
        self.prefs["theme"] = "light"; _save_prefs(self.prefs)
        self.on_change_theme("light"); self.on_apply_colors(colors)
        self._apply_preview_theme()

    def _delete_selected_theme(self):
        idx = self.cmb_custom.currentIndex()
        if idx <= 0: return
        name = self.cmb_custom.currentText()
        if name in self.prefs.get("custom_themes", {}):
            del self.prefs["custom_themes"][name]
            _save_prefs(self.prefs)
            self._reload_custom_themes()

    def _load_selected_custom_theme_as_light(self, idx: int):
        # *** FIX: todo este bloque debe ir indentado dentro del def ***
        if idx <= 0:
            return
        theme_name = self.cmb_custom.currentText()
        colors = self.prefs.get("custom_themes", {}).get(theme_name, {})
        if not colors:
            return

        # Guardar selección como tema claro personalizado
        self.prefs["last_custom_theme_name"] = theme_name
        self.prefs["theme"] = "light"
        self.prefs["theme_colors"] = dict(colors)
        _save_prefs(self.prefs)

        # Notificar al main y aplicar
        if callable(self.on_change_theme):
            self.on_change_theme("light")
        if callable(self.on_apply_colors):
            self.on_apply_colors(colors)

        # Refrescar botones de color y previsualización
        for k, btn in self.color_buttons.items():
            val = colors.get(k, "#ffffff")
            label = btn.text().split(":")[0]
            btn.setText(f"{label}: {val}")
            self._style_color_btn(btn, val)
        self._apply_preview_theme()

    def _apply_row_height(self):
        try:
            val = max(40, int(self.row_height_edit.text()))
        except Exception:
            val = 80
        self.prefs["row_height"] = val; _save_prefs(self.prefs)
        # Notificamos al main si quiere re-aplicar
        if hasattr(self.parent(), "_apply_row_height_from_prefs"):
            self.parent()._apply_row_height_from_prefs()

    def _apply_preview_theme(self):
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


class _ClickToEditFilter(QObject):
    def __init__(self, start_cb): super().__init__(); self.start_cb = start_cb
    def eventFilter(self, obj, ev):
        if ev.type() == QEvent.MouseButtonPress and ev.button() == Qt.LeftButton:
            self.start_cb(); return True
        return False

class _EnterCommitFilter(QObject):
    def __init__(self, commit_cb): super().__init__(); self.commit_cb = commit_cb
    def eventFilter(self, obj, ev):
        if isinstance(ev, QKeyEvent) and ev.type() == QEvent.KeyPress and ev.key() in (Qt.Key_Return, Qt.Key_Enter):
            self.commit_cb()
            return True  # << evita que Enter dispare botones por defecto
        return False


# ========================= Ventana Principal =========================
class MainWindow(QMainWindow):
    def __init__(self, parent=None):
        super().__init__(parent)

        # Estado / Preferencias
        self.prefs = _load_prefs()
        self.favorites = set(self.prefs.get("favorites", []))
        self.container_icons = dict(self.prefs.get("container_icons", {}))  # contenedor->ruta
        self.theme = self.prefs.get("theme", "light")
        self.theme_colors = self.prefs.get("theme_colors", {
            "bg": "#fafbfd", "surface": "#ffffff", "text": "#1a1d21", "muted": "#6b7785", "accent": "#4b9fff"
        })
        self.prefs.setdefault("custom_themes", {})
        self.prefs.setdefault("table_col_widths", {})   # str(index)->width
        self.prefs.setdefault("row_height", 80)

        self.ssh_client: SSHClient = None
        self.current_profile: Dict[str, Any] = None
        self.rows_cache = []  # [(name,image,status,ports)]

        # Auto-refresh
        self.timer = QTimer(self)
        self.auto_refresh_ms = int(self.prefs.get("auto_refresh_ms", 5000))
        self.auto_refresh_on = bool(self.prefs.get("auto_refresh_on", True))
        self.timer.timeout.connect(self.refresh_all)

        # Ventana
        self.setWindowTitle("Helo Wrlod - Docker SSH Manager")
        self.resize(1400, 860)
        self.setWindowIcon(QIcon(os.path.join("ui", "resources", "docker.png")))

        # Centro con splitter (lista + panel derecho log/connecting)
        splitter = QSplitter(Qt.Horizontal, self)
        main_panel = QWidget(); right_panel = QWidget(); right_panel.setObjectName("rightPanel")
        splitter.addWidget(main_panel); splitter.addWidget(right_panel)
        splitter.setStretchFactor(0, 3); splitter.setStretchFactor(1, 1)
        self.setCentralWidget(splitter)

        root = QVBoxLayout(main_panel); root.setContentsMargins(14,14,14,14); root.setSpacing(12)

        # Barra superior: buscador + ?
        top = QHBoxLayout(); top.setSpacing(10)
        self.filter_edit = QLineEdit(); self.filter_edit.setPlaceholderText("Filtrar contenedores…")
        self.filter_edit.textChanged.connect(self._apply_filter); self.filter_edit.setMinimumHeight(40)
        top.addWidget(self.filter_edit, 1)

        btn_help = QToolButton(); btn_help.setText("?"); btn_help.setToolButtonStyle(Qt.ToolButtonTextOnly)
        btn_help.clicked.connect(self._show_help)
        top.addWidget(btn_help, 0, Qt.AlignRight)
        root.addLayout(top)

        # Tabla
        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(["", "", "Nombre", "Imagen", "Estado", "Puertos"])
        hdr = self.table.horizontalHeader()
        hdr.setStretchLastSection(True)
        hdr.setSectionResizeMode(0, QHeaderView.Fixed)  # estado
        hdr.setSectionResizeMode(1, QHeaderView.Fixed)  # icono docker
        hdr.setSectionResizeMode(2, QHeaderView.Stretch)
        hdr.setSectionResizeMode(3, QHeaderView.Stretch)
        hdr.setSectionResizeMode(4, QHeaderView.Stretch)
        hdr.setSectionResizeMode(5, QHeaderView.Stretch)
        hdr.setMinimumSectionSize(160)

        self.table.verticalHeader().setVisible(False)
        self._apply_row_height_from_prefs()
        self.table.setAlternatingRowColors(True)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._context_menu)
        self.table.itemDoubleClicked.connect(self._double_click_open)

        # Cargar anchos guardados por columna
        self._apply_saved_col_widths()
        hdr.sectionResized.connect(self._save_col_width)

        self.table.setStyleSheet("""
            QTableWidget { font-size: 16px; background: #ffffff; }
            QTableWidget::item { padding: 10px 12px; }
            QHeaderView::section { font-size: 14px; padding: 12px 10px; background: #f5f7fb; }
            QMainWindow[theme="dark"] QTableWidget { background: #252a32; color: #e6e6e6; }
            QMainWindow[theme="dark"] QHeaderView::section { background: #2b313b; color: #e6e6e6; }
        """)
        root.addWidget(self.table, 1)

        # Grid (oculto por defecto)
        self.grid_wrap = QWidget()
        self.grid = QGridLayout(self.grid_wrap); self.grid.setContentsMargins(0,0,0,0)
        self.grid.setHorizontalSpacing(20); self.grid.setVerticalSpacing(20)
        self.grid_wrap.hide()
        root.addWidget(self.grid_wrap, 1)

        # Panel derecho: se reutiliza para "Conectando..." y para "Log del servidor"
        self.right_stack = _RightPane(self)
        rlay = QVBoxLayout(right_panel); rlay.setContentsMargins(0,0,0,0); rlay.addWidget(self.right_stack)

        # Toolbar
        tb = QToolBar("Acciones")
        tb.setIconSize(QSize(28, 28))
        tb.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.addToolBar(tb)

        def _ico(fn, fallback="docker.png"):
            p = os.path.join("ui", "resources", "icons", fn)
            return QIcon(p if os.path.exists(p) else os.path.join("ui", "resources", fallback))

        act_connect = QAction(_ico("connect.png"), "Conectar…", self)
        act_connect.triggered.connect(self._connect_profile)
        tb.addAction(act_connect)

        act_new_profile = QAction(_ico("add_profile.png"), "Nuevo perfil…", self)
        act_new_profile.triggered.connect(self._create_profile_from_toolbar)
        tb.addAction(act_new_profile)

        self.btn_view = QToolButton(self); self.btn_view.setText("Vista")
        self.btn_view.setIcon(_ico("view.png")); self.btn_view.setPopupMode(QToolButton.InstantPopup)
        view_menu = QMenu(self)
        self.act_view_list  = view_menu.addAction("Lista",  lambda: self._set_view("list"))
        self.act_view_icons = view_menu.addAction("Iconos", lambda: self._set_view("icons"))
        self.btn_view.setMenu(view_menu); tb.addWidget(self.btn_view)

        self.btn_auto = QToolButton(self); self.btn_auto.setText("Actualización")
        self.btn_auto.setIcon(_ico("auto.png")); self.btn_auto.setPopupMode(QToolButton.InstantPopup)
        auto_menu = QMenu(self)
        self.auto_actions = {
            0:     auto_menu.addAction("Desactivada", lambda: self._set_autorefresh(0)),
            2000:  auto_menu.addAction("Cada 2 s",   lambda: self._set_autorefresh(2000)),
            5000:  auto_menu.addAction("Cada 5 s",   lambda: self._set_autorefresh(5000)),
            10000: auto_menu.addAction("Cada 10 s",  lambda: self._set_autorefresh(10000)),
            30000: auto_menu.addAction("Cada 30 s",  lambda: self._set_autorefresh(30000)),
        }
        for a in self.auto_actions.values(): a.setCheckable(True)
        self._sync_auto_checks()
        self.btn_auto.setMenu(auto_menu); tb.addWidget(self.btn_auto)

        act_refresh = QAction(_ico("refresh.png"), "Actualizar", self)
        act_refresh.triggered.connect(self.refresh_all)
        tb.addAction(act_refresh)

        act_server_log = QAction(_ico("hostlog.png"), "Log del servidor", self)
        act_server_log.triggered.connect(self._toggle_server_log_pane)
        tb.addAction(act_server_log)

        act_help = QAction(_ico("help.png"), "Ayuda", self)
        act_help.triggered.connect(self._show_help)
        tb.addAction(act_help)

        spacer = QWidget(); spacer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        tb.addWidget(spacer)

        self.btn_user = QToolButton(self)
        self.btn_user.setPopupMode(QToolButton.InstantPopup)
        self.btn_user.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self._reload_user_button_icon()
        menu_user = QMenu(self)
        menu_user.addAction("Ajustes…", self._open_settings)
        menu_user.addAction("Perfiles de conexión…", self._open_profiles)
        menu_user.addAction("Nuevo perfil…", self._create_profile_from_toolbar)
        menu_user.addSeparator()
        menu_user.addAction("Tema claro",  lambda: self._set_theme("light"))
        menu_user.addAction("Tema oscuro", lambda: self._set_theme("dark"))
        menu_user.addAction("Temas personalizados…", self._open_settings)
        self.btn_user.setMenu(menu_user)
        tb.addWidget(self.btn_user)

        # Status bar
        self.status = QStatusBar(); self.setStatusBar(self.status)
        self.status.showMessage("Listo")

        # Tema inicial
        self._apply_theme()

        # Auto-refresh
        if self.auto_refresh_on and self.auto_refresh_ms > 0:
            self.timer.start(self.auto_refresh_ms)

        # Double-click para icono docker (columna 1)
        self._icon_click_map = {}  # QLabel -> container name
        self._icon_click_filter = _IconDblClickFilter(self._on_icon_dblclicked)

    # ---------- User / Ajustes ----------
    def _reload_user_button_icon(self):
        # *** FIX: cuerpo bien indentado ***
        avatar = self.prefs.get("user_avatar")
        icon = None
        if avatar and os.path.exists(avatar):
            icon = QIcon(avatar)
        else:
            default_path = os.path.join("ui", "resources", "docker.png")
            icon = QIcon(default_path) if os.path.exists(default_path) else self.style().standardIcon(QStyle.SP_ComputerIcon)
        title = self.prefs.get("profile_display_name") or "Usuario"
        self.btn_user.setIcon(icon)
        self.btn_user.setText(title)

    def _open_settings(self):
        dlg = UserSettingsDialog(
            parent=self,
            prefs=self.prefs,
            on_change_theme=self._set_theme,                 # <- aplica preset claro/oscuro
            on_open_profiles=self._open_profiles,            # <- abre selector
            on_create_profile=self._create_profile_from_toolbar,  # <- crear perfil
            on_apply_colors=self._apply_custom_colors,       # <- aplica colores personalizados
            on_reset_col_widths=self._reset_col_widths,      # <- resetea anchos por columna
            get_active_profile=lambda: (self.current_profile or {})
        )
        dlg.setProperty("theme", self.theme)
        dlg.exec_()
        self._reload_user_button_icon()

    def _open_profiles(self):
        selector = ProfileSelector(self)
        selector.exec_()

    def _create_profile_from_toolbar(self):
        selector = ProfileSelector(self)
        if hasattr(selector, "create_new"):
            try:
                selector.create_new()
            except Exception:
                pass
        selector.exec_()
        # si el selector guarda, no necesitamos más; al conectar se usa la fuente del selector

    # ---------- Server log embebido ----------
    def _toggle_server_log_pane(self):
        if self.right_stack.mode == "server_log":
            self.right_stack.hide_pane()
            return
        if not self._ensure_connected():
            return
        self.right_stack.show_server_log("Cargando log…")
        # stream docker log del servicio si existe; si falla, fallback a docker events
        def worker():
            cmd_candidates = [
                "journalctl -u docker -f --no-pager",
                "sudo journalctl -u docker -f --no-pager",
                "docker events --format '{{json .}}'"
            ]
            err_txt = ""
            for cmd in cmd_candidates:
                try:
                    for chunk in self._stream_command(cmd):
                        self.right_stack.append_server_log(chunk)
                    return
                except Exception as e:
                    err_txt += f"\n[{cmd}] {e}"
            self.right_stack.append_server_log("\nNo se pudo seguir el log del servidor.\n" + err_txt)
        threading.Thread(target=worker, daemon=True).start()

    def _stream_command(self, cmd: str):
        # SSHClient no expone stream? re-evaluamos con 'exec_command' en bucle
        # Intento 1: si tiene stream_command
        if hasattr(self.ssh_client, "stream_command"):
            for chunk in self.ssh_client.stream_command(cmd):
                yield chunk
            return
        # Intento 2: pseudo-stream (repetir tail -n0 + sleep)
        if "journalctl" in cmd:
            base = cmd.replace("-f", "").strip()
            while True:
                out = self.ssh_client.exec_command(base + " -n 50")
                yield "".join(out)
                time.sleep(2)
        else:
            # docker events produce output continuo: hacemos poll corto
            while True:
                out = self.ssh_client.exec_command(cmd + " --since 5s")
                txt = "".join(out)
                if txt:
                    yield txt
                time.sleep(2)

    # ---------- Conexión / carga ----------
    def _ensure_connected(self):
        if not self.ssh_client:
            QMessageBox.warning(self, "Conexión", "No hay conexión SSH activa")
            return False
        return True

    def _connect_profile(self):
        selector = ProfileSelector(self)
        if hasattr(selector, "setWindowTitle"):
            selector.setWindowTitle("Selecciona o crea un perfil")
        # intenta añadir botón "nuevo" dentro del selector si lo soporta
        if selector.exec_() != QDialog.Accepted:
            return
        profile = None
        try:
            profile = selector.get_selected_profile()
        except Exception:
            profile = None
        if not isinstance(profile, dict):
            QMessageBox.warning(self, "Conectar", "No se ha seleccionado un perfil válido."); return
        host = (profile.get("host") or "").strip()
        user = (profile.get("user") or "").strip()
        if not host or not user:
            QMessageBox.warning(self, "Conectar", "El perfil no tiene host/usuario válidos."); return

        # Mostrar pane "Conectando…"
        self.right_stack.show_connecting(host, user)

        def worker():
            try:
                pwd_enc = profile.get("password", "")
                password = decrypt_password(pwd_enc) if pwd_enc else ""
                client = SSHClient(host, user, password)
                # Puedes exponer puertos/clave si tu SSHClient lo soporta:
                # client.port = profile.get("port", 22); client.key_path = profile.get("key_path", "")
                client.connect()
                self.ssh_client = client
                self.current_profile = profile
                # Nombre visible si no hay uno
                if not self.prefs.get("profile_display_name"):
                    self.prefs["profile_display_name"] = profile.get("name") or host
                    _save_prefs(self.prefs)
                self.status.showMessage(f"Conectado a {user}@{host}")
                self.right_stack.hide_pane()
                QTimer.singleShot(0, self.refresh_all)
            except Exception as e:
                self.right_stack.connecting_error(str(e))

        threading.Thread(target=worker, daemon=True).start()

    def refresh_all(self):
        if not self.ssh_client: return
        try:
            stdout = self.ssh_client.exec_command("docker ps -a --format '{{.Names}};{{.Image}};{{.Status}};{{.Ports}}'")
            rows = [line.strip().split(";") for line in stdout if line.strip()]
        except Exception as e:
            QMessageBox.critical(self, "docker ps", str(e)); return

        def is_running(status: str) -> bool: return "up" in (status or "").lower()

        parsed = []
        for r in rows:
            name = r[0]; image = r[1] if len(r) > 1 else ""
            status = r[2] if len(r) > 2 else ""
            ports = r[3] if len(r) > 3 else ""
            parsed.append((name, image, status, ports))

        self.rows_cache = sorted(parsed, key=lambda x: (
            0 if x[0] in self.favorites else 1,
            0 if is_running(x[2]) else 1,
            x[0].lower()
        ))
        self._render_table()
        self._render_grid()
        self._apply_filter()

    # ---------- Vistas / auto ----------
    def _set_view(self, mode: str):
        if mode == "list":
            self.table.show(); self.grid_wrap.hide()
        else:
            self.table.hide(); self.grid_wrap.show()

    def _set_autorefresh(self, ms: int):
        if ms <= 0:
            self.timer.stop(); self.auto_refresh_on = False
            self.status.showMessage("Auto: desactivada")
        else:
            self.auto_refresh_ms = ms; self.auto_refresh_on = True
            self.timer.start(self.auto_refresh_ms)
            self.status.showMessage(f"Auto: cada {ms/1000:.0f} s")
        self.prefs["auto_refresh_ms"] = self.auto_refresh_ms
        self.prefs["auto_refresh_on"] = self.auto_refresh_on
        _save_prefs(self.prefs)
        self._sync_auto_checks()

    def _sync_auto_checks(self):
        for ms, act in self.auto_actions.items():
            act.setChecked((not self.auto_refresh_on and ms == 0) or (self.auto_refresh_on and ms == self.auto_refresh_ms))

    # ---------- Persistencia tamaños ----------
    def _apply_row_height_from_prefs(self):
        row_h = int(self.prefs.get("row_height", 80))
        icon_pad = 8
        icon_w = max(24, row_h - icon_pad)
        self.table.verticalHeader().setDefaultSectionSize(row_h)
        self.table.setIconSize(QSize(icon_w, icon_w))
        # columnas fijas base (estado 0, icono 1)
        self.table.setColumnWidth(0, 36)
        self.table.setColumnWidth(1, row_h + 24)

    def _apply_saved_col_widths(self):
        widths: Dict[str, int] = self.prefs.get("table_col_widths", {})
        for i in range(6):
            w = widths.get(str(i))
            if w and i not in (0, 1):  # las 0 y 1 son fijas y calculadas
                self.table.setColumnWidth(i, int(w))

    def _save_col_width(self, logicalIndex: int, oldSize: int, newSize: int):
        if logicalIndex in (0, 1):  # no persistir fijas
            return
        self.prefs.setdefault("table_col_widths", {})[str(logicalIndex)] = int(newSize)
        _save_prefs(self.prefs)

    def _reset_col_widths(self):
        self.prefs["table_col_widths"] = {}
        _save_prefs(self.prefs)
        self._apply_saved_col_widths()

    # ---------- Render Lista ----------
    def _render_table(self):
        self._icon_click_map.clear()
        self.table.setRowCount(0)
        self.table.setRowCount(len(self.rows_cache))

        for i, (name, image, status, ports) in enumerate(self.rows_cache):
            is_up = "up" in (status or "").lower()

            # Col 0: estrella 16 + estado 16, centrados
            wrap = QWidget(); lay = QHBoxLayout(wrap); lay.setContentsMargins(0,0,0,0); lay.setSpacing(4)
            lay.addStretch(1)
            star_path = os.path.join("ui", "resources", "star.png")
            if name in self.favorites and os.path.exists(star_path):
                fav_lbl = QLabel(); fav_lbl.setAlignment(Qt.AlignCenter)
                fav_lbl.setPixmap(QIcon(star_path).pixmap(16,16))
                lay.addWidget(fav_lbl)
            st_lbl = QLabel(); st_lbl.setAlignment(Qt.AlignCenter)
            st_lbl.setPixmap(QIcon(os.path.join("ui","resources","green.png" if is_up else "red.png")).pixmap(16,16))
            lay.addWidget(st_lbl)
            lay.addStretch(1)
            self.table.setCellWidget(i, 0, wrap)

            # Col 1: icono docker (alto de fila). Doble-clic = cambiar icono
            ico_lbl = QLabel(); ico_lbl.setAlignment(Qt.AlignCenter)
            icon = self._icon_for_container(image, name)
            h = self.table.verticalHeader().defaultSectionSize()
            ico_lbl.setPixmap(icon.pixmap(h-8, h-8))
            self.table.setCellWidget(i, 1, ico_lbl)

            ico_lbl.setProperty("container_name", name)
            ico_lbl.installEventFilter(self._icon_click_filter)
            self._icon_click_map[ico_lbl] = name

            # Col 2-5
            self.table.setItem(i, 2, QTableWidgetItem(name))
            self.table.setItem(i, 3, QTableWidgetItem(image))
            self.table.setItem(i, 4, QTableWidgetItem(status))
            self.table.setItem(i, 5, QTableWidgetItem(ports))

    # ---------- Render Grid ----------
    def _render_grid(self):
        for i in reversed(range(self.grid.count())):
            w = self.grid.itemAt(i).widget()
            if w: w.deleteLater()
        for idx, (name, image, status, ports) in enumerate(self.rows_cache):
            self.grid.addWidget(self._make_card(name, image, status, ports), idx // 4, idx % 4)

    def _make_card(self, name, image, status, ports):
        card = QFrame(); card.setObjectName("containerCard")
        card.setStyleSheet("""
            QFrame#containerCard { border-radius:16px; border:1px solid rgba(0,0,0,0.08); background:#ffffff; }
            QFrame#containerCard:hover { border:1px solid #4b9fff; box-shadow: 0 6px 18px rgba(0,0,0,0.06); }
            QMainWindow[theme="dark"] QFrame#containerCard { background:#252a32; border:1px solid #3b4252; }
            QMainWindow[theme="dark"] QFrame#containerCard:hover { background:#2b313b; border:1px solid #569cd6; }
            QLabel { font-size:15px; }
        """)
        lay = QVBoxLayout(card); lay.setContentsMargins(18,18,18,18); lay.setSpacing(10)

        is_up = "up" in (status or "").lower()
        st = QLabel(); st.setAlignment(Qt.AlignCenter)
        st.setPixmap(QIcon(os.path.join("ui","resources","green.png" if is_up else "red.png")).pixmap(16,16))

        icon_lbl = QLabel(); icon_lbl.setAlignment(Qt.AlignCenter)
        icon = self._icon_for_container(image, name)
        icon_lbl.setPixmap(icon.pixmap(88,88))

        # Título + botón ▼ para icono
        title_row = QHBoxLayout(); title_row.addStretch(1)
        name_lbl = QLabel(name); name_lbl.setAlignment(Qt.AlignCenter)
        name_lbl.setStyleSheet("font-weight:600; font-size:16px;")
        btn_more = QToolButton(); btn_more.setText("▼"); btn_more.setToolButtonStyle(Qt.ToolButtonTextOnly)
        menu = QMenu(btn_more); act_set = menu.addAction("Cambiar icono…"); act_clear = menu.addAction("Quitar icono")
        btn_more.setMenu(menu); btn_more.setPopupMode(QToolButton.InstantPopup)
        def _menu_handler(action):
            if action == act_set: self._set_custom_icon(name)
            elif action == act_clear:
                if name in self.container_icons:
                    del self.container_icons[name]; self.prefs["container_icons"] = self.container_icons; _save_prefs(self.prefs); self.refresh_all()
        menu.triggered.connect(_menu_handler)
        title_row.addWidget(name_lbl); title_row.addSpacing(6); title_row.addWidget(btn_more); title_row.addStretch(1)

        def open_inspector(_): self._open_inspector(name, image, status, ports)
        card.mouseDoubleClickEvent = open_inspector

        def context_menu_event(e): self._show_context_menu_global(name, image, status, ports, e.globalPos())
        card.contextMenuEvent = context_menu_event

        lay.addWidget(st); lay.addWidget(icon_lbl); lay.addLayout(title_row)
        return card

    # ---------- Filtro ----------
    def _apply_filter(self):
        q = (self.filter_edit.text() or "").lower()
        for r in range(self.table.rowCount()):
            visible = False
            for c in (2,3,4,5):
                it = self.table.item(r, c)
                if it and q in it.text().lower(): visible = True; break
            self.table.setRowHidden(r, not visible)

    # ---------- Contextual ----------
    def _context_menu(self, pos: QPoint):
        it = self.table.itemAt(pos)
        if not it: return
        r = it.row()
        name = self.table.item(r, 2).text()
        image = self.table.item(r, 3).text()
        status = self.table.item(r, 4).text()
        ports = self.table.item(r, 5).text()
        self._show_context_menu_global(name, image, status, ports, self.table.viewport().mapToGlobal(pos))

    def _show_context_menu_global(self, name, image, status, ports, global_pos):
        menu = QMenu(self)
        act_open = menu.addAction("Abrir inspector")
        act_browser = menu.addAction("Abrir en navegador")
        fav_label = "Añadir a favoritos" if name not in self.favorites else "Quitar de favoritos"
        act_fav = menu.addAction(fav_label)
        menu.addSeparator()
        act_set_icon = menu.addAction("Cambiar icono…")
        act_clear_icon = menu.addAction("Quitar icono")
        menu.addSeparator()
        act_start = menu.addAction("Iniciar")
        act_stop = menu.addAction("Parar")
        act_restart = menu.addAction("Reiniciar")

        chosen = menu.exec_(global_pos)
        if chosen == act_open:
            self._open_inspector(name, image, status, ports)
        elif chosen == act_browser:
            self._open_in_browser(ports)
        elif chosen == act_fav:
            if name in self.favorites: self.favorites.remove(name)
            else: self.favorites.add(name)
            self.prefs["favorites"] = list(self.favorites); _save_prefs(self.prefs); self.refresh_all()
        elif chosen == act_set_icon:
            self._set_custom_icon(name)
        elif chosen == act_clear_icon:
            if name in self.container_icons:
                del self.container_icons[name]; self.prefs["container_icons"] = self.container_icons; _save_prefs(self.prefs); self.refresh_all()
        elif chosen in (act_start, act_stop, act_restart):
            action = "start" if chosen == act_start else "stop" if chosen == act_stop else "restart"
            self._container_action(name, action)

    # ---------- Inspector / utilidades ----------
    def _double_click_open(self, it: QTableWidgetItem):
        r = it.row()
        self._open_inspector(
            self.table.item(r, 2).text(),
            self.table.item(r, 3).text(),
            self.table.item(r, 4).text(),
            self.table.item(r, 5).text(),
        )

    def _open_inspector(self, name, image, status, ports):
        if not self._ensure_connected(): return
        dlg = ContainerInspector(
            ssh_client=self.ssh_client,
            profile_host=self.current_profile["host"] if self.current_profile else "localhost",
            name=name, image=image, status=status, ports=ports,
            icon=self._icon_for_container(image, name),
            parent=self
        )
        try: dlg.resize(900, 680)
        except Exception: pass
        # Menú ▼ dentro del inspector si expone set_more_menu
        if hasattr(dlg, "set_more_menu"):
            m = QMenu(dlg)
            act_set = m.addAction("Cambiar icono…")
            act_clear = m.addAction("Quitar icono")
            def _h(a):
                if a == act_set: self._set_custom_icon(name)
                elif a == act_clear:
                    if name in self.container_icons:
                        del self.container_icons[name]; self.prefs["container_icons"] = self.container_icons; _save_prefs(self.prefs); self.refresh_all()
            m.triggered.connect(_h)
            try: dlg.set_more_menu(m)  # el inspector dibuja el triangulito ▼ y usa este menú
            except Exception: pass
        # auto-scroll log si lo soporta
        if hasattr(dlg, "stick_log_bottom"):
            try: dlg.stick_log_bottom()
            except Exception: pass
        if hasattr(dlg, "start_follow_logs"):
            try: dlg.start_follow_logs()
            except Exception: pass
        dlg.exec_()

    def _icon_for_container(self, image: str, name: str) -> QIcon:
        custom = self.container_icons.get(name)
        if custom and os.path.exists(custom): return QIcon(custom)
        base_dir = os.path.join("ui", "resources", "containers")
        def exists(fn): return os.path.exists(os.path.join(base_dir, fn))
        def slug(s): return re.sub(r"[^a-z0-9_\-]", "_", (s or "").lower())
        candidates = []
        if name: candidates.append(f"{slug(name)}.png")
        repo = (image.split(":")[0] if ":" in image else image) or ""
        parts = repo.split("/")
        org, rep = ("library", parts[0]) if len(parts) == 1 else (parts[-2], parts[-1])
        candidates += [f"{slug(rep)}.png", f"{slug(org)}_{slug(rep)}.png"]
        for fn in candidates:
            if exists(fn): return QIcon(os.path.join(base_dir, fn))
        return QIcon(os.path.join("ui", "resources", "docker.png"))

    def _on_icon_dblclicked(self, label: QLabel):
        name = self._icon_click_map.get(label)
        if not name: return
        self._set_custom_icon(name)

    def _set_custom_icon(self, name: str):
        fn, _ = QFileDialog.getOpenFileName(self, f"Icono para {name}", os.path.expanduser("~"), "Imágenes (*.png *.jpg *.jpeg *.webp)")
        if not fn: return
        self.container_icons[name] = fn
        self.prefs["container_icons"] = self.container_icons
        _save_prefs(self.prefs)
        self.refresh_all()

    def _first_host_port(self, ports: str):
        if not ports: return None
        parts = [p.strip() for p in ports.split(",") if p.strip()]
        if not parts: return None
        m = re.search(r"(?:(?:\[.*\]|[^:,\s]+):)?(?P<hostport>\d+)->\d+/(?:tcp|udp)", parts[0])
        return m.group("hostport") if m else None

    def _open_in_browser(self, ports: str):
        host = self.current_profile["host"] if self.current_profile else "localhost"
        p = self._first_host_port(ports)
        if not p:
            QMessageBox.warning(self, "Navegador", "Este contenedor no expone puertos"); return
        try:
            webbrowser.open(f"http://{host}:{p}")
        except Exception:
            QMessageBox.warning(self, "Navegador", "No se pudo abrir la URL")

    def _container_action(self, name, action):
        if not self._ensure_connected(): return
        try:
            self.ssh_client.exec_command(f"docker {action} {name}")
            self.status.showMessage(f"{action.upper()} en {name}")
            threading.Thread(target=self._delayed_refresh, daemon=True).start()
        except Exception as e:
            QMessageBox.critical(self, "Acción docker", str(e))

    def _delayed_refresh(self):
        time.sleep(0.8)
        QTimer.singleShot(0, self.refresh_all)

    def _show_help(self):
        QMessageBox.information(self, "Ayuda",
            "• Arriba: filtro, vista (Lista/Iconos), auto-actualización, log del servidor.\n"
            "• Lista: columna 0 muestra favorito (★) y estado (●). Columna 1: icono Docker.\n"
            "  - Doble clic en el icono Docker para cambiar el icono del contenedor.\n"
            "  - Menú contextual con iniciar/parar/reiniciar, favorito, iconos, abrir navegador.\n"
            "• Usuario (arriba derecha): Ajustes, Perfiles y Temas personalizados.\n"
            "• Ajustes: Tema Claro/Oscuro (presets), editor de colores para crear temas nuevos,\n"
            "  altura de filas y reset de anchos de columnas.\n"
            "• Log del servidor: panel derecho con seguimiento en vivo."
        )

    # ---------- Tema ----------
    def _build_stylesheet(self):
        c = dict(self.theme_colors)
        for k, v in {"bg":"#fafbfd","surface":"#ffffff","text":"#1a1d21","muted":"#6b7785","accent":"#4b9fff"}.items():
            c.setdefault(k, v)
        if self.theme == "dark":
            bg = "#1f2329"; surface = "#252a32"; text = "#e6e6e6"; accent = c["accent"]
        else:
            bg = c["bg"]; surface = c["surface"]; text = c["text"]; accent = c["accent"]

        return f"""
            QMainWindow[theme="{self.theme}"] {{ background-color: {bg}; color: {text}; }}
            QToolBar {{ background: {surface}; border: none; }}
            QLineEdit {{
                background: {surface}; color: {text};
                border: 1px solid #dfe3ea; border-radius: 10px; padding: 10px 12px; font-size:15px;
            }}
            QFrame#containerCard {{ background: {surface}; border: 1px solid #e8eef7; border-radius: 16px; }}
            QToolButton, QPushButton {{ font-size: 15px; padding: 6px 10px; }}
            QHeaderView::section {{ background: #f5f7fb; color: {text}; }}
            QMainWindow[theme="dark"] QHeaderView::section {{ background: #2b313b; color: {text}; }}
            QMenu {{ background: {surface}; color: {text}; }}
            QWidget#rightPanel {{ background: {surface}; }}
        """

    def _apply_theme(self):
        self.setProperty("theme", self.theme)
        QApplication.instance().setStyleSheet(self._build_stylesheet())

    def _apply_custom_colors(self, colors: dict):
        self.theme_colors.update(colors or {})
        self.prefs["theme_colors"] = self.theme_colors
        _save_prefs(self.prefs)
        self._apply_theme()

    def _set_theme(self, mode: str):
        """Aplica el preset 'light' o 'dark' (no editables) y persiste."""
        if mode == "dark":
            self.theme = "dark"
            self.theme_colors = {
                "bg": "#1f2329",
                "surface": "#252a32",
                "text": "#e6e6e6",
                "muted": "#6b7785",
                "accent": "#569cd6",
            }
        else:
            self.theme = "light"
            self.theme_colors = {
                "bg": "#fafbfd",
                "surface": "#ffffff",
                "text": "#1a1d21",
                "muted": "#6b7785",
                "accent": "#4b9fff",
            }
        # Persistir y aplicar inmediatamente
        self.prefs["theme"] = self.theme
        self.prefs["theme_colors"] = self.theme_colors
        _save_prefs(self.prefs)
        self._apply_theme()

    # (Método _poll_server_events queda sin uso aquí; si lo necesitas, muévelo a tu dialog de logs)


# ---------- Event filters ----------
class _IconDblClickFilter(QObject):
    def __init__(self, callback): super().__init__(); self.callback = callback
    def eventFilter(self, obj: QObject, event) -> bool:
        if isinstance(obj, QLabel) and isinstance(event, QMouseEvent):
            if event.type() == QEvent.MouseButtonDblClick and event.button() == Qt.LeftButton:
                self.callback(obj); return True
        return False


# ---------- Panel derecho (Connecting / Server log) ----------
class _RightPane(QWidget):
    mode = None  # "connecting" | "server_log" | None
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumWidth(360)
        self.v = QVBoxLayout(self); self.v.setContentsMargins(10,10,10,10); self.v.setSpacing(8)

        self.header = QHBoxLayout()
        self.title = QLabel("Panel"); self.title.setStyleSheet("font-weight:700; font-size:15px;")
        self.btn_close = QToolButton(); self.btn_close.setText("Ocultar"); self.btn_close.clicked.connect(self.hide_pane)
        self.header.addWidget(self.title); self.header.addStretch(1); self.header.addWidget(self.btn_close)

        self.stack = QVBoxLayout(); self.stack.setSpacing(8)

        self.v.addLayout(self.header); self.v.addLayout(self.stack)

        # Widgets compartidos
        self.conn_widget = QWidget()
        c_l = QVBoxLayout(self.conn_widget); c_l.setContentsMargins(0,0,0,0); c_l.setSpacing(4)
        c_l.addWidget(QLabel("Conectando…"))
        c_l.addWidget(QLabel("Espere por favor."), 0, Qt.AlignHCenter)

        # *** FIX: estas líneas debían estar indentadas dentro de __init__ ***
        self.progress = QLabel()
        self.progress.setAlignment(Qt.AlignCenter)
        spin_path = os.path.join("ui", "resources", "spinner.png")
        pix = QPixmap(spin_path) if os.path.exists(spin_path) else QPixmap()
        if not pix.isNull():
            self.progress.setPixmap(pix.scaled(32, 32, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        else:
            # Fallback a icono estándar si no existe spinner.png
            icon = self.style().standardIcon(QStyle.SP_BrowserReload)
            self.progress.setPixmap(icon.pixmap(32, 32))

        c_l.addWidget(self.progress, 0, Qt.AlignHCenter)
        self.conn_widget.setVisible(False)
        self.stack.addWidget(self.conn_widget)

        # Log
        self.log_widget = QTextEdit(); self.log_widget.setReadOnly(True); self.log_widget.setObjectName("serverLog")
        self.log_widget.setStyleSheet("""
            QTextEdit#serverLog {
                background: #f5f7fb; color: #1a1d21;
                border: 1px solid #dfe3ea; border-radius: 10px;
                padding: 10px; font-size: 14px;
            }
            QMainWindow[theme="dark"] QTextEdit#serverLog {
                background: #1f2329; color: #e6e6e6;
                border: 1px solid #3b4252;
            }
        """)
        self.stack.addWidget(self.log_widget)

        # Oculto por defecto
        self.hide_pane()

    def show_connecting(self, host, user):
        self.mode = "connecting"
        self.conn_widget.setVisible(True)
        self.log_widget.setVisible(False)
        self.title.setText(f"Conectando a {user}@{host}")
        self.btn_close.setVisible(True)
        self.show()

    def show_server_log(self, initial_text=""):
        self.mode = "server_log"
        self.conn_widget.setVisible(False)
        self.log_widget.setVisible(True)
        self.log_widget.clear()
        if initial_text:
            self.log_widget.append(initial_text)
        self.title.setText("Log del servidor")
        self.btn_close.setVisible(True)
        self.show()

    def hide_pane(self):
        self.mode = None
        self.conn_widget.setVisible(False)
        self.log_widget.setVisible(False)
        self.hide()

    def append_server_log(self, text: str):
        if not self.log_widget.isVisible():
            return
        # mover cursor al final y añadir texto
        cur = self.log_widget.textCursor()
        cur.movePosition(cur.End)
        self.log_widget.setTextCursor(cur)
        self.log_widget.insertPlainText(text)
        # autoscroll si ya estaba al final
        sb = self.log_widget.verticalScrollBar()
        sb.setValue(sb.maximum())

    def connecting_error(self, msg: str):
        self.append_server_log(f"\nError: {msg}\n")
        self.btn_close.setVisible(True)
