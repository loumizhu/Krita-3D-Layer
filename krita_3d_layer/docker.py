"""
docker.py - Krita DockWidget providing rich 3D controls and embedded viewport.
Fully fluid layout: no fixed widths, no clipping at narrow docker sizes.
All controls flow and wrap naturally.

Features:
- Collapsible parameter sections ordered by importance
- Interactive 3D Viewport with camera presets
- Live Canvas Sync ON by default — every parameter tweak updates canvas
- Camera modes: Orbit, First Person, Turntable
- Camera target coordinates (center on object)
- Near/Far clipping plane controls
- Comprehensive Camera & Perspective controls
- Wireframe backface culling toggle
- Wireframe & contour thickness + color pickers
- 3D Sphere Light Controller
- Programmatic API: Krita3DLayerDocker.instance()
"""

import os
import math
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QComboBox, QCheckBox, QSlider, QFileDialog,
    QColorDialog, QScrollArea, QFrame, QSizePolicy, QGridLayout,
    QButtonGroup, QDoubleSpinBox, QSpinBox
)
from PyQt5.QtGui import QColor
from PyQt5.QtCore import Qt

try:
    from krita import DockWidget, Krita
except ImportError:
    from PyQt5.QtWidgets import QDockWidget as DockWidget
    Krita = None

from .viewport import Viewport3D, CAMERA_MODES, CAMERA_MODE_ORBIT
from .renderer import RenderStyle
from .mesh_loader import load_3d_file
from .canvas_sync import CanvasSyncManager
from .widgets import CollapsibleSection, SphereLightWidget

DOCKER_ID = "krita_3d_layer_docker"
DEFAULT_ASARO_PATH = r"E:\(( References_Photos & Drawing ))\(( 00 - Figure Character Anatomy Ultimate Plates References - Anatomie))\00 - Head Tête - Anatomy Plates\3D Head Model Asaro\Asaro Head Planes.obj"

