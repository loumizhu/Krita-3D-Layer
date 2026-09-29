# Krita 3D Layer

A simple 3D reference docker for Krita. Load a 3D model, rotate it to the angle you need, adjust the light, and stamp it directly onto a paint layer.

I built this because jumping back and forth between Krita and external 3D software just to check head angles, proportions, or lighting got tedious. With this plugin, you can keep your reference models and perspective grids right inside Krita alongside your brushes.

It includes a built-in **Asaro Head** for plane and portrait studies, basic primitives (boxes, cylinders, spheres), and custom ground/ceiling perspective grids.

---

## Video Demo

[![Krita 3D Layer Video Demo](https://img.youtube.com/vi/qMYg-C_WqQc/maxresdefault.jpg)](https://youtu.be/qMYg-C_WqQc)

Watch the short walkthrough on YouTube: [https://youtu.be/qMYg-C_WqQc](https://youtu.be/qMYg-C_WqQc)

---

## Features

- **Docked 3D Viewport:** Orbit, pan, zoom, and tweak FOV directly from the docker panel. Includes custom gradient or solid studio backgrounds, compact centered orbit target pivot toggle, and complete display customization.
- **Quick Actions Toolbar:** Responsive mini toolbar directly below the viewport featuring an auto-wrapping flow layout that never clips buttons on narrow docker sizes. Offers fast one-click access to tools, lens presets, view angles, primitives, and sync toggles with custom colors, icons, and preset configurations.
- **Ground Calibrator & Perspective Matching:**
  - **4-Point Ground Draw:** Match your 3D camera to any sketch or photo by pinning 4 corners on a ground plane to solve Yaw, Tilt, Roll, FOV, and distance.
  - **5-Point Ground + Height:** Pin 4 corners for the base plus a 5th point to define vertical height and object scale in perspective simultaneously.
  - **Interactive Horizon Line:** Grab and drag the horizon line directly on-screen to smoothly adjust camera eye-level tilt (pitch) in real time.
  - **On-Screen Transform Gizmo & Modifiers:** Move (✥), Rotate (⟳), and Scale (⤢) the ground quad right inside the canvas preview. Supports intuitive shortcut modifiers:
    - *Drag inside quad:* Move / Translate
    - *Shift + Drag:* Proportional Scale
    - *Ctrl / Alt + Drag:* Rotate around center
  - **Aspect Ratio Presets:** Lock proportions to 1:1:1 Cube, 1:2:1 Standing Block, 1:3:1 Character, 2:1:3 Interior Room, 4:1:4 Wide Stage, or Freeform.
  - **History Dropdown:** Quickly recall recently placed primitives and camera setups with dimensions and timestamps.
- **Base Pivot & Bottom-Up Height:** Primitives (boxes, cylinders, pyramids, cones, spheres, planes) rest cleanly on the ground plane at $Y = 0.0$; height adjustments extrude upwards from the base without shifting position.
- **Canvas Stamping & Live Sync:** Press Stamp to place the render onto a new paint layer, or leave Live Sync on so your active layer updates automatically whenever you move the camera.
- **Render Modes:** Shaded planes, wireframe only (with quad detection to hide internal diagonal tris), shaded + wireframe, flat silhouette mask, and normal maps.
- **Built-in Reference Models:** Asaro head bust, mannequin head, boxes, spheres, cylinders, and grids ready to use without importing files.
- **File Support:** Loads standard `.obj`, `.glb` / `.gltf`, and `.stl` files.
- **Custom Lighting:** Key and fill lights with an interactive direction ball and an optional "follow camera" toggle.
- **Perspective Grids:** Ground tiles, ceiling grid, and an eye-level horizon line. Supports standard linear perspective, 5-point curvilinear, and fisheye lens distortion.
- **Cross-Platform:** Pure Python and PyQt5 (already bundled with Krita). Works on Windows, Linux, and macOS without extra drivers or installs.

---

## Installation

### Method 1: Direct from Web (Easiest)

1. Open Krita.
2. In the menu, go to **Tools → Scripts → Import Python Plugin from Web...**
3. Paste the repository URL:
   ```text
   https://github.com/loumizhu/Krita-3D-Layer
   ```
4. Click **OK** to let Krita download and extract it.
5. Restart Krita.
6. Enable the plugin in **Settings → Configure Krita → Python Plugin Manager → Krita 3D Layer**.
7. Open the docker: **Settings → Dockers → 3D Layer**.

---

### Method 2: From ZIP File

1. Download **`krita_3d_layer.zip`** from the [Releases](https://github.com/loumizhu/Krita-3D-Layer/releases) page.
2. In Krita, go to **Tools → Scripts → Import Python Plugin from File...**
3. Select the zip file.
4. Restart Krita, enable it in **Python Plugin Manager**, and open the docker from **Settings → Dockers → 3D Layer**.

---

### Method 3: Manual Install (From Source)

1. Clone or download this repo:
   ```bash
   git clone https://github.com/loumizhu/Krita-3D-Layer.git
   ```
2. Copy the `krita_3d_layer/` folder and `krita_3d_layer.desktop` file into your Krita `pykrita` directory:
   - **Windows:** `%APPDATA%\krita\pykrita\`
   - **Linux:** `~/.local/share/krita/pykrita/`
   - **macOS:** `~/Library/Application Support/krita/pykrita/`
3. Restart Krita and enable the plugin in **Settings → Configure Krita → Python Plugin Manager**.

---

## Quick Start

1. Create a canvas in Krita.
2. Open the docker (**Settings → Dockers → 3D Layer**).
3. Click **Asaro Head** (or click **Import 3D** to open your own model).
4. Use mouse navigation in the viewport:
   - **Left click + drag:** Orbit around the model
   - **Middle click (or Alt + left drag):** Pan
   - **Right click + drag (or Ctrl + left drag):** Zoom distance
   - **Mouse scroll:** Field of view (focal length)
   - **Shift + left drag:** Rotate the key light
5. Click **Stamp** to drop the current view onto a layer in your layer stack. Create a layer above it and start painting.

---

## Ground Perspective Matching & Primitive Drawing

1. Click **📐 Ground Rect** (or **📍 Ground 5P (H)**) in the docker or Quick Actions toolbar.
2. In the interactive calibrator window:
   - Click **✏️ Draw Rect** to drag an outline, or click **📍 4-Point Draw** to click 4 corners directly on your canvas sketch.
   - For vertical height, use **📍 5-Point Draw** (click 4 base corners + 1 height point).
   - Grab the yellow **Horizon Line** and drag up or down to align the camera's eye-level tilt.
   - Use the **Center Gizmo** or canvas shortcuts (Shift+Drag to scale, Ctrl+Drag to rotate) to position the ground quad.
3. Choose your object: align your **Loaded 3D Model** or create a 3D primitive (**Box**, **Cylinder**, **Sphere**, **Pyramid**, **Cone**, **Plane**).
4. Click **✔ Place Model on Ground & Apply** to instantly orient the camera and place the object resting directly on your artwork's perspective plane.

---

## Render Styles

| Style | Purpose |
|---|---|
| **Shaded Planes** | Flat shaded faces, helpful for values and shadow mapping |
| **Shaded + Wireframe** | Shading with ink line overlay |
| **Wireframe Only** | Clean outlines on a transparent layer, ideal for tracing |
| **Silhouette Mask** | Solid shape fill for checking silhouettes and thumbnails |
| **Normal Map** | Color-coded surface angles (RGB) |

---

## Saving Presets

When you set up an angle or grid you like, click **Save...** under Presets to give it a name. Presets are saved locally as standard JSON in your Krita settings directory:
- **Windows:** `%APPDATA%\krita\krita_3d_layer_presets.json`
- **Linux:** `~/.local/share/krita/krita_3d_layer_presets.json`
- **macOS:** `~/Library/Application Support/krita/krita_3d_layer_presets.json`

---

## Feedback & Issues

If something looks off or crashes, please open an issue on the GitHub repository with your Krita version and OS. Pull requests and feature suggestions are always welcome.

---

## License

MIT License. Free to use for personal, educational, and commercial artwork.
