"""
widgets.py - Custom UI widgets for Krita 3D Layer plugin.
Includes:
- CollapsibleSection: Elegant expandable/collapsible parameter section.
- SphereLightWidget: Interactive 3D sphere with 3D directional arrow for intuitive light control.
"""

import math
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QFrame, QSizePolicy, QSpinBox, QDoubleSpinBox, QAbstractSpinBox
)
from PyQt5.QtGui import (
    QPainter, QColor, QPen, QBrush, QRadialGradient,
    QPolygonF, QFont, QPainterPath
)
from PyQt5.QtCore import Qt, QPoint, QPointF, pyqtSignal, QSize


class CollapsibleSection(QWidget):
    """
    Collapsible section container with an arrow toggle and styled header.
    Can be expanded or collapsed to save vertical docker space.
    """
    toggled = pyqtSignal(bool)

    def __init__(self, title="", expanded=True, parent=None):
        super().__init__(parent)
        self.title_text = title
        self._expanded = expanded

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 2, 0, 2)
        main_layout.setSpacing(0)

        # Header Toggle Button
        self.header_btn = QPushButton()
        self.header_btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.header_btn.setFixedHeight(20)
        self.header_btn.setStyleSheet("""
            QPushButton {
                text-align: left;
                font-size: 11px;
                font-weight: bold;
                padding: 2px 6px;
                background-color: #2b2e38;
                border: 1px solid #3d4352;
                border-radius: 3px;
                color: #e2e8f0;
            }
            QPushButton:hover {
                background-color: #383d4c;
                border-color: #4b5568;
                color: #ffffff;
            }
            QPushButton:pressed {
                background-color: #22252e;
            }
        """)
        self.header_btn.clicked.connect(self.toggle)
        main_layout.addWidget(self.header_btn)

        # Content Container Frame
        self.content_frame = QFrame()
        self.content_frame.setStyleSheet("""
            QFrame {
                background-color: rgba(28, 30, 37, 0.45);
                border-left: 1px solid #323744;
                border-right: 1px solid #323744;
                border-bottom: 1px solid #323744;
                border-bottom-left-radius: 3px;
                border-bottom-right-radius: 3px;
            }
        """)
        self.content_layout = QVBoxLayout(self.content_frame)
        self.content_layout.setContentsMargins(2, 2, 2, 2)
        self.content_layout.setSpacing(2)
        main_layout.addWidget(self.content_frame)

        self._update_header()
        self.content_frame.setVisible(self._expanded)

    def _update_header(self):
        arrow = "▼" if self._expanded else "▶"
        self.header_btn.setText(f"{arrow}  {self.title_text}")

    def toggle(self):
        self.set_expanded(not self._expanded)

    def set_expanded(self, expanded):
        self._expanded = bool(expanded)
        self.content_frame.setVisible(self._expanded)
        self._update_header()
        self.toggled.emit(self._expanded)

    def is_expanded(self):
        return self._expanded

    def add_widget(self, widget):
        self.content_layout.addWidget(widget)

    def add_layout(self, layout):
        self.content_layout.addLayout(layout)


