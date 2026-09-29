"""
Ground plane calibrator. Matches camera angles and FOV to a 4-point rectangle on canvas.
"""

import os
import json
import math
import datetime
from PyQt5.QtWidgets import (
    QDialog, QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QLabel, QSizePolicy, QFrame, QCheckBox, QApplication, QDesktopWidget,
    QComboBox, QMenu, QAction
)
from PyQt5.QtGui import (
    QPainter, QColor, QPen, QBrush, QFont, QPolygonF, QImage, QCursor,
    QVector3D, QVector4D, QMatrix4x4
)
from PyQt5.QtCore import Qt, QPointF, QRectF, pyqtSignal, QByteArray

from .renderer import (
    Camera3D, Lighting3D, Renderer3D, RenderStyle, project_camera_point,
    ProjectionMode, ObjectTransform
)
from .primitive_drawer import (
    create_box_primitive, create_cylinder_primitive, create_sphere_primitive,
    create_pyramid_primitive, create_cone_primitive, create_plane_primitive,
    create_room_primitive,
    add_primitive_to_history, load_primitive_history, clear_primitive_history
)


def get_ground_dialog_geometry_file_path():
    hdir = os.path.join(os.path.expanduser("~"), ".krita_3d_layer")
    os.makedirs(hdir, exist_ok=True)
    return os.path.join(hdir, "ground_dialog_geometry.json")


def load_ground_dialog_geometry():
    path = get_ground_dialog_geometry_file_path()
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data.get("geometry")
        except Exception:
            pass
    return None


def save_ground_dialog_geometry(geo_hex):
    path = get_ground_dialog_geometry_file_path()
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"geometry": geo_hex}, f)
    except Exception:
        pass


def segments_intersect(p1, p2, p3, p4):
    """Checks if line segment p1-p2 strictly intersects line segment p3-p4."""
    def ccw(a, b, c):
        return (c.y() - a.y()) * (b.x() - a.x()) > (b.y() - a.y()) * (c.x() - a.x())
    return (ccw(p1, p3, p4) != ccw(p2, p3, p4)) and (ccw(p1, p2, p3) != ccw(p1, p2, p4))


def pt_dist_to_segment(p, a, b):
    """Calculates perpendicular pixel distance from 2D point p to segment a-b."""
    abx = b.x() - a.x()
    aby = b.y() - a.y()
    l2 = abx * abx + aby * aby
    if l2 < 1e-6:
        return math.hypot(p.x() - a.x(), p.y() - a.y())
    t = max(0.0, min(1.0, ((p.x() - a.x()) * abx + (p.y() - a.y()) * aby) / l2))
    proj_x = a.x() + t * abx
    proj_y = a.y() + t * aby
    return math.hypot(p.x() - proj_x, p.y() - proj_y)


def validate_ground_quad(p0, p1, p2, p3):
    """
    Validates a ground quad defined by 4 corner points:
      p0: Front-Left (1 FL)
      p1: Front-Right (2 FR)
      p2: Back-Right (3 BR)
      p3: Back-Left (4 BL)
    Returns: (is_valid: bool, level: str, message: str)
    """
    pts = [p0, p1, p2, p3]

    # 1. Area / Collinear check
    area = 0.5 * abs(
        (p0.x() * p1.y() - p1.x() * p0.y()) +
        (p1.x() * p2.y() - p2.x() * p1.y()) +
        (p2.x() * p3.y() - p3.x() * p2.y()) +
        (p3.x() * p0.y() - p0.x() * p3.y())
    )
    if area < 100.0:
        return False, "error", "⚠️ Points are collinear or too close together. Spread out the 4 pins to define a ground plane."

    # 2. Self-intersecting edges (hourglass / bowtie)
    if segments_intersect(p0, p1, p2, p3) or segments_intersect(p1, p2, p3, p0):
        return False, "error", "⚠️ Edges cross each other (hourglass shape)! Pins must be placed in order: 1 FL ➔ 2 FR ➔ 3 BR ➔ 4 BL."

    # 3. Convexity check (all corner turns must bend outward)
    def cross_2d(oa, ob):
        return (oa.x() * ob.y()) - (oa.y() * ob.x())

    crosses = []
    for i in range(4):
        prev = pts[i]
        curr = pts[(i + 1) % 4]
        nxt = pts[(i + 2) % 4]
        e1 = QPointF(curr.x() - prev.x(), curr.y() - prev.y())
        e2 = QPointF(nxt.x() - curr.x(), nxt.y() - curr.y())
        crosses.append(cross_2d(e1, e2))

    has_pos = any(c > 1e-4 for c in crosses)
    has_neg = any(c < -1e-4 for c in crosses)
    if has_pos and has_neg:
        return False, "error", "⚠️ Non-convex quad! In perspective, all 4 corners must bend outward. Please adjust pin positions."

    # 4. Inverted X direction (Front-Right to the left of Front-Left)
    if (p1.x() - p0.x()) < -10.0:
        return False, "warn", "⚠️ Inverted Front Edge: Point 2 (FR) is to the left of Point 1 (FL). Click '🔄 Flip 180°' or swap pins."

    # 5. Inverted perspective check (back edge significantly wider than front edge)
    w_front = math.hypot(p1.x() - p0.x(), p1.y() - p0.y())
    w_back = math.hypot(p2.x() - p3.x(), p2.y() - p3.y())
    if (p3.y() < p0.y() and p2.y() < p1.y()) and w_front > 10.0:
        if w_back > w_front * 1.55:
            return True, "warn", "⚠️ Diverging perspective: Back edge is wider than front edge. Receding ground edges should narrow toward horizon."

    return True, "success", "✔ Valid ground rectangle: Model placed cleanly on perspective ground."


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
        view_size = min(float(fw), float(fh))
    else:
        w = float(width) if width > 0 else 1000.0
        h = float(height) if height > 0 else 1000.0
        cx = w * 0.5
        cy = h * 0.5
        view_size = min(w, h)

    # In Qt / OpenGL perspective(fov, aspect), fov is VERTICAL FOV.
    # Therefore, focal length is always relative to half the view size:
    half_size = view_size * 0.5

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
    f_base = half_size / math.tan(math.radians(max(5.0, min(160.0, current_fov)) * 0.5))
    f = f_base
    solved_fov = current_fov

    if vp1 and vp2:
        u1 = (vp1.x() - cx, -(vp1.y() - cy))
        u2 = (vp2.x() - cx, -(vp2.y() - cy))
        dot = u1[0] * u2[0] + u1[1] * u2[1]
        if dot < -100.0:  # Orthogonal directions in perspective
            f_calc = math.sqrt(-dot)
            calc_fov = 2.0 * math.atan(half_size / f_calc) * 180.0 / math.pi
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
        ray_X = QVector3D(p1.x() - p0.x(), -(p1.y() - p0.y()), 0.0).normalized()
    elif vp1:
        # Side lines are parallel in screen space
        ray_X = QVector3D(vp1.x() - cx, -(vp1.y() - cy), -f).normalized()
        ray_Z = QVector3D(p3.x() - p0.x(), -(p3.y() - p0.y()), 0.0).normalized()
    else:
        # Top-down / axonometric fallback
        ray_X = QVector3D(1.0, 0.0, 0.0)
        ray_Z = QVector3D(0.0, 0.0, -1.0)

    # Ensure ray_X points in direction p0 -> p1 (screen left to right)
    dir_2d_X = QVector3D(p1.x() - p0.x(), -(p1.y() - p0.y()), 0.0).normalized()
    if QVector3D.dotProduct(ray_X, dir_2d_X) < 0:
        ray_X = -ray_X

    # Ensure ray_Z points in direction p0 -> p3 (into screen towards horizon)
    dir_2d_Z = QVector3D(p3.x() - p0.x(), -(p3.y() - p0.y()), 0.0).normalized()
    if QVector3D.dotProduct(ray_Z, dir_2d_Z) < 0:
        ray_Z = -ray_Z

    # 6. Ground Normal in camera view space
    N = QVector3D.crossProduct(ray_X, ray_Z).normalized()
    if N.y() < 0:
        N = -N

    # 7. Pitch and Roll
    if keep_horizon:
        N = QVector3D(0.0, N.y(), N.z()).normalized()
        roll = 0.0
    else:
        roll = -math.degrees(math.atan2(N.x(), N.y()))
        roll = max(-85.0, min(85.0, roll))

    pitch = math.degrees(math.atan2(N.z(), math.sqrt(N.x()**2 + N.y()**2)))
    pitch = max(-85.0, min(85.0, pitch))

    # 8. Yaw (combining both axes for least-squares optimal alignment)
    cos_pitch = max(0.01, math.cos(math.radians(pitch)))
    # In Camera3D view space:
    # ray_X points from p0 to p1 (towards world -X).
    # ray_Z points from p0 to p3 (towards world +Z).
    sin_yaw_X = -ray_X.z() / cos_pitch
    cos_yaw_X = -ray_X.x()
    sin_yaw_Z = -ray_Z.x()
    cos_yaw_Z = ray_Z.z() / cos_pitch

    if vp1 and vp2:
        sin_yaw = (sin_yaw_X + sin_yaw_Z) * 0.5
        cos_yaw = (cos_yaw_X + cos_yaw_Z) * 0.5
    elif vp2:
        sin_yaw = sin_yaw_Z
        cos_yaw = cos_yaw_Z
    else:
        sin_yaw = sin_yaw_X
        cos_yaw = cos_yaw_X

    yaw = (math.degrees(math.atan2(sin_yaw, cos_yaw))) % 360.0
    if flip_yaw:
        yaw = (yaw + 180.0) % 360.0

    # 9. Ground Rectangle 3D Dimensions & Scaling
    # Compute rays through p0, p1, p2, p3 and intersect with ground plane in camera view space
    w01 = math.hypot(p1.x() - p0.x(), p1.y() - p0.y())
    w32 = math.hypot(p2.x() - p3.x(), p2.y() - p3.y())
    quad_w = max(5.0, (w01 + w32) * 0.5)

    L_perp = max(0.15, math.sqrt(ray_X.x()**2 + ray_X.y()**2))
    dist = f * (2.0 * L_perp) / quad_w
    dist = max(0.2, min(50.0, dist))

    # Center ray and ground center in camera coordinates:
    rc_len = math.sqrt((center_2d.x() - cx)**2 + (center_2d.y() - cy)**2 + f**2)
    rc = QVector3D((center_2d.x() - cx) / rc_len, -(center_2d.y() - cy) / rc_len, -f / rc_len)
    P_center = rc * dist

    def _project_ray_to_plane(pt):
        r_len = math.sqrt((pt.x() - cx)**2 + (pt.y() - cy)**2 + f**2)
        ray = QVector3D((pt.x() - cx) / r_len, -(pt.y() - cy) / r_len, -f / r_len)
        denom = QVector3D.dotProduct(N, ray)
        if abs(denom) > 1e-4:
            t = QVector3D.dotProduct(N, P_center) / denom
            return ray * t
        return P_center

    P0 = _project_ray_to_plane(p0)
    P1 = _project_ray_to_plane(p1)
    P2 = _project_ray_to_plane(p2)
    P3 = _project_ray_to_plane(p3)

    rect_w = max(0.2, min(50.0, ((P1 - P0).length() + (P2 - P3).length()) * 0.5))
    rect_d = max(0.2, min(50.0, ((P3 - P0).length() + (P2 - P1).length()) * 0.5))

    ground_y = -1.0
    target_x = 0.0
    target_y = ground_y
    target_z = 0.0
    if mesh and hasattr(mesh, 'bbox_min') and hasattr(mesh, 'bbox_max'):
        ground_y = mesh.bbox_min.y()
        target_x = (mesh.bbox_min.x() + mesh.bbox_max.x()) * 0.5
        target_y = ground_y
        target_z = (mesh.bbox_min.z() + mesh.bbox_max.z()) * 0.5

    ptype = getattr(mesh, 'primitive_type', None) if mesh else None
    if ptype == "Box":
        prev_h = 2.0
        if hasattr(mesh, 'primitive_params') and 'h' in mesh.primitive_params:
            prev_h = float(mesh.primitive_params['h'])
        elif hasattr(mesh, 'bbox_min') and hasattr(mesh, 'bbox_max'):
            prev_h = max(0.2, mesh.bbox_max.y() - mesh.bbox_min.y())
        rect_h = max(0.2, min(50.0, prev_h))
        sphere_radius = min(rect_w, rect_d) * 0.5
    elif ptype == "Pyramid":
        prev_h = 2.0
        if hasattr(mesh, 'primitive_params') and 'h' in mesh.primitive_params:
            prev_h = float(mesh.primitive_params['h'])
        elif hasattr(mesh, 'bbox_min') and hasattr(mesh, 'bbox_max'):
            prev_h = max(0.2, mesh.bbox_max.y() - mesh.bbox_min.y())
        rect_h = max(0.2, min(50.0, prev_h))
        sphere_radius = min(rect_w, rect_d) * 0.5
    elif ptype == "Sphere":
        sphere_radius = max(0.1, min(25.0, min(rect_w, rect_d) * 0.5))
        rect_h = sphere_radius * 2.0
    else:
        rect_h = (rect_w + rect_d) * 0.5
        sphere_radius = min(rect_w, rect_d) * 0.5

    # Scale factors for imported 3D mesh:
    if mesh and hasattr(mesh, 'bbox_min') and hasattr(mesh, 'bbox_max'):
        orig_w = max(0.01, mesh.bbox_max.x() - mesh.bbox_min.x())
        orig_d = max(0.01, mesh.bbox_max.z() - mesh.bbox_min.z())
        orig_h = max(0.01, mesh.bbox_max.y() - mesh.bbox_min.y())
        scale_x = max(0.01, min(100.0, rect_w / orig_w))
        scale_z = max(0.01, min(100.0, rect_d / orig_d))
        scale_y = (scale_x + scale_z) * 0.5
    else:
        scale_x = scale_y = scale_z = 1.0

    # 10. Camera Pan
    pan_x = ((center_2d.x() - cx) / f) * dist
    pan_y = -((center_2d.y() - cy) / f) * dist

    # 11. Fast Sub-Pixel Corner Refinement Optimization (Nelder-Mead simplex)
    # Refines yaw, pitch, roll, dist, pan_x, pan_y using actual rect_w and rect_d
    hw = rect_w * 0.5
    hd = rect_d * 0.5
    if not flip_yaw:
        corners_3d = [
            QVector3D(target_x + hw, ground_y, target_z - hd),  # p0: Front-Left
            QVector3D(target_x - hw, ground_y, target_z - hd),  # p1: Front-Right
            QVector3D(target_x - hw, ground_y, target_z + hd),  # p2: Back-Right
            QVector3D(target_x + hw, ground_y, target_z + hd),  # p3: Back-Left
        ]
    else:
        corners_3d = [
            QVector3D(target_x - hw, ground_y, target_z + hd),  # p0: Back-Right (flipped)
            QVector3D(target_x + hw, ground_y, target_z + hd),  # p1: Back-Left (flipped)
            QVector3D(target_x + hw, ground_y, target_z - hd),  # p2: Front-Left (flipped)
            QVector3D(target_x - hw, ground_y, target_z - hd),  # p3: Front-Right (flipped)
        ]
    target_pts = [p0, p1, p2, p3]

    def _eval_error(params):
        pyaw, ppitch, proll, pdist, ppx, ppy = params
        if pdist < 0.1 or abs(ppitch) > 87.0:
            return 1e9
        r_yaw = math.radians(pyaw)
        r_pitch = math.radians(ppitch)
        eye = QVector3D(
            target_x + pdist * math.cos(r_pitch) * math.sin(r_yaw),
            pdist * math.sin(r_pitch) + target_y,
            target_z + pdist * math.cos(r_pitch) * math.cos(r_yaw)
        )
        fwd = (QVector3D(target_x, target_y, target_z) - eye).normalized()
        right = QVector3D.crossProduct(fwd, QVector3D(0, 1, 0)).normalized()
        cup = QVector3D.crossProduct(right, fwd).normalized()
        if abs(proll) > 1e-4:
            r_roll = math.radians(proll)
            cr = math.cos(r_roll); sr = math.sin(r_roll)
            n_right = right * cr - cup * sr
            n_up = right * sr + cup * cr
            right, cup = n_right, n_up

        tot_err = 0.0
        for cp, tp in zip(corners_3d, target_pts):
            rel = cp - eye
            dfwd = QVector3D.dotProduct(rel, fwd)
            if dfwd <= 0.01:
                return 1e9
            sx = cx + f * ((QVector3D.dotProduct(rel, right) + ppx) / dfwd)
            sy = cy - f * ((QVector3D.dotProduct(rel, cup) + ppy) / dfwd)
            tot_err += (sx - tp.x())**2 + (sy - tp.y())**2
        return tot_err

    init_params = [yaw, pitch, roll, dist, pan_x, pan_y]
    steps = [2.0, 1.5, 0.0 if keep_horizon else 1.0, max(0.1, dist * 0.05), 0.05, 0.05]
    dim = 6
    simplex = [list(init_params)]
    for d in range(dim):
        pt = list(init_params)
        pt[d] += steps[d]
        simplex.append(pt)
    scores = [_eval_error(pt) for pt in simplex]

    for _ in range(80):
        order = sorted(range(dim + 1), key=lambda idx: scores[idx])
        simplex = [simplex[i] for i in order]
        scores = [scores[i] for i in order]
        if scores[0] < 0.1:
            break
        centroid = [sum(simplex[i][d] for i in range(dim)) / dim for d in range(dim)]
        xr = [2.0 * centroid[d] - simplex[dim][d] for d in range(dim)]
        if keep_horizon: xr[2] = 0.0
        sr_score = _eval_error(xr)
        if scores[0] <= sr_score < scores[dim - 1]:
            simplex[dim] = xr; scores[dim] = sr_score; continue
        if sr_score < scores[0]:
            xe = [centroid[d] + 2.0 * (xr[d] - centroid[d]) for d in range(dim)]
            if keep_horizon: xe[2] = 0.0
            se_score = _eval_error(xe)
            if se_score < sr_score:
                simplex[dim] = xe; scores[dim] = se_score
            else:
                simplex[dim] = xr; scores[dim] = sr_score
            continue
        xc = [centroid[d] + 0.5 * (simplex[dim][d] - centroid[d]) for d in range(dim)]
        if keep_horizon: xc[2] = 0.0
        sc_score = _eval_error(xc)
        if sc_score < scores[dim]:
            simplex[dim] = xc; scores[dim] = sc_score; continue
        for i in range(1, dim + 1):
            simplex[i] = [simplex[0][d] + 0.5 * (simplex[i][d] - simplex[0][d]) for d in range(dim)]
            if keep_horizon: simplex[i][2] = 0.0
            scores[i] = _eval_error(simplex[i])

    best = simplex[0]
    yaw = best[0] % 360.0
    pitch = max(-85.0, min(85.0, best[1]))
    roll = 0.0 if keep_horizon else max(-85.0, min(85.0, best[2]))
    dist = max(0.1, min(50.0, best[3]))
    pan_x = best[4]
    pan_y = best[5]

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
        "center_2d": center_2d,
        "rect_width": rect_w,
        "rect_depth": rect_d,
        "rect_height": rect_h,
        "sphere_radius": sphere_radius,
        "scale_x": scale_x,
        "scale_y": scale_y,
        "scale_z": scale_z,
        "primitive_type": ptype,
        "corners_3d": corners_3d,
    }


