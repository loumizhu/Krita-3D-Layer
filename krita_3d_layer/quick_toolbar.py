"""
Quick Actions Toolbar and Customizer for Krita 3D Layer.
Provides a customizable mini-toolbar directly beneath the 3D Viewport
with quick shortcuts to most-used features, custom button styling, and presets.
"""

import os
import json
from PyQt5.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QPushButton, QLabel,
    QScrollArea, QFrame, QDialog, QListWidget, QListWidgetItem,
    QComboBox, QColorDialog, QLineEdit, QMessageBox, QInputDialog,
    QSizePolicy, QLayout, QSpinBox
)
from PyQt5.QtGui import QColor, QFont
from PyQt5.QtCore import Qt, pyqtSignal, QPoint, QRect, QSize


# =====================================================================
# ACTION CATALOG
# =====================================================================
ACTION_CATALOG = {
    # Primitives & Drawing
    "draw_box": {
        "name": "Draw Box Primitive",
        "icon": "✏️",
        "label": "Draw Box",
        "tooltip": "Draw a 3D box directly on canvas sketch (infers perspective & FOV)",
        "color": "#065f46",
        "text_color": "#a7f3d0",
    },
    "ground_4p": {
        "name": "Ground Rectangle (4-Point)",
        "icon": "📐",
        "label": "Ground 4P",
        "tooltip": "Calibrate perspective and ground plane from 4 canvas pins",
        "color": "#1e3a5f",
        "text_color": "#93c5fd",
    },
    "ground_5p": {
        "name": "Ground Rectangle + Height (5-Point)",
        "icon": "📍",
        "label": "Ground 5P",
        "tooltip": "Calibrate ground plane + vertical height from 5 canvas pins",
        "color": "#3b0764",
        "text_color": "#e9d5ff",
    },
    "prim_box": {
        "name": "Add Box Primitive",
        "icon": "📦",
        "label": "Box",
        "tooltip": "Load or create a 3D Box primitive resting on ground",
        "color": "#1e293b",
        "text_color": "#e2e8f0",
    },
    "prim_cyl": {
        "name": "Add Cylinder Primitive",
        "icon": "🛢️",
        "label": "Cylinder",
        "tooltip": "Load or create a 3D Cylinder primitive resting on ground",
        "color": "#1e293b",
        "text_color": "#e2e8f0",
    },
    "prim_sph": {
        "name": "Add Sphere Primitive",
        "icon": "🔮",
        "label": "Sphere",
        "tooltip": "Load or create a 3D Sphere primitive",
        "color": "#1e293b",
        "text_color": "#e2e8f0",
    },
    "prim_pyr": {
        "name": "Add Pyramid Primitive",
        "icon": "📐",
        "label": "Pyramid",
        "tooltip": "Load or create a 3D Pyramid primitive resting on ground",
        "color": "#1e293b",
        "text_color": "#e2e8f0",
    },
    "prim_cone": {
        "name": "Add Cone Primitive",
        "icon": "🍦",
        "label": "Cone",
        "tooltip": "Load or create a 3D Cone primitive resting on ground",
        "color": "#1e293b",
        "text_color": "#e2e8f0",
    },
    "prim_plane": {
        "name": "Add Plane Primitive",
        "icon": "🏁",
        "label": "Plane",
        "tooltip": "Load or create a 3D Ground Plane primitive",
        "color": "#1e293b",
        "text_color": "#e2e8f0",
    },
    "prim_room": {
        "name": "Add Room Corner (3 Planes)",
        "icon": "🏠",
        "label": "Room 3P",
        "tooltip": "Load or create a 3-plane room interior primitive (floor + 2 walls with section grids)",
        "color": "#1e293b",
        "text_color": "#fed7aa",
    },
    "import_file": {
        "name": "Import 3D Model File",
        "icon": "📁",
        "label": "Import",
        "tooltip": "Import OBJ, STL, GLB, or glTF 3D model",
        "color": "#1f2937",
        "text_color": "#f3f4f6",
    },
    "clear_model": {
        "name": "No Model (Grid Only)",
        "icon": "🌐",
        "label": "Grid Only",
        "tooltip": "Clear 3D model and use perspective grid guides only",
        "color": "#1f2937",
        "text_color": "#cbd5e1",
    },

    # Camera Lenses / FOV
    "lens_24": {
        "name": "Wide Lens (24mm / 73° FOV)",
        "icon": "📷",
        "label": "24mm",
        "tooltip": "Set 24mm wide angle camera lens (73° FOV)",
        "color": "#1e1e2e",
        "text_color": "#38bdf8",
    },
    "lens_35": {
        "name": "Street Lens (35mm / 54° FOV)",
        "icon": "📷",
        "label": "35mm",
        "tooltip": "Set 35mm standard wide camera lens (54° FOV)",
        "color": "#1e1e2e",
        "text_color": "#38bdf8",
    },
    "lens_50": {
        "name": "Normal Lens (50mm / 39° FOV)",
        "icon": "📷",
        "label": "50mm",
        "tooltip": "Set 50mm human-eye camera lens (39° FOV)",
        "color": "#1e1e2e",
        "text_color": "#38bdf8",
    },
    "lens_85": {
        "name": "Portrait Lens (85mm / 24° FOV)",
        "icon": "📷",
        "label": "85mm",
        "tooltip": "Set 85mm portrait telephoto camera lens (24° FOV)",
        "color": "#1e1e2e",
        "text_color": "#38bdf8",
    },

    # Camera Views & Framing
    "frame_obj": {
        "name": "Frame Object in View",
        "icon": "🎯",
        "label": "Frame",
        "tooltip": "Auto-fit and frame current 3D object in the viewport",
        "color": "#1e293b",
        "text_color": "#38bdf8",
    },
    "center_model": {
        "name": "Center Camera on Model",
        "icon": "🔍",
        "label": "Center",
        "tooltip": "Center camera target directly on 3D model",
        "color": "#1e293b",
        "text_color": "#e2e8f0",
    },
    "center_origin": {
        "name": "Target Ground Origin (0,0)",
        "icon": "🌐",
        "label": "Origin",
        "tooltip": "Reset camera orbit target to ground origin (0,0,0)",
        "color": "#1e293b",
        "text_color": "#e2e8f0",
    },
    "view_front": {
        "name": "Front View Angle",
        "icon": "👀",
        "label": "Front",
        "tooltip": "Snap camera to Front View (Yaw 0°, Pitch 0°)",
        "color": "#1e293b",
        "text_color": "#e2e8f0",
    },
    "view_34": {
        "name": "Studio 3/4 View Angle",
        "icon": "📐",
        "label": "3/4 View",
        "tooltip": "Snap camera to classic 3/4 Studio View (Yaw 45°, Pitch 25°)",
        "color": "#1e293b",
        "text_color": "#e2e8f0",
    },
    "view_top": {
        "name": "Top-Down View Angle",
        "icon": "⬇️",
        "label": "Top",
        "tooltip": "Snap camera to Top-Down View (Yaw 0°, Pitch 89°)",
        "color": "#1e293b",
        "text_color": "#e2e8f0",
    },
    "view_side": {
        "name": "Side Profile View Angle",
        "icon": "➡️",
        "label": "Side",
        "tooltip": "Snap camera to Side Profile View (Yaw 90°, Pitch 0°)",
        "color": "#1e293b",
        "text_color": "#e2e8f0",
    },
    "reset_cam": {
        "name": "Reset Camera",
        "icon": "🔄",
        "label": "Reset Cam",
        "tooltip": "Reset camera distance, rotation, pan and FOV to defaults",
        "color": "#3f1d2a",
        "text_color": "#fca5a5",
    },

    # Shading Styles
    "style_shaded_wire": {
        "name": "Shading: Shaded + Wireframe",
        "icon": "🧊",
        "label": "Shd+Wire",
        "tooltip": "Switch render style to Shaded + Wireframe",
        "color": "#1e293b",
        "text_color": "#93c5fd",
    },
    "style_shaded": {
        "name": "Shading: Shaded Smooth",
        "icon": "🎨",
        "label": "Shaded",
        "tooltip": "Switch render style to Shaded",
        "color": "#1e293b",
        "text_color": "#93c5fd",
    },
    "style_wire": {
        "name": "Shading: Wireframe Only",
        "icon": "🕸️",
        "label": "Wireframe",
        "tooltip": "Switch render style to Wireframe lines only",
        "color": "#1e293b",
        "text_color": "#93c5fd",
    },
    "style_silhouette": {
        "name": "Shading: Silhouette Flat",
        "icon": "👤",
        "label": "Silhouette",
        "tooltip": "Switch render style to Flat Silhouette",
        "color": "#1e293b",
        "text_color": "#93c5fd",
    },

    # Perspective Grid
    "toggle_grid_vp": {
        "name": "Toggle Viewport Grid",
        "icon": "🏁",
        "label": "VP Grid",
        "tooltip": "Toggle perspective grid visibility in viewport",
        "color": "#1e293b",
        "text_color": "#fef08a",
    },
    "toggle_grid_canvas": {
        "name": "Toggle Canvas Grid",
        "icon": "🎨",
        "label": "Canvas Grid",
        "tooltip": "Toggle perspective grid rendering on Krita canvas layer",
        "color": "#1e293b",
        "text_color": "#fef08a",
    },

    # Sync & Stamp
    "stamp_now": {
        "name": "Stamp Scene onto Canvas",
        "icon": "⚡",
        "label": "Stamp",
        "tooltip": "Immediately stamp current 3D view and grid onto active Krita layer",
        "color": "#1d4ed8",
        "text_color": "#ffffff",
    },
    "toggle_live": {
        "name": "Toggle Live Canvas Sync",
        "icon": "🔄",
        "label": "Live Sync",
        "tooltip": "Enable or disable live synchronization to Krita canvas",
        "color": "#064e3b",
        "text_color": "#6ee7b7",
    },
    "pick_model_color": {
        "name": "Model Material Color",
        "icon": "🎨",
        "label": "Color",
        "tooltip": "Change 3D model diffuse material color",
        "color": "#334155",
        "text_color": "#ffffff",
    },
    "reset_xform": {
        "name": "Reset Object Transform",
        "icon": "📍",
        "label": "Rst Xform",
        "tooltip": "Reset object position, rotation, and scale to defaults",
        "color": "#1e293b",
        "text_color": "#cbd5e1",
    },
}

