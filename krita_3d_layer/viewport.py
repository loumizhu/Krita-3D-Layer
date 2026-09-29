"""
Interactive 3D viewport widget with camera navigation and perspective overlays.
"""

import math
from PyQt5.QtWidgets import QWidget, QSizePolicy, QToolTip, QPushButton
from PyQt5.QtGui import (
    QPainter, QColor, QFont, QPen, QBrush, QImage, QLinearGradient, QCursor, QVector3D
)
from PyQt5.QtCore import Qt, QPoint, QRect, QPointF, pyqtSignal

from .renderer import (
    Camera3D, Lighting3D, Renderer3D, RenderStyle,
    PerspectiveGridSettings, ProjectionMode, ObjectTransform
)

# Camera navigation modes
CAMERA_MODE_ORBIT       = "Orbit Around Object"
CAMERA_MODE_TURNTABLE   = "Turntable (Locked Up)"
CAMERA_MODE_FIRST_PERSON = "First Person (Look Around)"

CAMERA_MODES = [CAMERA_MODE_ORBIT, CAMERA_MODE_TURNTABLE, CAMERA_MODE_FIRST_PERSON]

# Orbit target modes (pivot point for camera rotation)
ORBIT_TARGET_OBJECT      = "Object"
ORBIT_TARGET_ORIGIN      = "Origin"
ORBIT_TARGET_VIEW_CENTER = "View Center"
ORBIT_TARGET_MODES = [ORBIT_TARGET_OBJECT, ORBIT_TARGET_ORIGIN, ORBIT_TARGET_VIEW_CENTER]

# Info-bar scrub fields
_INFO_FIELDS = [
    ("Y", "Yaw"),
    ("P", "Pitch"),
    ("T", "Tilt"),
    ("R", "Roll"),
    ("D", "Distance"),
    ("F", "FOV"),
]


