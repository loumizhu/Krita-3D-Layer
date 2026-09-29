"""
Custom UI widgets: CollapsibleSection and SphereLightWidget.
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
from PyQt5.QtCore import Qt, QPoint, QPointF, QRectF, QRect, pyqtSignal, QSize, QEvent


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
                # Arrow in front
                shaft_pen = QPen(QColor(251, 191, 36), 2.2)
                shaft_pen.setCapStyle(Qt.RoundCap)
                painter.setPen(shaft_pen)
                painter.drawLine(QPointF(tail_x, tail_y), QPointF(base_x, base_y))

                # Arrowhead
                painter.setPen(Qt.NoPen)
                painter.setBrush(QBrush(QColor(255, 215, 0)))
                painter.drawPolygon(QPolygonF([tip_pt, wing1, wing2]))

                # Light source marker at tail
                painter.setPen(Qt.NoPen)
                painter.setBrush(QBrush(QColor(251, 191, 36, 100)))
                painter.drawEllipse(QPointF(tail_x, tail_y), 5.5, 5.5)
                painter.setBrush(QBrush(QColor(255, 245, 200)))
                painter.drawEllipse(QPointF(tail_x, tail_y), 3.0, 3.0)
            else:
                # Arrow pointing behind sphere
                shaft_pen = QPen(QColor(148, 163, 184, 180), 1.8, Qt.DashLine)
                painter.setPen(shaft_pen)
                painter.drawLine(QPointF(tail_x, tail_y), QPointF(base_x, base_y))

                painter.setPen(Qt.NoPen)
                painter.setBrush(QBrush(QColor(148, 163, 184, 160)))
                painter.drawPolygon(QPolygonF([tip_pt, wing1, wing2]))

                # Source marker
                painter.setBrush(QBrush(QColor(148, 163, 184, 120)))
                painter.drawEllipse(QPointF(tail_x, tail_y), 3.5, 3.5)

        # Degree readout
        painter.setPen(QColor(180, 195, 215))
        font = QFont()
        font.setPixelSize(9)
        font.setBold(True)
        painter.setFont(font)
        angle_str = f"{int(self.azimuth)}° | {int(self.elevation)}°"
        painter.drawText(0, int(h - 2), w, 12, Qt.AlignHCenter | Qt.AlignBottom, angle_str)

class ScrubLabel(QLabel):
    """
    Click-and-drag label linked to a spinbox.
    Dragging left/right scrubs the linked spinbox value.
    Clicking without dragging focuses and selects all text in the spinbox for typing.
    """
    def __init__(self, text, spinbox=None, color="#38bdf8", parent=None):
        super().__init__(text, parent)
        self._spinbox = spinbox
        self._drag_start_x = None
        self._drag_start_val = 0
        self._is_dragging = False
        self.setCursor(Qt.SizeHorCursor)
        self.setStyleSheet(
            f"QLabel {{ color: {color}; font-weight: bold; font-size: 10px; }}"
            f"QLabel:hover {{ color: #7dd3fc; }}"
        )
        self.setToolTip("Drag left/right to scrub, click to type")

    def set_target(self, spinbox):
        self._spinbox = spinbox

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and self._spinbox:
            self._drag_start_x = event.globalPos().x()
            self._drag_start_val = self._spinbox.value()
            self._is_dragging = False
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._drag_start_x is not None and (event.buttons() & Qt.LeftButton) and self._spinbox:
            dx = event.globalPos().x() - self._drag_start_x
            if not self._is_dragging and abs(dx) >= 3:
                self._is_dragging = True
            if self._is_dragging:
                if hasattr(self._spinbox, "_apply_scrub_from"):
                    self._spinbox._apply_scrub_from(self._drag_start_val, dx, event.modifiers())
                elif isinstance(self._spinbox, QDoubleSpinBox):
                    step = self._spinbox.singleStep() or 0.1
                    factor = 0.2 if (event.modifiers() & Qt.ControlModifier) else (5.0 if (event.modifiers() & Qt.ShiftModifier) else 1.0)
                    delta = dx * (step / 5.0) * factor
                    self._spinbox.setValue(self._drag_start_val + delta)
                else:
                    step = self._spinbox.singleStep() or 1
                    factor = 0.2 if (event.modifiers() & Qt.ControlModifier) else (5.0 if (event.modifiers() & Qt.ShiftModifier) else 1.0)
                    delta = int(round(dx * (step / 5.0) * factor))
                    if delta == 0 and abs(dx) >= 3:
                        delta = 1 if dx > 0 else -1
                    self._spinbox.setValue(int(self._drag_start_val + delta))
                event.accept()
                return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton and self._spinbox:
            was_dragging = self._is_dragging
            self._is_dragging = False
            self._drag_start_x = None
            if was_dragging:
                event.accept()
                return
            # Click without dragging: focus and select all in the linked spinbox
            self._spinbox.setFocus()
            if hasattr(self._spinbox, 'lineEdit') and self._spinbox.lineEdit():
                self._spinbox.lineEdit().setFocus()
                self._spinbox.lineEdit().selectAll()
            event.accept()
            return
        super().mouseReleaseEvent(event)


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
        self.setCursor(Qt.SizeHorCursor)
        self._drag_start_x = None
        self._drag_start_val = 0
        self._is_dragging = False
        if self.lineEdit():
            self.lineEdit().setCursor(Qt.SizeHorCursor)
            self.lineEdit().installEventFilter(self)

    def eventFilter(self, watched, event):
        if watched == self.lineEdit():
            etype = event.type()
            if etype == QEvent.MouseButtonPress:
                if event.button() == Qt.LeftButton:
                    self._drag_start_x = event.globalPos().x()
                    self._drag_start_val = self.value()
                    self._is_dragging = False
                    return True
            elif etype == QEvent.MouseMove:
                if self._drag_start_x is not None and (event.buttons() & Qt.LeftButton):
                    dx = event.globalPos().x() - self._drag_start_x
                    if not self._is_dragging and abs(dx) >= 3:
                        self._is_dragging = True
                        self.setCursor(Qt.SizeHorCursor)
                        self.lineEdit().setCursor(Qt.SizeHorCursor)
                    if self._is_dragging:
                        self._apply_scrub_from(self._drag_start_val, dx, event.modifiers())
                        return True
            elif etype == QEvent.MouseButtonRelease:
                if event.button() == Qt.LeftButton and self._drag_start_x is not None:
                    was_dragging = self._is_dragging
                    self._is_dragging = False
                    self._drag_start_x = None
                    if was_dragging:
                        self.setCursor(Qt.SizeHorCursor)
                        self.lineEdit().setCursor(Qt.SizeHorCursor)
                        return True
                    else:
                        self.lineEdit().setFocus()
                        self.lineEdit().selectAll()
                        self.lineEdit().setCursor(Qt.IBeamCursor)
                        return True
            elif etype == QEvent.FocusOut:
                self.lineEdit().setCursor(Qt.SizeHorCursor)
            elif etype == QEvent.Enter:
                if not self.lineEdit().hasFocus():
                    self.lineEdit().setCursor(Qt.SizeHorCursor)
            elif etype == QEvent.Leave:
                if not self._is_dragging and not self.lineEdit().hasFocus():
                    self.lineEdit().unsetCursor()
        return super().eventFilter(watched, event)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_start_x = event.globalPos().x()
            self._drag_start_val = self.value()
            self._is_dragging = False
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._drag_start_x is not None and (event.buttons() & Qt.LeftButton):
            dx = event.globalPos().x() - self._drag_start_x
            if not self._is_dragging and abs(dx) >= 3:
                self._is_dragging = True
                self.setCursor(Qt.SizeHorCursor)
            if self._is_dragging:
                self._apply_scrub_from(self._drag_start_val, dx, event.modifiers())
                event.accept()
                return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton and self._drag_start_x is not None:
            was_dragging = self._is_dragging
            self._is_dragging = False
            self._drag_start_x = None
            if was_dragging:
                self.setCursor(Qt.SizeHorCursor)
                event.accept()
                return
            if self.lineEdit():
                self.lineEdit().setFocus()
                self.lineEdit().selectAll()
                self.lineEdit().setCursor(Qt.IBeamCursor)
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def _apply_scrub_from(self, start_val, dx, modifiers):
        step = self.singleStep() or 1
        factor = 0.2 if (modifiers & Qt.ControlModifier) else (5.0 if (modifiers & Qt.ShiftModifier) else 1.0)
        delta = int(round(dx * (step / 5.0) * factor))
        if delta == 0 and abs(dx) >= 3:
            delta = 1 if dx > 0 else -1
        new_val = min(self.maximum(), max(self.minimum(), int(start_val + delta)))
        self.setValue(new_val)


class ScrubbableDoubleSpinBox(QDoubleSpinBox):
    """
    Double numeric spinbox supporting click-to-type AND click-and-drag horizontal scrubbing.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setButtonSymbols(QAbstractSpinBox.NoButtons)
        self.setAlignment(Qt.AlignCenter)
        self.setCursor(Qt.SizeHorCursor)
        self._drag_start_x = None
        self._drag_start_val = 0.0
        self._is_dragging = False
        if self.lineEdit():
            self.lineEdit().setCursor(Qt.SizeHorCursor)
            self.lineEdit().installEventFilter(self)

    def eventFilter(self, watched, event):
        if watched == self.lineEdit():
            etype = event.type()
            if etype == QEvent.MouseButtonPress:
                if event.button() == Qt.LeftButton:
                    self._drag_start_x = event.globalPos().x()
                    self._drag_start_val = self.value()
                    self._is_dragging = False
                    return True
            elif etype == QEvent.MouseMove:
                if self._drag_start_x is not None and (event.buttons() & Qt.LeftButton):
                    dx = event.globalPos().x() - self._drag_start_x
                    if not self._is_dragging and abs(dx) >= 3:
                        self._is_dragging = True
                        self.setCursor(Qt.SizeHorCursor)
                        self.lineEdit().setCursor(Qt.SizeHorCursor)
                    if self._is_dragging:
                        self._apply_scrub_from(self._drag_start_val, dx, event.modifiers())
                        return True
            elif etype == QEvent.MouseButtonRelease:
                if event.button() == Qt.LeftButton and self._drag_start_x is not None:
                    was_dragging = self._is_dragging
                    self._is_dragging = False
                    self._drag_start_x = None
                    if was_dragging:
                        self.setCursor(Qt.SizeHorCursor)
                        self.lineEdit().setCursor(Qt.SizeHorCursor)
                        return True
                    else:
                        self.lineEdit().setFocus()
                        self.lineEdit().selectAll()
                        self.lineEdit().setCursor(Qt.IBeamCursor)
                        return True
            elif etype == QEvent.FocusOut:
                self.lineEdit().setCursor(Qt.SizeHorCursor)
            elif etype == QEvent.Enter:
                if not self.lineEdit().hasFocus():
                    self.lineEdit().setCursor(Qt.SizeHorCursor)
            elif etype == QEvent.Leave:
                if not self._is_dragging and not self.lineEdit().hasFocus():
                    self.lineEdit().unsetCursor()
        return super().eventFilter(watched, event)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_start_x = event.globalPos().x()
            self._drag_start_val = self.value()
            self._is_dragging = False
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._drag_start_x is not None and (event.buttons() & Qt.LeftButton):
            dx = event.globalPos().x() - self._drag_start_x
            if not self._is_dragging and abs(dx) >= 3:
                self._is_dragging = True
                self.setCursor(Qt.SizeHorCursor)
            if self._is_dragging:
                self._apply_scrub_from(self._drag_start_val, dx, event.modifiers())
                event.accept()
                return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton and self._drag_start_x is not None:
            was_dragging = self._is_dragging
            self._is_dragging = False
            self._drag_start_x = None
            if was_dragging:
                self.setCursor(Qt.SizeHorCursor)
                event.accept()
                return
            if self.lineEdit():
                self.lineEdit().setFocus()
                self.lineEdit().selectAll()
                self.lineEdit().setCursor(Qt.IBeamCursor)
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def _apply_scrub_from(self, start_val, dx, modifiers):
        step = self.singleStep() or 0.1
        factor = 0.2 if (modifiers & Qt.ControlModifier) else (5.0 if (modifiers & Qt.ShiftModifier) else 1.0)
        delta = dx * (step / 5.0) * factor
        new_val = min(self.maximum(), max(self.minimum(), start_val + delta))
        self.setValue(new_val)


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


