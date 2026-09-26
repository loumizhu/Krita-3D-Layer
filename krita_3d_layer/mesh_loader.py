"""
mesh_loader.py - High performance 3D mesh parser for OBJ and STL formats.
Zero external dependencies, utilizes PyQt5.QtGui.QVector3D.
"""

import os
import math
import struct
import json
import base64
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
        self.polygon_edges = None   # Optional set of (min_idx, max_idx) original polygon perimeter edges
        self.coplanar_edges = set() # Set of (min_idx, max_idx) internal triangulation diagonals / coplanar edges

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

        # Recompute bounding box and center in normalized coordinates
        min_x = min(v.x() for v in self.vertices)
        max_x = max(v.x() for v in self.vertices)
        min_y = min(v.y() for v in self.vertices)
        max_y = max(v.y() for v in self.vertices)
        min_z = min(v.z() for v in self.vertices)
        max_z = max(v.z() for v in self.vertices)
        self.bbox_min = QVector3D(min_x, min_y, min_z)
        self.bbox_max = QVector3D(max_x, max_y, max_z)
        self.center = QVector3D((min_x + max_x) * 0.5, (min_y + max_y) * 0.5, (min_z + max_z) * 0.5)

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

    def compute_coplanar_edges(self, threshold_degrees=1.5):
        """
        Identify internal triangulation diagonals / coplanar edges.
        If polygon_edges is defined (e.g. from OBJ quads/polygons), any edge
        not in polygon_edges is an internal diagonal.
        Otherwise (e.g. STL, GLB, triangulated OBJ), edges shared by two adjacent
        faces whose dihedral angle is <= threshold_degrees are marked as coplanar diagonals.
        """
        self.coplanar_edges = set()
        edge_to_faces = {}
        for fi, face in enumerate(self.faces):
            v0, v1, v2 = face[0], face[1], face[2]
            for e in ((v0, v1) if v0 < v1 else (v1, v0),
                      (v1, v2) if v1 < v2 else (v2, v1),
                      (v2, v0) if v2 < v0 else (v0, v2)):
                if e not in edge_to_faces:
                    edge_to_faces[e] = [fi]
                else:
                    edge_to_faces[e].append(fi)

        self.edge_to_faces = edge_to_faces
        has_poly_edges = (self.polygon_edges is not None and len(self.polygon_edges) > 0)
        cos_thresh = math.cos(math.radians(threshold_degrees))

        for e, f_list in edge_to_faces.items():
            if has_poly_edges:
                if e not in self.polygon_edges:
                    self.coplanar_edges.add(e)
            elif len(f_list) == 2:
                n1 = self.face_normals[f_list[0]]
                n2 = self.face_normals[f_list[1]]
                dot = n1.x() * n2.x() + n1.y() * n2.y() + n1.z() * n2.z()
                if dot >= cos_thresh:
                    self.coplanar_edges.add(e)


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
    has_quads = False
    orig_edges = set()

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
                
                if len(poly_verts) >= 3:
                    if len(poly_verts) > 3:
                        has_quads = True
                    for k in range(len(poly_verts)):
                        u = poly_verts[k]
                        v = poly_verts[(k + 1) % len(poly_verts)]
                        orig_edges.add((u, v) if u < v else (v, u))

                # Triangulate face using triangle fan
                if len(poly_verts) == 3:
                    faces.append(tuple(poly_verts))
                elif len(poly_verts) > 3:
                    for i in range(1, len(poly_verts) - 1):
                        faces.append((poly_verts[0], poly_verts[i], poly_verts[i+1]))

    if has_quads:
        mesh.polygon_edges = orig_edges
    mesh.vertices = raw_verts
    mesh.faces = faces
    mesh.compute_bounds_and_normalize()
    mesh.compute_face_normals()
    mesh.compute_coplanar_edges()
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
    mesh.compute_coplanar_edges()
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
    mesh.compute_coplanar_edges()
    return mesh


