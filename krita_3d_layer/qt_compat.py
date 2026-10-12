"""
qt_compat.py — Cross-compatibility layer for PyQt5 (Krita 5.x) and PyQt6 (Krita 6.x).
Provides unified access to QtCore, QtGui, QtWidgets, Qt enums, and QAction.
"""

import sys

QT_VERSION = 5

try:
    from PyQt5 import QtCore, QtGui, QtWidgets
    QT_VERSION = 5
except (ImportError, ModuleNotFoundError):
    from PyQt6 import QtCore, QtGui, QtWidgets
    QT_VERSION = 6

# In PyQt6, QAction was moved from QtWidgets to QtGui
if not hasattr(QtWidgets, 'QAction') and hasattr(QtGui, 'QAction'):
    QtWidgets.QAction = QtGui.QAction

# In PyQt6, QDesktopWidget was removed in favor of QScreen
if not hasattr(QtWidgets, 'QDesktopWidget'):
    class _CompatDesktopWidget:
        def availableGeometry(self, *args):
            screen = QtGui.QGuiApplication.primaryScreen()
            return screen.availableGeometry() if screen else QtCore.QRect(0, 0, 1920, 1080)
        def screenGeometry(self, *args):
            screen = QtGui.QGuiApplication.primaryScreen()
            return screen.geometry() if screen else QtCore.QRect(0, 0, 1920, 1080)
    QtWidgets.QDesktopWidget = _CompatDesktopWidget

# In PyQt6, exec_ was deprecated/removed in favor of exec
for cls in (QtWidgets.QDialog, QtWidgets.QMenu, QtWidgets.QApplication):
    if hasattr(cls, 'exec') and not hasattr(cls, 'exec_'):
        cls.exec_ = cls.exec


class _QtEnumProxy:
    """
    Transparent proxy for QtCore.Qt allowing Qt5-style enum access (e.g. Qt.AlignCenter,
    Qt.LeftButton, Qt.DashLine) seamlessly under both PyQt5 and PyQt6.
    """
    def __init__(self, qt_mod):
        self._qt = qt_mod
        self._cache = {}

    def __getattr__(self, name):
        if hasattr(self._qt, name):
            return getattr(self._qt, name)
        if name in self._cache:
            return self._cache[name]
        for attr_name in dir(self._qt):
            attr = getattr(self._qt, attr_name)
            if isinstance(attr, type):
                try:
                    if hasattr(attr, name):
                        val = getattr(attr, name)
                        self._cache[name] = val
                        return val
                except Exception:
                    pass
        raise AttributeError(f"QtCore.Qt has no attribute '{name}'")


Qt = _QtEnumProxy(QtCore.Qt)

# QtCore re-exports
QPoint = QtCore.QPoint
QPointF = QtCore.QPointF
QRect = QtCore.QRect
QRectF = QtCore.QRectF
QSize = QtCore.QSize
QSizeF = QtCore.QSizeF
QByteArray = QtCore.QByteArray
QEvent = QtCore.QEvent
pyqtSignal = QtCore.pyqtSignal
pyqtSlot = QtCore.pyqtSlot
QUrl = QtCore.QUrl
QObject = QtCore.QObject
QTimer = QtCore.QTimer

# QtGui re-exports
QColor = QtGui.QColor
QImage = QtGui.QImage
QPainter = QtGui.QPainter
QPainterPath = QtGui.QPainterPath
QPen = QtGui.QPen
QBrush = QtGui.QBrush
QFont = QtGui.QFont
QFontMetrics = QtGui.QFontMetrics
QLinearGradient = QtGui.QLinearGradient
QRadialGradient = QtGui.QRadialGradient
QVector3D = QtGui.QVector3D
QVector4D = QtGui.QVector4D
QMatrix4x4 = QtGui.QMatrix4x4
QPolygonF = QtGui.QPolygonF
QIcon = QtGui.QIcon
QCursor = QtGui.QCursor
QDesktopServices = QtGui.QDesktopServices

# QtWidgets re-exports
QWidget = QtWidgets.QWidget
QDialog = QtWidgets.QDialog
QVBoxLayout = QtWidgets.QVBoxLayout
QHBoxLayout = QtWidgets.QHBoxLayout
QGridLayout = QtWidgets.QGridLayout
QLayout = QtWidgets.QLayout
QPushButton = QtWidgets.QPushButton
QToolButton = QtWidgets.QToolButton
QLabel = QtWidgets.QLabel
QSlider = QtWidgets.QSlider
QSpinBox = QtWidgets.QSpinBox
QDoubleSpinBox = QtWidgets.QDoubleSpinBox
QAbstractSpinBox = QtWidgets.QAbstractSpinBox
QComboBox = QtWidgets.QComboBox
QCheckBox = QtWidgets.QCheckBox
QScrollArea = QtWidgets.QScrollArea
QFrame = QtWidgets.QFrame
QGroupBox = QtWidgets.QGroupBox
QMenu = QtWidgets.QMenu
QAction = QtWidgets.QAction
QFileDialog = QtWidgets.QFileDialog
QMessageBox = QtWidgets.QMessageBox
QApplication = QtWidgets.QApplication
QDockWidget = QtWidgets.QDockWidget
QSizePolicy = QtWidgets.QSizePolicy
QMenuBar = QtWidgets.QMenuBar
QDesktopWidget = QtWidgets.QDesktopWidget
QColorDialog = QtWidgets.QColorDialog
QButtonGroup = QtWidgets.QButtonGroup
QInputDialog = QtWidgets.QInputDialog
QToolTip = QtWidgets.QToolTip
QLineEdit = QtWidgets.QLineEdit
QListWidget = QtWidgets.QListWidget
QListWidgetItem = QtWidgets.QListWidgetItem
