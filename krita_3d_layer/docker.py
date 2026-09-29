"""
Main docker panel for Krita 3D Layer.
Hosts the viewport, model/material settings, camera angles, perspective grids, and layer stamping.
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
    ScrubbableSpinBox, ScrubbableDoubleSpinBox, ScrubLabel, ViewportResizeHandle,
    PositionGizmoWidget, RotationGizmoWidget, ScaleGizmoWidget
)
from .ground_calibrator import GroundCalibratorDialog
from .primitive_drawer import (
    PrimitiveDrawerDialog, create_box_primitive, create_cylinder_primitive,
    create_sphere_primitive, create_pyramid_primitive, create_cone_primitive,
    create_plane_primitive
)
from .quick_toolbar import QuickActionsToolbar

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
        background: #1e222b; border: 1px solid #3d4352;
        border-radius: 2px; color: #e5e7eb;
    }
    QDoubleSpinBox:hover, QSpinBox:hover {
        background: #282d39; border-color: #38bdf8;
    }
    QDoubleSpinBox:focus, QSpinBox:focus {
        background: #0f172a; border-color: #60a5fa; color: #ffffff;
    }
    QDoubleSpinBox::up-button, QDoubleSpinBox::down-button,
    QSpinBox::up-button, QSpinBox::down-button {
        width: 0px; height: 0px; border: none;
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
        self._outer_layout = outer_layout

        # Viewport + Resize Handle + Quick Toolbar container (pinned at top by default)
        self._top_viewport_container = QWidget()
        self._top_viewport_layout = QVBoxLayout(self._top_viewport_container)
        self._top_viewport_layout.setContentsMargins(3, 3, 3, 2)
        self._top_viewport_layout.setSpacing(2)

        self.viewport = Viewport3D()
        self.viewport.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.viewport.setFixedHeight(170)
        self.viewport.setMinimumHeight(60)
        self.viewport.camera_changed.connect(self._on_camera_changed)
        self.viewport.interaction_ended.connect(self._on_interaction_ended)
        self.viewport.interaction_ended.connect(self._save_session)
        self.viewport.fov_changed.connect(self._on_viewport_fov_changed)
        self._top_viewport_layout.addWidget(self.viewport)

        # Draggable height separator
        self.resize_handle = ViewportResizeHandle(self.viewport)
        self.resize_handle.resized.connect(self._on_viewport_resized)
        self._top_viewport_layout.addWidget(self.resize_handle)

        # Quick Actions Mini Toolbar directly below viewport
        self.quick_toolbar = QuickActionsToolbar(self)
        self._top_viewport_layout.addWidget(self.quick_toolbar)

        outer_layout.addWidget(self._top_viewport_container)

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
        self._controls_layout = L

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

        self.btn_save_preset = QPushButton("💾")
        self.btn_save_preset.setFixedSize(22, 20)
        self.btn_save_preset.setToolTip("Save current parameters as a new custom preset")
        self.btn_save_preset.clicked.connect(self._save_custom_preset)
        pr_row.addWidget(self.btn_save_preset, 0)

        self.btn_del_preset = QPushButton("🗑")
        self.btn_del_preset.setFixedSize(22, 20)
        self.btn_del_preset.setToolTip("Delete custom preset")
        self.btn_del_preset.clicked.connect(self._delete_custom_preset)
        pr_row.addWidget(self.btn_del_preset, 0)

        self.btn_help_manual = QPushButton("❓")
        self.btn_help_manual.setFixedSize(22, 20)
        self.btn_help_manual.setStyleSheet("background:#1e293b; color:#93c5fd; font-weight:bold; border:1px solid #3b82f6;")
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
        bi = QPushButton("📁 Import")
        bi.setToolTip("Import 3D model (.obj, .stl, .glb, .gltf)")
        bi.clicked.connect(self._import)
        mr.addWidget(bi, 2)

        self.btn_draw_primitive = QPushButton("✏️ Draw Box")
        self.btn_draw_primitive.setStyleSheet(
            "QPushButton{background:#065f46; color:#a7f3d0; font-weight:bold; border:1px solid #059669;}"
            "QPushButton:hover{background:#059669; color:#fff;}"
        )
        self.btn_draw_primitive.setToolTip(
            "Draw or trace a 3D box primitive directly onto your canvas sketch! "
            "Automatically infers FOV, camera tilt, rotation, box proportions, and perspective."
        )
        self.btn_draw_primitive.clicked.connect(self._open_primitive_drawer)
        mr.addWidget(self.btn_draw_primitive, 2)

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
        self.btn_model_color.setFixedSize(24, 20)
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

        self.chk_hide_coplanar = QCheckBox("Quad Wire")
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
        # SECTION: OBJECT & PRIMITIVE TRANSFORM
        # =============================================================
        self.sec_object = CollapsibleSection("OBJECT & PRIMITIVE TRANSFORM", expanded=True)

        # ----------------- 1. POSITION ROW -----------------
        pos_row = QHBoxLayout(); pos_row.setSpacing(4)
        self.gizmo_pos = PositionGizmoWidget()
        self.gizmo_pos.position_changed.connect(self._on_gizmo_pos_changed)
        self.gizmo_pos.interaction_ended.connect(self._on_interaction_ended)
        self.gizmo_pos.interaction_ended.connect(self._schedule_save)
        pos_row.addWidget(self.gizmo_pos, 0)

        pos_controls = QVBoxLayout(); pos_controls.setSpacing(1)
        pos_hdr = QHBoxLayout(); pos_hdr.setSpacing(2)
        lbl_p_title = QLabel("Position")
        lbl_p_title.setStyleSheet("font-weight:bold; font-size:10px; color:#e2e8f0;")
        pos_hdr.addWidget(lbl_p_title, 1)
        btn_rst_pos = QPushButton("↺")
        btn_rst_pos.setFixedSize(18, 16)
        btn_rst_pos.setToolTip("Reset object position to (0, 0, 0)")
        btn_rst_pos.clicked.connect(self._reset_obj_pos)
        pos_hdr.addWidget(btn_rst_pos, 0)
        pos_controls.addLayout(pos_hdr)

        self.spin_obj_px = self._dspin(-100.0, 100.0, 0.0, 0.1, self._on_obj_pos_spin)
        self.spin_obj_px.setToolTip("Object Position X (drag to scrub, click to type)")
        px_row = QHBoxLayout(); px_row.setSpacing(2)
        px_row.addWidget(ScrubLabel("X:", self.spin_obj_px, color="#ef4444"), 0)
        px_row.addWidget(self.spin_obj_px, 1)
        pos_controls.addLayout(px_row)

        self.spin_obj_py = self._dspin(-100.0, 100.0, 0.0, 0.1, self._on_obj_pos_spin)
        self.spin_obj_py.setToolTip("Object Position Y (drag to scrub, click to type)")
        py_row = QHBoxLayout(); py_row.setSpacing(2)
        py_row.addWidget(ScrubLabel("Y:", self.spin_obj_py, color="#22c55e"), 0)
        py_row.addWidget(self.spin_obj_py, 1)
        pos_controls.addLayout(py_row)

        self.spin_obj_pz = self._dspin(-100.0, 100.0, 0.0, 0.1, self._on_obj_pos_spin)
        self.spin_obj_pz.setToolTip("Object Position Z (drag to scrub, click to type)")
        pz_row = QHBoxLayout(); pz_row.setSpacing(2)
        pz_row.addWidget(ScrubLabel("Z:", self.spin_obj_pz, color="#3b82f6"), 0)
        pz_row.addWidget(self.spin_obj_pz, 1)
        pos_controls.addLayout(pz_row)

        pos_row.addLayout(pos_controls, 1)
        self.sec_object.add_layout(pos_row)

        # ----------------- 2. ROTATION ROW -----------------
        rot_row = QHBoxLayout(); rot_row.setSpacing(4)
        self.gizmo_rot = RotationGizmoWidget()
        self.gizmo_rot.rotation_changed.connect(self._on_gizmo_rot_changed)
        self.gizmo_rot.interaction_ended.connect(self._on_interaction_ended)
        self.gizmo_rot.interaction_ended.connect(self._schedule_save)
        rot_row.addWidget(self.gizmo_rot, 0)

        rot_controls = QVBoxLayout(); rot_controls.setSpacing(1)
        rot_hdr = QHBoxLayout(); rot_hdr.setSpacing(2)
        lbl_r_title = QLabel("Rotation")
        lbl_r_title.setStyleSheet("font-weight:bold; font-size:10px; color:#e2e8f0;")
        rot_hdr.addWidget(lbl_r_title, 1)
        btn_rst_rot = QPushButton("↺")
        btn_rst_rot.setFixedSize(18, 16)
        btn_rst_rot.setToolTip("Reset object rotation to (0°, 0°, 0°)")
        btn_rst_rot.clicked.connect(self._reset_obj_rot)
        rot_hdr.addWidget(btn_rst_rot, 0)
        rot_controls.addLayout(rot_hdr)

        self.spin_obj_rx = self._dspin(-360.0, 360.0, 0.0, 1.0, self._on_obj_rot_spin)
        self.spin_obj_rx.setSuffix("°")
        self.spin_obj_rx.setToolTip("Object Rotation X (Pitch) (drag to scrub, click to type)")
        rx_row = QHBoxLayout(); rx_row.setSpacing(2)
        rx_row.addWidget(ScrubLabel("X:", self.spin_obj_rx, color="#ef4444"), 0)
        rx_row.addWidget(self.spin_obj_rx, 1)
        rot_controls.addLayout(rx_row)

        self.spin_obj_ry = self._dspin(-360.0, 360.0, 0.0, 1.0, self._on_obj_rot_spin)
        self.spin_obj_ry.setSuffix("°")
        self.spin_obj_ry.setToolTip("Object Rotation Y (Yaw) (drag to scrub, click to type)")
        ry_row = QHBoxLayout(); ry_row.setSpacing(2)
        ry_row.addWidget(ScrubLabel("Y:", self.spin_obj_ry, color="#22c55e"), 0)
        ry_row.addWidget(self.spin_obj_ry, 1)
        rot_controls.addLayout(ry_row)

        self.spin_obj_rz = self._dspin(-360.0, 360.0, 0.0, 1.0, self._on_obj_rot_spin)
        self.spin_obj_rz.setSuffix("°")
        self.spin_obj_rz.setToolTip("Object Rotation Z (Roll) (drag to scrub, click to type)")
        rz_row = QHBoxLayout(); rz_row.setSpacing(2)
        rz_row.addWidget(ScrubLabel("Z:", self.spin_obj_rz, color="#3b82f6"), 0)
        rz_row.addWidget(self.spin_obj_rz, 1)
        rot_controls.addLayout(rz_row)

        rot_row.addLayout(rot_controls, 1)
        self.sec_object.add_layout(rot_row)

        # ----------------- 3. SCALE ROW -----------------
        scale_row = QHBoxLayout(); scale_row.setSpacing(4)
        self.gizmo_scale = ScaleGizmoWidget()
        self.gizmo_scale.scale_changed.connect(self._on_gizmo_scale_changed)
        self.gizmo_scale.interaction_ended.connect(self._on_interaction_ended)
        self.gizmo_scale.interaction_ended.connect(self._schedule_save)
        scale_row.addWidget(self.gizmo_scale, 0)

        scale_controls = QVBoxLayout(); scale_controls.setSpacing(1)
        scale_hdr = QHBoxLayout(); scale_hdr.setSpacing(2)
        lbl_s_title = QLabel("Scale")
        lbl_s_title.setStyleSheet("font-weight:bold; font-size:10px; color:#e2e8f0;")
        scale_hdr.addWidget(lbl_s_title, 1)

        self.btn_uniform_scale = QPushButton("🔗")
        self.btn_uniform_scale.setCheckable(True)
        self.btn_uniform_scale.setChecked(True)
        self.btn_uniform_scale.setFixedSize(18, 16)
        self.btn_uniform_scale.setStyleSheet("QPushButton:checked { background: #2563eb; color: #fff; }")
        self.btn_uniform_scale.setToolTip("Uniform Scale Lock (toggle to scale all axes proportionally or independently)")
        scale_hdr.addWidget(self.btn_uniform_scale, 0)

        btn_rst_scale = QPushButton("↺")
        btn_rst_scale.setFixedSize(18, 16)
        btn_rst_scale.setToolTip("Reset object scale to (1.0, 1.0, 1.0)")
        btn_rst_scale.clicked.connect(self._reset_obj_scale)
        scale_hdr.addWidget(btn_rst_scale, 0)
        scale_controls.addLayout(scale_hdr)

        self.spin_obj_sx = self._dspin(0.01, 100.0, 1.0, 0.05, self._on_obj_scale_spin)
        self.spin_obj_sx.setToolTip("Object Scale X (drag to scrub, click to type)")
        sx_row = QHBoxLayout(); sx_row.setSpacing(2)
        sx_row.addWidget(ScrubLabel("X:", self.spin_obj_sx, color="#ef4444"), 0)
        sx_row.addWidget(self.spin_obj_sx, 1)
        scale_controls.addLayout(sx_row)

        self.spin_obj_sy = self._dspin(0.01, 100.0, 1.0, 0.05, self._on_obj_scale_spin)
        self.spin_obj_sy.setToolTip("Object Scale Y (drag to scrub, click to type)")
        sy_row = QHBoxLayout(); sy_row.setSpacing(2)
        sy_row.addWidget(ScrubLabel("Y:", self.spin_obj_sy, color="#22c55e"), 0)
        sy_row.addWidget(self.spin_obj_sy, 1)
        scale_controls.addLayout(sy_row)

        self.spin_obj_sz = self._dspin(0.01, 100.0, 1.0, 0.05, self._on_obj_scale_spin)
        self.spin_obj_sz.setToolTip("Object Scale Z (drag to scrub, click to type)")
        sz_row = QHBoxLayout(); sz_row.setSpacing(2)
        sz_row.addWidget(ScrubLabel("Z:", self.spin_obj_sz, color="#3b82f6"), 0)
        sz_row.addWidget(self.spin_obj_sz, 1)
        scale_controls.addLayout(sz_row)

        scale_row.addLayout(scale_controls, 1)
        self.sec_object.add_layout(scale_row)

        # ----------------- 4. PRIMITIVE PARAMETERS FRAME -----------------
        self.frame_primitive = QFrame()
        self.frame_primitive.setStyleSheet(
            "QFrame { background: #1c2230; border: 1px solid #3b82f6; border-radius: 4px; padding: 2px; }"
        )
        l_prim = QVBoxLayout(self.frame_primitive)
        l_prim.setContentsMargins(4, 4, 4, 4)
        l_prim.setSpacing(2)

        prim_hdr_row = QHBoxLayout(); prim_hdr_row.setSpacing(2)
        self.lbl_primitive_title = QLabel("📦 Primitive Parameters")
        self.lbl_primitive_title.setStyleSheet("font-weight:bold; font-size:10px; color:#93c5fd;")
        prim_hdr_row.addWidget(self.lbl_primitive_title, 1)

        self.combo_primitive_type = QComboBox()
        self.combo_primitive_type.addItems(["📦 Box", "🛢️ Cylinder", "🔮 Sphere", "📐 Pyramid", "🍦 Cone", "🏁 Plane"])
        self.combo_primitive_type.setToolTip("Select or convert primitive shape")
        self.combo_primitive_type.currentTextChanged.connect(self._on_primitive_type_selected)
        prim_hdr_row.addWidget(self.combo_primitive_type, 1)
        l_prim.addLayout(prim_hdr_row)

        # -- Box sub-widget --
        self.w_prim_box = QWidget()
        l_p_box = QVBoxLayout(self.w_prim_box); l_p_box.setContentsMargins(0, 0, 0, 0); l_p_box.setSpacing(1)
        b_r1 = QHBoxLayout(); b_r1.setSpacing(2)
        self.spin_prim_box_w = self._dspin(0.05, 50.0, 2.0, 0.1, self._on_primitive_param_changed)
        b_r1.addWidget(ScrubLabel("Width:", self.spin_prim_box_w), 0)
        b_r1.addWidget(self.spin_prim_box_w, 1)
        self.spin_prim_box_h = self._dspin(0.05, 50.0, 2.0, 0.1, self._on_primitive_param_changed)
        b_r1.addWidget(ScrubLabel("Height:", self.spin_prim_box_h), 0)
        b_r1.addWidget(self.spin_prim_box_h, 1)
        l_p_box.addLayout(b_r1)
        b_r2 = QHBoxLayout(); b_r2.setSpacing(2)
        self.spin_prim_box_d = self._dspin(0.05, 50.0, 2.0, 0.1, self._on_primitive_param_changed)
        b_r2.addWidget(ScrubLabel("Depth:", self.spin_prim_box_d), 0)
        b_r2.addWidget(self.spin_prim_box_d, 1)
        l_p_box.addLayout(b_r2)
        l_prim.addWidget(self.w_prim_box)

        # -- Cylinder sub-widget --
        self.w_prim_cyl = QWidget()
        l_p_cyl = QVBoxLayout(self.w_prim_cyl); l_p_cyl.setContentsMargins(0, 0, 0, 0); l_p_cyl.setSpacing(1)
        c_r1 = QHBoxLayout(); c_r1.setSpacing(2)
        self.spin_prim_cyl_r = self._dspin(0.05, 50.0, 1.0, 0.1, self._on_primitive_param_changed)
        c_r1.addWidget(ScrubLabel("Radius:", self.spin_prim_cyl_r), 0)
        c_r1.addWidget(self.spin_prim_cyl_r, 1)
        self.spin_prim_cyl_h = self._dspin(0.05, 50.0, 2.0, 0.1, self._on_primitive_param_changed)
        c_r1.addWidget(ScrubLabel("Height:", self.spin_prim_cyl_h), 0)
        c_r1.addWidget(self.spin_prim_cyl_h, 1)
        l_p_cyl.addLayout(c_r1)
        c_r2 = QHBoxLayout(); c_r2.setSpacing(2)
        self.spin_prim_cyl_seg = self._ispin(3, 64, 24, 1, self._on_primitive_param_changed)
        c_r2.addWidget(ScrubLabel("Segments:", self.spin_prim_cyl_seg), 0)
        c_r2.addWidget(self.spin_prim_cyl_seg, 1)
        l_p_cyl.addLayout(c_r2)
        l_prim.addWidget(self.w_prim_cyl)

        # -- Sphere sub-widget --
        self.w_prim_sph = QWidget()
        l_p_sph = QVBoxLayout(self.w_prim_sph); l_p_sph.setContentsMargins(0, 0, 0, 0); l_p_sph.setSpacing(1)
        s_r1 = QHBoxLayout(); s_r1.setSpacing(2)
        self.spin_prim_sph_r = self._dspin(0.05, 50.0, 1.0, 0.1, self._on_primitive_param_changed)
        s_r1.addWidget(ScrubLabel("Radius:", self.spin_prim_sph_r), 0)
        s_r1.addWidget(self.spin_prim_sph_r, 1)
        l_p_sph.addLayout(s_r1)
        s_r2 = QHBoxLayout(); s_r2.setSpacing(2)
        self.spin_prim_sph_rings = self._ispin(4, 48, 16, 1, self._on_primitive_param_changed)
        s_r2.addWidget(ScrubLabel("Rings:", self.spin_prim_sph_rings), 0)
        s_r2.addWidget(self.spin_prim_sph_rings, 1)
        self.spin_prim_sph_sectors = self._ispin(4, 48, 24, 1, self._on_primitive_param_changed)
        s_r2.addWidget(ScrubLabel("Sectors:", self.spin_prim_sph_sectors), 0)
        s_r2.addWidget(self.spin_prim_sph_sectors, 1)
        l_p_sph.addLayout(s_r2)
        l_prim.addWidget(self.w_prim_sph)

        # -- Pyramid sub-widget --
        self.w_prim_pyr = QWidget()
        l_p_pyr = QVBoxLayout(self.w_prim_pyr); l_p_pyr.setContentsMargins(0, 0, 0, 0); l_p_pyr.setSpacing(1)
        py_r1 = QHBoxLayout(); py_r1.setSpacing(2)
        self.spin_prim_pyr_w = self._dspin(0.05, 50.0, 2.0, 0.1, self._on_primitive_param_changed)
        py_r1.addWidget(ScrubLabel("Width:", self.spin_prim_pyr_w), 0)
        py_r1.addWidget(self.spin_prim_pyr_w, 1)
        self.spin_prim_pyr_h = self._dspin(0.05, 50.0, 2.0, 0.1, self._on_primitive_param_changed)
        py_r1.addWidget(ScrubLabel("Height:", self.spin_prim_pyr_h), 0)
        py_r1.addWidget(self.spin_prim_pyr_h, 1)
        l_p_pyr.addLayout(py_r1)
        py_r2 = QHBoxLayout(); py_r2.setSpacing(2)
        self.spin_prim_pyr_d = self._dspin(0.05, 50.0, 2.0, 0.1, self._on_primitive_param_changed)
        py_r2.addWidget(ScrubLabel("Depth:", self.spin_prim_pyr_d), 0)
        py_r2.addWidget(self.spin_prim_pyr_d, 1)
        l_p_pyr.addLayout(py_r2)
        l_prim.addWidget(self.w_prim_pyr)

        # -- Cone sub-widget --
        self.w_prim_cone = QWidget()
        l_p_cone = QVBoxLayout(self.w_prim_cone); l_p_cone.setContentsMargins(0, 0, 0, 0); l_p_cone.setSpacing(1)
        co_r1 = QHBoxLayout(); co_r1.setSpacing(2)
        self.spin_prim_cone_r = self._dspin(0.05, 50.0, 1.0, 0.1, self._on_primitive_param_changed)
        co_r1.addWidget(ScrubLabel("Radius:", self.spin_prim_cone_r), 0)
        co_r1.addWidget(self.spin_prim_cone_r, 1)
        self.spin_prim_cone_h = self._dspin(0.05, 50.0, 2.0, 0.1, self._on_primitive_param_changed)
        co_r1.addWidget(ScrubLabel("Height:", self.spin_prim_cone_h), 0)
        co_r1.addWidget(self.spin_prim_cone_h, 1)
        l_p_cone.addLayout(co_r1)
        co_r2 = QHBoxLayout(); co_r2.setSpacing(2)
        self.spin_prim_cone_seg = self._ispin(3, 64, 24, 1, self._on_primitive_param_changed)
        co_r2.addWidget(ScrubLabel("Segments:", self.spin_prim_cone_seg), 0)
        co_r2.addWidget(self.spin_prim_cone_seg, 1)
        l_p_cone.addLayout(co_r2)
        l_prim.addWidget(self.w_prim_cone)

        # -- Plane sub-widget --
        self.w_prim_plane = QWidget()
        l_p_pl = QVBoxLayout(self.w_prim_plane); l_p_pl.setContentsMargins(0, 0, 0, 0); l_p_pl.setSpacing(1)
        pl_r1 = QHBoxLayout(); pl_r1.setSpacing(2)
        self.spin_prim_plane_w = self._dspin(0.05, 50.0, 2.0, 0.1, self._on_primitive_param_changed)
        pl_r1.addWidget(ScrubLabel("Width:", self.spin_prim_plane_w), 0)
        pl_r1.addWidget(self.spin_prim_plane_w, 1)
        self.spin_prim_plane_d = self._dspin(0.05, 50.0, 2.0, 0.1, self._on_primitive_param_changed)
        pl_r1.addWidget(ScrubLabel("Depth:", self.spin_prim_plane_d), 0)
        pl_r1.addWidget(self.spin_prim_plane_d, 1)
        l_p_pl.addLayout(pl_r1)
        pl_r2 = QHBoxLayout(); pl_r2.setSpacing(2)
        self.spin_prim_plane_sub = self._ispin(1, 32, 2, 1, self._on_primitive_param_changed)
        pl_r2.addWidget(ScrubLabel("Subdiv:", self.spin_prim_plane_sub), 0)
        pl_r2.addWidget(self.spin_prim_plane_sub, 1)
        l_p_pl.addLayout(pl_r2)
        l_prim.addWidget(self.w_prim_plane)

        self.sec_object.add_widget(self.frame_primitive)
        self.frame_primitive.setVisible(False)

        L.addWidget(self.sec_object)

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

        # Field of View Calibration (Dolly Zoom) for Fisheye
        self.chk_fish_dolly = QCheckBox("Lock 3D Size (FOV Calibration)")
        self.chk_fish_dolly.setChecked(False)
        self.chk_fish_dolly.setStyleSheet("font-size: 9px; color: #38bdf8;")
        self.chk_fish_dolly.setToolTip(
            "Field of View Calibration: When changing Fisheye FOV, automatically compensate camera distance "
            "so the 3D model maintains its exact apparent size in the viewport (Dolly Zoom)."
        )
        self.chk_fish_dolly.stateChanged.connect(lambda s: self._sync_dolly_checks(s, source=self.chk_fish_dolly))
        l_fish.addWidget(self.chk_fish_dolly)

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
        self.lbl_tilt = QLabel("Pitch 12°")
        tr_pitch.addWidget(self.lbl_tilt)
        b_p0 = QPushButton("0"); b_p0.setFixedSize(20, 18); b_p0.setToolTip("Level orbit pitch to 0°"); b_p0.clicked.connect(self._reset_pitch)
        tr_pitch.addWidget(b_p0)
        self.sec_cam.add_layout(tr_pitch)
        self.sl_tilt = self._slider(-89, 89, 12, self._on_tilt)
        self.sl_tilt.setToolTip("Orbit pitch angle up/down around target")
        self.sec_cam.add_widget(self.sl_tilt)

        # Azimuth / Yaw
        self.lbl_yaw = QLabel("Yaw 145°")
        self.sec_cam.add_widget(self.lbl_yaw)
        self.sl_yaw = self._slider(0, 360, 145, self._on_yaw)
        self.sl_yaw.setToolTip("Horizontal orbit azimuth around target (0° to 360°)")
        self.sec_cam.add_widget(self.sl_yaw)

        # Lens Tilt (optical axis shift)
        tr_ltilt = QHBoxLayout(); tr_ltilt.setSpacing(1)
        self.lbl_lens_tilt = QLabel("Tilt 0°")
        self.lbl_lens_tilt.setStyleSheet("font-weight:bold; color:#38bdf8;")
        tr_ltilt.addWidget(self.lbl_lens_tilt)
        b_llevel = QPushButton("0"); b_llevel.setFixedSize(20, 18); b_llevel.setToolTip("Set camera lens tilt to 0°"); b_llevel.clicked.connect(self._reset_lens_tilt)
        tr_ltilt.addWidget(b_llevel)
        self.sec_cam.add_layout(tr_ltilt)
        self.sl_lens_tilt = self._slider(-89, 89, 0, self._on_lens_tilt)
        self.sl_lens_tilt.setToolTip("Tilt the camera view axis vertically without moving camera eye position")
        self.sec_cam.add_widget(self.sl_lens_tilt)

        # Camera Roll
        rr = QHBoxLayout(); rr.setSpacing(1)
        self.lbl_roll = QLabel("Roll 0°")
        rr.addWidget(self.lbl_roll)
        b_r0 = QPushButton("0"); b_r0.setFixedSize(20, 18); b_r0.setToolTip("Reset camera roll to 0°"); b_r0.clicked.connect(self._reset_roll)
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

        # Field of View Calibration (Dolly Zoom / Constant Framing)
        self.chk_dolly_zoom = QCheckBox("Lock 3D Size (FOV Calibration)")
        self.chk_dolly_zoom.setChecked(False)
        self.chk_dolly_zoom.setStyleSheet("font-size: 9px; color: #38bdf8;")
        self.chk_dolly_zoom.setToolTip(
            "Field of View Calibration: When changing FOV, automatically zoom camera distance "
            "so the 3D model maintains the exact same apparent size in the viewport (Dolly Zoom)."
        )
        self.chk_dolly_zoom.stateChanged.connect(lambda s: self._sync_dolly_checks(s, source=self.chk_dolly_zoom))
        self.sec_cam.add_widget(self.chk_dolly_zoom)

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
        self.sl_dist = self._slider(1, 1000, 28, self._on_dist)
        self.sl_dist.setToolTip("Camera distance to target (zoom)")
        self.sec_cam.add_widget(self.sl_dist)

        pan_row = QHBoxLayout(); pan_row.setSpacing(2)
        pan_lbl = QLabel("Pan:"); pan_lbl.setStyleSheet("font-size:9px; color:#94a3b8;")
        pan_row.addWidget(pan_lbl)
        self.spin_pan_x = self._dspin(-50.0, 50.0, 0.0, 0.1, self._on_pan_spins)
        self.spin_pan_x.setToolTip("Pan X: Screen pan horizontal offset (drag left/right to scrub, click to type)")
        pan_row.addWidget(ScrubLabel("X:", self.spin_pan_x))
        pan_row.addWidget(self.spin_pan_x)

        self.spin_pan_y = self._dspin(-50.0, 50.0, 0.0, 0.1, self._on_pan_spins)
        self.spin_pan_y.setToolTip("Pan Y: Screen pan vertical offset (drag left/right to scrub, click to type)")
        pan_row.addWidget(ScrubLabel("Y:", self.spin_pan_y))
        pan_row.addWidget(self.spin_pan_y)

        b_pan_rst = QPushButton("0"); b_pan_rst.setFixedSize(20, 18); b_pan_rst.setToolTip("Reset pan to (0, 0)"); b_pan_rst.clicked.connect(self._reset_pan)
        pan_row.addWidget(b_pan_rst)
        self.sec_cam.add_layout(pan_row)

        # Look-at Target XYZ
        tl = QLabel("Target XYZ:")
        tl.setStyleSheet("font-weight:bold; font-size:9px;")
        self.sec_cam.add_widget(tl)
        tr = QHBoxLayout(); tr.setSpacing(2)
        self.spin_tx = self._dspin(-50, 50, 0.0, 0.1, self._on_target)
        self.spin_tx.setToolTip("Target world X position (drag left/right to scrub, click to type)")
        tr.addWidget(ScrubLabel("X:", self.spin_tx))
        tr.addWidget(self.spin_tx)

        self.spin_ty = self._dspin(-50, 50, 0.0, 0.1, self._on_target)
        self.spin_ty.setToolTip("Target world Y height position (drag left/right to scrub, click to type)")
        tr.addWidget(ScrubLabel("Y:", self.spin_ty))
        tr.addWidget(self.spin_ty)

        self.spin_tz = self._dspin(-50, 50, 0.0, 0.1, self._on_target)
        self.spin_tz.setToolTip("Target world Z depth position (drag left/right to scrub, click to type)")
        tr.addWidget(ScrubLabel("Z:", self.spin_tz))
        tr.addWidget(self.spin_tz)
        self.sec_cam.add_layout(tr)

        # Frame / Center / Origin quick actions
        cam_frame_row = QHBoxLayout(); cam_frame_row.setSpacing(2)
        btn_cam_frame = QPushButton("🎯 Frame")
        btn_cam_frame.setStyleSheet("font-size:9px; padding:2px 3px;")
        btn_cam_frame.setToolTip("Frame 3D model in view (double-click viewport)")
        btn_cam_frame.clicked.connect(self._frame_view)
        cam_frame_row.addWidget(btn_cam_frame)
        btn_cam_center = QPushButton("⌖ Center")
        btn_cam_center.setStyleSheet("font-size:9px; padding:2px 3px;")
        btn_cam_center.setToolTip("Move camera target to model center")
        btn_cam_center.clicked.connect(self._center_on_model)
        cam_frame_row.addWidget(btn_cam_center)
        btn_cam_origin = QPushButton("Origin")
        btn_cam_origin.setStyleSheet("font-size:9px; padding:2px 3px;")
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
        self.btn_ground = QPushButton("📐 Ground Rect")
        self.btn_ground.setStyleSheet("background:#2e3440; color:#93c5fd; font-weight:bold; padding:3px 4px; border:1px solid #4c566a; font-size:9px;")
        self.btn_ground.setToolTip(
            "Ground Rectangle (Draw & Calibrate):\n"
            "Open the Ground Rectangle tool to calibrate camera yaw, tilt, roll, and place 3D model directly on canvas ground."
        )
        self.btn_ground.clicked.connect(lambda: self._open_ground_calibrator())
        calib_row.addWidget(self.btn_ground, 3)

        self.btn_ground_5p = QPushButton("📍 Ground 5P (H)")
        self.btn_ground_5p.setStyleSheet("background:#3b0764; color:#e9d5ff; font-weight:bold; padding:3px 4px; border:1px solid #7e22ce; font-size:9px;")
        self.btn_ground_5p.setToolTip(
            "Ground Rectangle + Height (5-Point Draw):\n"
            "Define 4 ground pins + 5th height point to calibrate perspective & height."
        )
        self.btn_ground_5p.clicked.connect(lambda: self._open_ground_calibrator(initial_mode=5))
        calib_row.addWidget(self.btn_ground_5p, 2)

        btn_full_canv = QPushButton("🖥️ Full")
        btn_full_canv.setStyleSheet("background:#1e293b; color:#e2e8f0; font-weight:bold; padding:3px 3px; border:1px solid #334155; font-size:9px;")
        btn_full_canv.setToolTip("Match viewport ratio to full Krita canvas (clears frame limit)")
        btn_full_canv.clicked.connect(self._use_full_canvas)
        calib_row.addWidget(btn_full_canv, 1)

        btn_draw_frame = QPushButton("✏️ Frame")
        btn_draw_frame.setStyleSheet("background:#1e293b; color:#93c5fd; font-weight:bold; padding:3px 3px; border:1px solid #2563eb; font-size:9px;")
        btn_draw_frame.setToolTip("Define the frame of the 3D scene from active rectangular selection on canvas")
        btn_draw_frame.clicked.connect(self._draw_frame_action)
        calib_row.addWidget(btn_draw_frame, 1)
        self.sec_canvas.add_layout(calib_row)

        self.chk_use_frame = QCheckBox("Limit 3D to Canvas Frame")
        self.chk_use_frame.setChecked(False)
        self.chk_use_frame.setToolTip("Render 3D object only within this frame on Krita canvas (outside remains untouched)")
        self.chk_use_frame.stateChanged.connect(self._on_frame_toggle)
        self.sec_canvas.add_widget(self.chk_use_frame)

        fr_grid = QGridLayout(); fr_grid.setSpacing(1)
        self.spin_fx = self._ispin(0, 20000, 0, 10, self._on_frame_spins)
        self.spin_fx.setToolTip("Frame left pixel coordinate (drag left/right to scrub, click to type)")
        fr_grid.addWidget(ScrubLabel("X:", self.spin_fx), 0, 0)
        fr_grid.addWidget(self.spin_fx, 0, 1)

        self.spin_fy = self._ispin(0, 20000, 0, 10, self._on_frame_spins)
        self.spin_fy.setToolTip("Frame top pixel coordinate (drag left/right to scrub, click to type)")
        fr_grid.addWidget(ScrubLabel("Y:", self.spin_fy), 0, 2)
        fr_grid.addWidget(self.spin_fy, 0, 3)

        self.spin_fw = self._ispin(1, 20000, 800, 10, self._on_frame_spins)
        self.spin_fw.setToolTip("Frame width in pixels (drag left/right to scrub, click to type)")
        fr_grid.addWidget(ScrubLabel("W:", self.spin_fw), 1, 0)
        fr_grid.addWidget(self.spin_fw, 1, 1)

        self.spin_fh = self._ispin(1, 20000, 600, 10, self._on_frame_spins)
        self.spin_fh.setToolTip("Frame height in pixels (drag left/right to scrub, click to type)")
        fr_grid.addWidget(ScrubLabel("H:", self.spin_fh), 1, 2)
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
        self.chk_grid_canvas = QCheckBox("Canvas Grid")
        self.chk_grid_canvas.setToolTip("Draw 3D perspective grid directly onto the Krita canvas layer (with or without 3D model)")
        self.chk_grid_canvas.stateChanged.connect(self._on_grid_changed)
        gr_toggles.addWidget(self.chk_grid_canvas)

        self.chk_grid_viewport = QCheckBox("Viewport")
        self.chk_grid_viewport.setChecked(True)
        self.chk_grid_viewport.setToolTip("Show perspective grid in 3D viewport")
        self.chk_grid_viewport.stateChanged.connect(self._on_grid_changed)
        gr_toggles.addWidget(self.chk_grid_viewport)
        self.sec_grid.add_layout(gr_toggles)

        hr_row = QHBoxLayout(); hr_row.setSpacing(2)
        self.chk_grid_horizon = QCheckBox("Horizon")
        self.chk_grid_horizon.setChecked(True)
        self.chk_grid_horizon.setToolTip("Draw eye-level horizon line across canvas")
        self.chk_grid_horizon.stateChanged.connect(self._on_grid_changed)
        hr_row.addWidget(self.chk_grid_horizon)

        self.chk_horizon_level = QCheckBox("Level")
        self.chk_horizon_level.setChecked(False)
        self.chk_horizon_level.setToolTip("Always Horizontal: keep horizon line strictly horizontal regardless of camera roll")
        self.chk_horizon_level.stateChanged.connect(self._on_grid_changed)
        hr_row.addWidget(self.chk_horizon_level)

        self.chk_grid_ground = QCheckBox("Ground Grid")
        self.chk_grid_ground.setChecked(True)
        self.chk_grid_ground.setToolTip("Draw ground floor perspective grid squares")
        self.chk_grid_ground.stateChanged.connect(self._on_grid_changed)
        hr_row.addWidget(self.chk_grid_ground)
        self.sec_grid.add_layout(hr_row)

        ceil_row = QHBoxLayout(); ceil_row.setSpacing(2)
        self.chk_grid_ceiling = QCheckBox("Ceiling Grid")
        self.chk_grid_ceiling.setChecked(False)
        self.chk_grid_ceiling.setToolTip("Draw a matching ceiling grid above the scene at ceiling height")
        self.chk_grid_ceiling.stateChanged.connect(self._on_grid_changed)
        ceil_row.addWidget(self.chk_grid_ceiling)

        self.chk_grid_verticals = QCheckBox("Height Poles")
        self.chk_grid_verticals.setChecked(True)
        self.chk_grid_verticals.setToolTip("Draw vertical guide poles for 3D vertical perspective")
        self.chk_grid_verticals.stateChanged.connect(self._on_grid_changed)
        ceil_row.addWidget(self.chk_grid_verticals)
        self.sec_grid.add_layout(ceil_row)

        # Grid parameters: Extent, Tile Size, Ceiling Height, Subdivisions
        p_row1 = QHBoxLayout(); p_row1.setSpacing(2)
        self.spin_grid_extent = self._ispin(2, 60, 10, 1, self._on_grid_changed)
        self.spin_grid_extent.setToolTip("Number of grid tiles from origin in each direction (drag left/right to scrub, click to type)")
        p_row1.addWidget(ScrubLabel("Tiles:", self.spin_grid_extent))
        p_row1.addWidget(self.spin_grid_extent, 1)

        self.spin_grid_tile = self._dspin(0.05, 10.0, 0.5, 0.05, self._on_grid_changed)
        self.spin_grid_tile.setToolTip("Size of each square tile in 3D units (drag left/right to scrub, click to type)")
        p_row1.addWidget(ScrubLabel("Size:", self.spin_grid_tile))
        p_row1.addWidget(self.spin_grid_tile, 1)
        self.sec_grid.add_layout(p_row1)

        p_row2 = QHBoxLayout(); p_row2.setSpacing(2)
        self.spin_grid_cheight = self._dspin(0.5, 20.0, 2.5, 0.2, self._on_grid_changed)
        self.spin_grid_cheight.setToolTip("Height of ceiling grid above the floor in 3D units (drag left/right to scrub, click to type)")
        p_row2.addWidget(ScrubLabel("Ceil H:", self.spin_grid_cheight))
        p_row2.addWidget(self.spin_grid_cheight, 1)

        self.spin_grid_subdiv = self._ispin(1, 10, 1, 1, self._on_grid_changed)
        self.spin_grid_subdiv.setToolTip("Subdivisions per square tile (drag left/right to scrub, click to type)")
        p_row2.addWidget(ScrubLabel("Subdiv:", self.spin_grid_subdiv))
        p_row2.addWidget(self.spin_grid_subdiv, 1)
        self.sec_grid.add_layout(p_row2)

        # Horizon extension & Horizon Fading
        fade_row = QHBoxLayout(); fade_row.setSpacing(2)
        self.chk_grid_exceed = QCheckBox("Extend Horizon")
        self.chk_grid_exceed.setChecked(True)
        self.chk_grid_exceed.setToolTip("Extend grid lines deep into the distance toward horizon")
        self.chk_grid_exceed.stateChanged.connect(self._on_grid_changed)
        fade_row.addWidget(self.chk_grid_exceed)

        self.chk_fade_grid = QCheckBox("Fade Horizon")
        self.chk_fade_grid.setChecked(False)
        self.chk_fade_grid.setToolTip("Activate Fading Grid: Grid lines extend to the horizon line but fade out smoothly little by little")
        self.chk_fade_grid.stateChanged.connect(self._on_grid_changed)
        fade_row.addWidget(self.chk_fade_grid)
        self.sec_grid.add_layout(fade_row)

        self.chk_grid_axis = QCheckBox("Color XYZ Axes")
        self.chk_grid_axis.setChecked(True)
        self.chk_grid_axis.setToolTip("Highlight primary 3D world axes with color (Red X, Blue Z, Green Y)")
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
        rl = QPushButton("Rst")
        rl.setFixedSize(30, 20)
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

        # Performance: Render Quality & Refresh Rate Debounce
        perf_hdr = QLabel("Performance & Refresh Rate:")
        perf_hdr.setStyleSheet("font-weight:bold; color:#93c5fd;")
        self.sec_settings.add_widget(perf_hdr)

        q_row = QHBoxLayout(); q_row.setSpacing(2)
        q_row.addWidget(QLabel("Quality:"))
        self.combo_quality = QComboBox()
        self.combo_quality.addItems(["⚡ Fast (Draft)", "⚖️ Balanced (Standard)", "💎 High (Super-Sampled)"])
        self.combo_quality.setCurrentIndex(1)
        self.combo_quality.setToolTip("Render quality: Fast reduces CPU load on huge canvases, High enables super-sampling")
        self.combo_quality.currentIndexChanged.connect(self._on_quality_changed)
        q_row.addWidget(self.combo_quality, 1)
        self.sec_settings.add_layout(q_row)

        rate_row = QHBoxLayout(); rate_row.setSpacing(2)
        self.spin_debounce = self._ispin(30, 1000, 120, 10, self._on_debounce_changed)
        self.spin_debounce.setToolTip("Delay in milliseconds before updating Krita canvas layer when dragging (debounce delay)")
        rate_row.addWidget(ScrubLabel("Refresh Rate (ms):", self.spin_debounce))
        rate_row.addWidget(self.spin_debounce, 1)
        self.sec_settings.add_layout(rate_row)

        # Canvas Layer Background Color & Transparent background
        bg_hdr = QLabel("Canvas Layer Background:")
        bg_hdr.setStyleSheet("font-weight:bold; color:#93c5fd; margin-top:3px;")
        self.sec_settings.add_widget(bg_hdr)

        bg_row = QHBoxLayout(); bg_row.setSpacing(2)
        self.chk_transp = QCheckBox("Transparent Layer BG (T.BG)")
        self.chk_transp.setChecked(True)
        self.chk_transp.setToolTip("Render 3D object onto Krita layer with transparent background")
        self.chk_transp.stateChanged.connect(self._live_sync)
        self.chk_transp.stateChanged.connect(self._schedule_save)
        bg_row.addWidget(self.chk_transp, 1)

        self.btn_bg_col = QPushButton("🎨 Layer BG")
        self.btn_bg_col.setToolTip("Pick solid background color for Krita layer (used when T.BG is unchecked)")
        self.btn_bg_col.clicked.connect(self._pick_bg_color)
        bg_row.addWidget(self.btn_bg_col, 0)
        self.sec_settings.add_layout(bg_row)

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

        L.addWidget(self.sec_settings)

        # =============================================================
        # SECTION 8: 3D VIEWPORT SETTINGS
        # =============================================================
        self.sec_viewport_settings = CollapsibleSection("3D VIEWPORT SETTINGS", expanded=False)

        # 1. Viewport Display Elements
        lbl_vp_disp = QLabel("Viewport Display Elements:")
        lbl_vp_disp.setStyleSheet("font-weight:bold; color:#93c5fd;")
        self.sec_viewport_settings.add_widget(lbl_vp_disp)

        self.chk_vp_top_labels = QCheckBox("Show Viewport Top Info Bar (Angles, FOV)")
        self.chk_vp_top_labels.setChecked(True)
        self.chk_vp_top_labels.setToolTip("Show/hide camera yaw, pitch, FOV, and mesh stats overlay at top of viewport")
        self.chk_vp_top_labels.stateChanged.connect(self._on_toggle_vp_top_labels)
        self.sec_viewport_settings.add_widget(self.chk_vp_top_labels)

        self.chk_show_overlay = QCheckBox("Show Overlay Nav Buttons (Right edge)")
        self.chk_show_overlay.setChecked(True)
        self.chk_show_overlay.setToolTip("Show/hide mini navigation buttons (Orbit, Pan, Zoom, Tilt, Roll) on right edge of viewport")
        self.chk_show_overlay.stateChanged.connect(self._on_toggle_overlay_buttons)
        self.sec_viewport_settings.add_widget(self.chk_show_overlay)

        self.chk_show_gizmo = QCheckBox("Show 3D XYZ Axis Orientation Gizmo")
        self.chk_show_gizmo.setChecked(True)
        self.chk_show_gizmo.setToolTip("Show/hide 3D coordinate axis orientation gizmo in bottom-left corner of viewport")
        self.chk_show_gizmo.stateChanged.connect(self._on_toggle_gizmo)
        self.sec_viewport_settings.add_widget(self.chk_show_gizmo)

        self.chk_vp_orbit_btn = QCheckBox("Show Bottom Orbit Pivot Button")
        self.chk_vp_orbit_btn.setChecked(True)
        self.chk_vp_orbit_btn.setToolTip("Show/hide orbit pivot target button (Obj / Origin / View) at bottom of viewport")
        self.chk_vp_orbit_btn.stateChanged.connect(self._on_toggle_vp_orbit_button)
        self.sec_viewport_settings.add_widget(self.chk_vp_orbit_btn)

        self.chk_show_frame_guide = QCheckBox("Show Canvas Aspect Frame Guide")
        self.chk_show_frame_guide.setChecked(True)
        self.chk_show_frame_guide.setToolTip("Show dashed framing border indicating active Krita canvas aspect ratio")
        self.chk_show_frame_guide.stateChanged.connect(self._on_toggle_frame_guide)
        self.sec_viewport_settings.add_widget(self.chk_show_frame_guide)

        self.chk_vp_quick_toolbar = QCheckBox("Show Quick Actions Mini Toolbar")
        self.chk_vp_quick_toolbar.setChecked(True)
        self.chk_vp_quick_toolbar.setToolTip("Show/hide customizable quick action shortcut buttons beneath viewport")
        self.chk_vp_quick_toolbar.stateChanged.connect(self._on_toggle_quick_toolbar)
        self.sec_viewport_settings.add_widget(self.chk_vp_quick_toolbar)

        self.chk_sticky_viewport = QCheckBox("Sticky Viewport (Pinned at Top of Docker)")
        self.chk_sticky_viewport.setChecked(True)
        self.chk_sticky_viewport.setToolTip("When enabled, 3D viewport stays pinned at top while scrolling controls")
        self.chk_sticky_viewport.stateChanged.connect(self._on_toggle_sticky_viewport)
        self.sec_viewport_settings.add_widget(self.chk_sticky_viewport)

        # 2. Viewport Background Styling
        lbl_vp_bg = QLabel("Viewport Background Styling:")
        lbl_vp_bg.setStyleSheet("font-weight:bold; color:#93c5fd; margin-top:4px;")
        self.sec_viewport_settings.add_widget(lbl_vp_bg)

        self.chk_vp_bg_gradient = QCheckBox("Use Gradient Background (vs Solid)")
        self.chk_vp_bg_gradient.setChecked(True)
        self.chk_vp_bg_gradient.setToolTip("Render a smooth vertical gradient across the viewport background instead of a flat solid color")
        self.chk_vp_bg_gradient.stateChanged.connect(self._on_toggle_vp_gradient)
        self.sec_viewport_settings.add_widget(self.chk_vp_bg_gradient)

        bg_col_row = QHBoxLayout(); bg_col_row.setSpacing(4)
        self.btn_vp_bg_top = QPushButton("🎨 Top / Solid Color")
        self.btn_vp_bg_top.setToolTip("Pick solid background color or top color of gradient")
        self.btn_vp_bg_top.clicked.connect(self._pick_vp_bg_top_color)
        bg_col_row.addWidget(self.btn_vp_bg_top, 1)

        self.btn_vp_bg_bot = QPushButton("🎨 Bottom Color")
        self.btn_vp_bg_bot.setToolTip("Pick bottom color of gradient")
        self.btn_vp_bg_bot.clicked.connect(self._pick_vp_bg_bottom_color)
        bg_col_row.addWidget(self.btn_vp_bg_bot, 1)
        self.sec_viewport_settings.add_layout(bg_col_row)

        # Theme preset buttons row
        theme_row = QHBoxLayout(); theme_row.setSpacing(2)
        btn_th1 = QPushButton("Studio"); btn_th1.setToolTip("Studio Dark Theme (#323844 to #181b22)")
        btn_th1.clicked.connect(lambda: self._set_vp_theme(QColor(50, 56, 68), QColor(24, 27, 34), True))
        theme_row.addWidget(btn_th1)

        btn_th2 = QPushButton("Slate"); btn_th2.setToolTip("Deep Slate Theme (#1e293b to #0f172a)")
        btn_th2.clicked.connect(lambda: self._set_vp_theme(QColor(30, 41, 59), QColor(15, 23, 42), True))
        theme_row.addWidget(btn_th2)

        btn_th3 = QPushButton("Charcoal"); btn_th3.setToolTip("Charcoal Theme (#23272e to #181a1f)")
        btn_th3.clicked.connect(lambda: self._set_vp_theme(QColor(35, 39, 46), QColor(24, 26, 31), True))
        theme_row.addWidget(btn_th3)

        btn_th4 = QPushButton("Grey"); btn_th4.setToolTip("Neutral Grey Theme (#3d3d3d to #242424)")
        btn_th4.clicked.connect(lambda: self._set_vp_theme(QColor(61, 61, 61), QColor(36, 36, 36), True))
        theme_row.addWidget(btn_th4)

        btn_th5 = QPushButton("Blueprint"); btn_th5.setToolTip("Blueprint Blue Theme (#1e3a5f to #0b192c)")
        btn_th5.clicked.connect(lambda: self._set_vp_theme(QColor(30, 58, 95), QColor(11, 25, 44), True))
        theme_row.addWidget(btn_th5)

        btn_th6 = QPushButton("Solid"); btn_th6.setToolTip("Flat Solid Dark (#1e222b)")
        btn_th6.clicked.connect(lambda: self._set_vp_theme(QColor(30, 34, 43), QColor(30, 34, 43), False))
        theme_row.addWidget(btn_th6)
        self.sec_viewport_settings.add_layout(theme_row)

        # 3. Viewport Height Control
        lbl_vp_size = QLabel("Viewport Height:")
        lbl_vp_size.setStyleSheet("font-weight:bold; color:#93c5fd; margin-top:4px;")
        self.sec_viewport_settings.add_widget(lbl_vp_size)

        vh_row = QHBoxLayout(); vh_row.setSpacing(4)
        self.spin_vp_height = self._ispin(60, 800, 170, 10, self._on_vp_height_spin)
        self.spin_vp_height.setToolTip("Viewport height in pixels (drag left/right or type)")
        vh_row.addWidget(ScrubLabel("Height (px):", self.spin_vp_height))
        vh_row.addWidget(self.spin_vp_height, 1)

        btn_rst_vh = QPushButton("Reset 170px")
        btn_rst_vh.clicked.connect(self._reset_vp_height)
        vh_row.addWidget(btn_rst_vh, 0)
        self.sec_viewport_settings.add_layout(vh_row)

        # 4. Navigation Preferences
        lbl_nav = QLabel("Mouse Drag Navigation Directions:")
        lbl_nav.setStyleSheet("font-weight:bold; color:#93c5fd; margin-top:4px;")
        self.sec_viewport_settings.add_widget(lbl_nav)

        nav_row1 = QHBoxLayout(); nav_row1.setSpacing(2)
        self.chk_invert_orbit_x = QCheckBox("Invert Orbit L/R (Yaw)")
        self.chk_invert_orbit_x.setChecked(True)
        self.chk_invert_orbit_x.setToolTip("Invert horizontal mouse drag direction when orbiting")
        self.chk_invert_orbit_x.stateChanged.connect(self._on_toggle_invert_orbit_x)
        nav_row1.addWidget(self.chk_invert_orbit_x)

        self.chk_invert_orbit_y = QCheckBox("Invert Orbit U/D (Pitch)")
        self.chk_invert_orbit_y.setChecked(False)
        self.chk_invert_orbit_y.setToolTip("Invert vertical mouse drag direction when orbiting")
        self.chk_invert_orbit_y.stateChanged.connect(self._on_toggle_invert_orbit_y)
        nav_row1.addWidget(self.chk_invert_orbit_y)
        self.sec_viewport_settings.add_layout(nav_row1)

        nav_row2 = QHBoxLayout(); nav_row2.setSpacing(2)
        self.chk_invert_pan = QCheckBox("Invert Pan Direction")
        self.chk_invert_pan.setChecked(True)
        self.chk_invert_pan.setToolTip("Invert mouse dragging direction for viewport pan")
        self.chk_invert_pan.stateChanged.connect(self._on_toggle_invert_pan)
        nav_row2.addWidget(self.chk_invert_pan)
        self.sec_viewport_settings.add_layout(nav_row2)

        L.addWidget(self.sec_viewport_settings)

        L.addStretch(1)

        # Connect all collapsible section toggles to schedule auto-save
        for sec in (self.sec_presets, self.sec_model, self.sec_cam,
                    self.sec_canvas, self.sec_grid, self.sec_light, self.sec_settings, self.sec_viewport_settings):
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
        menu.setStyleSheet("QMenu { background:#1e293b; color:#e2e8f0; font-size:11px; } QMenu::item:selected { background:#2563eb; } QMenu::separator { height:1px; background:#334155; margin:3px 0px; }")
        menu.aboutToShow.connect(lambda: self._populate_primitives_menu(menu))
        self.btn_primitives.setMenu(menu)

    def _populate_primitives_menu(self, menu):
        menu.clear()

        # 1. Procedural Primitives (Created by plugin)
        action_title_prim = menu.addAction("── Procedural Primitives ──")
        action_title_prim.setEnabled(False)
        prims = [
            ("📦 Box", "Box"),
            ("🛢️ Cylinder", "Cylinder"),
            ("🔮 Sphere", "Sphere"),
            ("📐 Pyramid", "Pyramid"),
            ("🍦 Cone", "Cone"),
            ("🏁 Plane", "Plane"),
        ]
        for label, ptype in prims:
            act = menu.addAction(label)
            act.setToolTip(f"Create procedural 3D {ptype} with live parameter controls")
            act.triggered.connect(lambda checked, pt=ptype: self._create_primitive(pt))

        menu.addSeparator()

        # 2. DrawerBox History (primitives drawn by the user)
        from .primitive_drawer import load_primitive_history
        hist = load_primitive_history()
        if hist:
            action_title_hist = menu.addAction("── Drawn Box History ──")
            action_title_hist.setEnabled(False)
            for i, entry in enumerate(hist[:8]):
                ptype = entry.get("primitive_type", "Box")
                persp = entry.get("persp_type", "2-Point")
                fov = entry.get("fov", 50.0)
                name = f"✏️ #{i+1}: {ptype} ({persp}, FOV {fov:.0f}°)"
                act = menu.addAction(name)
                act.setToolTip(f"Load drawn {ptype} ({persp} perspective, {fov:.1f}° FOV)")
                act.triggered.connect(lambda checked, e=entry: self._apply_drawn_primitive_entry(e))
            menu.addSeparator()

        # 3. 3D Reference Files from 3D-Primitive/
        base_dir = os.path.dirname(os.path.abspath(__file__))
        prim_dir = os.path.join(base_dir, "3D-Primitive")

        if os.path.isdir(prim_dir):
            files = sorted(os.listdir(prim_dir))
            mesh_files = [f for f in files if os.path.splitext(f)[1].lower() in ('.obj', '.stl', '.glb', '.gltf')]
            if mesh_files:
                action_title_ref = menu.addAction("── Reference Models ──")
                action_title_ref.setEnabled(False)
                for f in mesh_files:
                    path = os.path.join(prim_dir, f)
                    action_name = os.path.splitext(f)[0]
                    icon_prefix = "👤 " if "asaro" in f.lower() or "head" in f.lower() else "📄 "
                    action = menu.addAction(f"{icon_prefix}{action_name}")
                    action.triggered.connect(lambda checked, p=path: self._load_file(p))
                menu.addSeparator()

        # 4. No Object (Grid Only)
        action_grid_only = menu.addAction("🌐 No Object - Only Grid")
        action_grid_only.setToolTip("Clear 3D model and activate perspective grid for drawing guides")
        action_grid_only.triggered.connect(self._select_no_object_only_grid)

    def _apply_drawn_primitive_entry(self, entry):
        ptype = entry.get("primitive_type", "Box")
        w = float(entry.get("box_w", 2.0))
        h = float(entry.get("box_h", 2.0))
        d = float(entry.get("box_d", 2.0))
        if ptype == "Box":
            mesh = create_box_primitive(w, h, d)
        elif ptype == "Cylinder":
            mesh = create_cylinder_primitive(w * 0.5, h, 24)
        elif ptype == "Sphere":
            mesh = create_sphere_primitive(w * 0.5, 16, 24)
        elif ptype == "Pyramid":
            mesh = create_pyramid_primitive(w, h, d)
        elif ptype == "Cone":
            mesh = create_cone_primitive(w * 0.5, h, 24)
        elif ptype == "Plane":
            mesh = create_plane_primitive(w, d, 2)
        else:
            mesh = create_box_primitive(w, h, d)

        sol = dict(entry)
        sol["mesh"] = mesh
        self._on_primitive_drawer_applied(sol)

    # -----------------------------------------------------------------
    # Object Transform & Primitive Controls
    # -----------------------------------------------------------------
    def _on_gizmo_pos_changed(self, x, y, z):
        t = self.viewport.object_transform
        t.pos_x = float(x); t.pos_y = float(y); t.pos_z = float(z)
        if hasattr(self, 'spin_obj_px'):
            self.spin_obj_px.blockSignals(True); self.spin_obj_px.setValue(t.pos_x); self.spin_obj_px.blockSignals(False)
            self.spin_obj_py.blockSignals(True); self.spin_obj_py.setValue(t.pos_y); self.spin_obj_py.blockSignals(False)
            self.spin_obj_pz.blockSignals(True); self.spin_obj_pz.setValue(t.pos_z); self.spin_obj_pz.blockSignals(False)
        self.viewport.update()
        self._live_sync()

    def _on_obj_pos_spin(self):
        t = self.viewport.object_transform
        t.pos_x = self.spin_obj_px.value()
        t.pos_y = self.spin_obj_py.value()
        t.pos_z = self.spin_obj_pz.value()
        if hasattr(self, 'gizmo_pos'):
            self.gizmo_pos.set_position(t.pos_x, t.pos_y, t.pos_z)
        self.viewport.update()
        self._live_sync()

    def _reset_obj_pos(self):
        t = self.viewport.object_transform
        t.reset_position()
        if hasattr(self, 'spin_obj_px'):
            self.spin_obj_px.blockSignals(True); self.spin_obj_px.setValue(0.0); self.spin_obj_px.blockSignals(False)
            self.spin_obj_py.blockSignals(True); self.spin_obj_py.setValue(0.0); self.spin_obj_py.blockSignals(False)
            self.spin_obj_pz.blockSignals(True); self.spin_obj_pz.setValue(0.0); self.spin_obj_pz.blockSignals(False)
        if hasattr(self, 'gizmo_pos'):
            self.gizmo_pos.set_position(0.0, 0.0, 0.0)
        self.viewport.update()
        self._live_sync()
        self._save_session()

    def _on_gizmo_rot_changed(self, rx, ry, rz):
        t = self.viewport.object_transform
        t.rot_x = float(rx); t.rot_y = float(ry); t.rot_z = float(rz)
        if hasattr(self, 'spin_obj_rx'):
            self.spin_obj_rx.blockSignals(True); self.spin_obj_rx.setValue(t.rot_x); self.spin_obj_rx.blockSignals(False)
            self.spin_obj_ry.blockSignals(True); self.spin_obj_ry.setValue(t.rot_y); self.spin_obj_ry.blockSignals(False)
            self.spin_obj_rz.blockSignals(True); self.spin_obj_rz.setValue(t.rot_z); self.spin_obj_rz.blockSignals(False)
        self.viewport.update()
        self._live_sync()

    def _on_obj_rot_spin(self):
        t = self.viewport.object_transform
        t.rot_x = self.spin_obj_rx.value()
        t.rot_y = self.spin_obj_ry.value()
        t.rot_z = self.spin_obj_rz.value()
        if hasattr(self, 'gizmo_rot'):
            self.gizmo_rot.set_rotation(t.rot_x, t.rot_y, t.rot_z)
        self.viewport.update()
        self._live_sync()

    def _reset_obj_rot(self):
        t = self.viewport.object_transform
        t.reset_rotation()
        if hasattr(self, 'spin_obj_rx'):
            self.spin_obj_rx.blockSignals(True); self.spin_obj_rx.setValue(0.0); self.spin_obj_rx.blockSignals(False)
            self.spin_obj_ry.blockSignals(True); self.spin_obj_ry.setValue(0.0); self.spin_obj_ry.blockSignals(False)
            self.spin_obj_rz.blockSignals(True); self.spin_obj_rz.setValue(0.0); self.spin_obj_rz.blockSignals(False)
        if hasattr(self, 'gizmo_rot'):
            self.gizmo_rot.set_rotation(0.0, 0.0, 0.0)
        self.viewport.update()
        self._live_sync()
        self._save_session()

    def _on_gizmo_scale_changed(self, sx, sy, sz):
        t = self.viewport.object_transform
        t.scale_x = float(sx); t.scale_y = float(sy); t.scale_z = float(sz)
        if hasattr(self, 'spin_obj_sx'):
            self.spin_obj_sx.blockSignals(True); self.spin_obj_sx.setValue(t.scale_x); self.spin_obj_sx.blockSignals(False)
            self.spin_obj_sy.blockSignals(True); self.spin_obj_sy.setValue(t.scale_y); self.spin_obj_sy.blockSignals(False)
            self.spin_obj_sz.blockSignals(True); self.spin_obj_sz.setValue(t.scale_z); self.spin_obj_sz.blockSignals(False)
        self.viewport.update()
        self._live_sync()

    def _on_obj_scale_spin(self):
        t = self.viewport.object_transform
        sx = self.spin_obj_sx.value()
        sy = self.spin_obj_sy.value()
        sz = self.spin_obj_sz.value()

        if getattr(self, 'btn_uniform_scale', None) and self.btn_uniform_scale.isChecked():
            sender = self.sender()
            if sender == self.spin_obj_sx and t.scale_x > 0:
                ratio = sx / t.scale_x
                sy = max(0.01, t.scale_y * ratio)
                sz = max(0.01, t.scale_z * ratio)
                self.spin_obj_sy.blockSignals(True); self.spin_obj_sy.setValue(sy); self.spin_obj_sy.blockSignals(False)
                self.spin_obj_sz.blockSignals(True); self.spin_obj_sz.setValue(sz); self.spin_obj_sz.blockSignals(False)
            elif sender == self.spin_obj_sy and t.scale_y > 0:
                ratio = sy / t.scale_y
                sx = max(0.01, t.scale_x * ratio)
                sz = max(0.01, t.scale_z * ratio)
                self.spin_obj_sx.blockSignals(True); self.spin_obj_sx.setValue(sx); self.spin_obj_sx.blockSignals(False)
                self.spin_obj_sz.blockSignals(True); self.spin_obj_sz.setValue(sz); self.spin_obj_sz.blockSignals(False)
            elif sender == self.spin_obj_sz and t.scale_z > 0:
                ratio = sz / t.scale_z
                sx = max(0.01, t.scale_x * ratio)
                sy = max(0.01, t.scale_y * ratio)
                self.spin_obj_sx.blockSignals(True); self.spin_obj_sx.setValue(sx); self.spin_obj_sx.blockSignals(False)
                self.spin_obj_sy.blockSignals(True); self.spin_obj_sy.setValue(sy); self.spin_obj_sy.blockSignals(False)

        t.scale_x = sx; t.scale_y = sy; t.scale_z = sz
        if hasattr(self, 'gizmo_scale'):
            self.gizmo_scale.set_scale(sx, sy, sz)
        self.viewport.update()
        self._live_sync()

    def _reset_obj_scale(self):
        t = self.viewport.object_transform
        t.reset_scale()
        if hasattr(self, 'spin_obj_sx'):
            self.spin_obj_sx.blockSignals(True); self.spin_obj_sx.setValue(1.0); self.spin_obj_sx.blockSignals(False)
            self.spin_obj_sy.blockSignals(True); self.spin_obj_sy.setValue(1.0); self.spin_obj_sy.blockSignals(False)
            self.spin_obj_sz.blockSignals(True); self.spin_obj_sz.setValue(1.0); self.spin_obj_sz.blockSignals(False)
        if hasattr(self, 'gizmo_scale'):
            self.gizmo_scale.set_scale(1.0, 1.0, 1.0)
        self.viewport.update()
        self._live_sync()
        self._save_session()

    def _reset_obj_all(self):
        """Resets the object transform to identity so the object is cleanly centered at world origin (0,0,0)."""
        t = self.viewport.object_transform
        t.reset()
        if hasattr(self, 'spin_obj_px'):
            for spin, val in [
                (self.spin_obj_px, 0.0), (self.spin_obj_py, 0.0), (self.spin_obj_pz, 0.0),
                (self.spin_obj_rx, 0.0), (self.spin_obj_ry, 0.0), (self.spin_obj_rz, 0.0),
                (self.spin_obj_sx, 1.0), (self.spin_obj_sy, 1.0), (self.spin_obj_sz, 1.0)
            ]:
                spin.blockSignals(True)
                spin.setValue(val)
                spin.blockSignals(False)
        if hasattr(self, 'gizmo_pos'):
            self.gizmo_pos.set_position(0.0, 0.0, 0.0)
        if hasattr(self, 'gizmo_rot'):
            self.gizmo_rot.set_rotation(0.0, 0.0, 0.0)
        if hasattr(self, 'gizmo_scale'):
            self.gizmo_scale.set_scale(1.0, 1.0, 1.0)
        self.viewport.update()
        self._live_sync()

    def _sync_primitive_ui(self):
        if not hasattr(self, 'frame_primitive'):
            return
        ptype = getattr(self.mesh, 'primitive_type', None) if self.mesh else None
        if not ptype:
            self.frame_primitive.setVisible(False)
            return

        self.frame_primitive.setVisible(True)
        self.lbl_primitive_title.setText(f"📦 Primitive: {ptype}")

        self.combo_primitive_type.blockSignals(True)
        for i in range(self.combo_primitive_type.count()):
            if ptype.lower() in self.combo_primitive_type.itemText(i).lower():
                self.combo_primitive_type.setCurrentIndex(i)
                break
        self.combo_primitive_type.blockSignals(False)

        self.w_prim_box.setVisible(ptype == "Box")
        self.w_prim_cyl.setVisible(ptype == "Cylinder")
        self.w_prim_sph.setVisible(ptype == "Sphere")
        self.w_prim_pyr.setVisible(ptype == "Pyramid")
        self.w_prim_cone.setVisible(ptype == "Cone")
        self.w_prim_plane.setVisible(ptype == "Plane")

        params = getattr(self.mesh, 'primitive_params', {}) or {}
        if ptype == "Box":
            if "w" in params:
                self.spin_prim_box_w.blockSignals(True); self.spin_prim_box_w.setValue(params["w"]); self.spin_prim_box_w.blockSignals(False)
            if "h" in params:
                self.spin_prim_box_h.blockSignals(True); self.spin_prim_box_h.setValue(params["h"]); self.spin_prim_box_h.blockSignals(False)
            if "d" in params:
                self.spin_prim_box_d.blockSignals(True); self.spin_prim_box_d.setValue(params["d"]); self.spin_prim_box_d.blockSignals(False)
        elif ptype == "Cylinder":
            if "radius" in params:
                self.spin_prim_cyl_r.blockSignals(True); self.spin_prim_cyl_r.setValue(params["radius"]); self.spin_prim_cyl_r.blockSignals(False)
            if "height" in params:
                self.spin_prim_cyl_h.blockSignals(True); self.spin_prim_cyl_h.setValue(params["height"]); self.spin_prim_cyl_h.blockSignals(False)
            if "segments" in params:
                self.spin_prim_cyl_seg.blockSignals(True); self.spin_prim_cyl_seg.setValue(params["segments"]); self.spin_prim_cyl_seg.blockSignals(False)
        elif ptype == "Sphere":
            if "radius" in params:
                self.spin_prim_sph_r.blockSignals(True); self.spin_prim_sph_r.setValue(params["radius"]); self.spin_prim_sph_r.blockSignals(False)
            if "rings" in params:
                self.spin_prim_sph_rings.blockSignals(True); self.spin_prim_sph_rings.setValue(params["rings"]); self.spin_prim_sph_rings.blockSignals(False)
            if "sectors" in params:
                self.spin_prim_sph_sectors.blockSignals(True); self.spin_prim_sph_sectors.setValue(params["sectors"]); self.spin_prim_sph_sectors.blockSignals(False)
        elif ptype == "Pyramid":
            if "w" in params:
                self.spin_prim_pyr_w.blockSignals(True); self.spin_prim_pyr_w.setValue(params["w"]); self.spin_prim_pyr_w.blockSignals(False)
            if "h" in params:
                self.spin_prim_pyr_h.blockSignals(True); self.spin_prim_pyr_h.setValue(params["h"]); self.spin_prim_pyr_h.blockSignals(False)
            if "d" in params:
                self.spin_prim_pyr_d.blockSignals(True); self.spin_prim_pyr_d.setValue(params["d"]); self.spin_prim_pyr_d.blockSignals(False)
        elif ptype == "Cone":
            if "radius" in params:
                self.spin_prim_cone_r.blockSignals(True); self.spin_prim_cone_r.setValue(params["radius"]); self.spin_prim_cone_r.blockSignals(False)
            if "height" in params:
                self.spin_prim_cone_h.blockSignals(True); self.spin_prim_cone_h.setValue(params["height"]); self.spin_prim_cone_h.blockSignals(False)
            if "segments" in params:
                self.spin_prim_cone_seg.blockSignals(True); self.spin_prim_cone_seg.setValue(params["segments"]); self.spin_prim_cone_seg.blockSignals(False)
        elif ptype == "Plane":
            if "w" in params:
                self.spin_prim_plane_w.blockSignals(True); self.spin_prim_plane_w.setValue(params["w"]); self.spin_prim_plane_w.blockSignals(False)
            if "d" in params:
                self.spin_prim_plane_d.blockSignals(True); self.spin_prim_plane_d.setValue(params["d"]); self.spin_prim_plane_d.blockSignals(False)
            if "subdivisions" in params:
                self.spin_prim_plane_sub.blockSignals(True); self.spin_prim_plane_sub.setValue(params["subdivisions"]); self.spin_prim_plane_sub.blockSignals(False)

    def _create_primitive(self, ptype):
        self._reset_obj_all()
        if ptype == "Box":
            w = self.spin_prim_box_w.value() if hasattr(self, 'spin_prim_box_w') else 2.0
            h = self.spin_prim_box_h.value() if hasattr(self, 'spin_prim_box_h') else 2.0
            d = self.spin_prim_box_d.value() if hasattr(self, 'spin_prim_box_d') else 2.0
            new_mesh = create_box_primitive(w, h, d)
        elif ptype == "Cylinder":
            r = self.spin_prim_cyl_r.value() if hasattr(self, 'spin_prim_cyl_r') else 1.0
            h = self.spin_prim_cyl_h.value() if hasattr(self, 'spin_prim_cyl_h') else 2.0
            seg = self.spin_prim_cyl_seg.value() if hasattr(self, 'spin_prim_cyl_seg') else 24
            new_mesh = create_cylinder_primitive(r, h, seg)
        elif ptype == "Sphere":
            r = self.spin_prim_sph_r.value() if hasattr(self, 'spin_prim_sph_r') else 1.0
            rings = self.spin_prim_sph_rings.value() if hasattr(self, 'spin_prim_sph_rings') else 16
            sec = self.spin_prim_sph_sectors.value() if hasattr(self, 'spin_prim_sph_sectors') else 24
            new_mesh = create_sphere_primitive(r, rings, sec)
        elif ptype == "Pyramid":
            w = self.spin_prim_pyr_w.value() if hasattr(self, 'spin_prim_pyr_w') else 2.0
            h = self.spin_prim_pyr_h.value() if hasattr(self, 'spin_prim_pyr_h') else 2.0
            d = self.spin_prim_pyr_d.value() if hasattr(self, 'spin_prim_pyr_d') else 2.0
            new_mesh = create_pyramid_primitive(w, h, d)
        elif ptype == "Cone":
            r = self.spin_prim_cone_r.value() if hasattr(self, 'spin_prim_cone_r') else 1.0
            h = self.spin_prim_cone_h.value() if hasattr(self, 'spin_prim_cone_h') else 2.0
            seg = self.spin_prim_cone_seg.value() if hasattr(self, 'spin_prim_cone_seg') else 24
            new_mesh = create_cone_primitive(r, h, seg)
        elif ptype == "Plane":
            w = self.spin_prim_plane_w.value() if hasattr(self, 'spin_prim_plane_w') else 2.0
            d = self.spin_prim_plane_d.value() if hasattr(self, 'spin_prim_plane_d') else 2.0
            sub = self.spin_prim_plane_sub.value() if hasattr(self, 'spin_prim_plane_sub') else 2
            new_mesh = create_plane_primitive(w, d, sub)
        else:
            return

        self.mesh = new_mesh
        self.mesh_path = None
        self.viewport.set_mesh(new_mesh)
        self._sync_primitive_ui()
        self.lbl_model.setText(f"Primitive: {ptype}\n{len(new_mesh.vertices)} verts, {len(new_mesh.faces)} faces")
        self.lbl_status.setText(f"Created {ptype}")
        self.viewport.update()
        self._live_sync()
        self._save_session()

    def _on_primitive_type_selected(self, text):
        clean_name = text.replace("📦", "").replace("🛢️", "").replace("🔮", "").replace("📐", "").replace("🍦", "").replace("🏁", "").strip()
        self._create_primitive(clean_name)

    def _on_primitive_param_changed(self):
        if not self.mesh or not getattr(self.mesh, 'primitive_type', None):
            return
        ptype = self.mesh.primitive_type
        if ptype == "Box":
            w = self.spin_prim_box_w.value()
            h = self.spin_prim_box_h.value()
            d = self.spin_prim_box_d.value()
            new_mesh = create_box_primitive(w, h, d)
        elif ptype == "Cylinder":
            r = self.spin_prim_cyl_r.value()
            h = self.spin_prim_cyl_h.value()
            seg = self.spin_prim_cyl_seg.value()
            new_mesh = create_cylinder_primitive(r, h, seg)
        elif ptype == "Sphere":
            r = self.spin_prim_sph_r.value()
            rings = self.spin_prim_sph_rings.value()
            sec = self.spin_prim_sph_sectors.value()
            new_mesh = create_sphere_primitive(r, rings, sec)
        elif ptype == "Pyramid":
            w = self.spin_prim_pyr_w.value()
            h = self.spin_prim_pyr_h.value()
            d = self.spin_prim_pyr_d.value()
            new_mesh = create_pyramid_primitive(w, h, d)
        elif ptype == "Cone":
            r = self.spin_prim_cone_r.value()
            h = self.spin_prim_cone_h.value()
            seg = self.spin_prim_cone_seg.value()
            new_mesh = create_cone_primitive(r, h, seg)
        elif ptype == "Plane":
            w = self.spin_prim_plane_w.value()
            d = self.spin_prim_plane_d.value()
            sub = self.spin_prim_plane_sub.value()
            new_mesh = create_plane_primitive(w, d, sub)
        else:
            return

        self.mesh = new_mesh
        self.viewport.set_mesh(new_mesh)
        self.lbl_model.setText(f"Primitive: {ptype}\n{len(new_mesh.vertices)} verts, {len(new_mesh.faces)} faces")
        self.viewport.update()
        self._live_sync()
        self._schedule_save()

    def _select_no_object_only_grid(self):
        self.mesh = None
        self.mesh_path = None
        self.viewport.set_mesh(None)
        self.lbl_model.setText("No object (Grid only)")
        self.lbl_status.setText("Grid-only mode active")
        # Activate drawing grid if not already activated
        if hasattr(self, 'chk_grid_canvas') and not self.chk_grid_canvas.isChecked():
            self.chk_grid_canvas.setChecked(True)
        if hasattr(self, 'chk_grid_viewport') and not self.chk_grid_viewport.isChecked():
            self.chk_grid_viewport.setChecked(True)
        if hasattr(self, 'chk_grid_ground') and not self.chk_grid_ground.isChecked():
            self.chk_grid_ground.setChecked(True)
        self._on_grid_changed()
        self.viewport.update()
        self._live_sync()
        self._save_session()

    def _import(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Import 3D Model", "",
            "3D Files (*.obj *.stl *.glb *.gltf);;OBJ (*.obj);;STL (*.stl);;GLB/glTF (*.glb *.gltf);;All Files (*)"
        )
        if path:
            self._load_file(path)

    def _load_file(self, path, frame=True):
        try:
            self._reset_obj_all()
            m = load_3d_file(path)
            self.mesh = m
            self.mesh_path = path

            fn_lower = os.path.basename(path).lower()
            if "box" in fn_lower or "cube" in fn_lower:
                m.primitive_type = "Box"
                m.primitive_params = {"w": 2.0, "h": 2.0, "d": 2.0}
            elif "cylinder" in fn_lower:
                m.primitive_type = "Cylinder"
                m.primitive_params = {"radius": 1.0, "height": 2.0, "segments": 24}
            elif "sphere" in fn_lower:
                m.primitive_type = "Sphere"
                m.primitive_params = {"radius": 1.0, "rings": 16, "sectors": 24}
            elif "pyramid" in fn_lower:
                m.primitive_type = "Pyramid"
                m.primitive_params = {"w": 2.0, "h": 2.0, "d": 2.0}
            elif "cone" in fn_lower:
                m.primitive_type = "Cone"
                m.primitive_params = {"radius": 1.0, "height": 2.0, "segments": 24}
            elif "plane" in fn_lower or "grid" in fn_lower:
                m.primitive_type = "Plane"
                m.primitive_params = {"w": 2.0, "d": 2.0, "subdivisions": 2}
            else:
                m.primitive_type = None
                m.primitive_params = {}

            self.viewport.set_mesh(m)
            self._sync_primitive_ui()
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

    def _sync_dolly_checks(self, state, source=None):
        is_checked = (state == Qt.Checked or state is True or state == 2)
        for chk in [getattr(self, 'chk_dolly_zoom', None), getattr(self, 'chk_fish_dolly', None)]:
            if chk is not None and chk is not source:
                chk.blockSignals(True)
                chk.setChecked(is_checked)
                chk.blockSignals(False)

    def _lens_cb(self, fov):
        def handler():
            new_fov = float(fov)
            old_fov = self.viewport.camera.fov
            is_locked = bool(getattr(self, "chk_dolly_zoom", None) and self.chk_dolly_zoom.isChecked()) or \
                        bool(getattr(self, "chk_fish_dolly", None) and self.chk_fish_dolly.isChecked())
            if is_locked and old_fov > 1.0 and new_fov > 1.0:
                tan_old = math.tan(math.radians(old_fov * 0.5))
                tan_new = math.tan(math.radians(new_fov * 0.5))
                if tan_new > 1e-4:
                    new_dist = self.viewport.camera.distance * (tan_old / tan_new)
                    new_dist = max(0.05, min(100.0, new_dist))
                    self.viewport.camera.distance = new_dist
                    if hasattr(self, 'sl_dist'):
                        self.sl_dist.blockSignals(True)
                        self.sl_dist.setValue(int(min(self.sl_dist.maximum(), max(self.sl_dist.minimum(), round(new_dist * 10)))))
                        self.sl_dist.blockSignals(False)
                    if hasattr(self, 'lbl_dist'):
                        self.lbl_dist.setText(f"Dist {new_dist:.1f}")
            self.viewport.camera.fov = new_fov
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
        is_fisheye       = (text == ProjectionMode.FISHEYE)
        is_artist_5vp    = (text == ProjectionMode.ARTIST_5VP)
        is_artist_linear = (text == ProjectionMode.ARTIST_LINEAR)
        is_curv_other    = (text in (ProjectionMode.ARTIST_5VP, ProjectionMode.CYLINDRICAL))
        if hasattr(self, 'w_fisheye_group'):
            self.w_fisheye_group.setVisible(is_fisheye)
        if hasattr(self, 'lbl_curv'):
            if is_artist_linear:
                self.lbl_curv.setText(f"Artist Natural Angle: {int(self.viewport.camera.curvature * 100)}%")
                self.lbl_curv.setVisible(True)
            elif is_curv_other:
                self.lbl_curv.setText(f"Curvature {int(self.viewport.camera.curvature * 100)}%")
                self.lbl_curv.setVisible(True)
            else:
                self.lbl_curv.setVisible(False)
        if hasattr(self, 'sl_curv'):
            self.sl_curv.setVisible(is_curv_other or is_artist_linear)
        if hasattr(self, 'sl_fov'):
            self.sl_fov.setEnabled(text != ProjectionMode.ORTHOGRAPHIC)
        # Also sync camera state immediately
        self.viewport.camera.projection_mode = text
        self.viewport.camera.orthographic = (text == ProjectionMode.ORTHOGRAPHIC)

    def _get_center_scale(self, mode):
        """Calculates center projection scale to preserve 3D object size when switching projection modes."""
        c = self.viewport.camera
        if mode in (ProjectionMode.PERSPECTIVE, ProjectionMode.ARTIST_LINEAR):
            return 1.0 / max(1e-4, math.tan(math.radians(max(5.0, c.fov) * 0.5)))
        elif mode == ProjectionMode.FISHEYE:
            eff_fov = min(250.0, max(40.0, getattr(c, 'fisheye_fov', 180.0)))
            th = math.radians(eff_fov * 0.5)
            lt = getattr(c, 'fisheye_lens_type', 'Equidistant')
            if lt == "Stereographic":
                g = max(1e-4, 2.0 * math.tan(th * 0.5))
            elif lt == "Equisolid":
                g = max(1e-4, 2.0 * math.sin(th * 0.5))
            elif lt == "Orthographic":
                g = max(1e-4, math.sin(th))
            else:
                g = max(1e-4, th)
            curv = max(0.1, min(4.0, getattr(c, 'curvature', 1.0)))
            bk = curv * 1.6
            barrel_slope = (bk / math.atan(bk)) if bk > 1e-4 else 1.0
            return (barrel_slope / g) * getattr(c, 'fisheye_zoom', 1.0)
        elif mode == ProjectionMode.CYLINDRICAL:
            curv = max(0.1, min(3.0, getattr(c, 'curvature', 0.65)))
            return 1.0 / max(1e-4, math.tan(math.radians(max(5.0, c.fov) * 0.5)) * curv)
        elif mode == ProjectionMode.ARTIST_5VP:
            curv = max(0.5, min(4.0, getattr(c, 'curvature', 1.5)))
            bk = curv * 2.0
            barrel_slope = (bk / math.atan(bk)) if bk > 1e-4 else 1.0
            return (barrel_slope / (math.pi * 0.5)) * getattr(c, 'fisheye_zoom', 1.0)
        elif mode == ProjectionMode.ORTHOGRAPHIC:
            return 1.0 / max(0.01, c.distance * 0.5)
        return 1.0

    def _on_proj_mode(self, text):
        old_mode = self.viewport.camera.projection_mode
        new_mode = text
        is_locked = bool(getattr(self, "chk_dolly_zoom", None) and self.chk_dolly_zoom.isChecked()) or \
                    bool(getattr(self, "chk_fish_dolly", None) and self.chk_fish_dolly.isChecked())
        if is_locked and old_mode != new_mode and old_mode != ProjectionMode.ORTHOGRAPHIC and new_mode != ProjectionMode.ORTHOGRAPHIC:
            s_old = self._get_center_scale(old_mode)
            s_new = self._get_center_scale(new_mode)
            if s_old > 1e-6 and s_new > 1e-6:
                new_dist = self.viewport.camera.distance * (s_new / s_old)
                new_dist = max(0.05, min(100.0, new_dist))
                self.viewport.camera.distance = new_dist
                if hasattr(self, 'sl_dist'):
                    self.sl_dist.blockSignals(True)
                    self.sl_dist.setValue(int(min(self.sl_dist.maximum(), max(self.sl_dist.minimum(), round(new_dist * 10)))))
                    self.sl_dist.blockSignals(False)
                if hasattr(self, 'lbl_dist'):
                    self.lbl_dist.setText(f"Dist {new_dist:.1f}")

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
        if "fade_grid" in p or "grid_fade" in p:
            gs.fade_grid = bool(p.get("grid_fade", p.get("fade_grid", True)))
            if hasattr(self, 'chk_fade_grid'):
                self.chk_fade_grid.blockSignals(True); self.chk_fade_grid.setChecked(gs.fade_grid); self.chk_fade_grid.blockSignals(False)
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
            "grid_fade": getattr(gs, 'fade_grid', True),
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
        if getattr(self.viewport.camera, 'projection_mode', '') == ProjectionMode.ARTIST_LINEAR:
            self.lbl_curv.setText(f"Artist Natural Angle: {int(v)}%")
        else:
            self.lbl_curv.setText(f"Curvature {int(v)}%")
        self.viewport.update()
        self._live_sync()

    def _on_fish_lens_changed(self, text):
        """Change fisheye mathematical formula / lens type."""
        new_lens = text.split()[0]
        old_lens = getattr(self.viewport.camera, 'fisheye_lens_type', 'Equidistant')
        fov = getattr(self.viewport.camera, 'fisheye_fov', 180.0)
        is_locked = bool(getattr(self, "chk_dolly_zoom", None) and self.chk_dolly_zoom.isChecked()) or \
                    bool(getattr(self, "chk_fish_dolly", None) and self.chk_fish_dolly.isChecked())
        if is_locked and old_lens != new_lens:
            def get_g(lt):
                th = math.radians(fov * 0.5)
                if lt == "Stereographic":
                    return max(1e-4, 2.0 * math.tan(th * 0.5))
                elif lt == "Equisolid":
                    return max(1e-4, 2.0 * math.sin(th * 0.5))
                elif lt == "Orthographic":
                    return max(1e-4, math.sin(th))
                else:
                    return max(1e-4, th)
            g_old = get_g(old_lens)
            g_new = get_g(new_lens)
            if g_new > 1e-6:
                new_dist = self.viewport.camera.distance * (g_old / g_new)
                new_dist = max(0.05, min(100.0, new_dist))
                self.viewport.camera.distance = new_dist
                if hasattr(self, 'sl_dist'):
                    self.sl_dist.blockSignals(True)
                    self.sl_dist.setValue(int(min(self.sl_dist.maximum(), max(self.sl_dist.minimum(), round(new_dist * 10)))))
                    self.sl_dist.blockSignals(False)
                if hasattr(self, 'lbl_dist'):
                    self.lbl_dist.setText(f"Dist {new_dist:.1f}")

        self.viewport.camera.fisheye_lens_type = new_lens
        self.viewport.update()
        self._live_sync()

    def _on_fish_fov(self, v):
        """Fisheye angle of view in degrees."""
        new_fov = float(v)
        old_fov = getattr(self.viewport.camera, 'fisheye_fov', 180.0)
        is_locked = bool(getattr(self, "chk_dolly_zoom", None) and self.chk_dolly_zoom.isChecked()) or \
                    bool(getattr(self, "chk_fish_dolly", None) and self.chk_fish_dolly.isChecked())
        if is_locked and old_fov > 10.0 and new_fov > 10.0 and abs(new_fov - old_fov) > 0.01:
            lens_type = getattr(self.viewport.camera, 'fisheye_lens_type', 'Equidistant')
            def get_g(f_deg):
                th = math.radians(f_deg * 0.5)
                if lens_type == "Stereographic":
                    return max(1e-4, 2.0 * math.tan(th * 0.5))
                elif lens_type == "Equisolid":
                    return max(1e-4, 2.0 * math.sin(th * 0.5))
                elif lens_type == "Orthographic":
                    return max(1e-4, math.sin(th))
                else:  # Equidistant
                    return max(1e-4, th)

            g_old = get_g(old_fov)
            g_new = get_g(new_fov)
            if g_new > 1e-6:
                new_dist = self.viewport.camera.distance * (g_old / g_new)
                new_dist = max(0.05, min(100.0, new_dist))
                self.viewport.camera.distance = new_dist
                if hasattr(self, 'sl_dist'):
                    self.sl_dist.blockSignals(True)
                    self.sl_dist.setValue(int(min(self.sl_dist.maximum(), max(self.sl_dist.minimum(), round(new_dist * 10)))))
                    self.sl_dist.blockSignals(False)
                if hasattr(self, 'lbl_dist'):
                    self.lbl_dist.setText(f"Dist {new_dist:.1f}")

        self.viewport.camera.fisheye_fov = new_fov
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
        new_fov = float(v)
        old_fov = self.viewport.camera.fov
        is_locked = bool(getattr(self, "chk_dolly_zoom", None) and self.chk_dolly_zoom.isChecked()) or \
                    bool(getattr(self, "chk_fish_dolly", None) and self.chk_fish_dolly.isChecked())
        if is_locked:
            if old_fov > 1.0 and new_fov > 1.0:
                tan_old = math.tan(math.radians(old_fov * 0.5))
                tan_new = math.tan(math.radians(new_fov * 0.5))
                if tan_new > 1e-4:
                    new_dist = self.viewport.camera.distance * (tan_old / tan_new)
                    new_dist = max(0.05, min(100.0, new_dist))
                    self.viewport.camera.distance = new_dist
                    if hasattr(self, 'sl_dist'):
                        self.sl_dist.blockSignals(True)
                        self.sl_dist.setValue(int(min(self.sl_dist.maximum(), max(self.sl_dist.minimum(), round(new_dist * 10)))))
                        self.sl_dist.blockSignals(False)
                    if hasattr(self, 'lbl_dist'):
                        self.lbl_dist.setText(f"Dist {new_dist:.1f}")
        self.viewport.camera.fov = new_fov
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
        if hasattr(self, 'chk_horizon_level'):
            gs.horizon_always_horizontal = self.chk_horizon_level.isChecked()
        gs.ground_enabled = self.chk_grid_ground.isChecked()
        gs.ceiling_enabled = self.chk_grid_ceiling.isChecked()
        gs.ceiling_height = self.spin_grid_cheight.value()
        gs.grid_extent = self.spin_grid_extent.value()
        gs.tile_size = self.spin_grid_tile.value()
        gs.subdivisions = self.spin_grid_subdiv.value()
        gs.exceed_lines = self.chk_grid_exceed.isChecked()
        if hasattr(self, 'chk_fade_grid'):
            gs.fade_grid = self.chk_fade_grid.isChecked()
        gs.vertical_lines = self.chk_grid_verticals.isChecked()
        gs.axis_colors = self.chk_grid_axis.isChecked()
        self.viewport.update()
        self._live_sync()
        self._schedule_save()

    # -----------------------------------------------------------------
    # Ground Perspective Calibrator Dialog
    # -----------------------------------------------------------------
    def drawRectangleGround(self, initial_mode=None, *args):
        """Public alias for Ground Rectangle Calibrator."""
        return self._open_ground_calibrator(initial_mode, *args)

    def _open_ground_calibrator(self, initial_mode=None, *args):
        # Sanitize initial_mode against PyQt event arguments (like boolean False)
        if not isinstance(initial_mode, (int, str)):
            initial_mode = None

        snapshot = CanvasSyncManager.get_canvas_snapshot()
        active_frame = self.frame_rect if (self.chk_use_frame.isChecked() and self.frame_rect) else None
        dlg = GroundCalibratorDialog(
            bg_image=snapshot,
            mesh=self.mesh,
            camera=self.viewport.camera,
            lighting=self.viewport.lighting,
            renderer=self.viewport.renderer,
            frame_rect=active_frame,
            start_in_click_draw=(initial_mode in ("draw", "drag")),
            initial_mode=initial_mode,
            parent=self
        )
        if initial_mode == 4:
            if hasattr(dlg, '_start_4point_pick'):
                dlg._start_4point_pick()
            elif hasattr(dlg, 'calibrator_widget') and hasattr(dlg.calibrator_widget, 'start_pick_mode'):
                dlg.calibrator_widget.start_pick_mode(4)
        elif initial_mode == 5:
            if hasattr(dlg, '_start_5point_pick'):
                dlg._start_5point_pick()
            elif hasattr(dlg, 'calibrator_widget') and hasattr(dlg.calibrator_widget, 'start_pick_mode'):
                dlg.calibrator_widget.start_pick_mode(5)
        elif initial_mode in ("draw", "drag"):
            if hasattr(dlg, 'start_drag_mode'):
                dlg.start_drag_mode()
            elif hasattr(dlg, 'calibrator_widget') and hasattr(dlg.calibrator_widget, 'start_drag_mode'):
                dlg.calibrator_widget.start_drag_mode()

        sel = CanvasSyncManager.get_active_selection_rect()
        doc_info = CanvasSyncManager.get_document_info()
        if sel and doc_info and initial_mode is None:
            dlg.calibrator_widget.set_from_rect(
                sel[0], sel[1], sel[2], sel[3],
                doc_info["width"], doc_info["height"]
            )
        dlg.applied.connect(self._on_ground_calibrator_applied)
        dlg.exec_()

    def _on_ground_calibrator_applied(self, sol):
        # 1. Reset object transform so model sits cleanly centered and resting on the ground quad
        self._reset_obj_all()

        # 2. Set generated 3D primitive mesh or scale existing 3D Object
        ptype = sol.get("primitive_type") or (getattr(self.mesh, 'primitive_type', None) if self.mesh else None)
        rw = float(sol.get("rect_width", 2.0))
        rd = float(sol.get("rect_depth", 2.0))
        rh = float(sol.get("rect_height", 2.0))
        sr = float(sol.get("sphere_radius", 1.0))

        if "mesh" in sol and sol["mesh"]:
            self.mesh = sol["mesh"]
            self.mesh_path = None
            self.mesh.primitive_type = ptype
            if ptype == "Box":
                self.mesh.primitive_params = {"w": rw, "h": rh, "d": rd}
            elif ptype == "Cylinder":
                self.mesh.primitive_params = {"radius": rw * 0.5, "height": rh, "segments": 24}
            elif ptype == "Sphere":
                self.mesh.primitive_params = {"radius": sr, "rings": 16, "sectors": 24}
            elif ptype == "Pyramid":
                self.mesh.primitive_params = {"w": rw, "h": rh, "d": rd}
            elif ptype == "Cone":
                self.mesh.primitive_params = {"radius": rw * 0.5, "height": rh, "segments": 24}
            elif ptype == "Plane":
                self.mesh.primitive_params = {"w": rw, "d": rd, "subdivisions": 2}
            self.viewport.set_mesh(self.mesh)
            self._sync_primitive_ui()
            self.lbl_model.setText(f"3D Primitive: {ptype} ({self.mesh.vertex_count} vertices, {self.mesh.face_count} faces)")
        elif self.mesh and ("scale_x" in sol):
            sx = float(sol.get("scale_x", 1.0))
            sy = float(sol.get("scale_y", 1.0))
            sz = float(sol.get("scale_z", 1.0))
            if hasattr(self, 'spin_obj_sx'): self.spin_obj_sx.setValue(sx)
            if hasattr(self, 'spin_obj_sz'): self.spin_obj_sz.setValue(sz)
            if hasattr(self, 'spin_obj_sy'): self.spin_obj_sy.setValue(sy)

        # 3. Reset projection mode to standard linear perspective to match calibration
        c = self.viewport.camera
        c.projection_mode = ProjectionMode.PERSPECTIVE
        c.orthographic = False
        if hasattr(self, 'combo_proj'):
            self.combo_proj.blockSignals(True)
            self.combo_proj.setCurrentText(ProjectionMode.PERSPECTIVE)
            self.combo_proj.blockSignals(False)
        self._update_proj_controls_visibility(ProjectionMode.PERSPECTIVE)

        # 4. Apply calibrated camera parameters
        c.yaw = float(sol.get("yaw", c.yaw)) % 360.0
        c.pitch = max(-85.0, min(85.0, float(sol.get("pitch", c.pitch))))
        c.roll = float(sol.get("roll", 0.0))
        c.tilt = 0.0
        c.fov = float(sol.get("fov", c.fov))
        c.distance = float(sol.get("distance", c.distance))
        c.pan_x = float(sol.get("pan_x", 0.0))
        c.pan_y = float(sol.get("pan_y", 0.0))
        if "target_x" in sol:
            c.target_x = float(sol["target_x"])
            c.target_y = float(sol["target_y"])
            c.target_z = float(sol["target_z"])
        c.ground_y = float(sol.get("target_y", 0.0))
        if ptype == "Sphere":
            c.target_y = float(sol.get("target_y", 0.0)) + sr

        self._sync_ui()
        self._sync_target_spins()
        self.viewport.update()
        self._stamp()
        self.lbl_status.setText(f"Perspective calibrated: Tilt {c.pitch:.1f}° Yaw {c.yaw:.1f}° Roll {c.roll:.1f}° (Placed on ground)")
        self._save_session()

    # -----------------------------------------------------------------
    # Unified Primitive Drawer / Ground Calibrator Dialog
    # -----------------------------------------------------------------
    def _open_primitive_drawer(self, start_click_draw=False):
        snapshot = CanvasSyncManager.get_canvas_snapshot()
        active_frame = self.frame_rect if (self.chk_use_frame.isChecked() and self.frame_rect) else None
        dlg = GroundCalibratorDialog(
            bg_image=snapshot,
            mesh=self.mesh,
            camera=self.viewport.camera,
            lighting=self.viewport.lighting,
            renderer=self.viewport.renderer,
            frame_rect=active_frame,
            start_in_click_draw=start_click_draw,
            parent=self
        )
        dlg.applied.connect(self._on_ground_calibrator_applied)
        dlg.exec_()

    def _on_primitive_drawer_applied(self, sol):
        # 0. Ensure full canvas is used and reset any custom frame rect
        self.chk_use_frame.setChecked(False)
        self.frame_rect = None
        self.viewport.set_scene_frame(None, "")
        self._match_ratio()

        # 1. Set generated 3D primitive mesh
        if "mesh" in sol and sol["mesh"]:
            self._reset_obj_all()
            self.mesh = sol["mesh"]
            self.mesh_path = None
            ptype = sol.get("primitive_type", "Box")
            self.mesh.primitive_type = ptype
            if ptype == "Box":
                self.mesh.primitive_params = {"w": sol.get("box_w", 2.0), "h": sol.get("box_h", 2.0), "d": sol.get("box_d", 2.0)}
            elif ptype == "Cylinder":
                self.mesh.primitive_params = {"radius": sol.get("box_w", 2.0) * 0.5, "height": sol.get("box_h", 2.0), "segments": 24}
            elif ptype == "Sphere":
                self.mesh.primitive_params = {"radius": sol.get("box_w", 2.0) * 0.5, "rings": 16, "sectors": 24}
            elif ptype == "Pyramid":
                self.mesh.primitive_params = {"w": sol.get("box_w", 2.0), "h": sol.get("box_h", 2.0), "d": sol.get("box_d", 2.0)}
            elif ptype == "Cone":
                self.mesh.primitive_params = {"radius": sol.get("box_w", 2.0) * 0.5, "height": sol.get("box_h", 2.0), "segments": 24}
            elif ptype == "Plane":
                self.mesh.primitive_params = {"w": sol.get("box_w", 2.0), "d": sol.get("box_d", 2.0), "subdivisions": 2}
            self.viewport.set_mesh(self.mesh)
            self._sync_primitive_ui()
            self.lbl_model.setText(f"Drawn Primitive: {ptype} ({self.mesh.vertex_count} vertices, {self.mesh.face_count} faces)")

        # 2. Reset camera projection mode to standard linear perspective to match calibration
        c = self.viewport.camera
        c.projection_mode = ProjectionMode.PERSPECTIVE
        c.orthographic = False
        if hasattr(self, 'combo_proj'):
            self.combo_proj.blockSignals(True)
            self.combo_proj.setCurrentText(ProjectionMode.PERSPECTIVE)
            self.combo_proj.blockSignals(False)
        self._update_proj_controls_visibility(ProjectionMode.PERSPECTIVE)

        # 3. Set calibrated camera parameters
        c.yaw = float(sol.get("yaw", c.yaw)) % 360.0
        c.pitch = max(-85.0, min(85.0, float(sol.get("pitch", c.pitch))))
        c.roll = float(sol.get("roll", 0.0))
        c.tilt = 0.0
        c.fov = float(sol.get("fov", c.fov))
        c.distance = float(sol.get("distance", c.distance))
        c.pan_x = float(sol.get("pan_x", 0.0))
        c.pan_y = float(sol.get("pan_y", 0.0))
        c.target_x = float(sol.get("target_x", 0.0))
        c.target_y = float(sol.get("target_y", 0.0))
        c.target_z = float(sol.get("target_z", 0.0))

        self._sync_ui()
        self._sync_target_spins()
        self.viewport.update()

        # 4. Stamp immediately and synchronously so canvas layer matches calibration dialog with 100% fidelity
        self._stamp()

        ptype = sol.get("primitive_type", "Box")
        persp = sol.get("persp_type", "2-Point")
        self.lbl_status.setText(f"3D {ptype} created! ({persp} | FOV {c.fov:.1f}° | Tilt {c.pitch:+.1f}° | Yaw {c.yaw:.1f}°)")
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
        if hasattr(self, 'chk_vp_sticky'):
            self.chk_vp_sticky.blockSignals(True)
            self.chk_vp_sticky.setChecked(self.is_sticky_viewport)
            self.chk_vp_sticky.blockSignals(False)

        if self.is_sticky_viewport:
            # Pinned above scroll area
            if hasattr(self, '_top_viewport_container') and self._top_viewport_container.parent() != self._root_container:
                self._controls_layout.removeWidget(self._top_viewport_container)
                self._outer_layout.insertWidget(0, self._top_viewport_container)
        else:
            # Scrollable inside controls
            if hasattr(self, '_top_viewport_container') and self._top_viewport_container.parent() == self._root_container:
                self._outer_layout.removeWidget(self._top_viewport_container)
                self._controls_layout.insertWidget(0, self._top_viewport_container)

    def _on_toggle_sticky_viewport(self, state):
        """Toggle sticky viewport: pins the viewport above the scroll area."""
        self._apply_sticky_viewport(state == Qt.Checked)
        self._save_session()

    def _on_toggle_vp_top_labels(self, state):
        self.viewport.show_top_labels = (state == Qt.Checked)
        self.viewport.update()
        self._schedule_save()

    def _on_toggle_vp_orbit_button(self, state):
        self.viewport.show_orbit_button = (state == Qt.Checked)
        if hasattr(self.viewport, '_layout_bottom_controls'):
            self.viewport._layout_bottom_controls()
        self.viewport.update()
        self._schedule_save()

    def _on_toggle_quick_toolbar(self, state):
        show = (state == Qt.Checked or state is True or state == 2)
        if hasattr(self, 'quick_toolbar'):
            self.quick_toolbar.setVisible(show)
        self._schedule_save()

    def _on_toggle_vp_gradient(self, state):
        self.viewport.bg_use_gradient = (state == Qt.Checked)
        if hasattr(self, 'btn_vp_bg_bot'):
            self.btn_vp_bg_bot.setEnabled(self.viewport.bg_use_gradient)
        self.viewport.update()
        self._schedule_save()

    def _pick_vp_bg_top_color(self):
        c = QColorDialog.getColor(self.viewport.bg_color_top, self, "Select Viewport Top/Solid Background Color")
        if c.isValid():
            self.viewport.bg_color_top = c
            self._update_vp_bg_buttons()
            self.viewport.update()
            self._schedule_save()

    def _pick_vp_bg_bottom_color(self):
        c = QColorDialog.getColor(self.viewport.bg_color_bottom, self, "Select Viewport Bottom Gradient Color")
        if c.isValid():
            self.viewport.bg_color_bottom = c
            self._update_vp_bg_buttons()
            self.viewport.update()
            self._schedule_save()

    def _set_vp_theme(self, top_col, bot_col, use_gradient):
        self.viewport.bg_color_top = top_col
        self.viewport.bg_color_bottom = bot_col
        self.viewport.bg_use_gradient = use_gradient
        if hasattr(self, 'chk_vp_bg_gradient'):
            self.chk_vp_bg_gradient.blockSignals(True)
            self.chk_vp_bg_gradient.setChecked(use_gradient)
            self.chk_vp_bg_gradient.blockSignals(False)
        self._update_vp_bg_buttons()
        self.viewport.update()
        self._schedule_save()

    def _update_vp_bg_buttons(self):
        if hasattr(self, 'btn_vp_bg_top'):
            hex_top = self.viewport.bg_color_top.name()
            self.btn_vp_bg_top.setStyleSheet(f"background: {hex_top}; color: #ffffff; border: 1px solid #ffffff; font-weight: bold;")
        if hasattr(self, 'btn_vp_bg_bot'):
            hex_bot = self.viewport.bg_color_bottom.name()
            self.btn_vp_bg_bot.setStyleSheet(f"background: {hex_bot}; color: #ffffff; border: 1px solid #ffffff; font-weight: bold;")
            self.btn_vp_bg_bot.setEnabled(getattr(self.viewport, 'bg_use_gradient', True))

    def _on_vp_height_spin(self):
        if hasattr(self, 'spin_vp_height'):
            h = self.spin_vp_height.value()
            self.viewport.setFixedHeight(h)
            self._schedule_save()

    def _reset_vp_height(self):
        self.viewport.setFixedHeight(170)
        if hasattr(self, 'spin_vp_height'):
            self.spin_vp_height.blockSignals(True)
            self.spin_vp_height.setValue(170)
            self.spin_vp_height.blockSignals(False)
        self._schedule_save()

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
    def _ensure_layer_visible(self):
        try:
            CanvasSyncManager.ensure_layer_visible(layer_mode="named", layer_name="3D Perspective & Model")
        except Exception:
            pass

    def _live_sync(self, *_):
        self._ensure_layer_visible()
        if self.chk_live.isChecked():
            self.live_sync_timer.start(self.debounce_ms)

    def _do_live_sync(self):
        if self.chk_live.isChecked():
            self._stamp()

    def _on_camera_changed(self):
        self._sync_ui()
        self._live_sync()

    def _on_interaction_ended(self):
        self._ensure_layer_visible()
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
                draw_model=has_mesh,
                object_transform=self.viewport.object_transform
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

        # Object Transform & Primitive
        t = getattr(self.viewport, 'object_transform', None)
        if t:
            if hasattr(self, 'spin_obj_px'):
                self.spin_obj_px.blockSignals(True); self.spin_obj_px.setValue(t.pos_x); self.spin_obj_px.blockSignals(False)
                self.spin_obj_py.blockSignals(True); self.spin_obj_py.setValue(t.pos_y); self.spin_obj_py.blockSignals(False)
                self.spin_obj_pz.blockSignals(True); self.spin_obj_pz.setValue(t.pos_z); self.spin_obj_pz.blockSignals(False)
            if hasattr(self, 'gizmo_pos'):
                self.gizmo_pos.set_position(t.pos_x, t.pos_y, t.pos_z)

            if hasattr(self, 'spin_obj_rx'):
                self.spin_obj_rx.blockSignals(True); self.spin_obj_rx.setValue(t.rot_x); self.spin_obj_rx.blockSignals(False)
                self.spin_obj_ry.blockSignals(True); self.spin_obj_ry.setValue(t.rot_y); self.spin_obj_ry.blockSignals(False)
                self.spin_obj_rz.blockSignals(True); self.spin_obj_rz.setValue(t.rot_z); self.spin_obj_rz.blockSignals(False)
            if hasattr(self, 'gizmo_rot'):
                self.gizmo_rot.set_rotation(t.rot_x, t.rot_y, t.rot_z)

            if hasattr(self, 'spin_obj_sx'):
                self.spin_obj_sx.blockSignals(True); self.spin_obj_sx.setValue(t.scale_x); self.spin_obj_sx.blockSignals(False)
                self.spin_obj_sy.blockSignals(True); self.spin_obj_sy.setValue(t.scale_y); self.spin_obj_sy.blockSignals(False)
                self.spin_obj_sz.blockSignals(True); self.spin_obj_sz.setValue(t.scale_z); self.spin_obj_sz.blockSignals(False)
            if hasattr(self, 'gizmo_scale'):
                self.gizmo_scale.set_scale(t.scale_x, t.scale_y, t.scale_z)

        self._sync_primitive_ui()
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
            self._restore_session()
            self._match_ratio()
            if hasattr(self, "is_sticky_viewport"):
                self._apply_sticky_viewport(self.is_sticky_viewport)
            self._sync_ui()
            self.viewport.update()
            if hasattr(self, 'chk_live') and self.chk_live.isChecked():
                self._live_sync()
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
            # Viewport Display & Styling
            "viewport_height":      self.viewport.height(),
            "sticky_viewport":      self.is_sticky_viewport,
            "show_overlay_buttons": bool(self.viewport.show_overlay_buttons),
            "show_gizmo":           bool(self.viewport.show_gizmo),
            "show_frame_guide":     bool(self.viewport.show_canvas_frame),
            "show_top_labels":      bool(getattr(self.viewport, 'show_top_labels', True)),
            "show_orbit_button":    bool(getattr(self.viewport, 'show_orbit_button', True)),
            "show_quick_toolbar":   bool(self.quick_toolbar.isVisible() if hasattr(self, 'quick_toolbar') else True),
            "bg_use_gradient":      bool(getattr(self.viewport, 'bg_use_gradient', True)),
            "bg_color_top":         self.viewport.bg_color_top.name() if hasattr(self.viewport, 'bg_color_top') else "#323844",
            "bg_color_bottom":      self.viewport.bg_color_bottom.name() if hasattr(self.viewport, 'bg_color_bottom') else "#181b22",
            "quick_toolbar_items":  self.quick_toolbar.get_items() if hasattr(self, 'quick_toolbar') else [],

            # Camera Navigation & Transform
            "nav_camera_mode":      self.viewport.camera_mode,
            "nav_orbit_target_mode": getattr(self.viewport, 'orbit_target_mode', 'Object'),
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
            "dolly_zoom":           bool(getattr(self, "chk_dolly_zoom", None) and self.chk_dolly_zoom.isChecked()),

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
            "horizon_always_horizontal": bool(getattr(gs, "horizon_always_horizontal", False)),
            "grid_ground":          bool(gs.ground_enabled),
            "grid_ceiling":         bool(gs.ceiling_enabled),
            "grid_ceil_h":          float(gs.ceiling_height),
            "grid_extent":          int(gs.grid_extent),
            "grid_tile":            float(gs.tile_size),
            "grid_subdiv":          int(gs.subdivisions),
            "grid_exceed":          bool(gs.exceed_lines),
            "grid_fade":            bool(getattr(gs, "fade_grid", False)),
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
            "sec_presets_exp":           self.sec_presets.is_expanded() if hasattr(self, "sec_presets") else True,
            "sec_object_exp":            self.sec_object.is_expanded() if hasattr(self, "sec_object") else True,
            "sec_model_exp":             self.sec_model.is_expanded() if hasattr(self, "sec_model") else True,
            "sec_cam_exp":               self.sec_cam.is_expanded() if hasattr(self, "sec_cam") else True,
            "sec_canvas_exp":            self.sec_canvas.is_expanded() if hasattr(self, "sec_canvas") else True,
            "sec_grid_exp":              self.sec_grid.is_expanded() if hasattr(self, "sec_grid") else True,
            "sec_light_exp":             self.sec_light.is_expanded() if hasattr(self, "sec_light") else False,
            "sec_settings_exp":          self.sec_settings.is_expanded() if hasattr(self, "sec_settings") else False,
            "sec_viewport_settings_exp": self.sec_viewport_settings.is_expanded() if hasattr(self, "sec_viewport_settings") else False,

            # Object Transform & Primitive
            "obj_pos_x":            float(self.viewport.object_transform.pos_x) if hasattr(self.viewport, 'object_transform') else 0.0,
            "obj_pos_y":            float(self.viewport.object_transform.pos_y) if hasattr(self.viewport, 'object_transform') else 0.0,
            "obj_pos_z":            float(self.viewport.object_transform.pos_z) if hasattr(self.viewport, 'object_transform') else 0.0,
            "obj_rot_x":            float(self.viewport.object_transform.rot_x) if hasattr(self.viewport, 'object_transform') else 0.0,
            "obj_rot_y":            float(self.viewport.object_transform.rot_y) if hasattr(self.viewport, 'object_transform') else 0.0,
            "obj_rot_z":            float(self.viewport.object_transform.rot_z) if hasattr(self.viewport, 'object_transform') else 0.0,
            "obj_scale_x":          float(self.viewport.object_transform.scale_x) if hasattr(self.viewport, 'object_transform') else 1.0,
            "obj_scale_y":          float(self.viewport.object_transform.scale_y) if hasattr(self.viewport, 'object_transform') else 1.0,
            "obj_scale_z":          float(self.viewport.object_transform.scale_z) if hasattr(self.viewport, 'object_transform') else 1.0,
            "primitive_type":       getattr(self.mesh, "primitive_type", "") if self.mesh else "",
            "primitive_params":     getattr(self.mesh, "primitive_params", {}) if self.mesh else {},
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
            if not loaded and data.get("primitive_type"):
                ptype = data.get("primitive_type")
                pparams = data.get("primitive_params", {})
                if ptype == "Box":
                    self.mesh = create_box_primitive(pparams.get("w", 2.0), pparams.get("h", 2.0), pparams.get("d", 2.0))
                elif ptype == "Cylinder":
                    self.mesh = create_cylinder_primitive(pparams.get("radius", 1.0), pparams.get("height", 2.0), pparams.get("segments", 24))
                elif ptype == "Sphere":
                    self.mesh = create_sphere_primitive(pparams.get("radius", 1.0), pparams.get("rings", 16), pparams.get("sectors", 24))
                elif ptype == "Pyramid":
                    self.mesh = create_pyramid_primitive(pparams.get("w", 2.0), pparams.get("h", 2.0), pparams.get("d", 2.0))
                elif ptype == "Cone":
                    self.mesh = create_cone_primitive(pparams.get("radius", 1.0), pparams.get("height", 2.0), pparams.get("segments", 24))
                elif ptype == "Plane":
                    self.mesh = create_plane_primitive(pparams.get("w", 2.0), pparams.get("d", 2.0), pparams.get("subdivisions", 2))
                if self.mesh:
                    self.viewport.set_mesh(self.mesh)
                    self.lbl_model.setText(f"Primitive: {ptype}\n{len(self.mesh.vertices)} verts, {len(self.mesh.faces)} faces")
                    loaded = True

            if not loaded and self.mesh is None and not data.get("primitive_type"):
                default_asaro = os.path.join(os.path.dirname(__file__), "3D-Primitive", "Asaro Head Planes.obj")
                if os.path.exists(default_asaro):
                    self._load_file(default_asaro, frame=False)

            # Restore Object Transform
            t = getattr(self.viewport, 'object_transform', None)
            if t:
                t.pos_x = float(data.get("obj_pos_x", 0.0))
                t.pos_y = float(data.get("obj_pos_y", 0.0))
                t.pos_z = float(data.get("obj_pos_z", 0.0))
                t.rot_x = float(data.get("obj_rot_x", 0.0))
                t.rot_y = float(data.get("obj_rot_y", 0.0))
                t.rot_z = float(data.get("obj_rot_z", 0.0))
                t.scale_x = float(data.get("obj_scale_x", 1.0))
                t.scale_y = float(data.get("obj_scale_y", 1.0))
                t.scale_z = float(data.get("obj_scale_z", 1.0))

            # 2. Viewport height & Sticky Viewport
            vh = data.get("viewport_height", 170)
            if 60 <= vh <= 800:
                self.viewport.setFixedHeight(vh)
                if hasattr(self, 'spin_vp_height'):
                    self.spin_vp_height.blockSignals(True)
                    self.spin_vp_height.setValue(vh)
                    self.spin_vp_height.blockSignals(False)

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

            tl = bool(data.get("show_top_labels", True))
            self.viewport.show_top_labels = tl
            if hasattr(self, "chk_vp_top_labels"):
                self.chk_vp_top_labels.blockSignals(True)
                self.chk_vp_top_labels.setChecked(tl)
                self.chk_vp_top_labels.blockSignals(False)

            ob = bool(data.get("show_orbit_button", True))
            self.viewport.show_orbit_button = ob
            if hasattr(self, "chk_vp_orbit_btn"):
                self.chk_vp_orbit_btn.blockSignals(True)
                self.chk_vp_orbit_btn.setChecked(ob)
                self.chk_vp_orbit_btn.blockSignals(False)
            if hasattr(self.viewport, '_layout_bottom_controls'):
                self.viewport._layout_bottom_controls()

            # Quick Actions Toolbar
            qt_items = data.get("quick_toolbar_items")
            if qt_items and hasattr(self, "quick_toolbar"):
                self.quick_toolbar.set_items(qt_items)

            show_qt = bool(data.get("show_quick_toolbar", True))
            if hasattr(self, "quick_toolbar"):
                self.quick_toolbar.setVisible(show_qt)
            if hasattr(self, "chk_vp_quick_toolbar"):
                self.chk_vp_quick_toolbar.blockSignals(True)
                self.chk_vp_quick_toolbar.setChecked(show_qt)
                self.chk_vp_quick_toolbar.blockSignals(False)

            # Viewport Background Styling
            use_grad = bool(data.get("bg_use_gradient", True))
            self.viewport.bg_use_gradient = use_grad
            if hasattr(self, "chk_vp_bg_gradient"):
                self.chk_vp_bg_gradient.blockSignals(True)
                self.chk_vp_bg_gradient.setChecked(use_grad)
                self.chk_vp_bg_gradient.blockSignals(False)

            top_col = data.get("bg_color_top", "#323844")
            bot_col = data.get("bg_color_bottom", "#181b22")
            self.viewport.bg_color_top = QColor(top_col)
            self.viewport.bg_color_bottom = QColor(bot_col)
            self._update_vp_bg_buttons()

            # Navigation preferences
            cam_mode = data.get("nav_camera_mode", CAMERA_MODE_ORBIT)
            self.viewport.camera_mode = cam_mode
            if hasattr(self, "combo_cam_mode"):
                idx = self.combo_cam_mode.findText(cam_mode)
                if idx >= 0:
                    self.combo_cam_mode.blockSignals(True)
                    self.combo_cam_mode.setCurrentIndex(idx)
                    self.combo_cam_mode.blockSignals(False)

            if hasattr(self.viewport, "set_orbit_target_mode"):
                self.viewport.set_orbit_target_mode(data.get("nav_orbit_target_mode", "Object"))

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

            if hasattr(self, "chk_dolly_zoom"):
                self.chk_dolly_zoom.blockSignals(True)
                self.chk_dolly_zoom.setChecked(bool(data.get("dolly_zoom", False)))
                self.chk_dolly_zoom.blockSignals(False)

            if hasattr(self, "chk_fish_dolly"):
                self.chk_fish_dolly.blockSignals(True)
                self.chk_fish_dolly.setChecked(bool(data.get("dolly_zoom", False)))
                self.chk_fish_dolly.blockSignals(False)

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
            gs.horizon_always_horizontal = bool(data.get("horizon_always_horizontal", False))
            gs.ground_enabled = bool(data.get("grid_ground", True))
            gs.ceiling_enabled = bool(data.get("grid_ceiling", False))
            gs.ceiling_height = float(data.get("grid_ceil_h", 2.5))
            gs.grid_extent = int(data.get("grid_extent", 10))
            gs.tile_size = float(data.get("grid_tile", 0.5))
            gs.subdivisions = int(data.get("grid_subdiv", 1))
            gs.exceed_lines = bool(data.get("grid_exceed", True))
            gs.fade_grid = bool(data.get("grid_fade", False))
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
            if hasattr(self, "chk_horizon_level"):
                self.chk_horizon_level.blockSignals(True)
                self.chk_horizon_level.setChecked(gs.horizon_always_horizontal)
                self.chk_horizon_level.blockSignals(False)
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
            if hasattr(self, "chk_fade_grid"):
                self.chk_fade_grid.blockSignals(True)
                self.chk_fade_grid.setChecked(gs.fade_grid)
                self.chk_fade_grid.blockSignals(False)
            if hasattr(self, "chk_verticals"):
                self.chk_verticals.blockSignals(True)
                self.chk_verticals.setChecked(gs.vertical_lines)
                self.chk_verticals.blockSignals(False)
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
                ("sec_presets",           "sec_presets_exp"),
                ("sec_object",            "sec_object_exp"),
                ("sec_model",             "sec_model_exp"),
                ("sec_cam",               "sec_cam_exp"),
                ("sec_canvas",            "sec_canvas_exp"),
                ("sec_grid",              "sec_grid_exp"),
                ("sec_light",             "sec_light_exp"),
                ("sec_settings",          "sec_settings_exp"),
                ("sec_viewport_settings", "sec_viewport_settings_exp"),
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
