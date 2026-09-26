"""
renderer.py - Software 3D rendering engine using PyQt5.QtGui.
Supports linear perspective, orthographic, fisheye/curvilinear,
cylindrical/panini projections, studio lighting, depth sorting,
backface culling, and comprehensive 3D perspective grids.
"""

import math
from PyQt5.QtGui import (
    QMatrix4x4, QVector3D, QVector4D, QPainter, QImage,
    QColor, QBrush, QPen, QPolygonF, QFont, QPainterPath
)
from PyQt5.QtCore import QPointF, Qt


class RenderStyle:
    SHADED = "Shaded Planes"
    SHADED_WIREFRAME = "Shaded + Wireframe"
    WIREFRAME = "Wireframe Only"
    SILHOUETTE = "Silhouette Mask"
    NORMAL_MAP = "Normal Map Colors"


class ProjectionMode:
    PERSPECTIVE  = "Linear Perspective"
    ORTHOGRAPHIC = "Orthographic"
    FISHEYE      = "Fisheye / Curvilinear"      # replaces old Fisheye + 5-Point (merged)
    ARTIST_5VP   = "Artist 5-VP (Arc Curves)"   # artist-style curvilinear with arc vanishing lines
    CYLINDRICAL  = "Cylindrical (Panini)"

    ALL = [PERSPECTIVE, ORTHOGRAPHIC, FISHEYE, ARTIST_5VP, CYLINDRICAL]


def project_cam_coords(camera, xc, yc, zc, render_size, offset_x=0.0, offset_y=0.0,
                       aspect=1.0, fill_viewport=False):
    """
    Unified 3D point projection.
    fill_viewport=True: use full render_size (not cropped to circle) for fisheye —
    this makes the grid fill the whole viewport area instead of a smaller circle.
    Returns (QPointF(screen_x, screen_y), ndc_z) or (None, None).
    """
    half_size = render_size * 0.5
    proj_mode = getattr(camera, 'projection_mode', ProjectionMode.PERSPECTIVE)

    # ---- Orthographic -------------------------------------------------------
    if proj_mode == ProjectionMode.ORTHOGRAPHIC or getattr(camera, 'orthographic', False):
        ortho_size = max(0.01, camera.distance * 0.5)
        ndc_x = xc / (ortho_size * aspect)
        ndc_y = yc / ortho_size
        ndc_z = -zc / max(1.0, camera.far_clip)
        sx = (ndc_x + 1.0) * half_size + offset_x
        sy = (1.0 - ndc_y) * half_size + offset_y
        return QPointF(sx, sy), ndc_z

    # ---- Linear Perspective -------------------------------------------------
    if proj_mode == ProjectionMode.PERSPECTIVE:
        if zc <= getattr(camera, 'near_clip', 0.01):
            return None, None
        tan_fov = math.tan(math.radians(max(5.0, min(160.0, camera.fov)) * 0.5))
        ndc_x = xc / (zc * tan_fov * aspect)
        ndc_y = yc / (zc * tan_fov)
        ndc_z = (zc - camera.near_clip) / max(1.0, (camera.far_clip - camera.near_clip))
        sx = (ndc_x + 1.0) * half_size + offset_x
        sy = (1.0 - ndc_y) * half_size + offset_y
        return QPointF(sx, sy), ndc_z

    # ---- Fisheye / Curvilinear (merged from old Fisheye + 5-Point) ----------
    if proj_mode == ProjectionMode.FISHEYE:
        if zc <= 0.001:
            return None, None
        rho = math.hypot(xc, yc)
        theta = math.atan2(rho, zc)   # angle from optical axis [0, pi]

        fish_fov  = getattr(camera, 'fisheye_fov', 180.0)
        fish_mult = getattr(camera, 'fish_fov_mult', 1.0)
        curv      = max(0.1, min(4.0, getattr(camera, 'curvature', 1.0)))
        zoom      = getattr(camera, 'fisheye_zoom', 1.0)
        lens_type = getattr(camera, 'fisheye_lens_type', "Equidistant")

        eff_fov   = min(250.0, max(40.0, fish_fov * fish_mult))
        max_theta = math.radians(eff_fov * 0.5)
        if theta > max_theta:
            return None, None

        norm_theta = theta / max_theta

        # Lens projection model
        if lens_type == "Stereographic":
            denom = math.tan(max_theta * 0.5)
            r = (math.tan(theta * 0.5) / denom) if denom > 1e-6 else norm_theta
        elif lens_type == "Equisolid":
            denom = math.sin(max_theta * 0.5)
            r = (math.sin(theta * 0.5) / denom) if denom > 1e-6 else norm_theta
        elif lens_type == "Orthographic":
            denom = math.sin(max_theta)
            r = (math.sin(theta) / denom) if denom > 1e-6 else norm_theta
        else:  # Equidistant (default)
            r = norm_theta

        # Barrel curvature — stronger distortion so lines visibly bow
        # curv=1 → natural fisheye; curv>1 → more barrel; curv<1 → less
        barrel_k = curv * 1.6
        if barrel_k > 1e-4:
            r_curved = math.atan(r * barrel_k) / math.atan(barrel_k)
        else:
            r_curved = r

        r_final = r_curved * zoom

        factor = (r_final / rho) if rho > 1e-6 else 1.0
        ndc_x = xc * factor
        ndc_y = yc * factor
        ndc_z = zc / max(1.0, camera.far_clip)
        sx = (ndc_x + 1.0) * half_size + offset_x
        sy = (1.0 - ndc_y) * half_size + offset_y
        return QPointF(sx, sy), ndc_z

    # ---- Artist 5-VP Curvilinear (arc-based, handled in grid draw code) -----
    if proj_mode == ProjectionMode.ARTIST_5VP:
        # Same projection as fisheye but with a wider, more exaggerated barrel.
        # The actual arc curves are drawn explicitly in render_perspective_grid.
        if zc <= 0.001:
            return None, None
        rho = math.hypot(xc, yc)
        theta = math.atan2(rho, zc)
        curv  = max(0.5, min(4.0, getattr(camera, 'curvature', 1.5)))
        if theta > math.pi * 0.9:
            return None, None

        norm_t = theta / (math.pi * 0.5)
        # Strong barrel: maps straight lines to visible arcs
        barrel_k = curv * 2.0
        r = math.atan(norm_t * barrel_k) / math.atan(barrel_k) if barrel_k > 1e-4 else norm_t

        zoom = getattr(camera, 'fisheye_zoom', 1.0)
        r *= zoom
        mult = (r / rho) if rho > 1e-6 else 1.0
        ndc_x = xc * mult
        ndc_y = yc * mult
        ndc_z = zc / max(1.0, camera.far_clip)
        sx = (ndc_x + 1.0) * half_size + offset_x
        sy = (1.0 - ndc_y) * half_size + offset_y
        return QPointF(sx, sy), ndc_z

    # ---- Cylindrical / Panini -----------------------------------------------
    if proj_mode == ProjectionMode.CYLINDRICAL:
        if zc <= getattr(camera, 'near_clip', 0.01):
            return None, None
        curv    = max(0.1, min(3.0, getattr(camera, 'curvature', 0.65)))
        tan_fov = math.tan(math.radians(max(5.0, min(160.0, camera.fov)) * 0.5))
        theta_x = math.atan2(xc, zc)
        ndc_x   = theta_x / (tan_fov * aspect * curv)
        ndc_y   = yc / (math.hypot(xc, zc) * tan_fov)
        ndc_z   = zc / max(1.0, camera.far_clip)
        sx = (ndc_x + 1.0) * half_size + offset_x
        sy = (1.0 - ndc_y) * half_size + offset_y
        return QPointF(sx, sy), ndc_z

    return None, None