# =====================================================================
# BUILTIN PRESETS
# =====================================================================
TOOLBAR_PRESETS = {
    "Artist Essentials": [
        {"action_id": "draw_box", "color": "#065f46", "text_color": "#a7f3d0"},
        {"action_id": "ground_5p", "color": "#4c1d95", "text_color": "#e9d5ff"},
        {"action_id": "frame_obj", "color": "#1e293b", "text_color": "#38bdf8"},
        {"action_id": "lens_50", "color": "#1e1e2e", "text_color": "#38bdf8"},
        {"action_id": "stamp_now", "color": "#1d4ed8", "text_color": "#ffffff"},
        {"action_id": "toggle_live", "color": "#064e3b", "text_color": "#6ee7b7"},
    ],
    "Perspective & Ground": [
        {"action_id": "ground_4p", "color": "#1e3a5f", "text_color": "#93c5fd"},
        {"action_id": "ground_5p", "color": "#4c1d95", "text_color": "#e9d5ff"},
        {"action_id": "draw_box", "color": "#065f46", "text_color": "#a7f3d0"},
        {"action_id": "toggle_grid_vp", "color": "#1e293b", "text_color": "#fef08a"},
        {"action_id": "view_front", "color": "#1e293b", "text_color": "#e2e8f0"},
        {"action_id": "view_34", "color": "#1e293b", "text_color": "#e2e8f0"},
        {"action_id": "view_top", "color": "#1e293b", "text_color": "#e2e8f0"},
    ],
    "Primitives & Shapes": [
        {"action_id": "prim_box", "color": "#1e293b", "text_color": "#e2e8f0"},
        {"action_id": "prim_cyl", "color": "#1e293b", "text_color": "#e2e8f0"},
        {"action_id": "prim_sph", "color": "#1e293b", "text_color": "#e2e8f0"},
        {"action_id": "prim_pyr", "color": "#1e293b", "text_color": "#e2e8f0"},
        {"action_id": "draw_box", "color": "#065f46", "text_color": "#a7f3d0"},
        {"action_id": "ground_5p", "color": "#4c1d95", "text_color": "#e9d5ff"},
        {"action_id": "frame_obj", "color": "#1e293b", "text_color": "#38bdf8"},
    ],
    "Camera Director": [
        {"action_id": "lens_24", "color": "#1e1e2e", "text_color": "#38bdf8"},
        {"action_id": "lens_35", "color": "#1e1e2e", "text_color": "#38bdf8"},
        {"action_id": "lens_50", "color": "#1e1e2e", "text_color": "#38bdf8"},
        {"action_id": "lens_85", "color": "#1e1e2e", "text_color": "#38bdf8"},
        {"action_id": "frame_obj", "color": "#1e293b", "text_color": "#38bdf8"},
        {"action_id": "center_origin", "color": "#1e293b", "text_color": "#e2e8f0"},
        {"action_id": "view_34", "color": "#1e293b", "text_color": "#e2e8f0"},
        {"action_id": "reset_cam", "color": "#3f1d2a", "text_color": "#fca5a5"},
    ],
    "Reference & Inking": [
        {"action_id": "style_shaded_wire", "color": "#1e293b", "text_color": "#93c5fd"},
        {"action_id": "style_wire", "color": "#1e293b", "text_color": "#93c5fd"},
        {"action_id": "style_silhouette", "color": "#1e293b", "text_color": "#93c5fd"},
        {"action_id": "pick_model_color", "color": "#334155", "text_color": "#ffffff"},
        {"action_id": "stamp_now", "color": "#1d4ed8", "text_color": "#ffffff"},
        {"action_id": "toggle_live", "color": "#064e3b", "text_color": "#6ee7b7"},
    ]
}


