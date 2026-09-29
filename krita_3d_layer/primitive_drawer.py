"""
Interactive Primitive Drawer & Perspective Calibrator for Krita-3D-Layer.

Allows artists to draw or trace a 3D box (or other primitive) directly on the canvas,
automatically inferring:
  - Perspective type (1-Point, 2-Point, or 3-Point)
  - Camera Field of View (FOV) and lens equivalent (e.g. 24mm, 50mm)
  - Camera Tilt (Pitch), Rotation (Yaw), and Dutch angle (Roll)
  - Box proportions (Width, Height, Depth)
  - 3D spatial position (Distance, Pan X, Pan Y)

Generates the 3D primitive mesh and calibrates the 3D scene camera to match with pixel accuracy.
"""

import os
import json
import datetime
import math
from PyQt5.QtCore import Qt, QPointF, QRectF, pyqtSignal, QByteArray
from PyQt5.QtGui import (
    QPainter, QPen, QColor, QBrush, QPolygonF, QFont,
    QLinearGradient, QVector3D, QVector4D, QCursor
)
from PyQt5.QtWidgets import (
    QWidget, QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QCheckBox, QComboBox, QFrame, QSizePolicy, QSlider
)

from .mesh_loader import MeshData
from .renderer import Camera3D, Lighting3D, Renderer3D, RenderStyle, ProjectionMode, project_camera_point

try:
    import numpy as np
    HAVE_NUMPY = True
except ImportError:
    HAVE_NUMPY = False


# -----------------------------------------------------------------------------
# Primitive History Persistence
# -----------------------------------------------------------------------------

def get_primitive_history_file_path():
    appdata = os.environ.get("APPDATA")
    if appdata and os.path.exists(appdata):
        kdir = os.path.join(appdata, "krita")
        os.makedirs(kdir, exist_ok=True)
        return os.path.join(kdir, "krita_3d_primitive_history.json")
    hdir = os.path.expanduser("~/.local/share/krita")
    os.makedirs(hdir, exist_ok=True)
    return os.path.join(hdir, "krita_3d_primitive_history.json")


def load_primitive_history():
    path = get_primitive_history_file_path()
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                items = json.load(f)
                if isinstance(items, list):
                    return items
        except Exception:
            pass
    return []


def save_primitive_history(items):
    path = get_primitive_history_file_path()
    try:
        trimmed = items[:50] if len(items) > 50 else items
        with open(path, "w", encoding="utf-8") as f:
            json.dump(trimmed, f, indent=2)
    except Exception:
        pass


def add_primitive_to_history(entry):
    items = load_primitive_history()
    # Check if duplicate of most recent entry
    if items and items[0].get("corners") == entry.get("corners") and items[0].get("primitive_type") == entry.get("primitive_type"):
        items[0] = entry
    else:
        items.insert(0, entry)
    save_primitive_history(items)


def clear_primitive_history():
    path = get_primitive_history_file_path()
    if os.path.exists(path):
        try:
            os.remove(path)
        except Exception:
            pass


def get_last_primitive():
    items = load_primitive_history()
    return items[0] if items else None


def get_dialog_geometry_file_path():
    hdir = os.path.join(os.path.expanduser("~"), ".krita_3d_layer")
    os.makedirs(hdir, exist_ok=True)
    return os.path.join(hdir, "drawer_dialog_geometry.json")


def load_dialog_geometry():
    path = get_dialog_geometry_file_path()
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data.get("geometry")
        except Exception:
            pass
    return None


def save_dialog_geometry(geo_hex):
    path = get_dialog_geometry_file_path()
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"geometry": geo_hex}, f)
    except Exception:
        pass



# -----------------------------------------------------------------------------
# Primitive Mesh Generators (Box, Cylinder, Sphere, Pyramid)
# Note: Vertices are explicitly sized (not down-scaled by radius) so their
# world dimensions match the camera distance and perspective solver.
# -----------------------------------------------------------------------------

def create_box_primitive(w=2.0, h=2.0, d=2.0, name="Primitive Box"):
    """
    Generates a clean 3D box mesh with specified width, height, and depth.
    Base is positioned at Y=0 so height is added upwards from the base,
    and the transform pivot point sits at the base center (0, 0, 0).
    Sets polygon_edges and coplanar_edges so wireframe mode cleanly outlines quads.
    """
    mesh = MeshData(name)
    hw = max(0.05, float(w) * 0.5)
    h_val = max(0.05, float(h))
    hd = max(0.05, float(d) * 0.5)

    # 8 vertices: bottom 0..3 (Y=0.0), top 4..7 (Y=h_val)
    mesh.vertices = [
        QVector3D( hw, 0.0, -hd),  # 0: Front-Left (facing camera in 3/4 view)
        QVector3D(-hw, 0.0, -hd),  # 1: Front-Right
        QVector3D(-hw, 0.0,  hd),  # 2: Back-Right
        QVector3D( hw, 0.0,  hd),  # 3: Back-Left
        QVector3D( hw, h_val, -hd),  # 4: Top Front-Left
        QVector3D(-hw, h_val, -hd),  # 5: Top Front-Right
        QVector3D(-hw, h_val,  hd),  # 6: Top Back-Right
        QVector3D( hw, h_val,  hd),  # 7: Top Back-Left
    ]
    mesh.original_vertices = [(v.x(), v.y(), v.z()) for v in mesh.vertices]

    quads = [
        (0, 3, 2, 1),  # Bottom (-Y)
        (4, 5, 6, 7),  # Top (+Y)
        (0, 1, 5, 4),  # Front (-Z)
        (2, 3, 7, 6),  # Back (+Z)
        (3, 0, 4, 7),  # Left (+X)
        (1, 2, 6, 5),  # Right (-X)
    ]

    mesh.faces = []
    mesh.coplanar_edges = set()
    mesh.polygon_edges = set()

    for q in quads:
        v0, v1, v2, v3 = q
        mesh.faces.append((v0, v1, v2))
        mesh.faces.append((v0, v2, v3))
        mesh.coplanar_edges.add((min(v0, v2), max(v0, v2)))
        mesh.polygon_edges.add((min(v0, v1), max(v0, v1)))
        mesh.polygon_edges.add((min(v1, v2), max(v1, v2)))
        mesh.polygon_edges.add((min(v2, v3), max(v2, v3)))
        mesh.polygon_edges.add((min(v3, v0), max(v3, v0)))

    mesh.compute_face_normals()
    mesh.bbox_min = QVector3D(-hw, 0.0, -hd)
    mesh.bbox_max = QVector3D(hw, h_val, hd)
    mesh.center = QVector3D(0.0, h_val * 0.5, 0.0)
    mesh.radius = math.sqrt(hw*hw + (h_val*0.5)**2 + hd*hd)
    mesh.scale = 1.0
    mesh.primitive_type = "Box"
    mesh.primitive_params = {"w": float(w), "h": float(h), "d": float(d)}
    return mesh


def create_cylinder_primitive(radius=1.0, height=2.0, segments=24, name="Primitive Cylinder"):
    """Generates a clean cylinder mesh with base at Y=0, height upwards, pivot at base."""
    mesh = MeshData(name)
    h_val = max(0.05, float(height))
    r = max(0.05, float(radius))
    segments = max(6, int(segments))

    mesh.vertices.append(QVector3D(0, 0.0, 0))  # 0: Bottom center
    mesh.vertices.append(QVector3D(0, h_val, 0))  # 1: Top center

    # Bottom ring vertices: 2 .. 2 + segments - 1 (Y=0.0)
    for i in range(segments):
        ang = 2.0 * math.pi * i / segments
        x = r * math.cos(ang)
        z = r * math.sin(ang)
        mesh.vertices.append(QVector3D(x, 0.0, z))

    # Top ring vertices: 2 + segments .. 2 + 2*segments - 1 (Y=h_val)
    for i in range(segments):
        ang = 2.0 * math.pi * i / segments
        x = r * math.cos(ang)
        z = r * math.sin(ang)
        mesh.vertices.append(QVector3D(x, h_val, z))

    mesh.faces = []
    mesh.polygon_edges = set()
    mesh.coplanar_edges = set()

    for i in range(segments):
        ni = (i + 1) % segments
        b1 = 2 + i; b2 = 2 + ni
        t1 = 2 + segments + i; t2 = 2 + segments + ni

        # Bottom cap (pointing down -Y)
        mesh.faces.append((0, b1, b2))
        # Top cap (pointing up +Y)
        mesh.faces.append((1, t2, t1))
        # Side quad: two triangles (pointing outward)
        mesh.faces.append((b1, t1, t2))
        mesh.faces.append((b1, t2, b2))

        mesh.coplanar_edges.add((min(b1, t2), max(b1, t2)))
        mesh.polygon_edges.add((min(b1, b2), max(b1, b2)))
        mesh.polygon_edges.add((min(t1, t2), max(t1, t2)))
        mesh.polygon_edges.add((min(b1, t1), max(b1, t1)))

    mesh.original_vertices = [(v.x(), v.y(), v.z()) for v in mesh.vertices]
    mesh.compute_face_normals()
    mesh.bbox_min = QVector3D(-r, 0.0, -r)
    mesh.bbox_max = QVector3D(r, h_val, r)
    mesh.center = QVector3D(0.0, h_val * 0.5, 0.0)
    mesh.radius = math.sqrt(r*r + (h_val*0.5)**2)
    mesh.scale = 1.0
    mesh.primitive_type = "Cylinder"
    mesh.primitive_params = {"radius": float(radius), "height": float(height), "segments": int(segments)}
    return mesh


