"""Переходник «PySide6 -> PySide2 (Qt 5)» для сборки под Windows 8.

Код программы написан под PySide6 и импортирует его модули. В сборке для старых Windows этот пакет подставляется вместо настоящего PySide6
и отдаёт то же самое из PySide2; различия Qt 5 и Qt 6, которые встречаются в программе, сглаживаются здесь, чтобы не форкать код.
"""
import PySide2 as _p
from PySide2 import QtCore as _core, QtGui as _gui, QtWidgets as _widgets

__legacy__ = True
__version__ = _p.__version__

# события мыши и колеса: position() (Qt 6) -> localPos() / posF() (Qt 5)
_gui.QMouseEvent.position = lambda self: self.localPos()
_gui.QWheelEvent.position = lambda self: self.posF()
if hasattr(_gui, "QDropEvent"):
    _gui.QDropEvent.position = lambda self: self.posF()
# Qt 6 называет exec() то, что в Qt 5 exec_()
for _cls in (_widgets.QDialog, _widgets.QMenu, _widgets.QApplication, _widgets.QMessageBox, _widgets.QFileDialog, _core.QEventLoop):
    _cls.exec = _cls.exec_
