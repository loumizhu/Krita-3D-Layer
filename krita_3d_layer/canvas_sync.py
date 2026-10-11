"""
Renders and stamps the 3D viewport onto Krita paint layers.
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
    def ensure_layer_visible(layer_mode="named", layer_name="3D Perspective & Model"):
        """
        If the target Krita layer exists and is currently hidden, unhides it
        and refreshes the document projection so changes are visible immediately.
        """
        doc = CanvasSyncManager.get_active_document()
        if not doc:
            return False
        try:
            target_node = None
            if layer_mode == "active":
                target_node = doc.activeNode()
                if target_node and target_node.type() != "paintlayer":
                    target_node = None
            elif layer_mode == "named":
                target_node = doc.nodeByName(layer_name)
                if not target_node:
                    active = doc.activeNode()
                    if active and "3D" in active.name():
                        target_node = active

            if target_node and hasattr(target_node, "visible") and hasattr(target_node, "setVisible"):
                if not target_node.visible():
                    target_node.setVisible(True)
                    doc.refreshProjection()
                    return True
        except Exception:
            pass
        return False

    @staticmethod
    def render_to_krita_layer(mesh, camera, lighting, renderer, render_style,
                              layer_mode="named", layer_name="3D Model Layer",
                              transparent_bg=True, custom_bg=None,
                              scale_factor=1.0, frame=None,
                              grid_settings=None, draw_model=True,
                              object_transform=None, set_active=True):
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
                draw_model=draw_model,
                object_transform=object_transform
            )

            if qimg.format() != QImage.Format_ARGB32:
                qimg = qimg.convertToFormat(QImage.Format_ARGB32)

            if render_w != fw or render_h != fh:
                qimg = qimg.scaled(fw, fh, Qt.IgnoreAspectRatio, Qt.SmoothTransformation)

            ptr = qimg.bits()
            ptr.setsize(fw * fh * 4)
            pixel_data = bytes(ptr)
            out_x, out_y, out_w, out_h = fx, fy, fw, fh
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
                draw_model=draw_model,
                object_transform=object_transform
            )

            if qimg.format() != QImage.Format_ARGB32:
                qimg = qimg.convertToFormat(QImage.Format_ARGB32)

            if render_w != doc_w or render_h != doc_h:
                qimg = qimg.scaled(doc_w, doc_h, Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
                render_w, render_h = doc_w, doc_h

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
                mesh_n = mesh.name if (mesh and hasattr(mesh, 'name') and mesh.name) else "3D"
                final_name = f"{mesh_n} Stamp"
            elif layer_mode == "active":
                final_name = "3D Stamp"
            target_node = doc.createNode(final_name, "paintlayer")

            # Place target_node directly ABOVE active node, or at top of rootNode
            above_node = doc.activeNode()
            root = doc.rootNode()
            parent = (above_node.parentNode() if (above_node and hasattr(above_node, 'parentNode') and above_node.parentNode()) else None) or root
            try:
                if above_node and parent:
                    parent.addChildNode(target_node, above_node)
                else:
                    children = root.childNodes()
                    top_node = children[-1] if children else None
                    root.addChildNode(target_node, top_node)
            except Exception:
                root.addChildNode(target_node, None)

        # Unhide layer if it is hidden so user sees updates immediately
        if hasattr(target_node, "visible") and hasattr(target_node, "setVisible"):
            if not target_node.visible():
                target_node.setVisible(True)
        if hasattr(target_node, "opacity") and hasattr(target_node, "setOpacity"):
            if target_node.opacity() == 0:
                target_node.setOpacity(255)

        # Check and handle document color model & bit depth
        color_model = doc.colorModel() if hasattr(doc, 'colorModel') else "RGBA"
        color_depth = doc.colorDepth() if hasattr(doc, 'colorDepth') else "U8"

        if color_model == "RGBA" and color_depth == "U16":
            # Expand 8-bit ARGB32 to 16-bit uint16 (little-endian 2 bytes per channel)
            u16_bytes = bytearray(len(pixel_data) * 2)
            for i, b in enumerate(pixel_data):
                val16 = b * 257
                u16_bytes[i * 2] = val16 & 0xFF
                u16_bytes[i * 2 + 1] = (val16 >> 8) & 0xFF
            pixel_data = bytes(u16_bytes)
        elif color_model == "GRAYA" and color_depth == "U8":
            # Convert 4-channel BGRA to 2-channel Grayscale + Alpha
            num_px = out_w * out_h
            gray_bytes = bytearray(num_px * 2)
            for i in range(num_px):
                b = pixel_data[i * 4]
                g = pixel_data[i * 4 + 1]
                r = pixel_data[i * 4 + 2]
                a = pixel_data[i * 4 + 3]
                gray_val = int(0.299 * r + 0.587 * g + 0.114 * b)
                gray_bytes[i * 2] = gray_val
                gray_bytes[i * 2 + 1] = a
            pixel_data = bytes(gray_bytes)
        elif color_model not in ("RGBA", "GRAYA"):
            raise RuntimeError(
                f"Document color model '{color_model}' is not supported for 3D stamping. "
                f"Please use an RGB canvas (Image -> Convert Image Color Space...)."
            )

        # Write pixel data to layer
        target_node.setPixelData(pixel_data, out_x, out_y, out_w, out_h)
        if set_active:
            doc.setActiveNode(target_node)
        doc.refreshProjection()
        if hasattr(doc, 'waitForDone'):
            try:
                doc.waitForDone()
            except Exception:
                pass

        return target_node.name()