def create_sphere_primitive(radius=1.0, rings=16, sectors=24, name="Primitive Sphere"):
    """Generates a smooth UV sphere mesh with base resting at Y=0, pivot at base."""
    mesh = MeshData(name)
    r = max(0.05, float(radius))
    rings = max(4, int(rings))
    sectors = max(4, int(sectors))

    # Top pole (North): index 0 at Y = 2*r
    mesh.vertices.append(QVector3D(0.0, 2.0 * r, 0.0))

    # Intermediate rings: (rings - 1) rings * sectors, Y = r + r * cos(phi)
    for i in range(1, rings):
        phi = math.pi * i / rings
        y = r + r * math.cos(phi)
        r_ring = r * math.sin(phi)
        for j in range(sectors):
            theta = 2.0 * math.pi * j / sectors
            x = r_ring * math.sin(theta)
            z = r_ring * math.cos(theta)
            mesh.vertices.append(QVector3D(x, y, z))

    # Bottom pole (South): index len(vertices) at Y = 0.0
    south_idx = len(mesh.vertices)
    mesh.vertices.append(QVector3D(0.0, 0.0, 0.0))

    mesh.faces = []
    mesh.polygon_edges = set()
    mesh.coplanar_edges = set()

    # Top cap triangles (connect top pole 0 to first ring)
    for j in range(sectors):
        nj = (j + 1) % sectors
        v1 = 1 + j
        v2 = 1 + nj
        mesh.faces.append((0, v1, v2))
        mesh.polygon_edges.add((min(0, v1), max(0, v1)))
        mesh.polygon_edges.add((min(v1, v2), max(v1, v2)))

    # Middle body quads
    for i in range(rings - 2):
        row_curr = 1 + i * sectors
        row_next = 1 + (i + 1) * sectors
        for j in range(sectors):
            nj = (j + 1) % sectors
            i0 = row_curr + j
            i1 = row_curr + nj
            i2 = row_next + j
            i3 = row_next + nj

            mesh.faces.append((i0, i2, i1))
            mesh.faces.append((i1, i2, i3))
            mesh.coplanar_edges.add((min(i1, i2), max(i1, i2)))
            mesh.polygon_edges.add((min(i0, i1), max(i0, i1)))
            mesh.polygon_edges.add((min(i0, i2), max(i0, i2)))

    # Bottom cap triangles (connect last ring to south pole)
    last_row = 1 + (rings - 2) * sectors
    for j in range(sectors):
        nj = (j + 1) % sectors
        v1 = last_row + j
        v2 = last_row + nj
        mesh.faces.append((south_idx, v2, v1))
        mesh.polygon_edges.add((min(south_idx, v1), max(south_idx, v1)))
        mesh.polygon_edges.add((min(v1, v2), max(v1, v2)))

    mesh.original_vertices = [(v.x(), v.y(), v.z()) for v in mesh.vertices]
    mesh.compute_face_normals()
    mesh.bbox_min = QVector3D(-r, 0.0, -r)
    mesh.bbox_max = QVector3D(r, 2.0 * r, r)
    mesh.center = QVector3D(0.0, r, 0.0)
    mesh.radius = r
    mesh.scale = 1.0
    mesh.primitive_type = "Sphere"
    mesh.primitive_params = {"radius": float(radius), "rings": int(rings), "sectors": int(sectors)}
    return mesh


def create_pyramid_primitive(w=2.0, h=2.0, d=2.0, name="Primitive Pyramid"):
    """Generates a 4-sided pyramid mesh with base at Y=0, height upwards, pivot at base."""
    mesh = MeshData(name)
    hw, hd = max(0.05, float(w) * 0.5), max(0.05, float(d) * 0.5)
    h_val = max(0.05, float(h))

    mesh.vertices = [
        QVector3D( hw, 0.0, -hd),  # 0: FL
        QVector3D(-hw, 0.0, -hd),  # 1: FR
        QVector3D(-hw, 0.0,  hd),  # 2: BR
        QVector3D( hw, 0.0,  hd),  # 3: BL
        QVector3D(0.0, h_val, 0.0), # 4: Apex
    ]
    mesh.original_vertices = [(v.x(), v.y(), v.z()) for v in mesh.vertices]

    mesh.faces = [
        (0, 3, 2), (0, 2, 1), # Base
        (0, 1, 4),           # Front
        (1, 2, 4),           # Right
        (2, 3, 4),           # Back
        (3, 0, 4),           # Left
    ]
    mesh.coplanar_edges = {(0, 2)}
    mesh.polygon_edges = {
        (0, 1), (1, 2), (2, 3), (3, 0),
        (0, 4), (1, 4), (2, 4), (3, 4)
    }

    mesh.compute_face_normals()
    mesh.bbox_min = QVector3D(-hw, 0.0, -hd)
    mesh.bbox_max = QVector3D(hw, h_val, hd)
    mesh.center = QVector3D(0.0, h_val * 0.5, 0.0)
    mesh.radius = math.sqrt(hw*hw + (h_val*0.5)**2 + hd*hd)
    mesh.scale = 1.0
    mesh.primitive_type = "Pyramid"
    mesh.primitive_params = {"w": float(w), "h": float(h), "d": float(d)}
    return mesh


def create_cone_primitive(radius=1.0, height=2.0, segments=24, name="Primitive Cone"):
    """Generates a clean cone mesh with base at Y=0, height upwards, pivot at base."""
    mesh = MeshData(name)
    h_val = max(0.05, float(height))
    r = max(0.05, float(radius))
    segments = max(6, int(segments))

    mesh.vertices.append(QVector3D(0, 0.0, 0))  # 0: Bottom center
    mesh.vertices.append(QVector3D(0, h_val, 0))  # 1: Apex

    for i in range(segments):
        ang = 2.0 * math.pi * i / segments
        x = r * math.cos(ang)
        z = r * math.sin(ang)
        mesh.vertices.append(QVector3D(x, 0.0, z))  # 2 + i: bottom ring

    mesh.faces = []
    mesh.polygon_edges = set()
    mesh.coplanar_edges = set()

    for i in range(segments):
        ni = (i + 1) % segments
        b1 = 2 + i; b2 = 2 + ni

        mesh.faces.append((0, b1, b2))  # Base (pointing down -Y)
        mesh.faces.append((b1, 1, b2))  # Side to apex (pointing outward)

        mesh.polygon_edges.add((min(b1, b2), max(b1, b2)))
        mesh.polygon_edges.add((min(b1, 1), max(b1, 1)))

    mesh.original_vertices = [(v.x(), v.y(), v.z()) for v in mesh.vertices]
    mesh.compute_face_normals()
    mesh.bbox_min = QVector3D(-r, 0.0, -r)
    mesh.bbox_max = QVector3D(r, h_val, r)
    mesh.center = QVector3D(0.0, h_val * 0.5, 0.0)
    mesh.radius = math.sqrt(r*r + (h_val*0.5)**2)
    mesh.scale = 1.0
    mesh.primitive_type = "Cone"
    mesh.primitive_params = {"radius": float(radius), "height": float(height), "segments": int(segments)}
    return mesh


def create_plane_primitive(w=2.0, d=2.0, subdivisions=1, name="Primitive Plane"):
    """Generates a flat horizontal plane/grid mesh visible from both sides."""
    mesh = MeshData(name)
    hw = max(0.05, float(w) * 0.5)
    hd = max(0.05, float(d) * 0.5)
    subs = max(1, min(32, int(subdivisions)))

    for j in range(subs + 1):
        z = -hd + 2.0 * hd * (j / subs)
        for i in range(subs + 1):
            x = -hw + 2.0 * hw * (i / subs)
            mesh.vertices.append(QVector3D(x, 0.0, z))

    mesh.faces = []
    mesh.polygon_edges = set()
    mesh.coplanar_edges = set()

    row_len = subs + 1
    for j in range(subs):
        for i in range(subs):
            i0 = j * row_len + i
            i1 = j * row_len + (i + 1)
            i2 = (j + 1) * row_len + (i + 1)
            i3 = (j + 1) * row_len + i

            # Top faces (pointing up +Y)
            mesh.faces.append((i0, i2, i1))
            mesh.faces.append((i0, i3, i2))
            # Bottom faces (pointing down -Y for two-sided visibility)
            mesh.faces.append((i0, i1, i2))
            mesh.faces.append((i0, i2, i3))

            mesh.coplanar_edges.add((min(i0, i2), max(i0, i2)))
            mesh.polygon_edges.add((min(i0, i1), max(i0, i1)))
            mesh.polygon_edges.add((min(i1, i2), max(i1, i2)))
            mesh.polygon_edges.add((min(i2, i3), max(i2, i3)))
            mesh.polygon_edges.add((min(i3, i0), max(i3, i0)))

    mesh.original_vertices = [(v.x(), v.y(), v.z()) for v in mesh.vertices]
    mesh.compute_face_normals()
    mesh.bbox_min = QVector3D(-hw, -0.01, -hd)
    mesh.bbox_max = QVector3D(hw, 0.01, hd)
    mesh.center = QVector3D(0.0, 0.0, 0.0)
    mesh.radius = math.sqrt(hw*hw + hd*hd)
    mesh.scale = 1.0
    mesh.primitive_type = "Plane"
    mesh.primitive_params = {"w": float(w), "d": float(d), "subdivisions": int(subs)}
    return mesh


# -----------------------------------------------------------------------------
# Geometric Helpers & Closed-Form Perspective Solvers
# -----------------------------------------------------------------------------

def line_equation(p1, p2):
    """Returns normalized (A, B, C) for line Ax + By + C = 0."""
    a = p1.y() - p2.y()
    b = p2.x() - p1.x()
    c = p1.x() * p2.y() - p2.x() * p1.y()
    norm = math.hypot(a, b)
    if norm > 1e-8:
        return a / norm, b / norm, c / norm
    return 0.0, 0.0, 0.0


def intersect_lines(p1, p2, p3, p4):
    """Finds intersection point of line (p1, p2) and line (p3, p4)."""
    l1 = line_equation(p1, p2)
    l2 = line_equation(p3, p4)
    a1, b1, c1 = l1
    a2, b2, c2 = l2
    det = a1 * b2 - a2 * b1
    if abs(det) < 1e-7:
        return None
    x = (b1 * c2 - b2 * c1) / det
    y = (a2 * c1 - a1 * c2) / det
    return QPointF(x, y)


def _clamp(v, lo, hi):
    """Clamps a numeric value between lo and hi without requiring numpy."""
    return max(lo, min(hi, v))


def solve_linear_system(A, b):
    """Solves A * x = b for square matrix A via Gaussian elimination with partial pivoting."""
    n = len(A)
    M = [list(A[i]) + [b[i]] for i in range(n)]
    for i in range(n):
        pivot = max(range(i, n), key=lambda r: abs(M[r][i]))
        M[i], M[pivot] = M[pivot], M[i]
        diag = M[i][i]
        if abs(diag) < 1e-12:
            diag = 1e-12
        inv_diag = 1.0 / diag
        for j in range(i, n + 1):
            M[i][j] *= inv_diag
        for r in range(n):
            if r != i:
                factor = M[r][i]
                if abs(factor) > 1e-15:
                    for j in range(i, n + 1):
                        M[r][j] -= factor * M[i][j]
    return [M[i][n] for i in range(n)]


def solve_linear_least_squares(A, B):
    """Solves A * x = B via least squares. Uses NumPy if available, with pure Python fallback."""
    if HAVE_NUMPY:
        try:
            sol, _, _, _ = np.linalg.lstsq(A, B, rcond=None)
            return [float(v) for v in sol]
        except Exception:
            pass

    # Pure Python least squares via Normal Equations (A^T A x = A^T B)
    m = len(A)
    n = len(A[0])
    AtA = [[sum(A[k][i] * A[k][j] for k in range(m)) for j in range(n)] for i in range(n)]
    AtB = [sum(A[k][i] * B[k] for k in range(m)) for i in range(n)]
    return solve_linear_system(AtA, AtB)