def get_toolbar_presets_file():
    appdata = os.environ.get("APPDATA")
    if appdata and os.path.exists(appdata):
        kdir = os.path.join(appdata, "krita")
        os.makedirs(kdir, exist_ok=True)
        return os.path.join(kdir, "krita_3d_layer_toolbars.json")
    hdir = os.path.expanduser("~/.local/share/krita")
    os.makedirs(hdir, exist_ok=True)
    return os.path.join(hdir, "krita_3d_layer_toolbars.json")


def load_all_toolbar_presets():
    presets = dict(TOOLBAR_PRESETS)
    p_path = get_toolbar_presets_file()
    if os.path.exists(p_path):
        try:
            with open(p_path, "r", encoding="utf-8") as f:
                user_p = json.load(f)
                if isinstance(user_p, dict):
                    presets.update(user_p)
        except Exception:
            pass
    return presets


def save_user_toolbar_preset(name, items_list):
    p_path = get_toolbar_presets_file()
    user_p = {}
    if os.path.exists(p_path):
        try:
            with open(p_path, "r", encoding="utf-8") as f:
                loaded = json.load(f)
                if isinstance(loaded, dict):
                    user_p = loaded
        except Exception:
            pass
    user_p[name] = items_list
    with open(p_path, "w", encoding="utf-8") as f:
        json.dump(user_p, f, indent=2)


def delete_user_toolbar_preset(name):
    p_path = get_toolbar_presets_file()
    if os.path.exists(p_path):
        try:
            with open(p_path, "r", encoding="utf-8") as f:
                user_p = json.load(f)
            if name in user_p:
                del user_p[name]
                with open(p_path, "w", encoding="utf-8") as f:
                    json.dump(user_p, f, indent=2)
                return True
        except Exception:
            pass
    return False


