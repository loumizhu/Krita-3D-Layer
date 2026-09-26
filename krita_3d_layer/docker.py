"""
docker.py - Krita DockWidget providing rich 3D controls and embedded viewport.
Fully fluid layout: no fixed widths, no clipping at narrow docker sizes.
All controls flow and wrap naturally.

Reorganized into 7 logical, intuitive sections:
1. 3D VIEWPORT (interactive viewport with overlay tools and resize handle)
2. MODEL & MATERIAL (import, primitives, dedicated model color swatch, styles, outlines, framing)
3. CAMERA & PROJECTION (projection presets, navigation modes, angles, FOV, lens presets, distance, pan, target)
4. GROUND & FRAMING (ground rect perspective calibrator, canvas scene frame limits)
5. PERSPECTIVE GRIDS (horizon line, ground floor grid, ceiling grid above, tile size, poles)
6. LIGHTING (studio light sphere, ambient, key, fill)
7. SETTINGS & PERFORMANCE (display toggles, render quality, refresh rate in ms, background color)
"""

import os
import math
import json
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QComboBox, QCheckBox, QSlider, QFileDialog,
    QColorDialog, QScrollArea, QFrame, QSizePolicy, QGridLayout,
    QButtonGroup, QDoubleSpinBox, QSpinBox, QMenu,
    QInputDialog, QMessageBox
)
from PyQt5.QtGui import QColor, QFont, QDesktopServices
from PyQt5.QtCore import Qt, QTimer, QUrl

try:
    from krita import DockWidget, Krita
except ImportError:
    from PyQt5.QtWidgets import QDockWidget as DockWidget
    Krita = None

from .viewport import Viewport3D, CAMERA_MODES, CAMERA_MODE_ORBIT
from .renderer import (
    RenderStyle, PerspectiveGridSettings, ProjectionMode, Camera3D
)
from .mesh_loader import load_3d_file
from .canvas_sync import CanvasSyncManager
from .widgets import (
    CollapsibleSection, SphereLightWidget,
    ScrubbableSpinBox, ScrubbableDoubleSpinBox, ViewportResizeHandle
)
from .ground_calibrator import GroundCalibratorDialog

DOCKER_ID = "krita_3d_layer_docker"

BUILTIN_PRESETS = {
    "Default Studio 3/4": {
        "proj_mode": "Perspective",
        "fov": 45.0,
        "distance": 3.2,
        "yaw": 45.0,
        "pitch": 25.0,
        "roll": 0.0,
        "tilt": 0.0,
        "pan_x": 0.0,
        "pan_y": 0.0,
        "curvature": 1.0,
        "grid_enabled_canvas": False,
        "grid_viewport": True,
        "grid_ground": True,
        "grid_ceiling": False,
        "ceiling_height": 2.5,
        "horizon_enabled": True,
        "grid_extent": 16,
        "tile_size": 0.5,
        "subdivisions": 2,
        "exceed_lines": True,
        "vertical_lines": False,
        "vertical_height": 2.0,
        "axis_colors": True,
        "render_style": "Shaded + Wireframe",
        "light_az": 45.0,
        "light_el": 40.0,
    },
    "Dramatic Fisheye 180°": {
        "proj_mode": "Fisheye / Curvilinear",
        "fov": 65.0,
        "distance": 2.6,
        "yaw": 35.0,
        "pitch": 22.0,
        "roll": 0.0,
        "tilt": 0.0,
        "pan_x": 0.0,
        "pan_y": 0.0,
        "fisheye_fov": 180.0,
        "curvature": 1.7,
        "fisheye_zoom": 1.0,
        "lens_type": "Stereographic",
        "grid_enabled_canvas": False,
        "grid_viewport": True,
        "grid_ground": True,
        "grid_ceiling": False,
        "ceiling_height": 2.5,
        "horizon_enabled": True,
        "grid_extent": 20,
        "tile_size": 0.5,
        "subdivisions": 2,
        "exceed_lines": True,
        "vertical_lines": True,
        "vertical_height": 2.0,
        "axis_colors": True,
        "render_style": "Shaded + Wireframe",
        "light_az": 50.0,
        "light_el": 45.0,
    },
    "5-Point Comic Curvilinear": {
        "proj_mode": "Artist 5-VP (Arc Curves)",
        "fov": 85.0,
        "distance": 2.4,
        "yaw": 40.0,
        "pitch": 18.0,
        "roll": 0.0,
        "tilt": 0.0,
        "pan_x": 0.0,
        "pan_y": 0.0,
        "curvature": 1.5,
        "grid_enabled_canvas": False,
        "grid_viewport": True,
        "grid_ground": True,
        "grid_ceiling": True,
        "ceiling_height": 2.6,
        "horizon_enabled": True,
        "grid_extent": 18,
        "tile_size": 0.5,
        "subdivisions": 2,
        "exceed_lines": True,
        "vertical_lines": True,
        "vertical_height": 2.6,
        "axis_colors": True,
        "render_style": "Shaded + Wireframe",
        "light_az": 40.0,
        "light_el": 55.0,
    },
    "Ultra-Wide Low-Angle (Hero)": {
        "proj_mode": "Perspective",
        "fov": 85.0,
        "distance": 2.0,
        "yaw": 28.0,
        "pitch": -28.0,
        "roll": 0.0,
        "tilt": 0.0,
        "pan_x": 0.0,
        "pan_y": 0.0,
        "curvature": 1.0,
        "grid_enabled_canvas": False,
        "grid_viewport": True,
        "grid_ground": True,
        "grid_ceiling": False,
        "ceiling_height": 2.5,
        "horizon_enabled": True,
        "grid_extent": 20,
        "tile_size": 0.5,
        "subdivisions": 2,
        "exceed_lines": True,
        "vertical_lines": True,
        "vertical_height": 2.5,
        "axis_colors": True,
        "render_style": "Shaded + Wireframe",
        "light_az": 30.0,
        "light_el": 45.0,
    },
    "Bird's Eye Top-Down": {
        "proj_mode": "Perspective",
        "fov": 45.0,
        "distance": 4.5,
        "yaw": 0.0,
        "pitch": 78.0,
        "roll": 0.0,
        "tilt": 0.0,
        "pan_x": 0.0,
        "pan_y": 0.0,
        "curvature": 1.0,
        "grid_enabled_canvas": False,
        "grid_viewport": True,
        "grid_ground": True,
        "grid_ceiling": False,
        "ceiling_height": 2.5,
        "horizon_enabled": False,
        "grid_extent": 20,
        "tile_size": 0.5,
        "subdivisions": 2,
        "exceed_lines": True,
        "vertical_lines": False,
        "vertical_height": 2.0,
        "axis_colors": True,
        "render_style": "Shaded + Wireframe",
        "light_az": 45.0,
        "light_el": 75.0,
    },
    "Isometric Architectural": {
        "proj_mode": "Orthographic",
        "fov": 45.0,
        "distance": 3.5,
        "yaw": 45.0,
        "pitch": 35.264,
        "roll": 0.0,
        "tilt": 0.0,
        "pan_x": 0.0,
        "pan_y": 0.0,
        "curvature": 1.0,
        "grid_enabled_canvas": False,
        "grid_viewport": True,
        "grid_ground": True,
        "grid_ceiling": False,
        "ceiling_height": 2.5,
        "horizon_enabled": False,
        "grid_extent": 20,
        "tile_size": 0.5,
        "subdivisions": 2,
        "exceed_lines": True,
        "vertical_lines": False,
        "vertical_height": 2.0,
        "axis_colors": True,
        "render_style": "Shaded + Wireframe",
        "light_az": 60.0,
        "light_el": 45.0,
    },
    "Cinematic Portrait (85mm)": {
        "proj_mode": "Perspective",
        "fov": 28.0,
        "distance": 5.8,
        "yaw": 20.0,
        "pitch": 8.0,
        "roll": 0.0,
        "tilt": 0.0,
        "pan_x": 0.0,
        "pan_y": 0.0,
        "curvature": 1.0,
        "grid_enabled_canvas": False,
        "grid_viewport": True,
        "grid_ground": True,
        "grid_ceiling": False,
        "ceiling_height": 2.5,
        "horizon_enabled": True,
        "grid_extent": 16,
        "tile_size": 0.5,
        "subdivisions": 2,
        "exceed_lines": True,
        "vertical_lines": False,
        "vertical_height": 2.0,
        "axis_colors": True,
        "render_style": "Shaded + Wireframe",
        "light_az": 35.0,
        "light_el": 30.0,
    },
    "Full Room (Floor + Ceiling)": {
        "proj_mode": "Perspective",
        "fov": 70.0,
        "distance": 3.2,
        "yaw": 32.0,
        "pitch": 12.0,
        "roll": 0.0,
        "tilt": 0.0,
        "pan_x": 0.0,
        "pan_y": 0.0,
        "curvature": 1.0,
        "grid_enabled_canvas": False,
        "grid_viewport": True,
        "grid_ground": True,
        "grid_ceiling": True,
        "ceiling_height": 2.8,
        "horizon_enabled": True,
        "grid_extent": 20,
        "tile_size": 0.5,
        "subdivisions": 2,
        "exceed_lines": True,
        "vertical_lines": True,
        "vertical_height": 2.8,
        "axis_colors": True,
        "render_style": "Shaded + Wireframe",
        "light_az": 45.0,
        "light_el": 60.0,
    },
    "High Dynamic Low Ground": {
        "proj_mode": "Fisheye / Curvilinear",
        "fov": 75.0,
        "distance": 1.8,
        "yaw": 20.0,
        "pitch": -12.0,
        "roll": 0.0,
        "tilt": 0.0,
        "pan_x": 0.0,
        "pan_y": 0.0,
        "fisheye_fov": 180.0,
        "curvature": 2.0,
        "fisheye_zoom": 1.0,
        "lens_type": "Stereographic",
        "grid_enabled_canvas": False,
        "grid_viewport": True,
        "grid_ground": True,
        "grid_ceiling": False,
        "ceiling_height": 2.5,
        "horizon_enabled": True,
        "grid_extent": 22,
        "tile_size": 0.5,
        "subdivisions": 2,
        "exceed_lines": True,
        "vertical_lines": True,
        "vertical_height": 2.0,
        "axis_colors": True,
        "render_style": "Shaded + Wireframe",
        "light_az": 45.0,
        "light_el": 45.0,
    }
}


def get_presets_file_path():
    appdata = os.environ.get("APPDATA")
    if appdata and os.path.exists(appdata):
        kdir = os.path.join(appdata, "krita")
        os.makedirs(kdir, exist_ok=True)
        return os.path.join(kdir, "krita_3d_layer_presets.json")
    hdir = os.path.expanduser("~/.local/share/krita")
    os.makedirs(hdir, exist_ok=True)
    return os.path.join(hdir, "krita_3d_layer_presets.json")


def load_all_presets():
    presets = dict(BUILTIN_PRESETS)
    p_path = get_presets_file_path()
    if os.path.exists(p_path):
        try:
            with open(p_path, "r", encoding="utf-8") as f:
                user_p = json.load(f)
                if isinstance(user_p, dict):
                    presets.update(user_p)
        except Exception:
            pass
    return presets


def save_custom_preset_to_disk(name, preset_dict):
    p_path = get_presets_file_path()
    user_p = {}
    if os.path.exists(p_path):
        try:
            with open(p_path, "r", encoding="utf-8") as f:
                loaded = json.load(f)
                if isinstance(loaded, dict):
                    user_p = loaded
        except Exception:
            pass
    user_p[name] = preset_dict
    with open(p_path, "w", encoding="utf-8") as f:
        json.dump(user_p, f, indent=2)


def delete_custom_preset_from_disk(name):
    p_path = get_presets_file_path()
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


def get_session_file_path():
    """Returns path to the persistent session/settings JSON file."""
    appdata = os.environ.get("APPDATA")
    if appdata and os.path.exists(appdata):
        kdir = os.path.join(appdata, "krita")
        os.makedirs(kdir, exist_ok=True)
        return os.path.join(kdir, "krita_3d_layer_session.json")
    hdir = os.path.expanduser("~/.local/share/krita")
    os.makedirs(hdir, exist_ok=True)
    return os.path.join(hdir, "krita_3d_layer_session.json")