def solve_perspective_box(b0, b1, b2, b3, t0, t1, t2, t3, canvas_w, canvas_h,
                          auto_fov=True, default_fov=45.0, keep_horizon=True):
    w_doc = max(10, float(canvas_w))
    h_doc = max(10, float(canvas_h))
    render_size = min(w_doc, h_doc)
    half_size = render_size * 0.5
    cx = w_doc * 0.5
    cy = h_doc * 0.5
    offset_x = (w_doc - render_size) * 0.5
    offset_y = (h_doc - render_size) * 0.5

    def line_eq(p1, p2):
        a = p1.y() - p2.y()
        b = p2.x() - p1.x()
        c = p1.x() * p2.y() - p2.x() * p1.y()
        n = math.hypot(a, b)
        return (a / n, b / n, c / n) if n > 1e-8 else (0.0, 0.0, 0.0)

    def intersect(l1, l2):
        det = l1[0] * l2[1] - l2[0] * l1[1]
        if abs(det) < 1e-7:
            return None
        return QPointF((l1[1] * l2[2] - l2[1] * l1[2]) / det,
                       (l2[0] * l1[2] - l1[0] * l2[2]) / det)

    vpx = intersect(line_eq(b0, b1), line_eq(b3, b2))
    vpz = intersect(line_eq(b0, b3), line_eq(b1, b2))

    # Reject vanishing points on wrong side
    if vpx is not None and vpx.x() < b0.x():
        vpx = None
    if vpz is not None and vpz.x() > b0.x():
        vpz = None

    fov = float(default_fov)
    tan_fov = math.tan(math.radians(max(5.0, fov * 0.5)))
    f = half_size / tan_fov

    if auto_fov and vpx is not None and vpz is not None:
        dot = (vpx.x() - cx) * (vpz.x() - cx) + (vpx.y() - cy) * (vpz.y() - cy)
        if dot < -50.0:
            f_cand = math.sqrt(-dot)
            fov_cand = 2.0 * math.degrees(math.atan(half_size / f_cand))
            if 15.0 <= fov_cand <= 120.0:
                f = f_cand
                fov = fov_cand

    # Initial pitch, roll, yaw
    pitch0 = 18.0
    roll0 = 0.0
    yaw0 = 145.0

    if vpx is not None and vpz is not None:
        hy = (vpx.y() + vpz.y()) * 0.5
        if abs(hy - cy) < h_doc * 3.0:
            pitch0 = float(_clamp(math.degrees(math.atan2(cy - hy, f)), -75.0, 75.0))
            if not keep_horizon:
                dx = vpz.x() - vpx.x()
                dy = vpz.y() - vpx.y()
                roll0 = float(_clamp(math.degrees(math.atan2(dy, dx)), -45.0, 45.0))
        cos_p = max(0.01, math.cos(math.radians(pitch0)))
        tan_y = (vpz.x() - cx) * cos_p / f
        yaw0 = float((180.0 + math.degrees(math.atan(tan_y))) % 360.0)
    elif vpz is not None:
        if abs(vpz.y() - cy) < h_doc * 3.0:
            pitch0 = float(_clamp(math.degrees(math.atan2(cy - vpz.y(), f)), -75.0, 75.0))
        cos_p = max(0.01, math.cos(math.radians(pitch0)))
        tan_y = (vpz.x() - cx) * cos_p / f
        yaw0 = float((180.0 + math.degrees(math.atan(tan_y))) % 360.0)
    elif vpx is not None:
        if abs(vpx.y() - cy) < h_doc * 3.0:
            pitch0 = float(_clamp(math.degrees(math.atan2(cy - vpx.y(), f)), -75.0, 75.0))
        cos_p = max(0.01, math.cos(math.radians(pitch0)))
        tan_y = -f / ((vpx.x() - cx) * cos_p)
        yaw0 = float((180.0 + math.degrees(math.atan(tan_y))) % 360.0)

    # Initial box extents:
    w01 = math.hypot(b1.x() - b0.x(), b1.y() - b0.y())
    w03 = math.hypot(b3.x() - b0.x(), b3.y() - b0.y())
    h0 = abs(b0.y() - t0.y())

    center_x = (b0.x() + b1.x() + b2.x() + b3.x()) * 0.25
    center_y = (b0.y() + b1.y() + b2.y() + b3.y()) * 0.25 - h0 * 0.5

    dist0 = 4.0
    px0 = ((center_x - cx) / f) * dist0
    py0 = -((center_y - cy) / f) * dist0

    hw0 = max(0.1, (w01 / render_size) * dist0 * 0.6)
    hd0 = max(0.1, (w03 / render_size) * dist0 * 0.6)
    hh0 = max(0.1, (h0 / render_size) * dist0 * 0.6)

    p_init = [yaw0, pitch0, roll0, dist0, px0, py0, hw0, hh0, hd0]
    target_pts = [
        (b0.x(), b0.y()),
        (b1.x(), b1.y()),
        (b2.x(), b2.y()),
        (b3.x(), b3.y()),
        (t0.x(), t0.y()),
    ]
    weights = [3.0, 3.0, 3.0, 3.0, 1.2]
    signs = [(+1, -1, -1), (-1, -1, -1), (-1, -1, +1), (+1, -1, +1), (+1, +1, -1)]

    def project_p(param):
        yaw, pitch, roll, dist, px, py, hw, hh, hd = param
        cam = Camera3D()
        cam.yaw = yaw
        cam.pitch = pitch
        cam.roll = roll if not keep_horizon else 0.0
        cam.fov = fov
        cam.distance = max(0.2, dist)
        cam.pan_x = px
        cam.pan_y = py
        _, view, _ = cam.get_matrices(render_size, render_size)
        res = []
        for (sx, sy, sz), (tx, ty), w in zip(signs, target_pts, weights):
            pt, _ = project_camera_point(cam, view, sx * hw, sy * hh, sz * hd, render_size, offset_x, offset_y)
            if pt is None:
                res.extend([1000.0, 1000.0])
            else:
                res.extend([(pt.x() - tx) * w, (pt.y() - ty) * w])
        return res

    p = None
    if HAVE_NUMPY:
        try:
            p_np = np.array(p_init, dtype=float)

            def project_p_np(param):
                return np.array(project_p(param), dtype=float)

            p_curr = p_np
            lam = 0.05
            eps = 1e-4
            for _ in range(25):
                r = project_p_np(p_curr)
                err = float(np.sum(r**2))
                J = np.zeros((len(r), len(p_curr)))
                for j in range(len(p_curr)):
                    if keep_horizon and j == 2:
                        continue
                    pj = p_curr.copy()
                    pj[j] += eps
                    rj = project_p_np(pj)
                    J[:, j] = (rj - r) / eps
                JtJ = J.T @ J
                diag = np.diag(np.diag(JtJ))
                try:
                    delta = np.linalg.solve(JtJ + lam * diag + 1e-4 * np.eye(len(p_curr)), -J.T @ r)
                except Exception:
                    break
                delta[0] = max(-30.0, min(30.0, float(delta[0])))
                delta[1] = max(-20.0, min(20.0, float(delta[1])))
                p_cand = p_curr + delta
                p_cand[0] = p_cand[0] % 360.0
                p_cand[1] = max(-85.0, min(85.0, p_cand[1]))
                p_cand[3] = max(0.5, p_cand[3])
                p_cand[6] = max(0.05, abs(p_cand[6]))
                p_cand[7] = max(0.05, abs(p_cand[7]))
                p_cand[8] = max(0.05, abs(p_cand[8]))
                if keep_horizon:
                    p_cand[2] = 0.0

                r_cand = project_p_np(p_cand)
                err_cand = float(np.sum(r_cand**2))
                if err_cand < err:
                    p_curr = p_cand
                    lam = max(1e-4, lam * 0.4)
                    if abs(err - err_cand) < 0.05:
                        break
                else:
                    lam = min(1e4, lam * 3.0)
            p = [float(x) for x in p_curr]
        except Exception:
            p = None

    if p is None:
        p = list(p_init)
        n_p = len(p)
        lam = 0.05
        eps = 1e-4

        for _ in range(25):
            r = project_p(p)
            err = sum(x * x for x in r)
            m = len(r)

            J = [[0.0] * n_p for _ in range(m)]
            for j in range(n_p):
                if keep_horizon and j == 2:
                    continue
                pj = list(p)
                pj[j] += eps
                rj = project_p(pj)
                inv_eps = 1.0 / eps
                for i in range(m):
                    J[i][j] = (rj[i] - r[i]) * inv_eps

            A = [[0.0] * n_p for _ in range(n_p)]
            rhs = [0.0] * n_p
            for i in range(n_p):
                if keep_horizon and i == 2:
                    A[i][i] = 1.0
                    rhs[i] = 0.0
                    continue
                for j in range(n_p):
                    if keep_horizon and j == 2:
                        continue
                    s = sum(J[k][i] * J[k][j] for k in range(m))
                    A[i][j] = s
                A[i][i] += lam * A[i][i] + 1e-4
                rhs[i] = -sum(J[k][i] * r[k] for k in range(m))

            try:
                delta = solve_linear_system(A, rhs)
            except Exception:
                break

            delta[0] = max(-30.0, min(30.0, float(delta[0])))
            delta[1] = max(-20.0, min(20.0, float(delta[1])))
            p_cand = [p[i] + delta[i] for i in range(n_p)]
            p_cand[0] = p_cand[0] % 360.0
            p_cand[1] = max(-85.0, min(85.0, p_cand[1]))
            p_cand[3] = max(0.5, p_cand[3])
            p_cand[6] = max(0.05, abs(p_cand[6]))
            p_cand[7] = max(0.05, abs(p_cand[7]))
            p_cand[8] = max(0.05, abs(p_cand[8]))
            if keep_horizon:
                p_cand[2] = 0.0

            r_cand = project_p(p_cand)
            err_cand = sum(x * x for x in r_cand)
            if err_cand < err:
                p = p_cand
                lam = max(1e-4, lam * 0.4)
                if abs(err - err_cand) < 0.05:
                    break
            else:
                lam = min(1e4, lam * 3.0)

    yaw, pitch, roll, dist, px, py, hw, hh, hd = p
    yaw = float(yaw) % 360.0
    pitch = max(-85.0, min(85.0, float(pitch)))
    roll = 0.0 if keep_horizon else roll

    # Scale-invariant normalization:
    # In 3D perspective projection, scaling all spatial coordinates and distance by scalar s
    # leaves the 2D projected image 100% mathematically identical: (s * x) / (s * dist) = x / dist.
    # Normalizing target_dist to 4.0 guarantees that camera distance stays in standard orbit range,
    # viewport sliders never clamp or cause zoom jumps, and 3D proportions are perfectly preserved.
    target_dist = 4.0
    s = target_dist / max(0.2, dist)
    box_w = 2.0 * hw * s
    box_h = 2.0 * hh * s
    box_d = 2.0 * hd * s
    dist = target_dist
    px *= s
    py *= s

    cam_sol = Camera3D()
    cam_sol.yaw = float(yaw)
    cam_sol.pitch = float(pitch)
    cam_sol.roll = float(roll)
    cam_sol.fov = float(fov)
    cam_sol.distance = float(dist)
    cam_sol.pan_x = float(px)
    cam_sol.pan_y = float(py)
    _, view_sol, _ = cam_sol.get_matrices(render_size, render_size)

    hw_s = box_w * 0.5
    hh_s = box_h * 0.5
    hd_s = box_d * 0.5
    corners_3d = [
        QVector3D( hw_s, -hh_s, -hd_s),  # b0
        QVector3D(-hw_s, -hh_s, -hd_s),  # b1
        QVector3D(-hw_s, -hh_s,  hd_s),  # b2
        QVector3D( hw_s, -hh_s,  hd_s),  # b3
        QVector3D( hw_s,  hh_s, -hd_s),  # t0
        QVector3D(-hw_s,  hh_s, -hd_s),  # t1
        QVector3D(-hw_s,  hh_s,  hd_s),  # t2
        QVector3D( hw_s,  hh_s,  hd_s),  # t3
    ]
    proj_corners = [
        project_camera_point(cam_sol, view_sol, c.x(), c.y(), c.z(), render_size, offset_x, offset_y)[0]
        for c in corners_3d
    ]

    mm_equiv = int(round((36.0 * 0.5) / math.tan(math.radians(max(5.0, fov * 0.5)))))
    center_2d = QPointF(center_x, center_y)

    horizon = None
    if vpx and vpz:
        horizon = line_eq(vpx, vpz)

    return {
        "persp_type": "2-Point" if vpx and vpz else "1-Point",
        "fov": float(fov),
        "focal_mm": mm_equiv,
        "pitch": float(pitch),
        "yaw": float(yaw),
        "roll": float(roll),
        "distance": float(dist),
        "pan_x": float(px),
        "pan_y": float(py),
        "target_x": 0.0,
        "target_y": 0.0,
        "target_z": 0.0,
        "box_w": float(box_w),
        "box_h": float(box_h),
        "box_d": float(box_d),
        "vp_x": vpx,
        "vp_z": vpz,
        "horizon": horizon,
        "center_2d": center_2d,
        "projected_corners": proj_corners,
    }


