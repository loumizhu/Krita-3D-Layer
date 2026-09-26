"""
ground_calibrator.py - Ground Rectangle Perspective Matcher & Camera Calibrator.
Allows artists to draw or adjust a 4-point ground rectangle directly on the canvas snapshot.
Mathematically solves camera orientation (Yaw, Pitch/Tilt, Roll, FOV, Distance, Pan X/Y)
and places the 3D model directly on top of that ground rectangle with live preview.
"""

import math
from PyQt5.QtWidgets import (
    QDialog, QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QLabel, QSizePolicy, QFrame, QCheckBox
)
from PyQt5.QtGui import (
    QPainter, QColor, QPen, QBrush, QFont, QPolygonF, QImage, QCursor,
    QVector3D, QVector4D, QMatrix4x4
)
from PyQt5.QtCore import Qt, QPointF, QRectF, pyqtSignal

from .renderer import Camera3D, Lighting3D, Renderer3D, RenderStyle


def line_equation(pa, pb):
    """Returns (A, B, C) for line A*x + B*y + C = 0."""
    A = pa.y() - pb.y()
    B = pb.x() - pa.x()
    C = pa.x() * pb.y() - pb.x() * pa.y()
    return A, B, C


def line_intersection(l1, l2):
    """Returns QPointF or None for line intersection."""
    A1, B1, C1 = l1
    A2, B2, C2 = l2
    denom = A1 * B2 - A2 * B1
    if abs(denom) < 1e-6:
        return None
    x = (B1 * C2 - B2 * C1) / denom
    y = (C1 * A2 - C2 * A1) / denom
    return QPointF(x, y)


