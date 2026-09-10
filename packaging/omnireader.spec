# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for OmniReader Pro (Windows one-folder build, no console).

Build:  pyinstaller packaging/omnireader.spec --noconfirm
Output: dist/OmniReaderPro/OmniReaderPro.exe
"""
import sys
from pathlib import Path

ROOT = Path(SPECPATH).resolve().parent

datas = [
    (str(ROOT / "resources" / "icons"), "resources/icons"),
]

hiddenimports = [
    # Qt platform / plugin modules PyInstaller sometimes misses on Windows
    "PySide6.QtWebEngineWidgets",
    "PySide6.QtWebEngineCore",
    "PySide6.QtWebChannel",
    "PySide6.QtNetwork",
    "PySide6.QtPrintSupport",
    # Optional engines that are imported lazily by design
    "ebooklib",
    "openpyxl",
    "pptx",
    "odf",
    "cryptography.hazmat.primitives.ciphers.aead",
    "pytesseract",
    "rarfile",
    "pypdf",
    "docx",
    "chardet",
    "rapidfuzz",
]

a = Analysis(
    [str(ROOT / "run_omnireader.pyw")],
    pathex=[str(ROOT / "src")],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=[
        "PySide6.QtQml", "PySide6.QtQuick", "PySide6.QtQuick3D",
        "PySide6.QtMultimedia", "PySide6.QtBluetooth", "PySide6.QtLocation",
        "PySide6.QtSensors", "PySide6.QtSerialPort", "PySide6.QtTest",
        "PySide6.QtSql", "PySide6.QtXml", "PySide6.QtDesigner",
        "PySide6.QtHelp", "PySide6.QtOpenGL",
        "tkinter", "test", "unittest", "pydoc_data",
    ],
    noarchive=False,
    optimize=1,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="OmniReaderPro",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,                 # no terminal window
    disable_windowed_traceback=False,
    icon=str(ROOT / "resources" / "icons" / "omnireader.ico"),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="OmniReaderPro",
)