def project_camera_point(camera, view_mat, x, y, z, render_size,
                         offset_x=0.0, offset_y=0.0, aspect=1.0):
    p_cam = view_mat * QVector4D(x, y, z, 1.0)
    xc = p_cam.x()
    yc = p_cam.y()
    zc = -p_cam.z()
    return project_cam_coords(camera, xc, yc, zc, render_size, offset_x, offset_y, aspect)


def apply_projection_distortion(ndc_x, ndc_y, mode, curvature=0.65):
    """Legacy 2D distortion fallback."""
    if mode in (ProjectionMode.PERSPECTIVE, ProjectionMode.ORTHOGRAPHIC):
        return ndc_x, ndc_y
    r = math.sqrt(ndc_x * ndc_x + ndc_y * ndc_y)
    if r < 1e-6:
        return ndc_x, ndc_y
    k = max(0.05, float(curvature))
    if mode in (ProjectionMode.FISHEYE, ProjectionMode.ARTIST_5VP):
        theta = math.atan(r * k * 1.8)
        r_dist = theta / (k * 1.8)
        factor = (r_dist / r) * (1.0 + 0.15 * k * r * r)
        return ndc_x * factor, ndc_y * factor
    elif mode == ProjectionMode.CYLINDRICAL:
        x_dist = math.atan(ndc_x * k * 1.5) / (k * 1.5)
        y_dist = ndc_y / math.sqrt(1.0 + (ndc_x * k * 1.5) ** 2)
        return x_dist, y_dist
    return ndc_x, ndc_y


class PerspectiveGridSettings:
    """Settings for rendering mathematically correct 3D perspective grids."""
    def __init__(self):
        self.enabled = False            # Draw grid on Krita canvas layer
        self.show_in_viewport = True    # Show grid in 3D viewport
        self.horizon_enabled = True     # Draw horizon line
        self.horizon_color = QColor(250, 204, 21, 240)
        self.horizon_width = 1.8
        self.horizon_opacity = 0.95
        self.ground_enabled = True
        self.ceiling_enabled = False
        self.ceiling_height = 2.5
        self.grid_extent = 12
        self.tile_size = 0.5
        self.subdivisions = 1
        self.exceed_lines = True
        self.vertical_lines = True
        self.vertical_height = 2.5
        self.grid_color = QColor(56, 189, 248, 160)
        self.ceiling_color = QColor(217, 70, 239, 140)
        self.sub_color = QColor(148, 163, 184, 90)
        self.grid_width = 1.0
        self.grid_opacity = 0.85
        self.axis_colors = True
        self.fade_grid = True