def solve_ground_rectangle(p0, p1, p2, p3, width, height, current_fov=45.0, mesh=None, frame_rect=None,
                           keep_horizon=True, flip_yaw=False):
    """
    Solves camera parameters from 4 ground quad points (p0..p3) in document pixel space:
      p0: Front-Left
      p1: Front-Right
      p2: Back-Right
      p3: Back-Left
    Returns a dict with: yaw, pitch, roll, fov, distance, pan_x, pan_y,
    target_x, target_y, target_z, vp1, vp2, horizon, center_2d.
    """
    # 1. Coordinate Space
    if frame_rect and len(frame_rect) == 4 and frame_rect[2] > 0 and frame_rect[3] > 0:
        fx, fy, fw, fh = frame_rect
        cx = fx + fw * 0.5
        cy = fy + fh * 0.5
        render_size = float(min(fw, fh))
    else:
        w = float(width) if width > 0 else 1000.0
        h = float(height) if height > 0 else 1000.0
        cx = w * 0.5
        cy = h * 0.5
        render_size = float(min(w, h))

    half_s = render_size * 0.5

    # 2. Vanishing Points
    # Axis X (Front & Back): p0->p1 and p3->p2
    L_front = line_equation(p0, p1)
    L_back = line_equation(p3, p2)
    vp1 = line_intersection(L_front, L_back)

    # Axis Z (Left & Right): p0->p3 and p1->p2
    L_left = line_equation(p0, p3)
    L_right = line_equation(p1, p2)
    vp2 = line_intersection(L_left, L_right)

    # 3. Perspective center of quad (intersection of diagonals)
    diag1 = line_equation(p0, p2)
    diag2 = line_equation(p1, p3)
    center_2d = line_intersection(diag1, diag2)
    if not center_2d:
        center_2d = QPointF(
            (p0.x() + p1.x() + p2.x() + p3.x()) * 0.25,
            (p0.y() + p1.y() + p2.y() + p3.y()) * 0.25
        )

    # 4. Focal length and FOV recovery
    f_base = half_s / math.tan(math.radians(max(5.0, min(160.0, current_fov)) * 0.5))
    f = f_base
    solved_fov = current_fov

    if vp1 and vp2:
        u1 = (vp1.x() - cx, -(vp1.y() - cy))
        u2 = (vp2.x() - cx, -(vp2.y() - cy))
        dot = u1[0] * u2[0] + u1[1] * u2[1]
        if dot < -100.0:  # Orthogonal directions in perspective
            f_calc = math.sqrt(-dot)
            calc_fov = 2.0 * math.atan(half_s / f_calc) * 180.0 / math.pi
            if 12.0 <= calc_fov <= 120.0:
                f = f_calc
                solved_fov = calc_fov

    # 5. Ray vectors in Camera View Space (OpenGL convention: -Z is forward, +Y is up, +X is right)
    if vp1 and vp2:
        ray_X = QVector3D(vp1.x() - cx, -(vp1.y() - cy), -f).normalized()
        ray_Z = QVector3D(vp2.x() - cx, -(vp2.y() - cy), -f).normalized()
    elif vp2:
        # 1-point perspective: Front/Back lines are parallel in screen space
        ray_Z = QVector3D(vp2.x() - cx, -(vp2.y() - cy), -f).normalized()
        ray_X = QVector3D(p0.x() - p1.x(), -(p0.y() - p1.y()), 0.0).normalized()
    elif vp1:
        # Side lines are parallel in screen space
        ray_X = QVector3D(vp1.x() - cx, -(vp1.y() - cy), -f).normalized()
        ray_Z = QVector3D(p3.x() - p0.x(), -(p3.y() - p0.y()), 0.0).normalized()
    else:
        # Top-down / axonometric fallback
        ray_X = QVector3D(1.0, 0.0, 0.0)
        ray_Z = QVector3D(0.0, 0.0, -1.0)

    # Align ray directions with the model's coordinate frame:
    # Model +X (right side of model) points from Front-Right (p1) to Front-Left (p0)
    dir_2d_X = QVector3D(p0.x() - p1.x(), -(p0.y() - p1.y()), 0.0).normalized()
    if QVector3D.dotProduct(ray_X, dir_2d_X) < 0:
        ray_X = -ray_X

    dir_2d_Z = QVector3D(p3.x() - p0.x(), -(p3.y() - p0.y()), 0.0).normalized()
    if QVector3D.dotProduct(ray_Z, dir_2d_Z) < 0:
        ray_Z = -ray_Z

    # 6. Ground Normal in camera view space (pointing up: N.y > 0)
    N = QVector3D.crossProduct(ray_Z, ray_X).normalized()
    if N.y() < 0:
        N = -N

    # 7. Pitch (tilt angle up/down) and Roll (camera tilt sideways)
    pitch = math.degrees(math.atan2(N.z(), math.sqrt(N.x()**2 + N.y()**2)))
    pitch = max(-89.0, min(89.0, pitch))

    roll = -math.degrees(math.atan2(N.x(), N.y()))
    roll = max(-89.0, min(89.0, roll))
    if keep_horizon:
        roll = 0.0

    # 8. Yaw (azimuth rotation around world up)
    # Project ray_X onto horizontal basis perpendicular to N
    world_horiz_X = QVector3D(1.0, 0.0, 0.0)
    h_X = (world_horiz_X - N * QVector3D.dotProduct(world_horiz_X, N)).normalized()
    h_Z = QVector3D.crossProduct(N, h_X).normalized()

    x_prime = QVector3D.dotProduct(ray_X, h_X)
    z_prime = QVector3D.dotProduct(ray_X, h_Z)
    # Correct orientation so the front of the model faces forward towards the viewer
    yaw = (math.degrees(math.atan2(z_prime, -x_prime))) % 360.0
    if flip_yaw:
        yaw = (yaw + 180.0) % 360.0

    # 9. Model Ground Alignment & Scale
    ground_y = -1.0
    base_width = 2.0
    if mesh and hasattr(mesh, 'bbox_min') and hasattr(mesh, 'bbox_max'):
        ground_y = mesh.bbox_min.y()
        base_width = max(0.2, mesh.bbox_max.x() - mesh.bbox_min.x())

    # Target points to the base of the model on the ground
    target_x = 0.0
    target_y = ground_y
    target_z = 0.0

    # 10. Distance calculation (matches model base width to quad width)
    w01 = math.hypot(p1.x() - p0.x(), p1.y() - p0.y())
    w32 = math.hypot(p2.x() - p3.x(), p2.y() - p3.y())
    quad_w = max(5.0, (w01 + w32) * 0.5)

    # Perspective foreshortening factor for the X axis
    L_perp = max(0.15, math.sqrt(ray_X.x()**2 + ray_X.y()**2))
    dist = f * (base_width * L_perp) / quad_w
    dist = max(0.2, min(50.0, dist))

    # 11. Exact Camera Pan
    # In camera space with pre-multiplied pan:
    # sx = cx + f * (pan_x / dist)  =>  pan_x = ((sx - cx) / f) * dist
    # sy = cy - f * (pan_y / dist)  =>  pan_y = -((sy - cy) / f) * dist
    pan_x = ((center_2d.x() - cx) / f) * dist
    pan_y = -((center_2d.y() - cy) / f) * dist

    # 12. Horizon line
    horizon = None
    if keep_horizon:
        # Strictly horizontal horizon line
        if vp1 and vp2:
            avg_y = (vp1.y() + vp2.y()) * 0.5
        elif vp2:
            avg_y = vp2.y()
        elif vp1:
            avg_y = vp1.y()
        else:
            avg_y = cy - f * math.tan(math.radians(pitch))
        horizon = (0.0, 1.0, -avg_y)
    elif vp1 and vp2:
        horizon = line_equation(vp1, vp2)
    elif vp2:
        horizon = (0.0, 1.0, -vp2.y())
    elif vp1:
        horizon = (0.0, 1.0, -vp1.y())

    return {
        "yaw": yaw,
        "pitch": pitch,
        "roll": roll,
        "fov": solved_fov,
        "distance": dist,
        "pan_x": pan_x,
        "pan_y": pan_y,
        "target_x": target_x,
        "target_y": target_y,
        "target_z": target_z,
        "vp1": vp1,
        "vp2": vp2,
        "horizon": horizon,
        "center_2d": center_2d
    }


