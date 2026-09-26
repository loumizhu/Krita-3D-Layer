"""
renderer.py - Software 3D rendering engine using PyQt5.QtGui.
Supports perspective and orthographic camera, studio dual-light (key + fill),
depth sorting (Painter's algorithm), backface culling, seamless anti-aliased shading,
and multiple artistic shading styles.
"""

import math
from PyQt5.QtGui import (
    QMatrix4x4, QVector3D, QVector4D, QPainter, QImage,
    QColor, QBrush, QPen, QPolygonF
)
from PyQt5.QtCore import QPointF, Qt


class RenderStyle:
    SHADED = "Shaded Planes"
    SHADED_WIREFRAME = "Shaded + Wireframe"
    WIREFRAME = "Wireframe Only"
    SILHOUETTE = "Silhouette Mask"
    NORMAL_MAP = "Normal Map Colors"


class Camera3D:
    def __init__(self):
        self.yaw = 145.0        # Default to 3/4 dynamic face view
        self.pitch = 12.0       # Slight downward tilt
        self.roll = 0.0         # Camera roll
        self.distance = 2.4     # Distance to center
        self.pan_x = 0.0        # Screen-space pan X
        self.pan_y = 0.0        # Screen-space pan Y
        self.fov = 45.0         # Field of view
        self.orthographic = False
        self.near_clip = 0.01
        self.far_clip = 200.0
        # Camera look-at target (world coords, default origin)
        self.target_x = 0.0
        self.target_y = 0.0
        self.target_z = 0.0

    def reset(self):
        self.yaw = 145.0
        self.pitch = 12.0
        self.roll = 0.0
        self.distance = 2.4
        self.pan_x = 0.0
        self.pan_y = 0.0
        self.fov = 45.0
        self.orthographic = False
        self.target_x = 0.0
        self.target_y = 0.0
        self.target_z = 0.0

    def set_front(self):
        self.yaw = 180.0
        self.pitch = 0.0
        self.roll = 0.0

    def set_side_right(self):
        self.yaw = 90.0
        self.pitch = 0.0
        self.roll = 0.0

    def set_side_left(self):
        self.yaw = 270.0
        self.pitch = 0.0
        self.roll = 0.0

    def set_top(self):
        self.yaw = 180.0
        self.pitch = 89.9
        self.roll = 0.0

    def set_bottom(self):
        self.yaw = 180.0
        self.pitch = -89.9
        self.roll = 0.0

    def set_three_quarter(self):
        self.yaw = 145.0
        self.pitch = 12.0
        self.roll = 0.0

    def get_eye_position(self):
        """Calculates camera eye position based on spherical coordinates."""
        rad_yaw = math.radians(self.yaw)
        rad_pitch = math.radians(self.pitch)
        
        x = self.distance * math.cos(rad_pitch) * math.sin(rad_yaw)
        y = self.distance * math.sin(rad_pitch)
        z = self.distance * math.cos(rad_pitch) * math.cos(rad_yaw)
        return QVector3D(x, y, z)

    def get_matrices(self, width, height):
        aspect = float(width) / float(height) if height > 0 else 1.0

        # 1. Projection Matrix
        proj = QMatrix4x4()
        if self.orthographic:
            ortho_size = self.distance * 0.5
            proj.ortho(-ortho_size * aspect, ortho_size * aspect,
                       -ortho_size, ortho_size,
                       self.near_clip, self.far_clip)
        else:
            proj.perspective(self.fov, aspect, self.near_clip, self.far_clip)

        # 2. View Matrix
        view = QMatrix4x4()
        eye = self.get_eye_position()
        target = QVector3D(self.target_x, self.target_y, self.target_z)
        eye = eye + target  # Offset eye by target position
        up = QVector3D(0, 1, 0)
        view.lookAt(eye, target, up)

        # Add pan in view space
        view.translate(self.pan_x, self.pan_y, 0.0)

        # 3. Model Matrix
        model = QMatrix4x4()
        if self.roll != 0:
            model.rotate(self.roll, 0, 0, 1)

        mvp = proj * view * model
        return mvp, view, model


