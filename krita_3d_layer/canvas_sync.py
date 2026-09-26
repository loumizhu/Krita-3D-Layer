"""
canvas_sync.py - Handles rendering 3D models directly onto Krita's canvas layers.
Interacts with Krita Python API (Document, Node, setPixelData).
"""

from PyQt5.QtGui import QColor, QImage, QPainter
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
    def get_active_selection_rect():
        """Returns (x, y, w, h) of active selection in Krita or None."""
        doc = CanvasSyncManager.get_active_document()
        if not doc:
            return None
        try:
            sel = doc.selection()
            if sel and sel.width() > 0 and sel.height() > 0:
                return (sel.x(), sel.y(), sel.width(), sel.height())
        except Exception:
            pass
        return None

    @staticmethod
    def get_canvas_snapshot():
        """Returns QImage of current Krita document canvas, or None."""
        doc = CanvasSyncManager.get_active_document()
        if not doc:
            return None
        try:
            w = doc.width()
            h = doc.height()
            if w <= 0 or h <= 0:
                return None
            data = doc.pixelData(0, 0, w, h)
            if data:
                qimg = QImage(data, w, h, QImage.Format_ARGB32)
                return qimg.copy()
        except Exception:
            pass
        return None

    @staticmethod
    def render_to_krita_layer(mesh, camera, lighting, renderer, render_style,
                              layer_mode="named", layer_name="3D Model Layer",
                              transparent_bg=True, custom_bg=None,
                              scale_factor=1.0, frame=None,
                              grid_settings=None, draw_model=True):
        """
        Renders the 3D model and/or perspective grid onto a Krita paint layer.
        If frame=(fx, fy, fw, fh) is provided, limits rendering strictly within that frame.
        """
        doc = CanvasSyncManager.get_active_document()
        if not doc:
            raise RuntimeError("No active document found in Krita. Please open or create a canvas first.")

        doc_w = doc.width()
        doc_h = doc.height()
        bg = QColor(0, 0, 0, 0) if transparent_bg else (custom_bg or QColor(255, 255, 255, 255))

        if frame and len(frame) == 4 and frame[2] > 0 and frame[3] > 0:
            fx = max(0, min(doc_w - 1, int(frame[0])))
            fy = max(0, min(doc_h - 1, int(frame[1])))
            fw = max(1, min(doc_w - fx, int(frame[2])))
            fh = max(1, min(doc_h - fy, int(frame[3])))

            render_w = max(32, int(fw * scale_factor))
            render_h = max(32, int(fh * scale_factor))

            qimg = renderer.render_to_image(
                mesh=mesh,
                camera=camera,
                lighting=lighting,
                style=render_style,
                width=render_w,
                height=render_h,
                bg_color=bg,
                grid_settings=grid_settings,
                draw_model=draw_model
            )

            # Compose onto full document canvas so everything outside frame is clear
            full_img = QImage(doc_w, doc_h, QImage.Format_ARGB32)
            full_img.fill(QColor(0, 0, 0, 0))
            painter = QPainter(full_img)
            painter.drawImage(fx, fy, qimg)
            painter.end()

            ptr = full_img.bits()
            ptr.setsize(doc_w * doc_h * 4)
            pixel_data = bytes(ptr)
            out_x, out_y, out_w, out_h = 0, 0, doc_w, doc_h
        else:
            # Full canvas render
            render_w = max(64, int(doc_w * scale_factor))
            render_h = max(64, int(doc_h * scale_factor))

            qimg = renderer.render_to_image(
                mesh=mesh,
                camera=camera,
                lighting=lighting,
                style=render_style,
                width=render_w,
                height=render_h,
                bg_color=bg,
                grid_settings=grid_settings,
                draw_model=draw_model
            )

            if qimg.format() != QImage.Format_ARGB32:
                qimg = qimg.convertToFormat(QImage.Format_ARGB32)

            ptr = qimg.bits()
            ptr.setsize(render_w * render_h * 4)
            pixel_data = bytes(ptr)
            out_x, out_y, out_w, out_h = 0, 0, render_w, render_h

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
        target_node.setPixelData(pixel_data, out_x, out_y, out_w, out_h)
        doc.setActiveNode(target_node)
        doc.refreshProjection()

        return target_node.name()
