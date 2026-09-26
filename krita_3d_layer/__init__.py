"""
Krita-3D-Layer Plugin.
Imports 3D models (OBJ, STL), renders them in an interactive 3D viewport,
and stamps/draws them directly onto Krita's canvas layers.
"""

try:
    from krita import Krita, DockWidgetFactory, DockWidgetFactoryBase
    from .docker import Krita3DLayerDocker, DOCKER_ID
    from .extension import Krita3DLayerExtension

    # Initialize and register with Krita instance
    app = Krita.instance()
    if app:
        # 1. Register Extension
        extension = Krita3DLayerExtension(parent=app)
        app.addExtension(extension)

        # 2. Register DockWidget
        app.addDockWidgetFactory(
            DockWidgetFactory(
                DOCKER_ID,
                DockWidgetFactoryBase.DockRight,
                Krita3DLayerDocker
            )
        )
except ImportError:
    # Running outside Krita (e.g. standalone test or installer)
    pass