class Lighting3D:
    def __init__(self):
        self.azimuth = 45.0     # Horizontal key light offset (degrees)
        self.elevation = 40.0   # Vertical key light angle (degrees)
        self.ambient = 0.35     # Ambient base lighting
        self.diffuse = 0.65     # Key light intensity
        self.fill_intensity = 0.25  # Soft opposite fill light
        self.follow_camera = True   # Studio light follows camera angle

    def get_light_directions(self, camera):
        """Returns normalized (key_light_dir, fill_light_dir) in model space."""
        rad_az = math.radians(self.azimuth)
        rad_el = math.radians(self.elevation)

        if self.follow_camera:
            eye = camera.get_eye_position().normalized()
            world_up = QVector3D(0, 1, 0)
            right = QVector3D.crossProduct(world_up, eye).normalized()
            cam_up = QVector3D.crossProduct(eye, right).normalized()

            # Key light offset from camera view
            key = (eye * math.cos(rad_el) * math.cos(rad_az) +
                   right * math.sin(rad_az) +
                   cam_up * math.sin(rad_el)).normalized()

            # Opposite fill light (cooler / softer)
            fill = (eye * 0.7 - right * 0.6 - cam_up * 0.3).normalized()
            return key, fill
        else:
            lx = math.cos(rad_el) * math.sin(rad_az)
            ly = math.sin(rad_el)
            lz = math.cos(rad_el) * math.cos(rad_az)
            key = QVector3D(lx, ly, lz).normalized()
            fill = QVector3D(-lx * 0.5, 0.3, -lz * 0.5).normalized()
            return key, fill


