"""
mesh_loader.py - High performance 3D mesh parser for OBJ and STL formats.
Zero external dependencies, utilizes PyQt5.QtGui.QVector3D.
"""

import os
import math
import struct
from PyQt5.QtGui import QVector3D


class MeshData:
    def __init__(self, name=""):
        self.name = name
        self.vertices = []          # List of normalized QVector3D
        self.original_vertices = [] # Raw (x, y, z)
        self.faces = []             # List of (v0, v1, v2)
        self.face_normals = []      # List of QVector3D
        self.vertex_normals = []    # Optional per-vertex normals
        self.center = QVector3D(0, 0, 0)
        self.bbox_min = QVector3D(0, 0, 0)
        self.bbox_max = QVector3D(0, 0, 0)
        self.radius = 1.0
        self.scale = 1.0

    @property
    def vertex_count(self):
        return len(self.vertices)

    @property
    def face_count(self):
        return len(self.faces)

    def compute_bounds_and_normalize(self):
        if not self.vertices:
            return

        min_x = min(v.x() for v in self.vertices)
        max_x = max(v.x() for v in self.vertices)
        min_y = min(v.y() for v in self.vertices)
        max_y = max(v.y() for v in self.vertices)
        min_z = min(v.z() for v in self.vertices)
        max_z = max(v.z() for v in self.vertices)

        self.bbox_min = QVector3D(min_x, min_y, min_z)
        self.bbox_max = QVector3D(max_x, max_y, max_z)
        self.center = QVector3D(
            (min_x + max_x) * 0.5,
            (min_y + max_y) * 0.5,
            (min_z + max_z) * 0.5
        )

        cx, cy, cz = self.center.x(), self.center.y(), self.center.z()
        max_dist_sq = 0.0
        for v in self.vertices:
            dx = v.x() - cx
            dy = v.y() - cy
            dz = v.z() - cz
            d2 = dx*dx + dy*dy + dz*dz
            if d2 > max_dist_sq:
                max_dist_sq = d2

        self.radius = math.sqrt(max_dist_sq) if max_dist_sq > 0 else 1.0
        # Normalize into unit sphere (radius = 1.0)
        norm_factor = 1.0 / self.radius if self.radius > 0 else 1.0
        self.scale = norm_factor
        self.vertices = [
            QVector3D((v.x() - cx) * norm_factor,
                      (v.y() - cy) * norm_factor,
                      (v.z() - cz) * norm_factor)
            for v in self.vertices
        ]

    def compute_face_normals(self):
        self.face_normals = []
        for f in self.faces:
            v0 = self.vertices[f[0]]
            v1 = self.vertices[f[1]]
            v2 = self.vertices[f[2]]
            e1 = v1 - v0
            e2 = v2 - v0
            norm = QVector3D.crossProduct(e1, e2)
            length = norm.length()
            if length > 1e-6:
                self.face_normals.append(norm * (1.0 / length))
            else:
                self.face_normals.append(QVector3D(0, 1, 0))


def load_obj(filepath):
    """
    Parse a Wavefront OBJ file.
    Handles vertices (v), vertex normals (vn), and polygonal faces (f) with triangulation.
    """
    if not os.path.exists(filepath):
        raise FileNotFoundError(f"OBJ file not found: {filepath}")

    mesh = MeshData(name=os.path.splitext(os.path.basename(filepath))[0])
    raw_verts = []
    raw_normals = []
    faces = []

    with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
        for line in f:
            if not line or line.startswith('#'):
                continue
            
            parts = line.split()
            if not parts:
                continue

            tag = parts[0]
            if tag == 'v':
                if len(parts) >= 4:
                    raw_verts.append(QVector3D(float(parts[1]), float(parts[2]), float(parts[3])))
            elif tag == 'vn':
                if len(parts) >= 4:
                    raw_normals.append(QVector3D(float(parts[1]), float(parts[2]), float(parts[3])))
            elif tag == 'f':
                # Face elements can be v, v/vt, v//vn, v/vt/vn
                poly_verts = []
                num_v = len(raw_verts)
                for item in parts[1:]:
                    sub = item.split('/')
                    idx = int(sub[0])
                    # Handle 1-based and relative negative indexing
                    v_idx = idx - 1 if idx > 0 else num_v + idx
                    poly_verts.append(v_idx)
                
                # Triangulate face using triangle fan
                if len(poly_verts) == 3:
                    faces.append(tuple(poly_verts))
                elif len(poly_verts) > 3:
                    for i in range(1, len(poly_verts) - 1):
                        faces.append((poly_verts[0], poly_verts[i], poly_verts[i+1]))

    mesh.vertices = raw_verts
    mesh.faces = faces
    mesh.compute_bounds_and_normalize()
    mesh.compute_face_normals()
    return mesh


