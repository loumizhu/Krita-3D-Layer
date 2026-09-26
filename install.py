"""
install.py - Automatic Installer & Live Injector for Krita-3D-Layer.
1. Installs plugin into %APPDATA%/krita/pykrita/
2. Enables plugin in kritarc configuration
3. Injects and activates plugin in the currently running Krita instance
"""

import os
import sys
import shutil
import configparser

SOURCE_DIR = os.path.dirname(os.path.abspath(__file__))
PACKAGE_SRC = os.path.join(SOURCE_DIR, "krita_3d_layer")
DESKTOP_SRC = os.path.join(SOURCE_DIR, "krita_3d_layer.desktop")

if sys.platform == "win32":
    PYKRITA_DIR = os.path.expandvars(r"%APPDATA%\krita\pykrita")
    KRITARC_PATH = os.path.expandvars(r"%LOCALAPPDATA%\kritarc")
elif sys.platform == "darwin":
    PYKRITA_DIR = os.path.expanduser("~/Library/Application Support/krita/pykrita")
    KRITARC_PATH = os.path.expanduser("~/Library/Preferences/kritarc")
else:  # Linux / Unix
    PYKRITA_DIR = os.path.expanduser("~/.local/share/krita/pykrita")
    KRITARC_PATH = os.path.expanduser("~/.config/kritarc")

PACKAGE_DEST = os.path.join(PYKRITA_DIR, "krita_3d_layer")
DESKTOP_DEST = os.path.join(PYKRITA_DIR, "krita_3d_layer.desktop")



def install_files():
    print(f"[1/3] Installing files into {PYKRITA_DIR}...")
    os.makedirs(PYKRITA_DIR, exist_ok=True)

    # 1. Desktop file
    shutil.copy2(DESKTOP_SRC, DESKTOP_DEST)
    print(f"  -> Copied {DESKTOP_SRC} to {DESKTOP_DEST}")

    # 2. Package directory (use Junction or copy)
    if os.path.exists(PACKAGE_DEST):
        if os.path.islink(PACKAGE_DEST) or os.path.isdir(PACKAGE_DEST):
            try:
                if os.path.islink(PACKAGE_DEST):
                    os.unlink(PACKAGE_DEST)
                else:
                    shutil.rmtree(PACKAGE_DEST)
            except Exception as e:
                print(f"  Warning removing existing destination: {e}")

    try:
        # Create directory junction / symlink on Windows
        os.symlink(PACKAGE_SRC, PACKAGE_DEST, target_is_directory=True)
        print(f"  -> Created junction/symlink: {PACKAGE_DEST} -> {PACKAGE_SRC}")
    except Exception as e:
        print(f"  -> Symlink not permitted, copying directory: {e}")
        shutil.copytree(PACKAGE_SRC, PACKAGE_DEST)
        print(f"  -> Copied {PACKAGE_SRC} to {PACKAGE_DEST}")


def enable_in_kritarc():
    print(f"[2/3] Updating {KRITARC_PATH}...")
    if not os.path.exists(KRITARC_PATH):
        print(f"  Warning: {KRITARC_PATH} not found.")
        return

    # Read kritarc preserving structure
    with open(KRITARC_PATH, "r", encoding="utf-8", errors="ignore") as f:
        lines = f.readlines()

    python_section_found = False
    plugin_enabled = False
    new_lines = []

    for line in lines:
        stripped = line.strip()
        if stripped == "[python]":
            python_section_found = True
        elif python_section_found and stripped.startswith("["):
            # Exiting [python] section, insert if not found
            if not plugin_enabled:
                new_lines.append("enable_krita_3d_layer=true\n")
                plugin_enabled = True
            python_section_found = False

        if python_section_found and stripped.startswith("enable_krita_3d_layer"):
            new_lines.append("enable_krita_3d_layer=true\n")
            plugin_enabled = True
            continue

        new_lines.append(line)

    if not plugin_enabled:
        if python_section_found:
            new_lines.append("enable_krita_3d_layer=true\n")
        else:
            new_lines.append("\n[python]\nenable_krita_3d_layer=true\n")

    with open(KRITARC_PATH, "w", encoding="utf-8") as f:
        f.writelines(new_lines)

    print("  -> Plugin enabled under [python] in kritarc: enable_krita_3d_layer=true")


