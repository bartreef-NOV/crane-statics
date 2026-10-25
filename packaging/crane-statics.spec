# PyInstaller spec: one-folder windowed build.
#   pyinstaller packaging/crane-statics.spec --noconfirm
# Paths are relative to the repo root (the directory pyinstaller is run from).
from pathlib import Path

ROOT = Path.cwd()
PKG = ROOT / "src" / "crane_statics"

a = Analysis(
    [str(ROOT / "packaging" / "launcher.py")],
    pathex=[str(ROOT / "src")],
    datas=[
        # QML is loaded from disk by path (app.QML_DIR), so it must ship as files.
        (str(PKG / "qml_app" / "qml"), "crane_statics/qml_app/qml"),
        (str(PKG / "schemas"), "crane_statics/schemas"),
    ],
    hiddenimports=[],
    excludes=[
        "tkinter",
        "pytest",
        "mypy",
        "PyQt6.QtWebEngineCore",
        "PyQt6.QtWebEngineWidgets",
        "PyQt6.QtWebEngineQuick",
        "PyQt6.Qt3DCore",
        "PyQt6.QtMultimedia",
        "PyQt6.QtBluetooth",
        "PyQt6.QtNfc",
        "PyQt6.QtSql",
        "PyQt6.QtPdf",
        "PyQt6.QtDesigner",
        "PyQt6.QtTest",
    ],
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="crane-statics",
    console=False,
    upx=False,
)
coll = COLLECT(exe, a.binaries, a.datas, name="crane-statics", upx=False)
