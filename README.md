# Krita 3D Layer 🗿🎨

**Drop 3D references right into your Krita canvas. No setup, no hassle.**

Ever wished you could just plop a 3D model into Krita, spin it around, and paint over it? That's exactly what this plugin does. Load an OBJ or STL, orbit it, tweak the lighting, and stamp it directly onto a paint layer — all without leaving Krita.

It ships with a built-in **Asaro Head** so you can start studying planes and values the second you install it.

<!-- ![3D Layer Demo](media/demo_preview.png) -->

---

## 🎬 Video Showcase

<!-- Add your video link or embed below -->
> 🎥 **Walkthrough video coming right up!**
> 
> *(A quick video showing how fast you can position models, tweak lights, and stamp them to your canvas will be posted here soon.)*

---

## ✨ What You Get

- **3D viewport right inside Krita** — orbit, pan, zoom, adjust FOV, all with your mouse
- **Stamp to canvas** — renders the 3D view at full document resolution onto a Krita layer with transparency
- **Live Sync** — move the camera, the canvas layer updates automatically when you release
- **Multiple render styles** — Shaded Planes, Wireframe, Shaded + Wireframe, Silhouette Mask, Normal Map
- **Studio lighting** — dual key + fill lights, draggable light direction sphere, follow-camera mode
- **OBJ & STL support** — load any standard mesh. Quads, tris, binary/ASCII STL, all handled
- **Camera presets** — Front, Side, 3/4, Top — one click each
- **Perspective & Ortho** — switch projection modes, adjust FOV with scroll wheel or lens presets
- **Zero dependencies** — runs on Krita's built-in PyQt5. No pip, no DLLs, no GPU required
- **100% Free** — free for all Krita artists, forever

---

## 📦 Installation

### Option A — From the ZIP (Recommended & Easiest)

1. Download **`krita_3d_layer.zip`** from the [Releases](https://github.com/loumizhu/Krita-3D-Layer/releases) section (or grab it directly from this repo).
2. Launch Krita.
3. In the top menu, go to **Tools → Scripts → Import Python Plugin from File...**
4. Choose the downloaded `krita_3d_layer.zip`.
5. Restart Krita.
6. Make sure it's enabled: **Settings → Configure Krita → Python Plugin Manager → ✅ Krita 3D Layer**.
7. Open the panel: **Settings → Dockers → 3D Layer & Viewport**.

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

Free to use. Made for artists, by artists (with a little help from AI).

---

<p align="center">
  <b>Krita 3D Layer</b> — because your 2D workflow deserves 3D superpowers 🚀
</p>