def solve_height_from_point(camera, doc_w, doc_h, base_corner_3d, norm_pt, frame_rect=None):
    """
    Solves 3D height H given a 2D canvas normalized point and a 3D base corner position.
    Uses true perspective projection matching the camera.
    """
    if not camera or doc_w <= 0 or doc_h <= 0 or norm_pt is None:
        return 2.0
    if frame_rect and len(frame_rect) == 4 and frame_rect[2] > 0 and frame_rect[3] > 0:
        fx, fy, fw, fh = frame_rect
        render_size = min(fw, fh)
        offset_x = fx + (fw - render_size) * 0.5
        offset_y = fy + (fh - render_size) * 0.5
    else:
        render_size = min(doc_w, doc_h)
        offset_x = (doc_w - render_size) * 0.5
        offset_y = (doc_h - render_size) * 0.5

    _, view_mat, _ = camera.get_matrices(render_size, render_size)
    bx, by, bz = base_corner_3d.x(), base_corner_3d.y(), base_corner_3d.z()
    pt_base, _ = project_camera_point(camera, view_mat, bx, by, bz, render_size, offset_x, offset_y)
    pt_test, _ = project_camera_point(camera, view_mat, bx, by + 1.0, bz, render_size, offset_x, offset_y)

    if pt_base is None or pt_test is None:
        return 2.0

    target_pt = QPointF(norm_pt.x() * doc_w, norm_pt.y() * doc_h)
    vx = pt_test.x() - pt_base.x()
    vy = pt_test.y() - pt_base.y()
    v_len_sq = vx * vx + vy * vy
    if v_len_sq < 1e-4:
        return 2.0

    t = ((target_pt.x() - pt_base.x()) * vx + (target_pt.y() - pt_base.y()) * vy) / v_len_sq
    if t <= 0.02:
        return 0.1

    low, high = 0.05, 50.0
    best_h = 2.0
    for _ in range(24):
        mid = (low + high) * 0.5
        pt_m, _ = project_camera_point(camera, view_mat, bx, by + mid, bz, render_size, offset_x, offset_y)
        if pt_m is None:
            high = mid
            continue
        tm = ((pt_m.x() - pt_base.x()) * vx + (pt_m.y() - pt_base.y()) * vy) / v_len_sq
        if tm < t:
            low = mid
            best_h = mid
        else:
            high = mid
            best_h = mid

    return max(0.1, min(50.0, best_h))


def project_height_to_norm_point(camera, doc_w, doc_h, base_corner_3d, height, frame_rect=None):
    """Projects 3D height point above base corner back to 2D normalized document coordinates."""
    if not camera or doc_w <= 0 or doc_h <= 0:
        return QPointF(0.25, 0.5)
    if frame_rect and len(frame_rect) == 4 and frame_rect[2] > 0 and frame_rect[3] > 0:
        fx, fy, fw, fh = frame_rect
        render_size = min(fw, fh)
        offset_x = fx + (fw - render_size) * 0.5
        offset_y = fy + (fh - render_size) * 0.5
    else:
        render_size = min(doc_w, doc_h)
        offset_x = (doc_w - render_size) * 0.5
        offset_y = (doc_h - render_size) * 0.5

    _, view_mat, _ = camera.get_matrices(render_size, render_size)
    bx, by, bz = base_corner_3d.x(), base_corner_3d.y(), base_corner_3d.z()
    pt_top, _ = project_camera_point(camera, view_mat, bx, by + height, bz, render_size, offset_x, offset_y)
    if pt_top is None:
        return QPointF(0.25, 0.5)
    return QPointF(max(0.001, min(0.999, pt_top.x() / doc_w)),
                   max(0.001, min(0.999, pt_top.y() / doc_h)))