class PositionGizmoWidget(QWidget):
    """
    Interactive 3D Position / Translation Gizmo widget.
    Shows an isometric 3D coordinate cross:
      - X Axis (Red)
      - Y Axis (Green)
      - Z Axis (Blue)
    Allows click-and-drag interaction:
      - Drag X/Y moves position in screen-plane.
      - Shift + drag moves Z axis (depth).
      - Double-click resets position to (0, 0, 0).
    """
    position_changed = pyqtSignal(float, float, float)
    interaction_ended = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(48, 48)
        self.setMaximumSize(68, 68)
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)
        self.setMouseTracking(True)
        self.setToolTip("3D Position Gizmo\n• Drag to move X & Y\n• Shift+Drag to move Z\n• Double-click to reset (0, 0, 0)")

        self.pos_x = 0.0
        self.pos_y = 0.0
        self.pos_z = 0.0

        self.is_dragging = False
        self.last_mouse_pos = QPoint()
        self._hover_axis = None

    def sizeHint(self):
        return QSize(58, 58)

    def set_position(self, x, y, z):
        self.pos_x = float(x)
        self.pos_y = float(y)
        self.pos_z = float(z)
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

        # Sensitivity scale
        factor = 0.015
        if event.modifiers() & Qt.ShiftModifier:
            # Shift drag moves Y (Depth on grid)
            self.pos_y += -delta.y() * factor * 2.0
            self.pos_x += delta.x() * factor
        elif event.modifiers() & Qt.ControlModifier:
            factor *= 0.2
            self.pos_x += delta.x() * factor
            self.pos_z -= delta.y() * factor  # Elevation
        else:
            self.pos_x += delta.x() * factor   # Horizontal on grid
            self.pos_z -= delta.y() * factor   # Elevation

        self.position_changed.emit(self.pos_x, self.pos_y, self.pos_z)
        self.update()
        event.accept()

    def mouseReleaseEvent(self, event):
        if self.is_dragging:
            self.is_dragging = False
            self.interaction_ended.emit()
            event.accept()

    def mouseDoubleClickEvent(self, event):
        self.pos_x = 0.0
        self.pos_y = 0.0
        self.pos_z = 0.0
        self.position_changed.emit(self.pos_x, self.pos_y, self.pos_z)
        self.interaction_ended.emit()
        self.update()
        event.accept()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)

        w = self.width()
        h = self.height()
        cx = w * 0.5
        cy = h * 0.5
        radius = min(w, h) * 0.5 - 4.0

        if radius < 10.0:
            return

        # Background circular bezel
        bg_grad = QRadialGradient(cx, cy, radius, cx - radius * 0.2, cy - radius * 0.2)
        bg_grad.setColorAt(0.0, QColor(36, 42, 54))
        bg_grad.setColorAt(0.7, QColor(22, 26, 35))
        bg_grad.setColorAt(1.0, QColor(14, 17, 23))

        p.setBrush(QBrush(bg_grad))
        p.setPen(QPen(QColor(60, 72, 92), 1.0))
        p.drawEllipse(QPointF(cx, cy), radius, radius)

        # Coordinate axes (isometric 3D: Z up, X right/down, Y left/down)
        axis_len = radius * 0.72

        # Z Axis (Blue, pointing up: angle -90°) - Elevation
        z_tip = QPointF(cx, cy - axis_len)
        p.setPen(QPen(QColor(59, 130, 246), 2.0, Qt.SolidLine, Qt.RoundCap))
        p.drawLine(QPointF(cx, cy), z_tip)
        p.setPen(Qt.NoPen); p.setBrush(QBrush(QColor(96, 165, 250)))
        p.drawEllipse(z_tip, 2.5, 2.5)

        # X Axis (Red, pointing down-right: angle +30°) - Grid Horizontal
        rad_x = math.radians(30.0)
        x_tip = QPointF(cx + axis_len * math.cos(rad_x), cy + axis_len * math.sin(rad_x))
        p.setPen(QPen(QColor(239, 68, 68), 2.0, Qt.SolidLine, Qt.RoundCap))
        p.drawLine(QPointF(cx, cy), x_tip)
        p.setPen(Qt.NoPen); p.setBrush(QBrush(QColor(248, 113, 113)))
        p.drawEllipse(x_tip, 2.5, 2.5)

        # Y Axis (Green, pointing down-left: angle +150°) - Grid Depth
        rad_y = math.radians(150.0)
        y_tip = QPointF(cx + axis_len * math.cos(rad_y), cy + axis_len * math.sin(rad_y))
        p.setPen(QPen(QColor(34, 197, 94), 2.0, Qt.SolidLine, Qt.RoundCap))
        p.drawLine(QPointF(cx, cy), y_tip)
        p.setPen(Qt.NoPen); p.setBrush(QBrush(QColor(74, 222, 128)))
        p.drawEllipse(y_tip, 2.5, 2.5)

        # Center hub / origin dot
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(QColor(254, 240, 138)))
        p.drawEllipse(QPointF(cx, cy), 3.0, 3.0)

        # Small axis label letters
        font = QFont("Segoe UI", 7)
        font.setBold(True)
        p.setFont(font)
        p.setPen(QColor(96, 165, 250))
        p.drawText(int(cx - 3), int(cy - axis_len - 1), "Z")
        p.setPen(QColor(248, 113, 113))
        p.drawText(int(x_tip.x() + 1), int(x_tip.y() + 4), "X")
        p.setPen(QColor(74, 222, 128))
        p.drawText(int(y_tip.x() - 6), int(y_tip.y() + 4), "Y")

        # Subtle value indicator text at bottom
        p.setPen(QColor(148, 163, 184, 180))
        p.setFont(QFont("Segoe UI", 6))
        p.drawText(0, int(h - 1), w, 8, Qt.AlignHCenter | Qt.AlignBottom, "POS")
        p.end()