class SphereLightWidget(QWidget):
    """
    Interactive 3D Sphere widget with 3D directional arrow indicator.
    Allows clicking & dragging anywhere on the sphere to orbit the light direction.
    Renders real-time 3D specular highlight, globe guide rings, and a 3D arrow orbiting the sphere.
    """
    light_changed = pyqtSignal(float, float)   # (azimuth, elevation)
    interaction_ended = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(50, 50)
        self.setMaximumSize(100, 100)
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)
        self.setMouseTracking(True)
        self.setToolTip("Drag on 3D sphere to aim light in 3D\nDouble-click to reset")

        self.azimuth = 45.0      # 0 to 360 degrees
        self.elevation = 40.0    # -85 to +85 degrees

        self.is_dragging = False
        self.last_mouse_pos = QPoint()

    def sizeHint(self):
        return QSize(90, 90)

    def set_light(self, azimuth, elevation):
        self.azimuth = float(azimuth) % 360.0
        self.elevation = max(-85.0, min(85.0, float(elevation)))
        self.update()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.is_dragging = True
            self.last_mouse_pos = event.pos()
            event.accept()

    def mouseMoveEvent(self, event):
        if not self.is_dragging:
            return

        delta = event.pos() - self.last_mouse_pos
        self.last_mouse_pos = event.pos()

        # Dragging adjusts azimuth (X) and elevation (Y)
        self.azimuth = (self.azimuth + delta.x() * 1.5) % 360.0
        self.elevation = max(-85.0, min(85.0, self.elevation - delta.y() * 1.5))

        self.light_changed.emit(self.azimuth, self.elevation)
        self.update()
        event.accept()

    def mouseReleaseEvent(self, event):
        if self.is_dragging:
            self.is_dragging = False
            self.interaction_ended.emit()
            event.accept()

    def mouseDoubleClickEvent(self, event):
        # Reset to default studio key light angle
        self.azimuth = 45.0
        self.elevation = 40.0
        self.light_changed.emit(self.azimuth, self.elevation)
        self.interaction_ended.emit()
        self.update()
        event.accept()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)

        w = self.width()
        h = self.height()
        cx = w * 0.5
        cy = h * 0.5
        radius = min(w, h) * 0.5 - 13.0

        if radius < 12.0:
            return

        # 1. Calculate 3D light vector components
        rad_az = math.radians(self.azimuth)
        rad_el = math.radians(self.elevation)

        # Right-handed coordinate system in widget:
        # lx: right, ly: up (screen Y is -ly), lz: towards viewer
        lx = math.cos(rad_el) * math.sin(rad_az)
        ly = math.sin(rad_el)
        lz = math.cos(rad_el) * math.cos(rad_az)

        # 2. Draw Back-side Orbit / Arrow if light is behind sphere (lz < 0)
        is_front = (lz >= 0.0)

        # 3. Draw 3D Shaded Sphere
        # Highlight position corresponds to light direction
        hl_dist = radius * 0.65
        hl_x = cx + hl_dist * lx
        hl_y = cy - hl_dist * ly

        grad = QRadialGradient(hl_x, hl_y, radius * 1.25, hl_x, hl_y)
        if is_front:
            # Bright directional specular hotspot
            grad.setColorAt(0.00, QColor(255, 255, 255, 255))
            grad.setColorAt(0.18, QColor(255, 238, 190, 240))
            grad.setColorAt(0.50, QColor(85, 105, 130, 255))
            grad.setColorAt(0.85, QColor(32, 40, 52, 255))
            grad.setColorAt(1.00, QColor(14, 18, 26, 255))
        else:
            # Light is behind sphere, front is primarily in shadow
            rim_x = cx + radius * lx * 0.9
            rim_y = cy - radius * ly * 0.9
            grad = QRadialGradient(rim_x, rim_y, radius * 1.3, rim_x, rim_y)
            grad.setColorAt(0.00, QColor(90, 110, 140, 200))
            grad.setColorAt(0.25, QColor(45, 55, 72, 255))
            grad.setColorAt(0.70, QColor(22, 28, 38, 255))
            grad.setColorAt(1.00, QColor(10, 14, 20, 255))

        painter.setPen(QPen(QColor(60, 70, 88), 1.0))
        painter.setBrush(QBrush(grad))
        painter.drawEllipse(QPointF(cx, cy), radius, radius)

        # 4. Draw subtle 3D globe wireframe guides (latitude & longitude)
        painter.save()
        clip_path = QPainterPath()
        clip_path.addEllipse(QPointF(cx, cy), radius, radius)
        painter.setClipPath(clip_path)

        grid_pen = QPen(QColor(200, 220, 255, 38), 1.0, Qt.DotLine)
        painter.setPen(grid_pen)
        painter.setBrush(Qt.NoBrush)

        # Equator
        painter.drawEllipse(QPointF(cx, cy), radius, radius * 0.32)
        # Prime meridian
        painter.drawEllipse(QPointF(cx, cy), radius * 0.32, radius)
        # Center crosshair
        painter.drawLine(int(cx - 3), int(cy), int(cx + 3), int(cy))
        painter.drawLine(int(cx), int(cy - 3), int(cx), int(cy + 3))

        painter.restore()

        # 5. Draw 3D Light Direction Arrow around the Sphere
        tail_dist = radius + 11.0
        tip_dist = radius - 1.0

        tail_x = cx + tail_dist * lx
        tail_y = cy - tail_dist * ly

        tip_x = cx + tip_dist * lx
        tip_y = cy - tip_dist * ly

        # Vector from tail to tip
        v_dx = tip_x - tail_x
        v_dy = tip_y - tail_y
        v_len = math.sqrt(v_dx * v_dx + v_dy * v_dy)

        if v_len > 0.001:
            u_x = v_dx / v_len
            u_y = v_dy / v_len
            # Perpendicular vector
            p_x = -u_y
            p_y = u_x

            # Arrowhead coordinates
            head_len = 6.5
            head_w = 4.5
            base_x = tip_x - u_x * head_len
            base_y = tip_y - u_y * head_len

            wing1 = QPointF(base_x + p_x * head_w, base_y + p_y * head_w)
            wing2 = QPointF(base_x - p_x * head_w, base_y - p_y * head_w)
            tip_pt = QPointF(tip_x, tip_y)

            if is_front:
                # Vivid glowing golden arrow in front
                shaft_pen = QPen(QColor(251, 191, 36), 2.2)
                shaft_pen.setCapStyle(Qt.RoundCap)
                painter.setPen(shaft_pen)
                painter.drawLine(QPointF(tail_x, tail_y), QPointF(base_x, base_y))

                # Arrowhead
                painter.setPen(Qt.NoPen)
                painter.setBrush(QBrush(QColor(255, 215, 0)))
                painter.drawPolygon(QPolygonF([tip_pt, wing1, wing2]))

                # Glowing Sun / Source Marker at tail
                painter.setPen(Qt.NoPen)
                painter.setBrush(QBrush(QColor(251, 191, 36, 100)))
                painter.drawEllipse(QPointF(tail_x, tail_y), 5.5, 5.5)
                painter.setBrush(QBrush(QColor(255, 245, 200)))
                painter.drawEllipse(QPointF(tail_x, tail_y), 3.0, 3.0)
            else:
                # Dimmer dashed arrow pointing behind sphere
                shaft_pen = QPen(QColor(148, 163, 184, 180), 1.8, Qt.DashLine)
                painter.setPen(shaft_pen)
                painter.drawLine(QPointF(tail_x, tail_y), QPointF(base_x, base_y))

                painter.setPen(Qt.NoPen)
                painter.setBrush(QBrush(QColor(148, 163, 184, 160)))
                painter.drawPolygon(QPolygonF([tip_pt, wing1, wing2]))

                # Translucent source marker
                painter.setBrush(QBrush(QColor(148, 163, 184, 120)))
                painter.drawEllipse(QPointF(tail_x, tail_y), 3.5, 3.5)

        # 6. Small Degree Readout at bottom
        painter.setPen(QColor(180, 195, 215))
        font = QFont()
        font.setPixelSize(9)
        font.setBold(True)
        painter.setFont(font)
        angle_str = f"{int(self.azimuth)}° | {int(self.elevation)}°"
        painter.drawText(0, int(h - 2), w, 12, Qt.AlignHCenter | Qt.AlignBottom, angle_str)


