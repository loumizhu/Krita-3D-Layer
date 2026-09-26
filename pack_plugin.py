"""
pack_plugin.py — Package krita_3d_layer into a Krita-installable ZIP.

Krita expects a ZIP containing:
  krita_3d_layer/
      __init__.py
      ... (all .py files)
  krita_3d_layer.desktop

Usage:
  python pack_plugin.py

Output:
  krita_3d_layer.zip (in the same directory)
"""

import os
import zipfile

SOURCE_DIR = os.path.dirname(os.path.abspath(__file__))
PACKAGE_DIR = os.path.join(SOURCE_DIR, "krita_3d_layer")
DESKTOP_FILE = os.path.join(SOURCE_DIR, "krita_3d_layer.desktop")
OUTPUT_ZIP = os.path.join(SOURCE_DIR, "krita_3d_layer.zip")

EXCLUDE_PATTERNS = {"__pycache__", ".pyc", ".pyo"}


def should_exclude(path):
    for pattern in EXCLUDE_PATTERNS:
        if pattern in path:
            return True
    return False


def pack():
    print(f"Packing plugin into {OUTPUT_ZIP}...")

    with zipfile.ZipFile(OUTPUT_ZIP, "w", zipfile.ZIP_DEFLATED) as zf:
        # Add desktop file at root of zip
        zf.write(DESKTOP_FILE, "krita_3d_layer.desktop")
        print(f"  + krita_3d_layer.desktop")

        # Explicitly add the main module directory entry (required by Krita's PluginImporter)
        main_dir_info = zipfile.ZipInfo("krita_3d_layer/")
        main_dir_info.external_attr = 0o755 << 16 | 0x10
        zf.writestr(main_dir_info, "")
        print(f"  + krita_3d_layer/ (directory)")

        added_dirs = {"krita_3d_layer/"}

        # Add all .py files and assets from the package
        for root, dirs, files in os.walk(PACKAGE_DIR):
            # Skip __pycache__ directories
            dirs[:] = [d for d in dirs if d != "__pycache__"]

            for d in sorted(dirs):
                dir_path = os.path.join(root, d)
                rel_dir = os.path.relpath(dir_path, SOURCE_DIR).replace("\\", "/") + "/"
                if rel_dir not in added_dirs:
                    added_dirs.add(rel_dir)
                    dinfo = zipfile.ZipInfo(rel_dir)
                    dinfo.external_attr = 0o755 << 16 | 0x10
                    zf.writestr(dinfo, "")
                    print(f"  + {rel_dir} (directory)")

            for filename in sorted(files):
                filepath = os.path.join(root, filename)
                if should_exclude(filepath):
                    continue
                # Include Python files, Manual HTML, JSON configs, and 3D model assets (.obj, .stl, .glb, .gltf)
                ext = os.path.splitext(filename)[1].lower()
                if ext not in ('.py', '.obj', '.stl', '.glb', '.gltf', '.html', '.json'):
                    continue

                arcname = os.path.relpath(filepath, SOURCE_DIR)
                # Normalize to forward slashes for zip
                arcname = arcname.replace("\\", "/")
                zf.write(filepath, arcname)
                print(f"  + {arcname}")

    size_kb = os.path.getsize(OUTPUT_ZIP) / 1024
    print(f"\nDone! {OUTPUT_ZIP} ({size_kb:.1f} KB)")
    print("Install in Krita: Tools -> Scripts -> Import Python Plugin from File...")


if __name__ == "__main__":
    pack()