class RotationGizmoWidget(QWidget):
    """
    Interactive 3D Rotation Gizmo widget.
    Renders a shaded 3D trackball sphere with 3 gimbal rings:
      - Pitch (Red X-ring)
      - Yaw (Green Y-ring)
      - Roll (Blue Z-ring)
    Allows click-and-drag interaction:
      - Horizontal drag rotates Yaw (Y).
      - Vertical drag rotates Pitch (X).
      - Shift + drag rotates Roll (Z).
      - Double-click resets rotation to (0, 0, 0).
    """
    rotation_changed = pyqtSignal(float, float, float)
    interaction_ended = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(48, 48)
        self.setMaximumSize(68, 68)
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)
        self.setMouseTracking(True)
        self.setToolTip("3D Rotation Gizmo\n• Drag Left/Right: Yaw (Y)\n• Drag Up/Down: Pitch (X)\n• Shift+Drag: Roll (Z)\n• Double-click to reset (0, 0, 0)")

        self.rot_x = 0.0
        self.rot_y = 0.0
        self.rot_z = 0.0

        self.is_dragging = False
        self.last_mouse_pos = QPoint()

    def sizeHint(self):
        return QSize(58, 58)

    def set_rotation(self, rx, ry, rz):
        self.rot_x = float(rx)
        self.rot_y = float(ry)
        self.rot_z = float(rz)
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

        if event.modifiers() & Qt.ShiftModifier:
            # Shift drag rotates Roll (Z)
            self.rot_z = (self.rot_z + delta.x() * 1.5) % 360.0
        else:
            self.rot_y = (self.rot_y + delta.x() * 1.5) % 360.0
            self.rot_x = (self.rot_x - delta.y() * 1.5) % 360.0

        self.rotation_changed.emit(self.rot_x, self.rot_y, self.rot_z)
        self.update()
        event.accept()

    def mouseReleaseEvent(self, event):
        if self.is_dragging:
            self.is_dragging = False
            self.interaction_ended.emit()
            event.accept()

    def mouseDoubleClickEvent(self, event):
        self.rot_x = 0.0
        self.rot_y = 0.0
        self.rot_z = 0.0
        self.rotation_changed.emit(self.rot_x, self.rot_y, self.rot_z)
        self.interaction_ended.emit()
        self.update()
        event.accept()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)

        w = self.width()
        h = self.height()
        cx = w * 0.5
        cy = h * 0.5
        radius = min(w, h) * 0.5 - 5.0

        if radius < 10.0:
            return

        # 3D Shaded Trackball Body
        sphere_grad = QRadialGradient(cx - radius * 0.3, cy - radius * 0.3, radius * 1.3)
        sphere_grad.setColorAt(0.0, QColor(70, 80, 100))
        sphere_grad.setColorAt(0.4, QColor(32, 38, 50))
        sphere_grad.setColorAt(0.85, QColor(16, 20, 28))
        sphere_grad.setColorAt(1.0, QColor(10, 12, 18))

        p.setBrush(QBrush(sphere_grad))
        p.setPen(QPen(QColor(55, 65, 85), 1.0))
        p.drawEllipse(QPointF(cx, cy), radius, radius)

        # Draw 3 Colored Rotation Gimbal Rings
        # 1. Blue outer rim ring (Roll / Z)
        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(QColor(59, 130, 246, 200), 1.4))
        p.drawEllipse(QPointF(cx, cy), radius * 0.94, radius * 0.94)

        # 2. Green equator ring (Yaw / Y)
        # Flattened ellipse tilted with pitch
        p.setPen(QPen(QColor(34, 197, 94, 210), 1.5))
        pitch_rad = math.radians(self.rot_x)
        y_squash = max(0.12, abs(math.cos(pitch_rad)))
        p.drawEllipse(QPointF(cx, cy), radius * 0.82, radius * 0.82 * y_squash)

        # 3. Red meridian ring (Pitch / X)
        p.setPen(QPen(QColor(239, 68, 68, 210), 1.5))
        yaw_rad = math.radians(self.rot_y)
        x_squash = max(0.12, abs(math.cos(yaw_rad)))
        p.drawEllipse(QPointF(cx, cy), radius * 0.82 * x_squash, radius * 0.82)

        # Center orientation axis needle (shows 3D direction)
        rad_y = math.radians(self.rot_y)
        rad_x = math.radians(self.rot_x)
        dir_x = math.cos(rad_x) * math.sin(rad_y)
        dir_y = -math.sin(rad_x)

        needle_len = radius * 0.65
        needle_tip = QPointF(cx + dir_x * needle_len, cy + dir_y * needle_len)
        p.setPen(QPen(QColor(251, 191, 36), 1.8, Qt.SolidLine, Qt.RoundCap))
        p.drawLine(QPointF(cx, cy), needle_tip)
        p.setPen(Qt.NoPen); p.setBrush(QBrush(QColor(253, 230, 138)))
        p.drawEllipse(needle_tip, 2.5, 2.5)

        # Center hub
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(QColor(241, 245, 249, 220)))
        p.drawEllipse(QPointF(cx, cy), 2.2, 2.2)

        # Label at bottom
        p.setPen(QColor(148, 163, 184, 180))
        p.setFont(QFont("Segoe UI", 6))
        p.drawText(0, int(h - 1), w, 8, Qt.AlignHCenter | Qt.AlignBottom, "ROT")
        p.end()