class ScrubbableSpinBox(QSpinBox):
    """
    Numeric integer spinbox supporting click-to-type AND click-and-drag horizontal scrubbing.
    Dragging horizontally increases/decreases the value.
    Shift = 5x faster, Ctrl = 0.2x finer.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setButtonSymbols(QAbstractSpinBox.NoButtons)
        self.setAlignment(Qt.AlignCenter)
        self._drag_start_pos = None
        self._drag_start_val = 0
        self._is_dragging = False

    def enterEvent(self, event):
        if not self.hasFocus():
            self.setCursor(Qt.SizeHorCursor)
        super().enterEvent(event)

    def leaveEvent(self, event):
        if not self._is_dragging:
            self.unsetCursor()
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_start_pos = event.pos()
            self._drag_start_val = self.value()
            self._is_dragging = False
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._drag_start_pos and (event.buttons() & Qt.LeftButton):
            dx = event.pos().x() - self._drag_start_pos.x()
            if not self._is_dragging and abs(dx) >= 3:
                self._is_dragging = True
                self.setCursor(Qt.SizeHorCursor)
                if self.lineEdit():
                    self.lineEdit().deselect()
            if self._is_dragging:
                step = self.singleStep() or 1
                factor = 0.2 if (event.modifiers() & Qt.ControlModifier) else (5.0 if (event.modifiers() & Qt.ShiftModifier) else 1.0)
                delta = int(dx * (step * 0.15 * factor))
                new_val = min(self.maximum(), max(self.minimum(), self._drag_start_val + delta))
                self.setValue(new_val)
                event.accept()
                return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self._is_dragging:
            self._is_dragging = False
            self._drag_start_pos = None
            self.unsetCursor()
            event.accept()
            return
        self._drag_start_pos = None
        super().mouseReleaseEvent(event)
        # Click without dragging: select text for direct typing!
        if self.lineEdit():
            self.lineEdit().setFocus()
            self.lineEdit().selectAll()


class ScrubbableDoubleSpinBox(QDoubleSpinBox):
    """
    Double numeric spinbox supporting click-to-type AND click-and-drag horizontal scrubbing.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setButtonSymbols(QAbstractSpinBox.NoButtons)
        self.setAlignment(Qt.AlignCenter)
        self._drag_start_pos = None
        self._drag_start_val = 0.0
        self._is_dragging = False

    def enterEvent(self, event):
        if not self.hasFocus():
            self.setCursor(Qt.SizeHorCursor)
        super().enterEvent(event)

    def leaveEvent(self, event):
        if not self._is_dragging:
            self.unsetCursor()
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_start_pos = event.pos()
            self._drag_start_val = self.value()
            self._is_dragging = False
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._drag_start_pos and (event.buttons() & Qt.LeftButton):
            dx = event.pos().x() - self._drag_start_pos.x()
            if not self._is_dragging and abs(dx) >= 3:
                self._is_dragging = True
                self.setCursor(Qt.SizeHorCursor)
                if self.lineEdit():
                    self.lineEdit().deselect()
            if self._is_dragging:
                step = self.singleStep() or 0.1
                factor = 0.2 if (event.modifiers() & Qt.ControlModifier) else (5.0 if (event.modifiers() & Qt.ShiftModifier) else 1.0)
                delta = dx * (step * 0.1 * factor)
                new_val = min(self.maximum(), max(self.minimum(), self._drag_start_val + delta))
                self.setValue(new_val)
                event.accept()
                return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self._is_dragging:
            self._is_dragging = False
            self._drag_start_pos = None
            self.unsetCursor()
            event.accept()
            return
        self._drag_start_pos = None
        super().mouseReleaseEvent(event)
        # Click without dragging: select text for direct typing!
        if self.lineEdit():
            self.lineEdit().setFocus()
            self.lineEdit().selectAll()


