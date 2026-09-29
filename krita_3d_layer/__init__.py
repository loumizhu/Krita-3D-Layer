"""
Krita 3D Layer - 3D reference docker and layer stamping plugin for Krita.
"""

import sys

try:
    from krita import Krita, DockWidgetFactory, DockWidgetFactoryBase
except ImportError:
    Krita = None

if Krita is not None:
    try:
        from .docker import Krita3DLayerDocker, DOCKER_ID
        from .extension import Krita3DLayerExtension

        app = Krita.instance()
        if app:
            # Register extension
            try:
                extension = Krita3DLayerExtension(parent=app)
                app.addExtension(extension)
            except Exception as e:
                print(f"[Krita-3D-Layer] Notice adding extension: {e}", file=sys.stderr)

            # Register docker
            try:
                dock_pos = getattr(getattr(DockWidgetFactoryBase, 'DockPosition', DockWidgetFactoryBase), 'DockRight', 1)
                app.addDockWidgetFactory(
                    DockWidgetFactory(
                        DOCKER_ID,
                        dock_pos,
                        Krita3DLayerDocker
                    )
                )
                print(f"[Krita-3D-Layer] Registered DockWidgetFactory: {DOCKER_ID}", file=sys.stderr)
            except Exception as e:
                print(f"[Krita-3D-Layer] Error adding dock widget factory: {e}", file=sys.stderr)
    except Exception as e:
        import traceback
        print(f"[Krita-3D-Layer] Error initializing plugin: {e}", file=sys.stderr)
        traceback.print_exc()