class Renderer3D:
    def __init__(self):
        self.base_color = QColor(235, 232, 225)     # Classical plaster white
        self.wire_color = QColor(50, 52, 60, 140)    # Fine graphite/ink contour
        self.wire_width = 1.0
        self.contour_color = QColor(30, 30, 35)      # Dark outline for silhouette
        self.contour_width = 0.0                      # 0 = off, >0 = draw silhouette edges
        self.backface_culling = True
        self.wireframe_backface_culling = True         # Hide back-face wireframes

    def render_to_image(self, mesh, camera, lighting, style=RenderStyle.SHADED,
                        width=800, height=800, bg_color=None):
        """
        Renders the mesh to a QImage of specified size.
        If bg_color is transparent or None, produces transparent background.
        """
        img = QImage(width, height, QImage.Format_ARGB32_Premultiplied)
        if bg_color is None or bg_color.alpha() == 0:
            img.fill(QColor(0, 0, 0, 0))
        else:
            img.fill(bg_color)

        painter = QPainter(img)
        painter.setRenderHint(QPainter.Antialiasing, True)
        self.render_scene(painter, mesh, camera, lighting, style, width, height)
        painter.end()
        return img

    def render_scene(self, painter, mesh, camera, lighting, style, width, height):
        if not mesh or not mesh.vertices or not mesh.faces:
            return

        # Use a square rendering region centered in the viewport
        # This prevents aspect ratio distortion from non-square docker shapes
        render_size = min(width, height)
        offset_x = (width - render_size) * 0.5
        offset_y = (height - render_size) * 0.5

        mvp, view_mat, model_mat = camera.get_matrices(render_size, render_size)
        key_dir, fill_dir = lighting.get_light_directions(camera)
        ambient = lighting.ambient
        diffuse = lighting.diffuse
        fill_weight = lighting.fill_intensity

        # 1. Project all normalized vertices with proper perspective W-divide
        half_size = render_size * 0.5
        
        ndc_pts = []     # (ndc_x, ndc_y, ndc_z) after W-divide
        screen_pts = []
        for v in mesh.vertices:
            # Multiply by MVP as homogeneous 4D vector
            clip = mvp * QVector4D(v.x(), v.y(), v.z(), 1.0)
            w_clip = clip.w()
            if abs(w_clip) < 1e-7:
                w_clip = 1e-7  # Avoid division by zero
            # Perspective divide: clip space -> NDC (-1..1)
            ndc_x = clip.x() / w_clip
            ndc_y = clip.y() / w_clip
            ndc_z = clip.z() / w_clip
            ndc_pts.append((ndc_x, ndc_y, ndc_z))
            # NDC to screen pixels (square region, then offset to center)
            sx = (ndc_x + 1.0) * half_size + offset_x
            sy = (1.0 - ndc_y) * half_size + offset_y
            screen_pts.append(QPointF(sx, sy))

        # 2. Process faces: culling, lighting calculation, and depth collection
        visible_faces = []
        is_wire_only = (style == RenderStyle.WIREFRAME)
        is_normal_map = (style == RenderStyle.NORMAL_MAP)
        is_silhouette = (style == RenderStyle.SILHOUETTE)
        is_shaded_wire = (style == RenderStyle.SHADED_WIREFRAME)

        for i, face in enumerate(mesh.faces):
            p0 = screen_pts[face[0]]
            p1 = screen_pts[face[1]]
            p2 = screen_pts[face[2]]

            # Fast 2D winding order check
            cross2d = (p1.x() - p0.x()) * (p2.y() - p0.y()) - (p1.y() - p0.y()) * (p2.x() - p0.x())
            
            # Cull back-facing triangles (>= 0 because screen Y is flipped)
            is_backface = (cross2d >= 0.0)
            if self.backface_culling and is_backface and not is_wire_only:
                continue
            # Also cull wireframe back-faces if option enabled
            if is_wire_only and self.wireframe_backface_culling and is_backface:
                continue

            # Average depth in NDC space (after perspective divide)
            z_avg = (ndc_pts[face[0]][2] + ndc_pts[face[1]][2] + ndc_pts[face[2]][2]) / 3.0

            # Compute Color
            if is_silhouette:
                face_color = self.base_color
            elif is_normal_map:
                norm = mesh.face_normals[i] if i < len(mesh.face_normals) else QVector3D(0, 1, 0)
                nr = int((norm.x() * 0.5 + 0.5) * 255)
                ng = int((norm.y() * 0.5 + 0.5) * 255)
                nb = int((norm.z() * 0.5 + 0.5) * 255)
                face_color = QColor(nr, ng, nb)
            elif not is_wire_only:
                norm = mesh.face_normals[i] if i < len(mesh.face_normals) else QVector3D(0, 1, 0)
                
                # Lambertian key light + soft fill light
                dot_key = max(0.0, norm.x() * key_dir.x() + norm.y() * key_dir.y() + norm.z() * key_dir.z())
                dot_fill = max(0.0, norm.x() * fill_dir.x() + norm.y() * fill_dir.y() + norm.z() * fill_dir.z())
                light_val = ambient + diffuse * dot_key + fill_weight * dot_fill
                light_val = min(1.0, max(0.0, light_val))
                
                r = int(self.base_color.red() * light_val)
                g = int(self.base_color.green() * light_val)
                b = int(self.base_color.blue() * light_val)
                face_color = QColor(r, g, b, self.base_color.alpha())
            else:
                face_color = QColor(0, 0, 0, 0)

            visible_faces.append((z_avg, face, face_color))

        # 3. Sort by depth (farthest first - Painter's Algorithm)
        visible_faces.sort(key=lambda item: item[0], reverse=True)

        # 4. Draw polygons and track visible face indices for contour detection
        visible_face_indices = set()
        for _, face, f_color in visible_faces:
            if is_wire_only:
                painter.setPen(QPen(self.wire_color, self.wire_width))
                painter.setBrush(Qt.NoBrush)
            elif is_shaded_wire:
                painter.setPen(QPen(self.wire_color, self.wire_width))
                painter.setBrush(QBrush(f_color))
            else:
                # Seal seams by matching pen color with brush fill
                painter.setPen(QPen(f_color, 1.0))
                painter.setBrush(QBrush(f_color))
            
            poly = QPolygonF([screen_pts[face[0]], screen_pts[face[1]], screen_pts[face[2]]])
            painter.drawPolygon(poly)

        # 5. Draw silhouette contour edges (outline around the model)
        if self.contour_width > 0.1 and not is_wire_only:
            # Build or retrieve cached edge -> face adjacency
            edge_faces = getattr(mesh, '_edge_faces_cache', None)
            if edge_faces is None:
                edge_faces = {}
                for i, face_tuple in enumerate(mesh.faces):
                    for j in range(len(face_tuple)):
                        v0 = face_tuple[j]
                        v1 = face_tuple[(j + 1) % len(face_tuple)]
                        ek = (min(v0, v1), max(v0, v1))
                        if ek not in edge_faces:
                            edge_faces[ek] = []
                        edge_faces[ek].append(i)
                mesh._edge_faces_cache = edge_faces

            # Determine which faces are front-facing (visible)
            front_facing = set()
            for i, face_tuple in enumerate(mesh.faces):
                p0 = screen_pts[face_tuple[0]]
                p1 = screen_pts[face_tuple[1]]
                p2 = screen_pts[face_tuple[2]]
                cross = (p1.x()-p0.x())*(p2.y()-p0.y()) - (p1.y()-p0.y())*(p2.x()-p0.x())
                if cross < 0.0:  # Front-facing in screen Y-flipped coords
                    front_facing.add(i)

            # Find silhouette edges: boundary or front/back transition
            contour_pen = QPen(self.contour_color, self.contour_width)
            contour_pen.setCapStyle(Qt.RoundCap)
            contour_pen.setJoinStyle(Qt.RoundJoin)
            painter.setPen(contour_pen)
            painter.setBrush(Qt.NoBrush)
            for (v0, v1), faces_list in edge_faces.items():
                is_silhouette = False
                if len(faces_list) == 1:
                    # Boundary edge - silhouette if face is front-facing
                    if faces_list[0] in front_facing:
                        is_silhouette = True
                elif len(faces_list) >= 2:
                    # Transition edge: one front, one back
                    f0_front = faces_list[0] in front_facing
                    f1_front = faces_list[1] in front_facing
                    if f0_front != f1_front:
                        is_silhouette = True
                if is_silhouette:
                    painter.drawLine(screen_pts[v0], screen_pts[v1])

    def draw_coordinate_gizmo(self, painter, camera, origin_x=45, origin_y=45, size=28):
        """Draws 3D XYZ coordinate gizmo in screen coordinates."""
        eye = camera.get_eye_position().normalized()
        up = QVector3D(0, 1, 0)
        right = QVector3D.crossProduct(up, eye).normalized()
        real_up = QVector3D.crossProduct(eye, right).normalized()

        axes = [
            ("X", QVector3D(1, 0, 0), QColor(240, 75, 75)),
            ("Y", QVector3D(0, 1, 0), QColor(75, 220, 75)),
            ("Z", QVector3D(0, 0, 1), QColor(75, 140, 255))
        ]

        projected = []
        for label, vec, col in axes:
            sx = QVector3D.dotProduct(vec, right) * size
            sy = -QVector3D.dotProduct(vec, real_up) * size
            sz = -QVector3D.dotProduct(vec, eye)
            projected.append((sz, sx, sy, label, col))

        projected.sort(key=lambda item: item[0])

        painter.save()
        painter.setRenderHint(QPainter.Antialiasing, True)
        
        # Background disc
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(QColor(20, 22, 28, 160)))
        painter.drawEllipse(int(origin_x - size - 6), int(origin_y - size - 6), int((size + 6) * 2), int((size + 6) * 2))

        for _, sx, sy, label, col in projected:
            pen = QPen(col, 2.2)
            pen.setCapStyle(Qt.RoundCap)
            painter.setPen(pen)
            painter.drawLine(int(origin_x), int(origin_y), int(origin_x + sx), int(origin_y + sy))
            
            painter.setPen(QPen(col))
            painter.drawText(int(origin_x + sx + (3 if sx >= 0 else -10)),
                             int(origin_y + sy + (3 if sy >= 0 else -3)), label)
        
        painter.restore()