# -----------------------------------------------------------------------------
# Box Drawer Interactive Canvas Widget
# -----------------------------------------------------------------------------

class BoxDrawerWidget(QWidget):
    """
    Interactive drawing canvas where the artist can position the 3D box pins
    directly over their sketch or drawing, seeing live perspective vanishing lines,
    horizon, and a real-time rendered 3D preview.
    """
    solution_changed = pyqtSignal(dict)
    click_draw_finished = pyqtSignal()

    HANDLE_BASE_0 = 0  # Front-Left
    HANDLE_BASE_1 = 1  # Front-Right
    HANDLE_BASE_2 = 2  # Back-Right
    HANDLE_BASE_3 = 3  # Back-Left
    HANDLE_HEIGHT = 4  # Top Height Pin
    HANDLE_CENTER = 5  # Pan/Move whole box
    HANDLE_TOP_0  = 6  # Unlocked Top FL
    HANDLE_TOP_1  = 7  # Unlocked Top FR
    HANDLE_TOP_2  = 8  # Unlocked Top BR
    HANDLE_TOP_3  = 9  # Unlocked Top BL

    HANDLE_RADIUS = 9

    def __init__(self, bg_image=None, camera=None, lighting=None, renderer=None, parent=None):
        super().__init__(parent)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)

        self.bg_image = bg_image
        self.camera = camera
        self.lighting = lighting or Lighting3D()
        self.renderer = renderer or Renderer3D()

        self.img_rect = QRectF()
        self.active_handle = None
        self.drag_start_pos = None

        self.auto_fov = True
        self.keep_horizon = True
        self.unlock_top_corners = False
        self.primitive_type = "Box"
        self.box_opacity = 0.80

        # Click-to-draw state
        self.click_draw_mode = False
        self.click_draw_step = 0
        self.click_points = []
        self.hover_doc_pos = None

        # Document-space box corner coordinates
        dw = bg_image.width() if (bg_image and not bg_image.isNull()) else 0
        dh = bg_image.height() if (bg_image and not bg_image.isNull()) else 0
        if dw <= 0 or dh <= 0:
            try:
                from .canvas_sync import CanvasSyncManager
                info = CanvasSyncManager.get_document_info()
                if info and info.get("width", 0) > 0 and info.get("height", 0) > 0:
                    dw = int(info["width"])
                    dh = int(info["height"])
            except Exception:
                pass
        if dw <= 0 or dh <= 0:
            dw = 1200
            dh = 900
        self.doc_w = dw
        self.doc_h = dh

        self.last_solution = {}
        self.cached_preview_mesh = None
        self.pb0 = None; self.pb1 = None; self.pb2 = None; self.pb3 = None
        self.pt0 = None; self.pt1 = None; self.pt2 = None; self.pt3 = None

        # Initialize corners with classic 2-point eye level perspective
        self.apply_preset("2pt_eye")

    def start_click_draw(self):
        """Activates 4-click draw mode. Hides 3D box so canvas is clear."""
        self.click_draw_mode = True
        self.click_draw_step = 0
        self.click_points = []
        self.update()

    def cancel_click_draw(self):
        """Cancels 4-click draw and restores the previous box."""
        self.click_draw_mode = False
        self.click_draw_step = 0
        self.click_points = []
        self.update()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            if self.click_draw_mode:
                self.cancel_click_draw()
                self.click_draw_finished.emit()
                event.accept()
                return
        super().keyPressEvent(event)

    def restore_from_entry(self, entry):
        """Restores all primitive corners, proportions, and camera solution from a saved history entry."""
        if not entry:
            return
        self.primitive_type = entry.get("primitive_type", "Box")
        self.auto_fov = entry.get("auto_fov", True)
        self.keep_horizon = entry.get("keep_horizon", True)
        self.unlock_top_corners = entry.get("unlock_top", False)
        self.box_opacity = float(entry.get("box_opacity", 0.80))

        old_doc_w, old_doc_h = entry.get("doc_size", [self.doc_w, self.doc_h])
        sx = (float(self.doc_w) / float(old_doc_w)) if (old_doc_w > 0 and self.doc_w > 0) else 1.0
        sy = (float(self.doc_h) / float(old_doc_h)) if (old_doc_h > 0 and self.doc_h > 0) else 1.0

        corners = entry.get("corners", {})
        if corners and "b0" in corners:
            b0 = corners["b0"]
            b1 = corners["b1"]
            b2 = corners["b2"]
            b3 = corners["b3"]
            self.b0 = QPointF(float(b0[0]) * sx, float(b0[1]) * sy)
            self.b1 = QPointF(float(b1[0]) * sx, float(b1[1]) * sy)
            self.b2 = QPointF(float(b2[0]) * sx, float(b2[1]) * sy)
            self.b3 = QPointF(float(b3[0]) * sx, float(b3[1]) * sy)

            if "t0" in corners and self.unlock_top_corners:
                t0 = corners["t0"]; t1 = corners["t1"]; t2 = corners["t2"]; t3 = corners["t3"]
                self.t0 = QPointF(float(t0[0]) * sx, float(t0[1]) * sy)
                self.t1 = QPointF(float(t1[0]) * sx, float(t1[1]) * sy)
                self.t2 = QPointF(float(t2[0]) * sx, float(t2[1]) * sy)
                self.t3 = QPointF(float(t3[0]) * sx, float(t3[1]) * sy)
                self.height_offset = entry.get("height_offset", abs(self.b0.y() - self.t0.y())) * sy
            else:
                raw_h = entry.get("height_offset", 150.0)
                self.height_offset = max(20.0, raw_h * sy)
                self._update_top_corners_from_height()

        self._recalculate()
        self.update()

    # -------------------------------------------------------------------------
    # Coordinate Transforms (Widget <-> Document Image)
    # -------------------------------------------------------------------------

    def _doc_to_widget(self, pt):
        if not self.img_rect.isValid() or self.doc_w <= 0:
            return pt
        sx = self.img_rect.width() / float(self.doc_w)
        sy = self.img_rect.height() / float(self.doc_h)
        return QPointF(self.img_rect.x() + pt.x() * sx, self.img_rect.y() + pt.y() * sy)

    def _widget_to_doc(self, pt):
        if not self.img_rect.isValid() or self.img_rect.width() <= 0:
            return pt
        sx = float(self.doc_w) / self.img_rect.width()
        sy = float(self.doc_h) / self.img_rect.height()
        return QPointF((pt.x() - self.img_rect.x()) * sx, (pt.y() - self.img_rect.y()) * sy)

    def _update_top_corners_from_height(self):
        """Updates top corners from base corners and current height offset in true perspective."""
        if not self.unlock_top_corners:
            self.t0 = QPointF(self.b0.x(), self.b0.y() - self.height_offset)

            # Find base vanishing points
            vpx = intersect_lines(self.b0, self.b1, self.b3, self.b2)
            vpz = intersect_lines(self.b0, self.b3, self.b1, self.b2)

            p_up1 = QPointF(self.b1.x(), self.b1.y() - 4000.0)
            p_up3 = QPointF(self.b3.x(), self.b3.y() - 4000.0)

            if vpx is not None:
                t1 = intersect_lines(self.t0, vpx, self.b1, p_up1)
            else:
                t1 = QPointF(self.b1.x(), self.t0.y())
            self.t1 = t1 if t1 else QPointF(self.b1.x(), self.t0.y())

            if vpz is not None:
                t3 = intersect_lines(self.t0, vpz, self.b3, p_up3)
            else:
                t3 = QPointF(self.b3.x(), self.t0.y())
            self.t3 = t3 if t3 else QPointF(self.b3.x(), self.t0.y())

            if vpx is not None and vpz is not None:
                t2 = intersect_lines(self.t1, vpz, self.t3, vpx)
            elif vpz is not None:
                t2 = intersect_lines(self.t1, vpz, self.b2, QPointF(self.b2.x(), self.b2.y() - 4000.0))
            else:
                t2 = QPointF(self.b2.x(), self.t3.y())
            self.t2 = t2 if t2 else QPointF(self.b2.x(), (self.t1.y() + self.t3.y()) * 0.5)

    def _recalculate(self):
        default_fov = self.camera.fov if self.camera else 45.0
        sol = solve_perspective_box(
            self.b0, self.b1, self.b2, self.b3,
            self.t0, self.t1, self.t2, self.t3,
            self.doc_w, self.doc_h,
            auto_fov=self.auto_fov,
            default_fov=default_fov,
            keep_horizon=self.keep_horizon
        )
        self.last_solution = sol

        # Generate preview mesh with exact physical dimensions
        bw = sol.get("box_w", 2.0)
        bh = sol.get("box_h", 2.0)
        bd = sol.get("box_d", 2.0)
        if self.primitive_type == "Box":
            self.cached_preview_mesh = create_box_primitive(bw, bh, bd)
        elif self.primitive_type == "Cylinder":
            self.cached_preview_mesh = create_cylinder_primitive(bw * 0.5, bh)
        elif self.primitive_type == "Sphere":
            self.cached_preview_mesh = create_sphere_primitive(max(bw, bh, bd) * 0.5)
        elif self.primitive_type == "Pyramid":
            self.cached_preview_mesh = create_pyramid_primitive(bw, bh, bd)
        elif self.primitive_type == "Cone":
            self.cached_preview_mesh = create_cone_primitive(bw * 0.5, bh)
        elif self.primitive_type == "Plane":
            self.cached_preview_mesh = create_plane_primitive(bw, bd, 2)

        proj = sol.get("projected_corners")
        if proj and len(proj) == 8:
            self.pb0, self.pb1, self.pb2, self.pb3 = proj[0:4]
            self.pt0, self.pt1, self.pt2, self.pt3 = proj[4:8]
            if not self.unlock_top_corners:
                self.t1 = QPointF(self.pt1)
                self.t2 = QPointF(self.pt2)
                self.t3 = QPointF(self.pt3)
        else:
            self.pb0, self.pb1, self.pb2, self.pb3 = self.b0, self.b1, self.b2, self.b3
            self.pt0, self.pt1, self.pt2, self.pt3 = self.t0, self.t1, self.t2, self.t3

        self.solution_changed.emit(sol)
        self.update()

    # -------------------------------------------------------------------------
    # Presets
    # -------------------------------------------------------------------------

    def apply_preset(self, name):
        """Applies classic artist perspective box templates computed from true 3D camera geometry."""
        dw, dh = self.doc_w, self.doc_h
        render_size = min(dw, dh)
        offset_x = (dw - render_size) * 0.5
        offset_y = (dh - render_size) * 0.5

        configs = {
            "2pt_eye":    {"yaw": 145.0, "pitch":  12.0, "dist": 4.6, "bw": 2.0, "bh": 1.8, "bd": 1.5},
            "birds_eye":  {"yaw": 145.0, "pitch":  30.0, "dist": 4.8, "bw": 2.0, "bh": 1.8, "bd": 1.5},
            "worms_eye":  {"yaw": 145.0, "pitch": -15.0, "dist": 4.8, "bw": 2.0, "bh": 1.8, "bd": 1.5},
            "1pt_front":  {"yaw": 180.0, "pitch":  10.0, "dist": 4.6, "bw": 2.0, "bh": 1.8, "bd": 1.5},
        }
        cfg = configs.get(name, configs["2pt_eye"])

        cam = Camera3D()
        cam.yaw = cfg["yaw"]
        cam.pitch = cfg["pitch"]
        cam.fov = 45.0
        cam.distance = cfg["dist"]
        _, view, _ = cam.get_matrices(render_size, render_size)

        hw, hh, hd = cfg["bw"] * 0.5, cfg["bh"] * 0.5, cfg["bd"] * 0.5
        corners = [
            QVector3D( hw, -hh, -hd),  # b0
            QVector3D(-hw, -hh, -hd),  # b1
            QVector3D(-hw, -hh,  hd),  # b2
            QVector3D( hw, -hh,  hd),  # b3
            QVector3D( hw,  hh, -hd),  # t0
            QVector3D(-hw,  hh, -hd),  # t1
            QVector3D(-hw,  hh,  hd),  # t2
            QVector3D( hw,  hh,  hd),  # t3
        ]
        pts = [project_camera_point(cam, view, c.x(), c.y(), c.z(), render_size, offset_x, offset_y)[0] for c in corners]

        self.b0 = pts[0]
        self.b1 = pts[1]
        self.b2 = pts[2]
        self.b3 = pts[3]
        self.t0 = pts[4]
        self.t1 = pts[5]
        self.t2 = pts[6]
        self.t3 = pts[7]

        self.height_offset = self.b0.y() - self.t0.y()
        self.unlock_top_corners = False
        self._recalculate()

    # -------------------------------------------------------------------------
    # Mouse Interaction
    # -------------------------------------------------------------------------

    def _get_handles_widget(self):
        """Returns list of (handle_id, QPointF_widget, label, color)."""
        wb0 = self._doc_to_widget(self.pb0 if self.pb0 is not None else self.b0)
        wb1 = self._doc_to_widget(self.pb1 if self.pb1 is not None else self.b1)
        wb2 = self._doc_to_widget(self.pb2 if self.pb2 is not None else self.b2)
        wb3 = self._doc_to_widget(self.pb3 if self.pb3 is not None else self.b3)
        wt0 = self._doc_to_widget(self.pt0 if self.pt0 is not None else self.t0)
        wt1 = self._doc_to_widget(self.pt1 if self.pt1 is not None else self.t1)
        wt2 = self._doc_to_widget(self.pt2 if self.pt2 is not None else self.t2)
        wt3 = self._doc_to_widget(self.pt3 if self.pt3 is not None else self.t3)

        # Height handle on front vertical pillar
        wh = QPointF(wt0.x(), wt0.y())

        # Center handle on ground plane
        wc = QPointF((wb0.x() + wb1.x() + wb2.x() + wb3.x()) * 0.25,
                     (wb0.y() + wb1.y() + wb2.y() + wb3.y()) * 0.25)

        handles = [
            (self.HANDLE_BASE_0, wb0, "1", QColor(34, 197, 94)),
            (self.HANDLE_BASE_1, wb1, "2", QColor(34, 197, 94)),
            (self.HANDLE_BASE_2, wb2, "3", QColor(34, 197, 94)),
            (self.HANDLE_BASE_3, wb3, "4", QColor(34, 197, 94)),
            (self.HANDLE_HEIGHT, wh, "▲ H", QColor(56, 189, 248)),
            (self.HANDLE_CENTER, wc, "✛", QColor(245, 158, 11)),
        ]

        if self.unlock_top_corners:
            handles.extend([
                (self.HANDLE_TOP_0, wt0, "T1", QColor(14, 165, 233)),
                (self.HANDLE_TOP_1, wt1, "T2", QColor(14, 165, 233)),
                (self.HANDLE_TOP_2, wt2, "T3", QColor(14, 165, 233)),
                (self.HANDLE_TOP_3, wt3, "T4", QColor(14, 165, 233)),
            ])
        return handles

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            pos = event.pos()

            # Click-to-draw mode
            if self.click_draw_mode:
                doc_pt = self._widget_to_doc(pos)
                self.click_points.append(doc_pt)
                self.click_draw_step += 1
                if self.click_draw_step == 1:
                    self.b0 = doc_pt
                elif self.click_draw_step == 2:
                    self.b1 = doc_pt
                elif self.click_draw_step == 3:
                    self.b2 = doc_pt
                    # Infer b3 as parallelogram
                    self.b3 = QPointF(self.b0.x() + (self.b2.x() - self.b1.x()),
                                      self.b0.y() + (self.b2.y() - self.b1.y()))
                    self.height_offset = max(30.0, math.hypot(self.b1.x() - self.b0.x(), self.b1.y() - self.b0.y()) * 0.8)
                    self._update_top_corners_from_height()
                elif self.click_draw_step == 4:
                    self.height_offset = max(20.0, abs(self.b0.y() - doc_pt.y()))
                    self._update_top_corners_from_height()
                    self.click_draw_mode = False
                    self.click_draw_step = 0
                    self.click_points = []
                    self.click_draw_finished.emit()
                    self._recalculate()
                self.update()
                event.accept()
                return

            # Check handle hits
            handles = self._get_handles_widget()
            for hid, hpos, _, _ in handles:
                if math.hypot(pos.x() - hpos.x(), pos.y() - hpos.y()) <= self.HANDLE_RADIUS + 5:
                    self.active_handle = hid
                    self.drag_start_pos = pos
                    self.drag_base_b0 = QPointF(self.b0)
                    self.drag_base_b1 = QPointF(self.b1)
                    self.drag_base_b2 = QPointF(self.b2)
                    self.drag_base_b3 = QPointF(self.b3)
                    self.drag_base_h = self.height_offset
                    event.accept()
                    return

        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        pos = event.pos()
        self.hover_doc_pos = self._widget_to_doc(pos)

        # Update cursor on hover
        if not self.click_draw_mode and self.active_handle is None:
            handles = self._get_handles_widget()
            hovering = False
            is_center = False
            for hid, hpos, _, _ in handles:
                if math.hypot(pos.x() - hpos.x(), pos.y() - hpos.y()) <= self.HANDLE_RADIUS + 5:
                    hovering = True
                    is_center = (hid == self.HANDLE_CENTER)
                    break
            if is_center:
                self.setCursor(Qt.SizeAllCursor)
            elif hovering:
                self.setCursor(Qt.PointingHandCursor)
            else:
                self.setCursor(Qt.ArrowCursor)

        if self.click_draw_mode:
            self.update()
            event.accept()
            return

        if self.active_handle is not None:
            doc_pos = self._widget_to_doc(pos)

            if self.active_handle == self.HANDLE_BASE_0:
                self.b0 = doc_pos
            elif self.active_handle == self.HANDLE_BASE_1:
                self.b1 = doc_pos
            elif self.active_handle == self.HANDLE_BASE_2:
                self.b2 = doc_pos
            elif self.active_handle == self.HANDLE_BASE_3:
                self.b3 = doc_pos
            elif self.active_handle == self.HANDLE_HEIGHT:
                self.height_offset = max(10.0, self.b0.y() - doc_pos.y())
            elif self.active_handle == self.HANDLE_CENTER:
                doc_start = self._widget_to_doc(self.drag_start_pos)
                dx = doc_pos.x() - doc_start.x()
                dy = doc_pos.y() - doc_start.y()
                self.b0 = QPointF(self.drag_base_b0.x() + dx, self.drag_base_b0.y() + dy)
                self.b1 = QPointF(self.drag_base_b1.x() + dx, self.drag_base_b1.y() + dy)
                self.b2 = QPointF(self.drag_base_b2.x() + dx, self.drag_base_b2.y() + dy)
                self.b3 = QPointF(self.drag_base_b3.x() + dx, self.drag_base_b3.y() + dy)
            elif self.active_handle == self.HANDLE_TOP_0:
                self.t0 = doc_pos
            elif self.active_handle == self.HANDLE_TOP_1:
                self.t1 = doc_pos
            elif self.active_handle == self.HANDLE_TOP_2:
                self.t2 = doc_pos
            elif self.active_handle == self.HANDLE_TOP_3:
                self.t3 = doc_pos

            self._update_top_corners_from_height()
            self._recalculate()
            event.accept()
            return

        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self.active_handle is not None:
            self.active_handle = None
            if hasattr(self, 'pb0') and self.pb0 is not None:
                self.b0 = QPointF(self.pb0)
                self.b1 = QPointF(self.pb1)
                self.b2 = QPointF(self.pb2)
                self.b3 = QPointF(self.pb3)
                self.t0 = QPointF(self.pt0)
                self.t1 = QPointF(self.pt1)
                self.t2 = QPointF(self.pt2)
                self.t3 = QPointF(self.pt3)
                self.height_offset = max(10.0, abs(self.b0.y() - self.t0.y()))
            self.update()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    # -------------------------------------------------------------------------
    # Paint Canvas, Vanishing Lines & Real-Time 3D Mesh
    # -------------------------------------------------------------------------

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)

        w = self.width()
        h = self.height()

        # 1. Background Image or Blueprint Grid
        if self.bg_image and not self.bg_image.isNull():
            scaled = self.bg_image.size().scaled(w, h, Qt.KeepAspectRatio)
            bx = (w - scaled.width()) // 2
            by = (h - scaled.height()) // 2
            self.img_rect = QRectF(bx, by, scaled.width(), scaled.height())
            painter.fillRect(0, 0, w, h, QColor(15, 17, 23))
            painter.drawImage(self.img_rect, self.bg_image)
        else:
            self.img_rect = QRectF(0, 0, w, h)
            painter.fillRect(0, 0, w, h, QColor(15, 23, 42))
            painter.setPen(QPen(QColor(30, 41, 59), 1))
            step = 30
            for x in range(0, w, step): painter.drawLine(x, 0, x, h)
            for y in range(0, h, step): painter.drawLine(0, y, w, y)

        wb0 = self._doc_to_widget(self.pb0 if self.pb0 is not None else self.b0)
        wb1 = self._doc_to_widget(self.pb1 if self.pb1 is not None else self.b1)
        wb2 = self._doc_to_widget(self.pb2 if self.pb2 is not None else self.b2)
        wb3 = self._doc_to_widget(self.pb3 if self.pb3 is not None else self.b3)
        wt0 = self._doc_to_widget(self.pt0 if self.pt0 is not None else self.t0)
        wt1 = self._doc_to_widget(self.pt1 if self.pt1 is not None else self.t1)
        wt2 = self._doc_to_widget(self.pt2 if self.pt2 is not None else self.t2)
        wt3 = self._doc_to_widget(self.pt3 if self.pt3 is not None else self.t3)

        sol = self.last_solution

        # When 4-click draw mode is active: the previous box, crating lines, rays,
        # and handles disappear completely so the artist has a clear view of their canvas.
        if not self.click_draw_mode:
            # 2. Horizon Line (Eye Level)
            vp_x_doc = sol.get("vp_x")
            vp_z_doc = sol.get("vp_z")
            if vp_x_doc and vp_z_doc:
                vpx_w = self._doc_to_widget(vp_x_doc)
                vpz_w = self._doc_to_widget(vp_z_doc)
                dx = vpz_w.x() - vpx_w.x()
                dy = vpz_w.y() - vpx_w.y()
                if abs(dx) > 1e-3 or abs(dy) > 1e-3:
                    scale = max(w, h) * 4.0
                    hp1 = QPointF(vpx_w.x() - dx * scale, vpx_w.y() - dy * scale)
                    hp2 = QPointF(vpz_w.x() + dx * scale, vpz_w.y() + dy * scale)
                    painter.setPen(QPen(QColor(234, 179, 8, 190), 1.5, Qt.DashLine))
                    painter.drawLine(hp1, hp2)

                    painter.setPen(QColor(250, 204, 21))
                    painter.setFont(QFont("Segoe UI", 8, QFont.Bold))
                    mid_y = int(max(16, min(h - 12, (vpx_w.y() + vpz_w.y()) * 0.5)))
                    painter.drawText(int(self.img_rect.x() + 8), mid_y, "── Horizon Line (Eye Level) ──")
            elif vp_z_doc:
                # 1-Point Perspective horizontal horizon line
                vpz_w = self._doc_to_widget(vp_z_doc)
                hy = vpz_w.y()
                painter.setPen(QPen(QColor(234, 179, 8, 190), 1.5, Qt.DashLine))
                painter.drawLine(0, int(hy), w, int(hy))
                painter.setPen(QColor(250, 204, 21))
                painter.setFont(QFont("Segoe UI", 8, QFont.Bold))
                painter.drawText(int(self.img_rect.x() + 8), int(hy - 4), "── 1-Point Horizon Line ──")

            # 3. Vanishing Rays towards VP_X and VP_Z
            def draw_ray(p_start, vp_doc, color):
                if not vp_doc: return
                vp_w = self._doc_to_widget(vp_doc)
                painter.setPen(QPen(color, 1.0, Qt.DotLine))
                painter.drawLine(p_start, vp_w)

            # Rays to VP_X (Red/Pink dotted)
            vpx_col = QColor(244, 63, 94, 90)
            draw_ray(wb0, vp_x_doc, vpx_col)
            draw_ray(wt0, vp_x_doc, vpx_col)
            draw_ray(wb3, vp_x_doc, vpx_col)
            draw_ray(wt3, vp_x_doc, vpx_col)

            # Rays to VP_Z (Cyan dotted)
            vpz_col = QColor(56, 189, 248, 90)
            draw_ray(wb0, vp_z_doc, vpz_col)
            draw_ray(wt0, vp_z_doc, vpz_col)
            draw_ray(wb1, vp_z_doc, vpz_col)
            draw_ray(wt1, vp_z_doc, vpz_col)

            # 4. Real 3D Mesh Rendering with Box Opacity Control
            if self.cached_preview_mesh and sol:
                preview_cam = Camera3D()
                preview_cam.yaw = sol.get("yaw", 145.0)
                preview_cam.pitch = sol.get("pitch", 12.0)
                preview_cam.roll = sol.get("roll", 0.0)
                preview_cam.fov = sol.get("fov", 45.0)
                preview_cam.distance = sol.get("distance", 3.5)
                preview_cam.pan_x = sol.get("pan_x", 0.0)
                preview_cam.pan_y = sol.get("pan_y", 0.0)
                preview_cam.target_x = sol.get("target_x", 0.0)
                preview_cam.target_y = sol.get("target_y", 0.0)
                preview_cam.target_z = sol.get("target_z", 0.0)

                painter.save()
                painter.translate(self.img_rect.topLeft())
                if self.doc_w > 0 and self.doc_h > 0:
                    sx = self.img_rect.width() / float(self.doc_w)
                    sy = self.img_rect.height() / float(self.doc_h)
                    painter.scale(sx, sy)

                # Set transparency of the 3D box preview
                painter.setOpacity(max(0.0, min(1.0, float(getattr(self, "box_opacity", 0.80)))))

                # Render shaded + wireframe 3D primitive directly on canvas
                self.renderer.render_scene(
                    painter=painter,
                    mesh=self.cached_preview_mesh,
                    camera=preview_cam,
                    lighting=self.lighting,
                    style=RenderStyle.SHADED_WIREFRAME,
                    width=int(self.doc_w),
                    height=int(self.doc_h)
                )
                painter.restore()

            # 5. Outer Guide Wireframe Lines (Bounding Crating Box)
            guide_alpha = int(max(60, min(220, getattr(self, "box_opacity", 0.80) * 255)))

            # Base Edges: Emerald Green
            painter.setPen(QPen(QColor(34, 197, 94, guide_alpha), 2.0))
            painter.drawLine(wb0, wb1)
            painter.drawLine(wb1, wb2)
            painter.drawLine(wb2, wb3)
            painter.drawLine(wb3, wb0)

            # Vertical Pillars: Amber Gold
            painter.setPen(QPen(QColor(245, 158, 11, guide_alpha), 2.0))
            painter.drawLine(wb0, wt0)
            painter.drawLine(wb1, wt1)
            painter.drawLine(wb2, wt2)
            painter.drawLine(wb3, wt3)

            # Top Edges: Sky Blue
            painter.setPen(QPen(QColor(56, 189, 248, guide_alpha), 2.0))
            painter.drawLine(wt0, wt1)
            painter.drawLine(wt1, wt2)
            painter.drawLine(wt2, wt3)
            painter.drawLine(wt3, wt0)

            # 6. Interactive Guide Pins / Handles
            handles = self._get_handles_widget()
            for hid, hpos, lbl, col in handles:
                is_active = (self.active_handle == hid)
                r = self.HANDLE_RADIUS + (2 if is_active else 0)

                # Outer glow
                painter.setPen(Qt.NoPen)
                painter.setBrush(QBrush(QColor(col.red(), col.green(), col.blue(), 75)))
                painter.drawEllipse(hpos, r + 4, r + 4)

                # Inner circle
                painter.setBrush(QBrush(col))
                painter.setPen(QPen(QColor(255, 255, 255), 1.5))
                painter.drawEllipse(hpos, r, r)

                # Handle label
                painter.setFont(QFont("Segoe UI", 7, QFont.Bold))
                painter.setPen(QColor(0, 0, 0) if col.lightness() > 150 else QColor(255, 255, 255))
                painter.drawText(
                    QRectF(hpos.x() - r, hpos.y() - r, r * 2, r * 2),
                    Qt.AlignCenter, lbl
                )
        else:
            # 7. Click-to-Draw Dynamic Guides (Box is hidden so canvas is completely clear)
            steps_desc = [
                "Click 1 of 4: Place Base Front-Left Corner (1)",
                "Click 2 of 4: Place Base Front-Right Corner (2)",
                "Click 3 of 4: Place Base Back-Right Corner (3)",
                "Click 4 of 4: Set Box Height in Perspective (▲)"
            ]
            msg = steps_desc[min(len(steps_desc) - 1, self.click_draw_step)]

            # Draw step instruction banner
            bw = 480
            bh = 34
            bx = int(self.img_rect.x() + (self.img_rect.width() - bw) * 0.5)
            by = int(self.img_rect.y() + 16)
            painter.setPen(QPen(QColor(56, 189, 248, 180), 1.5))
            painter.setBrush(QBrush(QColor(15, 23, 42, 220)))
            painter.drawRoundedRect(bx, by, bw, bh, 6, 6)

            painter.setPen(QColor(241, 245, 249))
            painter.setFont(QFont("Segoe UI", 10, QFont.Bold))
            painter.drawText(QRectF(bx, by, bw, bh), Qt.AlignCenter, f"✏️ {msg}")

            # Draw clicked points and rubber-bands
            n_pts = len(self.click_points)
            w_pts = [self._doc_to_widget(p) for p in self.click_points]
            h_pos_w = self._doc_to_widget(self.hover_doc_pos) if self.hover_doc_pos else None

            # Point badges
            colors = [QColor(34, 197, 94), QColor(34, 197, 94), QColor(34, 197, 94), QColor(56, 189, 248)]
            labels = ["1", "2", "3", "▲"]
            for i, wpt in enumerate(w_pts):
                col = colors[min(i, len(colors) - 1)]
                painter.setPen(Qt.NoPen)
                painter.setBrush(QBrush(QColor(col.red(), col.green(), col.blue(), 80)))
                painter.drawEllipse(wpt, 14, 14)
                painter.setBrush(QBrush(col))
                painter.setPen(QPen(QColor(255, 255, 255), 2.0))
                painter.drawEllipse(wpt, 9, 9)
                painter.setPen(QColor(0, 0, 0))
                painter.setFont(QFont("Segoe UI", 8, QFont.Bold))
                painter.drawText(QRectF(wpt.x() - 9, wpt.y() - 9, 18, 18), Qt.AlignCenter, labels[i])

            if n_pts == 1 and h_pos_w:
                painter.setPen(QPen(QColor(250, 204, 21), 2.0, Qt.DashLine))
                painter.drawLine(w_pts[0], h_pos_w)
            elif n_pts == 2:
                painter.setPen(QPen(QColor(34, 197, 94), 2.5))
                painter.drawLine(w_pts[0], w_pts[1])
                if h_pos_w:
                    painter.setPen(QPen(QColor(250, 204, 21), 2.0, Qt.DashLine))
                    painter.drawLine(w_pts[1], h_pos_w)
            elif n_pts == 3:
                p0_d = self.click_points[0]
                p1_d = self.click_points[1]
                p2_d = self.click_points[2]
                p3_d = QPointF(p0_d.x() + (p2_d.x() - p1_d.x()), p0_d.y() + (p2_d.y() - p1_d.y()))
                p3_w = self._doc_to_widget(p3_d)

                base_poly = QPolygonF([w_pts[0], w_pts[1], w_pts[2], p3_w])
                painter.setPen(QPen(QColor(34, 197, 94, 220), 2.5))
                painter.setBrush(QBrush(QColor(34, 197, 94, 50)))
                painter.drawPolygon(base_poly)

                painter.setPen(QPen(QColor(255, 255, 255, 180), 1.5, Qt.DashLine))
                painter.setBrush(QBrush(QColor(34, 197, 94, 160)))
                painter.drawEllipse(p3_w, 8, 8)
                painter.setPen(QColor(255, 255, 255))
                painter.setFont(QFont("Segoe UI", 7, QFont.Bold))
                painter.drawText(QRectF(p3_w.x() - 8, p3_w.y() - 8, 16, 16), Qt.AlignCenter, "4")

                if h_pos_w:
                    h_target = QPointF(w_pts[0].x(), h_pos_w.y())
                    painter.setPen(QPen(QColor(56, 189, 248), 2.5, Qt.DashLine))
                    painter.drawLine(w_pts[0], h_target)
                    painter.setBrush(QBrush(QColor(56, 189, 248)))
                    painter.setPen(QPen(QColor(255, 255, 255), 1.5))
                    painter.drawEllipse(h_target, 7, 7)


