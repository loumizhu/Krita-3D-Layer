"""
viewport.py - Interactive 3D Viewport Widget for Krita.
Provides smooth mouse-driven camera orbiting, panning, zooming, and light manipulation.
Scroll wheel over viewport controls FOV (focal length), not docker scroll.
Supports Orbit, First-Person, and Turntable camera modes.
"""

from PyQt5.QtWidgets import QWidget
from PyQt5.QtGui import QPainter, QColor, QPen, QBrush, QFont
from PyQt5.QtCore import Qt, QPoint, pyqtSignal
import math

from .renderer import Camera3D, Lighting3D, Renderer3D, RenderStyle


# Camera navigation modes
CAMERA_MODE_ORBIT = "Orbit Around Object"
CAMERA_MODE_FIRST_PERSON = "First Person (Look Around)"
CAMERA_MODE_TURNTABLE = "Turntable (Locked Up)"

CAMERA_MODES = [CAMERA_MODE_ORBIT, CAMERA_MODE_FIRST_PERSON, CAMERA_MODE_TURNTABLE]


class Viewport3D(QWidget):
    camera_changed = pyqtSignal()
    interaction_ended = pyqtSignal()
    fov_changed = pyqtSignal(float)   # emitted when scroll-wheel changes FOV

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setMouseTracking(True)
        self.setMinimumSize(60, 60)  # Allow very narrow dockers

        # Core 3D engine components
        self.camera = Camera3D()
        self.lighting = Lighting3D()
        self.renderer = Renderer3D()
        self.mesh = None
        self.render_style = RenderStyle.SHADED_WIREFRAME

        # Camera navigation mode
        self.camera_mode = CAMERA_MODE_ORBIT

        # Interaction state
        self.last_mouse_pos = QPoint()
        self.is_dragging = False
        self.drag_button = None
        self.drag_modifiers = Qt.NoModifier

        # Canvas framing guide
        self.canvas_aspect_ratio = None  # None or float (width / height)
        self.show_canvas_frame = True

        # Viewport background
        self.bg_color = QColor(30, 31, 35)

    def set_mesh(self, mesh):
        self.mesh = mesh
        self.update()

    def set_render_style(self, style):
        self.render_style = style
        self.update()

    def set_canvas_aspect_ratio(self, ratio):
        self.canvas_aspect_ratio = ratio
        self.update()

    def set_camera_mode(self, mode):
        self.camera_mode = mode

    def mousePressEvent(self, event):
        self.last_mouse_pos = event.pos()
        self.is_dragging = True
        self.drag_button = event.button()
        self.drag_modifiers = event.modifiers()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if not self.is_dragging:
            super().mouseMoveEvent(event)
            return

        delta = event.pos() - self.last_mouse_pos
        dx = delta.x()
        dy = delta.y()
        self.last_mouse_pos = event.pos()

        mods = event.modifiers()

        # 1. Shift + Left Click: Adjust Light direction
        if (self.drag_button == Qt.LeftButton and (mods & Qt.ShiftModifier)) or \
           (self.drag_button == Qt.RightButton and (mods & Qt.ShiftModifier)):
            self.lighting.azimuth = (self.lighting.azimuth + dx * 0.8) % 360.0
            self.lighting.elevation = max(-85.0, min(85.0, self.lighting.elevation - dy * 0.8))
            self.camera_changed.emit()
            self.update()
            return

        # 2. Middle Click OR Alt + Left Click: Pan
        if self.drag_button == Qt.MiddleButton or \
           (self.drag_button == Qt.LeftButton and (mods & Qt.AltModifier)):
            pan_speed = 0.0025 * self.camera.distance
            self.camera.pan_x += dx * pan_speed
            self.camera.pan_y -= dy * pan_speed
            self.camera_changed.emit()
            self.update()
            return

        # 3. Right Click OR Ctrl + Left Click: Zoom (distance)
        if self.drag_button == Qt.RightButton or \
           (self.drag_button == Qt.LeftButton and (mods & Qt.ControlModifier)):
            zoom_speed = 0.005 * self.camera.distance
            self.camera.distance = max(0.01, min(50.0, self.camera.distance + (dy - dx) * zoom_speed))
            self.camera_changed.emit()
            self.update()
            return

        # 4. Standard Left Click: Camera rotation (mode-dependent)
        if self.drag_button == Qt.LeftButton:
            orbit_speed = 0.6

            if self.camera_mode == CAMERA_MODE_FIRST_PERSON:
                # First person: camera stays in place, rotates view direction
                # Yaw and pitch change orientation, but distance stays constant
                self.camera.yaw = (self.camera.yaw + dx * orbit_speed) % 360.0
                self.camera.pitch = max(-89.9, min(89.9, self.camera.pitch - dy * orbit_speed))
            elif self.camera_mode == CAMERA_MODE_TURNTABLE:
                # Turntable: only yaw rotates, pitch is locked-axis vertical
                self.camera.yaw = (self.camera.yaw - dx * orbit_speed) % 360.0
                self.camera.pitch = max(-89.9, min(89.9, self.camera.pitch + dy * orbit_speed))
            else:
                # Standard Orbit: model appears to follow the mouse
                self.camera.yaw = (self.camera.yaw - dx * orbit_speed) % 360.0
                self.camera.pitch = max(-89.9, min(89.9, self.camera.pitch + dy * orbit_speed))

            self.camera_changed.emit()
            self.update()
            return

        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self.is_dragging:
            self.is_dragging = False
            self.drag_button = None
            self.interaction_ended.emit()
        super().mouseReleaseEvent(event)

    def wheelEvent(self, event):
        """Scroll wheel over viewport = change FOV (focal length), not scroll the docker."""
        # Accept the event so it doesn't propagate to parent QScrollArea
        event.accept()

        angle = event.angleDelta().y()
        if angle == 0:
            return

        # Adjust FOV: scroll up = narrower FOV (zoom in / telephoto), scroll down = wider
        fov_step = -1.5 if angle > 0 else 1.5
        new_fov = max(5.0, min(120.0, self.camera.fov + fov_step))
        self.camera.fov = new_fov
        self.fov_changed.emit(new_fov)
        self.camera_changed.emit()
        self.interaction_ended.emit()
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        
        w = self.width()
        h = self.height()

        # 1. Background fill
        painter.fillRect(0, 0, w, h, self.bg_color)

        # 2. Canvas framing guide (if aspect ratio is set)
        frame_rect = None
        if self.show_canvas_frame and self.canvas_aspect_ratio and self.canvas_aspect_ratio > 0:
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
            painter.setPen(QPen(QColor(70, 75, 85, 180), 1, Qt.DashLine))
            painter.drawRect(fx, fy, fw, fh)

        # 3. Render 3D Scene
        if self.mesh:
            self.renderer.render_scene(
                painter, self.mesh, self.camera, self.lighting,
                self.render_style, w, h
            )
        else:
            painter.setPen(QColor(130, 135, 145))
            font = QFont("Segoe UI", 9)
            painter.setFont(font)
            text = "No 3D Model\n\nImport .obj / .stl"
            painter.drawText(self.rect(), Qt.AlignCenter, text)

        # 4. Coordinate Gizmo in bottom-left
        gizmo_size = min(28, int(min(w, h) * 0.15))
        if gizmo_size >= 10:
            self.renderer.draw_coordinate_gizmo(
                painter, self.camera,
                origin_x=gizmo_size + 8, origin_y=h - gizmo_size - 8,
                size=gizmo_size
            )

        # 5. Compact info overlay
        if self.mesh and w > 80 and h > 40:
            painter.setPen(QColor(160, 165, 175, 180))
            font_size = max(7, min(8, int(w * 0.04)))
            painter.setFont(QFont("Segoe UI", font_size))
            info = f"Y:{self.camera.yaw:.0f} P:{self.camera.pitch:.0f} D:{self.camera.distance:.1f} F:{self.camera.fov:.0f}°"
            painter.drawText(4, 12, info)

        painter.end()