class Camera3D:
    def __init__(self):
        self.yaw = 145.0
        self.pitch = 12.0
        self.tilt = 0.0
        self.roll = 0.0
        self.distance = 2.8
        self.pan_x = 0.0
        self.pan_y = 0.0
        self.fov = 45.0
        self.orthographic = False
        self.projection_mode = ProjectionMode.PERSPECTIVE
        self.curvature = 1.0
        self.fish_fov_mult = 1.0
        self.fisheye_fov = 180.0
        self.fisheye_lens_type = "Equidistant"
        self.fisheye_crop_circle = False
        self.fisheye_zoom = 1.0
        self.near_clip = 0.01
        self.far_clip = 300.0
        self.target_x = 0.0
        self.target_y = 0.0
        self.target_z = 0.0

    def reset(self):
        self.yaw = 145.0
        self.pitch = 12.0
        self.tilt = 0.0
        self.roll = 0.0
        self.distance = 2.8
        self.pan_x = 0.0
        self.pan_y = 0.0
        self.fov = 45.0
        self.orthographic = False
        self.projection_mode = ProjectionMode.PERSPECTIVE
        self.curvature = 1.0
        self.fish_fov_mult = 1.0
        self.fisheye_fov = 180.0
        self.fisheye_lens_type = "Equidistant"
        self.fisheye_crop_circle = False
        self.fisheye_zoom = 1.0
        self.target_x = 0.0
        self.target_y = 0.0
        self.target_z = 0.0

    def set_front(self):
        self.yaw = 180.0; self.pitch = 0.0; self.roll = 0.0; self.tilt = 0.0

    def set_side_right(self):
        self.yaw = 90.0;  self.pitch = 0.0; self.roll = 0.0; self.tilt = 0.0

    def set_side_left(self):
        self.yaw = 270.0; self.pitch = 0.0; self.roll = 0.0; self.tilt = 0.0

    def set_top(self):
        self.yaw = 180.0; self.pitch = 89.9; self.roll = 0.0; self.tilt = 0.0

    def set_bottom(self):
        self.yaw = 180.0; self.pitch = -89.9; self.roll = 0.0; self.tilt = 0.0

    def set_three_quarter(self):
        self.yaw = 145.0; self.pitch = 12.0; self.roll = 0.0; self.tilt = 0.0

    def get_eye_position(self):
        rad_yaw   = math.radians(self.yaw)
        rad_pitch = math.radians(self.pitch)
        x = self.distance * math.cos(rad_pitch) * math.sin(rad_yaw)
        y = self.distance * math.sin(rad_pitch)
        z = self.distance * math.cos(rad_pitch) * math.cos(rad_yaw)
        return QVector3D(x, y, z)

    def get_matrices(self, width, height):
        aspect = float(width) / float(height) if height > 0 else 1.0

        proj = QMatrix4x4()
        is_ortho = (self.orthographic or self.projection_mode == ProjectionMode.ORTHOGRAPHIC)
        if is_ortho:
            ortho_size = self.distance * 0.5
            proj.ortho(-ortho_size * aspect, ortho_size * aspect,
                       -ortho_size, ortho_size, self.near_clip, self.far_clip)
        else:
            proj.perspective(self.fov, aspect, self.near_clip, self.far_clip)

        view = QMatrix4x4()
        eye    = self.get_eye_position()
        target = QVector3D(self.target_x, self.target_y, self.target_z)
        eye    = eye + target
        view.lookAt(eye, target, QVector3D(0, 1, 0))

        cam_transform = QMatrix4x4()
        cam_transform.translate(self.pan_x, self.pan_y, 0.0)
        if getattr(self, 'tilt', 0.0) != 0.0:
            cam_transform.rotate(self.tilt, 1, 0, 0)
        if getattr(self, 'roll', 0.0) != 0.0:
            cam_transform.rotate(self.roll, 0, 0, 1)
        view = cam_transform * view

        model = QMatrix4x4()
        mvp   = proj * view * model
        return mvp, view, model


class Lighting3D:
    def __init__(self):
        self.azimuth   = 45.0
        self.elevation = 40.0
        self.ambient   = 0.45
        self.diffuse   = 0.55
        self.fill_intensity = 0.35
        self.follow_camera  = True

    def get_light_directions(self, camera):
        rad_az = math.radians(self.azimuth)
        rad_el = math.radians(self.elevation)
        if self.follow_camera:
            eye     = camera.get_eye_position().normalized()
            world_up = QVector3D(0, 1, 0)
            right   = QVector3D.crossProduct(world_up, eye).normalized()
            cam_up  = QVector3D.crossProduct(eye, right).normalized()
            key  = (eye * math.cos(rad_el) * math.cos(rad_az) +
                    right * math.sin(rad_az) +
                    cam_up * math.sin(rad_el)).normalized()
            fill = (eye * 0.7 - right * 0.6 - cam_up * 0.3).normalized()
        else:
            lx  = math.cos(rad_el) * math.sin(rad_az)
            ly  = math.sin(rad_el)
            lz  = math.cos(rad_el) * math.cos(rad_az)
            key  = QVector3D(lx, ly, lz).normalized()
            fill = QVector3D(-lx * 0.5, 0.3, -lz * 0.5).normalized()
        return key, fill