# -----------------------------------------------------------------------------
# Primitive Drawer & Calibrator Dialog
# -----------------------------------------------------------------------------

class PrimitiveDrawerDialog(QDialog):
    """
    Unified dialog proxy: forwards to GroundCalibratorDialog so Draw Primitive
    and Ground Calibrator share one unified, merged interface.
    """
    applied = pyqtSignal(dict)

    def __new__(cls, bg_image=None, camera=None, lighting=None, renderer=None, start_in_click_draw=False, parent=None, **kwargs):
        from .ground_calibrator import GroundCalibratorDialog
        return GroundCalibratorDialog(
            bg_image=bg_image,
            mesh=kwargs.get("mesh"),
            camera=camera,
            lighting=lighting,
            renderer=renderer,
            frame_rect=kwargs.get("frame_rect"),
            start_in_click_draw=start_in_click_draw,
            initial_mode=kwargs.get("initial_mode"),
            parent=parent
        )

    def _build_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(8)

        # 1. Header Toolbar
        hdr_box = QFrame()
        hdr_box.setStyleSheet("background: #1e293b; border-radius: 6px; padding: 6px;")
        hdr_layout = QVBoxLayout(hdr_box)
        hdr_layout.setContentsMargins(8, 6, 8, 6)
        hdr_layout.setSpacing(6)

        # Row 1: Primitive type, 4-Click Draw, Opacity Slider, History dropdown
        r1_layout = QHBoxLayout()
        r1_layout.setSpacing(10)

        r1_layout.addWidget(QLabel("Primitive:"))
        self.combo_prim = QComboBox()
        self.combo_prim.addItems(["📦 Box", "🛢️ Cylinder", "🔮 Sphere", "📐 Pyramid", "🍦 Cone", "🏁 Plane"])
        self.combo_prim.setStyleSheet(
            "QComboBox { background: #334155; color: #38bdf8; font-weight: bold; padding: 3px 8px; border-radius: 4px; }"
        )
        self.combo_prim.currentIndexChanged.connect(self._on_primitive_type_changed)
        r1_layout.addWidget(self.combo_prim)

        # 4-Click Draw button
        self.btn_click_draw = QPushButton("✏️ 4-Click Draw")
        self.btn_click_draw.setToolTip("Click 4 points on canvas to quickly trace a box (FL, FR, BR, Height). Hides box during click placement.")
        self.btn_click_draw.setStyleSheet(
            "QPushButton { background: #0284c7; color: #fff; font-weight: bold; padding: 4px 10px; border-radius: 4px; }"
            "QPushButton:hover { background: #0369a1; }"
        )
        self.btn_click_draw.clicked.connect(self._start_click_draw)
        r1_layout.addWidget(self.btn_click_draw)

        # Box Transparency / Opacity Slider
        r1_layout.addWidget(QLabel("Box Opacity:"))
        self.sl_opacity = QSlider(Qt.Horizontal)
        self.sl_opacity.setRange(0, 100)
        self.sl_opacity.setValue(int(self.drawer_widget.box_opacity * 100))
        self.sl_opacity.setFixedWidth(80)
        self.sl_opacity.setToolTip("Control transparency of the 3D box preview")
        self.sl_opacity.valueChanged.connect(self._on_opacity_changed)
        r1_layout.addWidget(self.sl_opacity)

        self.lbl_opacity = QLabel(f"{int(self.drawer_widget.box_opacity * 100)}%")
        self.lbl_opacity.setStyleSheet("color: #38bdf8; font-weight: bold; min-width: 32px;")
        r1_layout.addWidget(self.lbl_opacity)

        r1_layout.addSpacing(10)

        # History Dropdown
        r1_layout.addWidget(QLabel("History:"))
        self.combo_history = QComboBox()
        self.combo_history.setMinimumWidth(260)
        self.combo_history.setStyleSheet(
            "QComboBox { background: #334155; color: #f1f5f9; padding: 3px 8px; border-radius: 4px; font-size: 11px; }"
        )
        self._populate_history_combo()
        self.combo_history.currentIndexChanged.connect(self._on_history_selected)
        r1_layout.addWidget(self.combo_history)

        self.btn_clear_history = QPushButton("🗑️")
        self.btn_clear_history.setToolTip("Clear primitive history")
        self.btn_clear_history.setStyleSheet(
            "QPushButton { background: #334155; color: #f87171; padding: 3px 8px; border-radius: 4px; font-size: 11px; }"
            "QPushButton:hover { background: #475569; color: #ef4444; }"
        )
        self.btn_clear_history.clicked.connect(self._on_clear_history)
        r1_layout.addWidget(self.btn_clear_history)

        r1_layout.addStretch(1)
        hdr_layout.addLayout(r1_layout)

        # Row 2: Quick Perspective Presets & Alignment Checkboxes
        r2_layout = QHBoxLayout()
        r2_layout.setSpacing(10)

        r2_layout.addWidget(QLabel("Presets:"))
        for name, key, tip in [
            ("2-Point Eye", "2pt_eye", "Standard 2-point perspective at eye level"),
            ("Bird's Eye (Down)", "birds_eye", "High-angle view looking down at the box"),
            ("Worm's Eye (Up)", "worms_eye", "Low-angle view looking up at the box"),
            ("1-Point Front", "1pt_front", "Frontal 1-point perspective"),
        ]:
            btn = QPushButton(name)
            btn.setToolTip(tip)
            btn.setStyleSheet(
                "QPushButton { background: #334155; color: #e2e8f0; font-size: 10px; padding: 3px 6px; border-radius: 3px; }"
                "QPushButton:hover { background: #475569; color: #fff; }"
            )
            btn.clicked.connect(lambda _, k=key: self._on_preset_clicked(k))
            r2_layout.addWidget(btn)

        r2_layout.addSpacing(15)

        # Options Checkboxes
        self.chk_auto_fov = QCheckBox("Auto-Estimate FOV")
        self.chk_auto_fov.setChecked(True)
        self.chk_auto_fov.setToolTip("Automatically compute Field of View from orthogonal vanishing points")
        self.chk_auto_fov.stateChanged.connect(self._on_options_changed)
        r2_layout.addWidget(self.chk_auto_fov)

        self.chk_level_horizon = QCheckBox("Level Horizon (0° Roll)")
        self.chk_level_horizon.setChecked(True)
        self.chk_level_horizon.setToolTip("Keep camera upright without sideways tilt")
        self.chk_level_horizon.stateChanged.connect(self._on_options_changed)
        r2_layout.addWidget(self.chk_level_horizon)

        self.chk_unlock_top = QCheckBox("Unlock Top Pins")
        self.chk_unlock_top.setChecked(False)
        self.chk_unlock_top.setToolTip("Enable independent dragging of top pins for custom 3-point tilt shapes")
        self.chk_unlock_top.stateChanged.connect(self._on_unlock_top_changed)
        r2_layout.addWidget(self.chk_unlock_top)

        r2_layout.addStretch(1)
        hdr_layout.addLayout(r2_layout)

        main_layout.addWidget(hdr_box)

        # 2. Central Interactive Drawer Canvas
        main_layout.addWidget(self.drawer_widget, 1)

        # 3. HUD Information Banner
        self.hud_frame = QFrame()
        self.hud_frame.setStyleSheet(
            "background: #111827; border: 1px solid #1f2937; border-radius: 6px; padding: 6px 12px;"
        )
        hud_l = QHBoxLayout(self.hud_frame)
        hud_l.setContentsMargins(4, 2, 4, 2)
        hud_l.setSpacing(16)

        self.lbl_hud_persp = QLabel("Perspective: 2-Point")
        self.lbl_hud_persp.setStyleSheet("color: #38bdf8; font-weight: bold; font-size: 11px;")
        hud_l.addWidget(self.lbl_hud_persp)

        self.lbl_hud_fov = QLabel("FOV: 45.0° (43mm)")
        self.lbl_hud_fov.setStyleSheet("color: #4ade80; font-weight: bold; font-size: 11px;")
        hud_l.addWidget(self.lbl_hud_fov)

        self.lbl_hud_angles = QLabel("Tilt: 15.0° | Yaw: 35.0° | Roll: 0.0°")
        self.lbl_hud_angles.setStyleSheet("color: #facc15; font-size: 11px;")
        hud_l.addWidget(self.lbl_hud_angles)

        self.lbl_hud_ratio = QLabel("Box Ratio: 1.00 : 1.20 : 0.85")
        self.lbl_hud_ratio.setStyleSheet("color: #c084fc; font-size: 11px;")
        hud_l.addWidget(self.lbl_hud_ratio)

        hud_l.addStretch(1)
        main_layout.addWidget(self.hud_frame)

        # 4. Action Buttons Footer
        foot_l = QHBoxLayout()
        foot_l.setSpacing(10)

        hint = QLabel("💡 Drag ground pins (1, 2, 3, 4) to trace base. Drag (▲ H) to adjust height. Drag (✛) to move entire box.")
        hint.setStyleSheet("color: #94a3b8; font-size: 10px;")
        foot_l.addWidget(hint, 1)

        b_cancel = QPushButton("Cancel")
        b_cancel.setStyleSheet(
            "QPushButton { background: #334155; color: #f1f5f9; padding: 6px 14px; border-radius: 4px; }"
            "QPushButton:hover { background: #475569; }"
        )
        b_cancel.clicked.connect(self.reject)
        foot_l.addWidget(b_cancel)

        self.b_apply = QPushButton("✅ Create 3D Primitive & Calibrate Scene")
        self.b_apply.setStyleSheet(
            "QPushButton { background: #059669; color: #fff; font-weight: bold; padding: 6px 18px; border-radius: 4px; }"
            "QPushButton:hover { background: #10b981; }"
        )
        self.b_apply.clicked.connect(self._apply_and_close)
        foot_l.addWidget(self.b_apply)

        main_layout.addLayout(foot_l)

    def _populate_history_combo(self):
        self.combo_history.blockSignals(True)
        self.combo_history.clear()
        if not self.history_items:
            self.combo_history.addItem("(No previous boxes)")
            self.combo_history.setEnabled(False)
        else:
            self.combo_history.setEnabled(True)
            for i, item in enumerate(self.history_items):
                lbl = item.get("label", f"Primitive #{i+1}")
                if i == 0:
                    lbl = f"{lbl} (Last Used)"
                self.combo_history.addItem(lbl)
        self.combo_history.blockSignals(False)

    def _on_history_selected(self, index):
        if index < 0 or index >= len(self.history_items):
            return
        entry = self.history_items[index]
        self.drawer_widget.restore_from_entry(entry)
        self._sync_ui_from_drawer()

    def _on_clear_history(self):
        clear_primitive_history()
        self.history_items = []
        self._populate_history_combo()

    def _on_opacity_changed(self, v):
        self.drawer_widget.box_opacity = v / 100.0
        self.lbl_opacity.setText(f"{v}%")
        self.drawer_widget.update()

    def _on_preset_clicked(self, key):
        self.drawer_widget.apply_preset(key)
        self._sync_ui_from_drawer()

    def _sync_ui_from_drawer(self):
        w = self.drawer_widget
        ptype = w.primitive_type
        for i in range(self.combo_prim.count()):
            if ptype in self.combo_prim.itemText(i):
                self.combo_prim.blockSignals(True)
                self.combo_prim.setCurrentIndex(i)
                self.combo_prim.blockSignals(False)
                break

        self.chk_auto_fov.blockSignals(True)
        self.chk_auto_fov.setChecked(w.auto_fov)
        self.chk_auto_fov.blockSignals(False)

        self.chk_level_horizon.blockSignals(True)
        self.chk_level_horizon.setChecked(w.keep_horizon)
        self.chk_level_horizon.blockSignals(False)

        self.chk_unlock_top.blockSignals(True)
        self.chk_unlock_top.setChecked(w.unlock_top_corners)
        self.chk_unlock_top.blockSignals(False)

        self.sl_opacity.blockSignals(True)
        self.sl_opacity.setValue(int(w.box_opacity * 100))
        self.sl_opacity.blockSignals(False)
        self.lbl_opacity.setText(f"{int(w.box_opacity * 100)}%")

        self._update_hud(w.last_solution)

    def _on_options_changed(self):
        self.drawer_widget.auto_fov = self.chk_auto_fov.isChecked()
        self.drawer_widget.keep_horizon = self.chk_level_horizon.isChecked()
        self.drawer_widget._recalculate()

    def _on_unlock_top_changed(self):
        self.drawer_widget.unlock_top_corners = self.chk_unlock_top.isChecked()
        self.drawer_widget.update()

    def _save_dialog_geom(self):
        try:
            geo_hex = self.saveGeometry().toHex().data().decode('ascii')
            save_dialog_geometry(geo_hex)
        except Exception:
            pass

    def closeEvent(self, event):
        self._save_dialog_geom()
        super().closeEvent(event)

    def reject(self):
        self._save_dialog_geom()
        super().reject()

    def _on_primitive_type_changed(self, idx):
        types = ["Box", "Cylinder", "Sphere", "Pyramid", "Cone", "Plane"]
        if 0 <= idx < len(types):
            self.drawer_widget.primitive_type = types[idx]
            self.drawer_widget._recalculate()

    def _start_click_draw(self):
        if self.drawer_widget.click_draw_mode:
            self.drawer_widget.cancel_click_draw()
            self._on_click_draw_finished()
        else:
            self.drawer_widget.start_click_draw()
            self.btn_click_draw.setText("❌ Cancel 4-Click")
            self.btn_click_draw.setStyleSheet(
                "QPushButton { background: #dc2626; color: #fff; font-weight: bold; padding: 4px 10px; border-radius: 4px; }"
                "QPushButton:hover { background: #b91c1c; }"
            )

    def _on_click_draw_finished(self):
        self.btn_click_draw.setText("✏️ 4-Click Draw")
        self.btn_click_draw.setStyleSheet(
            "QPushButton { background: #0284c7; color: #fff; font-weight: bold; padding: 4px 10px; border-radius: 4px; }"
            "QPushButton:hover { background: #0369a1; }"
        )
        self._update_hud(self.drawer_widget.last_solution)

    def _on_solution_changed(self, sol):
        self._update_hud(sol)

    def _update_hud(self, sol):
        if not sol: return
        persp = sol.get("persp_type", "2-Point")
        fov = sol.get("fov", 45.0)
        mm = sol.get("focal_mm", 43)
        pitch = sol.get("pitch", 0.0)
        yaw = sol.get("yaw", 0.0)
        roll = sol.get("roll", 0.0)
        bw = sol.get("box_w", 2.0)
        bh = sol.get("box_h", 2.0)
        bd = sol.get("box_d", 2.0)

        self.lbl_hud_persp.setText(f"Perspective: {persp} Perspective")
        self.lbl_hud_fov.setText(f"FOV: {fov:.1f}° ({mm}mm Lens)")
        self.lbl_hud_angles.setText(f"Camera Tilt: {pitch:+.1f}° | Rotation: {yaw:.1f}° | Roll: {roll:+.1f}°")
        self.lbl_hud_ratio.setText(f"Box Proportions (W:H:D): {bw:.2f} : {bh:.2f} : {bd:.2f}")

    def _apply_and_close(self):
        self._save_dialog_geom()
        w = self.drawer_widget
        now_dt = datetime.datetime.now()
        ts_str = now_dt.strftime("%Y-%m-%d %H:%M:%S")
        time_str = now_dt.strftime("%H:%M:%S")
        ptype = w.primitive_type
        persp = w.last_solution.get("persp_type", "2-Point")
        icon = {"Box": "📦", "Cylinder": "🛢️", "Sphere": "🔮", "Pyramid": "📐", "Cone": "🍦", "Plane": "🏁"}.get(ptype, "📦")
        label = f"{icon} {ptype} ({persp}) — {ts_str}"

        corners = {
            "b0": [w.b0.x(), w.b0.y()] if w.b0 else [0, 0],
            "b1": [w.b1.x(), w.b1.y()] if w.b1 else [0, 0],
            "b2": [w.b2.x(), w.b2.y()] if w.b2 else [0, 0],
            "b3": [w.b3.x(), w.b3.y()] if w.b3 else [0, 0],
            "t0": [w.t0.x(), w.t0.y()] if w.t0 else [0, 0],
            "t1": [w.t1.x(), w.t1.y()] if w.t1 else [0, 0],
            "t2": [w.t2.x(), w.t2.y()] if w.t2 else [0, 0],
            "t3": [w.t3.x(), w.t3.y()] if w.t3 else [0, 0],
        }
        entry = {
            "id": now_dt.strftime("%Y%m%d%H%M%S"),
            "timestamp": ts_str,
            "time_short": time_str,
            "label": label,
            "primitive_type": ptype,
            "persp_type": persp,
            "corners": corners,
            "height_offset": float(w.height_offset),
            "doc_size": [w.doc_w, w.doc_h],
            "auto_fov": bool(w.auto_fov),
            "keep_horizon": bool(w.keep_horizon),
            "unlock_top": bool(w.unlock_top_corners),
            "box_opacity": float(w.box_opacity),
            "solution": {
                "fov": float(w.last_solution.get("fov", 45.0)),
                "pitch": float(w.last_solution.get("pitch", 0.0)),
                "yaw": float(w.last_solution.get("yaw", 0.0)),
                "roll": float(w.last_solution.get("roll", 0.0)),
                "distance": float(w.last_solution.get("distance", 3.5)),
                "pan_x": float(w.last_solution.get("pan_x", 0.0)),
                "pan_y": float(w.last_solution.get("pan_y", 0.0)),
                "target_x": float(w.last_solution.get("target_x", 0.0)),
                "target_y": float(w.last_solution.get("target_y", 0.0)),
                "target_z": float(w.last_solution.get("target_z", 0.0)),
                "box_w": float(w.last_solution.get("box_w", 2.0)),
                "box_h": float(w.last_solution.get("box_h", 2.0)),
                "box_d": float(w.last_solution.get("box_d", 2.0)),
            }
        }
        add_primitive_to_history(entry)

        sol = dict(w.last_solution)
        sol["mesh"] = w.cached_preview_mesh
        sol["primitive_type"] = w.primitive_type
        self.applied.emit(sol)
        self.accept()