# =====================================================================
# QUICK ACTIONS TOOLBAR WIDGET
# =====================================================================
# FLOW LAYOUT (Auto-wrapping horizontal layout)
# =====================================================================
class FlowLayout(QLayout):
    """
    Layout that arranges items left-to-right and wraps to the next row
    when items exceed available width. Ensures buttons never get clipped.
    """
    def __init__(self, parent=None, margin=0, h_spacing=3, v_spacing=3):
        super().__init__(parent)
        self.setContentsMargins(margin, margin, margin, margin)
        self._h_spacing = h_spacing
        self._v_spacing = v_spacing
        self._item_list = []

    def __del__(self):
        item = self.takeAt(0)
        while item:
            item = self.takeAt(0)

    def addItem(self, item):
        self._item_list.append(item)

    def count(self):
        return len(self._item_list)

    def itemAt(self, index):
        if 0 <= index < len(self._item_list):
            return self._item_list[index]
        return None

    def takeAt(self, index):
        if 0 <= index < len(self._item_list):
            return self._item_list.pop(index)
        return None

    def expandingDirections(self):
        return Qt.Orientations(0)

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        return self._do_layout(QRect(0, 0, width, 0), True)

    def setGeometry(self, rect):
        super().setGeometry(rect)
        self._do_layout(rect, False)

    def sizeHint(self):
        w = 280
        p = self.parentWidget()
        if p and p.width() > 50:
            w = p.width()
        h = self.heightForWidth(w)
        return QSize(w, max(26, h))

    def minimumSize(self):
        w = 280
        p = self.parentWidget()
        if p and p.width() > 50:
            w = p.width()
        h = self.heightForWidth(w)
        return QSize(60, max(24, h))

    def _do_layout(self, rect, test_only):
        left, top, right, bottom = self.getContentsMargins()
        effective_rect = rect.adjusted(left, top, -right, -bottom)
        x = effective_rect.x()
        y = effective_rect.y()
        line_height = 0

        for item in self._item_list:
            wid = item.widget()
            if wid and wid.isHidden():
                continue
            item_size = item.sizeHint()
            next_x = x + item_size.width() + self._h_spacing

            if next_x - self._h_spacing > effective_rect.right() and line_height > 0:
                x = effective_rect.x()
                y = y + line_height + self._v_spacing
                next_x = x + item_size.width() + self._h_spacing
                line_height = 0

            if not test_only:
                item.setGeometry(QRect(QPoint(x, y), item_size))

            x = next_x
            line_height = max(line_height, item_size.height())

        return y + line_height - rect.y() + bottom