class ScaleGizmoWidget(QWidget):
    """
    Interactive 3D Scale Gizmo widget.
    Shows 3D scale axes ending in cubic handles:
      - X Axis (Red) with box handle
      - Y Axis (Green) with box handle
      - Z Axis (Blue) with box handle
      - Center handle (Amber) for uniform scaling
      - Dynamic wireframe bounding box visualizing scale proportions.
    Allows click-and-drag interaction:
      - Dragging scales uniformly.
      - Shift + drag scales non-uniformly.
      - Double-click resets scale to (1.0, 1.0, 1.0).
    """
    scale_changed = pyqtSignal(float, float, float)
    interaction_ended = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(48, 48)
        self.setMaximumSize(68, 68)
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)
        self.setMouseTracking(True)
        self.setToolTip("3D Scale Gizmo\n• Drag right/up to scale up, left/down to scale down\n• Shift+Drag for independent X/Y scale\n• Double-click to reset (1.0, 1.0, 1.0)")

        self.scale_x = 1.0
        self.scale_y = 1.0
        self.scale_z = 1.0

        self.is_dragging = False
        self.last_mouse_pos = QPoint()

    def sizeHint(self):
        return QSize(58, 58)

    def set_scale(self, sx, sy, sz):
        self.scale_x = max(0.01, float(sx))
        self.scale_y = max(0.01, float(sy))
        self.scale_z = max(0.01, float(sz))
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

        if event.modifiers() & Qt.ShiftModifier:
            # Shift drag scales X and Y independently
            self.scale_x = max(0.01, min(100.0, self.scale_x + delta.x() * 0.02))
            self.scale_y = max(0.01, min(100.0, self.scale_y - delta.y() * 0.02))
        else:
            # Default uniform scaling
            delta_val = (delta.x() - delta.y()) * 0.015
            factor = max(0.1, 1.0 + delta_val)
            self.scale_x = max(0.01, min(100.0, self.scale_x * factor))
            self.scale_y = max(0.01, min(100.0, self.scale_y * factor))
            self.scale_z = max(0.01, min(100.0, self.scale_z * factor))

        self.scale_changed.emit(self.scale_x, self.scale_y, self.scale_z)
        self.update()
        event.accept()

    def mouseReleaseEvent(self, event):
        if self.is_dragging:
            self.is_dragging = False
            self.interaction_ended.emit()
            event.accept()

    def mouseDoubleClickEvent(self, event):
        self.scale_x = 1.0
        self.scale_y = 1.0
        self.scale_z = 1.0
        self.scale_changed.emit(self.scale_x, self.scale_y, self.scale_z)
        self.interaction_ended.emit()
        self.update()
        event.accept()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)

        w = self.width()
        h = self.height()
        cx = w * 0.5
        cy = h * 0.5
        radius = min(w, h) * 0.5 - 4.0

        if radius < 10.0:
            return

        # Background circular bezel
        bg_grad = QRadialGradient(cx, cy, radius, cx - radius * 0.2, cy - radius * 0.2)
        bg_grad.setColorAt(0.0, QColor(36, 42, 54))
        bg_grad.setColorAt(0.7, QColor(22, 26, 35))
        bg_grad.setColorAt(1.0, QColor(14, 17, 23))

        p.setBrush(QBrush(bg_grad))
        p.setPen(QPen(QColor(60, 72, 92), 1.0))
        p.drawEllipse(QPointF(cx, cy), radius, radius)

        # Scale proportion wireframe box preview
        # Normalized between 0.3 and 1.6
        avg_scale = (self.scale_x + self.scale_y + self.scale_z) / 3.0
        box_hw = max(4.0, min(radius * 0.75, radius * 0.35 * (self.scale_x / max(0.1, avg_scale))))
        box_hh = max(4.0, min(radius * 0.75, radius * 0.35 * (self.scale_z / max(0.1, avg_scale))))

        p.setPen(QPen(QColor(245, 158, 11, 80), 1.0, Qt.DashLine))
        p.setBrush(QBrush(QColor(245, 158, 11, 20)))
        p.drawRect(QRectF(cx - box_hw, cy - box_hh, box_hw * 2, box_hh * 2))

        # 3 Scale Axes with Cubic Handles
        axis_len = radius * 0.68

        # Z Axis (Blue, pointing up) - Elevation Height
        z_tip = QPointF(cx, cy - axis_len)
        p.setPen(QPen(QColor(59, 130, 246), 2.0, Qt.SolidLine, Qt.RoundCap))
        p.drawLine(QPointF(cx, cy), z_tip)
        p.setPen(Qt.NoPen); p.setBrush(QBrush(QColor(96, 165, 250)))
        p.drawRect(QRectF(z_tip.x() - 2.5, z_tip.y() - 2.5, 5, 5))

        # X Axis (Red, pointing down-right: 30°) - Grid Horizontal Width
        rad_x = math.radians(30.0)
        x_tip = QPointF(cx + axis_len * math.cos(rad_x), cy + axis_len * math.sin(rad_x))
        p.setPen(QPen(QColor(239, 68, 68), 2.0, Qt.SolidLine, Qt.RoundCap))
        p.drawLine(QPointF(cx, cy), x_tip)
        p.setPen(Qt.NoPen); p.setBrush(QBrush(QColor(248, 113, 113)))
        p.drawRect(QRectF(x_tip.x() - 2.5, x_tip.y() - 2.5, 5, 5))

        # Y Axis (Green, pointing down-left: 150°) - Grid Depth
        rad_y = math.radians(150.0)
        y_tip = QPointF(cx + axis_len * math.cos(rad_y), cy + axis_len * math.sin(rad_y))
        p.setPen(QPen(QColor(34, 197, 94), 2.0, Qt.SolidLine, Qt.RoundCap))
        p.drawLine(QPointF(cx, cy), y_tip)
        p.setPen(Qt.NoPen); p.setBrush(QBrush(QColor(74, 222, 128)))
        p.drawRect(QRectF(y_tip.x() - 2.5, y_tip.y() - 2.5, 5, 5))

        # Center uniform scale cube
        p.setPen(QPen(QColor(254, 240, 138), 1.0))
        p.setBrush(QBrush(QColor(245, 158, 11)))
        p.drawRect(QRectF(cx - 3.0, cy - 3.0, 6.0, 6.0))

        # Label at bottom
        p.setPen(QColor(148, 163, 184, 180))
        p.setFont(QFont("Segoe UI", 6))
        p.drawText(0, int(h - 1), w, 8, Qt.AlignHCenter | Qt.AlignBottom, "SCALE")
        p.end()


