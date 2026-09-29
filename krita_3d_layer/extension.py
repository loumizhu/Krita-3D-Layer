"""
Extension menu entries for Tools -> Scripts.
"""

from PyQt5.QtWidgets import QDialog, QVBoxLayout, QPushButton, QHBoxLayout
from PyQt5.QtCore import Qt

try:
    from krita import Extension, Krita
except ImportError:
    Extension = object
    Krita = None

from .docker import Krita3DLayerDocker


class Krita3DLayerDialog(QDialog):
    """Floating standalone 3D viewport dialog."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("3D Layer - Model Reference & Camera")
        self.resize(700, 600)
        self.setWindowFlags(self.windowFlags() | Qt.Window)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)

        # Reuse docker widget for complete feature set
        self.docker_widget = Krita3DLayerDocker()
        layout.addWidget(self.docker_widget)


class Krita3DLayerExtension(Extension):
    def __init__(self, parent):
        super().__init__(parent)
        self.dialog = None

    def setup(self):
        pass

    def createActions(self, window):
        action = window.createAction(
            "krita_3d_layer_open",
            "Open 3D Model Viewer...",
            "tools/scripts"
        )
        action.triggered.connect(self.show_dialog)

        manual_action = window.createAction(
            "krita_3d_layer_manual",
            "3D Layer Manual & Quick Guide...",
            "tools/scripts"
        )
        manual_action.triggered.connect(self.show_manual)

        draw_action = window.createAction(
            "krita_3d_layer_draw_box",
            "Draw 3D Box / Primitive...",
            "tools/scripts"
        )
        draw_action.triggered.connect(self.draw_box)

        ground_action = window.createAction(
            "krita_3d_layer_ground_calibrator",
            "3D Ground Rectangle Calibrator...",
            "tools/scripts"
        )
        ground_action.triggered.connect(self.open_ground_calibrator)

    def open_ground_calibrator(self):
        """Shows the 3D layer docker and launches the Ground Rectangle Calibrator window."""
        app = Krita.instance() if Krita else None
        if app:
            for d in app.dockers():
                if d.objectName() == "krita_3d_layer_docker" or "3d layer" in d.windowTitle().lower():
                    d.setVisible(True)
                    d.raise_()
                    if hasattr(d, '_open_ground_calibrator'):
                        d._open_ground_calibrator()
                        return
                    elif hasattr(d, 'btn_ground'):
                        d.btn_ground.click()
                        return
        self.show_dialog()
        if self.dialog and hasattr(self.dialog, 'docker_widget'):
            self.dialog.docker_widget._open_ground_calibrator()

    def draw_box(self):
        """Shows the 3D layer docker and launches the Draw 3D Box & Calibrator window."""
        app = Krita.instance() if Krita else None
        if app:
            for d in app.dockers():
                if d.objectName() == "krita_3d_layer_docker" or "3d layer" in d.windowTitle().lower():
                    d.setVisible(True)
                    d.raise_()
                    if hasattr(d, '_open_primitive_drawer'):
                        d._open_primitive_drawer(start_click_draw=True)
                        return
                    elif hasattr(d, 'btn_draw_box'):
                        d.btn_draw_box.click()
                        return
        self.show_dialog()
        if self.dialog and hasattr(self.dialog, 'docker_widget'):
            self.dialog.docker_widget._open_primitive_drawer(start_click_draw=True)

    def show_dialog(self):
        if not self.dialog:
            self.dialog = Krita3DLayerDialog()
        self.dialog.show()
        self.dialog.raise_()
        self.dialog.activateWindow()

    def show_manual(self):
        import os
        from PyQt5.QtGui import QDesktopServices
        from PyQt5.QtCore import QUrl
        manual_path = os.path.join(os.path.dirname(__file__), "Manual.html")
        if os.path.exists(manual_path):
            QDesktopServices.openUrl(QUrl.fromLocalFile(manual_path))