GLTF_COMPONENT_TYPES = {
    5120: ('b', 1),  # BYTE
    5121: ('B', 1),  # UNSIGNED_BYTE
    5122: ('h', 2),  # SHORT
    5123: ('H', 2),  # UNSIGNED_SHORT
    5125: ('I', 4),  # UNSIGNED_INT
    5126: ('f', 4)   # FLOAT
}

GLTF_TYPE_COUNTS = {
    'SCALAR': 1,
    'VEC2': 2,
    'VEC3': 3,
    'VEC4': 4,
    'MAT4': 16
}


def _read_gltf_accessor(gltf, acc_idx, buffers_data):
    accessors = gltf.get('accessors', [])
    if acc_idx < 0 or acc_idx >= len(accessors):
        return []
    acc = accessors[acc_idx]
    if 'bufferView' not in acc:
        return []

    buffer_views = gltf.get('bufferViews', [])
    bv_idx = acc['bufferView']
    if bv_idx >= len(buffer_views):
        return []
    bv = buffer_views[bv_idx]

    buf_idx = bv.get('buffer', 0)
    if buf_idx >= len(buffers_data):
        return []
    buffer_bytes = buffers_data[buf_idx]

    comp_type, comp_size = GLTF_COMPONENT_TYPES.get(acc.get('componentType', 5126), ('f', 4))
    num_comps = GLTF_TYPE_COUNTS.get(acc.get('type', 'SCALAR'), 1)
    count = acc.get('count', 0)

    start = bv.get('byteOffset', 0) + acc.get('byteOffset', 0)
    stride = bv.get('byteStride', comp_size * num_comps)
    item_format = '<' + comp_type * num_comps
    item_size = comp_size * num_comps

    res = []
    for i in range(count):
        offset = start + i * stride
        if offset + item_size > len(buffer_bytes):
            break
        vals = struct.unpack_from(item_format, buffer_bytes, offset)
        if num_comps == 1:
            res.append(vals[0])
        elif num_comps == 3:
            res.append(QVector3D(float(vals[0]), float(vals[1]), float(vals[2])))
        else:
            res.append(vals)
    return res


def _parse_gltf_structure(gltf, buffers_data, name):
    mesh = MeshData(name=name)
    all_vertices = []
    all_faces = []

    for m in gltf.get('meshes', []):
        for prim in m.get('primitives', []):
            attrs = prim.get('attributes', {})
            if 'POSITION' not in attrs:
                continue

            pos_idx = attrs['POSITION']
            positions = _read_gltf_accessor(gltf, pos_idx, buffers_data)
            if not positions:
                continue

            base_idx = len(all_vertices)
            all_vertices.extend(positions)
            mode = prim.get('mode', 4)  # 4 = TRIANGLES

            if 'indices' in prim:
                indices = _read_gltf_accessor(gltf, prim['indices'], buffers_data)
                if mode == 4:  # TRIANGLES
                    for i in range(0, len(indices) - 2, 3):
                        all_faces.append((
                            base_idx + int(indices[i]),
                            base_idx + int(indices[i + 1]),
                            base_idx + int(indices[i + 2])
                        ))
                elif mode == 5:  # TRIANGLE_STRIP
                    for i in range(len(indices) - 2):
                        if i % 2 == 0:
                            all_faces.append((
                                base_idx + int(indices[i]),
                                base_idx + int(indices[i + 1]),
                                base_idx + int(indices[i + 2])
                            ))
                        else:
                            all_faces.append((
                                base_idx + int(indices[i + 1]),
                                base_idx + int(indices[i]),
                                base_idx + int(indices[i + 2])
                            ))
                elif mode == 6:  # TRIANGLE_FAN
                    for i in range(1, len(indices) - 1):
                        all_faces.append((
                            base_idx + int(indices[0]),
                            base_idx + int(indices[i]),
                            base_idx + int(indices[i + 1])
                        ))
            else:
                # Non-indexed
                if mode == 4:  # TRIANGLES
                    for i in range(0, len(positions) - 2, 3):
                        all_faces.append((base_idx + i, base_idx + i + 1, base_idx + i + 2))

    if not all_vertices or not all_faces:
        raise ValueError(f"No valid triangle geometry found in glTF / GLB: {name}")

    mesh.vertices = all_vertices
    mesh.faces = all_faces
    mesh.compute_bounds_and_normalize()
    mesh.compute_face_normals()
    mesh.compute_coplanar_edges()
    return mesh


