# Krita-3D-Layer — AI Agent Technical Reference

> **Last updated:** 2026-09-26
> **Status:** Active MVP — functional, in daily use, under iterative development.
> **Platform:** Windows 10/11, Krita 5.3+ (Portable), Python 3.13 (Krita-embedded), PyQt5.

---

## 1. What This Project Is

A **Krita Python plugin** that adds an interactive 3D model viewer as a docker panel inside Krita. It lets artists import OBJ/STL meshes, rotate/zoom them in a real-time 3D viewport, and **stamp** the rendered result directly onto a Krita paint layer at full document resolution.

It is a **pure-software renderer** — no OpenGL, no GPU, no external 3D libraries. Everything is drawn via `QPainter` + `QMatrix4x4` + `QVector4D` perspective math using only PyQt5, which ships bundled inside Krita.

### Core Workflow
1. User opens Krita, opens/creates a canvas.
2. 3D Layer docker appears (docked right by default).
3. User imports an OBJ/STL mesh (or the Asaro Head loads by default).
4. User orbits, zooms, adjusts lighting, wireframe, FOV, etc. in the interactive viewport.
5. With **Live Sync** enabled (default), every camera/style change automatically renders the 3D model at full document resolution and writes it into a dedicated Krita paint layer called `"3D Model Reference"`.
6. User draws over the reference on separate layers.

---

## 2. Project File Map

```
Krita-3D-Layer/
├── install.py                          # Installer: copies to pykrita, enables in kritarc, live-injects via named pipe
├── krita_3d_layer.desktop              # Krita plugin registration (ServiceTypes=Krita/PythonPlugin)
├── AI AGENTS Read Me.md                # THIS FILE — comprehensive technical reference
│
└── krita_3d_layer/                     # Python package (the actual plugin)
    ├── __init__.py                     # Plugin entry point: registers DockWidgetFactory + Extension with Krita
    ├── docker.py                       # Krita3DLayerDocker (DockWidget) — all UI, collapsible sections, controls
    ├── viewport.py                     # Viewport3D (QWidget) — interactive 3D viewport, mouse orbit/pan/zoom/FOV
    ├── renderer.py                     # Software 3D rendering engine: Camera3D, Lighting3D, Renderer3D
    ├── mesh_loader.py                  # OBJ/STL parser → MeshData (vertices, faces, normals, normalization)
    ├── canvas_sync.py                  # CanvasSyncManager — renders to QImage → writes pixel data to Krita layers
    ├── widgets.py                      # Custom widgets: CollapsibleSection, SphereLightWidget (3D light sphere)
    └── extension.py                    # Krita3DLayerExtension — registers "Open 3D Model Viewer..." menu action
```

---