class GroundCalibratorWidget(QWidget):
    """
    Interactive canvas widget that displays the canvas snapshot, allows dragging
    the 4 ground quad corner pins, and renders a LIVE 3D PREVIEW of the model
    sitting directly on top of the ground rectangle.
    """
    solution_changed = pyqtSignal(dict)

    HANDLE_RADIUS = 8

    def __init__(self, bg_image=None, mesh=None, camera=None, lighting=None, renderer=None,
                 frame_rect=None, parent=None):
        super().__init__(parent)
        self.setMouseTracking(True)
        self.setMinimumSize(480, 360)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        self.bg_image = bg_image
        self.mesh = mesh
        self.camera = camera
        self.lighting = lighting or Lighting3D()
        self.renderer = renderer or Renderer3D()
        self.frame_rect = frame_rect

        self.active_handle = None
        self.hovered_handle = None
        self.is_picking_mode = False
        self.picked_points = []
        self.keep_horizon = True
        self.flip_yaw = False
        self.current_cursor_pos = None

        # Current image rect within widget (for letterbox/aspect mapping)
        self.img_rect = QRectF(0, 0, 480, 360)

        # 4 ground points in normalized document coordinates [0, 1]
        # P0: Front-Left, P1: Front-Right, P2: Back-Right, P3: Back-Left
        self.norm_points = [
            QPointF(0.25, 0.78),  # 0: Front-Left
            QPointF(0.75, 0.78),  # 1: Front-Right
            QPointF(0.62, 0.48),  # 2: Back-Right
            QPointF(0.38, 0.48),  # 3: Back-Left
        ]

        self.last_solution = {}
        self._recalculate()

    def set_keep_horizon(self, val):
        self.keep_horizon = bool(val)
        self._recalculate()
        self.update()

    def toggle_flip_yaw(self):
        self.flip_yaw = not self.flip_yaw
        self._recalculate()
        self.update()

    def set_canvas_image(self, qimg):
        self.bg_image = qimg
        self._recalculate()
        self.update()

    def start_pick_mode(self):
        self.is_picking_mode = True
        self.picked_points = []
        self.setCursor(Qt.CrossCursor)
        self.update()

    def reset_points(self):
        self.norm_points = [
            QPointF(0.25, 0.78),
            QPointF(0.75, 0.78),
            QPointF(0.62, 0.48),
            QPointF(0.38, 0.48),
        ]
        self.is_picking_mode = False
        self.setCursor(Qt.ArrowCursor)
        self._recalculate()
        self.update()

    def center_quad(self):
        """Centers the quad within the current canvas image."""
        self.norm_points = [
            QPointF(0.30, 0.75),
            QPointF(0.70, 0.75),
            QPointF(0.60, 0.50),
            QPointF(0.40, 0.50),
        ]
        self._recalculate()
        self.update()

    def set_from_rect(self, rx, ry, rw, rh, total_w, total_h):
        """Initializes quad from a 2D selection rectangle."""
        if total_w <= 0 or total_h <= 0 or rw <= 0 or rh <= 0:
            return
        x0 = rx / float(total_w)
        x1 = (rx + rw) / float(total_w)
        y0 = ry / float(total_h)
        y1 = (ry + rh) / float(total_h)

        mx = (x0 + x1) * 0.5
        w_half = (x1 - x0) * 0.5
        self.norm_points = [
            QPointF(x0, y1),
            QPointF(x1, y1),
            QPointF(mx + w_half * 0.75, y0),
            QPointF(mx - w_half * 0.75, y0),
        ]
        self._recalculate()
        self.update()

    def _get_doc_size(self):
        if self.bg_image and not self.bg_image.isNull():
            return float(self.bg_image.width()), float(self.bg_image.height())
        return float(max(100, self.width())), float(max(100, self.height()))

    def _get_doc_points(self):
        doc_w, doc_h = self._get_doc_size()
        return [QPointF(p.x() * doc_w, p.y() * doc_h) for p in self.norm_points]

    def _doc_to_widget(self, pt_doc):
        doc_w, doc_h = self._get_doc_size()
        if doc_w <= 0 or doc_h <= 0:
            return QPointF(pt_doc)
        wx = self.img_rect.x() + (pt_doc.x() / doc_w) * self.img_rect.width()
        wy = self.img_rect.y() + (pt_doc.y() / doc_h) * self.img_rect.height()
        return QPointF(wx, wy)

    def _widget_to_doc_norm(self, pos):
        if self.img_rect.width() <= 0 or self.img_rect.height() <= 0:
            return QPointF(0.5, 0.5)
        nx = (pos.x() - self.img_rect.x()) / self.img_rect.width()
        ny = (pos.y() - self.img_rect.y()) / self.img_rect.height()
        return QPointF(max(0.001, min(0.999, nx)), max(0.001, min(0.999, ny)))

    def _get_widget_points(self):
        return [
            QPointF(
                self.img_rect.x() + p.x() * self.img_rect.width(),
                self.img_rect.y() + p.y() * self.img_rect.height()
            )
            for p in self.norm_points
        ]

    def _recalculate(self):
        doc_pts = self._get_doc_points()
        doc_w, doc_h = self._get_doc_size()
        cur_fov = self.camera.fov if self.camera else 45.0
        self.last_solution = solve_ground_rectangle(
            doc_pts[0], doc_pts[1], doc_pts[2], doc_pts[3],
            doc_w, doc_h,
            current_fov=cur_fov,
            mesh=self.mesh,
            frame_rect=self.frame_rect,
            keep_horizon=self.keep_horizon,
            flip_yaw=self.flip_yaw
        )
        self.solution_changed.emit(self.last_solution)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape and self.is_picking_mode:
            self.is_picking_mode = False
            self.picked_points = []
            self.setCursor(Qt.ArrowCursor)
            self.update()
            event.accept()
            return
        super().keyPressEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            pos = event.pos()

            # Sequential 4-point picking mode (Draw 4 points)
            if self.is_picking_mode:
                norm_pt = self._widget_to_doc_norm(pos)
                self.picked_points.append(norm_pt)
                if len(self.picked_points) == 4:
                    self.norm_points = list(self.picked_points)
                    self.is_picking_mode = False
                    self.setCursor(Qt.ArrowCursor)
                    self._recalculate()
                self.update()
                event.accept()
                return

            # Check handle hits
            pts = self._get_widget_points()
            for idx, pt in enumerate(pts):
                dist = (pt - QPointF(pos)).manhattanLength()
                if dist <= self.HANDLE_RADIUS + 6:
                    self.active_handle = idx
                    event.accept()
                    return

        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        pos = event.pos()
        self.current_cursor_pos = pos

        if self.is_picking_mode:
            self.update()
            event.accept()
            return

        if self.active_handle is not None:
            norm_pt = self._widget_to_doc_norm(pos)
            self.norm_points[self.active_handle] = norm_pt
            self._recalculate()
            self.update()
            event.accept()
            return

        pts = self._get_widget_points()
        old_h = self.hovered_handle
        self.hovered_handle = None
        for idx, pt in enumerate(pts):
            dist = (pt - QPointF(pos)).manhattanLength()
            if dist <= self.HANDLE_RADIUS + 6:
                self.hovered_handle = idx
                self.setCursor(Qt.PointingHandCursor)
                break
        if self.hovered_handle is None:
            self.setCursor(Qt.ArrowCursor)
        if old_h != self.hovered_handle:
            self.update()

        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self.active_handle is not None:
            self.active_handle = None
            self.update()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)

        w = self.width()
        h = self.height()

        # 1. Background (canvas image snapshot or studio dark grid)
        if self.bg_image and not self.bg_image.isNull():
            scaled = self.bg_image.size().scaled(w, h, Qt.KeepAspectRatio)
            bx = (w - scaled.width()) // 2
            by = (h - scaled.height()) // 2
            self.img_rect = QRectF(bx, by, scaled.width(), scaled.height())
            painter.fillRect(0, 0, w, h, QColor(18, 20, 24))
            painter.drawImage(self.img_rect, self.bg_image)
        else:
            self.img_rect = QRectF(0, 0, w, h)
            painter.fillRect(0, 0, w, h, QColor(24, 26, 32))
            painter.setPen(QPen(QColor(42, 46, 56), 1))
            step = 30
            for x in range(0, w, step):
                painter.drawLine(x, 0, x, h)
            for y in range(0, h, step):
                painter.drawLine(0, y, w, y)

        pts = self._get_widget_points()
        p0, p1, p2, p3 = pts

        sol = self.last_solution

        # 2. Horizon Line
        vp1_doc = sol.get("vp1")
        vp2_doc = sol.get("vp2")
        if vp1_doc and vp2_doc:
            vp1_w = self._doc_to_widget(vp1_doc)
            vp2_w = self._doc_to_widget(vp2_doc)
            dx = vp2_w.x() - vp1_w.x()
            dy = vp2_w.y() - vp1_w.y()
            if abs(dx) > 1e-3 or abs(dy) > 1e-3:
                scale = max(w, h) * 4.0
                h_p1 = QPointF(vp1_w.x() - dx * scale, vp1_w.y() - dy * scale)
                h_p2 = QPointF(vp2_w.x() + dx * scale, vp2_w.y() + dy * scale)
                painter.setPen(QPen(QColor(234, 179, 8, 190), 1.5, Qt.DashLine))
                painter.drawLine(h_p1, h_p2)

                # Horizon Label
                painter.setPen(QColor(250, 204, 21))
                painter.setFont(QFont("Segoe UI", 8, QFont.Bold))
                mid_y = int(max(16, min(h - 12, (vp1_w.y() + vp2_w.y()) * 0.5)))
                painter.drawText(int(self.img_rect.x() + 8), mid_y, "── Horizon Line (Eye Level) ──")

        # 3. Ground Perspective Floor Subdivision Grid
        grid_subdiv = 4
        painter.setPen(QPen(QColor(56, 189, 248, 90), 1))
        for i in range(1, grid_subdiv):
            t = i / float(grid_subdiv)
            # Lines along X
            pa = QPointF(p0.x() + (p3.x() - p0.x()) * t, p0.y() + (p3.y() - p0.y()) * t)
            pb = QPointF(p1.x() + (p2.x() - p1.x()) * t, p1.y() + (p2.y() - p1.y()) * t)
            painter.drawLine(pa, pb)
            # Lines along Z
            pc = QPointF(p0.x() + (p1.x() - p0.x()) * t, p0.y() + (p1.y() - p0.y()) * t)
            pd = QPointF(p3.x() + (p2.x() - p3.x()) * t, p3.y() + (p2.y() - p3.y()) * t)
            painter.drawLine(pc, pd)

        # 4. Quad Fill and Outline
        quad_poly = QPolygonF([p0, p1, p2, p3])
        painter.setBrush(QBrush(QColor(59, 130, 246, 35)))
        painter.setPen(Qt.NoPen)
        painter.drawPolygon(quad_poly)

        # Axis X edges: Red (Front P0-P1, Back P3-P2)
        painter.setPen(QPen(QColor(239, 68, 68), 2.5))
        painter.drawLine(p0, p1)
        painter.drawLine(p3, p2)

        # Axis Z edges: Blue (Left P0-P3, Right P1-P2)
        painter.setPen(QPen(QColor(59, 130, 246), 2.5))
        painter.drawLine(p0, p3)
        painter.drawLine(p1, p2)

        # Diagonals to perspective center
        painter.setPen(QPen(QColor(148, 163, 184, 120), 1, Qt.DotLine))
        painter.drawLine(p0, p2)
        painter.drawLine(p1, p3)

        # Center target pin
        c_doc = sol.get("center_2d", QPointF(0, 0))
        c_widget = self._doc_to_widget(c_doc)
        painter.setBrush(QBrush(QColor(34, 197, 94)))
        painter.setPen(QPen(QColor(255, 255, 255), 1.5))
        painter.drawEllipse(c_widget, 4.5, 4.5)

        # 5. LIVE 3D MODEL PREVIEW resting on the ground quad!
        if self.mesh and self.mesh.vertices and self.renderer:
            pw = max(64, int(self.img_rect.width()))
            ph = max(64, int(self.img_rect.height()))

            cam_prev = Camera3D()
            cam_prev.yaw = sol.get("yaw", 180.0)
            cam_prev.pitch = sol.get("pitch", 15.0)
            cam_prev.roll = sol.get("roll", 0.0)
            cam_prev.fov = sol.get("fov", 45.0)
            cam_prev.distance = sol.get("distance", 3.0)
            cam_prev.pan_x = sol.get("pan_x", 0.0)
            cam_prev.pan_y = sol.get("pan_y", 0.0)
            cam_prev.target_x = sol.get("target_x", 0.0)
            cam_prev.target_y = sol.get("target_y", 0.0)
            cam_prev.target_z = sol.get("target_z", 0.0)

            # Render preview image
            prev_img = self.renderer.render_to_image(
                mesh=self.mesh,
                camera=cam_prev,
                lighting=self.lighting,
                style=RenderStyle.SHADED_WIREFRAME,
                width=pw,
                height=ph,
                bg_color=QColor(0, 0, 0, 0),
                draw_model=True
            )
            # Draw semi-transparent preview over the quad
            painter.setOpacity(0.88)
            painter.drawImage(int(self.img_rect.x()), int(self.img_rect.y()), prev_img)
            painter.setOpacity(1.0)

        # 6. Corner Pin Handles (Pins)
        handle_colors = [
            QColor(34, 197, 94),   # 0: Front-Left (Green)
            QColor(239, 68, 68),   # 1: Front-Right (Red)
            QColor(59, 130, 246),  # 2: Back-Right (Blue)
            QColor(234, 179, 8),   # 3: Back-Left (Yellow)
        ]
        handle_names = ["1 FL", "2 FR", "3 BR", "4 BL"]

        for idx, (pt, col, name) in enumerate(zip(pts, handle_colors, handle_names)):
            is_hover = (self.hovered_handle == idx)
            is_active = (self.active_handle == idx)

            r = self.HANDLE_RADIUS + (2.5 if is_hover or is_active else 0)
            painter.setBrush(QBrush(col))
            painter.setPen(QPen(QColor(255, 255, 255), 2.5 if (is_hover or is_active) else 1.5))
            painter.drawEllipse(pt, r, r)

            # Pin badge label
            painter.setFont(QFont("Segoe UI", 8, QFont.Bold))
            painter.setPen(QColor(255, 255, 255))
            painter.drawText(int(pt.x() + r + 4), int(pt.y() + 4), name)

        # 7. Sequential Picking Mode Banner & Rubber-band Guides
        if self.is_picking_mode:
            painter.setBrush(QBrush(QColor(15, 23, 42, 230)))
            painter.setPen(Qt.NoPen)
            painter.drawRect(0, 0, w, 34)
            painter.setPen(QColor(250, 204, 21))
            painter.setFont(QFont("Segoe UI", 9, QFont.Bold))
            step_names = ['1: Front-Left (Green)', '2: Front-Right (Red)', '3: Back-Right (Blue)', '4: Back-Left (Yellow)']
            cur_idx = min(3, len(self.picked_points))
            msg = f"✏️ Drawing Mode — Click point {cur_idx + 1} of 4: {step_names[cur_idx]}  [Esc to cancel]"
            painter.drawText(14, 22, msg)

            # Draw lines and points for already clicked corners
            clicked_pts = [
                QPointF(self.img_rect.x() + p.x() * self.img_rect.width(),
                        self.img_rect.y() + p.y() * self.img_rect.height())
                for p in self.picked_points
            ]
            if clicked_pts:
                p_pen = QPen(QColor(56, 189, 248), 2, Qt.DashLine)
                painter.setPen(p_pen)
                for i in range(len(clicked_pts) - 1):
                    painter.drawLine(clicked_pts[i], clicked_pts[i+1])
                if self.current_cursor_pos:
                    painter.drawLine(clicked_pts[-1], QPointF(self.current_cursor_pos))

                for i, cp in enumerate(clicked_pts):
                    painter.setBrush(QBrush(handle_colors[i]))
                    painter.setPen(QPen(QColor(255, 255, 255), 2))
                    painter.drawEllipse(cp, 7, 7)
                    painter.setFont(QFont("Segoe UI", 8, QFont.Bold))
                    painter.setPen(QColor(255, 255, 255))
                    painter.drawText(int(cp.x() + 9), int(cp.y() + 4), handle_names[i])

        painter.end()