class Viewport3D(QWidget):
    camera_changed   = pyqtSignal()
    interaction_ended = pyqtSignal()
    fov_changed      = pyqtSignal(float)
    viewport_height_changed = pyqtSignal(int)   # emitted when resize handle is dragged

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setMouseTracking(True)
        self.setMinimumSize(60, 60)

        # Core 3D engine
        self.camera           = Camera3D()
        self.lighting         = Lighting3D()
        self.renderer         = Renderer3D()
        self.object_transform = ObjectTransform()
        self.mesh             = None
        self.render_style     = RenderStyle.SHADED_WIREFRAME
        self.grid_settings    = PerspectiveGridSettings()

        # Camera navigation mode
        self.camera_mode = CAMERA_MODE_ORBIT

        # Navigation direction preferences (split x/y)
        self.invert_pan     = False
        self.invert_orbit_x = False   # invert left/right (yaw)
        self.invert_orbit_y = False   # invert up/down (pitch)

        # Display toggles
        self.show_overlay_buttons = True
        self.show_gizmo           = True
        self.show_canvas_frame    = True

        # Interaction state
        self.last_mouse_pos  = QPoint()
        self.is_dragging     = False
        self.drag_button     = None
        self.drag_modifiers  = Qt.NoModifier

        # Canvas framing guide
        self.canvas_aspect_ratio = None
        self.scene_frame  = None
        self.frame_label  = ""

        # Overlay buttons
        self.hovered_overlay_action = None
        self.active_overlay_action  = None
        self.overlay_drag_start     = QPoint()

        # Info-bar scrubbing (drag on Y/P/D/F labels)
        self._info_scrub_field    = None   # which field is being scrubbed
        self._info_scrub_start_x  = 0
        self._info_scrub_start_val = 0.0
        self._info_hovered_field  = None

        # Gizmo hit-test rects {label: QRect}
        self._gizmo_rects = {}

        # Viewport background
        self.bg_use_gradient = True
        self.bg_color_top    = QColor(50, 56, 68)
        self.bg_color_bottom = QColor(24, 27, 34)

        # UI toggles
        self.show_overlay_buttons = True
        self.show_gizmo           = True
        self.show_top_labels      = True
        self.show_orbit_button    = True
        self.show_canvas_frame    = True

        # Orbit Target Mode (pivot point for camera rotation)
        self.orbit_target_mode = ORBIT_TARGET_OBJECT

        # Small bottom-center toggle button for Orbit Target Mode
        self.btn_orbit_target = QPushButton(self)
        self.btn_orbit_target.setObjectName("btn_orbit_target")
        self.btn_orbit_target.setCursor(Qt.PointingHandCursor)
        self.btn_orbit_target.setStyleSheet("""
            QPushButton#btn_orbit_target {
                background: rgba(15, 23, 42, 215);
                border: 1px solid rgba(56, 189, 248, 140);
                border-radius: 3px;
                color: #38bdf8;
                font-family: 'Segoe UI';
                font-size: 8px;
                font-weight: bold;
                padding: 0px 4px;
            }
            QPushButton#btn_orbit_target:hover {
                background: rgba(30, 41, 59, 240);
                border-color: #38bdf8;
                color: #ffffff;
            }
            QPushButton#btn_orbit_target:pressed {
                background: rgba(14, 116, 144, 250);
            }
        """)
        self.btn_orbit_target.clicked.connect(self.toggle_orbit_target_mode)
        self._update_orbit_target_button()

    # ------------------------------------------------------------------
    def set_mesh(self, mesh):
        self.mesh = mesh
        self.update()

    def set_render_style(self, style):
        self.render_style = style
        self.update()

    def set_canvas_aspect_ratio(self, ratio):
        self.canvas_aspect_ratio = ratio
        self.update()

    def set_scene_frame(self, frame_rect, label=""):
        self.scene_frame = frame_rect
        self.frame_label = label
        if frame_rect and frame_rect[2] > 0 and frame_rect[3] > 0:
            self.canvas_aspect_ratio = float(frame_rect[2]) / float(frame_rect[3])
        self.update()

    def clear_scene_frame(self):
        self.set_scene_frame(None, "")

    def set_grid_settings(self, settings):
        self.grid_settings = settings
        self.update()

    def set_camera_mode(self, mode):
        self.camera_mode = mode

    def toggle_orbit_target_mode(self):
        modes = ORBIT_TARGET_MODES
        curr_idx = modes.index(self.orbit_target_mode) if self.orbit_target_mode in modes else 0
        new_mode = modes[(curr_idx + 1) % len(modes)]
        self.set_orbit_target_mode(new_mode)

    def set_orbit_target_mode(self, mode):
        if mode not in ORBIT_TARGET_MODES:
            mode = ORBIT_TARGET_OBJECT
        self.orbit_target_mode = mode
        self._apply_orbit_target_mode()
        self._update_orbit_target_button()
        self.camera_changed.emit()
        self.update()

    def _update_orbit_target_button(self):
        if not hasattr(self, 'btn_orbit_target'):
            return
        if self.orbit_target_mode == ORBIT_TARGET_OBJECT:
            self.btn_orbit_target.setText("⌖ Pivot: Obj")
            self.btn_orbit_target.setToolTip(
                "Orbit Pivot: Object Center\n"
                "Rotating camera pivots around 3D model center.\n"
                "Click to toggle: Origin (0,0,0) ➔ View Center ➔ Object"
            )
        elif self.orbit_target_mode == ORBIT_TARGET_ORIGIN:
            self.btn_orbit_target.setText("⌖ Pivot: (0,0)")
            self.btn_orbit_target.setToolTip(
                "Orbit Pivot: World Origin (0,0,0)\n"
                "Rotating camera pivots around world ground origin.\n"
                "Click to toggle: View Center ➔ Object ➔ Origin"
            )
        elif self.orbit_target_mode == ORBIT_TARGET_VIEW_CENTER:
            self.btn_orbit_target.setText("⌖ Pivot: View")
            self.btn_orbit_target.setToolTip(
                "Orbit Pivot: Viewport Screen Center\n"
                "Rotating camera pivots around current screen look-at center.\n"
                "Click to toggle: Object ➔ Origin ➔ View Center"
            )
        self._layout_bottom_controls()

    def _apply_orbit_target_mode(self):
        if self.orbit_target_mode == ORBIT_TARGET_ORIGIN:
            self.camera.target_x = 0.0
            self.camera.target_y = 0.0
            self.camera.target_z = 0.0
        elif self.orbit_target_mode == ORBIT_TARGET_OBJECT:
            if self.mesh and self.mesh.vertices:
                min_x = min_y = min_z = 1e9
                max_x = max_y = max_z = -1e9
                mat = self.object_transform.get_matrix() if hasattr(self, 'object_transform') and self.object_transform and not self.object_transform.is_identity() else None
                for v in self.mesh.vertices:
                    v_t = mat.map(v) if mat else v
                    vx, vy, vz = v_t.x(), v_t.y(), v_t.z()
                    if vx < min_x: min_x = vx
                    if vx > max_x: max_x = vx
                    if vy < min_y: min_y = vy
                    if vy > max_y: max_y = vy
                    if vz < min_z: min_z = vz
                    if vz > max_z: max_z = vz
                self.camera.target_x = (min_x + max_x) * 0.5
                self.camera.target_y = (min_y + max_y) * 0.5
                self.camera.target_z = (min_z + max_z) * 0.5
            else:
                self.camera.target_x = 0.0
                self.camera.target_y = 0.0
                self.camera.target_z = 0.0
        elif self.orbit_target_mode == ORBIT_TARGET_VIEW_CENTER:
            if abs(self.camera.pan_x) > 1e-4 or abs(self.camera.pan_y) > 1e-4:
                rad_yaw = math.radians(self.camera.yaw)
                rad_pitch = math.radians(self.camera.pitch)
                eye = QVector3D(
                    self.camera.target_x + self.camera.distance * math.cos(rad_pitch) * math.sin(rad_yaw),
                    self.camera.target_y + self.camera.distance * math.sin(rad_pitch),
                    self.camera.target_z + self.camera.distance * math.cos(rad_pitch) * math.cos(rad_yaw)
                )
                fwd = (QVector3D(self.camera.target_x, self.camera.target_y, self.camera.target_z) - eye).normalized()
                right = QVector3D.crossProduct(fwd, QVector3D(0, 1, 0)).normalized()
                cup = QVector3D.crossProduct(right, fwd).normalized()
                new_t = QVector3D(self.camera.target_x, self.camera.target_y, self.camera.target_z) - right * self.camera.pan_x - cup * self.camera.pan_y
                self.camera.target_x = new_t.x()
                self.camera.target_y = new_t.y()
                self.camera.target_z = new_t.z()
                self.camera.pan_x = 0.0
                self.camera.pan_y = 0.0

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._layout_bottom_controls()

    def _layout_bottom_controls(self):
        w = self.width()
        h = self.height()
        if hasattr(self, 'btn_orbit_target'):
            btn_h = 15
            btn_w = max(42, self.btn_orbit_target.sizeHint().width() + 4)
            # Center horizontally at the bottom of the viewport
            bx = (w - btn_w) // 2
            by = h - btn_h - 4
            self.btn_orbit_target.setGeometry(bx, by, btn_w, btn_h)
            self.btn_orbit_target.setVisible(getattr(self, 'show_orbit_button', True) and w > 80 and h > 45)

    # ------------------------------------------------------------------
    # Overlay buttons layout
    # ------------------------------------------------------------------
    def _get_overlay_buttons(self):
        """Returns list of (action_id, symbol, tooltip, QRect) on right side."""
        if not self.show_overlay_buttons:
            return []
        w, h = self.width(), self.height()
        if w < 50 or h < 60:
            return []

        spacing      = 2
        buttons = [
            ("orbit", "⟳", "Orbit View: Drag to rotate (Click to reset 3/4)"),
            ("pan",   "✥", "Pan View: Drag to pan (Click to center)"),
            ("zoom",  "🔍", "Zoom View: Drag to zoom (Click to frame)"),
            ("tilt",  "↕", "Lens Tilt: Drag up/down or left/right (Click to reset 0°)"),
            ("roll",  "↺", "Camera Roll / Tilt: Drag to tilt sideways (Click to reset 0°)"),
        ]
        btn_size = min(20, max(14, (h - 16) // len(buttons) - spacing))
        margin_right = 4
        total_h = len(buttons) * btn_size + (len(buttons) - 1) * spacing
        start_y = max(6, (h - total_h) // 2)
        res = []
        for i, (act, sym, tip) in enumerate(buttons):
            rx = w - margin_right - btn_size
            ry = start_y + i * (btn_size + spacing)
            res.append((act, sym, tip, QRect(rx, ry, btn_size, btn_size)))
        return res

    # ------------------------------------------------------------------
    # Info-bar scrub field rects (top-left overlay)
    # ------------------------------------------------------------------
    def _get_info_field_rects(self):
        """Returns list of (field_id, QRect) for the top-left info overlay."""
        if not (self.width() > 80 and self.height() > 40):
            return []
        font_size = max(7, min(8, int(self.width() * 0.038)))
        rects = []
        x = 4
        for fid, _ in _INFO_FIELDS:
            f_w = 34 if fid in ("Y", "P", "T", "R") else 30
            r = QRect(x, 2, f_w, 14)
            rects.append((fid, r))
            x += f_w + 3
        return rects

    # ------------------------------------------------------------------
    # Mouse events
    # ------------------------------------------------------------------
    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.LeftButton:
            # Check if double-clicking in gizmo area → reset camera
            for label, rect in self._gizmo_rects.items():
                if rect.contains(event.pos()):
                    self._snap_to_axis(label)
                    event.accept()
                    return
            self.frame_object()
            event.accept()
        else:
            super().mouseDoubleClickEvent(event)

    def frame_object(self):
        """Reset view to cleanly frame the object."""
        self.camera.pan_x = 0.0
        self.camera.pan_y = 0.0
        self.camera.roll  = 0.0
        self.camera.tilt  = 0.0
        if self.mesh and self.mesh.vertices:
            min_x = min_y = min_z = float('inf')
            max_x = max_y = max_z = float('-inf')
            mat = self.object_transform.get_matrix() if hasattr(self, 'object_transform') and self.object_transform and not self.object_transform.is_identity() else None
            for v in self.mesh.vertices:
                v_t = mat.map(v) if mat else v
                vx, vy, vz = v_t.x(), v_t.y(), v_t.z()
                if vx < min_x: min_x = vx
                if vx > max_x: max_x = vx
                if vy < min_y: min_y = vy
                if vy > max_y: max_y = vy
                if vz < min_z: min_z = vz
                if vz > max_z: max_z = vz

            cx = (min_x + max_x) * 0.5
            cy = (min_y + max_y) * 0.5
            cz = (min_z + max_z) * 0.5
            self.camera.target_x = cx
            self.camera.target_y = cy
            self.camera.target_z = cz

            half_x = (max_x - min_x) * 0.5
            half_y = (max_y - min_y) * 0.5
            half_z = (max_z - min_z) * 0.5
            max_r  = max(half_x, half_y, half_z, 0.2)

            fov_rad = math.radians(max(5.0, min(160.0, self.camera.fov)) * 0.5)
            tan_fov = math.tan(fov_rad)
            aspect  = float(self.width()) / float(max(1, self.height()))

            dist_y    = half_y / tan_fov
            dist_x    = half_x / (tan_fov * max(0.1, aspect))
            dist_diag = max_r / tan_fov
            self.camera.distance = max(0.2, min(50.0, max(dist_y, dist_x, dist_diag) * 1.35))
        else:
            self.camera.target_x = 0.0
            self.camera.target_y = 0.0
            self.camera.target_z = 0.0
            self.camera.distance = 2.8

        self.camera_changed.emit()
        self.interaction_ended.emit()
        self.update()

    def _snap_to_axis(self, label):
        """Snap camera view along a world axis (like Blender numpad)."""
        label = label.upper()
        if label == "X":
            self.camera.yaw   = 90.0
            self.camera.pitch = 0.0
        elif label == "Y":
            self.camera.yaw   = 180.0
            self.camera.pitch = 89.9
        elif label == "Z":
            self.camera.yaw   = 180.0
            self.camera.pitch = 0.0
        self.camera.roll  = 0.0
        self.camera.tilt  = 0.0
        self.camera_changed.emit()
        self.interaction_ended.emit()
        self.update()

    # ------------------------------------------------------------------
    def mousePressEvent(self, event):
        pos = event.pos()
        self.last_mouse_pos = pos

        # Check gizmo axis click → snap view
        if event.button() == Qt.LeftButton and self.show_gizmo:
            for label, rect in self._gizmo_rects.items():
                if rect.contains(pos):
                    self._snap_to_axis(label)
                    event.accept()
                    return

        # Check info-bar scrub fields
        if event.button() == Qt.LeftButton:
            for fid, rect in self._get_info_field_rects():
                if rect.contains(pos):
                    self._info_scrub_field = fid
                    self._info_scrub_start_x   = pos.x()
                    self._info_scrub_start_val  = self._get_cam_field(fid)
                    self.setCursor(Qt.SizeHorCursor)
                    self.is_dragging = True
                    self.drag_button = event.button()
                    self.drag_modifiers = event.modifiers()
                    event.accept()
                    return

        # Check overlay buttons
        if event.button() == Qt.LeftButton and self.show_overlay_buttons:
            for act, sym, tip, rect in self._get_overlay_buttons():
                if rect.contains(pos):
                    self.active_overlay_action = act
                    self.overlay_drag_start    = pos
                    self.is_dragging = True
                    self.drag_button = event.button()
                    self.drag_modifiers = event.modifiers()
                    self.update()
                    event.accept()
                    return

        self.is_dragging     = True
        self.drag_button     = event.button()
        self.drag_modifiers  = event.modifiers()
        if event.button() == Qt.LeftButton and self.camera_mode == CAMERA_MODE_FIRST_PERSON:
            rad_yaw = math.radians(self.camera.yaw)
            rad_pitch = math.radians(self.camera.pitch)
            offset = QVector3D(
                self.camera.distance * math.cos(rad_pitch) * math.sin(rad_yaw),
                self.camera.distance * math.sin(rad_pitch),
                self.camera.distance * math.cos(rad_pitch) * math.cos(rad_yaw)
            )
            self._fp_eye = QVector3D(self.camera.target_x, self.camera.target_y, self.camera.target_z) + offset
        else:
            self._fp_eye = None
        super().mousePressEvent(event)

    def _get_cam_field(self, fid):
        c = self.camera
        if fid == "Y": return c.yaw
        if fid == "P": return c.pitch
        if fid == "T": return c.tilt
        if fid == "R": return c.roll
        if fid == "D": return c.distance
        if fid == "F": return c.fov
        return 0.0

    def _set_cam_field(self, fid, val):
        c = self.camera
        if fid == "Y":   c.yaw      = val % 360.0
        elif fid == "P": c.pitch    = max(-89.9, min(89.9, val))
        elif fid == "T": c.tilt     = max(-89.9, min(89.9, val))
        elif fid == "R": c.roll     = max(-180.0, min(180.0, val))
        elif fid == "D": c.distance = max(0.05, min(50.0, val))
        elif fid == "F": c.fov      = max(5.0, min(140.0, val))

    def mouseMoveEvent(self, event):
        pos = event.pos()

        # Info-bar scrub
        if self._info_scrub_field and self.is_dragging:
            dx    = pos.x() - self._info_scrub_start_x
            field = self._info_scrub_field
            speed = {
                "Y": 0.8, "P": 0.5, "T": 0.5, "R": 0.6,
                "D": 0.01 * max(0.1, self.camera.distance), "F": 0.4
            }.get(field, 0.5)
            new_val = self._info_scrub_start_val + dx * speed
            self._set_cam_field(field, new_val)
            self.camera_changed.emit()
            self.update()
            event.accept()
            return

        if not self.is_dragging:
            # Update info-bar hover highlight
            old_hover = self._info_hovered_field
            self._info_hovered_field = None
            for fid, rect in self._get_info_field_rects():
                if rect.contains(pos):
                    self._info_hovered_field = fid
                    self.setCursor(Qt.SizeHorCursor)
                    break
            else:
                self.setCursor(Qt.ArrowCursor)

            # Update overlay button hover
            old_btn_hover = self.hovered_overlay_action
            self.hovered_overlay_action = None
            if self.show_overlay_buttons:
                for act, sym, tip, rect in self._get_overlay_buttons():
                    if rect.contains(pos):
                        self.hovered_overlay_action = act
                        self.setToolTip(tip)
                        break
            if not self.hovered_overlay_action:
                self.setToolTip("")
            if old_hover != self._info_hovered_field or old_btn_hover != self.hovered_overlay_action:
                self.update()
            super().mouseMoveEvent(event)
            return

        delta = pos - self.last_mouse_pos
        dx    = delta.x()
        dy    = delta.y()
        self.last_mouse_pos = pos

        pan_mult         = -1.0 if self.invert_pan     else 1.0
        orbit_yaw_mult   = -1.0 if self.invert_orbit_x else 1.0
        orbit_pitch_mult = -1.0 if self.invert_orbit_y else 1.0

        # 0. Active Overlay Button Drag
        if self.active_overlay_action:
            if self.active_overlay_action == "orbit":
                orbit_speed = 0.5
                self.camera.yaw   = (self.camera.yaw   + dx * orbit_speed * orbit_yaw_mult) % 360.0
                self.camera.pitch = max(-89.9, min(89.9, self.camera.pitch + dy * orbit_speed * orbit_pitch_mult))
            elif self.active_overlay_action == "pan":
                pan_speed = 0.0025 * self.camera.distance
                self.camera.pan_x -= dx * pan_speed * pan_mult
                self.camera.pan_y += dy * pan_speed * pan_mult
            elif self.active_overlay_action == "zoom":
                zoom_speed = 0.005 * self.camera.distance
                self.camera.distance = max(0.05, min(100.0, self.camera.distance + (dy - dx) * zoom_speed))
            elif self.active_overlay_action == "tilt":
                tilt_speed = 0.5
                drag_delta = -dy if abs(dy) >= abs(dx) else dx
                self.camera.tilt = max(-89.9, min(89.9, self.camera.tilt + drag_delta * tilt_speed))
            elif self.active_overlay_action == "roll":
                roll_speed = 0.5
                drag_delta = dx if abs(dx) >= abs(dy) else -dy
                self.camera.roll = max(-180.0, min(180.0, self.camera.roll + drag_delta * roll_speed))
            self.camera_changed.emit()
            self.update()
            return

        mods = event.modifiers()

        # 1. Shift + Click: Adjust Light
        if (self.drag_button in (Qt.LeftButton, Qt.RightButton)) and (mods & Qt.ShiftModifier):
            self.lighting.azimuth   = (self.lighting.azimuth + dx * 0.8) % 360.0
            self.lighting.elevation = max(-85.0, min(85.0, self.lighting.elevation - dy * 0.8))
            self.camera_changed.emit()
            self.update()
            return

        # 2. Middle Click OR Alt + Left Click: Pan / Strafe
        if self.drag_button == Qt.MiddleButton or \
           (self.drag_button == Qt.LeftButton and (mods & Qt.AltModifier)):
            if self.camera_mode == CAMERA_MODE_FIRST_PERSON:
                # First Person: Strafe camera in its local view plane
                rad_yaw = math.radians(self.camera.yaw)
                rx = math.cos(rad_yaw)
                rz = -math.sin(rad_yaw)
                speed = 0.0025 * max(0.5, self.camera.distance) * pan_mult
                mx = dx * speed
                my = dy * speed
                self.camera.target_x -= rx * mx
                self.camera.target_z -= rz * mx
                self.camera.target_y += my
            else:
                pan_speed = 0.0025 * self.camera.distance
                self.camera.pan_x -= dx * pan_speed * pan_mult
                self.camera.pan_y += dy * pan_speed * pan_mult
            self.camera_changed.emit()
            self.update()
            return

        # 3. Right Click OR Ctrl + Left Click: Zoom
        if self.drag_button == Qt.RightButton or \
           (self.drag_button == Qt.LeftButton and (mods & Qt.ControlModifier)):
            zoom_speed = 0.005 * self.camera.distance
            self.camera.distance = max(0.01, min(100.0, self.camera.distance + (dy - dx) * zoom_speed))
            self.camera_changed.emit()
            self.update()
            return

        # 4. Left Click: Camera rotation / Look
        if self.drag_button == Qt.LeftButton:
            orbit_speed = 0.55
            if self.camera_mode == CAMERA_MODE_FIRST_PERSON:
                if self._fp_eye is None:
                    rad_yaw = math.radians(self.camera.yaw)
                    rad_pitch = math.radians(self.camera.pitch)
                    offset = QVector3D(
                        self.camera.distance * math.cos(rad_pitch) * math.sin(rad_yaw),
                        self.camera.distance * math.sin(rad_pitch),
                        self.camera.distance * math.cos(rad_pitch) * math.cos(rad_yaw)
                    )
                    self._fp_eye = QVector3D(self.camera.target_x, self.camera.target_y, self.camera.target_z) + offset

                # First Person: turn gaze from stationary eye position
                self.camera.yaw   = (self.camera.yaw   - dx * 0.45 * orbit_yaw_mult) % 360.0
                self.camera.pitch = max(-88.0, min(88.0, self.camera.pitch - dy * 0.45 * orbit_pitch_mult))

                new_rad_yaw = math.radians(self.camera.yaw)
                new_rad_pitch = math.radians(self.camera.pitch)
                new_offset = QVector3D(
                    self.camera.distance * math.cos(new_rad_pitch) * math.sin(new_rad_yaw),
                    self.camera.distance * math.sin(new_rad_pitch),
                    self.camera.distance * math.cos(new_rad_pitch) * math.cos(new_rad_yaw)
                )
                new_target = self._fp_eye - new_offset
                self.camera.target_x = new_target.x()
                self.camera.target_y = new_target.y()
                self.camera.target_z = new_target.z()
            elif self.camera_mode == CAMERA_MODE_TURNTABLE:
                # Turntable (Locked Up):
                # Locked upright with world +Y, pitch clamped above table [0, 85]
                self.camera.roll  = 0.0
                self.camera.tilt  = 0.0
                self.camera.yaw   = (self.camera.yaw   + dx * orbit_speed * orbit_yaw_mult) % 360.0
                self.camera.pitch = max(0.0, min(85.0, self.camera.pitch + dy * orbit_speed * orbit_pitch_mult))
            else:  # Orbit Around Object / Target
                if self.orbit_target_mode == ORBIT_TARGET_VIEW_CENTER:
                    if abs(self.camera.pan_x) > 1e-4 or abs(self.camera.pan_y) > 1e-4:
                        self._apply_orbit_target_mode()
                self.camera.yaw   = (self.camera.yaw   + dx * orbit_speed * orbit_yaw_mult) % 360.0
                self.camera.pitch = max(-89.9, min(89.9, self.camera.pitch + dy * orbit_speed * orbit_pitch_mult))
            self.camera_changed.emit()
            self.update()
            return

        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self._fp_eye = None
        # End info-bar scrub
        if self._info_scrub_field:
            self._info_scrub_field = None
            self.setCursor(Qt.ArrowCursor)
            self.is_dragging  = False
            self.drag_button  = None
            self.interaction_ended.emit()
            event.accept()
            return

        if self.active_overlay_action:
            move_dist = (event.pos() - self.overlay_drag_start).manhattanLength()
            if move_dist < 4:
                if self.active_overlay_action == "orbit":
                    self.camera.set_three_quarter()
                elif self.active_overlay_action == "pan":
                    self.camera.pan_x = 0.0
                    self.camera.pan_y = 0.0
                elif self.active_overlay_action == "zoom":
                    self.frame_object()
                elif self.active_overlay_action == "tilt":
                    self.camera.tilt = 0.0
                elif self.active_overlay_action == "roll":
                    self.camera.roll = 0.0
                self.camera_changed.emit()

            self.active_overlay_action = None
            self.is_dragging  = False
            self.drag_button  = None
            self.interaction_ended.emit()
            self.update()
            super().mouseReleaseEvent(event)
            return

        if self.is_dragging:
            self.is_dragging = False
            self.drag_button = None
            self.interaction_ended.emit()
        super().mouseReleaseEvent(event)

    def leaveEvent(self, event):
        if self.hovered_overlay_action or self._info_hovered_field:
            self.hovered_overlay_action = None
            self._info_hovered_field    = None
            self.setCursor(Qt.ArrowCursor)
            self.setToolTip("")
            self.update()
        super().leaveEvent(event)

    def wheelEvent(self, event):
        """Scroll wheel → zoom or walk forward/backward in First Person."""
        event.accept()
        angle = event.angleDelta().y()
        if angle == 0:
            return
        if self.camera_mode == CAMERA_MODE_FIRST_PERSON:
            # Walk forward / backward along look direction in First Person mode
            rad_yaw = math.radians(self.camera.yaw)
            rad_pitch = math.radians(self.camera.pitch)
            look_x = -math.cos(rad_pitch) * math.sin(rad_yaw)
            look_y = -math.sin(rad_pitch)
            look_z = -math.cos(rad_pitch) * math.cos(rad_yaw)
            step = (0.25 if angle > 0 else -0.25) * max(0.4, self.camera.distance * 0.15)
            self.camera.target_x += look_x * step
            self.camera.target_y += look_y * step
            self.camera.target_z += look_z * step
        else:
            # Faster zoom: use distance scaling for natural feel
            zoom_factor = 0.12 if angle > 0 else -0.12
            self.camera.distance = max(0.01, min(50.0, self.camera.distance * (1.0 - zoom_factor)))
            self.fov_changed.emit(self.camera.fov)
        self.camera_changed.emit()
        self.interaction_ended.emit()
        self.update()

    # ------------------------------------------------------------------
    # Paint
    # ------------------------------------------------------------------
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)

        w = self.width()
        h = self.height()

        # 1. Background (gradient or solid)
        if getattr(self, 'bg_use_gradient', True):
            bg_grad = QLinearGradient(0, 0, 0, h)
            bg_grad.setColorAt(0.0, self.bg_color_top)
            bg_grad.setColorAt(1.0, self.bg_color_bottom)
            painter.fillRect(0, 0, w, h, bg_grad)
        else:
            painter.fillRect(0, 0, w, h, self.bg_color_top)

        # 2. Canvas framing guide and render area
        rw, rh = w, h
        trans_x, trans_y = 0, 0
        if getattr(self, 'show_canvas_frame', True) and self.canvas_aspect_ratio and self.canvas_aspect_ratio > 0:
            view_ratio = float(w) / float(h) if h > 0 else 1.0
            if view_ratio > self.canvas_aspect_ratio:
                fw = int(h * self.canvas_aspect_ratio)
                fx = (w - fw) // 2
                frame_rect = (fx, 0, fw, h)
            else:
                fh = int(w / self.canvas_aspect_ratio)
                fy = (h - fh) // 2
                frame_rect = (0, fy, w, fh)
            fx, fy, fw, fh = frame_rect
            border_pen = QPen(
                QColor(59, 130, 246, 210) if self.scene_frame else QColor(90, 98, 115, 170),
                1.5 if self.scene_frame else 1.0, Qt.DashLine)
            painter.setPen(border_pen)
            painter.drawRect(fx, fy, fw, fh)
            rw, rh = fw, fh
            trans_x, trans_y = fx, fy

        if trans_x != 0 or trans_y != 0:
            painter.save()
            painter.translate(trans_x, trans_y)

        # 3. Perspective grid (World ground plane at ground_y=0.0)
        ground_y = float(getattr(self.camera, 'ground_y', 0.0))
        if self.grid_settings and (self.grid_settings.show_in_viewport or self.grid_settings.enabled):
            self.renderer.render_perspective_grid(
                painter, self.camera, self.grid_settings, rw, rh, ground_y=ground_y)

        # 4. 3D Model
        if self.mesh:
            obj_xform = self.object_transform if hasattr(self, 'object_transform') else None
            self.renderer.render_scene(
                painter, self.mesh, self.camera, self.lighting,
                self.render_style, rw, rh, object_transform=obj_xform)
        elif not (self.grid_settings and (self.grid_settings.show_in_viewport or self.grid_settings.enabled)):
            painter.setPen(QColor(180, 190, 205))
            painter.setFont(QFont("Segoe UI", 9))
            painter.drawText(QRect(0, 0, rw, rh), Qt.AlignCenter, "No 3D Model\n\nImport .obj / .glb / .stl")

        if trans_x != 0 or trans_y != 0:
            painter.restore()

        # 5. Coordinate Gizmo (bottom-left) with axis click detection (compact)
        self._gizmo_rects = {}
        if getattr(self, 'show_gizmo', True):
            gizmo_size = min(14, max(8, int(min(w, h) * 0.08)))
            if gizmo_size >= 7:
                ox = gizmo_size + 4
                oy = h - gizmo_size - 4
                self._draw_gizmo_with_hit_rects(painter, ox, oy, gizmo_size)

        # 6. Info overlay (top-left) with scrub highlights
        if getattr(self, 'show_top_labels', True) and (self.mesh or (self.grid_settings and (self.grid_settings.enabled or self.grid_settings.show_in_viewport))) and w > 80 and h > 40:
            self._draw_info_bar(painter)

        # 7. Overlay nav buttons (right side)
        if getattr(self, 'show_overlay_buttons', True):
            buttons = self._get_overlay_buttons()
            if buttons:
                btn_font = QFont("Segoe UI", 8)
                btn_font.setBold(True)
                painter.setFont(btn_font)
                for act, sym, tip, rect in buttons:
                    is_active = (self.active_overlay_action == act)
                    is_hover  = (self.hovered_overlay_action == act)
                    if is_active:
                        bg = QColor(29, 78, 216, 230); border = QColor(147, 197, 253)
                    elif is_hover:
                        bg = QColor(37, 99, 235, 200); border = QColor(96, 165, 250)
                    else:
                        bg = QColor(30, 34, 45, 190);  border = QColor(67, 73, 88, 180)
                    painter.setBrush(QBrush(bg))
                    painter.setPen(QPen(border, 1))
                    painter.drawRoundedRect(rect, 3, 3)
                    painter.setPen(QColor(241, 245, 249) if (is_hover or is_active) else QColor(203, 213, 225))
                    painter.drawText(rect, Qt.AlignCenter, sym)

        painter.end()

    def _draw_info_bar(self, painter):
        """Draw scrub-able info bar at top-left with Y/P/T/R/D/F labels."""
        c = self.camera
        fields = [
            ("Y", f"{c.yaw:.0f}°"),
            ("P", f"{c.pitch:.0f}°"),
            ("T", f"{c.tilt:.0f}°"),
            ("R", f"{c.roll:.0f}°"),
            ("D", f"{c.distance:.1f}"),
            ("F", f"{c.fov:.0f}°"),
        ]
        font_size = max(7, min(8, int(self.width() * 0.038)))
        painter.setFont(QFont("Segoe UI", font_size))

        for (fid, val), (_, rect) in zip(fields, self._get_info_field_rects()):
            is_hovered = (self._info_hovered_field == fid)
            is_scrubbing = (self._info_scrub_field == fid)

            # Background pill for hovered/active
            if is_hovered or is_scrubbing:
                painter.setBrush(QBrush(QColor(37, 99, 235, 180)))
                painter.setPen(Qt.NoPen)
                painter.drawRoundedRect(rect, 2, 2)
                painter.setPen(QColor(255, 255, 255))
            else:
                painter.setPen(QColor(190, 200, 215, 190))

            text = f"{fid}:{val}"
            painter.drawText(rect.adjusted(1, 1, 0, 0), Qt.AlignLeft | Qt.AlignVCenter, text)

    def _draw_gizmo_with_hit_rects(self, painter, ox, oy, size):
        """Draw coordinate gizmo AND store per-axis click rects (compact)."""
        import math as _math
        from PyQt5.QtGui import QVector4D, QFont as _QFont

        _, view_mat, _ = self.camera.get_matrices(100, 100)

        vx = view_mat * QVector4D(1, 0, 0, 0)
        vy = view_mat * QVector4D(0, 1, 0, 0)
        vz = view_mat * QVector4D(0, 0, 1, 0)

        axes = [
            (vx, QColor(239, 68, 68),  "X"),
            (vy, QColor(34, 197, 94),  "Y"),
            (vz, QColor(59, 130, 246), "Z"),
        ]
        axes.sort(key=lambda item: item[0].z())

        painter.save()
        painter.setRenderHint(QPainter.Antialiasing, True)

        # Underlay circle (compact)
        painter.setBrush(QBrush(QColor(15, 18, 25, 180)))
        painter.setPen(QPen(QColor(50, 56, 70), 1))
        painter.drawEllipse(ox - size - 1, oy - size - 1, (size + 1) * 2, (size + 1) * 2)

        lbl_font = QFont("Segoe UI", 6, QFont.Bold)

        self._gizmo_rects = {}
        for vec, color, label in axes:
            end_x = ox + vec.x() * size
            end_y = oy - vec.y() * size

            painter.setPen(QPen(color, 1.5, Qt.SolidLine, Qt.RoundCap))
            painter.drawLine(ox, oy, int(end_x), int(end_y))

            # Label — draw with hover highlight if hovered
            lx = int(end_x + (2 if vec.x() >= 0 else -7))
            ly = int(end_y + (3 if vec.y() <= 0 else -2))
            label_rect = QRect(lx - 2, ly - 7, 10, 10)
            self._gizmo_rects[label] = label_rect

            painter.setFont(lbl_font)
            # Slightly brighter to indicate clickability
            bright_color = QColor(
                min(255, color.red()   + 40),
                min(255, color.green() + 40),
                min(255, color.blue()  + 40))
            painter.setPen(bright_color)
            painter.drawText(lx, ly, label)

        painter.restore()