## 3. Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                   Krita Application                          │
│  ┌───────────────────────────────────────────────────────┐  │
│  │         Krita3DLayerDocker (docker.py)                 │  │
│  │  ┌─────────────────────────────────────────────────┐  │  │
│  │  │  Viewport3D (viewport.py)                        │  │  │
│  │  │  - Mouse events → Camera3D / Lighting3D          │  │  │
│  │  │  - paintEvent → Renderer3D.render_scene()        │  │  │
│  │  │  - wheelEvent → FOV change (not docker scroll)   │  │  │
│  │  └─────────────────────────────────────────────────┘  │  │
│  │  ┌──────────────┐  ┌──────────────────────────────┐  │  │
│  │  │ Collapsible   │  │ SphereLightWidget            │  │  │
│  │  │ Sections      │  │ (interactive 3D light arrow) │  │  │
│  │  └──────────────┘  └──────────────────────────────┘  │  │
│  └───────────────────────────────────────────────────────┘  │
│                           │                                  │
│                    Live Sync / Stamp                          │
│                           ▼                                  │
│  ┌───────────────────────────────────────────────────────┐  │
│  │  CanvasSyncManager (canvas_sync.py)                    │  │
│  │  render_to_krita_layer() → QImage → setPixelData()    │  │
│  └───────────────────────────────────────────────────────┘  │
│                           ▼                                  │
│              Krita Document Paint Layer                       │
└─────────────────────────────────────────────────────────────┘
```

### Rendering Pipeline (per frame)

1. **Vertex Projection** — Each vertex is multiplied by the 4×4 MVP matrix (`proj * view * model`) as a homogeneous `QVector4D(x, y, z, 1.0)`. Manual W-divide produces NDC coordinates. NDC is mapped to a **square pixel region** centered in the viewport to prevent aspect-ratio distortion.

2. **Backface Culling** — 2D cross product of screen-space triangle edges. Because Qt screen Y is flipped (down = +Y), the winding test is inverted: `cross2d >= 0.0` = back-facing. Wireframe mode has its own independent `wireframe_backface_culling` flag.

3. **Lighting** — Dual studio lights (key + fill) computed via Lambertian dot product against face normals. Key light follows the camera by default (studio rig behavior). Ambient + diffuse + fill intensity are all adjustable.

4. **Depth Sort** — Painter's algorithm: faces sorted by average NDC Z (farthest first), drawn back-to-front.

5. **Silhouette Contour** — Edge-face adjacency map (cached on `mesh._edge_faces_cache`). Silhouette edges are boundary edges or edges where one adjacent face is front-facing and the other is back-facing.

---

## 4. Key Classes & Their Properties

### `Camera3D` (renderer.py)
| Property | Type | Default | Description |
|---|---|---|---|
| `yaw` | float | 145.0 | Horizontal orbit angle (degrees, 0-360) |
| `pitch` | float | 12.0 | Vertical orbit angle (degrees, -89.9 to 89.9) |
| `roll` | float | 0.0 | Camera roll (degrees, -180 to 180) |
| `distance` | float | 2.4 | Distance from camera to target |
| `pan_x`, `pan_y` | float | 0.0 | Screen-space panning offset |
| `fov` | float | 45.0 | Field of view (degrees, 5-120) |
| `orthographic` | bool | False | True = parallel projection, False = perspective |
| `near_clip` | float | 0.01 | Near clipping plane distance |
| `far_clip` | float | 200.0 | Far clipping plane distance |
| `target_x/y/z` | float | 0.0 | World-space look-at target coordinates |

Camera uses spherical coordinates to orbit around `target`. Eye position = `target + spherical(yaw, pitch, distance)`.

Preset methods: `set_front()`, `set_side_right()`, `set_side_left()`, `set_top()`, `set_bottom()`, `set_three_quarter()`, `reset()`.

### `Lighting3D` (renderer.py)
| Property | Type | Default | Description |
|---|---|---|---|
| `azimuth` | float | 45.0 | Key light horizontal angle |
| `elevation` | float | 40.0 | Key light vertical angle |
| `ambient` | float | 0.35 | Ambient light intensity (0-1) |
| `diffuse` | float | 0.65 | Key light diffuse intensity (0-1) |
| `fill_intensity` | float | 0.25 | Fill light intensity (0-1) |
| `follow_camera` | bool | True | Light rotates with camera (studio rig) |

### `Renderer3D` (renderer.py)
| Property | Type | Default | Description |
|---|---|---|---|
| `base_color` | QColor | (235,232,225) | Model surface color (classical plaster white) |
| `wire_color` | QColor | (50,52,60,140) | Wireframe line color |
| `wire_width` | float | 1.0 | Wireframe stroke width (px) |
| `contour_color` | QColor | (30,30,35) | Silhouette outline color |
| `contour_width` | float | 0.0 | Silhouette outline width (0 = off) |
| `backface_culling` | bool | True | Cull back-facing triangles in shaded modes |
| `wireframe_backface_culling` | bool | True | Cull back-facing triangles in wireframe mode |

### `RenderStyle` (renderer.py)
- `SHADED` = `"Shaded Planes"` — flat-shaded faces, no wireframe
- `SHADED_WIREFRAME` = `"Shaded + Wireframe"` — faces + wireframe overlay
- `WIREFRAME` = `"Wireframe Only"` — edges only, no fill
- `SILHOUETTE` = `"Silhouette Mask"` — flat base_color fill, no shading
- `NORMAL_MAP` = `"Normal Map Colors"` — face normals encoded as RGB

### `MeshData` (mesh_loader.py)
| Property | Type | Description |
|---|---|---|
| `vertices` | list[QVector3D] | Normalized vertices (centered, unit-sphere scaled) |
| `original_vertices` | list[(x,y,z)] | Raw parsed vertex coordinates |
| `faces` | list[(v0,v1,v2)] | Triangle face indices |
| `face_normals` | list[QVector3D] | Per-face normals (computed from edge cross product) |
| `center` | QVector3D | Original bounding box center (pre-normalization) |
| `bbox_min/max` | QVector3D | Bounding box corners |
| `radius` | float | Bounding sphere radius (pre-normalization) |
| `scale` | float | Normalization scale factor |

All meshes are **centered and normalized to a unit bounding sphere** upon loading. This means `vertices` are in the range `[-1, 1]` approximately. The camera defaults (`distance=2.4`, `fov=45°`) are tuned to frame this normalized unit sphere.

### `Viewport3D` (viewport.py)
Interactive `QWidget` embedded in the docker. Handles all mouse interaction:

| Action | Mouse Control |
|---|---|
| **Orbit** | Left-click drag |
| **Pan** | Middle-click drag / Alt+Left drag |
| **Zoom (distance)** | Right-click drag / Ctrl+Left drag |
| **FOV (focal length)** | Scroll wheel over viewport |
| **Light direction** | Shift+Left or Shift+Right drag |

**Camera Modes** (selectable via dropdown):
- `Orbit Around Object` — standard turntable, model follows mouse
- `First Person (Look Around)` — camera stays in place, view direction rotates (inverted controls)
- `Turntable (Locked Up)` — same as orbit, but named explicitly for clarity

The viewport emits `camera_changed` and `interaction_ended` signals. The docker connects `interaction_ended` to trigger canvas sync when Live Sync is enabled.

**Critical behavior:** `wheelEvent` calls `event.accept()` to prevent scroll propagation to the parent `QScrollArea`. This ensures scrolling over the viewport changes FOV, not the docker scroll position.

### `Krita3DLayerDocker` (docker.py)
The main DockWidget. Sections (all collapsible):

1. **3D VIEWPORT** — embedded Viewport3D + camera preset buttons
2. **CANVAS SYNC** — Stamp button, Live Sync toggle (ON by default), layer mode dropdown
3. **CAMERA** — Camera mode, Perspective/Ortho, FOV slider + lens presets, distance, roll, target XYZ coordinates, center-on-model
4. **CLIPPING** — Near/Far clip plane sliders (collapsed by default)
5. **STYLE** — Render style dropdown, wireframe backface culling toggle, wire/contour thickness+color, base color, transparent background
6. **LIGHTING** — SphereLightWidget (interactive 3D sphere with directional arrow), Follow Camera toggle, Ambient/Key intensity sliders
7. **MODEL** — Import button, quick-load Asaro Head (collapsed by default)

**Scripting API:**
```python
d = Krita3DLayerDocker.instance()   # singleton accessor
d.viewport.camera.fov = 85
d.viewport.camera.yaw = 90
d.viewport.renderer.wire_width = 2.5
d.viewport.update()
d._stamp()                          # force render to canvas
```

### `CanvasSyncManager` (canvas_sync.py)
Static utility class. `render_to_krita_layer()` renders the full 3D scene at document resolution into a `QImage`, converts to ARGB32 byte buffer, and writes it to a Krita paint layer via `node.setPixelData()`.

Layer modes:
- `"named"` — finds or creates a layer called `"3D Model Reference"` (default)
- `"new"` — always creates a fresh layer
- `"active"` — overwrites the currently selected layer

### `CollapsibleSection` (widgets.py)
Custom `QWidget` with a `QPushButton` header (▼/▶ arrow + title). Clicking toggles visibility of the content frame. Emits `toggled(bool)`.

### `SphereLightWidget` (widgets.py)
Custom `QWidget` rendering a 3D-shaded sphere with a directional arrow indicating light direction. Dragging on the sphere adjusts `azimuth` and `elevation`. Double-click resets to defaults (45°, 40°). Emits `light_changed(float, float)` and `interaction_ended()`.

---

## 5. Installation & Deployment

### Paths (Windows)
| Path | Purpose |
|---|---|
| `E:\((_atWork_))\Krita-3D-Layer\` | Source code (development) |
| `%APPDATA%\krita\pykrita\krita_3d_layer\` | Installed plugin location (Krita reads from here) |
| `%APPDATA%\krita\pykrita\krita_3d_layer.desktop` | Plugin registration file |
| `%LOCALAPPDATA%\kritarc` | Krita config; `[python]` section has `enable_krita_3d_layer=true` |
| `C:\portable_apps\Krita-5.3-Portable\` | Krita portable installation |

### Install Command
```bash
python "E:\((_atWork_))\Krita-3D-Layer\install.py"
```

This script does three things:
1. **Copies** (not symlinks — `WinError 1314` on non-admin) the `krita_3d_layer/` package + `.desktop` file into `%APPDATA%\krita\pykrita\`.
2. **Enables** the plugin in `kritarc` (`enable_krita_3d_layer=true`).
3. **Live-injects** via the named pipe `\\.\pipe\runscriptz_socket` (if available) to hot-reload modules in the running Krita instance.

> **IMPORTANT:** After modifying any source file, you MUST run `install.py` again. The files are **copied**, not symlinked. Changes to source files are NOT automatically reflected in Krita.

### Live Reload Mechanism
The named pipe `\\.\pipe\runscriptz_socket` is provided by a separate Krita plugin (`runscriptz`). When available, `install.py` writes a bootstrap script path to it, which Krita executes internally. The bootstrap uses `importlib.reload()` on all modules in dependency order:
1. `krita_3d_layer` (init)
2. `krita_3d_layer.widgets`
3. `krita_3d_layer.docker`
4. `krita_3d_layer.viewport`
5. `krita_3d_layer.mesh_loader`
6. `krita_3d_layer.renderer`
7. `krita_3d_layer.canvas_sync`

If the pipe is unavailable, Krita must be restarted to pick up changes.

---

## 6. Technical Constraints & Gotchas

### No OpenGL / No GPU
Krita's Python environment does not expose OpenGL contexts. The entire renderer is **CPU-based QPainter operations**. Performance is adequate for meshes up to ~50k faces at viewport sizes under 800×800. Very high-poly meshes will be slow.

### Perspective W-Divide
Early versions used `QMatrix4x4.map(QVector3D)` which performs an implicit W=1 mapping but **does not divide by W**, producing incorrect orthographic-like projection. The fix: multiply as `mvp * QVector4D(x, y, z, 1.0)`, then manually divide `x/w, y/w, z/w`.

### Screen Y Flip
Qt's screen coordinate system has Y increasing downward. This inverts the winding order of projected triangles. Backface culling tests use `cross2d >= 0.0` (rather than `<= 0.0`) for this reason. Camera orbit pitch direction is also inverted accordingly.

### Square Rendering Region
The renderer uses `min(width, height)` as the render size, centered within the viewport. This prevents aspect-ratio distortion when the docker is resized to non-square dimensions.

### Mesh Normalization
All loaded meshes are centered at origin and scaled to fit within a unit bounding sphere (radius = 1.0). The camera's default distance (2.4) and FOV (45°) are calibrated for this normalized scale. If you need the original coordinates, they are preserved in `mesh.original_vertices`.

### Edge-Face Cache
Silhouette contour rendering builds an edge→face adjacency dictionary. This is cached on `mesh._edge_faces_cache` to avoid recomputing every frame.

### Docker Width
The UI is fully fluid with no fixed widths or minimum widths on controls. All font sizes are 10px. Buttons use `padding: 2px 3px`. The viewport has a minimum size of 60×60. The docker should work at any width without clipping.

---

## 7. Dependencies

**Zero external dependencies.** The plugin uses only:
- `PyQt5` (bundled with Krita) — `QtGui`, `QtWidgets`, `QtCore`
- `krita` module (Krita's Python API) — `Krita`, `DockWidget`, `DockWidgetFactory`, `Extension`
- Python stdlib — `math`, `os`, `struct`

No `numpy`, no `PIL`, no `trimesh`, no `moderngl`. Nothing needs to be `pip install`ed.

---

## 8. Supported 3D Formats

| Format | Parser | Notes |
|---|---|---|
| `.obj` (Wavefront) | `load_obj()` | Reads `v` (vertices), `vn` (normals), `f` (faces). Handles `v/vt/vn` face syntax. Polygons auto-triangulated via fan triangulation. 1-based and negative indexing supported. |
| `.stl` (Stereolithography) | `load_stl()` | Auto-detects binary vs ASCII. Binary: reads 50-byte triangle records. ASCII: parses `vertex` lines. Vertex deduplication via rounded-tuple hashing. |

Materials, textures, UV coordinates, and vertex colors are **not** loaded or rendered.

---

## 9. Scripting & Programmatic Access

The docker exposes a singleton accessor:

```python
from krita_3d_layer.docker import Krita3DLayerDocker