# =====================================================================
# QUICK ACTIONS TOOLBAR WIDGET
# =====================================================================
class QuickActionsToolbar(QWidget):
    """
    Mini toolbar hosted directly below the Viewport resize handle or top of controls.
    Displays configured quick shortcut buttons in an auto-wrapping flow layout
    so buttons are neatly aligned, never clipped, and wrap to new lines smoothly.
    Supports user-adjustable height and button sizing.
    """
    action_triggered = pyqtSignal(str)
    settings_requested = pyqtSignal()

    def __init__(self, docker, parent=None):
        super().__init__(parent)
        self.docker = docker
        self.items = list(TOOLBAR_PRESETS["Artist Essentials"])
        self._button_height = 24

        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setStyleSheet("""
            QuickActionsToolbar {
                background: #141821;
                border: 1px solid #232b3b;
                border-radius: 6px;
            }
        """)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(4, 3, 4, 4)
        main_layout.setSpacing(3)
        self._main_layout = main_layout

        # Header strip: Title on left, Config button on right
        header_row = QHBoxLayout()
        header_row.setContentsMargins(2, 0, 2, 0)
        header_row.setSpacing(4)

        self.lbl_title = QLabel("⚡ QUICK ACTIONS")
        self.lbl_title.setStyleSheet("font-size: 9px; font-weight: bold; color: #64748b; letter-spacing: 0.5px;")
        header_row.addWidget(self.lbl_title)
        header_row.addStretch(1)

        self.btn_config = QPushButton("⚙")
        self.btn_config.setFixedSize(18, 18)
        self.btn_config.setToolTip("Customize Quick Actions Toolbar (add/remove shortcuts, change colors, presets, adjust height)")
        self.btn_config.setStyleSheet(
            "QPushButton { background: #1e293b; color: #94a3b8; border: 1px solid #334155; border-radius: 3px; font-size: 10px; padding: 0; }"
            "QPushButton:hover { background: #334155; color: #38bdf8; border-color: #38bdf8; }"
        )
        self.btn_config.clicked.connect(self._open_customizer)
        header_row.addWidget(self.btn_config)
        main_layout.addLayout(header_row)

        # Button container with FlowLayout
        self.btn_container = QWidget()
        self.btn_container.setStyleSheet("background: transparent; border: none;")
        self.flow_layout = FlowLayout(self.btn_container, margin=0, h_spacing=3, v_spacing=3)
        main_layout.addWidget(self.btn_container)

        self.rebuild_buttons()

    @property
    def button_height(self):
        return getattr(self, "_button_height", 24)

    @button_height.setter
    def button_height(self, h):
        self.set_button_height(h)

    def set_button_height(self, h):
        val = max(20, min(50, int(h)))
        if val != getattr(self, "_button_height", 24):
            self._button_height = val
            self.rebuild_buttons()

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        w = max(60, width)
        flow_w = max(40, w - 10)
        flow_h = self.flow_layout.heightForWidth(flow_w)
        return 22 + flow_h + 7

    def sizeHint(self):
        w = self.width() if self.width() > 50 else (self.parentWidget().width() if self.parentWidget() and self.parentWidget().width() > 50 else 280)
        h = self.heightForWidth(w)
        return QSize(w, h)

    def minimumSizeHint(self):
        return self.sizeHint()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        w = max(60, self.width())
        h = self.heightForWidth(w)
        if abs(self.height() - h) > 1:
            self.setFixedHeight(h)
        flow_w = max(40, w - 10)
        flow_h = self.flow_layout.heightForWidth(flow_w)
        self.flow_layout.setGeometry(QRect(0, 0, flow_w, flow_h))
        self.updateGeometry()

    def set_items(self, items):
        self.items = list(items)
        self.rebuild_buttons()

    def get_items(self):
        return list(self.items)

    def rebuild_buttons(self):
        # Clear existing buttons
        while self.flow_layout.count() > 0:
            item = self.flow_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

        bh = getattr(self, "_button_height", 24)
        font_size = max(9, min(12, int(bh * 0.40)))
        pad_v = max(1, int((bh - font_size - 8) * 0.5))

        for item in self.items:
            action_id = item.get("action_id", "")
            cat = ACTION_CATALOG.get(action_id, {})
            icon = item.get("icon") or cat.get("icon", "")
            label = item.get("label") or cat.get("label", action_id)
            tooltip = cat.get("tooltip", label)
            bg_col = item.get("color") or cat.get("color", "#252831")
            fg_col = item.get("text_color") or cat.get("text_color", "#e2e8f0")

            btn = QPushButton(f"{icon} {label}".strip())
            btn.setFixedHeight(bh)
            btn.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
            btn.setToolTip(tooltip)
            btn.setStyleSheet(f"""
                QPushButton {{
                    background: {bg_col};
                    color: {fg_col};
                    border: 1px solid rgba(255, 255, 255, 0.18);
                    border-radius: 4px;
                    font-size: {font_size}px;
                    font-weight: 600;
                    padding: {pad_v}px 7px;
                }}
                QPushButton:hover {{
                    border-color: #38bdf8;
                    color: #ffffff;
                }}
                QPushButton:pressed {{
                    background: #0f172a;
                }}
            """)
            btn.clicked.connect(lambda checked, aid=action_id: self._trigger_action(aid))
            # Calculate tight fixed size based on content so it never stretches across width
            hint_w = btn.sizeHint().width()
            btn.setFixedWidth(max(40, hint_w + 4))
            self.flow_layout.addWidget(btn)

        cur_w = self.width() if self.width() > 60 else (self.parentWidget().width() if self.parentWidget() and self.parentWidget().width() > 60 else 280)
        h = self.heightForWidth(cur_w)
        self.setFixedHeight(h)
        flow_w = max(40, cur_w - 10)
        flow_h = self.flow_layout.heightForWidth(flow_w)
        self.flow_layout.setGeometry(QRect(0, 0, flow_w, flow_h))
        self.updateGeometry()
        p = self.parentWidget()
        if p:
            p.updateGeometry()

    def _trigger_action(self, action_id):
        self.action_triggered.emit(action_id)
        self._execute_action(action_id)

    def _execute_action(self, action_id):
        d = self.docker
        if not d:
            return

        if action_id == "draw_box":
            d._open_primitive_drawer(start_click_draw=True)
        elif action_id in ("ground_rect", "draw_ground_rect", "drawRectangleGround"):
            d._open_ground_calibrator()
        elif action_id == "ground_4p":
            d._open_ground_calibrator(initial_mode=4)
        elif action_id == "ground_5p":
            d._open_ground_calibrator(initial_mode=5)
        elif action_id == "prim_box":
            d._create_primitive("Box")
        elif action_id == "prim_cyl":
            d._create_primitive("Cylinder")
        elif action_id == "prim_sph":
            d._create_primitive("Sphere")
        elif action_id == "prim_pyr":
            d._create_primitive("Pyramid")
        elif action_id == "prim_cone":
            d._create_primitive("Cone")
        elif action_id == "prim_plane":
            d._create_primitive("Plane")
        elif action_id in ("prim_room", "room_3p"):
            d._create_primitive("Room")
        elif action_id == "import_file":
            d._import()
        elif action_id == "clear_model":
            d._select_no_object_only_grid()

        # Lenses
        elif action_id == "lens_24":
            d._lens_cb(73.0)()
        elif action_id == "lens_35":
            d._lens_cb(54.0)()
        elif action_id == "lens_50":
            d._lens_cb(39.0)()
        elif action_id == "lens_85":
            d._lens_cb(24.0)()

        # Views & Framing
        elif action_id == "frame_obj":
            d._frame_view()
        elif action_id == "center_model":
            d._center_on_model()
        elif action_id == "center_origin":
            d._center_origin()
        elif action_id == "view_front":
            d.viewport.camera.yaw = 0.0
            d.viewport.camera.pitch = 0.0
            d._sync_ui()
            d.viewport.update()
            d._live_sync()
            d._schedule_save()
        elif action_id == "view_34":
            d.viewport.camera.yaw = 45.0
            d.viewport.camera.pitch = 25.0
            d._sync_ui()
            d.viewport.update()
            d._live_sync()
            d._schedule_save()
        elif action_id == "view_top":
            d.viewport.camera.yaw = 0.0
            d.viewport.camera.pitch = 89.0
            d._sync_ui()
            d.viewport.update()
            d._live_sync()
            d._schedule_save()
        elif action_id == "view_side":
            d.viewport.camera.yaw = 90.0
            d.viewport.camera.pitch = 0.0
            d._sync_ui()
            d.viewport.update()
            d._live_sync()
            d._schedule_save()
        elif action_id == "reset_cam":
            d._reset_camera_all()

        # Styles
        elif action_id == "style_shaded_wire":
            d._on_style("Shaded + Wireframe")
        elif action_id == "style_shaded":
            d._on_style("Shaded")
        elif action_id == "style_wire":
            d._on_style("Wireframe")
        elif action_id == "style_silhouette":
            d._on_style("Silhouette")

        # Grids
        elif action_id == "toggle_grid_vp":
            if hasattr(d, 'chk_grid_viewport'):
                d.chk_grid_viewport.setChecked(not d.chk_grid_viewport.isChecked())
        elif action_id == "toggle_grid_canvas":
            if hasattr(d, 'chk_grid_canvas'):
                d.chk_grid_canvas.setChecked(not d.chk_grid_canvas.isChecked())

        # Sync, Color & Stamp
        elif action_id == "stamp_now":
            d._stamp()
        elif action_id == "toggle_live":
            if hasattr(d, 'chk_live'):
                d.chk_live.setChecked(not d.chk_live.isChecked())
        elif action_id == "pick_model_color":
            d._pick_model_color()
        elif action_id == "reset_xform":
            d._reset_obj_all()

    def _open_customizer(self):
        dlg = QuickToolbarCustomizerDialog(self.items, button_height=self.button_height, parent=self)
        if dlg.exec_() == QDialog.Accepted:
            self.items = dlg.get_items()
            self._button_height = dlg.get_button_height()
            self.rebuild_buttons()
            if self.docker:
                if hasattr(self.docker, 'spin_qt_btn_height'):
                    self.docker.spin_qt_btn_height.blockSignals(True)
                    self.docker.spin_qt_btn_height.setValue(self._button_height)
                    self.docker.spin_qt_btn_height.blockSignals(False)
                self.docker._schedule_save()


