from PyInstaller.utils.hooks import collect_all


sherpa_datas, sherpa_binaries, sherpa_hiddenimports = collect_all("sherpa_onnx")

analysis = Analysis(
    ["desktop.py"],
    pathex=[],
    binaries=sherpa_binaries,
    datas=sherpa_datas + [
        ("app/assets/zhichun-placeholder.png", "app/assets"),
        ("app/assets/zhichun-icon.png", "app/assets"),
    ],
    hiddenimports=sherpa_hiddenimports + ["sounddevice"],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(analysis.pure)

exe = EXE(
    pyz,
    analysis.scripts,
    [],
    exclude_binaries=True,
    name="Zhichun",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    argv_emulation=False,
    target_arch="arm64",
    codesign_identity=None,
    entitlements_file=None,
)

collection = COLLECT(
    exe,
    analysis.binaries,
    analysis.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="Zhichun",
)

app = BUNDLE(
    collection,
    name="芷春.app",
    icon="app/assets/zhichun-icon.png",
    bundle_identifier="com.zhichun.assistant",
    info_plist={
        "CFBundleDisplayName": "芷春",
        "NSMicrophoneUsageDescription": "芷春需要使用麦克风来检测唤醒词并识别你的问题。",
        "NSHighResolutionCapable": True,
    },
)