def inject_into_running_krita():
    import tempfile
    print("[3/3] Injecting plugin into running Krita instance...")
    # Generate live bootstrap script
    bridge_script = os.path.join(tempfile.gettempdir(), "krita_3d_layer_live_boot.py")
    boot_code = f"""
import sys, os
source_dir = r"{SOURCE_DIR}"
if source_dir not in sys.path:
    sys.path.insert(0, source_dir)

pykrita_dir = r"{PYKRITA_DIR}"
if pykrita_dir not in sys.path:
    sys.path.insert(0, pykrita_dir)

import importlib
try:
    import krita_3d_layer
    importlib.reload(krita_3d_layer)
    import krita_3d_layer.widgets
    importlib.reload(krita_3d_layer.widgets)
    import krita_3d_layer.docker
    importlib.reload(krita_3d_layer.docker)
    import krita_3d_layer.viewport
    importlib.reload(krita_3d_layer.viewport)
    import krita_3d_layer.mesh_loader
    importlib.reload(krita_3d_layer.mesh_loader)
    import krita_3d_layer.renderer
    importlib.reload(krita_3d_layer.renderer)
    import krita_3d_layer.ground_calibrator
    importlib.reload(krita_3d_layer.ground_calibrator)
    import krita_3d_layer.canvas_sync
    importlib.reload(krita_3d_layer.canvas_sync)
    print("[Krita-3D-Layer] Reloaded modules successfully.")
except Exception as e:
    print(f"[Krita-3D-Layer] Initial import: {{e}}")

from krita import Krita, DockWidgetFactory, DockWidgetFactoryBase
from krita_3d_layer.docker import Krita3DLayerDocker, DOCKER_ID

app = Krita.instance()
# Register Docker Factory
app.addDockWidgetFactory(
    DockWidgetFactory(
        DOCKER_ID,
        DockWidgetFactoryBase.DockRight,
        Krita3DLayerDocker
    )
)

# Show docker directly in the active main window
try:
    from PyQt5.QtCore import Qt
    from PyQt5.QtWidgets import QDockWidget, QAction, QMenu, QMenuBar
    qwin = app.activeWindow().qwindow() if app.activeWindow() else None
    if qwin:
        existing_dock = None
        for d in qwin.findChildren(QDockWidget):
            if d.objectName() == DOCKER_ID or "3d layer" in (d.windowTitle() or "").lower():
                existing_dock = d
                break
        if not existing_dock:
            existing_dock = Krita3DLayerDocker()
            qwin.addDockWidget(Qt.RightDockWidgetArea, existing_dock)

        existing_dock.show()
        existing_dock.raise_()
        existing_dock.setVisible(True)

        # Add toggle action to Settings -> Dockers menu
        dock_act = existing_dock.toggleViewAction()
        dock_act.setText("3D Layer")
        dock_act.setChecked(True)

        dockers_menu = None
        for m in qwin.findChildren(QMenu):
            t = (m.title() or "").replace("&", "").strip().lower()
            if t == "dockers" or t == "docker":
                dockers_menu = m
                break
        if not dockers_menu:
            for mb in qwin.findChildren(QMenuBar):
                for act in mb.actions():
                    if "setting" in (act.text() or "").lower():
                        sm = act.menu()
                        if sm:
                            for sa in sm.actions():
                                if "docker" in (sa.text() or "").lower():
                                    dockers_menu = sa.menu()
                                    break
        if dockers_menu:
            already_in = False
            for act in dockers_menu.actions():
                if act.text() == "3D Layer" or act == dock_act:
                    already_in = True
                    act.setChecked(True)
                    break
            if not already_in:
                dockers_menu.addAction(dock_act)
except Exception as e:
    print(f"[Krita-3D-Layer] Docker display notice: {{e}}")

print("[Krita-3D-Layer] Live registration complete! Docker ID:", DOCKER_ID)
status_file = os.path.join(tempfile.gettempdir(), "krita_3d_boot_status.txt")
with open(status_file, "w") as f:
    f.write("OK")
"""
    with open(bridge_script, "w", encoding="utf-8") as f:
        f.write(boot_code)

    # Send through Named Pipe if available
    pipe_path = r"\\.\pipe\runscriptz_socket"
    if os.path.exists(pipe_path):
        try:
            with open(pipe_path, "w", encoding="utf-8") as pipe:
                pipe.write(bridge_script + "\n")
                pipe.flush()
            print("  -> Sent live injection command via named pipe.")
            return True
        except Exception as e:
            print(f"  Note on named pipe: {e}")
    else:
        print("  Running Krita detected, configuration updated for next launch.")
    return False


if __name__ == "__main__":
    install_files()
    enable_in_kritarc()
    inject_into_running_krita()
    print("\n[DONE] Krita-3D-Layer installation completed!")