class ViewportResizeHandle(QWidget):
    """
    Subtle horizontal splitter grip beneath the Viewport.
    Dragging up/down resizes the viewport height dynamically.
    """
    resized = pyqtSignal(int)

    def __init__(self, target_widget, min_h=60, max_h=800, parent=None):
        super().__init__(parent)
        self.target = target_widget
        self.min_h = min_h
        self.max_h = max_h
        self.setFixedHeight(8)
        self.setCursor(Qt.SplitVCursor)
        self.setToolTip("Drag down/up to resize 3D viewport height")
        self._drag_start_y = None
        self._start_h = 0

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_start_y = event.globalPos().y()
            self._start_h = self.target.height()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._drag_start_y is not None:
            dy = event.globalPos().y() - self._drag_start_y
            new_h = max(self.min_h, min(self.max_h, self._start_h + dy))
            self.target.setFixedHeight(new_h)
            self.resized.emit(new_h)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self._drag_start_y = None
        super().mouseReleaseEvent(event)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        w = self.width()
        grip_w = min(40, max(24, w // 4))
        p.setBrush(QBrush(QColor(100, 116, 139, 180)))
        p.setPen(Qt.NoPen)
        p.drawRoundedRect((w - grip_w) // 2, 2, grip_w, 3, 1.5, 1.5)
        p.end()

