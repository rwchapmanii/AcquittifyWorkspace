# -*- mode: python ; coding: utf-8 -*-

from PyInstaller.utils.hooks import collect_all, copy_metadata

streamlit_datas, streamlit_binaries, streamlit_hiddenimports = collect_all('streamlit')

a = Analysis(
    ['scripts/launch_streamlit_app.py'],
    pathex=[],
    binaries=streamlit_binaries,
    datas=[
        ('assets/app_icon.png', 'assets'),
        ('app.py', '.'),
    ]
    + streamlit_datas
    + copy_metadata('streamlit'),
    hiddenimports=streamlit_hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
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
    name='Acquittify',
    icon='assets/app_icon.png',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
app = BUNDLE(
    exe,
    name='Acquittify.app',
    icon='assets/app_icon.png',
    bundle_identifier=None,
)
