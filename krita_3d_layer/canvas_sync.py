"""
canvas_sync.py - Handles rendering 3D models directly onto Krita's canvas layers.
Interacts with Krita Python API (Document, Node, setPixelData).
"""

from PyQt5.QtGui import QColor, QImage
from PyQt5.QtCore import Qt

try:
    from krita import Krita
except ImportError:
    Krita = None


class CanvasSyncManager:
    @staticmethod
    def get_active_document():
        if not Krita:
            return None
        return Krita.instance().activeDocument()

    @staticmethod
    def get_document_info():
        doc = CanvasSyncManager.get_active_document()
        if not doc:
            return None
        return {
            "name": doc.name(),
            "width": doc.width(),
            "height": doc.height(),
            "x_res": doc.xRes(),
            "y_res": doc.yRes(),
            "aspect_ratio": float(doc.width()) / float(doc.height()) if doc.height() > 0 else 1.0,
            "color_model": doc.colorModel(),
            "color_depth": doc.colorDepth()
        }

    @staticmethod
    def render_to_krita_layer(mesh, camera, lighting, renderer, render_style,
                              layer_mode="named", layer_name="3D Model Layer",
                              transparent_bg=True, custom_bg=None,
                              scale_factor=1.0):
        """
        Renders the 3D model at full document resolution and applies it to a Krita paint layer.

        layer_mode:
          - "named": writes to layer named layer_name (creates if not exists, overwrites content)
          - "new": always creates a new layer with unique timestamp/index
          - "active": overwrites the currently selected layer in Krita
        """
        doc = CanvasSyncManager.get_active_document()
        if not doc:
            raise RuntimeError("No active document found in Krita. Please open or create a canvas first.")

        doc_w = doc.width()
        doc_h = doc.height()

        # Render at target resolution
        render_w = max(64, int(doc_w * scale_factor))
        render_h = max(64, int(doc_h * scale_factor))

        bg = QColor(0, 0, 0, 0) if transparent_bg else (custom_bg or QColor(255, 255, 255, 255))
        
        qimg = renderer.render_to_image(
            mesh=mesh,
            camera=camera,
            lighting=lighting,
            style=render_style,
            width=render_w,
            height=render_h,
            bg_color=bg
        )

        # Ensure ARGB32 format for byte buffer compatibility
        if qimg.format() != QImage.Format_ARGB32:
            qimg = qimg.convertToFormat(QImage.Format_ARGB32)

        ptr = qimg.bits()
        ptr.setsize(render_w * render_h * 4)
        pixel_data = bytes(ptr)

        # Locate or create target layer
        target_node = None
        if layer_mode == "active":
            target_node = doc.activeNode()
            if target_node and target_node.type() != "paintlayer":
                target_node = None

        elif layer_mode == "named":
            target_node = doc.nodeByName(layer_name)

        if not target_node or layer_mode == "new":
            final_name = layer_name
            if layer_mode == "new":
                final_name = f"{mesh.name if mesh else '3D'} Ref"
            target_node = doc.createNode(final_name, "paintlayer")
            doc.rootNode().addChildNode(target_node, None)

        # Write pixel data to layer
        target_node.setPixelData(pixel_data, 0, 0, render_w, render_h)
        doc.setActiveNode(target_node)
        doc.refreshProjection()

        return target_node.name()