# =====================================================================
# QUICK TOOLBAR CUSTOMIZER DIALOG
# =====================================================================
class QuickToolbarCustomizerDialog(QDialog):
    """
    Interactive modal dialog to customize quick actions toolbar:
    - Add/remove/reorder actions
    - Custom label, icon, background color
    - Select built-in preset propositions
    - Save/delete user presets
    - Adjust button height
    """
    def __init__(self, current_items, button_height=26, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Customize Quick Actions Toolbar")
        self.resize(540, 480)
        self.setStyleSheet("""
            QDialog { background: #181b22; color: #e2e8f0; font-family: 'Segoe UI', sans-serif; }
            QLabel { font-size: 10px; color: #cbd5e1; }
            QPushButton {
                background: #272d3b; border: 1px solid #3d4659; border-radius: 3px;
                color: #e2e8f0; font-size: 10px; padding: 3px 8px; min-height: 20px;
            }
            QPushButton:hover { background: #374151; border-color: #38bdf8; color: #ffffff; }
            QPushButton:pressed { background: #1e293b; }
            QListWidget {
                background: #11141a; border: 1px solid #2b3240; border-radius: 4px;
                color: #e2e8f0; font-size: 10px; padding: 4px;
            }
            QListWidget::item { padding: 4px 6px; border-radius: 2px; }
            QListWidget::item:selected { background: #1d4ed8; color: #ffffff; font-weight: bold; }
            QComboBox, QLineEdit {
                background: #11141a; border: 1px solid #334155; border-radius: 3px;
                color: #e2e8f0; font-size: 10px; padding: 3px 6px;
            }
        """)

        self.items = list(current_items)
        self._all_presets = load_all_toolbar_presets()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        # Header with Preset bar
        pr_box = QHBoxLayout()
        pr_box.addWidget(QLabel("Presets:"))
        self.combo_presets = QComboBox()
        self._populate_presets_combo()
        self.combo_presets.activated.connect(self._on_preset_selected)
        pr_box.addWidget(self.combo_presets, 1)

        btn_save_p = QPushButton("💾 Save Preset")
        btn_save_p.clicked.connect(self._save_preset)
        pr_box.addWidget(btn_save_p)

        btn_del_p = QPushButton("🗑")
        btn_del_p.setToolTip("Delete custom preset")
        btn_del_p.clicked.connect(self._delete_preset)
        pr_box.addWidget(btn_del_p)
        layout.addLayout(pr_box)

        # Button Height Control
        ht_box = QHBoxLayout()
        ht_box.addWidget(QLabel("Toolbar Button Height:"))
        self.spin_btn_height = QSpinBox()
        self.spin_btn_height.setRange(20, 50)
        self.spin_btn_height.setValue(self.button_height)
        self.spin_btn_height.setSuffix(" px")
        self.spin_btn_height.setToolTip("Adjust toolbar button height (20px compact to 50px large)")
        self.spin_btn_height.setStyleSheet("background:#11141a; color:#f1f5f9; border:1px solid #334155; padding:2px 6px; font-weight:bold;")
        ht_box.addWidget(self.spin_btn_height)
        ht_box.addStretch(1)
        layout.addLayout(ht_box)

        # Columns: Left = Active Toolbar Items, Right = Catalog of Available Actions
        cols = QHBoxLayout()

        # Left Column (Active Toolbar)
        col_left = QVBoxLayout()
        col_left.addWidget(QLabel("<b>Current Toolbar Shortcuts:</b>"))

        self.list_active = QListWidget()
        self.list_active.currentRowChanged.connect(self._on_active_row_changed)
        col_left.addWidget(self.list_active, 1)

        # Up / Down / Remove buttons
        row_order = QHBoxLayout()
        btn_up = QPushButton("▲ Up")
        btn_up.clicked.connect(self._move_up)
        row_order.addWidget(btn_up)

        btn_down = QPushButton("▼ Down")
        btn_down.clicked.connect(self._move_down)
        row_order.addWidget(btn_down)

        btn_remove = QPushButton("✖ Remove")
        btn_remove.setStyleSheet("QPushButton { background: #451a1a; color: #fca5a5; } QPushButton:hover { background: #7f1d1d; color: #fff; }")
        btn_remove.clicked.connect(self._remove_item)
        row_order.addWidget(btn_remove)
        col_left.addLayout(row_order)

        cols.addLayout(col_left, 1)

        # Middle Add Button
        mid_layout = QVBoxLayout()
        mid_layout.addStretch(1)
        btn_add = QPushButton("◀ Add")
        btn_add.setStyleSheet("QPushButton { background: #065f46; color: #a7f3d0; font-weight: bold; padding: 6px 8px; } QPushButton:hover { background: #059669; color: #fff; }")
        btn_add.setToolTip("Add selected action to toolbar")
        btn_add.clicked.connect(self._add_action_to_active)
        mid_layout.addWidget(btn_add)
        mid_layout.addStretch(1)
        cols.addLayout(mid_layout, 0)

        # Right Column (Available Catalog)
        col_right = QVBoxLayout()
        col_right.addWidget(QLabel("<b>Available Actions Catalog:</b>"))

        self.list_catalog = QListWidget()
        self._populate_catalog()
        col_right.addWidget(self.list_catalog, 1)
        cols.addLayout(col_right, 1)

        layout.addLayout(cols, 1)

        # Item Customizer Box (Label, Icon, Background Color)
        edit_frame = QFrame()
        edit_frame.setStyleSheet("background: #11141a; border: 1px solid #2b3240; border-radius: 4px; padding: 6px;")
        edit_layout = QHBoxLayout(edit_frame)
        edit_layout.setContentsMargins(6, 4, 6, 4)
        edit_layout.setSpacing(6)

        edit_layout.addWidget(QLabel("Label:"))
        self.edit_label = QLineEdit()
        self.edit_label.setPlaceholderText("Short text")
        self.edit_label.textChanged.connect(self._on_label_edited)
        edit_layout.addWidget(self.edit_label, 1)

        edit_layout.addWidget(QLabel("Icon:"))
        self.edit_icon = QLineEdit()
        self.edit_icon.setFixedWidth(40)
        self.edit_icon.textChanged.connect(self._on_icon_edited)
        edit_layout.addWidget(self.edit_icon, 0)

        self.btn_color = QPushButton("🎨 BG Color")
        self.btn_color.setToolTip("Pick button background color")
        self.btn_color.clicked.connect(self._pick_button_color)
        edit_layout.addWidget(self.btn_color, 0)

        layout.addWidget(edit_frame)

        # Bottom standard buttons
        bot = QHBoxLayout()
        btn_reset = QPushButton("Reset to Default")
        btn_reset.clicked.connect(self._reset_to_default)
        bot.addWidget(btn_reset)

        bot.addStretch(1)

        btn_ok = QPushButton("✔ Apply & Close")
        btn_ok.setStyleSheet("background: #2563eb; color: #fff; font-weight: bold; padding: 4px 14px;")
        btn_ok.clicked.connect(self.accept)
        bot.addWidget(btn_ok)

        btn_cancel = QPushButton("Cancel")
        btn_cancel.clicked.connect(self.reject)
        bot.addWidget(btn_cancel)

        layout.addLayout(bot)

        self._refresh_active_list()

    def get_items(self):
        return list(self.items)

    def get_button_height(self):
        return self.spin_btn_height.value()

    def _populate_presets_combo(self):
        self.combo_presets.blockSignals(True)
        self.combo_presets.clear()
        self.combo_presets.addItem("── Select a Toolbar Preset ──")
        for name in self._all_presets.keys():
            self.combo_presets.addItem(name)
        self.combo_presets.blockSignals(False)

    def _on_preset_selected(self, idx):
        if idx <= 0:
            return
        name = self.combo_presets.itemText(idx)
        if name in self._all_presets:
            self.items = list(self._all_presets[name])
            self._refresh_active_list()

    def _save_preset(self):
        name, ok = QInputDialog.getText(self, "Save Toolbar Preset", "Preset Name:")
        if ok and name.strip():
            name = name.strip()
            save_user_toolbar_preset(name, self.items)
            self._all_presets = load_all_toolbar_presets()
            self._populate_presets_combo()
            self.combo_presets.setCurrentText(name)

    def _delete_preset(self):
        name = self.combo_presets.currentText()
        if name in TOOLBAR_PRESETS:
            QMessageBox.information(self, "Cannot Delete", "Built-in presets cannot be deleted.")
            return
        if delete_user_toolbar_preset(name):
            self._all_presets = load_all_toolbar_presets()
            self._populate_presets_combo()

    def _reset_to_default(self):
        self.items = list(TOOLBAR_PRESETS["Artist Essentials"])
        self._refresh_active_list()

    def _populate_catalog(self):
        self.list_catalog.clear()
        for aid, cat in ACTION_CATALOG.items():
            icon = cat.get("icon", "")
            name = cat.get("name", aid)
            item = QListWidgetItem(f"{icon}  {name}")
            item.setData(Qt.UserRole, aid)
            self.list_catalog.addItem(item)

    def _refresh_active_list(self, select_row=None):
        self.list_active.clear()
        for it in self.items:
            aid = it.get("action_id", "")
            cat = ACTION_CATALOG.get(aid, {})
            icon = it.get("icon") or cat.get("icon", "")
            label = it.get("label") or cat.get("label", aid)
            list_item = QListWidgetItem(f"{icon}  {label}  ({cat.get('name', aid)})")
            self.list_active.addItem(list_item)

        if select_row is not None and 0 <= select_row < self.list_active.count():
            self.list_active.setCurrentRow(select_row)
        elif self.list_active.count() > 0:
            self.list_active.setCurrentRow(0)

    def _on_active_row_changed(self, row):
        if 0 <= row < len(self.items):
            it = self.items[row]
            aid = it.get("action_id", "")
            cat = ACTION_CATALOG.get(aid, {})
            label = it.get("label") or cat.get("label", "")
            icon = it.get("icon") or cat.get("icon", "")
            bg_col = it.get("color") or cat.get("color", "#252831")

            self.edit_label.blockSignals(True)
            self.edit_label.setText(label)
            self.edit_label.blockSignals(False)

            self.edit_icon.blockSignals(True)
            self.edit_icon.setText(icon)
            self.edit_icon.blockSignals(False)

            self.btn_color.setStyleSheet(f"background: {bg_col}; color: #fff; font-weight: bold;")
        else:
            self.edit_label.setText("")
            self.edit_icon.setText("")
            self.btn_color.setStyleSheet("")

    def _on_label_edited(self, text):
        r = self.list_active.currentRow()
        if 0 <= r < len(self.items):
            self.items[r]["label"] = text
            aid = self.items[r].get("action_id", "")
            cat = ACTION_CATALOG.get(aid, {})
            icon = self.items[r].get("icon") or cat.get("icon", "")
            self.list_active.item(r).setText(f"{icon}  {text}  ({cat.get('name', aid)})")

    def _on_icon_edited(self, text):
        r = self.list_active.currentRow()
        if 0 <= r < len(self.items):
            self.items[r]["icon"] = text
            aid = self.items[r].get("action_id", "")
            cat = ACTION_CATALOG.get(aid, {})
            label = self.items[r].get("label") or cat.get("label", "")
            self.list_active.item(r).setText(f"{text}  {label}  ({cat.get('name', aid)})")

    def _pick_button_color(self):
        r = self.list_active.currentRow()
        if 0 <= r < len(self.items):
            cur_col = QColor(self.items[r].get("color", "#252831"))
            col = QColorDialog.getColor(cur_col, self, "Select Button Background Color")
            if col.isValid():
                hex_c = col.name()
                self.items[r]["color"] = hex_c
                self.btn_color.setStyleSheet(f"background: {hex_c}; color: #fff; font-weight: bold;")

    def _add_action_to_active(self):
        cur = self.list_catalog.currentItem()
        if not cur:
            return
        aid = cur.data(Qt.UserRole)
        cat = ACTION_CATALOG.get(aid, {})
        new_item = {
            "action_id": aid,
            "label": cat.get("label", aid),
            "icon": cat.get("icon", ""),
            "color": cat.get("color", "#1e293b"),
            "text_color": cat.get("text_color", "#e2e8f0"),
        }
        self.items.append(new_item)
        self._refresh_active_list(select_row=len(self.items) - 1)

    def _remove_item(self):
        r = self.list_active.currentRow()
        if 0 <= r < len(self.items):
            del self.items[r]
            new_r = min(r, len(self.items) - 1)
            self._refresh_active_list(select_row=new_r)

    def _move_up(self):
        r = self.list_active.currentRow()
        if r > 0:
            self.items[r], self.items[r - 1] = self.items[r - 1], self.items[r]
            self._refresh_active_list(select_row=r - 1)

    def _move_down(self):
        r = self.list_active.currentRow()
        if 0 <= r < len(self.items) - 1:
            self.items[r], self.items[r + 1] = self.items[r + 1], self.items[r]
            self._refresh_active_list(select_row=r + 1)