docker = Krita3DLayerDocker.instance()

# Camera control
docker.viewport.camera.yaw = 180.0
docker.viewport.camera.pitch = 0.0
docker.viewport.camera.fov = 85.0
docker.viewport.camera.distance = 3.0
docker.viewport.camera.orthographic = False
docker.viewport.camera.target_x = 0.0
docker.viewport.camera.target_y = 0.5
docker.viewport.camera.near_clip = 0.01
docker.viewport.camera.far_clip = 200.0

# Lighting
docker.viewport.lighting.azimuth = 60.0
docker.viewport.lighting.elevation = 30.0
docker.viewport.lighting.ambient = 0.4
docker.viewport.lighting.diffuse = 0.7

# Renderer
docker.viewport.renderer.wire_width = 2.0
docker.viewport.renderer.contour_width = 3.0
docker.viewport.renderer.base_color = QColor(200, 180, 160)
docker.viewport.renderer.wireframe_backface_culling = True

# Force render
docker.viewport.update()       # Refresh viewport
docker._stamp()                # Write to Krita canvas layer

# Load a different mesh
docker._load(r"C:\path\to\model.obj")
```

All properties are plain Python attributes — no getters/setters magic. Changes take effect on the next `viewport.update()` call.

---

## 10. Known Limitations & Future Work

| Limitation | Detail |
|---|---|
| **CPU-only renderer** | No GPU acceleration. Large meshes (>100k faces) will be slow. |
| **No smooth shading** | Flat-shaded faces only (per-face normals). Gouraud/Phong interpolation not implemented. |
| **No textures** | UV mapping and texture loading are not supported. |
| **No materials** | MTL files are ignored. Single base color for entire mesh. |
| **Painter's algorithm** | Depth sort by average Z can produce artifacts on intersecting or large triangles. No z-buffer. |
| **Triangle fan triangulation** | Concave polygons may triangulate incorrectly. |
| **Windows only** | Install script uses `%APPDATA%`, `%LOCALAPPDATA%`, Windows named pipes. |
| **Copy-based install** | No symlinks on non-admin Windows. Must re-run `install.py` after every source change. |

### Potential Improvements
- Vertex normal interpolation for smooth shading
- OBJ material/MTL support
- FBX/glTF loader (would require external library)
- GPU-accelerated rendering via QOpenGLWidget
- Multiple mesh/object support
- Animation keyframes for camera path
- Transparent mesh sorting (order-independent transparency)
