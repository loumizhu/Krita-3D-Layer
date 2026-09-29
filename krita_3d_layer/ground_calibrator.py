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
        self.has_height_point = (self.primitive_type in ("Box", "Cylinder", "Pyramid", "Cone"))
        self.aspect_preset = "Free"

        # Horizon interaction
        self.is_dragging_horizon = False
        self.hover_horizon = False
        self.drag_start_pitch = 15.0

        # Transform Gizmo & Quad dragging (Move, Rotate, Scale)
        self.active_gizmo_action = None  # None, 'move', 'rotate', 'scale'
        self.hover_gizmo_part = None     # None, 'move', 'rotate', 'scale', 'inside_quad'
        self.drag_start_mouse_pos = None
        self.drag_start_quad_pts = []
        self.drag_start_height_pt = None
        self.drag_start_center_norm = None
        self.drag_start_dist = 1.0
        self.drag_start_angle = 0.0

        # Current image rect within widget (for letterbox/aspect mapping)
        self.img_rect = QRectF(0, 0, 480, 360)

        # 4 ground points in normalized document coordinates [0, 1]
        # P0: Front-Left, P1: Front-Right, P2: Back-Right, P3: Back-Left
        self.norm_points = self._compute_initial_norm_points()

        self.last_solution = {}
        self._recalculate()

    def set_primitive_type(self, ptype):
        """Sets active 3D primitive type, ground rectangle, or loaded model."""
        self.primitive_type = ptype
        if ptype in ("Box", "Cylinder", "Pyramid", "Cone"):
            self.has_height_point = True
            corners_3d = self.last_solution.get("corners_3d")
            base_corner_3d = corners_3d[0] if (corners_3d and len(corners_3d) > 0) else QVector3D(0, 0, 0)
            rh = self.last_solution.get("rect_height", 2.0)
            doc_w, doc_h = self._get_doc_size()
            self.height_norm_pt = project_height_to_norm_point(self.camera, doc_w, doc_h, base_corner_3d, rh, self.frame_rect)
        else:
            self.has_height_point = False
            self.height_norm_pt = None
        self._recalculate()
        self.update()

    def set_aspect_preset(self, preset_name):
        """Sets aspect ratio proportions for the ground rectangle & height."""
        self.aspect_preset = preset_name
        if preset_name == "Free":
            self.update()
            return
        rw = self.last_solution.get("rect_width", 2.0)
        rd = self.last_solution.get("rect_depth", 2.0)
        base_size = max(0.5, (rw + rd) * 0.5)

        if preset_name == "1:1:1 Cube":
            rh = base_size
        elif preset_name == "1:2:1 Standing Block":
            rh = base_size * 2.0
        elif preset_name == "1:3:1 Human / Character":
            rh = base_size * 3.0
        elif preset_name == "2:1:3 Room / Interior":
            rh = base_size * 0.5
        elif preset_name == "4:1:4 Wide Stage":
            rh = base_size * 0.25
        else:
            rh = base_size

        self.last_solution["rect_height"] = rh
        corners_3d = self.last_solution.get("corners_3d")
        base_corner_3d = corners_3d[0] if (corners_3d and len(corners_3d) > 0) else QVector3D(0, 0, 0)
        doc_w, doc_h = self._get_doc_size()
        self.height_norm_pt = project_height_to_norm_point(self.camera, doc_w, doc_h, base_corner_3d, rh, self.frame_rect)
        self.has_height_point = True
        self._recalculate()
        self.update()

    def _get_horizon_endpoints(self):
        """Returns (p1, p2) representing the visible horizon line across the widget."""
        sol = self.last_solution
        vp1_doc = sol.get("vp1")
        vp2_doc = sol.get("vp2")
        w = float(self.width())
        h = float(self.height())
        if vp1_doc and vp2_doc:
            vp1_w = self._doc_to_widget(vp1_doc)
            vp2_w = self._doc_to_widget(vp2_doc)
            dx = vp2_w.x() - vp1_w.x()
            dy = vp2_w.y() - vp1_w.y()
            if abs(dx) > 1e-4 or abs(dy) > 1e-4:
                length = math.hypot(dx, dy)
                scale = max(w, h) * 4.0 / max(1.0, length)
                h_p1 = QPointF(vp1_w.x() - dx * scale, vp1_w.y() - dy * scale)
                h_p2 = QPointF(vp2_w.x() + dx * scale, vp2_w.y() + dy * scale)
                return h_p1, h_p2
        # Fallback horizontal line across image rect at solved eye-level
        doc_w, doc_h = self._get_doc_size()
        cy = doc_h * 0.5
        cur_fov = self.camera.fov if self.camera else 45.0
        pitch = sol.get("pitch", 15.0)
        f = (min(doc_w, doc_h) * 0.5) / math.tan(math.radians(max(5.0, min(160.0, cur_fov)) * 0.5))
        y_doc = cy - f * math.tan(math.radians(pitch))
        yw = self._doc_to_widget(QPointF(0, y_doc)).y()
        return QPointF(0, yw), QPointF(w, yw)

    def _distance_to_horizon(self, pt):
        """Calculates perpendicular pixel distance from point to the horizon line."""
        p1, p2 = self._get_horizon_endpoints()
        dx = p2.x() - p1.x()
        dy = p2.y() - p1.y()
        denom = math.hypot(dx, dy)
        if denom < 1e-4:
            return 9999.0
        numer = abs(dy * pt.x() - dx * pt.y() + p2.x() * p1.y() - p2.y() * p1.x())
        return numer / denom

    def _get_gizmo_parts(self):
        """
        Returns geometry of the on-screen transform gizmo at the quad center:
        (c_w, move_rect, rot_pt, scale_pt)
        """
        sol = self.last_solution
        c_doc = sol.get("center_2d")
        if not c_doc:
            doc_pts = self._get_doc_points()
            c_doc = QPointF(sum(p.x() for p in doc_pts) * 0.25, sum(p.y() for p in doc_pts) * 0.25)
        c_w = self._doc_to_widget(c_doc)

        move_rect = QRectF(c_w.x() - 13, c_w.y() - 13, 26, 26)
        rot_pt = QPointF(c_w.x(), c_w.y() - 38)
        scale_pt = QPointF(c_w.x() + 38, c_w.y())
        return c_w, move_rect, rot_pt, scale_pt

    def _start_gizmo_action(self, action, mouse_pos, c_w):
        """Initiates an interactive Move, Rotate, or Scale transformation."""
        self.active_gizmo_action = action
        self.drag_start_mouse_pos = QPointF(mouse_pos)
        self.drag_start_quad_pts = [QPointF(p) for p in self.norm_points]
        self.drag_start_height_pt = QPointF(self.height_norm_pt) if self.height_norm_pt else None

        pts = self.norm_points
        self.drag_start_center_norm = QPointF(
            sum(p.x() for p in pts) * 0.25,
            sum(p.y() for p in pts) * 0.25
        )
        self.drag_start_dist = max(10.0, math.hypot(mouse_pos.x() - c_w.x(), mouse_pos.y() - c_w.y()))
        self.drag_start_angle = math.atan2(mouse_pos.y() - c_w.y(), mouse_pos.x() - c_w.x())

        if action == 'move':
            self.guidance_changed.emit("✥ Moving Ground Rectangle: Drag to reposition on canvas.", "info")
            self.setCursor(Qt.SizeAllCursor)
        elif action == 'scale':
            self.guidance_changed.emit("⤢ Scaling Ground Rectangle: Drag outward to enlarge, inward to shrink.", "info")
            self.setCursor(Qt.SizeFDiagCursor)
        elif action == 'rotate':
            self.guidance_changed.emit("⟳ Rotating Ground Rectangle: Drag around center to rotate yaw/orientation.", "info")
            self.setCursor(Qt.PointingHandCursor)

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

            # 4. Check On-Screen Transform Gizmo handles (Rotate ⟳, Scale ⤢, Move ✥)
            c_w, move_rect, rot_pt, scale_pt = self._get_gizmo_parts()

            # Rotate handle (⟳)
            if (rot_pt - QPointF(pos)).manhattanLength() <= 14:
                self._start_gizmo_action('rotate', pos, c_w)
                event.accept()
                return

            # Scale handle (⤢)
            if (scale_pt - QPointF(pos)).manhattanLength() <= 14:
                self._start_gizmo_action('scale', pos, c_w)
                event.accept()
                return

            # Center Move handle (✥)
            if (c_w - QPointF(pos)).manhattanLength() <= 15:
                self._start_gizmo_action('move', pos, c_w)
                event.accept()
                return

            # 5. Check Quad interior with modifier keys (Shift: Scale, Ctrl/Alt: Rotate, Normal: Move)
            p0, p1, p2, p3 = pts[:4]
            quad_poly = QPolygonF([p0, p1, p2, p3])
            if quad_poly.containsPoint(pos, Qt.OddEvenFill):
                mods = event.modifiers()
                if mods & Qt.ShiftModifier:
                    self._start_gizmo_action('scale', pos, c_w)
                elif mods & (Qt.ControlModifier | Qt.AltModifier):
                    self._start_gizmo_action('rotate', pos, c_w)
                else:
                    self._start_gizmo_action('move', pos, c_w)
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

        # Gizmo Action Dragging (Move, Rotate, Scale)
        if self.active_gizmo_action is not None and self.drag_start_mouse_pos:
            c_w, _, _, _ = self._get_gizmo_parts()
            c_norm = self.drag_start_center_norm

            if self.active_gizmo_action == 'move':
                p_curr_norm = self._widget_to_doc_norm(pos)
                p_start_norm = self._widget_to_doc_norm(self.drag_start_mouse_pos)
                dx = p_curr_norm.x() - p_start_norm.x()
                dy = p_curr_norm.y() - p_start_norm.y()
                self.norm_points = [
                    QPointF(max(0.001, min(0.999, p.x() + dx)), max(0.001, min(0.999, p.y() + dy)))
                    for p in self.drag_start_quad_pts
                ]
                if self.drag_start_height_pt:
                    self.height_norm_pt = QPointF(
                        max(0.001, min(0.999, self.drag_start_height_pt.x() + dx)),
                        max(0.001, min(0.999, self.drag_start_height_pt.y() + dy))
                    )

            elif self.active_gizmo_action == 'scale':
                dist_curr = math.hypot(pos.x() - c_w.x(), pos.y() - c_w.y())
                s = max(0.1, min(10.0, dist_curr / max(10.0, self.drag_start_dist)))
                self.norm_points = [
                    QPointF(
                        max(0.001, min(0.999, c_norm.x() + (p.x() - c_norm.x()) * s)),
                        max(0.001, min(0.999, c_norm.y() + (p.y() - c_norm.y()) * s))
                    )
                    for p in self.drag_start_quad_pts
                ]
                if self.drag_start_height_pt:
                    self.height_norm_pt = QPointF(
                        max(0.001, min(0.999, c_norm.x() + (self.drag_start_height_pt.x() - c_norm.x()) * s)),
                        max(0.001, min(0.999, c_norm.y() + (self.drag_start_height_pt.y() - c_norm.y()) * s))
                    )

            elif self.active_gizmo_action == 'rotate':
                ang_curr = math.atan2(pos.y() - c_w.y(), pos.x() - c_w.x())
                ang_delta = ang_curr - self.drag_start_angle
                cos_a = math.cos(ang_delta)
                sin_a = math.sin(ang_delta)

                new_pts = []
                for p in self.drag_start_quad_pts:
                    ox = p.x() - c_norm.x()
                    oy = p.y() - c_norm.y()
                    rx = c_norm.x() + ox * cos_a - oy * sin_a
                    ry = c_norm.y() + ox * sin_a + oy * cos_a
                    new_pts.append(QPointF(max(0.001, min(0.999, rx)), max(0.001, min(0.999, ry))))
                self.norm_points = new_pts

                if self.drag_start_height_pt:
                    ox = self.drag_start_height_pt.x() - c_norm.x()
                    oy = self.drag_start_height_pt.y() - c_norm.y()
                    rx = c_norm.x() + ox * cos_a - oy * sin_a
                    ry = c_norm.y() + ox * sin_a + oy * cos_a
                    self.height_norm_pt = QPointF(max(0.001, min(0.999, rx)), max(0.001, min(0.999, ry)))

            self._recalculate()
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
        old_h = self.hovered_handle
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
            c_w, move_rect, rot_pt, scale_pt = self._get_gizmo_parts()
            if (rot_pt - QPointF(pos)).manhattanLength() <= 14:
                self.hover_gizmo_part = 'rotate'
                self.hover_horizon = False
                self.setCursor(Qt.PointingHandCursor)
                self.guidance_changed.emit("⟳ Gizmo Rotate: Drag around center to rotate ground rectangle.", "info")
            elif (scale_pt - QPointF(pos)).manhattanLength() <= 14:
                self.hover_gizmo_part = 'scale'
                self.hover_horizon = False
                self.setCursor(Qt.SizeFDiagCursor)
                self.guidance_changed.emit("⤢ Gizmo Scale: Drag outward/inward to scale ground rectangle.", "info")
            elif (c_w - QPointF(pos)).manhattanLength() <= 15:
                self.hover_gizmo_part = 'move'
                self.hover_horizon = False
                self.setCursor(Qt.SizeAllCursor)
                self.guidance_changed.emit("✥ Gizmo Move: Drag to translate ground rectangle on canvas.", "info")
            else:
                p0, p1, p2, p3 = pts[:4]
                quad_poly = QPolygonF([p0, p1, p2, p3])
                if quad_poly.containsPoint(pos, Qt.OddEvenFill):
                    self.hover_gizmo_part = 'inside_quad'
                    self.hover_horizon = False
                    mods = event.modifiers()
                    if mods & Qt.ShiftModifier:
                        self.setCursor(Qt.SizeFDiagCursor)
                        self.guidance_changed.emit("⤢ Shift+Drag inside quad: Scale ground rectangle.", "info")
                    elif mods & (Qt.ControlModifier | Qt.AltModifier):
                        self.setCursor(Qt.PointingHandCursor)
                        self.guidance_changed.emit("⟳ Ctrl+Drag inside quad: Rotate ground rectangle.", "info")
                    else:
                        self.setCursor(Qt.SizeAllCursor)
                        self.guidance_changed.emit("✥ Drag inside quad: Move  |  Shift+Drag: Scale  |  Ctrl+Drag: Rotate", "info")
                elif self._distance_to_horizon(pos) <= 8.0:
                    self.hover_horizon = True
                    self.hover_gizmo_part = None
                    self.setCursor(Qt.SizeVerCursor)
                    self.guidance_changed.emit("↕ Horizon Line: Drag up or down to tilt camera eye-level.", "info")
                else:
                    self.hover_horizon = False
                    self.hover_gizmo_part = None
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

        if self.active_gizmo_action is not None:
            self.active_gizmo_action = None
            self.drag_start_mouse_pos = None
            self.update()
            event.accept()
            return

        if self.is_dragging_horizon:
            self.is_dragging_horizon = False
            self.drag_start_mouse_pos = None
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

        # 6. ON-SCREEN TRANSFORM GIZMO (Center Move ✥, Rotate ⟳, Scale ⤢)
        c_w, move_rect, rot_pt, scale_pt = self._get_gizmo_parts()

        # Connecting dashed lines
        p_stem_rot = QPen(QColor(168, 85, 247, 200), 1.5, Qt.DashLine)
        painter.setPen(p_stem_rot)
        painter.drawLine(c_w, rot_pt)

        p_stem_scale = QPen(QColor(245, 158, 11, 200), 1.5, Qt.DashLine)
        painter.setPen(p_stem_scale)
        painter.drawLine(c_w, scale_pt)

        # Rotate Handle (at rot_pt)
        is_rot_act = (self.active_gizmo_action == 'rotate' or self.hover_gizmo_part == 'rotate')
        rot_bg = QColor(88, 28, 135) if is_rot_act else QColor(15, 23, 42, 230)
        rot_border = QColor(216, 180, 254) if is_rot_act else QColor(168, 85, 247)
        painter.setBrush(QBrush(rot_bg))
        painter.setPen(QPen(rot_border, 2.0 if is_rot_act else 1.5))
        painter.drawEllipse(rot_pt, 12, 12)
        painter.setFont(QFont("Segoe UI", 9, QFont.Bold))
        painter.setPen(QColor(255, 255, 255))
        painter.drawText(QRectF(rot_pt.x() - 12, rot_pt.y() - 12, 24, 24), Qt.AlignCenter, "⟳")

        # Scale Handle (at scale_pt)
        is_scale_act = (self.active_gizmo_action == 'scale' or self.hover_gizmo_part == 'scale')
        scale_bg = QColor(180, 83, 9) if is_scale_act else QColor(15, 23, 42, 230)
        scale_border = QColor(253, 224, 71) if is_scale_act else QColor(245, 158, 11)
        painter.setBrush(QBrush(scale_bg))
        painter.setPen(QPen(scale_border, 2.0 if is_scale_act else 1.5))
        painter.drawEllipse(scale_pt, 12, 12)
        painter.setFont(QFont("Segoe UI", 9, QFont.Bold))
        painter.setPen(QColor(255, 255, 255))
        painter.drawText(QRectF(scale_pt.x() - 12, scale_pt.y() - 12, 24, 24), Qt.AlignCenter, "⤢")

        # Center Move Disc Handle (at c_w)
        is_move_act = (self.active_gizmo_action == 'move' or self.hover_gizmo_part == 'move')
        move_bg = QColor(2, 132, 199) if is_move_act else QColor(15, 23, 42, 230)
        move_border = QColor(125, 211, 252) if is_move_act else QColor(56, 189, 248)
        painter.setBrush(QBrush(move_bg))
        painter.setPen(QPen(move_border, 2.0 if is_move_act else 1.5))
        painter.drawEllipse(c_w, 13, 13)
        painter.setFont(QFont("Segoe UI", 10, QFont.Bold))
        painter.setPen(QColor(255, 255, 255))
        painter.drawText(QRectF(c_w.x() - 13, c_w.y() - 13, 26, 26), Qt.AlignCenter, "✥")

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
        prim_items.extend(["📦 Box", "🛢️ Cylinder", "🔮 Sphere", "📐 Pyramid", "🍦 Cone", "🏁 Plane"])
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

        top_bar.addStretch(1)
        layout.addLayout(top_bar)

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

        # Status / Guidance bar
        self.lbl_guidance = QLabel("📐 Ready: Drag corner pins, horizon line, or center Gizmo to adjust perspective.")
        self.lbl_guidance.setWordWrap(True)
        self.lbl_guidance.setStyleSheet(
            "font-family:'Segoe UI'; font-size:11px; color:#38bdf8; "
            "background:#0f172a; padding:6px 10px; border-radius:4px; border:1px solid #1e293b;"
        )
        layout.addWidget(self.lbl_guidance)

        # Solved Parameters readout bar
        self.lbl_stats = QLabel("Solving...")
        self.lbl_stats.setStyleSheet(
            "font-family:'Consolas', monospace; font-size:11px; color:#38bdf8; "
            "background:#12141a; padding:6px 10px; border-radius:4px; border:1px solid #1e293b;"
        )
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

    def _set_guidance(self, text, level="info"):
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

