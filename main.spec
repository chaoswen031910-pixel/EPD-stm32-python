# -*- mode: python ; coding: utf-8 -*-

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    # [修改] 添加所有需要复制的非 .py 文件
    datas=[
        ('profiles', 'profiles')
    ],
    # [关键修改] 添加所有被"隐藏"的模块
    hiddenimports=[
        'workers.display_worker',
        'workers.multi_image_worker',
        'workers.lut_update_worker',
        'workers.device_scanner',
        'workers.flow_worker',
        'workers.serial_worker',
        'dialogs.code_gen_dialog',
        'dialogs.user_guide_dialog',
        'waveform_editor_tool.waveform_editor',
        'waveform_editor_tool.lut_formats',
        'waveform_editor_tool.ui_components',
        'services.image_processor',
        'services.script_executor',
        'services.code_generator',
        'utils',
        'serial.tools.list_ports' # PyInstaller 经常漏掉这个
    ],
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
    name='E-Paper-Pro-Suite', # [建议] 改一个更有意义的名字
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False, # [重要] 确保为 False，隐藏黑窗口
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    # [建议] 为 Windows 添加图标
    # icon='app_icon.ico' 
)