class GroundCalibratorDialog(QDialog):
    """
    Dialog window allowing the artist to define a ground perspective rectangle
    and automatically place the 3D model on top of it.
    """
    applied = pyqtSignal(dict)

    def __init__(self, bg_image=None, mesh=None, camera=None, lighting=None,
                 renderer=None, frame_rect=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("3D Ground Calibrator — Perspective Matching")
        self.resize(880, 620)
        self.setStyleSheet("""
            QDialog { background: #1c1e24; color: #f1f5f9; }
            QLabel { font-family: "Segoe UI"; font-size: 11px; color: #cbd5e1; }
            QCheckBox { font-family: "Segoe UI"; font-size: 11px; color: #cbd5e1; spacing: 4px; }
            QPushButton {
                background: #323642; border: 1px solid #434958; border-radius: 4px;
                color: #e5e7eb; font-size: 11px; padding: 4px 8px; font-weight: bold;
            }
            QPushButton:hover { background: #3d4352; color: #fff; }
            QPushButton:pressed { background: #242730; }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        # Header description
        hdr = QLabel(
            "📐 <b>Ground Calibrator</b>: Drag the 4 corner pins "
            "(<b style='color:#22c55e;'>1 FL</b> Front-Left, <b style='color:#ef4444;'>2 FR</b> Front-Right, "
            "<b style='color:#3b82f6;'>3 BR</b> Back-Right, <b style='color:#eab308;'>4 BL</b> Back-Left) "
            "or click <b>✏️ Draw 4 Points</b> to match an object/plane drawn on your canvas.<br>"
            "<span style='color:#94a3b8;font-size:10px;'>The 3D model is rendered live atop the rectangle and will be placed directly onto this ground upon applying.</span>"
        )
        hdr.setWordWrap(True)
        layout.addWidget(hdr)

        # Interactive Canvas Widget
        self.calibrator_widget = GroundCalibratorWidget(
            bg_image=bg_image,
            mesh=mesh,
            camera=camera,
            lighting=lighting,
            renderer=renderer,
            frame_rect=frame_rect,
            parent=self
        )
        self.calibrator_widget.solution_changed.connect(self._on_solution_changed)
        layout.addWidget(self.calibrator_widget, 1)

        # Solved Parameters readout bar
        self.lbl_stats = QLabel("Solving...")
        self.lbl_stats.setStyleSheet(
            "font-family:'Consolas', monospace; font-size:11px; color:#38bdf8; "
            "background:#12141a; padding:6px; border-radius:3px; border:1px solid #1e293b;"
        )
        layout.addWidget(self.lbl_stats)

        # Toolbar
        bar = QHBoxLayout()
        bar.setSpacing(6)

        btn_draw = QPushButton("✏️ Draw 4 Points")
        btn_draw.setStyleSheet("background:#1e293b; color:#38bdf8; font-weight:bold; border:1px solid #0284c7; padding:4px 10px;")
        btn_draw.setToolTip("Click 4 consecutive corners on your canvas (1 Front-Left, 2 Front-Right, 3 Back-Right, 4 Back-Left)")
        btn_draw.clicked.connect(self.calibrator_widget.start_pick_mode)
        bar.addWidget(btn_draw)

        self.chk_keep_horizon = QCheckBox("Keep Horizon Horizontal")
        self.chk_keep_horizon.setChecked(True)
        self.chk_keep_horizon.setToolTip("Lock camera roll to 0° so the horizon line stays completely horizontal")
        self.chk_keep_horizon.stateChanged.connect(self._on_keep_horizon_toggled)
        bar.addWidget(self.chk_keep_horizon)

        btn_flip = QPushButton("🔄 Flip 180°")
        btn_flip.setToolTip("Flip model yaw 180° (toggle between facing front and back)")
        btn_flip.clicked.connect(self._on_flip_clicked)
        bar.addWidget(btn_flip)

        btn_center = QPushButton("⌖ Center")
        btn_center.setToolTip("Centers the ground quad in view")
        btn_center.clicked.connect(self.calibrator_widget.center_quad)
        bar.addWidget(btn_center)

        btn_reset = QPushButton("⟲ Reset")
        btn_reset.setToolTip("Resets the 4 pins to default perspective")
        btn_reset.clicked.connect(self.calibrator_widget.reset_points)
        bar.addWidget(btn_reset)

        bar.addStretch(1)

        btn_apply = QPushButton("✔ Place Model on Ground & Apply")
        btn_apply.setStyleSheet(
            "background:#2563eb; color:#ffffff; border:1px solid #1d4ed8; padding:6px 14px; font-size:12px; font-weight:bold;"
        )
        btn_apply.setToolTip("Applies the solved camera and places the 3D model directly on top of the ground rectangle")
        btn_apply.clicked.connect(self._apply)
        bar.addWidget(btn_apply)

        btn_close = QPushButton("Cancel")
        btn_close.clicked.connect(self.reject)
        bar.addWidget(btn_close)

        layout.addLayout(bar)

        self._on_solution_changed(self.calibrator_widget.last_solution)

    def _on_keep_horizon_toggled(self, state):
        self.calibrator_widget.set_keep_horizon(state == Qt.Checked)

    def _on_flip_clicked(self):
        self.calibrator_widget.toggle_flip_yaw()

    def _on_solution_changed(self, sol):
        yaw = sol.get("yaw", 180.0)
        pitch = sol.get("pitch", 15.0)
        roll = sol.get("roll", 0.0)
        fov = sol.get("fov", 45.0)
        dist = sol.get("distance", 3.0)
        self.lbl_stats.setText(
            f"Yaw: {yaw:5.1f}° | Tilt/Pitch: {pitch:5.1f}° | Roll: {roll:5.1f}° | FOV: {fov:5.1f}° | Dist: {dist:4.2f}"
        )

    def _apply(self):
        self.applied.emit(self.calibrator_widget.last_solution)
        self.accept()