class GroundCalibratorWidget(QWidget):
    """
    Interactive canvas widget that displays the canvas snapshot, allows dragging
    the 4 ground quad corner pins (and optional 5th height pin), and renders a LIVE 3D PREVIEW
    of the model sitting directly on top of the ground rectangle.
    """
    solution_changed = pyqtSignal(dict)
    guidance_changed = pyqtSignal(str, str)
    gizmo_mode_changed = pyqtSignal(str)

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
        self.pick_mode_points = 4
        self.has_height_point = False
        self.height_norm_pt = None
        self.is_drag_mode = False
        self.drag_start_pos = None
        self.picked_points = []
        self.keep_horizon = True
        self.flip_yaw = False
        self.current_cursor_pos = None

        # Primitive selection & aspect preset
        self.primitive_type = "Ground Rectangle"
        if self.mesh and hasattr(self.mesh, 'primitive_type') and self.mesh.primitive_type:
            self.primitive_type = self.mesh.primitive_type
        elif self.mesh and getattr(self.mesh, 'vertices', None):
            self.primitive_type = "Loaded 3D Model"
        self.has_height_point = (self.primitive_type in ("Box", "Cylinder", "Pyramid", "Cone", "Room", "Room (3 Planes)"))
        self.aspect_preset = "Free"

        # Horizon interaction
        self.is_dragging_horizon = False
        self.hover_horizon = False
        self.drag_start_pitch = 15.0

        # 3D Blender-Style Transform Gizmo
        self.gizmo_mode = 'all'          # 'all' (combined), 'move', 'rotate', 'scale'
        self.active_gizmo_part = None    # 'trans_x', 'trans_y', 'trans_z', 'plane_xy', 'plane_xz', 'plane_yz', 'center',
                                         # 'rot_z', 'rot_x', 'rot_y', 'rot_view',
                                         # 'scale_x', 'scale_y', 'scale_z', 'scale_uniform'
        self.hover_gizmo_part = None
        self.drag_start_mouse_pos = None
        self.drag_start_obj_state = {}
        self.drag_start_angle = 0.0
        self.drag_start_dist = 1.0

        # Current image rect within widget (for letterbox/aspect mapping)
        self.img_rect = QRectF(0, 0, 480, 360)

        # 4 ground points in normalized document coordinates [0, 1]
        # P0: Front-Left, P1: Front-Right, P2: Back-Right, P3: Back-Left
        self.norm_points = self._compute_initial_norm_points()

        self.last_solution = {}
        self._recalculate()

    def set_primitive_type(self, ptype):
        """Sets active primitive type (e.g. 'Box', 'Cylinder', 'Ground Rectangle', 'Loaded 3D Model', 'Room')."""
        self.primitive_type = ptype
        self.has_height_point = (ptype in ("Box", "Cylinder", "Pyramid", "Cone", "Room", "Room (3 Planes)"))
        self._recalculate()
        self.update()

    def set_gizmo_mode(self, mode):
        """Sets active 3D gizmo mode: 'all' (combined), 'move', 'rotate', 'scale'."""
        self.gizmo_mode = mode
        if mode == 'move':
            self.guidance_changed.emit("✥ 3D Move Mode (G): Drag Red [X], Green [Y/Depth], or Blue [Z/Up] arrows to reposition 3D object.", "info")
        elif mode == 'rotate':
            self.guidance_changed.emit("⟳ 3D Rotate Mode (R): Drag Blue track (Yaw around Ground Up), Red track (Pitch), or Green track (Roll).", "info")
        elif mode == 'scale':
            self.guidance_changed.emit("⤢ 3D Scale Mode (S): Drag Red (Width), Green (Depth), or Blue (Height) cube handles.", "info")
        else:
            self.guidance_changed.emit("⚙ 3D Transform Gizmo (Blender style): Manipulate 3D object with 3 axes. 4 ground points adapt automatically.", "info")
        self.gizmo_mode_changed.emit(mode)
        self.update()

    def _compute_3d_gizmo_geometry(self):
        """
        Computes 3D coordinates and 2D projected screen coordinates for all
        Blender-style transform gizmo handles (axes, arrows, rings, planes, cubes).
        """
        sol = self.last_solution
        if not sol or not self.camera:
            return None

        doc_w, doc_h = self._get_doc_size()
        render_size = min(doc_w, doc_h)
        offset_x = (doc_w - render_size) * 0.5
        offset_y = (doc_h - render_size) * 0.5
        _, view_mat, _ = self.camera.get_matrices(render_size, render_size)

        tx = sol.get("target_x", 0.0)
        ty = sol.get("target_y", 0.0)
        tz = sol.get("target_z", 0.0)
        rw = sol.get("rect_width", 2.0)
        rd = sol.get("rect_depth", 2.0)
        rh = sol.get("rect_height", 2.0)
        yaw = sol.get("yaw", 180.0)

        origin_doc, _ = project_camera_point(self.camera, view_mat, tx, ty, tz, render_size, offset_x, offset_y)
        if not origin_doc:
            return None
        origin_w = self._doc_to_widget(origin_doc)

        r_yaw = math.radians(yaw)
        cos_y = math.cos(r_yaw)
        sin_y = math.sin(r_yaw)

        axis_x_3d = QVector3D(cos_y, 0, -sin_y)
        axis_y_3d = QVector3D(sin_y, 0, cos_y)
        axis_z_3d = QVector3D(0, 1, 0)

        arm_len = max(0.5, min(rw, rd) * 0.6)
        pt_x_doc, _ = project_camera_point(self.camera, view_mat, tx + axis_x_3d.x() * arm_len, ty + axis_x_3d.y() * arm_len, tz + axis_x_3d.z() * arm_len, render_size, offset_x, offset_y)
        pt_y_doc, _ = project_camera_point(self.camera, view_mat, tx + axis_y_3d.x() * arm_len, ty + axis_y_3d.y() * arm_len, tz + axis_y_3d.z() * arm_len, render_size, offset_x, offset_y)
        pt_z_doc, _ = project_camera_point(self.camera, view_mat, tx + axis_z_3d.x() * arm_len, ty + axis_z_3d.y() * arm_len, tz + axis_z_3d.z() * arm_len, render_size, offset_x, offset_y)

        if not pt_x_doc or not pt_y_doc or not pt_z_doc:
            return None

        pt_x_w = self._doc_to_widget(pt_x_doc)
        pt_y_w = self._doc_to_widget(pt_y_doc)
        pt_z_w = self._doc_to_widget(pt_z_doc)

        def norm_vec(p1, p0):
            dx = p1.x() - p0.x()
            dy = p1.y() - p0.y()
            l = math.hypot(dx, dy)
            if l < 1e-4:
                return QPointF(1, 0)
            return QPointF(dx / l, dy / l)

        dir_x = norm_vec(pt_x_w, origin_w)
        dir_y = norm_vec(pt_y_w, origin_w)
        dir_z = norm_vec(pt_z_w, origin_w)

        gizmo_radius = 70.0

        tip_x = QPointF(origin_w.x() + dir_x.x() * gizmo_radius, origin_w.y() + dir_x.y() * gizmo_radius)
        tip_y = QPointF(origin_w.x() + dir_y.x() * gizmo_radius, origin_w.y() + dir_y.y() * gizmo_radius)
        tip_z = QPointF(origin_w.x() + dir_z.x() * gizmo_radius, origin_w.y() + dir_z.y() * gizmo_radius)

        pl_dist = gizmo_radius * 0.44
        plane_xy_pt = QPointF(origin_w.x() + (dir_x.x() + dir_y.x()) * pl_dist * 0.7, origin_w.y() + (dir_x.y() + dir_y.y()) * pl_dist * 0.7)
        plane_xz_pt = QPointF(origin_w.x() + (dir_x.x() + dir_z.x()) * pl_dist * 0.7, origin_w.y() + (dir_x.y() + dir_z.y()) * pl_dist * 0.7)
        plane_yz_pt = QPointF(origin_w.x() + (dir_y.x() + dir_z.x()) * pl_dist * 0.7, origin_w.y() + (dir_y.y() + dir_z.y()) * pl_dist * 0.7)

        rot_pts_z = []
        rot_pts_x = []
        rot_pts_y = []
        r_3d = max(0.4, min(rw, rd) * 0.65)
        for step in range(33):
            phi = 2.0 * math.pi * step / 32.0
            cp = math.cos(phi)
            sp = math.sin(phi)
            p_z_3d = QVector3D(tx + (axis_x_3d.x() * cp + axis_y_3d.x() * sp) * r_3d,
                               ty,
                               tz + (axis_x_3d.z() * cp + axis_y_3d.z() * sp) * r_3d)
            p_z_doc, _ = project_camera_point(self.camera, view_mat, p_z_3d.x(), p_z_3d.y(), p_z_3d.z(), render_size, offset_x, offset_y)
            if p_z_doc:
                rot_pts_z.append(self._doc_to_widget(p_z_doc))

            p_x_3d = QVector3D(tx + axis_y_3d.x() * sp * r_3d,
                               ty + cp * r_3d,
                               tz + axis_y_3d.z() * sp * r_3d)
            p_x_doc, _ = project_camera_point(self.camera, view_mat, p_x_3d.x(), p_x_3d.y(), p_x_3d.z(), render_size, offset_x, offset_y)
            if p_x_doc:
                rot_pts_x.append(self._doc_to_widget(p_x_doc))

            p_y_3d = QVector3D(tx + axis_x_3d.x() * cp * r_3d,
                               ty + sp * r_3d,
                               tz + axis_x_3d.z() * cp * r_3d)
            p_y_doc, _ = project_camera_point(self.camera, view_mat, p_y_3d.x(), p_y_3d.y(), p_y_3d.z(), render_size, offset_x, offset_y)
            if p_y_doc:
                rot_pts_y.append(self._doc_to_widget(p_y_doc))

        return {
            "origin_w": origin_w,
            "dir_x": dir_x, "dir_y": dir_y, "dir_z": dir_z,
            "tip_x": tip_x, "tip_y": tip_y, "tip_z": tip_z,
            "axis_x_3d": axis_x_3d, "axis_y_3d": axis_y_3d, "axis_z_3d": axis_z_3d,
            "plane_xy_pt": plane_xy_pt, "plane_xz_pt": plane_xz_pt, "plane_yz_pt": plane_yz_pt,
            "rot_pts_z": rot_pts_z, "rot_pts_x": rot_pts_x, "rot_pts_y": rot_pts_y,
            "gizmo_radius": gizmo_radius,
            "center_rect": QRectF(origin_w.x() - 11, origin_w.y() - 11, 22, 22)
        }

    def _hit_test_3d_gizmo(self, pos):
        """
        Hit-tests mouse position against all 3D Blender-style gizmo elements.
        Returns the hit element key or None.
        """
        geom = self._compute_3d_gizmo_geometry()
        if not geom:
            return None

        o = geom["origin_w"]
        p = QPointF(pos)

        # Center disc (View-plane move / uniform scale)
        if math.hypot(p.x() - o.x(), p.y() - o.y()) <= 13.0:
            return "center"

        mode = getattr(self, "gizmo_mode", "all")

        # 1. Translation / Scale tip handles
        if mode in ("move", "all"):
            if math.hypot(p.x() - geom["plane_xy_pt"].x(), p.y() - geom["plane_xy_pt"].y()) <= 12.0:
                return "plane_xy"
            if math.hypot(p.x() - geom["plane_xz_pt"].x(), p.y() - geom["plane_xz_pt"].y()) <= 12.0:
                return "plane_xz"
            if math.hypot(p.x() - geom["plane_yz_pt"].x(), p.y() - geom["plane_yz_pt"].y()) <= 12.0:
                return "plane_yz"

            if math.hypot(p.x() - geom["tip_x"].x(), p.y() - geom["tip_x"].y()) <= 14.0 or pt_dist_to_segment(p, o, geom["tip_x"]) <= 6.0:
                return "trans_x"
            if math.hypot(p.x() - geom["tip_y"].x(), p.y() - geom["tip_y"].y()) <= 14.0 or pt_dist_to_segment(p, o, geom["tip_y"]) <= 6.0:
                return "trans_y"
            if math.hypot(p.x() - geom["tip_z"].x(), p.y() - geom["tip_z"].y()) <= 14.0 or pt_dist_to_segment(p, o, geom["tip_z"]) <= 6.0:
                return "trans_z"

        if mode == "scale":
            if math.hypot(p.x() - geom["tip_x"].x(), p.y() - geom["tip_x"].y()) <= 14.0:
                return "scale_x"
            if math.hypot(p.x() - geom["tip_y"].x(), p.y() - geom["tip_y"].y()) <= 14.0:
                return "scale_y"
            if math.hypot(p.x() - geom["tip_z"].x(), p.y() - geom["tip_z"].y()) <= 14.0:
                return "scale_z"

        # 2. Rotation rings
        if mode in ("rotate", "all"):
            # Blue Yaw ring (around ground up)
            pts_z = geom.get("rot_pts_z", [])
            for i in range(len(pts_z) - 1):
                if pt_dist_to_segment(p, pts_z[i], pts_z[i+1]) <= 7.0:
                    return "rot_z"

            if mode == "rotate":
                pts_x = geom.get("rot_pts_x", [])
                for i in range(len(pts_x) - 1):
                    if pt_dist_to_segment(p, pts_x[i], pts_x[i+1]) <= 7.0:
                        return "rot_x"

                pts_y = geom.get("rot_pts_y", [])
                for i in range(len(pts_y) - 1):
                    if pt_dist_to_segment(p, pts_y[i], pts_y[i+1]) <= 7.0:
                        return "rot_y"

                # Outer view ring
                dist_o = math.hypot(p.x() - o.x(), p.y() - o.y())
                if abs(dist_o - geom["gizmo_radius"] * 1.25) <= 7.0:
                    return "rot_view"

        return None

    def _start_3d_gizmo_action(self, part, pos):
        """Initiates an interactive 3D transformation on the 3D object."""
        self.active_gizmo_part = part
        self.drag_start_mouse_pos = QPointF(pos)
        sol = self.last_solution
        self.drag_start_obj_state = {
            "tx": sol.get("target_x", 0.0),
            "ty": sol.get("target_y", 0.0),
            "tz": sol.get("target_z", 0.0),
            "rw": sol.get("rect_width", 2.0),
            "rd": sol.get("rect_depth", 2.0),
            "rh": sol.get("rect_height", 2.0),
            "yaw": sol.get("yaw", 180.0),
            "pitch": sol.get("pitch", 15.0),
            "roll": sol.get("roll", 0.0),
        }
        geom = self._compute_3d_gizmo_geometry()
        o = geom["origin_w"] if geom else pos
        self.drag_start_angle = math.atan2(pos.y() - o.y(), pos.x() - o.x())
        self.drag_start_dist = max(10.0, math.hypot(pos.x() - o.x(), pos.y() - o.y()))

        if "trans" in part or part == "center":
            self.setCursor(Qt.SizeAllCursor)
            self.guidance_changed.emit(f"✥ Moving 3D Object along {part.upper()}: Drag across canvas. Pins adapt dynamically.", "info")
        elif "rot" in part:
            self.setCursor(Qt.PointingHandCursor)
            self.guidance_changed.emit(f"⟳ Rotating 3D Object: Drag around center. Ground corners follow model rotation.", "info")
        elif "scale" in part:
            self.setCursor(Qt.SizeFDiagCursor)
            self.guidance_changed.emit(f"⤢ Scaling 3D Object: Drag outward/inward. Base rectangle resizes to match.", "info")
        elif "plane" in part:
            self.setCursor(Qt.SizeAllCursor)
            self.guidance_changed.emit(f"✥ Sliding 3D Object on Ground Plane: Drag across ground. Pins adapt dynamically.", "info")

    def _update_pins_from_3d_object(self):
        """
        Projects the 3D object's transformed base rectangle (and height) through
        the camera onto the canvas, adapting the 4 ground corner pins and height pin.
        """
        sol = self.last_solution
        if not sol or not self.camera:
            return

        tx = sol.get("target_x", 0.0)
        ty = sol.get("target_y", 0.0)
        tz = sol.get("target_z", 0.0)
        rw = sol.get("rect_width", 2.0)
        rd = sol.get("rect_depth", 2.0)
        rh = sol.get("rect_height", 2.0)
        yaw = sol.get("yaw", 180.0)
        flip = getattr(self, "flip_yaw", False)

        hw = rw * 0.5
        hd = rd * 0.5

        r_yaw = math.radians(yaw)
        cos_y = math.cos(r_yaw)
        sin_y = math.sin(r_yaw)

        def rot_xz(lx, lz):
            rx = lx * cos_y - lz * sin_y
            rz = lx * sin_y + lz * cos_y
            return tx + rx, tz + rz

        if not flip:
            c0_x, c0_z = rot_xz(hw, -hd)   # 1 FL
            c1_x, c1_z = rot_xz(-hw, -hd)  # 2 FR
            c2_x, c2_z = rot_xz(-hw, hd)   # 3 BR
            c3_x, c3_z = rot_xz(hw, hd)    # 4 BL
        else:
            c0_x, c0_z = rot_xz(-hw, hd)
            c1_x, c1_z = rot_xz(hw, hd)
            c2_x, c2_z = rot_xz(hw, -hd)
            c3_x, c3_z = rot_xz(-hw, -hd)

        corners_3d = [
            QVector3D(c0_x, ty, c0_z),
            QVector3D(c1_x, ty, c1_z),
            QVector3D(c2_x, ty, c2_z),
            QVector3D(c3_x, ty, c3_z),
        ]
        sol["corners_3d"] = corners_3d

        doc_w, doc_h = self._get_doc_size()
        render_size = min(doc_w, doc_h)
        offset_x = (doc_w - render_size) * 0.5
        offset_y = (doc_h - render_size) * 0.5
        _, view_mat, _ = self.camera.get_matrices(render_size, render_size)

        new_norm_points = []
        for c in corners_3d:
            pt, _ = project_camera_point(self.camera, view_mat, c.x(), c.y(), c.z(),
                                         render_size, offset_x, offset_y)
            if pt:
                new_norm_points.append(QPointF(max(0.001, min(0.999, pt.x() / doc_w)),
                                               max(0.001, min(0.999, pt.y() / doc_h))))
        if len(new_norm_points) == 4:
            self.norm_points = new_norm_points

        if getattr(self, 'has_height_point', False):
            pt_top, _ = project_camera_point(self.camera, view_mat, corners_3d[0].x(), corners_3d[0].y() + rh, corners_3d[0].z(),
                                             render_size, offset_x, offset_y)
            if pt_top:
                self.height_norm_pt = QPointF(max(0.001, min(0.999, pt_top.x() / doc_w)),
                                              max(0.001, min(0.999, pt_top.y() / doc_h)))


    def _compute_initial_norm_points(self):
        doc_w, doc_h = self._get_doc_size()
        if (self.mesh and hasattr(self.mesh, 'bbox_min') and hasattr(self.mesh, 'bbox_max')
                and self.camera and doc_w > 0 and doc_h > 0):
            try:
                ground_y = self.mesh.bbox_min.y()
                hw = max(0.1, (self.mesh.bbox_max.x() - self.mesh.bbox_min.x()) * 0.5)
                hd = max(0.1, (self.mesh.bbox_max.z() - self.mesh.bbox_min.z()) * 0.5)
                tx = (self.mesh.bbox_min.x() + self.mesh.bbox_max.x()) * 0.5
                tz = (self.mesh.bbox_min.z() + self.mesh.bbox_max.z()) * 0.5

                corners = [
                    QVector3D(tx + hw, ground_y, tz - hd),
                    QVector3D(tx - hw, ground_y, tz - hd),
                    QVector3D(tx - hw, ground_y, tz + hd),
                    QVector3D(tx + hw, ground_y, tz + hd),
                ]

                render_size = min(doc_w, doc_h)
                offset_x = (doc_w - render_size) * 0.5
                offset_y = (doc_h - render_size) * 0.5
                _, view_mat, _ = self.camera.get_matrices(render_size, render_size)

                pts_norm = []
                for c in corners:
                    pt, ndc_z = project_camera_point(self.camera, view_mat, c.x(), c.y(), c.z(),
                                                     render_size, offset_x, offset_y)
                    if pt is not None and -0.1 * doc_w <= pt.x() <= 1.1 * doc_w and -0.1 * doc_h <= pt.y() <= 1.1 * doc_h:
                        pts_norm.append(QPointF(max(0.01, min(0.99, pt.x() / doc_w)),
                                                max(0.01, min(0.99, pt.y() / doc_h))))
                if len(pts_norm) == 4:
                    return pts_norm
            except Exception:
                pass

        return [
            QPointF(0.25, 0.78),  # 0: Front-Left
            QPointF(0.75, 0.78),  # 1: Front-Right
            QPointF(0.62, 0.48),  # 2: Back-Right
            QPointF(0.38, 0.48),  # 3: Back-Left
        ]

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

    def start_drag_mode(self):
        """Activates click-and-drag ground rectangle mode."""
        self.is_drag_mode = True
        self.is_picking_mode = False
        self.picked_points = []
        self.drag_start_pos = None
        self.setCursor(Qt.CrossCursor)
        self.guidance_changed.emit("✏️ Draw Mode: Click and drag across the canvas to outline your ground rectangle.", "info")
        self.update()

    def start_pick_mode(self, num_points=4):
        """Activates sequential 4-point or 5-point placement mode (FL, FR, BR, BL, [H])."""
        self.is_picking_mode = True
        self.pick_mode_points = max(4, min(5, int(num_points)))
        self.is_drag_mode = False
        self.picked_points = []
        self.drag_start_pos = None
        self.setCursor(Qt.CrossCursor)
        self.guidance_changed.emit(f"👉 [Step 1 of {self.pick_mode_points}] Click the FRONT-LEFT (1 FL) corner of your ground rectangle.", "info")
        self.update()

    def reset_points(self):
        self.norm_points = [
            QPointF(0.25, 0.78),
            QPointF(0.75, 0.78),
            QPointF(0.62, 0.48),
            QPointF(0.38, 0.48),
        ]
        self.has_height_point = False
        self.height_norm_pt = None
        self.is_picking_mode = False
        self.is_drag_mode = False
        self.drag_start_pos = None
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
        self.is_picking_mode = False
        self.is_drag_mode = False
        self.drag_start_pos = None
        self.setCursor(Qt.ArrowCursor)
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
        pts = [
            QPointF(
                self.img_rect.x() + p.x() * self.img_rect.width(),
                self.img_rect.y() + p.y() * self.img_rect.height()
            )
            for p in self.norm_points
        ]
        if getattr(self, 'has_height_point', False) and getattr(self, 'height_norm_pt', None):
            pts.append(
                QPointF(
                    self.img_rect.x() + self.height_norm_pt.x() * self.img_rect.width(),
                    self.img_rect.y() + self.height_norm_pt.y() * self.img_rect.height()
                )
            )
        return pts

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

        corners_3d = self.last_solution.get("corners_3d")
        base_corner_3d = corners_3d[0] if (corners_3d and len(corners_3d) > 0) else QVector3D(0, 0, 0)

        # 5-point height calculation
        if getattr(self, 'has_height_point', False):
            if self.height_norm_pt is not None:
                rh = solve_height_from_point(self.camera, doc_w, doc_h, base_corner_3d, self.height_norm_pt, self.frame_rect)
                self.last_solution["rect_height"] = rh
            else:
                rh = self.last_solution.get("rect_height", 2.0)
                self.height_norm_pt = project_height_to_norm_point(self.camera, doc_w, doc_h, base_corner_3d, rh, self.frame_rect)
        elif self.mesh and hasattr(self.mesh, 'primitive_params') and 'h' in self.mesh.primitive_params:
            self.last_solution["rect_height"] = float(self.mesh.primitive_params['h'])

        if not self.is_picking_mode and not self.is_drag_mode:
            is_valid, level, msg = validate_ground_quad(doc_pts[0], doc_pts[1], doc_pts[2], doc_pts[3])
            if is_valid:
                ptype = self.last_solution.get("primitive_type")
                rw = self.last_solution.get("rect_width", 2.0)
                rd = self.last_solution.get("rect_depth", 2.0)
                rh = self.last_solution.get("rect_height", 2.0)
                h_note = f" × {rh:.2f} (H)" if getattr(self, 'has_height_point', False) else ""
                if ptype == "Box":
                    msg = f"✔ Perspective matched: Box resized to {rw:.2f} (W) × {rd:.2f} (D){h_note} on ground."
                elif ptype == "Pyramid":
                    msg = f"✔ Perspective matched: Pyramid base resized to {rw:.2f} (W) × {rd:.2f} (D){h_note} on ground."
                elif ptype == "Sphere":
                    sr = self.last_solution.get("sphere_radius", 1.0)
                    msg = f"✔ Perspective matched: Sphere (radius {sr:.2f}) placed resting above ground rectangle."
                elif self.mesh:
                    msg = f"✔ Perspective matched: 3D model scaled to {rw:.2f} × {rd:.2f} footprint on ground rectangle."
                else:
                    msg = f"✔ Perspective matched: Ground rectangle {rw:.2f} × {rd:.2f}{h_note} solved."
            self.guidance_changed.emit(msg, level)

        self.solution_changed.emit(self.last_solution)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            if self.is_picking_mode or self.is_drag_mode:
                self.is_picking_mode = False
                self.is_drag_mode = False
                self.picked_points = []
                self.drag_start_pos = None
                self.setCursor(Qt.ArrowCursor)
                self.guidance_changed.emit("Drawing mode cancelled. Drag handles to refine perspective.", "info")
                self.update()
                event.accept()
                return
        elif event.key() in (Qt.Key_G, Qt.Key_G + 32):
            self.set_gizmo_mode('move')
            event.accept()
            return
        elif event.key() in (Qt.Key_R, Qt.Key_R + 32):
            self.set_gizmo_mode('rotate')
            event.accept()
            return
        elif event.key() in (Qt.Key_S, Qt.Key_S + 32):
            self.set_gizmo_mode('scale')
            event.accept()
            return
        elif event.key() in (Qt.Key_A, Qt.Key_A + 32):
            self.set_gizmo_mode('all')
            event.accept()
            return
        super().keyPressEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            pos = event.pos()

            # 1. Sequential 4-point or 5-point picking mode
            if self.is_picking_mode:
                norm_pt = self._widget_to_doc_norm(pos)
                self.picked_points.append(norm_pt)
                n = len(self.picked_points)
                target_count = getattr(self, 'pick_mode_points', 4)
                if n == 1:
                    self.guidance_changed.emit(f"👉 [Step 2 of {target_count}] Click FRONT-RIGHT (2 FR) corner (to the right of Front-Left).", "info")
                elif n == 2:
                    self.guidance_changed.emit(f"👉 [Step 3 of {target_count}] Click BACK-RIGHT (3 BR) corner (receding towards horizon).", "info")
                elif n == 3:
                    self.guidance_changed.emit(f"👉 [Step 4 of {target_count}] Click BACK-LEFT (4 BL) corner (receding towards horizon, left of Back-Right).", "info")
                elif n == 4:
                    if target_count == 4:
                        self.norm_points = list(self.picked_points[:4])
                        self.has_height_point = False
                        self.height_norm_pt = None
                        self.is_picking_mode = False
                        self.setCursor(Qt.ArrowCursor)
                        self._recalculate()
                    else:
                        self.norm_points = list(self.picked_points[:4])
                        self._recalculate()
                        self.guidance_changed.emit("👉 [Step 5 of 5] Click to define HEIGHT (5 H) (above Front-Left corner in perspective).", "info")
                elif n == 5:
                    self.norm_points = list(self.picked_points[:4])
                    self.has_height_point = True
                    self.height_norm_pt = self.picked_points[4]
                    self.is_picking_mode = False
                    self.setCursor(Qt.ArrowCursor)
                    self._recalculate()
                self.update()
                event.accept()
                return

            # 2. Click-and-drag ground rectangle mode
            if self.is_drag_mode:
                self.drag_start_pos = pos
                event.accept()
                return

            # 3. Check Corner Pin handles (1..4 + 5 H)
            pts = self._get_widget_points()
            for idx, pt in enumerate(pts):
                dist = (pt - QPointF(pos)).manhattanLength()
                if dist <= self.HANDLE_RADIUS + 6:
                    self.active_handle = idx
                    event.accept()
                    return

            # 4. Check 3D Blender-Style Transform Gizmo handles (Move, Rotate, Scale)
            hit_part = self._hit_test_3d_gizmo(pos)
            if hit_part:
                self._start_3d_gizmo_action(hit_part, pos)
                event.accept()
                return

            # 5. Check Quad interior with modifier keys (Shift: Scale, Ctrl/Alt: Rotate, Normal: Move Ground Plane)
            p0, p1, p2, p3 = pts[:4]
            quad_poly = QPolygonF([p0, p1, p2, p3])
            if quad_poly.containsPoint(pos, Qt.OddEvenFill):
                mods = event.modifiers()
                if mods & Qt.ShiftModifier:
                    self._start_3d_gizmo_action('scale_uniform', pos)
                elif mods & (Qt.ControlModifier | Qt.AltModifier):
                    self._start_3d_gizmo_action('rot_z', pos)
                else:
                    self._start_3d_gizmo_action('plane_xy', pos)
                event.accept()
                return

            # 6. Check Horizon Line grab
            if self._distance_to_horizon(pos) <= 8.0:
                self.is_dragging_horizon = True
                self.drag_start_mouse_pos = QPointF(pos)
                self.drag_start_pitch = self.last_solution.get("pitch", 15.0)
                self.guidance_changed.emit("↔ Horizon Line Grabbed: Drag up or down to adjust camera eye-level tilt (pitch).", "info")
                event.accept()
                return

        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        pos = event.pos()
        self.current_cursor_pos = pos

        # Picking mode
        if self.is_picking_mode:
            self.update()
            event.accept()
            return

        # Drag mode
        if self.is_drag_mode and self.drag_start_pos:
            p0 = self._widget_to_doc_norm(self.drag_start_pos)
            p1 = self._widget_to_doc_norm(pos)
            x0, x1 = min(p0.x(), p1.x()), max(p0.x(), p1.x())
            y0, y1 = min(p0.y(), p1.y()), max(p0.y(), p1.y())
            mx = (x0 + x1) * 0.5
            hw = (x1 - x0) * 0.5
            self.norm_points = [
                QPointF(x0, y1),
                QPointF(x1, y1),
                QPointF(mx + hw * 0.75, y0),
                QPointF(mx - hw * 0.75, y0)
            ]
            self._recalculate()
            self.update()
            event.accept()
            return

        # Horizon Line Dragging: smoothly moves horizon line up/down and shifts camera pitch
        if self.is_dragging_horizon and self.drag_start_mouse_pos:
            dy_widget = pos.y() - self.drag_start_mouse_pos.y()
            doc_w, doc_h = self._get_doc_size()
            scale_y = doc_h / max(1.0, self.img_rect.height())
            dy_doc = dy_widget * scale_y

            cur_fov = self.last_solution.get("fov", 45.0)
            half_size = min(doc_w, doc_h) * 0.5
            f = half_size / math.tan(math.radians(max(5.0, min(160.0, cur_fov)) * 0.5))
            cy = doc_h * 0.5

            y_start = cy - f * math.tan(math.radians(self.drag_start_pitch))
            y_new = y_start + dy_doc

            ratio = (cy - y_new) / f
            new_pitch = math.degrees(math.atan(ratio))
            new_pitch = max(-85.0, min(85.0, new_pitch))

            corners_3d = self.last_solution.get("corners_3d")
            if corners_3d and len(corners_3d) == 4 and self.camera:
                cam_temp = Camera3D()
                cam_temp.yaw = self.last_solution.get("yaw", 180.0)
                cam_temp.pitch = new_pitch
                cam_temp.roll = self.last_solution.get("roll", 0.0)
                cam_temp.fov = cur_fov
                cam_temp.distance = self.last_solution.get("distance", 3.0)
                cam_temp.pan_x = self.last_solution.get("pan_x", 0.0)
                cam_temp.pan_y = self.last_solution.get("pan_y", 0.0)
                cam_temp.target_x = self.last_solution.get("target_x", 0.0)
                cam_temp.target_y = self.last_solution.get("target_y", 0.0)
                cam_temp.target_z = self.last_solution.get("target_z", 0.0)

                render_size = min(doc_w, doc_h)
                offset_x = (doc_w - render_size) * 0.5
                offset_y = (doc_h - render_size) * 0.5
                _, view_mat, _ = cam_temp.get_matrices(render_size, render_size)

                new_pts = []
                for c in corners_3d:
                    pt, _ = project_camera_point(cam_temp, view_mat, c.x(), c.y(), c.z(),
                                                 render_size, offset_x, offset_y)
                    if pt:
                        new_pts.append(QPointF(max(0.001, min(0.999, pt.x() / doc_w)),
                                               max(0.001, min(0.999, pt.y() / doc_h))))
                if len(new_pts) == 4:
                    self.norm_points = new_pts

            self._recalculate()
            self.update()
            event.accept()
            return

        # 3D Blender-Style Gizmo Action Dragging
        if getattr(self, 'active_gizmo_part', None) is not None and self.drag_start_mouse_pos:
            part = self.active_gizmo_part
            dx = pos.x() - self.drag_start_mouse_pos.x()
            dy = pos.y() - self.drag_start_mouse_pos.y()

            geom = self._compute_3d_gizmo_geometry()
            sol = self.last_solution
            st = self.drag_start_obj_state
            if geom and sol and st:
                doc_w, doc_h = self._get_doc_size()
                render_size = min(doc_w, doc_h)
                cam = self.camera
                cur_dist = sol.get("distance", cam.distance if cam else 4.0)
                cur_fov = sol.get("fov", cam.fov if cam else 45.0)
                world_scale = (2.0 * cur_dist * math.tan(math.radians(max(5.0, min(160.0, cur_fov)) * 0.5))) / max(100.0, render_size)
                scale_screen = doc_w / max(1.0, self.img_rect.width())
                w_factor = world_scale * scale_screen

                dir_x = geom["dir_x"]
                dir_y = geom["dir_y"]
                dir_z = geom["dir_z"]
                ax_x = geom["axis_x_3d"]
                ax_y = geom["axis_y_3d"]

                # Translations
                if part == 'trans_x':
                    proj = dx * dir_x.x() + dy * dir_x.y()
                    delta_w = proj * w_factor
                    sol["target_x"] = st["tx"] + delta_w * ax_x.x()
                    sol["target_z"] = st["tz"] + delta_w * ax_x.z()
                    self.guidance_changed.emit(f"✥ Moving 3D Object [X]: Δ {delta_w:+.2f} (X: {sol['target_x']:.2f}, Z: {sol['target_z']:.2f})", "info")
                elif part == 'trans_y':
                    proj = dx * dir_y.x() + dy * dir_y.y()
                    delta_w = proj * w_factor
                    sol["target_x"] = st["tx"] + delta_w * ax_y.x()
                    sol["target_z"] = st["tz"] + delta_w * ax_y.z()
                    self.guidance_changed.emit(f"✥ Moving 3D Object [Y / Ground Depth]: Δ {delta_w:+.2f} (X: {sol['target_x']:.2f}, Z: {sol['target_z']:.2f})", "info")
                elif part == 'trans_z':
                    proj = dx * dir_z.x() + dy * dir_z.y()
                    delta_w = proj * w_factor
                    sol["target_y"] = st["ty"] + delta_w
                    self.guidance_changed.emit(f"✥ Moving 3D Object [Z / Elevation Up]: Δ {delta_w:+.2f} (Height: {sol['target_y']:.2f})", "info")
                elif part in ('plane_xy', 'center'):
                    proj_x = dx * dir_x.x() + dy * dir_x.y()
                    proj_y = dx * dir_y.x() + dy * dir_y.y()
                    sol["target_x"] = st["tx"] + (proj_x * ax_x.x() + proj_y * ax_y.x()) * w_factor
                    sol["target_z"] = st["tz"] + (proj_x * ax_x.z() + proj_y * ax_y.z()) * w_factor
                    self.guidance_changed.emit(f"✥ Sliding 3D Object on Ground: (X: {sol['target_x']:.2f}, Z: {sol['target_z']:.2f})", "info")
                elif part == 'plane_xz':
                    proj_x = dx * dir_x.x() + dy * dir_x.y()
                    proj_z = dx * dir_z.x() + dy * dir_z.y()
                    sol["target_x"] = st["tx"] + proj_x * ax_x.x() * w_factor
                    sol["target_z"] = st["tz"] + proj_x * ax_x.z() * w_factor
                    sol["target_y"] = st["ty"] + proj_z * w_factor
                    self.guidance_changed.emit(f"✥ Moving in XZ plane: (X: {sol['target_x']:.2f}, Y: {sol['target_y']:.2f})", "info")
                elif part == 'plane_yz':
                    proj_y = dx * dir_y.x() + dy * dir_y.y()
                    proj_z = dx * dir_z.x() + dy * dir_z.y()
                    sol["target_x"] = st["tx"] + proj_y * ax_y.x() * w_factor
                    sol["target_z"] = st["tz"] + proj_y * ax_y.z() * w_factor
                    sol["target_y"] = st["ty"] + proj_z * w_factor
                    self.guidance_changed.emit(f"✥ Moving in YZ plane: (Y: {sol['target_y']:.2f}, Z: {sol['target_z']:.2f})", "info")

                # Rotations
                elif part in ('rot_z', 'rot_view'):
                    o = geom["origin_w"]
                    ang_curr = math.atan2(pos.y() - o.y(), pos.x() - o.x())
                    ang_delta = math.degrees(ang_curr - self.drag_start_angle)
                    new_yaw = (st["yaw"] + ang_delta) % 360.0
                    sol["yaw"] = new_yaw
                    self.guidance_changed.emit(f"⟳ Rotating Yaw (Ground Up): {new_yaw:.1f}° (Δ {ang_delta:+.1f}°)", "info")
                elif part == 'rot_x':
                    o = geom["origin_w"]
                    ang_curr = math.atan2(pos.y() - o.y(), pos.x() - o.x())
                    ang_delta = math.degrees(ang_curr - self.drag_start_angle)
                    new_pitch = max(-85.0, min(85.0, st["pitch"] + ang_delta))
                    sol["pitch"] = new_pitch
                    self.guidance_changed.emit(f"⟳ Rotating Pitch: {new_pitch:.1f}°", "info")
                elif part == 'rot_y':
                    o = geom["origin_w"]
                    ang_curr = math.atan2(pos.y() - o.y(), pos.x() - o.x())
                    ang_delta = math.degrees(ang_curr - self.drag_start_angle)
                    new_roll = max(-85.0, min(85.0, st["roll"] + ang_delta))
                    sol["roll"] = new_roll
                    self.guidance_changed.emit(f"⟳ Rotating Roll: {new_roll:.1f}°", "info")

                # Scales
                elif part == 'scale_x':
                    proj = dx * dir_x.x() + dy * dir_x.y()
                    s = max(0.1, 1.0 + proj / 50.0)
                    new_rw = max(0.2, min(50.0, st["rw"] * s))
                    sol["rect_width"] = new_rw
                    self.guidance_changed.emit(f"⤢ Scaling Width (X): {new_rw:.2f} (W {new_rw:.2f} × D {sol.get('rect_depth', 2.0):.2f})", "info")
                elif part == 'scale_y':
                    proj = dx * dir_y.x() + dy * dir_y.y()
                    s = max(0.1, 1.0 + proj / 50.0)
                    new_rd = max(0.2, min(50.0, st["rd"] * s))
                    sol["rect_depth"] = new_rd
                    self.guidance_changed.emit(f"⤢ Scaling Depth (Y): {new_rd:.2f} (W {sol.get('rect_width', 2.0):.2f} × D {new_rd:.2f})", "info")
                elif part == 'scale_z':
                    proj = dx * dir_z.x() + dy * dir_z.y()
                    s = max(0.1, 1.0 + proj / 50.0)
                    new_rh = max(0.2, min(50.0, st["rh"] * s))
                    sol["rect_height"] = new_rh
                    self.guidance_changed.emit(f"⤢ Scaling Height (Z): {new_rh:.2f} (Height: {new_rh:.2f})", "info")
                elif part == 'scale_uniform':
                    o = geom["origin_w"]
                    dist_curr = math.hypot(pos.x() - o.x(), pos.y() - o.y())
                    s = max(0.1, dist_curr / max(10.0, self.drag_start_dist))
                    new_rw = max(0.2, min(50.0, st["rw"] * s))
                    new_rd = max(0.2, min(50.0, st["rd"] * s))
                    new_rh = max(0.2, min(50.0, st["rh"] * s))
                    sol["rect_width"] = new_rw
                    sol["rect_depth"] = new_rd
                    sol["rect_height"] = new_rh
                    self.guidance_changed.emit(f"⤢ Uniform Scaling: {s:.2f}× (W {new_rw:.2f} × D {new_rd:.2f} × H {new_rh:.2f})", "info")

                # Project 3D object base corners onto 2D canvas pins!
                self._update_pins_from_3d_object()

            self.update()
            event.accept()
            return

        # Active Corner Pin Handle Dragging
        if self.active_handle is not None:
            norm_pt = self._widget_to_doc_norm(pos)
            if self.active_handle < 4:
                self.norm_points[self.active_handle] = norm_pt
                if getattr(self, 'has_height_point', False):
                    corners_3d = self.last_solution.get("corners_3d")
                    base_corner_3d = corners_3d[0] if (corners_3d and len(corners_3d) > 0) else QVector3D(0, 0, 0)
                    rh = self.last_solution.get("rect_height", 2.0)
                    doc_w, doc_h = self._get_doc_size()
                    self.height_norm_pt = project_height_to_norm_point(self.camera, doc_w, doc_h, base_corner_3d, rh, self.frame_rect)
            elif self.active_handle == 4:
                self.height_norm_pt = norm_pt
            self._recalculate()
            self.update()
            event.accept()
            return

        # Passive Hover State Detection
        pts = self._get_widget_points()
        self.hovered_handle = None
        for idx, pt in enumerate(pts):
            dist = (pt - QPointF(pos)).manhattanLength()
            if dist <= self.HANDLE_RADIUS + 6:
                self.hovered_handle = idx
                self.hover_gizmo_part = None
                self.hover_horizon = False
                self.setCursor(Qt.PointingHandCursor)
                break

        if self.hovered_handle is None:
            hit_part = self._hit_test_3d_gizmo(pos)
            if hit_part:
                self.hover_gizmo_part = hit_part
                self.hover_horizon = False
                if "trans" in hit_part or hit_part in ("center", "plane_xy", "plane_xz", "plane_yz"):
                    self.setCursor(Qt.SizeAllCursor)
                    if hit_part == "trans_x":
                        self.guidance_changed.emit("✥ 3D Axis [X Red]: Drag to move model laterally along ground.", "info")
                    elif hit_part == "trans_y":
                        self.guidance_changed.emit("✥ 3D Axis [Y Green]: Drag to move model in depth along ground.", "info")
                    elif hit_part == "trans_z":
                        self.guidance_changed.emit("✥ 3D Axis [Z Blue]: Drag to move model vertically Up/Down.", "info")
                    elif hit_part == "plane_xy":
                        self.guidance_changed.emit("✥ Ground Plane Slider: Drag to slide 3D model freely on ground plane.", "info")
                    else:
                        self.guidance_changed.emit("✥ Center Disc: Drag to move 3D model in view plane.", "info")
                elif "rot" in hit_part:
                    self.setCursor(Qt.PointingHandCursor)
                    if hit_part == "rot_z":
                        self.guidance_changed.emit("⟳ Blue Yaw Ring: Drag around center to rotate 3D object on ground.", "info")
                    elif hit_part == "rot_x":
                        self.guidance_changed.emit("⟳ Red Pitch Ring: Drag to tilt 3D object forward/backward.", "info")
                    elif hit_part == "rot_y":
                        self.guidance_changed.emit("⟳ Green Roll Ring: Drag to roll 3D object side to side.", "info")
                    else:
                        self.guidance_changed.emit("⟳ View Ring: Drag to rotate view-aligned roll.", "info")
                elif "scale" in hit_part:
                    self.setCursor(Qt.SizeFDiagCursor)
                    self.guidance_changed.emit("⤢ Scale Handle: Drag to scale 3D object dimension.", "info")
            else:
                self.hover_gizmo_part = None
                p0, p1, p2, p3 = pts[:4]
                quad_poly = QPolygonF([p0, p1, p2, p3])
                if quad_poly.containsPoint(pos, Qt.OddEvenFill):
                    self.hover_horizon = False
                    mods = event.modifiers()
                    if mods & Qt.ShiftModifier:
                        self.setCursor(Qt.SizeFDiagCursor)
                        self.guidance_changed.emit("⤢ Shift+Drag inside: Uniform Scale 3D Object.", "info")
                    elif mods & (Qt.ControlModifier | Qt.AltModifier):
                        self.setCursor(Qt.PointingHandCursor)
                        self.guidance_changed.emit("⟳ Ctrl+Drag inside: Rotate 3D Object (Yaw).", "info")
                    else:
                        self.setCursor(Qt.SizeAllCursor)
                        self.guidance_changed.emit("✥ Drag inside: Slide on ground  |  Shift+Drag: Scale  |  Ctrl+Drag: Rotate", "info")
                elif self._distance_to_horizon(pos) <= 8.0:
                    self.hover_horizon = True
                    self.setCursor(Qt.SizeVerCursor)
                    self.guidance_changed.emit("↕ Horizon Line: Drag up or down to tilt camera eye-level.", "info")
                else:
                    self.hover_horizon = False
                    if not self.is_drag_mode and not self.is_picking_mode:
                        self.setCursor(Qt.ArrowCursor)

        self.update()
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self.is_drag_mode and self.drag_start_pos:
            self.is_drag_mode = False
            self.drag_start_pos = None
            self.setCursor(Qt.ArrowCursor)
            self._recalculate()
            self.update()
            event.accept()
            return

        if self.active_handle is not None:
            self.active_handle = None
            self.update()
            event.accept()
            return

        if getattr(self, 'active_gizmo_part', None) is not None:
            self.active_gizmo_part = None
            self.drag_start_mouse_pos = None
            self.drag_start_obj_state = {}
            self.update()
            self._recalculate()
            event.accept()
            return

        if self.is_dragging_horizon:
            self.is_dragging_horizon = False
            self.drag_start_mouse_pos = None
            self.update()
            event.accept()
            return

        super().mouseReleaseEvent(event)

    def _paint_3d_blender_gizmo(self, painter):
        """
        Renders a Blender-style 3D Transform Gizmo directly at the 3D object center/base,
        with 3 colored axes (Red X, Green Y/Depth, Blue Z/Height Up), arrowheads,
        plane sliders, and 3D elliptical rotation tracks.
        """
        geom = self._compute_3d_gizmo_geometry()
        if not geom:
            return

        painter.save()
        painter.setRenderHint(QPainter.Antialiasing, True)

        o = geom["origin_w"]
        tip_x = geom["tip_x"]
        tip_y = geom["tip_y"]
        tip_z = geom["tip_z"]
        dir_x = geom["dir_x"]
        dir_y = geom["dir_y"]
        dir_z = geom["dir_z"]

        mode = getattr(self, "gizmo_mode", "all")
        active_part = getattr(self, "active_gizmo_part", None)
        hover_part = getattr(self, "hover_gizmo_part", None)

        col_x = QColor(239, 68, 68)    # Red (X - Width)
        col_y = QColor(34, 197, 94)    # Green (Y - Ground Depth)
        col_z = QColor(59, 130, 246)   # Blue (Z - Height Up)
        col_hi = QColor(255, 255, 255) # Hover/Active glow

        # 1. 3D Rotation Rings (drawn under axes)
        if mode in ("rotate", "all"):
            # Blue Yaw Ring (Ground Plane Up)
            pts_z = geom.get("rot_pts_z", [])
            if len(pts_z) >= 2:
                is_act_rz = (active_part == 'rot_z' or hover_part == 'rot_z')
                pen_rz = QPen(col_hi if is_act_rz else QColor(59, 130, 246, 210), 3.0 if is_act_rz else 1.8)
                painter.setPen(pen_rz)
                painter.drawPolyline(QPolygonF(pts_z))

            if mode == "rotate":
                # Red Pitch Ring
                pts_x = geom.get("rot_pts_x", [])
                if len(pts_x) >= 2:
                    is_act_rx = (active_part == 'rot_x' or hover_part == 'rot_x')
                    pen_rx = QPen(col_hi if is_act_rx else QColor(239, 68, 68, 180), 3.0 if is_act_rx else 1.6)
                    painter.setPen(pen_rx)
                    painter.drawPolyline(QPolygonF(pts_x))

                # Green Roll Ring
                pts_y = geom.get("rot_pts_y", [])
                if len(pts_y) >= 2:
                    is_act_ry = (active_part == 'rot_y' or hover_part == 'rot_y')
                    pen_ry = QPen(col_hi if is_act_ry else QColor(34, 197, 94, 180), 3.0 if is_act_ry else 1.6)
                    painter.setPen(pen_ry)
                    painter.drawPolyline(QPolygonF(pts_y))

                # Outer View-aligned Ring
                is_act_rv = (active_part == 'rot_view' or hover_part == 'rot_view')
                pen_rv = QPen(col_hi if is_act_rv else QColor(248, 250, 252, 100), 2.5 if is_act_rv else 1.2)
                painter.setPen(pen_rv)
                painter.setBrush(Qt.NoBrush)
                painter.drawEllipse(o, geom["gizmo_radius"] * 1.25, geom["gizmo_radius"] * 1.25)

        # 2. Plane Slider Handles (Ground XY, XZ, YZ)
        if mode in ("move", "all"):
            # XY Ground Plane corner
            is_act_pxy = (active_part == 'plane_xy' or hover_part == 'plane_xy')
            p_xy_poly = QPolygonF([
                o,
                QPointF(o.x() + dir_x.x() * 22, o.y() + dir_x.y() * 22),
                geom["plane_xy_pt"],
                QPointF(o.x() + dir_y.x() * 22, o.y() + dir_y.y() * 22)
            ])
            painter.setBrush(QBrush(QColor(56, 189, 248, 140 if is_act_pxy else 60)))
            painter.setPen(QPen(col_hi if is_act_pxy else QColor(56, 189, 248, 200), 1.5))
            painter.drawPolygon(p_xy_poly)

            if mode == "move":
                # XZ Plane corner
                is_act_pxz = (active_part == 'plane_xz' or hover_part == 'plane_xz')
                p_xz_poly = QPolygonF([
                    o,
                    QPointF(o.x() + dir_x.x() * 22, o.y() + dir_x.y() * 22),
                    geom["plane_xz_pt"],
                    QPointF(o.x() + dir_z.x() * 22, o.y() + dir_z.y() * 22)
                ])
                painter.setBrush(QBrush(QColor(239, 68, 68, 140 if is_act_pxz else 50)))
                painter.setPen(QPen(col_hi if is_act_pxz else QColor(239, 68, 68, 180), 1.5))
                painter.drawPolygon(p_xz_poly)

                # YZ Plane corner
                is_act_pyz = (active_part == 'plane_yz' or hover_part == 'plane_yz')
                p_yz_poly = QPolygonF([
                    o,
                    QPointF(o.x() + dir_y.x() * 22, o.y() + dir_y.y() * 22),
                    geom["plane_yz_pt"],
                    QPointF(o.x() + dir_z.x() * 22, o.y() + dir_z.y() * 22)
                ])
                painter.setBrush(QBrush(QColor(34, 197, 94, 140 if is_act_pyz else 50)))
                painter.setPen(QPen(col_hi if is_act_pyz else QColor(34, 197, 94, 180), 1.5))
                painter.drawPolygon(p_yz_poly)

        # 3. Axis Shafts
        is_act_x = (active_part in ('trans_x', 'scale_x') or hover_part in ('trans_x', 'scale_x'))
        is_act_y = (active_part in ('trans_y', 'scale_y') or hover_part in ('trans_y', 'scale_y'))
        is_act_z = (active_part in ('trans_z', 'scale_z') or hover_part in ('trans_z', 'scale_z'))

        painter.setPen(QPen(col_hi if is_act_x else col_x, 3.0 if is_act_x else 2.2))
        painter.drawLine(o, tip_x)

        painter.setPen(QPen(col_hi if is_act_y else col_y, 3.0 if is_act_y else 2.2))
        painter.drawLine(o, tip_y)

        painter.setPen(QPen(col_hi if is_act_z else col_z, 3.0 if is_act_z else 2.2))
        painter.drawLine(o, tip_z)

        # Helper: Arrowhead
        def draw_cone(tip, d_vec, col, is_act):
            cone_len = 13.0
            cone_w = 6.0
            perp = QPointF(-d_vec.y(), d_vec.x())
            base = QPointF(tip.x() - d_vec.x() * cone_len, tip.y() - d_vec.y() * cone_len)
            p_l = QPointF(base.x() + perp.x() * cone_w, base.y() + perp.y() * cone_w)
            p_r = QPointF(base.x() - perp.x() * cone_w, base.y() - perp.y() * cone_w)
            painter.setBrush(QBrush(col_hi if is_act else col))
            painter.setPen(QPen(col_hi if is_act else col.darker(130), 1.5))
            painter.drawPolygon(QPolygonF([tip, p_l, p_r]))

        # Helper: Scale Cube
        def draw_box_handle(tip, col, is_act):
            sz = 10.0
            r = QRectF(tip.x() - sz * 0.5, tip.y() - sz * 0.5, sz, sz)
            painter.setBrush(QBrush(col_hi if is_act else col))
            painter.setPen(QPen(col_hi if is_act else col.darker(130), 1.5))
            painter.drawRoundedRect(r, 2.0, 2.0)

        # Helper: Badge
        def draw_badge(tip, d_vec, label, col):
            bp = QPointF(tip.x() + d_vec.x() * 11, tip.y() + d_vec.y() * 11)
            painter.setBrush(QBrush(col.darker(160)))
            painter.setPen(QPen(col, 1.5))
            painter.drawEllipse(bp, 7, 7)
            painter.setFont(QFont("Segoe UI", 8, QFont.Bold))
            painter.setPen(QColor(255, 255, 255))
            painter.drawText(QRectF(bp.x() - 7, bp.y() - 7, 14, 14), Qt.AlignCenter, label)

        # 4. Axis Tips & Labels
        if mode in ("move", "all"):
            draw_cone(tip_x, dir_x, col_x, is_act_x)
            draw_cone(tip_y, dir_y, col_y, is_act_y)
            draw_cone(tip_z, dir_z, col_z, is_act_z)
        elif mode == "scale":
            draw_box_handle(tip_x, col_x, is_act_x)
            draw_box_handle(tip_y, col_y, is_act_y)
            draw_box_handle(tip_z, col_z, is_act_z)

        draw_badge(tip_x, dir_x, "X", col_x)
        draw_badge(tip_y, dir_y, "Y", col_y)
        draw_badge(tip_z, dir_z, "Z", col_z)

        # 5. Center View Disc
        is_act_c = (active_part in ('center', 'scale_uniform') or hover_part in ('center', 'scale_uniform'))
        painter.setBrush(QBrush(col_hi if is_act_c else QColor(255, 255, 255, 180)))
        painter.setPen(QPen(QColor(56, 189, 248) if is_act_c else QColor(15, 23, 42, 220), 2.0 if is_act_c else 1.5))
        painter.drawEllipse(o, 8, 8)

        painter.restore()


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
        p0, p1, p2, p3 = pts[:4]

        sol = self.last_solution

        # 2. Horizon Line (Grabbable with hover & dragging glow)
        h_p1, h_p2 = self._get_horizon_endpoints()
        is_h_active = self.hover_horizon or self.is_dragging_horizon
        if is_h_active:
            painter.setPen(QPen(QColor(250, 204, 21, 255), 2.5, Qt.SolidLine))
        else:
            painter.setPen(QPen(QColor(234, 179, 8, 190), 1.5, Qt.DashLine))
        painter.drawLine(h_p1, h_p2)

        # Horizon Label
        painter.setPen(QColor(250, 204, 21))
        painter.setFont(QFont("Segoe UI", 8, QFont.Bold))
        mid_y = int(max(16, min(h - 12, (h_p1.y() + h_p2.y()) * 0.5)))
        painter.drawText(int(self.img_rect.x() + 8), mid_y, "── Horizon Line (Eye Level) ──  [Drag Up/Down to Adjust Tilt]")

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

        # 4. Quad Fill and Perspective Edges
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

        # 5. LIVE 3D PREVIEW (Renders selected Primitive or Loaded 3D Model sitting on Ground)
        if self.renderer:
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
            cam_prev.ground_y = sol.get("target_y", 0.0)
            cam_prev.projection_mode = ProjectionMode.PERSPECTIVE
            cam_prev.orthographic = False

            ptype = getattr(self, 'primitive_type', 'Box')
            rw = max(0.1, float(sol.get("rect_width", 2.0)))
            rd = max(0.1, float(sol.get("rect_depth", 2.0)))
            rh = max(0.1, float(sol.get("rect_height", 2.0)))

            preview_mesh = None
            obj_trans = None

            if ptype == "Box":
                preview_mesh = create_box_primitive(rw, rh, rd)
            elif ptype == "Cylinder":
                preview_mesh = create_cylinder_primitive(radius=min(rw, rd) * 0.5, height=rh, segments=24)
            elif ptype == "Sphere":
                sr = min(rw, rd) * 0.5
                preview_mesh = create_sphere_primitive(radius=sr, rings=16, sectors=24)
                cam_prev.target_y = sol.get("target_y", 0.0) + sr
            elif ptype == "Pyramid":
                preview_mesh = create_pyramid_primitive(rw, rh, rd)
            elif ptype == "Cone":
                preview_mesh = create_cone_primitive(radius=min(rw, rd) * 0.5, height=rh, segments=24)
            elif ptype == "Plane":
                preview_mesh = create_plane_primitive(rw, rd, 2)
            elif ptype in ("Room", "Room (3 Planes)", "Room Corner"):
                preview_mesh = create_room_primitive(rw, rh, rd)
            elif ptype == "Loaded 3D Model" and self.mesh and getattr(self.mesh, 'vertices', None):
                preview_mesh = self.mesh
                obj_trans = ObjectTransform()
                obj_trans.scale_x = sol.get("scale_x", 1.0)
                obj_trans.scale_y = sol.get("scale_y", 1.0)
                obj_trans.scale_z = sol.get("scale_z", 1.0)
            elif self.mesh and getattr(self.mesh, 'vertices', None):
                preview_mesh = self.mesh
                obj_trans = ObjectTransform()
                obj_trans.scale_x = sol.get("scale_x", 1.0)
                obj_trans.scale_y = sol.get("scale_y", 1.0)
                obj_trans.scale_z = sol.get("scale_z", 1.0)
            else:
                preview_mesh = create_box_primitive(rw, rh, rd)

            if preview_mesh:
                prev_img = self.renderer.render_to_image(
                    mesh=preview_mesh,
                    camera=cam_prev,
                    lighting=self.lighting,
                    style=RenderStyle.SHADED_WIREFRAME,
                    width=pw,
                    height=ph,
                    bg_color=QColor(0, 0, 0, 0),
                    draw_model=True,
                    object_transform=obj_trans
                )
                painter.setOpacity(0.88)
                painter.drawImage(int(self.img_rect.x()), int(self.img_rect.y()), prev_img)
                painter.setOpacity(1.0)

        # 6. ON-SCREEN TRANSFORM GIZMO (Blender-Style 3D Transform Gizmo)
        self._paint_3d_blender_gizmo(painter)

        # 7. Corner Pin Handles (Pins)
        handle_colors = [
            QColor(34, 197, 94),   # 0: Front-Left (Green)
            QColor(239, 68, 68),   # 1: Front-Right (Red)
            QColor(59, 130, 246),  # 2: Back-Right (Blue)
            QColor(234, 179, 8),   # 3: Back-Left (Yellow)
            QColor(192, 132, 252), # 4: Height Pin (Purple)
        ]
        handle_names = ["1 FL", "2 FR", "3 BR", "4 BL", "5 H"]

        if getattr(self, 'has_height_point', False) and len(pts) >= 5:
            # Draw vertical guide dashed line from base FL (pts[0]) to height pin (pts[4])
            h_pen = QPen(QColor(192, 132, 252, 220), 1.5, Qt.DashLine)
            painter.setPen(h_pen)
            painter.drawLine(pts[0], pts[4])

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
            if idx == 4:
                rh = sol.get("rect_height", 2.0)
                painter.drawText(int(pt.x() + r + 4), int(pt.y() + 4), f"{name} ({rh:.2f})")
            else:
                painter.drawText(int(pt.x() + r + 4), int(pt.y() + 4), name)

        # 8. Sequential Picking Mode Banner & Rubber-band Guides
        if self.is_picking_mode:
            painter.setBrush(QBrush(QColor(15, 23, 42, 230)))
            painter.setPen(Qt.NoPen)
            painter.drawRect(0, 0, w, 34)
            painter.setPen(QColor(250, 204, 21))
            painter.setFont(QFont("Segoe UI", 9, QFont.Bold))
            target_count = getattr(self, 'pick_mode_points', 4)
            step_names = [
                '1: Front-Left (Green)',
                '2: Front-Right (Red)',
                '3: Back-Right (Blue)',
                '4: Back-Left (Yellow)',
                '5: Height (Purple)'
            ]
            cur_idx = min(target_count - 1, len(self.picked_points))
            msg = f"📍 {target_count}-Point Mode — Click point {cur_idx + 1} of {target_count}: {step_names[cur_idx]}  [Esc to cancel]"
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
                if len(clicked_pts) == 4 and self.current_cursor_pos:
                    for i in range(3):
                        painter.drawLine(clicked_pts[i], clicked_pts[i+1])
                    painter.drawLine(clicked_pts[3], clicked_pts[0])
                    # Rubberband line from Front-Left to cursor for height
                    h_pen = QPen(QColor(192, 132, 252), 2, Qt.DashLine)
                    painter.setPen(h_pen)
                    painter.drawLine(clicked_pts[0], QPointF(self.current_cursor_pos))
                else:
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

        elif self.is_drag_mode and not self.drag_start_pos:
            painter.setBrush(QBrush(QColor(15, 23, 42, 230)))
            painter.setPen(Qt.NoPen)
            painter.drawRect(0, 0, w, 34)
            painter.setPen(QColor(56, 189, 248))
            painter.setFont(QFont("Segoe UI", 9, QFont.Bold))
            painter.drawText(14, 22, "✏️ Draw Mode — Click and drag on canvas to outline ground rectangle  [Esc to cancel]")

        painter.end()


