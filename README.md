# Krita 3D Layer 

**Drop 3D references right into your Krita canvas. No setup, no hassle.**

Ever wished you could just plop a 3D model into Krita, spin it around, and paint over it? That's exactly what this plugin does. Load an OBJ/GLB/OBJ, orbit it, tweak the lighting, and stamp it directly onto a paint layer — all without leaving Krita.
You can quickly have a perspective grid ready to draw.
It ships with a built-in **Asaro Head** so you can start studying planes and values the second you install it.

<!-- ![3D Layer Demo](media/demo_preview.png) -->

---

## 🎬 Video Showcase

<!-- Add your video link or embed below -->
> 🎥 **video demo**
> 
> *(A quick video showing how fast you can position models, tweak lights, and stamp them to your canvas will be posted here soon.)*

---

## ✨ What You Get

- **3D viewport right inside Krita** — orbit, pan, zoom, adjust FOV, all with your mouse
- **Interactive Gizmo & Scrub Labels** — click 3D axis gizmo to snap views (X/Y/Z) or drag Y/P/D/F labels to scrub camera angles

- **Multiple Perspective Modes** — Standard 3-Point, Fisheye / 5-Point Curvilinear, and Artist 5-Vanishing-Point arc modes
- **Live Sync** — move the camera, the canvas layer updates automatically when you release
- **Multiple render styles** — Shaded Planes, Wireframe, Shaded + Wireframe, Silhouette Mask, Normal Map
- **Studio lighting** — dual key + fill lights, draggable light direction sphere, follow-camera mode
- **OBJ, STL & GLB/glTF support** — load standard 3D meshes and embedded GLB/glTF models
- **Built-in 3D Primitives** — Asaro Head, primitive boxes, spheres, cylinders, ellipses, and ground grids included
- **Full Session Persistence & Presets** — automatically preserves viewport size, camera state, and parameters across sessions
- **100% Free & Cross-Platform** — works identically on Windows, Linux, and macOS

---

## 📦 Installation

### Option A — From the ZIP (Recommended & Easiest — All Platforms)

1. Download **`krita_3d_layer.zip`** from this repository or the Releases section.
2. Launch Krita.
3. In the top menu, go to **Tools → Scripts → Import Python Plugin from File...**
4. Choose the downloaded `krita_3d_layer.zip`.
5. Restart Krita.
6. Enable the plugin under **Settings → Configure Krita → Python Plugin Manager → ✅ Krita 3D Layer**.
7. Open the panel: **Settings → Dockers → 3D Layer**.

> 💡 **Built-in Manual:** In **Settings → Configure Krita → Python Plugin Manager**, select **Krita 3D Layer** and click the **Manual** button to open the full illustrated user guide! You can also click the **❓ Manual** button directly in the docker toolbar.

### Option B — Manual Install (from source)

1. Clone this repository:
   ```bash
   git clone https://github.com/loumizhu/Krita-3D-Layer.git
   ```
2. Copy `krita_3d_layer/` and `krita_3d_layer.desktop` into your Krita `pykrita` directory:
   - **Windows:** `%APPDATA%\krita\pykrita\`
   - **Linux:** `~/.local/share/krita/pykrita/`
   - **macOS:** `~/Library/Application Support/krita/pykrita/`
3. Restart Krita and enable the plugin under **Settings → Configure Krita → Python Plugin Manager**.

---

## 🌍 Multi-Platform Compatibility

**Krita 3D Layer is 100% Cross-Platform (Windows, Linux, and macOS).**
- Built on standard Python 3 and PyQt5 bundled inside Krita on all platforms.
- Completely self-contained software 3D rasterizer with zero native C++/Win32 dependencies, DLLs, or GPU requirements.
- Works identically across Windows, Linux distributions, and macOS.

---

## 💾 Where Parameters & Presets Are Saved

- **Custom Presets:** When you click **💾 Save...** in the Presets section, all camera angles (yaw, pitch, roll, tilt), FOV, projection mode, fisheye curvature, perspective grids, ceiling height, horizon, and studio lighting are saved to a standard JSON file:
  - **Windows:** `%APPDATA%\krita\krita_3d_layer_presets.json`
  - **Linux:** `~/.local/share/krita/krita_3d_layer_presets.json`
  - **macOS:** `~/Library/Application Support/krita/krita_3d_layer_presets.json`
- **Instant Automatic Loading:** Selecting any preset in the dropdown immediately loads and synchronizes all viewport parameters and canvas stamping.

---

## 🚀 Quick Start

1. Open Krita and create or open a document
2. Open the docker: **Settings → Dockers → 3D Layer & Viewport**
3. Click **🗿 Asaro Head** to load the built-in reference model (or **📁 Import Model** for your own)
4. Drag in the viewport to orbit • Middle-click to pan • Scroll to adjust FOV
5. Hit **🎨 Stamp** to render the 3D view onto your canvas — or turn on **Live Sync** and it updates as you go

That's it. Paint over it on a layer above, study planes, block shapes, trace wireframes — whatever your workflow needs.

---

## 🖼️ Render Styles

| Style | What it does |
|---|---|
| **Shaded Planes** | Clean planar shading — great for value studies |
| **Shaded + Wireframe** | Shaded faces with ink contours overlaid |
| **Wireframe Only** | Edges only on transparent background — perfect for tracing |
| **Silhouette Mask** | Flat solid shape — use it for silhouette blocking |
| **Normal Map** | RGB normal visualization |

---

## 🤝 Contributing

Found a bug? Got an idea? Open an issue or PR — this is a free community plugin and all contributions are welcome.

---

## 📄 License

Free to use. Made for artists, by artists (with AI coding).

---

<p align="center">
  <b>Krita 3D Layer</b> — because your 2D workflow deserves 3D superpowers 🚀
</p>