def load_session():
    """Load persistent session data. Falls back to packaged default_session.json."""
    path = get_session_file_path()
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                d = json.load(f)
                if d and isinstance(d, dict):
                    return d
        except Exception:
            pass
    # Fallback to packaged defaults
    pkg_default = os.path.join(os.path.dirname(__file__), "default_session.json")
    if os.path.exists(pkg_default):
        try:
            with open(pkg_default, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def save_session(data):
    """Persist session data dict to disk."""
    path = get_session_file_path()
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except Exception:
        pass

DOCKER_STYLE = """
    * { font-family: "Segoe UI", sans-serif; }
    QPushButton {
        font-size: 9px; padding: 1px 3px; min-height: 17px;
        background: #323642; border: 1px solid #434958;
        border-radius: 2px; color: #e5e7eb;
    }
    QPushButton:hover { background: #3d4352; color: #fff; border-color: #555e70; }
    QPushButton:pressed { background: #242730; }
    QPushButton:checked { background: #2563eb; border-color: #3b82f6; color: #fff; font-weight: bold; }
    QLabel { font-size: 9px; color: #cbd5e1; }
    QComboBox {
        font-size: 9px; min-height: 17px; padding: 1px 3px;
        background: #262932; border: 1px solid #3d4352;
        border-radius: 2px; color: #e5e7eb;
    }
    QComboBox::drop-down { border: none; width: 12px; }
    QCheckBox { font-size: 9px; color: #cbd5e1; spacing: 3px; }
    QSlider { min-height: 12px; max-height: 14px; }
    QSlider::groove:horizontal { height: 3px; background: #252831; border-radius: 1px; }
    QSlider::sub-page:horizontal { background: #3b82f6; border-radius: 1px; }
    QSlider::handle:horizontal {
        background: #93c5fd; border: 1px solid #1d4ed8;
        width: 7px; margin: -2px 0; border-radius: 3px;
    }
    QSlider::handle:horizontal:hover { background: #fff; }
    QDoubleSpinBox, QSpinBox {
        font-size: 9px; min-height: 17px; padding: 1px 2px;
        background: #262932; border: 1px solid #3d4352;
        border-radius: 2px; color: #e5e7eb;
    }
"""


class Krita3DLayerDocker(DockWidget):
    """
    3D Layer Docker for Krita.
    Access the active instance via Krita3DLayerDocker.instance().
    All properties on .viewport.camera, .viewport.lighting, .viewport.renderer
    are scriptable.
    """
    _active_instance = None

    @classmethod
    def instance(cls):
        """Returns the active docker instance for programmatic control."""
        return cls._active_instance

    def __init__(self):
        super().__init__()
        Krita3DLayerDocker._active_instance = self
        self.setObjectName(DOCKER_ID)
        self.setWindowTitle("3D Layer")

        # Root container with optional sticky viewport
        self._root_container = QWidget()
        self._root_container.setStyleSheet(DOCKER_STYLE)

        # Outer vertical layout: sticky viewport area + scrollable controls
        outer_layout = QVBoxLayout(self._root_container)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.setSpacing(0)

        # Sticky viewport container (shown/hidden based on setting)
        self._sticky_viewport_widget = QWidget()
        self._sticky_viewport_layout = QVBoxLayout(self._sticky_viewport_widget)
        self._sticky_viewport_layout.setContentsMargins(3, 3, 3, 0)
        self._sticky_viewport_layout.setSpacing(2)
        self._sticky_viewport_widget.setVisible(False)  # off by default
        outer_layout.addWidget(self._sticky_viewport_widget)

        # Scrollable area for controls
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._scroll = scroll

        root = QWidget()
        root.setStyleSheet(DOCKER_STYLE)
        scroll.setWidget(root)
        outer_layout.addWidget(scroll)

        self.setWidget(self._root_container)

        L = QVBoxLayout(root)
        L.setContentsMargins(3, 3, 3, 3)
        L.setSpacing(4)

        self.mesh = None
        self.mesh_path = None
        self.frame_rect = None
        self.custom_bg_color = QColor(255, 255, 255)
        self.is_sticky_viewport = True

        # Debounce timer for live canvas stamping
        self.live_sync_timer = QTimer(self)
        self.live_sync_timer.setSingleShot(True)
        self.live_sync_timer.timeout.connect(self._do_live_sync)
        self.debounce_ms = 120

        # Auto-save timer (saves session every 30 seconds while Krita is open)
        self._autosave_timer = QTimer(self)
        self._autosave_timer.setInterval(30000)
        self._autosave_timer.timeout.connect(self._save_session)
        self._autosave_timer.start()

        # Fast debounced save timer (triggers save 400ms after user tweaks any control)
        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.setInterval(400)
        self._save_timer.timeout.connect(self._save_session)

        # =============================================================
        # SECTION 1: 3D VIEWPORT
        # =============================================================
        self.sec_viewport = CollapsibleSection("3D VIEWPORT", expanded=False)

        self.viewport = Viewport3D()
        self.viewport.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.viewport.setFixedHeight(170)
        self.viewport.setMinimumHeight(60)
        self.viewport.camera_changed.connect(self._on_camera_changed)
        self.viewport.interaction_ended.connect(self._on_interaction_ended)
        self.viewport.interaction_ended.connect(self._save_session)
        self.viewport.fov_changed.connect(self._on_viewport_fov_changed)
        self.sec_viewport.add_widget(self.viewport)

        # Draggable height separator
        self.resize_handle = ViewportResizeHandle(self.viewport)
        self.resize_handle.resized.connect(self._on_viewport_resized)
        self.sec_viewport.add_widget(self.resize_handle)

        L.addWidget(self.sec_viewport)

        # =============================================================
        # SECTION: PRESETS & TEMPLATES
        # =============================================================
        self.sec_presets = CollapsibleSection("PRESETS & TEMPLATES", expanded=True)
        pr_layout = QVBoxLayout(); pr_layout.setSpacing(2)

        pr_row = QHBoxLayout(); pr_row.setSpacing(2)
        self.combo_presets = QComboBox()
        self.combo_presets.setStyleSheet(
            "QComboBox { background: #1e293b; color: #38bdf8; font-weight: bold; padding: 2px 4px; }"
            "QComboBox QAbstractItemView { background: #0f172a; color: #f1f5f9; selection-background-color: #2563eb; }"
        )
        self.combo_presets.setToolTip("Select a preset to load all camera, projection, grid & lighting parameters automatically!")
        self.combo_presets.activated.connect(self._on_preset_activated)
        pr_row.addWidget(self.combo_presets, 1)

        self.btn_save_preset = QPushButton("💾 Save...")
        self.btn_save_preset.setToolTip("Save current parameters as a new custom preset")
        self.btn_save_preset.clicked.connect(self._save_custom_preset)
        pr_row.addWidget(self.btn_save_preset, 0)

        self.btn_del_preset = QPushButton("🗑")
        self.btn_del_preset.setFixedSize(24, 22)
        self.btn_del_preset.setToolTip("Delete custom preset")
        self.btn_del_preset.clicked.connect(self._delete_custom_preset)
        pr_row.addWidget(self.btn_del_preset, 0)

        self.btn_help_manual = QPushButton("❓ Manual")
        self.btn_help_manual.setStyleSheet("background:#1e293b; color:#93c5fd; font-weight:bold; padding:2px 6px; border:1px solid #3b82f6;")
        self.btn_help_manual.setToolTip("Open Krita 3D Layer Manual & Quick Guide")
        self.btn_help_manual.clicked.connect(self._open_manual)
        pr_row.addWidget(self.btn_help_manual, 0)

        pr_layout.addLayout(pr_row)
        self.sec_presets.add_layout(pr_layout)
        L.addWidget(self.sec_presets)

        # =============================================================
        # SECTION 2: MODEL & MATERIAL
        # =============================================================
        self.sec_model = CollapsibleSection("MODEL & MATERIAL", expanded=True)

        mr = QHBoxLayout(); mr.setSpacing(2)
        bi = QPushButton("📁 Import 3D")
        bi.setToolTip("Import 3D model (.obj, .stl, .glb, .gltf)")
        bi.clicked.connect(self._import)
        mr.addWidget(bi, 2)

        self.btn_primitives = QPushButton("📦 Primitives ▾")
        self.btn_primitives.setStyleSheet(
            "QPushButton{background:#1e293b; color:#93c5fd; font-weight:bold; border:1px solid #3b82f6;}"
            "QPushButton:hover{background:#2563eb; color:#fff;}"
        )
        self.btn_primitives.setToolTip("Select and load a 3D primitive or reference model (Asaro head, box, sphere, cylinder...)")
        self._setup_primitives_menu()
        mr.addWidget(self.btn_primitives, 2)

        # Dedicated square color button with live swatch preview for 3D model color
        self.btn_model_color = QPushButton("🎨")
        self.btn_model_color.setFixedSize(28, 22)
        self.btn_model_color.setToolTip("Change 3D Model Material Color (Light Grey, Clay, Plaster, Skin, etc.)")
        self.btn_model_color.clicked.connect(self._pick_model_color)
        self._update_model_color_button()
        mr.addWidget(self.btn_model_color, 0)
        self.sec_model.add_layout(mr)

        self.lbl_model = QLabel("No model loaded")
        self.lbl_model.setWordWrap(True)
        self.lbl_model.setStyleSheet("color:#8fa0b5;font-size:9px;")
        self.sec_model.add_widget(self.lbl_model)

        # Shading style dropdown
        style_row = QHBoxLayout(); style_row.setSpacing(2)
        self.combo_style = QComboBox()
        self.combo_style.addItems([
            RenderStyle.SHADED_WIREFRAME, RenderStyle.SHADED,
            RenderStyle.WIREFRAME, RenderStyle.SILHOUETTE, RenderStyle.NORMAL_MAP
        ])
        self.combo_style.setToolTip("Choose 3D artistic rendering style (Shaded + Wireframe, Shaded, Wireframe, Silhouette, Normal Map)")
        self.combo_style.currentTextChanged.connect(self._on_style)
        style_row.addWidget(self.combo_style, 1)
        self.sec_model.add_layout(style_row)

        # Wireframe options row (Cull Back & Quad Wireframe / Hide Diagonals)
        wire_opts_row = QHBoxLayout(); wire_opts_row.setSpacing(4)
        self.chk_wire_cull = QCheckBox("Cull Back")
        self.chk_wire_cull.setChecked(True)
        self.chk_wire_cull.setToolTip("Hide back-facing wireframe edges for cleaner drawings")
        self.chk_wire_cull.stateChanged.connect(self._on_wire_cull)
        wire_opts_row.addWidget(self.chk_wire_cull, 0)

        self.chk_hide_coplanar = QCheckBox("Quad Wire (Hide Diagonals)")
        self.chk_hide_coplanar.setChecked(True)
        self.chk_hide_coplanar.setToolTip("Hide internal triangulation diagonals on flat faces and quads (Blender quad-style wireframe)")
        self.chk_hide_coplanar.stateChanged.connect(self._on_hide_coplanar)
        wire_opts_row.addWidget(self.chk_hide_coplanar, 1)
        self.sec_model.add_layout(wire_opts_row)

        # Wire thickness & Wire Color
        wr = QHBoxLayout(); wr.setSpacing(1)
        self.lbl_wire = QLabel("Wire 1.0")
        wr.addWidget(self.lbl_wire)
        bw = QPushButton("🔲")
        bw.setFixedSize(22, 20)
        bw.setToolTip("Pick Wireframe Color")
        bw.clicked.connect(self._pick_wire_col)
        wr.addWidget(bw)
        self.sec_model.add_layout(wr)
        self.sl_wire = self._slider(5, 50, 10, self._on_wire_w)
        self.sl_wire.setToolTip("Adjust wireframe stroke thickness")
        self.sec_model.add_widget(self.sl_wire)

        # Contour outline thickness & Contour Color
        cr2 = QHBoxLayout(); cr2.setSpacing(1)
        self.lbl_contour = QLabel("Contour Off")
        cr2.addWidget(self.lbl_contour)
        bc = QPushButton("🖊")
        bc.setFixedSize(22, 20)
        bc.setToolTip("Pick Silhouette Contour Color")
        bc.clicked.connect(self._pick_contour_col)
        cr2.addWidget(bc)
        self.sec_model.add_layout(cr2)
        self.sl_contour = self._slider(0, 80, 0, self._on_contour_w)
        self.sl_contour.setToolTip("Adjust silhouette outer contour width (0 = off)")
        self.sec_model.add_widget(self.sl_contour)

        L.addWidget(self.sec_model)

        # =============================================================
        # SECTION 3: CAMERA & PROJECTION
        # =============================================================
        self.sec_cam = CollapsibleSection("CAMERA & PROJECTION", expanded=True)

        # Projection Mode Dropdown (Perspective, Ortho, Fisheye, 5-Point, Cylindrical)
        proj_hdr = QHBoxLayout(); proj_hdr.setSpacing(2)
        proj_hdr.addWidget(QLabel("Projection:"))
        self.combo_proj = QComboBox()
        self.combo_proj.addItems(ProjectionMode.ALL)
        self.combo_proj.setToolTip("Select camera lens projection: Linear Perspective, Orthographic, Fisheye/Curvilinear, Artist 5-VP (Arc Curves), or Cylindrical/Panini")
        self.combo_proj.currentTextChanged.connect(self._on_proj_mode)
        proj_hdr.addWidget(self.combo_proj, 1)
        self.sec_cam.add_layout(proj_hdr)

        # Curvilinear curvature slider (active for 5-Point / Cylindrical)
        self.lbl_curv = QLabel("Curvature 100%")
        self.lbl_curv.setStyleSheet("color:#38bdf8; font-weight:bold;")
        self.sl_curv = self._slider(10, 250, 100, self._on_curvature)
        self.sl_curv.setToolTip("Adjust curvilinear bending strength (how much straight lines curve)")
        self.lbl_curv.setVisible(False)
        self.sl_curv.setVisible(False)
        self.sec_cam.add_widget(self.lbl_curv)
        self.sec_cam.add_widget(self.sl_curv)

        # ==================== FISHEYE CONTROLS GROUP ====================
        self.w_fisheye_group = QWidget()
        l_fish = QVBoxLayout(self.w_fisheye_group)
        l_fish.setContentsMargins(4, 4, 4, 4)
        l_fish.setSpacing(3)
        self.w_fisheye_group.setStyleSheet("background:#232733; border:1px solid #3b82f6; border-radius:4px; padding:2px;")

        # 1. Fisheye Lens Model
        fish_lens_hdr = QHBoxLayout(); fish_lens_hdr.setSpacing(2)
        fish_lens_hdr.addWidget(QLabel("Lens Model:"))
        self.combo_fish_lens = QComboBox()
        self.combo_fish_lens.addItems([
            "Equidistant (Standard 180°)",
            "Stereographic (Conformal)",
            "Equisolid (Photographic)",
            "Orthographic (Bubble)"
        ])
        self.combo_fish_lens.setToolTip("Fisheye projection formula: Equidistant (straight lines become circles), Stereographic (preserves angles), Equisolid (real lens), Orthographic (bubble)")
        self.combo_fish_lens.currentTextChanged.connect(self._on_fish_lens_changed)
        fish_lens_hdr.addWidget(self.combo_fish_lens, 1)
        l_fish.addLayout(fish_lens_hdr)

        # 2. Fisheye Angle of View (FOV)
        fov_btn_row = QHBoxLayout(); fov_btn_row.setSpacing(2)
        self.lbl_fish_fov = QLabel("Fisheye FOV: 180°")
        self.lbl_fish_fov.setStyleSheet("color:#a78bfa; font-weight:bold;")
        fov_btn_row.addWidget(self.lbl_fish_fov, 1)
        for ang in [120, 180, 220]:
            btn_ang = QPushButton(f"{ang}°")
            btn_ang.setToolTip(f"Set fisheye view angle to {ang}°")
            btn_ang.clicked.connect(lambda _, a=ang: self._set_fish_fov_preset(a))
            fov_btn_row.addWidget(btn_ang)
        l_fish.addLayout(fov_btn_row)

        self.sl_fish_fov = self._slider(60, 220, 180, self._on_fish_fov)
        self.sl_fish_fov.setToolTip("Fisheye angle of view in degrees (60° narrow to 220° ultra-wide circular)")
        l_fish.addWidget(self.sl_fish_fov)

        # 3. Fisheye Curvature Strength
        self.lbl_fish_curv = QLabel("Curvature Strength: 100%")
        self.lbl_fish_curv.setStyleSheet("color:#38bdf8;")
        l_fish.addWidget(self.lbl_fish_curv)
        self.sl_fish_curv = self._slider(20, 250, 100, self._on_fish_curv)
        self.sl_fish_curv.setToolTip("Adjust barrel distortion curvature intensity (100% is natural)")
        l_fish.addWidget(self.sl_fish_curv)

        # 4. Fisheye Lens Zoom & Circular Vignette Mask
        fish_opts_row = QHBoxLayout(); fish_opts_row.setSpacing(2)
        self.chk_fish_circle = QCheckBox("Circular Lens Vignette")
        self.chk_fish_circle.setChecked(False)
        self.chk_fish_circle.setToolTip("Draw circular peephole lens aperture mask around fisheye sphere")
        self.chk_fish_circle.stateChanged.connect(self._on_toggle_fish_circle)
        fish_opts_row.addWidget(self.chk_fish_circle)
        l_fish.addLayout(fish_opts_row)

        self.lbl_fish_zoom = QLabel("Lens Zoom: 100%")
        l_fish.addWidget(self.lbl_fish_zoom)
        self.sl_fish_zoom = self._slider(50, 200, 100, self._on_fish_zoom)
        self.sl_fish_zoom.setToolTip("Zoom inside fisheye lens circle to frame center or show entire hemisphere")
        l_fish.addWidget(self.sl_fish_zoom)

        self.w_fisheye_group.setVisible(False)
        self.sec_cam.add_widget(self.w_fisheye_group)

        # Navigation Mode (Orbit, Turntable, First Person)
        nav_hdr = QHBoxLayout(); nav_hdr.setSpacing(2)
        nav_hdr.addWidget(QLabel("Navigation:"))
        self.combo_cam_mode = QComboBox()
        for m in CAMERA_MODES:
            self.combo_cam_mode.addItem(m)
        self.combo_cam_mode.setToolTip("Camera viewport navigation style: Orbit Around Object, Turntable (Locked Up), or First Person (Look Around)")
        self.combo_cam_mode.currentTextChanged.connect(self._on_cam_mode)
        nav_hdr.addWidget(self.combo_cam_mode, 1)
        self.sec_cam.add_layout(nav_hdr)

        # Pitch (Tilt up/down)
        tr_pitch = QHBoxLayout(); tr_pitch.setSpacing(1)
        self.lbl_tilt = QLabel("Orbit Pitch 12°")
        tr_pitch.addWidget(self.lbl_tilt)
        b_p0 = QPushButton("0°"); b_p0.setToolTip("Level orbit pitch to 0°"); b_p0.clicked.connect(self._reset_pitch)
        tr_pitch.addWidget(b_p0)
        self.sec_cam.add_layout(tr_pitch)
        self.sl_tilt = self._slider(-89, 89, 12, self._on_tilt)
        self.sl_tilt.setToolTip("Orbit pitch angle up/down around target")
        self.sec_cam.add_widget(self.sl_tilt)

        # Azimuth / Yaw
        self.lbl_yaw = QLabel("Orbit Yaw 145°")
        self.sec_cam.add_widget(self.lbl_yaw)
        self.sl_yaw = self._slider(0, 360, 145, self._on_yaw)
        self.sl_yaw.setToolTip("Horizontal orbit azimuth around target (0° to 360°)")
        self.sec_cam.add_widget(self.sl_yaw)

        # Lens Tilt (optical axis shift)
        tr_ltilt = QHBoxLayout(); tr_ltilt.setSpacing(1)
        self.lbl_lens_tilt = QLabel("Lens Tilt 0°")
        self.lbl_lens_tilt.setStyleSheet("font-weight:bold; color:#38bdf8;")
        tr_ltilt.addWidget(self.lbl_lens_tilt)
        b_llevel = QPushButton("0°"); b_llevel.setToolTip("Set camera lens tilt to 0°"); b_llevel.clicked.connect(self._reset_lens_tilt)
        tr_ltilt.addWidget(b_llevel)
        self.sec_cam.add_layout(tr_ltilt)
        self.sl_lens_tilt = self._slider(-89, 89, 0, self._on_lens_tilt)
        self.sl_lens_tilt.setToolTip("Tilt the camera view axis vertically without moving camera eye position")
        self.sec_cam.add_widget(self.sl_lens_tilt)

        # Camera Roll
        rr = QHBoxLayout(); rr.setSpacing(1)
        self.lbl_roll = QLabel("Roll 0°")
        rr.addWidget(self.lbl_roll)
        b_r0 = QPushButton("0°"); b_r0.setToolTip("Reset camera roll to 0°"); b_r0.clicked.connect(self._reset_roll)
        rr.addWidget(b_r0)
        self.sec_cam.add_layout(rr)
        self.sl_roll = self._slider(-180, 180, 0, self._on_roll)
        self.sl_roll.setToolTip("Camera Dutch angle roll (tilt sideways)")
        self.sec_cam.add_widget(self.sl_roll)

        # Quick angle presets grid
        cg = QGridLayout(); cg.setSpacing(1); cg.setContentsMargins(0, 0, 0, 0)
        for idx, (lbl, fn, tip) in enumerate([
            ("Frt", self.viewport.camera.set_front, "Look directly at front (Yaw 180°)"),
            ("3/4", self.viewport.camera.set_three_quarter, "Three-quarter dynamic view (Yaw 145°, Pitch 12°)"),
            ("R", self.viewport.camera.set_side_right, "Right side view (Yaw 90°)"),
            ("L", self.viewport.camera.set_side_left, "Left side view (Yaw 270°)"),
            ("Top", self.viewport.camera.set_top, "Top-down view (Pitch 90°)"),
            ("Rst", self._reset_camera_all, "Reset camera angles, tilt, and roll to default"),
        ]):
            b = QPushButton(lbl)
            b.setToolTip(tip)
            b.clicked.connect(self._cam_cb(fn))
            cg.addWidget(b, idx // 3, idx % 3)
        self.sec_cam.add_layout(cg)

        # FOV (Field of view)
        self.lbl_fov = QLabel("FOV 45° (43mm)")
        self.sec_cam.add_widget(self.lbl_fov)
        self.sl_fov = self._slider(10, 120, 45, self._on_fov)
        self.sl_fov.setToolTip("Field of view in degrees (scroll wheel over viewport also changes FOV)")
        self.sec_cam.add_widget(self.sl_fov)

        # Lens presets
        lr = QHBoxLayout(); lr.setSpacing(1)
        for nm, fv in [("14mm", 100), ("24mm", 73), ("50mm", 40), ("85mm", 24), ("135mm", 15)]:
            b = QPushButton(nm)
            b.setToolTip(f"Simulate {nm} camera focal length")
            b.clicked.connect(self._lens_cb(fv))
            lr.addWidget(b)
        self.sec_cam.add_layout(lr)

        # Distance & Screen Pan
        self.lbl_dist = QLabel("Dist 2.8")
        self.sec_cam.add_widget(self.lbl_dist)
        self.sl_dist = self._slider(1, 200, 28, self._on_dist)
        self.sl_dist.setToolTip("Camera distance to target (zoom)")
        self.sec_cam.add_widget(self.sl_dist)

        pan_row = QHBoxLayout(); pan_row.setSpacing(1)
        pan_row.addWidget(QLabel("Pan X/Y:"))
        self.spin_pan_x = self._dspin(-50.0, 50.0, 0.0, 0.1, self._on_pan_spins)
        self.spin_pan_x.setToolTip("Camera screen pan horizontal offset")
        self.spin_pan_y = self._dspin(-50.0, 50.0, 0.0, 0.1, self._on_pan_spins)
        self.spin_pan_y.setToolTip("Camera screen pan vertical offset")
        b_pan_rst = QPushButton("0"); b_pan_rst.setToolTip("Reset pan to (0, 0)"); b_pan_rst.clicked.connect(self._reset_pan)
        pan_row.addWidget(self.spin_pan_x); pan_row.addWidget(self.spin_pan_y); pan_row.addWidget(b_pan_rst)
        self.sec_cam.add_layout(pan_row)

        # Look-at Target XYZ
        tl = QLabel("Target XYZ:")
        tl.setStyleSheet("font-weight:bold;")
        self.sec_cam.add_widget(tl)
        tr = QHBoxLayout(); tr.setSpacing(1)
        self.spin_tx = self._dspin(-50, 50, 0.0, 0.1, self._on_target)
        self.spin_tx.setToolTip("Target world X position (scrub left/right)")
        self.spin_ty = self._dspin(-50, 50, 0.0, 0.1, self._on_target)
        self.spin_ty.setToolTip("Target world Y height position (scrub left/right)")
        self.spin_tz = self._dspin(-50, 50, 0.0, 0.1, self._on_target)
        self.spin_tz.setToolTip("Target world Z depth position (scrub left/right)")
        tr.addWidget(self.spin_tx); tr.addWidget(self.spin_ty); tr.addWidget(self.spin_tz)
        self.sec_cam.add_layout(tr)

        # Frame / Center / Origin quick actions (moved here from Model section)
        cam_frame_row = QHBoxLayout(); cam_frame_row.setSpacing(2)
        btn_cam_frame = QPushButton("🎯 Frame")
        btn_cam_frame.setToolTip("Frame 3D model in view (double-click viewport)")
        btn_cam_frame.clicked.connect(self._frame_view)
        cam_frame_row.addWidget(btn_cam_frame)
        btn_cam_center = QPushButton("⌖ Center")
        btn_cam_center.setToolTip("Move camera target to model center")
        btn_cam_center.clicked.connect(self._center_on_model)
        cam_frame_row.addWidget(btn_cam_center)
        btn_cam_origin = QPushButton("Origin")
        btn_cam_origin.setToolTip("Reset camera target to world origin (0,0,0)")
        btn_cam_origin.clicked.connect(self._center_origin)
        cam_frame_row.addWidget(btn_cam_origin)
        self.sec_cam.add_layout(cam_frame_row)

        L.addWidget(self.sec_cam)

        # =============================================================
        # SECTION 4: GROUND & CANVAS FRAMING
        # =============================================================
        self.sec_canvas = CollapsibleSection("GROUND & FRAMING", expanded=True)

        calib_row = QHBoxLayout(); calib_row.setSpacing(2)
        btn_ground = QPushButton("📐 Ground Rect...")
        btn_ground.setStyleSheet("background:#2e3440; color:#fef08a; font-weight:bold; padding:4px 6px; border:1px solid #4c566a;")
        btn_ground.setToolTip(
            "Draw or adjust 4 ground points on your canvas to solve camera angles and place the 3D model directly on top.\n"
            "This draws a rectangle if you already have drawn on your canvas an object that you want to have a 3D overhead so it quickly fits."
        )
        btn_ground.clicked.connect(self._open_ground_calibrator)
        calib_row.addWidget(btn_ground, 3)

        btn_full_canv = QPushButton("🖥️ Full")
        btn_full_canv.setStyleSheet("background:#1e293b; color:#e2e8f0; font-weight:bold; padding:4px 4px; border:1px solid #334155;")
        btn_full_canv.setToolTip("Match viewport ratio to full Krita canvas (clears frame limit)")
        btn_full_canv.clicked.connect(self._use_full_canvas)
        calib_row.addWidget(btn_full_canv, 1)

        btn_draw_frame = QPushButton("✏️ Draw Frame")
        btn_draw_frame.setStyleSheet("background:#1e293b; color:#93c5fd; font-weight:bold; padding:4px 4px; border:1px solid #2563eb;")
        btn_draw_frame.setToolTip("Define the frame of the 3D scene from active rectangular selection on canvas")
        btn_draw_frame.clicked.connect(self._draw_frame_action)
        calib_row.addWidget(btn_draw_frame, 2)
        self.sec_canvas.add_layout(calib_row)

        self.chk_use_frame = QCheckBox("Limit 3D to Canvas Frame")
        self.chk_use_frame.setChecked(False)
        self.chk_use_frame.setToolTip("Render 3D object only within this frame on Krita canvas (outside remains untouched)")
        self.chk_use_frame.stateChanged.connect(self._on_frame_toggle)
        self.sec_canvas.add_widget(self.chk_use_frame)

        fr_grid = QGridLayout(); fr_grid.setSpacing(1)
        fr_grid.addWidget(QLabel("X:"), 0, 0)
        self.spin_fx = self._ispin(0, 20000, 0, 10, self._on_frame_spins)
        self.spin_fx.setToolTip("Frame left pixel coordinate")
        fr_grid.addWidget(self.spin_fx, 0, 1)

        fr_grid.addWidget(QLabel("Y:"), 0, 2)
        self.spin_fy = self._ispin(0, 20000, 0, 10, self._on_frame_spins)
        self.spin_fy.setToolTip("Frame top pixel coordinate")
        fr_grid.addWidget(self.spin_fy, 0, 3)

        fr_grid.addWidget(QLabel("W:"), 1, 0)
        self.spin_fw = self._ispin(1, 20000, 800, 10, self._on_frame_spins)
        self.spin_fw.setToolTip("Frame width in pixels")
        fr_grid.addWidget(self.spin_fw, 1, 1)

        fr_grid.addWidget(QLabel("H:"), 1, 2)
        self.spin_fh = self._ispin(1, 20000, 600, 10, self._on_frame_spins)
        self.spin_fh.setToolTip("Frame height in pixels")
        fr_grid.addWidget(self.spin_fh, 1, 3)
        self.sec_canvas.add_layout(fr_grid)

        self.lbl_frame_info = QLabel("Full Canvas (No limits)")
        self.lbl_frame_info.setStyleSheet("color:#64748b; font-size:9px;")
        self.sec_canvas.add_widget(self.lbl_frame_info)

        self.lbl_status = QLabel("Ready")
        self.lbl_status.setStyleSheet("color:#94a3b8;font-size:9px;")
        self.lbl_status.setAlignment(Qt.AlignHCenter)
        self.sec_canvas.add_widget(self.lbl_status)

        L.addWidget(self.sec_canvas)

        # =============================================================
        # SECTION 5: 3D PERSPECTIVE GRIDS
        # =============================================================
        self.sec_grid = CollapsibleSection("3D PERSPECTIVE GRIDS", expanded=True)

        gr_toggles = QHBoxLayout(); gr_toggles.setSpacing(2)
        self.chk_grid_canvas = QCheckBox("Grid on Canvas")
        self.chk_grid_canvas.setToolTip("Draw 3D perspective grid directly onto the Krita canvas layer (with or without 3D model)")
        self.chk_grid_canvas.stateChanged.connect(self._on_grid_changed)
        gr_toggles.addWidget(self.chk_grid_canvas)

        self.chk_grid_viewport = QCheckBox("In Viewport")
        self.chk_grid_viewport.setChecked(True)
        self.chk_grid_viewport.setToolTip("Show perspective grid in 3D viewport")
        self.chk_grid_viewport.stateChanged.connect(self._on_grid_changed)
        gr_toggles.addWidget(self.chk_grid_viewport)
        self.sec_grid.add_layout(gr_toggles)

        hr_row = QHBoxLayout(); hr_row.setSpacing(2)
        self.chk_grid_horizon = QCheckBox("Horizon Line")
        self.chk_grid_horizon.setChecked(True)
        self.chk_grid_horizon.setToolTip("Draw guaranteed-visible eye-level horizon line across canvas")
        self.chk_grid_horizon.stateChanged.connect(self._on_grid_changed)
        hr_row.addWidget(self.chk_grid_horizon)

        self.chk_grid_ground = QCheckBox("Ground Grid")
        self.chk_grid_ground.setChecked(True)
        self.chk_grid_ground.setToolTip("Draw ground floor perspective grid squares")
        self.chk_grid_ground.stateChanged.connect(self._on_grid_changed)
        hr_row.addWidget(self.chk_grid_ground)

        self.chk_grid_ceiling = QCheckBox("Ceiling Grid (Above)")
        self.chk_grid_ceiling.setChecked(False)
        self.chk_grid_ceiling.setToolTip("Draw a matching ceiling grid above the scene at ceiling height")
        self.chk_grid_ceiling.stateChanged.connect(self._on_grid_changed)
        hr_row.addWidget(self.chk_grid_ceiling)
        self.sec_grid.add_layout(hr_row)

        # Grid parameters: Extent, Tile Size, Ceiling Height, Subdivisions
        g_grid = QGridLayout(); g_grid.setSpacing(1)
        g_grid.addWidget(QLabel("Tiles:"), 0, 0)
        self.spin_grid_extent = self._ispin(2, 60, 10, 1, self._on_grid_changed)
        self.spin_grid_extent.setToolTip("Number of grid tiles from origin in each direction (drag left/right to scrub)")
        g_grid.addWidget(self.spin_grid_extent, 0, 1)

        g_grid.addWidget(QLabel("Size:"), 0, 2)
        self.spin_grid_tile = self._dspin(0.05, 10.0, 0.5, 0.05, self._on_grid_changed)
        self.spin_grid_tile.setToolTip("Size of each square tile in 3D units (drag left/right to scrub)")
        g_grid.addWidget(self.spin_grid_tile, 0, 3)

        g_grid.addWidget(QLabel("Ceil H:"), 1, 0)
        self.spin_grid_cheight = self._dspin(0.5, 20.0, 2.5, 0.2, self._on_grid_changed)
        self.spin_grid_cheight.setToolTip("Height of ceiling grid above the floor in 3D units")
        g_grid.addWidget(self.spin_grid_cheight, 1, 1)

        g_grid.addWidget(QLabel("Subdiv:"), 1, 2)
        self.spin_grid_subdiv = self._ispin(1, 10, 1, 1, self._on_grid_changed)
        self.spin_grid_subdiv.setToolTip("Subdivisions per square tile")
        g_grid.addWidget(self.spin_grid_subdiv, 1, 3)
        self.sec_grid.add_layout(g_grid)

        # Vanishing extension & Height poles
        g_extra = QHBoxLayout(); g_extra.setSpacing(2)
        self.chk_grid_exceed = QCheckBox("Extend to Horizon")
        self.chk_grid_exceed.setChecked(True)
        self.chk_grid_exceed.setToolTip("Extend grid lines deep into the distance to vanishing points")
        self.chk_grid_exceed.stateChanged.connect(self._on_grid_changed)
        g_extra.addWidget(self.chk_grid_exceed)

        self.chk_grid_verticals = QCheckBox("Height Poles")
        self.chk_grid_verticals.setChecked(True)
        self.chk_grid_verticals.setToolTip("Draw vertical guide poles for 3D vertical perspective")
        self.chk_grid_verticals.stateChanged.connect(self._on_grid_changed)
        g_extra.addWidget(self.chk_grid_verticals)
        self.sec_grid.add_layout(g_extra)

        self.chk_grid_axis = QCheckBox("Color XYZ Axes (Red X, Blue Z, Green Y)")
        self.chk_grid_axis.setChecked(True)
        self.chk_grid_axis.setToolTip("Highlight primary 3D world axes with color")
        self.chk_grid_axis.stateChanged.connect(self._on_grid_changed)
        self.sec_grid.add_widget(self.chk_grid_axis)

        L.addWidget(self.sec_grid)

        # =============================================================
        # SECTION 6: STUDIO LIGHTING
        # =============================================================
        self.sec_light = CollapsibleSection("LIGHTING", expanded=False)

        sr = QHBoxLayout(); sr.setSpacing(4)
        self.light_sphere = SphereLightWidget()
        self.light_sphere.setToolTip("Drag the light point to adjust key light azimuth and elevation angle in real-time")
        self.light_sphere.light_changed.connect(self._on_sphere_light)
        self.light_sphere.interaction_ended.connect(self._on_interaction_ended)
        self.light_sphere.interaction_ended.connect(self._save_session)
        sr.addWidget(self.light_sphere)

        sc = QVBoxLayout(); sc.setSpacing(1)
        self.lbl_light = QLabel("Az:45 El:40")
        self.lbl_light.setStyleSheet("font-weight:bold;")
        sc.addWidget(self.lbl_light)
        self.chk_follow = QCheckBox("Follow Cam")
        self.chk_follow.setChecked(True)
        self.chk_follow.setToolTip("Key light follows camera orbit angle so front faces are always illuminated")
        self.chk_follow.stateChanged.connect(self._on_follow)
        sc.addWidget(self.chk_follow)
        rl = QPushButton("Reset Light")
        rl.setToolTip("Reset lighting to standard studio angle")
        rl.clicked.connect(self._reset_light)
        sc.addWidget(rl)
        sr.addLayout(sc)
        self.sec_light.add_layout(sr)

        self.lbl_amb = QLabel("Ambient 45%")
        self.sec_light.add_widget(self.lbl_amb)
        self.sl_amb = self._slider(0, 100, 45, self._on_amb)
        self.sl_amb.setToolTip("Adjust base ambient shadow brightness")
        self.sec_light.add_widget(self.sl_amb)

        self.lbl_diff = QLabel("Key 55%")
        self.sec_light.add_widget(self.lbl_diff)
        self.sl_diff = self._slider(0, 100, 55, self._on_diff)
        self.sl_diff.setToolTip("Adjust directional key light intensity")
        self.sec_light.add_widget(self.sl_diff)

        L.addWidget(self.sec_light)

        # =============================================================
        # SECTION 7: SETTINGS & PERFORMANCE
        # =============================================================
        self.sec_settings = CollapsibleSection("SETTINGS & PERFORMANCE", expanded=False)

        # Viewport UI elements toggles
        disp_hdr = QLabel("Viewport Display:")
        disp_hdr.setStyleSheet("font-weight:bold;")
        self.sec_settings.add_widget(disp_hdr)

        self.chk_show_overlay = QCheckBox("Show Right Overlay Buttons (Orbit, Pan, Zoom, Tilt)")
        self.chk_show_overlay.setChecked(True)
        self.chk_show_overlay.setToolTip("Show/hide the mini overlay buttons on the right edge of the viewport")
        self.chk_show_overlay.stateChanged.connect(self._on_toggle_overlay_buttons)
        self.sec_settings.add_widget(self.chk_show_overlay)

        self.chk_show_gizmo = QCheckBox("Show Bottom-Left 3D Axis Gizmo")
        self.chk_show_gizmo.setChecked(True)
        self.chk_show_gizmo.setToolTip("Show/hide the XYZ axis orientation gizmo in viewport bottom-left corner")
        self.chk_show_gizmo.stateChanged.connect(self._on_toggle_gizmo)
        self.sec_settings.add_widget(self.chk_show_gizmo)

        self.chk_show_frame_guide = QCheckBox("Show Canvas Frame Guide")
        self.chk_show_frame_guide.setChecked(True)
        self.chk_show_frame_guide.setToolTip("Show canvas aspect ratio dashed framing border in viewport")
        self.chk_show_frame_guide.stateChanged.connect(self._on_toggle_frame_guide)
        self.sec_settings.add_widget(self.chk_show_frame_guide)

        # Sticky viewport setting (state initialized by _restore_session)
        self.chk_sticky_viewport = QCheckBox("Sticky Viewport (Always Visible on Scroll)")
        self.chk_sticky_viewport.setToolTip("When enabled, the 3D viewport stays pinned at the top of the docker and is always visible even when you scroll down through the controls")
        self.chk_sticky_viewport.stateChanged.connect(self._on_toggle_sticky_viewport)
        self.sec_settings.add_widget(self.chk_sticky_viewport)

        # Navigation direction preferences — split into X (L/R) and Y (U/D)
        nav_pref_row = QHBoxLayout(); nav_pref_row.setSpacing(2)
        self.chk_invert_pan = QCheckBox("Invert Pan")
        self.chk_invert_pan.setChecked(True)
        self.chk_invert_pan.setToolTip("Invert mouse dragging direction for viewport pan")
        self.chk_invert_pan.stateChanged.connect(self._on_toggle_invert_pan)
        nav_pref_row.addWidget(self.chk_invert_pan)
        self.sec_settings.add_layout(nav_pref_row)

        orbit_inv_row = QHBoxLayout(); orbit_inv_row.setSpacing(2)
        self.chk_invert_orbit_x = QCheckBox("Invert Orbit L/R")
        self.chk_invert_orbit_x.setChecked(True)
        self.chk_invert_orbit_x.setToolTip("Invert LEFT/RIGHT (yaw) mouse direction when orbiting")
        self.chk_invert_orbit_x.stateChanged.connect(self._on_toggle_invert_orbit_x)
        orbit_inv_row.addWidget(self.chk_invert_orbit_x)

        self.chk_invert_orbit_y = QCheckBox("Invert Orbit U/D")
        self.chk_invert_orbit_y.setChecked(False)
        self.chk_invert_orbit_y.setToolTip("Invert UP/DOWN (pitch) mouse direction when orbiting")
        self.chk_invert_orbit_y.stateChanged.connect(self._on_toggle_invert_orbit_y)
        orbit_inv_row.addWidget(self.chk_invert_orbit_y)
        self.sec_settings.add_layout(orbit_inv_row)

        # Opacities
        self.lbl_grid_opac = QLabel("Grid Opacity: 85%")
        self.sec_settings.add_widget(self.lbl_grid_opac)
        self.sl_grid_opac = self._slider(10, 100, 85, self._on_grid_opacity)
        self.sl_grid_opac.setToolTip("Perspective grid lines opacity")
        self.sec_settings.add_widget(self.sl_grid_opac)

        self.lbl_horizon_opac = QLabel("Horizon Opacity: 86%")
        self.sec_settings.add_widget(self.lbl_horizon_opac)
        self.sl_horizon_opac = self._slider(10, 100, 86, self._on_horizon_opacity)
        self.sl_horizon_opac.setToolTip("Horizon line opacity")
        self.sec_settings.add_widget(self.sl_horizon_opac)

        # Background color & Transparent background
        bg_hdr = QLabel("Background Color:")
        bg_hdr.setStyleSheet("font-weight:bold;")
        self.sec_settings.add_widget(bg_hdr)

        bg_row = QHBoxLayout(); bg_row.setSpacing(2)
        self.chk_transp = QCheckBox("Transparent Layer BG (T.BG)")
        self.chk_transp.setChecked(True)
        self.chk_transp.setToolTip("Render 3D object onto Krita layer with transparent background")
        self.chk_transp.stateChanged.connect(self._live_sync)
        self.chk_transp.stateChanged.connect(self._schedule_save)
        bg_row.addWidget(self.chk_transp, 1)

        self.btn_bg_col = QPushButton("🎨 BG Color")
        self.btn_bg_col.setToolTip("Pick solid background color for Krita layer (used when T.BG is unchecked)")
        self.btn_bg_col.clicked.connect(self._pick_bg_color)
        bg_row.addWidget(self.btn_bg_col, 0)
        self.sec_settings.add_layout(bg_row)

        # Performance: Render Quality & Refresh Rate Debounce
        perf_hdr = QLabel("Performance & Live Refresh:")
        perf_hdr.setStyleSheet("font-weight:bold;")
        self.sec_settings.add_widget(perf_hdr)

        q_row = QHBoxLayout(); q_row.setSpacing(2)
        q_row.addWidget(QLabel("Quality:"))
        self.combo_quality = QComboBox()
        self.combo_quality.addItems(["⚡ Fast (Draft / Low CPU)", "⚖️ Balanced (Standard)", "💎 High (Super-Sampled)"])
        self.combo_quality.setCurrentIndex(1)
        self.combo_quality.setToolTip("Render quality: Fast reduces CPU load on huge canvases, High enables super-sampling")
        self.combo_quality.currentIndexChanged.connect(self._on_quality_changed)
        q_row.addWidget(self.combo_quality, 1)
        self.sec_settings.add_layout(q_row)

        rate_row = QHBoxLayout(); rate_row.setSpacing(2)
        rate_row.addWidget(QLabel("Refresh Rate (ms):"))
        self.spin_debounce = self._ispin(30, 1000, 120, 10, self._on_debounce_changed)
        self.spin_debounce.setToolTip("Delay in milliseconds before updating Krita canvas layer when dragging (debounce delay)")
        rate_row.addWidget(self.spin_debounce, 1)
        self.sec_settings.add_layout(rate_row)

        # Live sync toggle & manual stamp
        sync_row = QHBoxLayout(); sync_row.setSpacing(2)
        self.chk_live = QCheckBox("Live Sync to Canvas")
        self.chk_live.setChecked(True)
        self.chk_live.setToolTip("Automatically update the Krita canvas paint layer on every camera adjustment")
        self.chk_live.stateChanged.connect(self._live_sync)
        self.chk_live.stateChanged.connect(self._schedule_save)
        sync_row.addWidget(self.chk_live, 1)

        self.btn_stamp = QPushButton("⚡ Stamp Now")
        self.btn_stamp.setStyleSheet("background:#2563eb; color:#fff; font-weight:bold; padding:3px 6px;")
        self.btn_stamp.setToolTip("Manually stamp 3D scene onto active Krita layer right now")
        self.btn_stamp.clicked.connect(self._stamp)
        sync_row.addWidget(self.btn_stamp, 0)
        self.sec_settings.add_layout(sync_row)

        L.addWidget(self.sec_settings)

        L.addStretch(1)

        # Connect all collapsible section toggles to schedule auto-save
        for sec in (self.sec_viewport, self.sec_presets, self.sec_model, self.sec_cam,
                    self.sec_canvas, self.sec_grid, self.sec_light, self.sec_settings):
            sec.toggled.connect(self._schedule_save)

        # Initialize UI sync
        self._sync_ui()
        self._match_ratio()
        self._populate_presets_combo()

        # Restore last saved session state (after all widgets are built)
        self._restore_session()

    # -----------------------------------------------------------------
    # Helper widget builders with tooltips
    # -----------------------------------------------------------------
    def _slider(self, mn, mx, val, cb):
        s = QSlider(Qt.Horizontal)
        s.setRange(mn, mx)
        s.setValue(val)
        s.valueChanged.connect(cb)
        s.valueChanged.connect(self._schedule_save)
        s.sliderReleased.connect(self._save_session)
        return s

    def _dspin(self, mn, mx, val, step, cb):
        s = ScrubbableDoubleSpinBox()
        s.setRange(mn, mx)
        s.setSingleStep(step)
        s.setValue(val)
        s.valueChanged.connect(cb)
        s.valueChanged.connect(self._schedule_save)
        return s

    def _ispin(self, mn, mx, val, step, cb):
        s = ScrubbableSpinBox()
        s.setRange(mn, mx)
        s.setSingleStep(step)
        s.setValue(val)
        s.valueChanged.connect(cb)
        s.valueChanged.connect(self._schedule_save)
        return s

    # -----------------------------------------------------------------
    # Primitives & Model Loading
    # -----------------------------------------------------------------
    def _setup_primitives_menu(self):
        menu = QMenu(self.btn_primitives)
        menu.setStyleSheet("QMenu { background:#1e293b; color:#e2e8f0; font-size:11px; } QMenu::item:selected { background:#2563eb; }")

        base_dir = os.path.dirname(os.path.abspath(__file__))
        prim_dir = os.path.join(base_dir, "3D-Primitive")

        if os.path.isdir(prim_dir):
            files = sorted(os.listdir(prim_dir))
            for f in files:
                ext = os.path.splitext(f)[1].lower()
                if ext in ('.obj', '.stl', '.glb', '.gltf'):
                    path = os.path.join(prim_dir, f)
                    action_name = os.path.splitext(f)[0]
                    icon_prefix = "👤 " if "asaro" in f.lower() or "head" in f.lower() else "📦 "
                    action = menu.addAction(f"{icon_prefix}{action_name}")
                    action.triggered.connect(lambda checked, p=path: self._load_file(p))

        self.btn_primitives.setMenu(menu)

    def _import(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Import 3D Model", "",
            "3D Files (*.obj *.stl *.glb *.gltf);;OBJ (*.obj);;STL (*.stl);;GLB/glTF (*.glb *.gltf);;All Files (*)"
        )
        if path:
            self._load_file(path)

    def _load_file(self, path, frame=True):
        try:
            m = load_3d_file(path)
            self.mesh = m
            self.mesh_path = path
            self.viewport.set_mesh(m)
            fn = os.path.basename(path)
            self.lbl_model.setText(f"{fn}\n{len(m.vertices)} verts, {len(m.faces)} faces")
            self.lbl_status.setText(f"Loaded {fn}")
            if frame:
                self.viewport.frame_object()
                self._sync_ui()
                self._live_sync()
            self._save_session()
        except Exception as e:
            self.lbl_model.setText(f"Load error: {e}")
            self.lbl_status.setText("Failed to load 3D file")

    _load_mesh_file = _load_file

    # -----------------------------------------------------------------
    # Color Pickers
    # -----------------------------------------------------------------
    def _pick_model_color(self):
        c = QColorDialog.getColor(self.viewport.renderer.base_color, self, "Select 3D Model Material Color")
        if c.isValid():
            self.viewport.renderer.base_color = c
            self._update_model_color_button()
            self.viewport.update()
            self._live_sync()
            self._save_session()

    def _update_model_color_button(self):
        col = self.viewport.renderer.base_color
        hex_c = col.name()
        self.btn_model_color.setStyleSheet(
            f"QPushButton {{ background: {hex_c}; border: 2px solid #ffffff; border-radius: 3px; font-weight: bold; }}"
            f"QPushButton:hover {{ border-color: #38bdf8; }}"
        )

    def _pick_wire_col(self):
        c = QColorDialog.getColor(self.viewport.renderer.wire_color, self, "Select Wireframe Color")
        if c.isValid():
            self.viewport.renderer.wire_color = c
            self.viewport.update()
            self._live_sync()
            self._save_session()

    def _pick_contour_col(self):
        c = QColorDialog.getColor(self.viewport.renderer.contour_color, self, "Select Contour Outline Color")
        if c.isValid():
            self.viewport.renderer.contour_color = c
            self.viewport.update()
            self._live_sync()
            self._save_session()

    def _pick_bg_color(self):
        c = QColorDialog.getColor(self.custom_bg_color, self, "Select Canvas Layer Solid Background Color")
        if c.isValid():
            self.custom_bg_color = c
            self.btn_bg_col.setStyleSheet(f"background:{c.name()}; color:#000;")
            self.viewport.update()
            self._live_sync()
            self._save_session()

    # -----------------------------------------------------------------
    # Camera Presets & Navigation
    # -----------------------------------------------------------------
    def _cam_cb(self, fn):
        def handler():
            fn()
            self._sync_ui()
            self.viewport.update()
            self._live_sync()
            self._save_session()
        return handler

    def _lens_cb(self, fov):
        def handler():
            self.viewport.camera.fov = float(fov)
            self._update_fov_label(fov)
            self.sl_fov.blockSignals(True)
            self.sl_fov.setValue(int(fov))
            self.sl_fov.blockSignals(False)
            self.viewport.update()
            self._live_sync()
            self._save_session()
        return handler

    def _reset_camera_all(self):
        self.viewport.camera.reset()
        self._sync_ui()
        self.viewport.update()
        self._live_sync()
        self._save_session()

    def _reset_pitch(self):
        self.viewport.camera.pitch = 0.0
        self._sync_ui()
        self.viewport.update()
        self._live_sync()
        self._save_session()

    def _reset_lens_tilt(self):
        self.viewport.camera.tilt = 0.0
        self._sync_ui()
        self.viewport.update()
        self._live_sync()
        self._save_session()

    def _reset_roll(self):
        self.viewport.camera.roll = 0.0
        self._sync_ui()
        self.viewport.update()
        self._live_sync()
        self._save_session()

    def _reset_pan(self):
        self.viewport.camera.pan_x = 0.0
        self.viewport.camera.pan_y = 0.0
        self.spin_pan_x.blockSignals(True); self.spin_pan_x.setValue(0.0); self.spin_pan_x.blockSignals(False)
        self.spin_pan_y.blockSignals(True); self.spin_pan_y.setValue(0.0); self.spin_pan_y.blockSignals(False)
        self.viewport.update()
        self._live_sync()
        self._save_session()

    def _frame_view(self):
        self.viewport.frame_object()
        self.viewport.camera_changed.emit()
        self._sync_ui()
        self.viewport.update()
        self._live_sync()
        self.lbl_status.setText("Framed object in view")
        self._save_session()

    def _center_on_model(self):
        # Center camera and target directly on model
        if self.mesh and hasattr(self.mesh, 'center'):
            cx = self.mesh.center.x()
            cy = self.mesh.center.y()
            cz = self.mesh.center.z()
        else:
            cx = cy = cz = 0.0

        self.spin_tx.setValue(cx)
        self.spin_ty.setValue(cy)
        self.spin_tz.setValue(cz)
        self.viewport.camera.target_x = cx
        self.viewport.camera.target_y = cy
        self.viewport.camera.target_z = cz
        self.viewport.camera.pan_x = 0.0
        self.viewport.camera.pan_y = 0.0
        self.viewport.frame_object()
        self.viewport.camera_changed.emit()
        self._sync_ui()
        self.viewport.update()
        self._live_sync()
        self.lbl_status.setText("Model centered in view")
        self._save_session()

    def _center_origin(self):
        self.spin_tx.setValue(0.0)
        self.spin_ty.setValue(0.0)
        self.spin_tz.setValue(0.0)
        self.viewport.camera.target_x = 0.0
        self.viewport.camera.target_y = 0.0
        self.viewport.camera.target_z = 0.0
        self.viewport.camera.pan_x = 0.0
        self.viewport.camera.pan_y = 0.0
        self.viewport.camera_changed.emit()
        self._sync_ui()
        self.viewport.update()
        self._live_sync()
        self.lbl_status.setText("Target reset to origin")
        self._save_session()

    def _update_proj_controls_visibility(self, text):
        is_fisheye    = (text == ProjectionMode.FISHEYE)
        is_artist_5vp = (text == ProjectionMode.ARTIST_5VP)
        is_curv_other = (text in (ProjectionMode.ARTIST_5VP, ProjectionMode.CYLINDRICAL))
        is_any_curv   = is_fisheye or is_artist_5vp or is_curv_other
        if hasattr(self, 'w_fisheye_group'):
            self.w_fisheye_group.setVisible(is_fisheye)
        if hasattr(self, 'lbl_curv'):
            self.lbl_curv.setVisible(is_curv_other)
        if hasattr(self, 'sl_curv'):
            self.sl_curv.setVisible(is_curv_other)
        if hasattr(self, 'sl_fov'):
            self.sl_fov.setEnabled(text != ProjectionMode.ORTHOGRAPHIC)
        # Also sync camera state immediately
        self.viewport.camera.projection_mode = text
        self.viewport.camera.orthographic = (text == ProjectionMode.ORTHOGRAPHIC)

    def _on_proj_mode(self, text):
        self._update_proj_controls_visibility(text)
        self.viewport.update()    # force repaint so viewport never appears empty
        self._live_sync()

    # -----------------------------------------------------------------
    # Presets System
    # -----------------------------------------------------------------
    def _populate_presets_combo(self, select_name=None):
        if not hasattr(self, 'combo_presets'):
            return
        self._all_presets = load_all_presets()
        self.combo_presets.blockSignals(True)
        self.combo_presets.clear()
        names = list(self._all_presets.keys())
        self.combo_presets.addItems(names)
        if select_name and select_name in names:
            self.combo_presets.setCurrentText(select_name)
        elif "Default Studio 3/4" in names:
            self.combo_presets.setCurrentText("Default Studio 3/4")
        self.combo_presets.blockSignals(False)

    def _on_preset_activated(self, index):
        name = self.combo_presets.itemText(index)
        if not name:
            return
        preset = self._all_presets.get(name)
        if preset:
            self._apply_preset(preset, name)

    def _apply_preset(self, p, name="Preset"):
        if not p:
            return
        c = self.viewport.camera
        # 1. Projection mode
        pm = p.get("proj_mode", "Perspective")
        if pm in ProjectionMode.ALL:
            c.projection_mode = pm
            if hasattr(self, 'combo_proj'):
                self.combo_proj.blockSignals(True)
                self.combo_proj.setCurrentText(pm)
                self.combo_proj.blockSignals(False)
            self._update_proj_controls_visibility(pm)

        # 2. Camera parameters
        c.fov = float(p.get("fov", c.fov))
        c.distance = float(p.get("distance", c.distance))
        c.yaw = float(p.get("yaw", c.yaw))
        c.pitch = float(p.get("pitch", c.pitch))
        c.roll = float(p.get("roll", 0.0))
        c.tilt = float(p.get("tilt", 0.0))
        c.pan_x = float(p.get("pan_x", 0.0))
        c.pan_y = float(p.get("pan_y", 0.0))

        # 3. Fisheye / Curvilinear
        if "curvature" in p:
            c.curvature = float(p["curvature"])
            if hasattr(self, 'sl_curv'):
                self.sl_curv.blockSignals(True); self.sl_curv.setValue(int(c.curvature * 100)); self.sl_curv.blockSignals(False)
            if hasattr(self, 'sl_fish_curv'):
                self.sl_fish_curv.blockSignals(True); self.sl_fish_curv.setValue(int(c.curvature * 100)); self.sl_fish_curv.blockSignals(False)
            if hasattr(self, 'lbl_curv'):
                self.lbl_curv.setText(f"Curvature {int(c.curvature * 100)}%")
            if hasattr(self, 'lbl_fish_curv'):
                self.lbl_fish_curv.setText(f"Curvature Strength: {int(c.curvature * 100)}%")

        if "fisheye_fov" in p:
            c.fisheye_fov = float(p["fisheye_fov"])
            if hasattr(self, 'sl_fish_fov'):
                self.sl_fish_fov.blockSignals(True); self.sl_fish_fov.setValue(int(c.fisheye_fov)); self.sl_fish_fov.blockSignals(False)
            if hasattr(self, 'lbl_fish_fov'):
                self.lbl_fish_fov.setText(f"Fisheye FOV: {int(c.fisheye_fov)}°")

        if "fisheye_zoom" in p:
            c.fisheye_zoom = float(p["fisheye_zoom"])
            if hasattr(self, 'sl_fish_zoom'):
                self.sl_fish_zoom.blockSignals(True); self.sl_fish_zoom.setValue(int(c.fisheye_zoom * 100)); self.sl_fish_zoom.blockSignals(False)
            if hasattr(self, 'lbl_fish_zoom'):
                self.lbl_fish_zoom.setText(f"Lens Zoom: {int(c.fisheye_zoom * 100)}%")

        if "lens_type" in p:
            c.fisheye_lens_type = p["lens_type"]
            if hasattr(self, 'combo_lens_type'):
                self.combo_lens_type.blockSignals(True)
                for idx in range(self.combo_lens_type.count()):
                    if self.combo_lens_type.itemText(idx).startswith(p["lens_type"]):
                        self.combo_lens_type.setCurrentIndex(idx)
                        break
                self.combo_lens_type.blockSignals(False)

        # 4. Grid settings
        gs = self.viewport.grid_settings
        if "grid_enabled_canvas" in p:
            gs.enabled = bool(p["grid_enabled_canvas"])
            self.chk_grid_canvas.blockSignals(True); self.chk_grid_canvas.setChecked(gs.enabled); self.chk_grid_canvas.blockSignals(False)
        if "grid_viewport" in p:
            gs.show_in_viewport = bool(p["grid_viewport"])
            self.chk_grid_viewport.blockSignals(True); self.chk_grid_viewport.setChecked(gs.show_in_viewport); self.chk_grid_viewport.blockSignals(False)
        if "grid_ground" in p:
            gs.ground_enabled = bool(p["grid_ground"])
            self.chk_grid_ground.blockSignals(True); self.chk_grid_ground.setChecked(gs.ground_enabled); self.chk_grid_ground.blockSignals(False)
        if "grid_ceiling" in p:
            gs.ceiling_enabled = bool(p["grid_ceiling"])
            self.chk_grid_ceiling.blockSignals(True); self.chk_grid_ceiling.setChecked(gs.ceiling_enabled); self.chk_grid_ceiling.blockSignals(False)
        if "ceiling_height" in p:
            gs.ceiling_height = float(p["ceiling_height"])
            self.spin_grid_cheight.blockSignals(True); self.spin_grid_cheight.setValue(gs.ceiling_height); self.spin_grid_cheight.blockSignals(False)
        if "horizon_enabled" in p:
            gs.horizon_enabled = bool(p["horizon_enabled"])
            self.chk_grid_horizon.blockSignals(True); self.chk_grid_horizon.setChecked(gs.horizon_enabled); self.chk_grid_horizon.blockSignals(False)
        if "grid_extent" in p:
            gs.grid_extent = int(p["grid_extent"])
            self.spin_grid_extent.blockSignals(True); self.spin_grid_extent.setValue(gs.grid_extent); self.spin_grid_extent.blockSignals(False)
        if "tile_size" in p:
            gs.tile_size = float(p["tile_size"])
            self.spin_grid_tile.blockSignals(True); self.spin_grid_tile.setValue(gs.tile_size); self.spin_grid_tile.blockSignals(False)
        if "subdivisions" in p:
            gs.subdivisions = int(p["subdivisions"])
            self.spin_grid_subdiv.blockSignals(True); self.spin_grid_subdiv.setValue(gs.subdivisions); self.spin_grid_subdiv.blockSignals(False)
        if "exceed_lines" in p:
            gs.exceed_lines = bool(p["exceed_lines"])
            self.chk_grid_exceed.blockSignals(True); self.chk_grid_exceed.setChecked(gs.exceed_lines); self.chk_grid_exceed.blockSignals(False)
        if "vertical_lines" in p:
            gs.vertical_lines = bool(p["vertical_lines"])
            self.chk_grid_verticals.blockSignals(True); self.chk_grid_verticals.setChecked(gs.vertical_lines); self.chk_grid_verticals.blockSignals(False)
        if "vertical_height" in p:
            gs.vertical_height = float(p["vertical_height"])
            if hasattr(self, 'spin_grid_vheight'):
                self.spin_grid_vheight.blockSignals(True); self.spin_grid_vheight.setValue(gs.vertical_height); self.spin_grid_vheight.blockSignals(False)
        if "axis_colors" in p:
            gs.axis_colors = bool(p["axis_colors"])
            self.chk_grid_axis.blockSignals(True); self.chk_grid_axis.setChecked(gs.axis_colors); self.chk_grid_axis.blockSignals(False)

        # 5. Lighting
        if "light_az" in p:
            self.viewport.lighting.azimuth = float(p["light_az"])
            self.light_sphere.azimuth = float(p["light_az"])
        if "light_el" in p:
            self.viewport.lighting.elevation = float(p["light_el"])
            self.light_sphere.elevation = float(p["light_el"])
        self.light_sphere.update()
        self.lbl_light.setText(f"Az:{int(self.viewport.lighting.azimuth)} El:{int(self.viewport.lighting.elevation)}")

        # 6. Shading Style
        if "render_style" in p and hasattr(self, 'combo_style'):
            self.combo_style.blockSignals(True)
            self.combo_style.setCurrentText(p["render_style"])
            self.combo_style.blockSignals(False)
            self.viewport.set_render_style(p["render_style"])

        self.viewport.camera_changed.emit()
        self._sync_ui()
        self.viewport.update()
        self._live_sync()
        self.lbl_status.setText(f"Loaded preset: {name}")

    def _save_custom_preset(self):
        text, ok = QInputDialog.getText(self, "Save Preset", "Enter a name for this preset:")
        if not ok or not text.strip():
            return
        name = text.strip()
        c = self.viewport.camera
        gs = self.viewport.grid_settings
        preset = {
            "proj_mode": c.projection_mode,
            "fov": c.fov,
            "distance": c.distance,
            "yaw": c.yaw,
            "pitch": c.pitch,
            "roll": c.roll,
            "tilt": c.tilt,
            "pan_x": c.pan_x,
            "pan_y": c.pan_y,
            "curvature": c.curvature,
            "fisheye_fov": getattr(c, 'fisheye_fov', 180.0),
            "fisheye_zoom": getattr(c, 'fisheye_zoom', 1.0),
            "lens_type": getattr(c, 'fisheye_lens_type', 'Stereographic'),
            "grid_enabled_canvas": gs.enabled,
            "grid_viewport": gs.show_in_viewport,
            "grid_ground": gs.ground_enabled,
            "grid_ceiling": gs.ceiling_enabled,
            "ceiling_height": gs.ceiling_height,
            "horizon_enabled": gs.horizon_enabled,
            "grid_extent": gs.grid_extent,
            "tile_size": gs.tile_size,
            "subdivisions": gs.subdivisions,
            "exceed_lines": gs.exceed_lines,
            "vertical_lines": gs.vertical_lines,
            "vertical_height": getattr(gs, 'vertical_height', 2.0),
            "axis_colors": gs.axis_colors,
            "render_style": self.combo_style.currentText() if hasattr(self, 'combo_style') else "Shaded + Wireframe",
            "light_az": self.viewport.lighting.azimuth,
            "light_el": self.viewport.lighting.elevation,
        }
        save_custom_preset_to_disk(name, preset)
        self._populate_presets_combo(select_name=name)
        self.lbl_status.setText(f"Saved custom preset: {name}")

    def _delete_custom_preset(self):
        name = self.combo_presets.currentText()
        if not name:
            return
        if name in BUILTIN_PRESETS:
            QMessageBox.information(self, "Preset Protected", f"'{name}' is a built-in preset and cannot be deleted.")
            return
        reply = QMessageBox.question(self, "Delete Preset", f"Delete custom preset '{name}'?",
                                     QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if reply == QMessageBox.Yes:
            delete_custom_preset_from_disk(name)
            self._populate_presets_combo()
            self.lbl_status.setText(f"Deleted preset: {name}")

    def _open_manual(self):
        manual_path = os.path.join(os.path.dirname(__file__), "Manual.html")
        if os.path.exists(manual_path):
            QDesktopServices.openUrl(QUrl.fromLocalFile(manual_path))
        else:
            QMessageBox.information(self, "3D Layer Manual", "Manual file not found.")

    def _on_curvature(self, v):
        k = v / 100.0
        self.viewport.camera.curvature = k
        self.lbl_curv.setText(f"Curvature {int(v)}%")
        self.viewport.update()
        self._live_sync()

    def _on_fish_lens_changed(self, text):
        """Change fisheye mathematical formula / lens type."""
        lens_type = text.split()[0]
        self.viewport.camera.fisheye_lens_type = lens_type
        self.viewport.update()
        self._live_sync()

    def _on_fish_fov(self, v):
        """Fisheye angle of view in degrees."""
        self.viewport.camera.fisheye_fov = float(v)
        self.lbl_fish_fov.setText(f"Fisheye FOV: {int(v)}°")
        self.viewport.update()
        self._live_sync()

    def _set_fish_fov_preset(self, val):
        self.sl_fish_fov.setValue(val)

    def _on_fish_curv(self, v):
        """Curvature strength for fisheye."""
        self.viewport.camera.curvature = v / 100.0
        self.lbl_fish_curv.setText(f"Curvature Strength: {int(v)}%")
        self.viewport.update()
        self._live_sync()

    def _on_toggle_fish_circle(self, state):
        self.viewport.camera.fisheye_crop_circle = (state == Qt.Checked)
        self.viewport.update()
        self._live_sync()

    def _on_fish_zoom(self, v):
        self.viewport.camera.fisheye_zoom = v / 100.0
        self.lbl_fish_zoom.setText(f"Lens Zoom: {int(v)}%")
        self.viewport.update()
        self._live_sync()

    def _on_cam_mode(self, text):
        self.viewport.set_camera_mode(text)
        self.lbl_status.setText(f"Navigation: {text}")

    def _on_fov(self, v):
        self.viewport.camera.fov = float(v)
        self._update_fov_label(v)
        self.viewport.update()
        self._live_sync()

    def _on_dist(self, v):
        self.viewport.camera.distance = v / 10.0
        self.lbl_dist.setText(f"Dist {v/10:.1f}")
        self.viewport.update()
        self._live_sync()

    def _on_tilt(self, v):
        self.viewport.camera.pitch = float(v)
        self.lbl_tilt.setText(f"Orbit Pitch {v}°")
        self.viewport.update()
        self._live_sync()

    def _on_yaw(self, v):
        self.viewport.camera.yaw = float(v)
        self.lbl_yaw.setText(f"Orbit Yaw {v}°")
        self.viewport.update()
        self._live_sync()

    def _on_lens_tilt(self, v):
        self.viewport.camera.tilt = float(v)
        self.lbl_lens_tilt.setText(f"Lens Tilt {v}°")
        self.viewport.update()
        self._live_sync()

    def _on_roll(self, v):
        self.viewport.camera.roll = float(v)
        self.lbl_roll.setText(f"Roll {v}°")
        self.viewport.update()
        self._live_sync()

    def _on_pan_spins(self):
        self.viewport.camera.pan_x = self.spin_pan_x.value()
        self.viewport.camera.pan_y = self.spin_pan_y.value()
        self.viewport.update()
        self._live_sync()

    def _on_target(self):
        self.viewport.camera.target_x = self.spin_tx.value()
        self.viewport.camera.target_y = self.spin_ty.value()
        self.viewport.camera.target_z = self.spin_tz.value()
        self.viewport.update()
        self._live_sync()

    # -----------------------------------------------------------------
    # Style & Shading
    # -----------------------------------------------------------------
    def _on_style(self, text):
        self.viewport.set_render_style(text)
        self.viewport.update()
        self._live_sync()
        self._schedule_save()

    def _on_wire_cull(self, state):
        self.viewport.renderer.wireframe_backface_culling = (state == Qt.Checked)
        self.viewport.update()
        self._live_sync()
        self._schedule_save()

    def _on_hide_coplanar(self, state):
        self.viewport.renderer.hide_coplanar_edges = (state == Qt.Checked)
        self.viewport.update()
        self._live_sync()
        self._schedule_save()

    def _on_wire_w(self, v):
        w = v / 10.0
        self.viewport.renderer.wire_width = w
        self.lbl_wire.setText(f"Wire {w:.1f}")
        self.viewport.update()
        self._live_sync()

    def _on_contour_w(self, v):
        t = v / 10.0
        self.viewport.renderer.contour_width = t
        self.lbl_contour.setText(f"Contour {t:.1f}" if t > 0.05 else "Contour Off")
        self.viewport.update()
        self._live_sync()

    # -----------------------------------------------------------------
    # Perspective Grid & Horizon
    # -----------------------------------------------------------------
    def _on_grid_changed(self):
        gs = self.viewport.grid_settings
        gs.enabled = self.chk_grid_canvas.isChecked()
        gs.show_in_viewport = self.chk_grid_viewport.isChecked()
        gs.horizon_enabled = self.chk_grid_horizon.isChecked()
        gs.ground_enabled = self.chk_grid_ground.isChecked()
        gs.ceiling_enabled = self.chk_grid_ceiling.isChecked()
        gs.ceiling_height = self.spin_grid_cheight.value()
        gs.grid_extent = self.spin_grid_extent.value()
        gs.tile_size = self.spin_grid_tile.value()
        gs.subdivisions = self.spin_grid_subdiv.value()
        gs.exceed_lines = self.chk_grid_exceed.isChecked()
        gs.vertical_lines = self.chk_grid_verticals.isChecked()
        gs.axis_colors = self.chk_grid_axis.isChecked()
        self.viewport.update()
        self._live_sync()
        self._schedule_save()

    # -----------------------------------------------------------------
    # Ground Perspective Calibrator Dialog
    # -----------------------------------------------------------------
    def _open_ground_calibrator(self):
        snapshot = CanvasSyncManager.get_canvas_snapshot()
        active_frame = self.frame_rect if (self.chk_use_frame.isChecked() and self.frame_rect) else None
        dlg = GroundCalibratorDialog(
            bg_image=snapshot,
            mesh=self.mesh,
            camera=self.viewport.camera,
            lighting=self.viewport.lighting,
            renderer=self.viewport.renderer,
            frame_rect=active_frame,
            parent=self
        )
        sel = CanvasSyncManager.get_active_selection_rect()
        doc_info = CanvasSyncManager.get_document_info()
        if sel and doc_info:
            dlg.calibrator_widget.set_from_rect(
                sel[0], sel[1], sel[2], sel[3],
                doc_info["width"], doc_info["height"]
            )
        dlg.applied.connect(self._on_ground_calibrator_applied)
        dlg.exec_()

    def _on_ground_calibrator_applied(self, sol):
        c = self.viewport.camera
        c.yaw = sol.get("yaw", c.yaw)
        c.pitch = sol.get("pitch", c.pitch)
        c.roll = sol.get("roll", c.roll)
        c.tilt = 0.0
        c.fov = sol.get("fov", c.fov)
        c.distance = sol.get("distance", c.distance)
        c.pan_x = sol.get("pan_x", c.pan_x)
        c.pan_y = sol.get("pan_y", c.pan_y)
        if "target_x" in sol:
            c.target_x = sol["target_x"]
            c.target_y = sol["target_y"]
            c.target_z = sol["target_z"]
        self._sync_ui()
        self._sync_target_spins()
        self.viewport.update()
        self._live_sync()
        self.lbl_status.setText(f"Ground calibrated: Tilt {c.pitch:.1f}° Yaw {c.yaw:.1f}° Roll {c.roll:.1f}° (Placed on ground)")
        self._save_session()

    # -----------------------------------------------------------------
    # Scene Frame Limits
    # -----------------------------------------------------------------
    def _use_full_canvas(self):
        self.chk_use_frame.setChecked(False)
        self.frame_rect = None
        self.lbl_frame_info.setText("Full Canvas (No limits)")
        self.viewport.set_scene_frame(None, "")
        self._match_ratio()
        self.lbl_status.setText("Camera mode: Full Canvas")
        self._live_sync()
        self._save_session()

    def _draw_frame_action(self):
        sel = CanvasSyncManager.get_active_selection_rect()
        if sel:
            fx, fy, fw, fh = sel
            self.spin_fx.blockSignals(True); self.spin_fx.setValue(fx); self.spin_fx.blockSignals(False)
            self.spin_fy.blockSignals(True); self.spin_fy.setValue(fy); self.spin_fy.blockSignals(False)
            self.spin_fw.blockSignals(True); self.spin_fw.setValue(fw); self.spin_fw.blockSignals(False)
            self.spin_fh.blockSignals(True); self.spin_fh.setValue(fh); self.spin_fh.blockSignals(False)
            self.chk_use_frame.setChecked(True)
            self._on_frame_toggle(Qt.Checked)
            self._match_ratio()
            self.lbl_status.setText(f"Frame locked to selection: {fw}×{fh}")
            self._save_session()
        else:
            try:
                if Krita:
                    action = Krita.instance().action("KisToolSelectRectangular")
                    if action:
                        action.trigger()
            except Exception:
                pass
            self.lbl_status.setText("Drag a rectangular selection on canvas, then click 'Draw Frame' again!")

    def _on_frame_toggle(self, state):
        if state == Qt.Checked:
            self.frame_rect = (
                self.spin_fx.value(),
                self.spin_fy.value(),
                self.spin_fw.value(),
                self.spin_fh.value()
            )
            self.lbl_frame_info.setText(f"Frame: {self.frame_rect[2]}×{self.frame_rect[3]} at ({self.frame_rect[0]},{self.frame_rect[1]})")
            self.viewport.set_scene_frame(self.frame_rect, f"{self.frame_rect[2]}×{self.frame_rect[3]}")
        else:
            self.frame_rect = None
            self.lbl_frame_info.setText("Full Canvas (No limits)")
            self.viewport.set_scene_frame(None, "")
            self._match_ratio()
        self.viewport.update()
        self._live_sync()
        self._schedule_save()

    def _on_frame_spins(self):
        if self.chk_use_frame.isChecked():
            self.frame_rect = (
                self.spin_fx.value(),
                self.spin_fy.value(),
                self.spin_fw.value(),
                self.spin_fh.value()
            )
            self.lbl_frame_info.setText(f"Frame: {self.frame_rect[2]}×{self.frame_rect[3]} at ({self.frame_rect[0]},{self.frame_rect[1]})")
            self.viewport.set_scene_frame(self.frame_rect, f"{self.frame_rect[2]}×{self.frame_rect[3]}")
            self.viewport.update()
            self._live_sync()
            self._schedule_save()

    # -----------------------------------------------------------------
    # Studio Lighting
    # -----------------------------------------------------------------
    def _on_sphere_light(self, az, el):
        self.viewport.lighting.azimuth = az
        self.viewport.lighting.elevation = el
        self.lbl_light.setText(f"Az:{int(az)} El:{int(el)}")
        self.viewport.update()
        self._live_sync()
        self._schedule_save()

    def _on_follow(self, state):
        self.viewport.lighting.follow_camera = (state == Qt.Checked)
        self.viewport.update()
        self._live_sync()
        self._schedule_save()

    def _reset_light(self):
        self.viewport.lighting.azimuth = 45.0
        self.viewport.lighting.elevation = 40.0
        self.lbl_light.setText("Az:45 El:40")
        self.light_sphere.azimuth = 45.0
        self.light_sphere.elevation = 40.0
        self.light_sphere.update()
        self.viewport.update()
        self._live_sync()
        self._save_session()

    def _on_amb(self, v):
        self.viewport.lighting.ambient = v / 100.0
        self.lbl_amb.setText(f"Ambient {v}%")
        self.viewport.update()
        self._live_sync()

    def _on_diff(self, v):
        self.viewport.lighting.diffuse = v / 100.0
        self.lbl_diff.setText(f"Key {v}%")
        self.viewport.update()
        self._live_sync()

    # -----------------------------------------------------------------
    # Settings & Performance
    # -----------------------------------------------------------------
    def _on_toggle_overlay_buttons(self, state):
        self.viewport.show_overlay_buttons = (state == Qt.Checked)
        self.viewport.update()
        self._schedule_save()

    def _on_toggle_gizmo(self, state):
        self.viewport.show_gizmo = (state == Qt.Checked)
        self.viewport.update()
        self._schedule_save()

    def _on_toggle_frame_guide(self, state):
        self.viewport.show_canvas_frame = (state == Qt.Checked)
        self.viewport.update()
        self._schedule_save()

    def _apply_sticky_viewport(self, enable):
        self.is_sticky_viewport = bool(enable)
        if hasattr(self, 'chk_sticky_viewport'):
            self.chk_sticky_viewport.blockSignals(True)
            self.chk_sticky_viewport.setChecked(self.is_sticky_viewport)
            self.chk_sticky_viewport.blockSignals(False)
        if self.is_sticky_viewport:
            # Move viewport + resize handle from scroll area into sticky container
            if self.viewport.parent() != self._sticky_viewport_widget:
                self.sec_viewport.content_layout.removeWidget(self.viewport)
                self.sec_viewport.content_layout.removeWidget(self.resize_handle)
                self._sticky_viewport_layout.addWidget(self.viewport)
                self._sticky_viewport_layout.addWidget(self.resize_handle)
            self._sticky_viewport_widget.setVisible(True)
            self.sec_viewport.set_expanded(False)
        else:
            # Move viewport + resize handle back into the collapsible section
            if self.viewport.parent() == self._sticky_viewport_widget:
                self._sticky_viewport_layout.removeWidget(self.viewport)
                self._sticky_viewport_layout.removeWidget(self.resize_handle)
                self.sec_viewport.content_layout.insertWidget(0, self.viewport)
                self.sec_viewport.content_layout.insertWidget(1, self.resize_handle)
            self._sticky_viewport_widget.setVisible(False)
            self.sec_viewport.set_expanded(True)

    def _on_toggle_sticky_viewport(self, state):
        """Toggle sticky viewport: pins the viewport above the scroll area."""
        self._apply_sticky_viewport(state == Qt.Checked)
        self._save_session()

    def _on_toggle_invert_pan(self, state):
        self.viewport.invert_pan = (state == Qt.Checked)
        self._schedule_save()

    def _on_toggle_invert_orbit_x(self, state):
        self.viewport.invert_orbit_x = (state == Qt.Checked)
        self._schedule_save()

    def _on_toggle_invert_orbit_y(self, state):
        self.viewport.invert_orbit_y = (state == Qt.Checked)
        self._schedule_save()

    def _on_grid_opacity(self, v):
        self.viewport.grid_settings.grid_opacity = v / 100.0
        self.lbl_grid_opac.setText(f"Grid Opacity: {v}%")
        self.viewport.update()
        self._live_sync()
        self._schedule_save()

    def _on_horizon_opacity(self, v):
        self.viewport.grid_settings.horizon_opacity = v / 100.0
        self.lbl_horizon_opac.setText(f"Horizon Opacity: {v}%")
        self.viewport.update()
        self._live_sync()
        self._schedule_save()

    def _on_quality_changed(self, idx):
        """Change render quality: affects viewport anti-aliasing only, NOT canvas resolution."""
        qualities = ["Fast", "Balanced", "High"]
        self.viewport.renderer.quality = qualities[idx]
        self.viewport.update()
        self._schedule_save()

    def _on_debounce_changed(self):
        self.debounce_ms = self.spin_debounce.value()
        self._schedule_save()

    # -----------------------------------------------------------------
    # Live Sync & Canvas Stamping
    # -----------------------------------------------------------------
    def _live_sync(self, *_):
        if self.chk_live.isChecked():
            self.live_sync_timer.start(self.debounce_ms)

    def _do_live_sync(self):
        if self.chk_live.isChecked():
            self._stamp()

    def _on_camera_changed(self):
        self._sync_ui()
        self._live_sync()

    def _on_interaction_ended(self):
        if self.chk_live.isChecked():
            self.live_sync_timer.stop()
            self._stamp()

    def _on_viewport_fov_changed(self, fov):
        self.sl_fov.blockSignals(True)
        self.sl_fov.setValue(int(fov))
        self.sl_fov.blockSignals(False)
        self._update_fov_label(fov)

    def _stamp(self):
        has_mesh = bool(self.mesh and self.mesh.vertices)
        has_grid = bool(self.chk_grid_canvas.isChecked())
        if not has_mesh and not has_grid:
            return

        quality_idx = self.combo_quality.currentIndex()
        # Always render at full document resolution to prevent canvas frame corruption
        # Quality setting only affects viewport anti-aliasing, not canvas render dimensions
        scale_factor = 1.0

        grid_settings = self.viewport.grid_settings if has_grid else None
        active_frame = self.frame_rect if (self.chk_use_frame.isChecked() and self.frame_rect) else None

        try:
            CanvasSyncManager.render_to_krita_layer(
                mesh=self.mesh if has_mesh else None,
                camera=self.viewport.camera,
                lighting=self.viewport.lighting,
                renderer=self.viewport.renderer,
                render_style=self.viewport.render_style,
                layer_mode="named",
                layer_name="3D Perspective & Model",
                transparent_bg=self.chk_transp.isChecked(),
                custom_bg=self.custom_bg_color,
                scale_factor=scale_factor,
                frame=active_frame,
                grid_settings=grid_settings,
                draw_model=has_mesh
            )
            self.lbl_status.setText("Layer updated")
        except Exception as e:
            self.lbl_status.setText(f"Sync error: {e}")

    # -----------------------------------------------------------------
    # UI Sync
    # -----------------------------------------------------------------
    def _sync_ui(self):
        c = self.viewport.camera
        if hasattr(self, 'sl_tilt') and not self.sl_tilt.isSliderDown():
            self.sl_tilt.blockSignals(True); self.sl_tilt.setValue(int(c.pitch)); self.sl_tilt.blockSignals(False)
        if hasattr(self, 'lbl_tilt'):
            self.lbl_tilt.setText(f"Orbit Pitch {int(c.pitch)}°")

        if hasattr(self, 'sl_yaw') and not self.sl_yaw.isSliderDown():
            self.sl_yaw.blockSignals(True); self.sl_yaw.setValue(int(c.yaw)); self.sl_yaw.blockSignals(False)
        if hasattr(self, 'lbl_yaw'):
            self.lbl_yaw.setText(f"Orbit Yaw {int(c.yaw)}°")

        if hasattr(self, 'sl_lens_tilt') and not self.sl_lens_tilt.isSliderDown():
            self.sl_lens_tilt.blockSignals(True); self.sl_lens_tilt.setValue(int(c.tilt)); self.sl_lens_tilt.blockSignals(False)
        if hasattr(self, 'lbl_lens_tilt'):
            self.lbl_lens_tilt.setText(f"Lens Tilt {int(c.tilt)}°")

        if hasattr(self, 'sl_roll') and not self.sl_roll.isSliderDown():
            self.sl_roll.blockSignals(True); self.sl_roll.setValue(int(c.roll)); self.sl_roll.blockSignals(False)
        if hasattr(self, 'lbl_roll'):
            self.lbl_roll.setText(f"Roll {int(c.roll)}°")

        if hasattr(self, 'sl_fov') and not self.sl_fov.isSliderDown():
            self.sl_fov.blockSignals(True); self.sl_fov.setValue(int(c.fov)); self.sl_fov.blockSignals(False)
        self._update_fov_label(c.fov)

        if hasattr(self, 'sl_dist') and not self.sl_dist.isSliderDown():
            self.sl_dist.blockSignals(True); self.sl_dist.setValue(int(c.distance * 10)); self.sl_dist.blockSignals(False)
        if hasattr(self, 'lbl_dist'):
            self.lbl_dist.setText(f"Dist {c.distance:.1f}")

        if hasattr(self, 'spin_pan_x'):
            self.spin_pan_x.blockSignals(True); self.spin_pan_x.setValue(c.pan_x); self.spin_pan_x.blockSignals(False)
            self.spin_pan_y.blockSignals(True); self.spin_pan_y.setValue(c.pan_y); self.spin_pan_y.blockSignals(False)

        self._sync_target_spins()

    def _sync_target_spins(self):
        c = self.viewport.camera
        if hasattr(self, 'spin_tx'):
            self.spin_tx.blockSignals(True); self.spin_tx.setValue(c.target_x); self.spin_tx.blockSignals(False)
            self.spin_ty.blockSignals(True); self.spin_ty.setValue(c.target_y); self.spin_ty.blockSignals(False)
            self.spin_tz.blockSignals(True); self.spin_tz.setValue(c.target_z); self.spin_tz.blockSignals(False)

    def _update_fov_label(self, fov):
        mm = int(18.0 / math.tan(math.radians(max(1.0, fov) * 0.5)))
        self.lbl_fov.setText(f"FOV {int(fov)}° ({mm}mm)")

    def _match_ratio(self):
        doc_info = CanvasSyncManager.get_document_info()
        if doc_info and doc_info.get("height", 0) > 0:
            ratio = float(doc_info["width"]) / float(doc_info["height"])
            self.viewport.set_canvas_aspect_ratio(ratio)

    def canvasChanged(self, canvas):
        """Called by Krita when active canvas or document changes."""
        try:
            self._match_ratio()
        except Exception:
            pass

    def showEvent(self, event):
        super().showEvent(event)
        try:
            self._match_ratio()
            if hasattr(self, "is_sticky_viewport"):
                self._apply_sticky_viewport(self.is_sticky_viewport)
            self.viewport.update()
        except Exception:
            pass

    def hideEvent(self, event):
        super().hideEvent(event)
        try:
            self._save_session()
        except Exception:
            pass

    def closeEvent(self, event):
        super().closeEvent(event)
        try:
            self._save_session()
        except Exception:
            pass

    # -----------------------------------------------------------------
    # Viewport resize handle
    # -----------------------------------------------------------------
    def _on_viewport_resized(self, new_h):
        """Called when the user drags the viewport resize handle."""
        self._save_session()

    # -----------------------------------------------------------------
    # Persistent Session Save / Load
    # -----------------------------------------------------------------
    def _schedule_save(self, *_):
        if getattr(self, "_restoring_session", False):
            return
        if hasattr(self, "_save_timer"):
            self._save_timer.start(400)

    def _collect_session(self):
        """Collect all current docker state into a flat dict for serialization."""
        c = self.viewport.camera
        gs = self.viewport.grid_settings
        ren = self.viewport.renderer
        lit = self.viewport.lighting

        data = {
            # Viewport
            "viewport_height":      self.viewport.height(),
            "sticky_viewport":      self.is_sticky_viewport,
            "show_overlay_buttons": bool(self.viewport.show_overlay_buttons),
            "show_gizmo":           bool(self.viewport.show_gizmo),
            "show_frame_guide":     bool(self.viewport.show_canvas_frame),

            # Camera Navigation & Transform
            "nav_camera_mode":      self.viewport.camera_mode,
            "invert_pan":           bool(self.viewport.invert_pan),
            "invert_orbit_x":       bool(self.viewport.invert_orbit_x),
            "invert_orbit_y":       bool(self.viewport.invert_orbit_y),
            "cam_yaw":              float(c.yaw),
            "cam_pitch":            float(c.pitch),
            "cam_tilt":             float(c.tilt),
            "cam_roll":             float(c.roll),
            "cam_distance":         float(c.distance),
            "cam_fov":              float(c.fov),
            "cam_pan_x":            float(c.pan_x),
            "cam_pan_y":            float(c.pan_y),
            "cam_target_x":         float(c.target_x),
            "cam_target_y":         float(c.target_y),
            "cam_target_z":         float(c.target_z),

            # Projection & Lens
            "cam_projection":       c.projection_mode,
            "cam_curvature":        float(c.curvature),
            "cam_fisheye_fov":      float(c.fisheye_fov),
            "cam_fish_fov_mult":    float(c.fish_fov_mult),
            "cam_fisheye_zoom":     float(c.fisheye_zoom),
            "cam_lens_type":        getattr(c, "fisheye_lens_type", "Equidistant"),
            "cam_crop_circle":      bool(getattr(c, "fisheye_crop_circle", False)),

            # Model & Material
            "mesh_path":            self.mesh_path or "",
            "render_style":         self.viewport.render_style,
            "base_color":           ren.base_color.name() if ren.base_color.isValid() else "#ecb613",
            "wire_cull":            bool(getattr(ren, "wireframe_backface_culling", True)),
            "hide_coplanar":        bool(getattr(ren, "hide_coplanar_edges", True)),
            "wire_width":           float(ren.wire_width),
            "wire_color":           ren.wire_color.name() if hasattr(ren, "wire_color") and ren.wire_color.isValid() else "#1e293b",
            "contour_width":        float(ren.contour_width),
            "contour_color":        ren.contour_color.name() if hasattr(ren, "contour_color") and ren.contour_color.isValid() else "#0f172a",

            # Studio Lighting
            "light_az":             float(lit.azimuth),
            "light_el":             float(lit.elevation),
            "light_ambient":        float(lit.ambient),
            "light_diffuse":        float(lit.diffuse),
            "light_follow":         bool(lit.follow_camera),

            # Perspective Grid
            "grid_canvas":          bool(gs.enabled),
            "grid_viewport":        bool(gs.show_in_viewport),
            "grid_horizon":         bool(gs.horizon_enabled),
            "grid_ground":          bool(gs.ground_enabled),
            "grid_ceiling":         bool(gs.ceiling_enabled),
            "grid_ceil_h":          float(gs.ceiling_height),
            "grid_extent":          int(gs.grid_extent),
            "grid_tile":            float(gs.tile_size),
            "grid_subdiv":          int(gs.subdivisions),
            "grid_exceed":          bool(gs.exceed_lines),
            "grid_verticals":       bool(gs.vertical_lines),
            "grid_vert_h":          float(gs.vertical_height),
            "grid_axis_col":        bool(gs.axis_colors),
            "grid_opacity":         float(gs.grid_opacity),
            "horizon_opacity":      float(gs.horizon_opacity),

            # Ground & Canvas Framing
            "use_frame":            self.chk_use_frame.isChecked() if hasattr(self, "chk_use_frame") else False,
            "frame_x":              self.spin_fx.value() if hasattr(self, "spin_fx") else 0,
            "frame_y":              self.spin_fy.value() if hasattr(self, "spin_fy") else 0,
            "frame_w":              self.spin_fw.value() if hasattr(self, "spin_fw") else 800,
            "frame_h":              self.spin_fh.value() if hasattr(self, "spin_fh") else 600,

            # Performance & Canvas Sync
            "quality":              ren.quality if hasattr(ren, "quality") else "Balanced",
            "debounce_ms":          self.debounce_ms,
            "live_sync":            self.chk_live.isChecked() if hasattr(self, "chk_live") else True,
            "transparent_bg":       self.chk_transp.isChecked() if hasattr(self, "chk_transp") else True,
            "custom_bg":            self.custom_bg_color.name() if (hasattr(self, "custom_bg_color") and self.custom_bg_color) else "#ffffff",

            # Section expand states
            "sec_viewport_exp":     self.sec_viewport.is_expanded() if hasattr(self, "sec_viewport") else False,
            "sec_presets_exp":      self.sec_presets.is_expanded() if hasattr(self, "sec_presets") else True,
            "sec_model_exp":        self.sec_model.is_expanded() if hasattr(self, "sec_model") else True,
            "sec_cam_exp":          self.sec_cam.is_expanded() if hasattr(self, "sec_cam") else True,
            "sec_canvas_exp":       self.sec_canvas.is_expanded() if hasattr(self, "sec_canvas") else True,
            "sec_grid_exp":         self.sec_grid.is_expanded() if hasattr(self, "sec_grid") else True,
            "sec_light_exp":        self.sec_light.is_expanded() if hasattr(self, "sec_light") else False,
            "sec_settings_exp":     self.sec_settings.is_expanded() if hasattr(self, "sec_settings") else False,
        }
        return data

    def _save_session(self):
        """Save current state to disk."""
        if getattr(self, "_restoring_session", False):
            return
        try:
            save_session(self._collect_session())
        except Exception:
            pass

    def _restore_session(self):
        """Load and apply previously saved session state with complete UI synchronization."""
        data = load_session()
        if not data:
            return

        self._restoring_session = True
        try:
            c   = self.viewport.camera
            gs  = self.viewport.grid_settings
            ren = self.viewport.renderer
            lit = self.viewport.lighting

            # 1. Model loading first (with frame=False so it doesn't overwrite camera)
            mpath = data.get("mesh_path", "")
            loaded = False
            if mpath and os.path.exists(mpath):
                self._load_file(mpath, frame=False)
                loaded = True
            elif mpath:
                cand = os.path.join(os.path.dirname(__file__), mpath)
                if os.path.exists(cand):
                    self._load_file(cand, frame=False)
                    loaded = True
                else:
                    cand2 = os.path.join(os.path.dirname(__file__), "3D-Primitive", os.path.basename(mpath))
                    if os.path.exists(cand2):
                        self._load_file(cand2, frame=False)
                        loaded = True
            if not loaded and self.mesh is None:
                default_asaro = os.path.join(os.path.dirname(__file__), "3D-Primitive", "Asaro Head Planes.obj")
                if os.path.exists(default_asaro):
                    self._load_file(default_asaro, frame=False)

            # 2. Viewport height & Sticky Viewport
            vh = data.get("viewport_height", 170)
            if 60 <= vh <= 800:
                self.viewport.setFixedHeight(vh)
            is_sticky = bool(data.get("sticky_viewport", True))
            self._apply_sticky_viewport(is_sticky)

            # Viewport display toggles
            ov = bool(data.get("show_overlay_buttons", True))
            self.viewport.show_overlay_buttons = ov
            if hasattr(self, "chk_show_overlay"):
                self.chk_show_overlay.blockSignals(True)
                self.chk_show_overlay.setChecked(ov)
                self.chk_show_overlay.blockSignals(False)

            gz = bool(data.get("show_gizmo", True))
            self.viewport.show_gizmo = gz
            if hasattr(self, "chk_show_gizmo"):
                self.chk_show_gizmo.blockSignals(True)
                self.chk_show_gizmo.setChecked(gz)
                self.chk_show_gizmo.blockSignals(False)

            fg = bool(data.get("show_frame_guide", True))
            self.viewport.show_canvas_frame = fg
            if hasattr(self, "chk_show_frame_guide"):
                self.chk_show_frame_guide.blockSignals(True)
                self.chk_show_frame_guide.setChecked(fg)
                self.chk_show_frame_guide.blockSignals(False)

            # Navigation preferences
            cam_mode = data.get("nav_camera_mode", CAMERA_MODE_ORBIT)
            self.viewport.camera_mode = cam_mode
            if hasattr(self, "combo_cam_mode"):
                idx = self.combo_cam_mode.findText(cam_mode)
                if idx >= 0:
                    self.combo_cam_mode.blockSignals(True)
                    self.combo_cam_mode.setCurrentIndex(idx)
                    self.combo_cam_mode.blockSignals(False)

            self.viewport.invert_pan = bool(data.get("invert_pan", True))
            if hasattr(self, "chk_invert_pan"):
                self.chk_invert_pan.blockSignals(True)
                self.chk_invert_pan.setChecked(self.viewport.invert_pan)
                self.chk_invert_pan.blockSignals(False)

            self.viewport.invert_orbit_x = bool(data.get("invert_orbit_x", True))
            if hasattr(self, "chk_invert_orbit_x"):
                self.chk_invert_orbit_x.blockSignals(True)
                self.chk_invert_orbit_x.setChecked(self.viewport.invert_orbit_x)
                self.chk_invert_orbit_x.blockSignals(False)

            self.viewport.invert_orbit_y = bool(data.get("invert_orbit_y", False))
            if hasattr(self, "chk_invert_orbit_y"):
                self.chk_invert_orbit_y.blockSignals(True)
                self.chk_invert_orbit_y.setChecked(self.viewport.invert_orbit_y)
                self.chk_invert_orbit_y.blockSignals(False)

            # 3. Camera parameters
            c.yaw         = float(data.get("cam_yaw", c.yaw))
            c.pitch       = float(data.get("cam_pitch", c.pitch))
            c.tilt        = float(data.get("cam_tilt", c.tilt))
            c.roll        = float(data.get("cam_roll", c.roll))
            c.distance    = float(data.get("cam_distance", c.distance))
            c.fov         = float(data.get("cam_fov", c.fov))
            c.pan_x       = float(data.get("cam_pan_x", c.pan_x))
            c.pan_y       = float(data.get("cam_pan_y", c.pan_y))
            c.target_x    = float(data.get("cam_target_x", c.target_x))
            c.target_y    = float(data.get("cam_target_y", c.target_y))
            c.target_z    = float(data.get("cam_target_z", c.target_z))

            # Projection & Lens
            proj = data.get("cam_projection", ProjectionMode.PERSPECTIVE)
            if proj in ProjectionMode.ALL:
                c.projection_mode = proj
                c.orthographic = (proj == ProjectionMode.ORTHOGRAPHIC)
                if hasattr(self, "combo_proj"):
                    idx = self.combo_proj.findText(proj)
                    if idx >= 0:
                        self.combo_proj.blockSignals(True)
                        self.combo_proj.setCurrentIndex(idx)
                        self.combo_proj.blockSignals(False)
                    self._update_proj_controls_visibility(proj)

            c.curvature = float(data.get("cam_curvature", c.curvature))
            if hasattr(self, "sl_curv"):
                self.sl_curv.blockSignals(True)
                self.sl_curv.setValue(int(c.curvature * 100))
                self.sl_curv.blockSignals(False)
                self.lbl_curv.setText(f"Curvature {int(c.curvature * 100)}%")
            if hasattr(self, "sl_fish_curv"):
                self.sl_fish_curv.blockSignals(True)
                self.sl_fish_curv.setValue(int(c.curvature * 100))
                self.sl_fish_curv.blockSignals(False)
                self.lbl_fish_curv.setText(f"Curvature Strength: {int(c.curvature * 100)}%")

            c.fisheye_fov = float(data.get("cam_fisheye_fov", c.fisheye_fov))
            if hasattr(self, "sl_fish_fov"):
                self.sl_fish_fov.blockSignals(True)
                self.sl_fish_fov.setValue(int(c.fisheye_fov))
                self.sl_fish_fov.blockSignals(False)
                self.lbl_fish_fov.setText(f"Fisheye FOV: {int(c.fisheye_fov)}°")

            c.fish_fov_mult = float(data.get("cam_fish_fov_mult", c.fish_fov_mult))
            c.fisheye_zoom = float(data.get("cam_fisheye_zoom", c.fisheye_zoom))
            if hasattr(self, "sl_fish_zoom"):
                self.sl_fish_zoom.blockSignals(True)
                self.sl_fish_zoom.setValue(int(c.fisheye_zoom * 100))
                self.sl_fish_zoom.blockSignals(False)
                self.lbl_fish_zoom.setText(f"Lens Zoom: {int(c.fisheye_zoom * 100)}%")

            c.fisheye_lens_type = data.get("cam_lens_type", "Equidistant")
            if hasattr(self, "combo_fish_lens"):
                for idx in range(self.combo_fish_lens.count()):
                    if self.combo_fish_lens.itemText(idx).startswith(c.fisheye_lens_type):
                        self.combo_fish_lens.blockSignals(True)
                        self.combo_fish_lens.setCurrentIndex(idx)
                        self.combo_fish_lens.blockSignals(False)
                        break

            c.fisheye_crop_circle = bool(data.get("cam_crop_circle", False))
            if hasattr(self, "chk_fish_circle"):
                self.chk_fish_circle.blockSignals(True)
                self.chk_fish_circle.setChecked(c.fisheye_crop_circle)
                self.chk_fish_circle.blockSignals(False)

            # 4. Model & Material
            rs = data.get("render_style", self.viewport.render_style)
            self.viewport.render_style = rs
            if hasattr(self, "combo_style"):
                idx = self.combo_style.findText(rs)
                if idx >= 0:
                    self.combo_style.blockSignals(True)
                    self.combo_style.setCurrentIndex(idx)
                    self.combo_style.blockSignals(False)

            wcull = bool(data.get("wire_cull", True))
            ren.wireframe_backface_culling = wcull
            if hasattr(self, "chk_wire_cull"):
                self.chk_wire_cull.blockSignals(True)
                self.chk_wire_cull.setChecked(wcull)
                self.chk_wire_cull.blockSignals(False)

            hcop = bool(data.get("hide_coplanar", True))
            ren.hide_coplanar_edges = hcop
            if hasattr(self, "chk_hide_coplanar"):
                self.chk_hide_coplanar.blockSignals(True)
                self.chk_hide_coplanar.setChecked(hcop)
                self.chk_hide_coplanar.blockSignals(False)

            ww = float(data.get("wire_width", 1.0))
            ren.wire_width = ww
            if hasattr(self, "sl_wire"):
                self.sl_wire.blockSignals(True)
                self.sl_wire.setValue(int(ww * 10))
                self.sl_wire.blockSignals(False)
                self.lbl_wire.setText(f"Wire {ww:.1f}")

            cw = float(data.get("contour_width", 0.0))
            ren.contour_width = cw
            if hasattr(self, "sl_contour"):
                self.sl_contour.blockSignals(True)
                self.sl_contour.setValue(int(cw * 10))
                self.sl_contour.blockSignals(False)
                self.lbl_contour.setText(f"Contour {cw:.1f}" if cw > 0.05 else "Contour Off")

            if "wire_color" in data:
                wc = QColor(data["wire_color"])
                if wc.isValid():
                    ren.wire_color = wc
            if "contour_color" in data:
                cc = QColor(data["contour_color"])
                if cc.isValid():
                    ren.contour_color = cc

            bc = QColor(data.get("base_color", "#848ba2"))
            if bc.isValid():
                ren.base_color = bc
                self._update_model_color_button()

            # 5. Studio Lighting
            lit.azimuth = float(data.get("light_az", 321.0))
            lit.elevation = float(data.get("light_el", 56.5))
            lit.ambient = float(data.get("light_ambient", 0.25))
            lit.diffuse = float(data.get("light_diffuse", 0.55))
            lit.follow_camera = bool(data.get("light_follow", True))

            if hasattr(self, "light_sphere"):
                self.light_sphere.set_light(lit.azimuth, lit.elevation)
            if hasattr(self, "lbl_light"):
                self.lbl_light.setText(f"Az:{int(lit.azimuth)} El:{int(lit.elevation)}")
            if hasattr(self, "chk_follow"):
                self.chk_follow.blockSignals(True)
                self.chk_follow.setChecked(lit.follow_camera)
                self.chk_follow.blockSignals(False)
            if hasattr(self, "sl_amb"):
                self.sl_amb.blockSignals(True)
                self.sl_amb.setValue(int(lit.ambient * 100))
                self.sl_amb.blockSignals(False)
                self.lbl_amb.setText(f"Ambient {int(lit.ambient * 100)}%")
            if hasattr(self, "sl_diff"):
                self.sl_diff.blockSignals(True)
                self.sl_diff.setValue(int(lit.diffuse * 100))
                self.sl_diff.blockSignals(False)
                self.lbl_diff.setText(f"Key {int(lit.diffuse * 100)}%")

            # 6. Perspective Grid
            gs.enabled = bool(data.get("grid_canvas", True))
            gs.show_in_viewport = bool(data.get("grid_viewport", True))
            gs.horizon_enabled = bool(data.get("grid_horizon", True))
            gs.ground_enabled = bool(data.get("grid_ground", True))
            gs.ceiling_enabled = bool(data.get("grid_ceiling", False))
            gs.ceiling_height = float(data.get("grid_ceil_h", 2.5))
            gs.grid_extent = int(data.get("grid_extent", 10))
            gs.tile_size = float(data.get("grid_tile", 0.5))
            gs.subdivisions = int(data.get("grid_subdiv", 1))
            gs.exceed_lines = bool(data.get("grid_exceed", True))
            gs.vertical_lines = bool(data.get("grid_verticals", True))
            gs.vertical_height = float(data.get("grid_vert_h", 2.5))
            gs.axis_colors = bool(data.get("grid_axis_col", True))
            gs.grid_opacity = float(data.get("grid_opacity", 0.85))
            gs.horizon_opacity = float(data.get("horizon_opacity", 0.86))

            if hasattr(self, "chk_grid_canvas"):
                self.chk_grid_canvas.blockSignals(True)
                self.chk_grid_canvas.setChecked(gs.enabled)
                self.chk_grid_canvas.blockSignals(False)
            if hasattr(self, "chk_grid_viewport"):
                self.chk_grid_viewport.blockSignals(True)
                self.chk_grid_viewport.setChecked(gs.show_in_viewport)
                self.chk_grid_viewport.blockSignals(False)
            if hasattr(self, "chk_grid_horizon"):
                self.chk_grid_horizon.blockSignals(True)
                self.chk_grid_horizon.setChecked(gs.horizon_enabled)
                self.chk_grid_horizon.blockSignals(False)
            if hasattr(self, "chk_grid_ground"):
                self.chk_grid_ground.blockSignals(True)
                self.chk_grid_ground.setChecked(gs.ground_enabled)
                self.chk_grid_ground.blockSignals(False)
            if hasattr(self, "chk_grid_ceiling"):
                self.chk_grid_ceiling.blockSignals(True)
                self.chk_grid_ceiling.setChecked(gs.ceiling_enabled)
                self.chk_grid_ceiling.blockSignals(False)
            if hasattr(self, "spin_grid_extent"):
                self.spin_grid_extent.blockSignals(True)
                self.spin_grid_extent.setValue(gs.grid_extent)
                self.spin_grid_extent.blockSignals(False)
            if hasattr(self, "spin_grid_tile"):
                self.spin_grid_tile.blockSignals(True)
                self.spin_grid_tile.setValue(gs.tile_size)
                self.spin_grid_tile.blockSignals(False)
            if hasattr(self, "spin_grid_cheight"):
                self.spin_grid_cheight.blockSignals(True)
                self.spin_grid_cheight.setValue(gs.ceiling_height)
                self.spin_grid_cheight.blockSignals(False)
            if hasattr(self, "spin_grid_subdiv"):
                self.spin_grid_subdiv.blockSignals(True)
                self.spin_grid_subdiv.setValue(gs.subdivisions)
                self.spin_grid_subdiv.blockSignals(False)
            if hasattr(self, "chk_grid_exceed"):
                self.chk_grid_exceed.blockSignals(True)
                self.chk_grid_exceed.setChecked(gs.exceed_lines)
                self.chk_grid_exceed.blockSignals(False)
            if hasattr(self, "chk_grid_verticals"):
                self.chk_grid_verticals.blockSignals(True)
                self.chk_grid_verticals.setChecked(gs.vertical_lines)
                self.chk_grid_verticals.blockSignals(False)
            if hasattr(self, "chk_grid_axis"):
                self.chk_grid_axis.blockSignals(True)
                self.chk_grid_axis.setChecked(gs.axis_colors)
                self.chk_grid_axis.blockSignals(False)
            if hasattr(self, "sl_grid_opac"):
                self.sl_grid_opac.blockSignals(True)
                self.sl_grid_opac.setValue(int(gs.grid_opacity * 100))
                self.sl_grid_opac.blockSignals(False)
                self.lbl_grid_opac.setText(f"Grid Opacity: {int(gs.grid_opacity * 100)}%")
            if hasattr(self, "sl_horizon_opac"):
                self.sl_horizon_opac.blockSignals(True)
                self.sl_horizon_opac.setValue(int(gs.horizon_opacity * 100))
                self.sl_horizon_opac.blockSignals(False)
                self.lbl_horizon_opac.setText(f"Horizon Opacity: {int(gs.horizon_opacity * 100)}%")

            # 7. Canvas Framing
            if hasattr(self, "chk_use_frame"):
                use_f = bool(data.get("use_frame", False))
                fx = int(data.get("frame_x", 0))
                fy = int(data.get("frame_y", 0))
                fw = int(data.get("frame_w", 800))
                fh = int(data.get("frame_h", 600))
                for spin, val in [(self.spin_fx, fx), (self.spin_fy, fy), (self.spin_fw, fw), (self.spin_fh, fh)]:
                    spin.blockSignals(True); spin.setValue(val); spin.blockSignals(False)
                self.chk_use_frame.blockSignals(True)
                self.chk_use_frame.setChecked(use_f)
                self.chk_use_frame.blockSignals(False)
                if use_f:
                    self.frame_rect = (fx, fy, fw, fh)
                    self.lbl_frame_info.setText(f"Frame: {fw}×{fh} at ({fx},{fy})")
                    self.viewport.set_scene_frame(self.frame_rect, f"{fw}×{fh}")
                else:
                    self.frame_rect = None
                    self.lbl_frame_info.setText("Full Canvas (No limits)")
                    self.viewport.clear_scene_frame()

            # 8. Performance & Canvas Sync
            q = data.get("quality", "Balanced")
            ren.quality = q
            if hasattr(self, "combo_quality"):
                qualities = ["Fast", "Balanced", "High"]
                idx = qualities.index(q) if q in qualities else 1
                self.combo_quality.blockSignals(True)
                self.combo_quality.setCurrentIndex(idx)
                self.combo_quality.blockSignals(False)

            self.debounce_ms = int(data.get("debounce_ms", 120))
            if hasattr(self, "spin_debounce"):
                self.spin_debounce.blockSignals(True)
                self.spin_debounce.setValue(self.debounce_ms)
                self.spin_debounce.blockSignals(False)

            tr = bool(data.get("transparent_bg", True))
            if hasattr(self, "chk_transp"):
                self.chk_transp.blockSignals(True)
                self.chk_transp.setChecked(tr)
                self.chk_transp.blockSignals(False)

            self.custom_bg_color = QColor(data.get("custom_bg", "#ffffff"))
            if hasattr(self, "btn_bg_col") and self.custom_bg_color.isValid():
                self.btn_bg_col.setStyleSheet(f"background:{self.custom_bg_color.name()}; color:#000;")

            ls = bool(data.get("live_sync", True))
            if hasattr(self, "chk_live"):
                self.chk_live.blockSignals(True)
                self.chk_live.setChecked(ls)
                self.chk_live.blockSignals(False)

            # 9. Collapsible Sections
            sections = [
                ("sec_viewport", "sec_viewport_exp"),
                ("sec_presets",  "sec_presets_exp"),
                ("sec_model",    "sec_model_exp"),
                ("sec_cam",      "sec_cam_exp"),
                ("sec_canvas",   "sec_canvas_exp"),
                ("sec_grid",     "sec_grid_exp"),
                ("sec_light",    "sec_light_exp"),
                ("sec_settings", "sec_settings_exp"),
            ]
            for attr, key in sections:
                if key in data and hasattr(self, attr):
                    sec = getattr(self, attr)
                    sec.set_expanded(bool(data[key]))

            # 10. Final UI & Viewport Sync
            self._sync_ui()
            self.viewport.update()
        except Exception as e:
            import traceback; traceback.print_exc()
        finally:
            self._restoring_session = False
