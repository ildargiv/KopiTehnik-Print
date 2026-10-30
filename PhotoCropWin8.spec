# -*- mode: python ; coding: utf-8 -*-
# Сборка для Windows 8: Python 3.8, PySide2 (Qt 5) через переходник legacy/PySide6, без «Документа» и печати на нескольких принтерах.
from PyInstaller.utils.hooks import collect_all

datas = []
binaries = []
hiddenimports = ['photo_crop', 'smart_crop', 'i18n', 'i18n_more', 'i18n_161', 'color_tools', 'print_stats', 'agent_bridge', 'agent_guide',
                 'agent_clients', 'gui_agent', 'qt_flavor', 'app_dirs', 'PySide6', 'PySide6.QtCore', 'PySide6.QtGui', 'PySide6.QtWidgets', 'PySide6.QtSvg',
                 'PySide2.QtSvg']
try:
    tmp_ret = collect_all('onnxruntime')
    datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
except Exception:
    pass

a = Analysis(
    ['photo_crop_qt.py'],
    pathex=['legacy'],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['PySide6.QtPdf', 'PySide6.QtPdfWidgets'],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='KopiTehnikPrint-Win8',
    icon='brand/app_icon.ico',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
)
