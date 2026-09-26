"""
extension.py - Krita Extension for Krita-3D-Layer.
Provides menu actions under Tools -> Scripts and support for floating 3D Window.
"""

from PyQt5.QtWidgets import QDialog, QVBoxLayout, QPushButton, QHBoxLayout
from PyQt5.QtCore import Qt

try:
    from krita import Extension, Krita
except ImportError:
    Extension = object
    Krita = None

from .docker import Krita3DLayerDocker, DEFAULT_ASARO_PATH


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

    def show_dialog(self):
        if not self.dialog:
            self.dialog = Krita3DLayerDialog()
        self.dialog.show()
        self.dialog.raise_()
        self.dialog.activateWindow()
