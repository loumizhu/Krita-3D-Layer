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

        # Add all .py files from the package
        for root, dirs, files in os.walk(PACKAGE_DIR):
            # Skip __pycache__ directories
            dirs[:] = [d for d in dirs if d != "__pycache__"]

            for filename in sorted(files):
                filepath = os.path.join(root, filename)
                if should_exclude(filepath):
                    continue
                # Only include Python files
                if not filename.endswith(".py"):
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
