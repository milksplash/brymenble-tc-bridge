# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for the brymenble-tc-bridge Windows EXE.
#
# Build (from the repo root, with the venv active):
#   pyinstaller brymenble-tc-bridge.spec
#
# Output: dist/brymenble-tc-bridge.exe  (onefile, console app)

from pathlib import Path

# SPECPATH = Path containing the spec file.
ROOT = Path(SPECPATH)

a = Analysis(
    ["bridge/__main__.py"],
    pathex=[str(ROOT)],
    binaries=[],
    datas=[],
    hiddenimports=[],
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="brymenble-tc-bridge",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,           # console app: shows logs / accepts CLI args
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(ROOT / "img" / "icon.ico") if (ROOT / "img" / "icon.ico").exists() else None,
)