class Renderer3D:
    def __init__(self):
        self.base_color    = QColor(228, 231, 236)
        self.wire_color    = QColor(50, 52, 60, 160)
        self.wire_width    = 1.0
        self.contour_color = QColor(30, 30, 35)
        self.contour_width = 0.0
        self.backface_culling          = True
        self.wireframe_backface_culling = True
        self.hide_coplanar_edges       = True
        self.quality = "Balanced"

    def render_to_image(self, mesh, camera, lighting, style=RenderStyle.SHADED,
                        width=800, height=800, bg_color=None, grid_settings=None,
                        draw_model=True):
        img = QImage(width, height, QImage.Format_ARGB32_Premultiplied)
        if bg_color is None or bg_color.alpha() == 0:
            img.fill(QColor(0, 0, 0, 0))
        else:
            img.fill(bg_color)

        painter = QPainter(img)
        painter.setRenderHint(QPainter.Antialiasing, True)

        ground_y = 0.0
        if mesh and hasattr(mesh, 'bbox_min'):
            ground_y = mesh.bbox_min.y()

        if grid_settings and (grid_settings.enabled or grid_settings.show_in_viewport):
            self.render_perspective_grid(painter, camera, grid_settings, width, height,
                                         ground_y=ground_y)
        if draw_model and mesh and mesh.vertices:
            self.render_scene(painter, mesh, camera, lighting, style, width, height)

        painter.end()
        return img

    def render_scene(self, painter, mesh, camera, lighting, style, width, height):
        if not mesh or not mesh.vertices or not mesh.faces:
            return

        proj_mode = getattr(camera, 'projection_mode', ProjectionMode.PERSPECTIVE)
        is_curvilinear = (proj_mode not in (ProjectionMode.PERSPECTIVE, ProjectionMode.ORTHOGRAPHIC))

        # For fisheye / curvilinear use full extent so model fills viewport
        render_size = max(width, height) if is_curvilinear else min(width, height)
        offset_x = (width  - render_size) * 0.5
        offset_y = (height - render_size) * 0.5

        mvp, view_mat, model_mat = camera.get_matrices(render_size, render_size)
        key_dir, fill_dir = lighting.get_light_directions(camera)
        ambient     = lighting.ambient
        diffuse     = lighting.diffuse
        fill_weight = lighting.fill_intensity

        half_size = render_size * 0.5

        screen_pts = []
        ndc_pts    = []
        for v in mesh.vertices:
            pt, ndc_z = project_camera_point(
                camera, view_mat, v.x(), v.y(), v.z(),
                render_size, offset_x, offset_y, aspect=1.0)
            if pt is None:
                screen_pts.append(QPointF(-9999.0, -9999.0))
                ndc_pts.append((0.0, 0.0, 999.0))
            else:
                screen_pts.append(pt)
                ndc_pts.append((0.0, 0.0, ndc_z if ndc_z is not None else 0.0))

        visible_faces  = []
        is_wire_only   = (style == RenderStyle.WIREFRAME)
        is_normal_map  = (style == RenderStyle.NORMAL_MAP)
        is_silhouette  = (style == RenderStyle.SILHOUETTE)
        is_shaded_wire = (style == RenderStyle.SHADED_WIREFRAME)

        for i, face in enumerate(mesh.faces):
            p0 = screen_pts[face[0]]; p1 = screen_pts[face[1]]; p2 = screen_pts[face[2]]

            cross2d   = (p1.x()-p0.x())*(p2.y()-p0.y()) - (p1.y()-p0.y())*(p2.x()-p0.x())
            is_backface = (cross2d >= 0.0)
            if self.backface_culling and is_backface and not is_wire_only:
                continue
            if is_wire_only and self.wireframe_backface_culling and is_backface:
                continue

            z_avg = (ndc_pts[face[0]][2] + ndc_pts[face[1]][2] + ndc_pts[face[2]][2]) / 3.0

            if is_silhouette:
                face_color = self.base_color
            elif is_normal_map:
                norm = mesh.face_normals[i] if i < len(mesh.face_normals) else QVector3D(0, 1, 0)
                face_color = QColor(int((norm.x()*0.5+0.5)*255),
                                    int((norm.y()*0.5+0.5)*255),
                                    int((norm.z()*0.5+0.5)*255))
            elif not is_wire_only:
                norm = mesh.face_normals[i] if i < len(mesh.face_normals) else QVector3D(0, 1, 0)
                dot_key  = max(0.0, norm.x()*key_dir.x()+norm.y()*key_dir.y()+norm.z()*key_dir.z())
                dot_fill = max(0.0, norm.x()*fill_dir.x()+norm.y()*fill_dir.y()+norm.z()*fill_dir.z())
                light_val = min(1.0, max(0.0, ambient + diffuse*dot_key + fill_weight*dot_fill))
                face_color = QColor(int(self.base_color.red()*light_val),
                                    int(self.base_color.green()*light_val),
                                    int(self.base_color.blue()*light_val),
                                    self.base_color.alpha())
            else:
                face_color = QColor(0, 0, 0, 0)

            visible_faces.append((z_avg, face, face_color))

        visible_faces.sort(key=lambda item: item[0], reverse=True)

        if self.contour_width > 0.1 and not is_wire_only:
            c_pen = QPen(self.contour_color, self.contour_width*2.0, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
            painter.setPen(c_pen)
            painter.setBrush(QBrush(self.contour_color))
            for _, face, _ in visible_faces:
                poly = QPolygonF([screen_pts[face[0]], screen_pts[face[1]], screen_pts[face[2]]])
                painter.drawPolygon(poly)

        # Shaded surfaces pass (for non-wire styles)
        if not is_wire_only and not is_shaded_wire:
            for _, face, f_color in visible_faces:
                poly = QPolygonF([screen_pts[face[0]], screen_pts[face[1]], screen_pts[face[2]]])
                painter.setPen(QPen(f_color, 0.7))
                painter.setBrush(QBrush(f_color))
                painter.drawPolygon(poly)
        elif is_shaded_wire:
            # Draw shaded faces without wire stroke to eliminate internal cracks
            for _, face, f_color in visible_faces:
                poly = QPolygonF([screen_pts[face[0]], screen_pts[face[1]], screen_pts[face[2]]])
                painter.setPen(QPen(f_color, 0.7))
                painter.setBrush(QBrush(f_color))
                painter.drawPolygon(poly)

        # Wireframe edges pass (for Wireframe and Shaded + Wireframe)
        if is_shaded_wire or is_wire_only:
            wire_pen = QPen(self.wire_color, self.wire_width, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
            painter.setPen(wire_pen)
            painter.setBrush(Qt.NoBrush)
            coplanar = getattr(mesh, "coplanar_edges", set()) if self.hide_coplanar_edges else set()
            drawn_edges = set()
            for _, face, _ in visible_faces:
                v0, v1, v2 = face[0], face[1], face[2]
                for e in ((v0, v1) if v0 < v1 else (v1, v0),
                          (v1, v2) if v1 < v2 else (v2, v1),
                          (v2, v0) if v2 < v0 else (v0, v2)):
                    if e in drawn_edges:
                        continue
                    drawn_edges.add(e)
                    if self.hide_coplanar_edges and e in coplanar:
                        continue
                    pA = screen_pts[e[0]]
                    pB = screen_pts[e[1]]
                    if pA.x() > -9000 and pB.x() > -9000:
                        painter.drawLine(pA, pB)

        # Circular fisheye vignette mask
        if proj_mode == ProjectionMode.FISHEYE and getattr(camera, 'fisheye_crop_circle', False):
            r_circ = half_size * getattr(camera, 'fisheye_zoom', 1.0)
            center = QPointF(half_size + offset_x, half_size + offset_y)
            path = QPainterPath()
            path.addRect(0, 0, width, height)
            circle_path = QPainterPath()
            circle_path.addEllipse(center, r_circ, r_circ)
            mask = path.subtracted(circle_path)
            painter.fillPath(mask, QBrush(QColor(15, 18, 25, 235)))
            painter.setPen(QPen(QColor(70, 85, 110, 190), 1.5))
            painter.drawEllipse(center, r_circ, r_circ)

    # ------------------------------------------------------------------
    def render_perspective_grid(self, painter, camera, settings, width, height, ground_y=0.0):
        """
        Renders a mathematically accurate 3D perspective grid.
        For fisheye/curvilinear modes, uses the FULL viewport size so the grid
        fills the complete area rather than being cropped to a small circle.
        For Artist 5-VP mode, draws arc curves like hand-drawn 5-point perspective.
        """
        if not settings:
            return

        proj_mode      = getattr(camera, 'projection_mode', ProjectionMode.PERSPECTIVE)
        is_curvilinear = (proj_mode not in (ProjectionMode.PERSPECTIVE, ProjectionMode.ORTHOGRAPHIC))
        is_artist_5vp  = (proj_mode == ProjectionMode.ARTIST_5VP)

        # Key fix: use FULL size for curvilinear so grid fills entire viewport
        if is_curvilinear:
            render_size = max(width, height)
        else:
            render_size = min(width, height)

        offset_x  = (width  - render_size) * 0.5
        offset_y  = (height - render_size) * 0.5
        half_size = render_size * 0.5

        mvp, view_mat, _ = camera.get_matrices(render_size, render_size)

        grid_opacity = getattr(settings, 'grid_opacity', 0.85)

        def project_3d_point(x, y, z):
            pt, _ = project_camera_point(
                camera, view_mat, x, y, z,
                render_size, offset_x, offset_y, aspect=1.0)
            return pt

        fade_active = bool(getattr(settings, 'fade_grid', True))

        def clip_segment_near_plane(p1, p2, near_z=0.03):
            c1 = view_mat * QVector4D(p1[0], p1[1], p1[2], 1.0)
            c2 = view_mat * QVector4D(p2[0], p2[1], p2[2], 1.0)
            z1 = -c1.z()
            z2 = -c2.z()
            if z1 < near_z and z2 < near_z:
                return None, None, 0.0, 0.0
            v1 = QVector3D(*p1)
            v2 = QVector3D(*p2)
            if z1 < near_z:
                denom = (z2 - z1)
                t = (near_z - z1) / denom if abs(denom) > 1e-6 else 0.0
                v1 = v1 * (1.0 - t) + v2 * t
                z1 = near_z
            elif z2 < near_z:
                denom = (z1 - z2)
                t = (near_z - z2) / denom if abs(denom) > 1e-6 else 0.0
                v2 = v2 * (1.0 - t) + v1 * t
                z2 = near_z
            return (v1.x(), v1.y(), v1.z()), (v2.x(), v2.y(), v2.z()), z1, z2

        # Compute dynamic horizon fade distances
        step_base = settings.tile_size
        grid_ext_count = max(16, settings.grid_extent)
        base_extent = grid_ext_count * step_base
        fade_start = base_extent * 0.35
        fade_end   = base_extent * 2.8 if settings.exceed_lines else base_extent * 1.2

        def get_depth_alpha(z):
            if not fade_active or z <= fade_start:
                return 1.0
            if z >= fade_end:
                return 0.0
            t = (z - fade_start) / (fade_end - fade_start)
            return max(0.0, min(1.0, 0.5 * (1.0 + math.cos(math.pi * t))))

        def draw_3d_segment(p1_3d, p2_3d, pen):
            cp1, cp2, z1, z2 = clip_segment_near_plane(p1_3d, p2_3d, near_z=0.03)
            if not cp1 or not cp2:
                return

            a1 = get_depth_alpha(z1)
            a2 = get_depth_alpha(z2)
            if fade_active and a1 <= 0.005 and a2 <= 0.005:
                return

            if is_curvilinear:
                v1 = QVector3D(*cp1)
                v2 = QVector3D(*cp2)
                seg_len = (v2 - v1).length()
                steps = max(24, min(80, int(seg_len * 12)))
                curr_seg = []
                for s in range(steps + 1):
                    t  = s / float(steps)
                    vm = v1 * (1.0 - t) + v2 * t
                    zs = z1 * (1.0 - t) + z2 * t
                    as_ = get_depth_alpha(zs)
                    if as_ <= 0.005:
                        continue
                    pt = project_3d_point(vm.x(), vm.y(), vm.z())
                    if pt is not None:
                        curr_seg.append((pt, as_))
                    else:
                        if len(curr_seg) >= 2:
                            for idx in range(len(curr_seg) - 1):
                                p_a = curr_seg[idx][0]
                                p_b = curr_seg[idx + 1][0]
                                a_mid = (curr_seg[idx][1] + curr_seg[idx + 1][1]) * 0.5
                                step_pen = QPen(pen)
                                c = step_pen.color()
                                c.setAlpha(int(c.alpha() * a_mid))
                                step_pen.setColor(c)
                                painter.setPen(step_pen)
                                painter.drawLine(p_a, p_b)
                        curr_seg = []
                if len(curr_seg) >= 2:
                    for idx in range(len(curr_seg) - 1):
                        p_a = curr_seg[idx][0]
                        p_b = curr_seg[idx + 1][0]
                        a_mid = (curr_seg[idx][1] + curr_seg[idx + 1][1]) * 0.5
                        step_pen = QPen(pen)
                        c = step_pen.color()
                        c.setAlpha(int(c.alpha() * a_mid))
                        step_pen.setColor(c)
                        painter.setPen(step_pen)
                        painter.drawLine(p_a, p_b)
                return

            pt1 = project_3d_point(*cp1)
            pt2 = project_3d_point(*cp2)
            if pt1 and pt2:
                if fade_active and (a1 < 0.99 or a2 < 0.99):
                    grad = QLinearGradient(pt1, pt2)
                    c1 = QColor(pen.color())
                    c1.setAlpha(int(c1.alpha() * a1))
                    c2 = QColor(pen.color())
                    c2.setAlpha(int(c2.alpha() * a2))
                    grad.setColorAt(0.0, c1)
                    grad.setColorAt(1.0, c2)
                    f_pen = QPen(QBrush(grad), pen.widthF(), pen.style(), pen.capStyle(), pen.joinStyle())
                    painter.setPen(f_pen)
                else:
                    painter.setPen(pen)
                painter.drawLine(pt1, pt2)
            elif pt1 or pt2:
                v1 = QVector3D(*cp1)
                v2 = QVector3D(*cp2)
                for step in range(1, 10):
                    t = step / 10.0
                    vm = v1 * (1.0 - t) + v2 * t
                    pt_mid = project_3d_point(vm.x(), vm.y(), vm.z())
                    if pt1 and not pt_mid:
                        t_prev = max(0.0, t - 0.1)
                        vm_prev = v1 * (1.0 - t_prev) + v2 * t_prev
                        pt_prev = project_3d_point(vm_prev.x(), vm_prev.y(), vm_prev.z())
                        if pt_prev:
                            painter.setPen(pen)
                            painter.drawLine(pt1, pt_prev)
                        break
                    elif pt2 and pt_mid:
                        painter.setPen(pen)
                        painter.drawLine(pt_mid, pt2)
                        break

        def draw_grid_plane(plane_y, base_col, is_ground=True):
            sub      = max(1, settings.subdivisions)
            step     = settings.tile_size
            sub_step = step / float(sub)
            grid_ext_count = max(16, settings.grid_extent)
            extent   = grid_ext_count * step
            max_range = extent * (3.0 if is_curvilinear else (10.0 if settings.exceed_lines else 1.0))

            num_dense  = int(round(extent / sub_step))
            num_exceed = int(round(max_range / step))

            # --- Lines parallel to Z (varying X) ---
            dense_x = [k * sub_step for k in range(-num_dense, num_dense + 1)]
            x_seen  = set(round(x, 4) for x in dense_x)
            outer_x = []
            if settings.exceed_lines:
                for k in range(-num_exceed, num_exceed + 1):
                    x_val = k * step
                    if round(x_val, 4) not in x_seen:
                        outer_x.append(x_val)

            for x in dense_x:
                is_axis = abs(x) < 1e-4
                is_main = abs(round(x / step) - (x / step)) < 1e-3
                if is_axis and settings.axis_colors and is_ground:
                    col = QColor(59, 130, 246, int(230 * grid_opacity))
                    pen = QPen(col, settings.grid_width + 0.9)
                elif is_main:
                    col = QColor(base_col); col.setAlpha(int(col.alpha() * grid_opacity))
                    pen = QPen(col, settings.grid_width)
                else:
                    col = QColor(settings.sub_color); col.setAlpha(int(col.alpha() * grid_opacity))
                    pen = QPen(col, max(0.5, settings.grid_width * 0.7), Qt.DotLine)
                z_reach = max_range if (settings.exceed_lines and is_main) else extent
                draw_3d_segment((x, plane_y, -z_reach), (x, plane_y, z_reach), pen)

            for x in outer_x:
                col = QColor(base_col); col.setAlpha(int(col.alpha() * grid_opacity * 0.65))
                pen = QPen(col, max(0.5, settings.grid_width * 0.8))
                draw_3d_segment((x, plane_y, -max_range), (x, plane_y, max_range), pen)

            # --- Lines parallel to X (varying Z) ---
            dense_z = [k * sub_step for k in range(-num_dense, num_dense + 1)]
            z_seen  = set(round(z, 4) for z in dense_z)
            outer_z = []
            if settings.exceed_lines:
                for k in range(-num_exceed, num_exceed + 1):
                    z_val = k * step
                    if round(z_val, 4) not in z_seen:
                        outer_z.append(z_val)

            for z in dense_z:
                is_axis = abs(z) < 1e-4
                is_main = abs(round(z / step) - (z / step)) < 1e-3
                if is_axis and settings.axis_colors and is_ground:
                    col = QColor(239, 68, 68, int(230 * grid_opacity))
                    pen = QPen(col, settings.grid_width + 0.9)
                elif is_main:
                    col = QColor(base_col); col.setAlpha(int(col.alpha() * grid_opacity))
                    pen = QPen(col, settings.grid_width)
                else:
                    col = QColor(settings.sub_color); col.setAlpha(int(col.alpha() * grid_opacity))
                    pen = QPen(col, max(0.5, settings.grid_width * 0.7), Qt.DotLine)
                x_reach = max_range if (settings.exceed_lines and is_main) else extent
                draw_3d_segment((-x_reach, plane_y, z), (x_reach, plane_y, z), pen)

            for z in outer_z:
                col = QColor(base_col); col.setAlpha(int(col.alpha() * grid_opacity * 0.65))
                pen = QPen(col, max(0.5, settings.grid_width * 0.8))
                draw_3d_segment((-max_range, plane_y, z), (max_range, plane_y, z), pen)

        # ============================================================
        # ARTIST 5-VP MODE — draw arc-based vanishing curves
        # ============================================================
        if is_artist_5vp:
            self._draw_artist_5vp_grid(
                painter, camera, settings, view_mat,
                render_size, offset_x, offset_y, ground_y, grid_opacity)
            # Horizon line still drawn below
        else:
            # Ground and Ceiling grids
            if settings.ground_enabled:
                draw_grid_plane(ground_y, settings.grid_color, is_ground=True)
            if getattr(settings, 'ceiling_enabled', False):
                ceil_h   = getattr(settings, 'ceiling_height', 2.5)
                ceil_col = getattr(settings, 'ceiling_color', QColor(217, 70, 239, 140))
                draw_grid_plane(ground_y + ceil_h, ceil_col, is_ground=False)

            # Vertical height poles
            if settings.vertical_lines and settings.vertical_height > 0:
                h_val = settings.vertical_height
                ext   = settings.grid_extent * settings.tile_size
                corner_pts = [
                    (0.0, 0.0), (-ext, -ext), (ext, -ext),
                    (-ext,  ext), (ext,  ext),
                    (0.0, -ext), (0.0, ext), (-ext, 0.0), (ext, 0.0)
                ]
                for cx_p, cz_p in corner_pts:
                    is_center = (abs(cx_p) < 1e-4 and abs(cz_p) < 1e-4)
                    if is_center and settings.axis_colors:
                        v_pen = QPen(QColor(34, 197, 94, int(220*grid_opacity)), settings.grid_width+0.8)
                    else:
                        v_pen = QPen(QColor(168, 85, 247, int(150*grid_opacity)), settings.grid_width, Qt.DashLine)
                    draw_3d_segment((cx_p, ground_y, cz_p), (cx_p, ground_y + h_val, cz_p), v_pen)

        # ============================================================
        # Horizon Line
        # ============================================================
        if settings.horizon_enabled:
            h_col  = QColor(settings.horizon_color)
            h_col.setAlpha(int(getattr(settings, 'horizon_opacity', 0.95) * 255))
            h_halo = QPen(QColor(0, 0, 0, 160), settings.horizon_width + 2.0)
            h_pen  = QPen(h_col, settings.horizon_width, Qt.SolidLine)

            norm_view = (view_mat * QVector4D(0, 1, 0, 0)).toVector3D().normalized()
            nx, ny, nz = norm_view.x(), norm_view.y(), norm_view.z()

            if is_curvilinear:
                u = QVector3D.crossProduct(QVector3D(nx, ny, nz), QVector3D(0, 0, -1))
                if u.length() < 1e-4:
                    u = QVector3D(1, 0, 0)
                else:
                    u.normalize()
                v = QVector3D.crossProduct(u, QVector3D(nx, ny, nz)).normalized()
                if v.z() > 0:
                    v = -v

                steps    = 100
                max_ang  = math.radians(min(176.0, getattr(camera, 'fisheye_fov', 180.0)) * 0.5)
                h_pts    = []
                for s in range(steps + 1):
                    frac = (s / float(steps)) * 2.0 - 1.0
                    ang  = frac * max_ang
                    dir_cam = u * math.sin(ang) + v * math.cos(ang)
                    xc_h = dir_cam.x() * 200.0
                    yc_h = dir_cam.y() * 200.0
                    zc_h = -dir_cam.z() * 200.0
                    if zc_h > 0.05:
                        pt, _ = project_cam_coords(camera, xc_h, yc_h, zc_h,
                                                   render_size, offset_x, offset_y, aspect=1.0)
                        if pt is not None:
                            h_pts.append(pt)

                if len(h_pts) >= 2:
                    for painter_pen in [h_halo, h_pen]:
                        painter.setPen(painter_pen)
                        for idx in range(len(h_pts) - 1):
                            painter.drawLine(h_pts[idx], h_pts[idx + 1])
            else:
                if abs(ny) > 1e-5:
                    fov_val  = max(5.0, min(160.0, camera.fov))
                    f_eff    = (render_size * 0.5) / math.tan(math.radians(fov_val * 0.5))
                    cx_center = width  * 0.5
                    cy_center = height * 0.5
                    cy_h  = cy_center - f_eff * (nz / ny)
                    slope = nx / ny
                    x_left  = -width * 2.0
                    y_left  = cy_h + slope * (x_left - cx_center)
                    x_right = width * 3.0
                    y_right = cy_h + slope * (x_right - cx_center)
                    painter.setPen(h_halo)
                    painter.drawLine(QPointF(x_left, y_left), QPointF(x_right, y_right))
                    painter.setPen(h_pen)
                    painter.drawLine(QPointF(x_left, y_left), QPointF(x_right, y_right))

    # ------------------------------------------------------------------
    def _draw_artist_5vp_grid(self, painter, camera, settings, view_mat,
                               render_size, offset_x, offset_y, ground_y, grid_opacity):
        """
        Artist-style 5-point perspective grid.
        Lines radiate from 5 vanishing points (L, R, T, B, C) and curve
        as arcs rather than straight projected lines — just like hand-drawn
        curvilinear perspective in illustration textbooks.
        """
        w = render_size + abs(offset_x) * 2
        h = render_size + abs(offset_y) * 2
        cx = offset_x + render_size * 0.5
        cy = offset_y + render_size * 0.5

        # Derive horizon position from camera pitch
        pitch_rad = math.radians(camera.pitch)
        horizon_y = cy - math.sin(pitch_rad) * render_size * 0.5

        # Radius of the containing circle (where all 5 VPs live)
        R = render_size * 0.5 * getattr(camera, 'fisheye_zoom', 1.0)

        # Yaw offset for left/right VP positions
        yaw_rad = math.radians(camera.yaw)
        yaw_offset_x = math.sin(yaw_rad) * R * 0.0  # symmetric for simplicity

        # 5 vanishing points
        VP_L = QPointF(cx - R, horizon_y)
        VP_R = QPointF(cx + R, horizon_y)
        VP_T = QPointF(cx, cy - R)
        VP_B = QPointF(cx, cy + R)
        VP_C = QPointF(cx, horizon_y)  # center / zenith

        grid_col  = QColor(settings.grid_color)
        grid_col.setAlpha(int(grid_col.alpha() * grid_opacity))
        main_pen  = QPen(grid_col, settings.grid_width, Qt.SolidLine)

        sub_col   = QColor(settings.sub_color)
        sub_col.setAlpha(int(sub_col.alpha() * grid_opacity))
        sub_pen   = QPen(sub_col, max(0.5, settings.grid_width * 0.6), Qt.DotLine)

        curvature = max(0.5, min(4.0, getattr(camera, 'curvature', 1.5)))

        def draw_arc_between(vp, target_pt, pen, n_pts=60):
            """Draw a curve from the vanishing point toward target_pt as an arc."""
            painter.setPen(pen)
            # Bezier-like curve: control point is offset perpendicular to center
            dx = target_pt.x() - vp.x()
            dy = target_pt.y() - vp.y()
            dist = math.hypot(dx, dy)
            if dist < 1.0:
                return
            # Perpendicular offset to create the arc bend — scaled by curvature
            perp_x = -dy / dist
            perp_y =  dx / dist
            ctrl_bulge = dist * 0.35 * (curvature - 1.0)  # 0 at curv=1
            ctrl = QPointF(
                (vp.x() + target_pt.x()) * 0.5 + perp_x * ctrl_bulge,
                (vp.y() + target_pt.y()) * 0.5 + perp_y * ctrl_bulge
            )
            path = QPainterPath(vp)
            path.quadTo(ctrl, target_pt)
            painter.drawPath(path)

        def radiate_from_vp(vp, angle_start, angle_end, n_lines, pen, radius=None):
            """Draw n_lines arcs radiating from a VP, spanning angle range."""
            if radius is None:
                radius = R * 2.2
            for i in range(n_lines):
                t   = i / max(1, n_lines - 1)
                ang = angle_start + t * (angle_end - angle_start)
                tx  = vp.x() + math.cos(math.radians(ang)) * radius
                ty  = vp.y() + math.sin(math.radians(ang)) * radius
                draw_arc_between(vp, QPointF(tx, ty), pen)

        n_main = max(4, settings.grid_extent // 2)
        n_sub  = n_main * max(1, settings.subdivisions)

        # ── Lines from Left VP ──────────────────────────────
        radiate_from_vp(VP_L, -60, 60, n_main, main_pen)
        if settings.subdivisions > 1:
            radiate_from_vp(VP_L, -60, 60, n_sub, sub_pen)

        # ── Lines from Right VP ─────────────────────────────
        radiate_from_vp(VP_R, 120, 240, n_main, main_pen)
        if settings.subdivisions > 1:
            radiate_from_vp(VP_R, 120, 240, n_sub, sub_pen)

        # ── Lines from Top VP (downward arcs) ───────────────
        if settings.ceiling_enabled or settings.vertical_lines:
            radiate_from_vp(VP_T, 60, 120, n_main // 2 + 2, main_pen)

        # ── Lines from Bottom VP (upward arcs) ──────────────
        if settings.ground_enabled:
            radiate_from_vp(VP_B, -120, -60, n_main // 2 + 2, main_pen)

        # ── Concentric arc "latitude" lines between L and R ─
        arc_col = QColor(settings.grid_color)
        for k in range(1, n_main):
            t = k / float(n_main)
            # Arc from VP_L to VP_R at different heights
            arc_y = horizon_y + (t - 0.5) * R * 1.4 * curvature
            mid_pt = QPointF(cx, arc_y)
            arc_pen = QPen(QColor(arc_col.red(), arc_col.green(), arc_col.blue(),
                                  int(arc_col.alpha() * grid_opacity * (0.9 if k % 2 == 0 else 0.6))),
                           settings.grid_width if k % 2 == 0 else max(0.5, settings.grid_width * 0.6))
            # Draw the arc as a quadratic bezier VP_L → mid_pt → VP_R
            ctrl = QPointF(cx, arc_y - (arc_y - horizon_y) * 0.5 * curvature)
            path = QPainterPath(VP_L)
            path.quadTo(ctrl, VP_R)
            painter.setPen(arc_pen)
            painter.drawPath(path)

    # ------------------------------------------------------------------
    def draw_coordinate_gizmo(self, painter, camera, origin_x=45, origin_y=45, size=28):
        """Draws small XYZ axis orientation gizmo in corner."""
        _, view_mat, _ = camera.get_matrices(100, 100)

        vx = view_mat * QVector4D(1, 0, 0, 0)
        vy = view_mat * QVector4D(0, 1, 0, 0)
        vz = view_mat * QVector4D(0, 0, 1, 0)

        axes = [
            (vx, QColor(239, 68, 68),  "X"),
            (vy, QColor(34, 197, 94),  "Y"),
            (vz, QColor(59, 130, 246), "Z"),
        ]
        axes.sort(key=lambda item: item[0].z())

        painter.save()
        painter.setRenderHint(QPainter.Antialiasing, True)

        painter.setBrush(QBrush(QColor(15, 18, 25, 180)))
        painter.setPen(QPen(QColor(50, 56, 70), 1))
        painter.drawEllipse(origin_x - size - 2, origin_y - size - 2,
                            (size + 2) * 2, (size + 2) * 2)

        for vec, color, label in axes:
            end_x = origin_x + vec.x() * size
            end_y = origin_y - vec.y() * size
            painter.setPen(QPen(color, 2, Qt.SolidLine, Qt.RoundCap))
            painter.drawLine(origin_x, origin_y, int(end_x), int(end_y))
            painter.setFont(QFont("Segoe UI", 7, QFont.Bold))
            painter.setPen(color)
            painter.drawText(int(end_x + (3 if vec.x() >= 0 else -9)),
                             int(end_y + (4 if vec.y() <= 0 else -2)),
                             label)

        painter.restore()