# =========================================================================
# UNIFIED GROUND CALIBRATOR & 3D PRIMITIVE DRAWER DIALOG
# =========================================================================
class GroundCalibratorDialog(QDialog):
    """
    Unified Perspective Calibrator & 3D Primitive Placement Dialog.
    Allows artists to calibrate camera perspective and ground planes,
    draw 3D primitives (Box, Cylinder, Sphere, Pyramid, Cone, Plane),
    or place imported 3D models directly on canvas perspective.
    """
    applied = pyqtSignal(dict)

    def __init__(self, bg_image=None, mesh=None, camera=None, lighting=None,
                 renderer=None, frame_rect=None, start_in_click_draw=False,
                 initial_mode=None, parent=None):
        super().__init__(parent)
        if start_in_click_draw or initial_mode in ("box", "primitive"):
            self.setWindowTitle("✏️ Draw 3D Primitive & Perspective Calibrator")
        else:
            self.setWindowTitle("📐 Draw Ground Rectangle & Perspective Calibrator")

        # Window sizing & geometry restoration:
        saved_geo = load_ground_dialog_geometry()
        restored = False
        if saved_geo:
            try:
                restored = self.restoreGeometry(QByteArray.fromHex(saved_geo.encode('ascii')))
            except Exception:
                restored = False

        if not restored:
            screen = QApplication.primaryScreen()
            if screen:
                geom = screen.availableGeometry()
            else:
                geom = QDesktopWidget().availableGeometry()
            w = int(geom.width() * 0.90)
            h = int(geom.height() * 0.90)
            x = geom.x() + (geom.width() - w) // 2
            y = geom.y() + (geom.height() - h) // 2
            self.setGeometry(x, y, w, h)

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
            QComboBox {
                background: #1e293b; color: #f1f5f9; border: 1px solid #334155;
                border-radius: 4px; padding: 3px 8px; font-size: 11px; font-weight: bold;
            }
            QComboBox:hover { border-color: #38bdf8; }
            QComboBox::drop-down { border: none; width: 18px; }
            QComboBox QAbstractItemView {
                background: #0f172a; color: #f1f5f9; selection-background-color: #2563eb;
                border: 1px solid #334155;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        # Header description
        hdr = QLabel(
            "📐 <b>Ground Calibrator & Perspective Matching</b>: Match camera perspective and fit 3D models or primitives to your canvas ground plane.<br>"
            "<span style='color:#94a3b8;font-size:10px;'>"
            "Drag the 4 corner pins (<b style='color:#22c55e;'>1 FL</b>, <b style='color:#ef4444;'>2 FR</b>, "
            "<b style='color:#3b82f6;'>3 BR</b>, <b style='color:#eab308;'>4 BL</b>), drag <b style='color:#c084fc;'>5 H</b> for height, "
            "drag <b style='color:#facc15;'>Horizon line</b> to tilt eye level, or use the <b>center Gizmo</b> (and Shift/Ctrl modifiers) to Move, Rotate, and Scale.</span>"
        )
        hdr.setWordWrap(True)
        layout.addWidget(hdr)

        # =========================================================================
        # TOP TOOLBAR: Modes, Primitive Selector, Aspect Presets, Controls
        # =========================================================================
        top_bar = QHBoxLayout()
        top_bar.setSpacing(6)

        btn_draw = QPushButton("✏️ Draw Rect")
        btn_draw.setStyleSheet("background:#1e293b; color:#38bdf8; font-weight:bold; border:1px solid #0284c7; padding:4px 10px;")
        btn_draw.setToolTip("Click and drag across canvas to draw a ground perspective rectangle")
        btn_draw.clicked.connect(self._on_draw_clicked)
        top_bar.addWidget(btn_draw)

        btn_pick_4 = QPushButton("📍 4-Point Draw")
        btn_pick_4.setStyleSheet("background:#1e293b; color:#facc15; font-weight:bold; border:1px solid #ca8a04; padding:4px 10px;")
        btn_pick_4.setToolTip("Click 4 consecutive corners on your canvas (1 Front-Left, 2 Front-Right, 3 Back-Right, 4 Back-Left)")
        btn_pick_4.clicked.connect(lambda: self._on_pick_clicked(4))
        top_bar.addWidget(btn_pick_4)

        btn_pick_5 = QPushButton("📍 5-Point Draw")
        btn_pick_5.setStyleSheet("background:#1e293b; color:#c084fc; font-weight:bold; border:1px solid #9333ea; padding:4px 10px;")
        btn_pick_5.setToolTip("Click 4 corners for the base + 1 fifth point to define the vertical height in perspective!")
        btn_pick_5.clicked.connect(lambda: self._on_pick_clicked(5))
        top_bar.addWidget(btn_pick_5)

        # Separator line
        sep1 = QFrame()
        sep1.setFrameShape(QFrame.VLine)
        sep1.setStyleSheet("color:#334155;")
        top_bar.addWidget(sep1)

        # Primitive Type selector
        lbl_prim = QLabel("Object:")
        lbl_prim.setStyleSheet("color:#94a3b8; font-weight:bold;")
        top_bar.addWidget(lbl_prim)

        self.combo_primitive = QComboBox()
        prim_items = ["📐 Ground Rectangle"]
        if mesh and getattr(mesh, 'vertices', None) and not getattr(mesh, 'primitive_type', None):
            prim_items.insert(0, "📁 Loaded 3D Model")
        prim_items.extend(["📦 Box", "🛢️ Cylinder", "🔮 Sphere", "📐 Pyramid", "🍦 Cone", "🏁 Plane", "🏠 Room (3 Planes)"])
        self.combo_primitive.addItems(prim_items)

        if start_in_click_draw or initial_mode in ("box", "primitive", 5):
            self.combo_primitive.setCurrentText("📦 Box")
        elif mesh and getattr(mesh, 'primitive_type', None):
            pt = getattr(mesh, 'primitive_type')
            for i in range(self.combo_primitive.count()):
                if pt.lower() in self.combo_primitive.itemText(i).lower():
                    self.combo_primitive.setCurrentIndex(i)
                    break
        elif mesh and getattr(mesh, 'vertices', None):
            self.combo_primitive.setCurrentText("📁 Loaded 3D Model")
        else:
            self.combo_primitive.setCurrentText("📐 Ground Rectangle")
        self.combo_primitive.currentTextChanged.connect(self._on_primitive_changed)
        top_bar.addWidget(self.combo_primitive)

        # Aspect Presets
        lbl_asp = QLabel("Aspect:")
        lbl_asp.setStyleSheet("color:#94a3b8; font-weight:bold;")
        top_bar.addWidget(lbl_asp)

        self.combo_aspect = QComboBox()
        self.combo_aspect.addItems([
            "Free",
            "1:1:1 Cube",
            "1:2:1 Standing Block",
            "1:3:1 Human / Character",
            "2:1:3 Room / Interior",
            "4:1:4 Wide Stage"
        ])
        self.combo_aspect.currentTextChanged.connect(self._on_aspect_changed)
        top_bar.addWidget(self.combo_aspect)

        sep2 = QFrame()
        sep2.setFrameShape(QFrame.VLine)
        sep2.setStyleSheet("color:#334155;")
        top_bar.addWidget(sep2)

        self.chk_keep_horizon = QCheckBox("Keep Horizon Level")
        self.chk_keep_horizon.setChecked(True)
        self.chk_keep_horizon.setToolTip("Lock camera roll to 0° so the horizon line stays completely horizontal")
        self.chk_keep_horizon.stateChanged.connect(self._on_keep_horizon_toggled)
        top_bar.addWidget(self.chk_keep_horizon)

        btn_flip = QPushButton("🔄 Flip 180°")
        btn_flip.setToolTip("Flip model yaw 180° (toggle between facing front and back)")
        btn_flip.clicked.connect(self._on_flip_clicked)
        top_bar.addWidget(btn_flip)

        btn_center = QPushButton("⌖ Center")
        btn_center.setToolTip("Centers the ground quad in view")
        btn_center.clicked.connect(self._on_center_clicked)
        top_bar.addWidget(btn_center)

        btn_reset = QPushButton("⟲ Reset")
        btn_reset.setToolTip("Resets the pins to default perspective")
        btn_reset.clicked.connect(self._on_reset_clicked)
        top_bar.addWidget(btn_reset)

        btn_history = QPushButton("🕒 History")
        btn_history.setToolTip("Pick a recently placed primitive or perspective")
        btn_history.clicked.connect(self._on_history_clicked)
        top_bar.addWidget(btn_history)

        sep_giz = QFrame()
        sep_giz.setFrameShape(QFrame.VLine)
        sep_giz.setStyleSheet("color:#334155;")
        top_bar.addWidget(sep_giz)

        lbl_giz = QLabel("Gizmo:")
        lbl_giz.setStyleSheet("color:#94a3b8; font-weight:bold;")
        top_bar.addWidget(lbl_giz)

        self.btn_giz_all = QPushButton("⚙ All (A)")
        self.btn_giz_all.setCheckable(True)
        self.btn_giz_all.setChecked(True)
        self.btn_giz_all.setStyleSheet("background:#2563eb; color:#ffffff; font-weight:bold; border:1px solid #60a5fa;")
        self.btn_giz_all.setToolTip("Blender 3D Transform: All axes (Move, Rotate, Scale) [Key: A]")
        self.btn_giz_all.clicked.connect(lambda: self._set_gizmo_mode("all"))
        top_bar.addWidget(self.btn_giz_all)

        self.btn_giz_move = QPushButton("✥ Move (G)")
        self.btn_giz_move.setCheckable(True)
        self.btn_giz_move.setStyleSheet("background:#323642; color:#cbd5e1; font-weight:bold; border:1px solid #434958;")
        self.btn_giz_move.setToolTip("Blender 3D Translation axes (Red X, Green Y, Blue Z Up) [Key: G]")
        self.btn_giz_move.clicked.connect(lambda: self._set_gizmo_mode("move"))
        top_bar.addWidget(self.btn_giz_move)

        self.btn_giz_rot = QPushButton("⟳ Rotate (R)")
        self.btn_giz_rot.setCheckable(True)
        self.btn_giz_rot.setStyleSheet("background:#323642; color:#cbd5e1; font-weight:bold; border:1px solid #434958;")
        self.btn_giz_rot.setToolTip("Blender 3D Rotation rings (Pitch X, Roll Y, Yaw Z) [Key: R]")
        self.btn_giz_rot.clicked.connect(lambda: self._set_gizmo_mode("rotate"))
        top_bar.addWidget(self.btn_giz_rot)

        self.btn_giz_scale = QPushButton("⤢ Scale (S)")
        self.btn_giz_scale.setCheckable(True)
        self.btn_giz_scale.setStyleSheet("background:#323642; color:#cbd5e1; font-weight:bold; border:1px solid #434958;")
        self.btn_giz_scale.setToolTip("Blender 3D Scale axes [Key: S]")
        self.btn_giz_scale.clicked.connect(lambda: self._set_gizmo_mode("scale"))
        top_bar.addWidget(self.btn_giz_scale)

        top_bar.addStretch(1)
        layout.addLayout(top_bar)

        # Pre-initialize status labels before calibrator_widget signals fire
        self.lbl_guidance = QLabel("📐 Ready: Drag corner pins, horizon line, or center Gizmo to adjust perspective.")
        self.lbl_guidance.setWordWrap(True)
        self.lbl_guidance.setStyleSheet(
            "font-family:'Segoe UI'; font-size:11px; color:#38bdf8; "
            "background:#0f172a; padding:6px 10px; border-radius:4px; border:1px solid #1e293b;"
        )

        self.lbl_stats = QLabel("Solving...")
        self.lbl_stats.setStyleSheet(
            "font-family:'Consolas', monospace; font-size:11px; color:#38bdf8; "
            "background:#12141a; padding:6px 10px; border-radius:4px; border:1px solid #1e293b;"
        )

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
        self.calibrator_widget.guidance_changed.connect(self._set_guidance)
        self.calibrator_widget.gizmo_mode_changed.connect(self._sync_gizmo_buttons)
        layout.addWidget(self.calibrator_widget, 1)

        # Sync initial primitive selection to widget
        cur_prim_text = self.combo_primitive.currentText()
        if "Ground" in cur_prim_text or "Rectangle" in cur_prim_text:
            cur_prim_clean = "Ground Rectangle"
        elif "Model" in cur_prim_text:
            cur_prim_clean = "Loaded 3D Model"
        else:
            cur_prim_clean = cur_prim_text.split()[-1]
        self.calibrator_widget.set_primitive_type(cur_prim_clean)

        # Add status & stats labels to layout below canvas
        layout.addWidget(self.lbl_guidance)
        layout.addWidget(self.lbl_stats)

        # Bottom Action Bar
        bot_bar = QHBoxLayout()
        bot_bar.setSpacing(6)
        bot_bar.addStretch(1)

        btn_apply = QPushButton("✔ Place Model on Ground & Apply")
        btn_apply.setStyleSheet(
            "background:#2563eb; color:#ffffff; border:1px solid #1d4ed8; padding:6px 18px; font-size:12px; font-weight:bold;"
        )
        btn_apply.setToolTip("Applies the calibrated camera and places the 3D model/primitive directly on top of the ground rectangle")
        btn_apply.clicked.connect(self._apply)
        bot_bar.addWidget(btn_apply)

        btn_close = QPushButton("Cancel")
        btn_close.clicked.connect(self.reject)
        bot_bar.addWidget(btn_close)

        layout.addLayout(bot_bar)

        # Initial mode trigger
        if start_in_click_draw or initial_mode in ("box", "primitive"):
            self.combo_primitive.setCurrentText("📦 Box")
            self.calibrator_widget.set_primitive_type("Box")
            self.calibrator_widget.start_drag_mode()
        elif initial_mode == 4:
            self._start_4point_pick()
        elif initial_mode == 5:
            if "Ground Rectangle" in self.combo_primitive.currentText():
                self.combo_primitive.setCurrentText("📦 Box")
            self._start_5point_pick()
        elif initial_mode in ("draw", "drag"):
            self.start_drag_mode()

        self._on_solution_changed(self.calibrator_widget.last_solution)

    def _save_geom(self):
        try:
            geo_hex = self.saveGeometry().toHex().data().decode('ascii')
            save_ground_dialog_geometry(geo_hex)
        except Exception:
            pass

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._save_geom()

    def moveEvent(self, event):
        super().moveEvent(event)
        self._save_geom()

    def closeEvent(self, event):
        self._save_geom()
        super().closeEvent(event)

    def reject(self):
        self._save_geom()
        super().reject()

    def _on_draw_clicked(self):
        if hasattr(self, 'calibrator_widget'):
            self.calibrator_widget.start_drag_mode()

    def _on_pick_clicked(self, n=4):
        if hasattr(self, 'calibrator_widget'):
            self.calibrator_widget.start_pick_mode(n)

    def _start_4point_pick(self):
        if hasattr(self, 'calibrator_widget'):
            self.calibrator_widget.start_pick_mode(4)

    def _start_5point_pick(self):
        if hasattr(self, 'calibrator_widget'):
            self.calibrator_widget.start_pick_mode(5)

    def start_pick_mode(self, n=4):
        if hasattr(self, 'calibrator_widget'):
            self.calibrator_widget.start_pick_mode(n)

    def start_drag_mode(self):
        if hasattr(self, 'calibrator_widget'):
            self.calibrator_widget.start_drag_mode()

    def _on_center_clicked(self):
        self.calibrator_widget.center_quad()

    def _on_reset_clicked(self):
        self.calibrator_widget.reset_points()

    def _on_keep_horizon_toggled(self, state):
        self.calibrator_widget.set_keep_horizon(state == Qt.Checked)

    def _on_flip_clicked(self):
        self.calibrator_widget.toggle_flip_yaw()

    def _on_primitive_changed(self, text):
        if not text:
            clean_name = "Ground Rectangle"
        elif "Ground" in text or "Rectangle" in text:
            clean_name = "Ground Rectangle"
        elif "Model" in text:
            clean_name = "Loaded 3D Model"
        else:
            clean_name = text.split()[-1]
        self.calibrator_widget.set_primitive_type(clean_name)

    def _on_aspect_changed(self, text):
        self.calibrator_widget.set_aspect_preset(text)

    def _on_history_clicked(self):
        history = load_primitive_history()
        menu = QMenu(self)
        menu.setStyleSheet("QMenu { background:#1e293b; color:#f1f5f9; border:1px solid #334155; } QMenu::item:selected { background:#2563eb; }")
        if not history:
            act = menu.addAction("No previous primitives")
            act.setEnabled(False)
        else:
            for item in history[:10]:
                ptype = item.get("primitive_type", "Box")
                bw = item.get("box_w", 2.0)
                bh = item.get("box_h", 2.0)
                bd = item.get("box_d", 2.0)
                t_str = item.get("timestamp", "")
                title = f"{ptype} ({bw:.1f} × {bh:.1f} × {bd:.1f})  -  {t_str}"
                act = menu.addAction(title)
                act.triggered.connect(lambda ch, ent=item: self._apply_history_entry(ent))
        btn = self.sender()
        if btn:
            menu.exec_(btn.mapToGlobal(btn.rect().bottomLeft()))

    def _apply_history_entry(self, entry):
        ptype = entry.get("primitive_type", "Box")
        for i in range(self.combo_primitive.count()):
            if ptype.lower() in self.combo_primitive.itemText(i).lower():
                self.combo_primitive.setCurrentIndex(i)
                break
        self.calibrator_widget.set_primitive_type(ptype)
        bh = float(entry.get("box_h", 2.0))
        self.calibrator_widget.last_solution["rect_height"] = bh
        corners_3d = self.calibrator_widget.last_solution.get("corners_3d")
        base_corner_3d = corners_3d[0] if (corners_3d and len(corners_3d) > 0) else QVector3D(0, 0, 0)
        doc_w, doc_h = self.calibrator_widget._get_doc_size()
        self.calibrator_widget.height_norm_pt = project_height_to_norm_point(
            self.calibrator_widget.camera, doc_w, doc_h, base_corner_3d, bh, self.calibrator_widget.frame_rect
        )
        self.calibrator_widget._recalculate()
        self.calibrator_widget.update()

    def _sync_gizmo_buttons(self, mode):
        for btn, is_active in [
            (self.btn_giz_all, mode == "all"),
            (self.btn_giz_move, mode == "move"),
            (self.btn_giz_rot, mode == "rotate"),
            (self.btn_giz_scale, mode == "scale"),
        ]:
            btn.setChecked(is_active)
            if is_active:
                btn.setStyleSheet("background:#2563eb; color:#ffffff; font-weight:bold; border:1px solid #60a5fa;")
            else:
                btn.setStyleSheet("background:#323642; color:#cbd5e1; font-weight:bold; border:1px solid #434958;")

    def _set_gizmo_mode(self, mode):
        self._sync_gizmo_buttons(mode)
        self.calibrator_widget.set_gizmo_mode(mode)

    def _set_guidance(self, text, level="info"):
        if not hasattr(self, 'lbl_guidance') or self.lbl_guidance is None:
            return
        level_styles = {
            "info":    "color:#38bdf8; background:#0f172a; border:1px solid #1e293b;",
            "warn":    "color:#facc15; background:#2d2006; border:1px solid #854d0e; font-weight:bold;",
            "error":   "color:#f87171; background:#2a0c0c; border:1px solid #991b1b; font-weight:bold;",
            "success": "color:#4ade80; background:#062e1b; border:1px solid #166534; font-weight:bold;"
        }
        style = level_styles.get(level, level_styles["info"])
        self.lbl_guidance.setStyleSheet(
            f"font-family:'Segoe UI'; font-size:11px; padding:6px 10px; border-radius:4px; {style}"
        )
        self.lbl_guidance.setText(text)

    def _on_solution_changed(self, sol):
        if not hasattr(self, 'lbl_stats') or self.lbl_stats is None:
            return
        yaw = sol.get("yaw", 180.0)
        pitch = sol.get("pitch", 15.0)
        roll = sol.get("roll", 0.0)
        fov = sol.get("fov", 45.0)
        dist = sol.get("distance", 3.0)
        rw = sol.get("rect_width", 2.0)
        rd = sol.get("rect_depth", 2.0)
        rh = sol.get("rect_height", 2.0)
        pt = getattr(self.calibrator_widget, 'primitive_type', 'Ground Rectangle')
        self.lbl_stats.setText(
            f"Object: {pt} | Ground: {rw:4.2f} × {rd:4.2f} | Height: {rh:4.2f} | Tilt: {pitch:5.1f}° | Yaw: {yaw:5.1f}° | FOV: {fov:5.1f}° | Dist: {dist:4.2f}"
        )

    def _apply(self):
        self._save_geom()
        sol = dict(self.calibrator_widget.last_solution)
        ptype = self.calibrator_widget.primitive_type
        rw = float(sol.get("rect_width", 2.0))
        rd = float(sol.get("rect_depth", 2.0))
        rh = float(sol.get("rect_height", 2.0))

        sol["primitive_type"] = ptype
        sol["box_w"] = rw
        sol["box_h"] = rh
        sol["box_d"] = rd

        if ptype in ("Ground Rectangle", "Loaded 3D Model", "Ground", "Model", None, ""):
            sol["mesh"] = None  # Docker retains current mesh and places/aligns on ground
        elif ptype == "Box":
            sol["mesh"] = create_box_primitive(rw, rh, rd)
        elif ptype == "Cylinder":
            sol["mesh"] = create_cylinder_primitive(rw * 0.5, rh, 24)
        elif ptype == "Sphere":
            sol["mesh"] = create_sphere_primitive(rw * 0.5, 16, 24)
        elif ptype == "Pyramid":
            sol["mesh"] = create_pyramid_primitive(rw, rh, rd)
        elif ptype == "Cone":
            sol["mesh"] = create_cone_primitive(rw * 0.5, rh, 24)
        elif ptype == "Plane":
            sol["mesh"] = create_plane_primitive(rw, rd, 2)
        elif ptype in ("Room", "Room (3 Planes)", "Room Corner"):
            sol["mesh"] = create_room_primitive(rw, rh, rd)
        else:
            sol["mesh"] = None

        try:
            add_primitive_to_history({
                "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
                "primitive_type": ptype,
                "box_w": rw, "box_h": rh, "box_d": rd,
                "yaw": sol.get("yaw", 180.0),
                "pitch": sol.get("pitch", 15.0),
                "fov": sol.get("fov", 45.0)
            })
        except Exception:
            pass

        self.applied.emit(sol)
        self.accept()