def load_stl(filepath):
    """
    Parse an STL file (ASCII or Binary).
    """
    if not os.path.exists(filepath):
        raise FileNotFoundError(f"STL file not found: {filepath}")

    mesh = MeshData(name=os.path.splitext(os.path.basename(filepath))[0])
    
    # Check if binary or ASCII
    file_size = os.path.getsize(filepath)
    is_binary = False
    with open(filepath, 'rb') as f:
        header = f.read(80)
        if len(header) == 80 and file_size > 84:
            count_bytes = f.read(4)
            num_triangles = struct.unpack('<I', count_bytes)[0]
            expected_size = 84 + num_triangles * 50
            if file_size == expected_size:
                is_binary = True

    if is_binary:
        return _load_stl_binary(filepath, mesh)
    else:
        return _load_stl_ascii(filepath, mesh)


def _load_stl_binary(filepath, mesh):
    raw_verts = []
    faces = []
    normals = []
    vert_map = {}

    with open(filepath, 'rb') as f:
        f.seek(80)
        num_triangles = struct.unpack('<I', f.read(4))[0]
        for _ in range(num_triangles):
            data = f.read(50)
            if len(data) < 50:
                break
            floats = struct.unpack('<12fH', data)
            nx, ny, nz = floats[0], floats[1], floats[2]
            normals.append(QVector3D(nx, ny, nz))
            
            tri_indices = []
            for i in range(3):
                vx = floats[3 + i*3]
                vy = floats[4 + i*3]
                vz = floats[5 + i*3]
                # Simple vertex deduplication using rounded tuple
                key = (round(vx, 4), round(vy, 4), round(vz, 4))
                if key in vert_map:
                    tri_indices.append(vert_map[key])
                else:
                    new_idx = len(raw_verts)
                    vert_map[key] = new_idx
                    raw_verts.append(QVector3D(vx, vy, vz))
                    tri_indices.append(new_idx)
            faces.append(tuple(tri_indices))

    mesh.vertices = raw_verts
    mesh.faces = faces
    mesh.compute_bounds_and_normalize()
    mesh.compute_face_normals()
    return mesh


def _load_stl_ascii(filepath, mesh):
    raw_verts = []
    faces = []
    vert_map = {}
    current_tri = []

    with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
        for line in f:
            parts = line.strip().split()
            if not parts:
                continue
            if parts[0] == 'vertex' and len(parts) >= 4:
                vx, vy, vz = float(parts[1]), float(parts[2]), float(parts[3])
                key = (round(vx, 4), round(vy, 4), round(vz, 4))
                if key in vert_map:
                    current_tri.append(vert_map[key])
                else:
                    new_idx = len(raw_verts)
                    vert_map[key] = new_idx
                    raw_verts.append(QVector3D(vx, vy, vz))
                    current_tri.append(new_idx)
                
                if len(current_tri) == 3:
                    faces.append(tuple(current_tri))
                    current_tri = []

    mesh.vertices = raw_verts
    mesh.faces = faces
    mesh.compute_bounds_and_normalize()
    mesh.compute_face_normals()
    return mesh


def load_3d_file(filepath):
    """
    Main loader entrypoint supporting OBJ and STL files.
    """
    ext = os.path.splitext(filepath)[1].lower()
    if ext == '.obj':
        return load_obj(filepath)
    elif ext == '.stl':
        return load_stl(filepath)
    else:
        raise ValueError(f"Unsupported 3D file format: {ext}. Supported formats are: .obj, .stl")