def load_glb(filepath):
    """
    Parse a binary glTF 2.0 (.glb) file.
    Reads header, JSON chunk, binary buffer chunk, and extracts all mesh geometry.
    """
    if not os.path.exists(filepath):
        raise FileNotFoundError(f"GLB file not found: {filepath}")

    with open(filepath, 'rb') as f:
        header = f.read(12)
        if len(header) < 12:
            raise ValueError(f"Invalid GLB file: file too short ({filepath})")
        magic, version, total_length = struct.unpack('<4sII', header)
        if magic != b'glTF':
            raise ValueError(f"Invalid GLB magic header: {magic}, expected b'glTF'")

        # Chunk 0: JSON
        c0_hdr = f.read(8)
        if len(c0_hdr) < 8:
            raise ValueError("Corrupt GLB: missing JSON chunk header.")
        c0_len, c0_type = struct.unpack('<II', c0_hdr)
        if c0_type != 0x4E4F534A:  # 'JSON'
            raise ValueError("Corrupt GLB: first chunk must be JSON.")
        json_data = f.read(c0_len).decode('utf-8', errors='ignore')
        gltf = json.loads(json_data)

        # Chunk 1: BIN (if present)
        bin_data = b''
        c1_hdr = f.read(8)
        if len(c1_hdr) == 8:
            c1_len, c1_type = struct.unpack('<II', c1_hdr)
            bin_data = f.read(c1_len)

    name = os.path.splitext(os.path.basename(filepath))[0]
    return _parse_gltf_structure(gltf, [bin_data], name)


def load_gltf(filepath):
    """
    Parse a text glTF 2.0 (.gltf) file.
    Loads JSON, resolves buffers (embedded base64 or external .bin files), and extracts geometry.
    """
    if not os.path.exists(filepath):
        raise FileNotFoundError(f"glTF file not found: {filepath}")

    base_dir = os.path.dirname(filepath)
    with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
        gltf = json.load(f)

    # Resolve all buffers
    buffers_data = []
    for buf in gltf.get('buffers', []):
        uri = buf.get('uri', '')
        if not uri:
            buffers_data.append(b'')
        elif uri.startswith('data:'):
            # Embedded base64
            parts = uri.split('base64,')
            if len(parts) > 1:
                buffers_data.append(base64.b64decode(parts[1]))
            else:
                buffers_data.append(b'')
        else:
            # External .bin file
            bin_path = os.path.join(base_dir, uri)
            if os.path.exists(bin_path):
                with open(bin_path, 'rb') as bf:
                    buffers_data.append(bf.read())
            else:
                buffers_data.append(b'')

    name = os.path.splitext(os.path.basename(filepath))[0]
    return _parse_gltf_structure(gltf, buffers_data, name)


def load_3d_file(filepath):
    """
    Main loader entrypoint supporting OBJ, STL, GLB, and glTF files.
    """
    ext = os.path.splitext(filepath)[1].lower()
    if ext == '.obj':
        return load_obj(filepath)
    elif ext == '.stl':
        return load_stl(filepath)
    elif ext == '.glb':
        return load_glb(filepath)
    elif ext in ('.gltf',):
        return load_gltf(filepath)
    else:
        raise ValueError(f"Unsupported 3D file format: '{ext}'. Supported formats are: .obj, .stl, .glb, .gltf")