# Fluid stylesheet — NO min-width, NO fixed sizes except modest min-height
DOCKER_STYLE = """
    * { font-family: "Segoe UI", sans-serif; }
    QPushButton {
        font-size: 10px; padding: 2px 3px; min-height: 18px;
        background: #323642; border: 1px solid #434958;
        border-radius: 2px; color: #e5e7eb;
    }
    QPushButton:hover { background: #3d4352; color: #fff; }
    QPushButton:pressed { background: #242730; }
    QPushButton:checked { background: #2563eb; border-color: #3b82f6; color: #fff; font-weight: bold; }
    QLabel { font-size: 10px; color: #cbd5e1; }
    QComboBox {
        font-size: 10px; min-height: 18px; padding: 1px 3px;
        background: #262932; border: 1px solid #3d4352;
        border-radius: 2px; color: #e5e7eb;
    }
    QComboBox::drop-down { border: none; width: 14px; }
    QCheckBox { font-size: 10px; color: #cbd5e1; spacing: 3px; }
    QSlider { min-height: 14px; max-height: 16px; }
    QSlider::groove:horizontal { height: 3px; background: #252831; border-radius: 1px; }
    QSlider::sub-page:horizontal { background: #3b82f6; border-radius: 1px; }
    QSlider::handle:horizontal {
        background: #93c5fd; border: 1px solid #1d4ed8;
        width: 8px; margin: -3px 0; border-radius: 4px;
    }
    QSlider::handle:horizontal:hover { background: #fff; }
    QDoubleSpinBox, QSpinBox {
        font-size: 10px; min-height: 18px; padding: 1px 2px;
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
        self.setWindowTitle("3D Layer")

        # Root scrollable widget — full fluid layout
        root = QWidget()
        root.setStyleSheet(DOCKER_STYLE)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setWidget(root)
        self.setWidget(scroll)

        L = QVBoxLayout(root)
        L.setContentsMargins(2, 2, 2, 2)
        L.setSpacing(3)

        # =============================================================
        # SECTION 1: 3D VIEWPORT
        # =============================================================
        self.sec_viewport = CollapsibleSection("3D VIEWPORT", expanded=True)

        self.viewport = Viewport3D()
        self.viewport.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.viewport.setMinimumHeight(100)
        self.viewport.camera_changed.connect(self._on_camera_changed)
        self.viewport.interaction_ended.connect(self._on_interaction_ended)
        self.viewport.fov_changed.connect(self._on_viewport_fov_changed)
        self.sec_viewport.add_widget(self.viewport)

        # Cam presets — use FlowLayout via wrapping grid
        cg = QGridLayout()
        cg.setSpacing(1)
        cg.setContentsMargins(0, 0, 0, 0)
        for idx, (lbl, fn) in enumerate([
            ("Frt", self.viewport.camera.set_front),
            ("3/4", self.viewport.camera.set_three_quarter),
            ("R", self.viewport.camera.set_side_right),
            ("L", self.viewport.camera.set_side_left),
            ("Top", self.viewport.camera.set_top),
            ("Rst", self._reset_camera_all),
        ]):
            b = QPushButton(lbl)
            b.clicked.connect(self._cam_cb(fn))
            cg.addWidget(b, idx // 3, idx % 3)
        self.sec_viewport.add_layout(cg)
        L.addWidget(self.sec_viewport)

        # =============================================================
        # SECTION 2: CANVAS SYNC
        # =============================================================
        self.sec_canvas = CollapsibleSection("CANVAS SYNC", expanded=True)

        self.btn_stamp = QPushButton("🎨 Stamp to Canvas")
        self.btn_stamp.setStyleSheet(
            "QPushButton{background:#2563eb;color:#fff;font-weight:bold;padding:4px;border-radius:3px;border:1px solid #1d4ed8;}"
            "QPushButton:hover{background:#3b82f6;}"
            "QPushButton:pressed{background:#1e40af;}"
        )
        self.btn_stamp.clicked.connect(self._stamp)
        self.sec_canvas.add_widget(self.btn_stamp)

        r = QHBoxLayout(); r.setSpacing(2)
        self.chk_live = QCheckBox("Live")
        self.chk_live.setChecked(True)
        self.chk_live.setToolTip("Auto-update canvas on every change")
        r.addWidget(self.chk_live)
        b = QPushButton("📐")
        b.setToolTip("Match canvas ratio")
        b.clicked.connect(self._match_ratio)
        r.addWidget(b)
        self.sec_canvas.add_layout(r)

        self.combo_layer = QComboBox()
        self.combo_layer.addItem("Update '3D Reference'", "named")
        self.combo_layer.addItem("New layer each", "new")
        self.combo_layer.addItem("Overwrite active", "active")
        self.sec_canvas.add_widget(self.combo_layer)

        self.lbl_status = QLabel("Ready")
        self.lbl_status.setStyleSheet("color:#94a3b8;font-size:9px;")
        self.lbl_status.setAlignment(Qt.AlignHCenter)
        self.sec_canvas.add_widget(self.lbl_status)
        L.addWidget(self.sec_canvas)

        # =============================================================
        # SECTION 3: CAMERA & PERSPECTIVE
        # =============================================================
        self.sec_cam = CollapsibleSection("CAMERA", expanded=True)

        # Camera Mode
        self.combo_cam_mode = QComboBox()
        for m in CAMERA_MODES:
            self.combo_cam_mode.addItem(m)
        self.combo_cam_mode.currentTextChanged.connect(self._on_cam_mode)
        self.sec_cam.add_widget(self.combo_cam_mode)

        # Projection toggle
        pr = QHBoxLayout(); pr.setSpacing(1)
        self.btn_persp = QPushButton("Persp")
        self.btn_persp.setCheckable(True); self.btn_persp.setChecked(True)
        self.btn_ortho = QPushButton("Ortho")
        self.btn_ortho.setCheckable(True)
        pg = QButtonGroup(self)
        pg.addButton(self.btn_persp); pg.addButton(self.btn_ortho)
        self.btn_persp.clicked.connect(lambda: self._set_proj(False))
        self.btn_ortho.clicked.connect(lambda: self._set_proj(True))
        pr.addWidget(self.btn_persp); pr.addWidget(self.btn_ortho)
        self.sec_cam.add_layout(pr)

        # FOV
        self.lbl_fov = QLabel("FOV 45° (43mm)")
        self.sec_cam.add_widget(self.lbl_fov)
        self.sl_fov = self._slider(10, 120, 45, self._on_fov)
        self.sec_cam.add_widget(self.sl_fov)

        # Lens presets
        lr = QHBoxLayout(); lr.setSpacing(1)
        for nm, fv in [("14", 100), ("24", 73), ("50", 40), ("85", 24), ("135", 15)]:
            b = QPushButton(nm)
            b.setToolTip(f"{nm}mm lens")
            b.clicked.connect(self._lens_cb(fv))
            lr.addWidget(b)
        self.sec_cam.add_layout(lr)

        # Distance
        self.lbl_dist = QLabel("Dist 2.4")
        self.sec_cam.add_widget(self.lbl_dist)
        self.sl_dist = self._slider(1, 200, 24, self._on_dist)
        self.sec_cam.add_widget(self.sl_dist)

        # Roll
        rr = QHBoxLayout(); rr.setSpacing(1)
        self.lbl_roll = QLabel("Roll 0°")
        rr.addWidget(self.lbl_roll)
        b = QPushButton("0°"); b.clicked.connect(self._reset_roll)
        rr.addWidget(b)
        self.sec_cam.add_layout(rr)
        self.sl_roll = self._slider(-180, 180, 0, self._on_roll)
        self.sec_cam.add_widget(self.sl_roll)

        # Camera Target (Center On)
        tl = QLabel("Target XYZ:")
        tl.setStyleSheet("font-weight:bold;")
        self.sec_cam.add_widget(tl)
        tr = QHBoxLayout(); tr.setSpacing(1)
        self.spin_tx = self._dspin(-50, 50, 0.0, 0.1, self._on_target)
        self.spin_ty = self._dspin(-50, 50, 0.0, 0.1, self._on_target)
        self.spin_tz = self._dspin(-50, 50, 0.0, 0.1, self._on_target)
        tr.addWidget(self.spin_tx); tr.addWidget(self.spin_ty); tr.addWidget(self.spin_tz)
        self.sec_cam.add_layout(tr)

        cr = QHBoxLayout(); cr.setSpacing(1)
        b = QPushButton("Center on Model")
        b.clicked.connect(self._center_on_model)
        cr.addWidget(b)
        b2 = QPushButton("Origin")
        b2.clicked.connect(self._center_origin)
        cr.addWidget(b2)
        self.sec_cam.add_layout(cr)

        L.addWidget(self.sec_cam)

        # =============================================================
        # SECTION 4: CLIPPING
        # =============================================================
        self.sec_clip = CollapsibleSection("CLIPPING", expanded=False)

        self.lbl_near = QLabel("Near: 0.01")
        self.sec_clip.add_widget(self.lbl_near)
        self.sl_near = self._slider(1, 500, 1, self._on_near)  # 0.01 to 5.0
        self.sec_clip.add_widget(self.sl_near)

        self.lbl_far = QLabel("Far: 200")
        self.sec_clip.add_widget(self.lbl_far)
        self.sl_far = self._slider(10, 1000, 200, self._on_far)
        self.sec_clip.add_widget(self.sl_far)

        L.addWidget(self.sec_clip)

        # =============================================================
        # SECTION 5: STYLE & OUTLINES
        # =============================================================
        self.sec_style = CollapsibleSection("STYLE", expanded=True)

        self.combo_style = QComboBox()
        self.combo_style.addItems([
            RenderStyle.SHADED_WIREFRAME, RenderStyle.SHADED,
            RenderStyle.WIREFRAME, RenderStyle.SILHOUETTE, RenderStyle.NORMAL_MAP
        ])
        self.combo_style.currentTextChanged.connect(self._on_style)
        self.sec_style.add_widget(self.combo_style)

        # Wireframe backface culling
        self.chk_wire_cull = QCheckBox("Hide back wireframes")
        self.chk_wire_cull.setChecked(True)
        self.chk_wire_cull.setToolTip("Cull back-facing wireframe triangles")
        self.chk_wire_cull.stateChanged.connect(self._on_wire_cull)
        self.sec_style.add_widget(self.chk_wire_cull)

        # Wire width
        wr = QHBoxLayout(); wr.setSpacing(1)
        self.lbl_wire = QLabel("Wire 1.0")
        wr.addWidget(self.lbl_wire)
        bw = QPushButton("🔲")
        bw.setToolTip("Wire color")
        bw.clicked.connect(self._pick_wire_col)
        wr.addWidget(bw)
        self.sec_style.add_layout(wr)
        self.sl_wire = self._slider(5, 50, 10, self._on_wire_w)
        self.sec_style.add_widget(self.sl_wire)

        # Contour
        cr2 = QHBoxLayout(); cr2.setSpacing(1)
        self.lbl_contour = QLabel("Contour Off")
        cr2.addWidget(self.lbl_contour)
        bc = QPushButton("🖊")
        bc.setToolTip("Contour color")
        bc.clicked.connect(self._pick_contour_col)
        cr2.addWidget(bc)
        self.sec_style.add_layout(cr2)
        self.sl_contour = self._slider(0, 80, 0, self._on_contour_w)
        self.sec_style.add_widget(self.sl_contour)

        # Base color + transparent
        br = QHBoxLayout(); br.setSpacing(2)
        bb = QPushButton("🎨 Color")
        bb.clicked.connect(self._pick_base_col)
        br.addWidget(bb)
        self.chk_transp = QCheckBox("T.BG")
        self.chk_transp.setChecked(True)
        self.chk_transp.stateChanged.connect(self._live_sync)
        br.addWidget(self.chk_transp)
        self.sec_style.add_layout(br)

        L.addWidget(self.sec_style)

        # =============================================================
        # SECTION 6: LIGHTING
        # =============================================================
        self.sec_light = CollapsibleSection("LIGHTING", expanded=True)

        sr = QHBoxLayout(); sr.setSpacing(4)
        self.light_sphere = SphereLightWidget()
        self.light_sphere.light_changed.connect(self._on_sphere_light)
        self.light_sphere.interaction_ended.connect(self._on_interaction_ended)
        sr.addWidget(self.light_sphere)

        sc = QVBoxLayout(); sc.setSpacing(1)
        self.lbl_light = QLabel("Az:45 El:40")
        self.lbl_light.setStyleSheet("font-weight:bold;")
        sc.addWidget(self.lbl_light)
        self.chk_follow = QCheckBox("Follow Cam")
        self.chk_follow.setChecked(True)
        self.chk_follow.stateChanged.connect(self._on_follow)
        sc.addWidget(self.chk_follow)
        rl = QPushButton("Reset")
        rl.clicked.connect(self._reset_light)
        sc.addWidget(rl)
        sr.addLayout(sc)
        self.sec_light.add_layout(sr)

        self.lbl_amb = QLabel("Ambient 35%")
        self.sec_light.add_widget(self.lbl_amb)
        self.sl_amb = self._slider(0, 100, 35, self._on_amb)
        self.sec_light.add_widget(self.sl_amb)

        self.lbl_diff = QLabel("Key 65%")
        self.sec_light.add_widget(self.lbl_diff)
        self.sl_diff = self._slider(0, 100, 65, self._on_diff)
        self.sec_light.add_widget(self.sl_diff)

        L.addWidget(self.sec_light)

        # =============================================================
        # SECTION 7: MODEL (collapsed by default)
        # =============================================================
        self.sec_model = CollapsibleSection("MODEL", expanded=False)

        mr = QHBoxLayout(); mr.setSpacing(1)
        bi = QPushButton("📁 Import")
        bi.clicked.connect(self._import)
        mr.addWidget(bi)
        if os.path.exists(DEFAULT_ASARO_PATH):
            ba = QPushButton("🗿 Asaro")
            ba.clicked.connect(lambda: self._load(DEFAULT_ASARO_PATH))
            mr.addWidget(ba)
        self.sec_model.add_layout(mr)

        self.lbl_model = QLabel("No model")
        self.lbl_model.setWordWrap(True)
        self.lbl_model.setStyleSheet("color:#8fa0b5;font-size:9px;")
        self.sec_model.add_widget(self.lbl_model)

        L.addWidget(self.sec_model)
        L.addStretch(1)

        # Auto-load
        if os.path.exists(DEFAULT_ASARO_PATH):
            self._load(DEFAULT_ASARO_PATH)

    # -----------------------------------------------------------------
    # Helpers
    # -----------------------------------------------------------------
    def _slider(self, lo, hi, val, cb):
        s = QSlider(Qt.Horizontal)
        s.setRange(lo, hi); s.setValue(val)
        s.valueChanged.connect(cb)
        s.sliderReleased.connect(self._live_sync)
        return s

    def _dspin(self, lo, hi, val, step, cb):
        s = QDoubleSpinBox()
        s.setRange(lo, hi); s.setValue(val); s.setSingleStep(step)
        s.setDecimals(2)
        s.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        s.valueChanged.connect(cb)
        return s

    def _cam_cb(self, fn):
        def cb():
            fn()
            self._sync_ui(); self.viewport.update()
            self._live_sync()
        return cb

    def _lens_cb(self, fv):
        def cb(): self.sl_fov.setValue(fv)
        return cb

    def _live_sync(self, *_):
        if self.chk_live.isChecked():
            self._stamp()

    def _on_camera_changed(self):
        self._sync_ui()

    def _on_interaction_ended(self):
        self._live_sync()

    def _on_viewport_fov_changed(self, fov):
        """Sync FOV slider when viewport scroll wheel changes FOV."""
        self.sl_fov.blockSignals(True)
        self.sl_fov.setValue(int(fov))
        self.sl_fov.blockSignals(False)
        self._update_fov_label(fov)

    # -----------------------------------------------------------------
    # UI Sync
    # -----------------------------------------------------------------
    def _sync_ui(self):
        c = self.viewport.camera
        if not self.sl_fov.isSliderDown():
            self.sl_fov.blockSignals(True); self.sl_fov.setValue(int(c.fov)); self.sl_fov.blockSignals(False)
        self._update_fov_label(c.fov)
        if not self.sl_dist.isSliderDown():
            self.sl_dist.blockSignals(True); self.sl_dist.setValue(int(c.distance * 10)); self.sl_dist.blockSignals(False)
        self.lbl_dist.setText(f"Dist {c.distance:.1f}")
        if not self.sl_roll.isSliderDown():
            self.sl_roll.blockSignals(True); self.sl_roll.setValue(int(c.roll)); self.sl_roll.blockSignals(False)
        self.lbl_roll.setText(f"Roll {int(c.roll)}°")
        self.light_sphere.blockSignals(True)
        self.light_sphere.set_light(self.viewport.lighting.azimuth, self.viewport.lighting.elevation)
        self.light_sphere.blockSignals(False)
        self.lbl_light.setText(f"Az:{int(self.viewport.lighting.azimuth)} El:{int(self.viewport.lighting.elevation)}")

    def _update_fov_label(self, fov):
        rad = math.radians(max(2, min(170, fov)) * 0.5)
        mm = round(18.0 / math.tan(rad))
        self.lbl_fov.setText(f"FOV {int(fov)}° ({mm}mm)")

    # -----------------------------------------------------------------
    # Camera
    # -----------------------------------------------------------------
    def _on_cam_mode(self, text):
        self.viewport.set_camera_mode(text)

    def _set_proj(self, ortho):
        self.viewport.camera.orthographic = ortho
        self.btn_persp.setChecked(not ortho)
        self.btn_ortho.setChecked(ortho)
        self.sl_fov.setEnabled(not ortho)
        self.viewport.update()
        self._live_sync()

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

    def _on_roll(self, v):
        self.viewport.camera.roll = float(v)
        self.lbl_roll.setText(f"Roll {v}°")
        self.viewport.update()
        self._live_sync()

    def _reset_roll(self):
        self.viewport.camera.roll = 0
        self.sl_roll.setValue(0)
        self.viewport.update()
        self._live_sync()

    def _reset_camera_all(self):
        self.viewport.camera.reset()
        self.btn_persp.setChecked(True); self.btn_ortho.setChecked(False)
        self.sl_fov.setEnabled(True)
        self._sync_target_spins()
        self._sync_ui(); self.viewport.update()
        self._live_sync()

    def _on_target(self, _=None):
        self.viewport.camera.target_x = self.spin_tx.value()
        self.viewport.camera.target_y = self.spin_ty.value()
        self.viewport.camera.target_z = self.spin_tz.value()
        self.viewport.update()
        self._live_sync()

    def _center_on_model(self):
        m = self.viewport.mesh
        if m:
            self.spin_tx.setValue(m.center.x())
            self.spin_ty.setValue(m.center.y())
            self.spin_tz.setValue(m.center.z())

    def _center_origin(self):
        self.spin_tx.setValue(0.0)
        self.spin_ty.setValue(0.0)
        self.spin_tz.setValue(0.0)

    def _sync_target_spins(self):
        c = self.viewport.camera
        self.spin_tx.blockSignals(True); self.spin_tx.setValue(c.target_x); self.spin_tx.blockSignals(False)
        self.spin_ty.blockSignals(True); self.spin_ty.setValue(c.target_y); self.spin_ty.blockSignals(False)
        self.spin_tz.blockSignals(True); self.spin_tz.setValue(c.target_z); self.spin_tz.blockSignals(False)

    # -----------------------------------------------------------------
    # Clipping
    # -----------------------------------------------------------------
    def _on_near(self, v):
        val = v / 100.0
        self.viewport.camera.near_clip = val
        self.lbl_near.setText(f"Near: {val:.2f}")
        self.viewport.update()
        self._live_sync()

    def _on_far(self, v):
        self.viewport.camera.far_clip = float(v)
        self.lbl_far.setText(f"Far: {v}")
        self.viewport.update()
        self._live_sync()

    # -----------------------------------------------------------------
    # Style
    # -----------------------------------------------------------------
    def _on_style(self, t):
        self.viewport.set_render_style(t)
        self._live_sync()

    def _on_wire_cull(self, state):
        self.viewport.renderer.wireframe_backface_culling = (state == Qt.Checked)
        self.viewport.update()
        self._live_sync()

    def _on_wire_w(self, v):
        t = v / 10.0
        self.viewport.renderer.wire_width = t
        self.lbl_wire.setText(f"Wire {t:.1f}")
        self.viewport.update()
        self._live_sync()

    def _on_contour_w(self, v):
        t = v / 10.0
        self.viewport.renderer.contour_width = t
        self.lbl_contour.setText(f"Contour {t:.1f}" if t > 0.05 else "Contour Off")
        self.viewport.update()
        self._live_sync()

    def _pick_base_col(self):
        c = QColorDialog.getColor(self.viewport.renderer.base_color, self)
        if c.isValid():
            self.viewport.renderer.base_color = c
            self.viewport.update()
            self._live_sync()

    def _pick_wire_col(self):
        c = QColorDialog.getColor(self.viewport.renderer.wire_color, self)
        if c.isValid():
            self.viewport.renderer.wire_color = c
            self.viewport.update()
            self._live_sync()

    def _pick_contour_col(self):
        c = QColorDialog.getColor(self.viewport.renderer.contour_color, self)
        if c.isValid():
            self.viewport.renderer.contour_color = c
            self.viewport.update()
            self._live_sync()

    # -----------------------------------------------------------------
    # Lighting
    # -----------------------------------------------------------------
    def _on_sphere_light(self, az, el):
        self.viewport.lighting.azimuth = az
        self.viewport.lighting.elevation = el
        self.lbl_light.setText(f"Az:{int(az)} El:{int(el)}")
        self.viewport.update()

    def _on_follow(self, st):
        self.viewport.lighting.follow_camera = (st == Qt.Checked)
        self.viewport.update()
        self._live_sync()

    def _reset_light(self):
        self.viewport.lighting.azimuth = 45.0
        self.viewport.lighting.elevation = 40.0
        self.chk_follow.setChecked(True)
        self.light_sphere.set_light(45, 40)
        self.lbl_light.setText("Az:45 El:40")
        self.viewport.update()
        self._live_sync()

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
    # Model
    # -----------------------------------------------------------------
    def _import(self):
        fp, _ = QFileDialog.getOpenFileName(self, "Import 3D", "", "3D (*.obj *.stl)")
        if fp:
            self._load(fp)

    def _load(self, fp):
        try:
            m = load_3d_file(fp)
            self.viewport.set_mesh(m)
            self.lbl_model.setText(f"{m.name}\n{m.face_count:,}f {m.vertex_count:,}v")
            self.lbl_status.setText(f"Loaded: {m.name}")
            self._match_ratio()
            self._live_sync()
        except Exception as e:
            self.lbl_model.setText(f"Error: {e}")
            self.lbl_status.setText(str(e))

    def _match_ratio(self):
        info = CanvasSyncManager.get_document_info()
        if info:
            self.viewport.set_canvas_aspect_ratio(info["aspect_ratio"])
        else:
            self.viewport.set_canvas_aspect_ratio(None)

    def _stamp(self):
        if not self.viewport.mesh:
            return
        try:
            ln = CanvasSyncManager.render_to_krita_layer(
                mesh=self.viewport.mesh,
                camera=self.viewport.camera,
                lighting=self.viewport.lighting,
                renderer=self.viewport.renderer,
                render_style=self.viewport.render_style,
                layer_mode=self.combo_layer.currentData(),
                layer_name="3D Model Reference",
                transparent_bg=self.chk_transp.isChecked()
            )
            self.lbl_status.setText(f"→ {ln}")
        except Exception as e:
            self.lbl_status.setText(f"Err: {e}")

    def canvasChanged(self, canvas):
        self._match_ratio()
