# -*- mode: python -*-
# Сборка .app для macOS: packaging/build-mac.sh (или .github/workflows/release.yml)
import os

from PyInstaller.utils.hooks import collect_all

REPO_ROOT = os.path.abspath(os.path.join(SPECPATH, ".."))

# mlx: нативная библиотека + metallib-шейдеры; mlx_whisper: mel-фильтры и токенайзер
mlx_datas, mlx_binaries, mlx_hidden = collect_all("mlx")
mlxw_datas, mlxw_binaries, mlxw_hidden = collect_all("mlx_whisper")

a = Analysis(
    ["entry.py"],
    pathex=[REPO_ROOT],
    binaries=mlx_binaries + mlxw_binaries,
    datas=[("../molvi/assets", "molvi/assets")] + mlx_datas + mlxw_datas,
    hiddenimports=["pystray._darwin", "PIL.ImageTk", "sounddevice",
                   # Платформенный слой импортируется через if по sys.platform —
                   # перечисляем явно, чтобы анализатор не потерял darwin-ветку.
                   "molvi.platform.darwin.autostart", "molvi.platform.darwin.hotkey",
                   "molvi.platform.darwin.overlay", "molvi.platform.darwin.sounds",
                   "molvi.platform.darwin.typer", "molvi.platform.darwin.transcriber",
                   ] + mlx_hidden + mlxw_hidden,
    # torch нужен mlx_whisper только для конвертации весов (torch_whisper.py) —
    # в рантайме не импортируется, а в бандле весил бы гигабайты.
    # faster-whisper/ctranslate2 — Windows-движок, molvi.transcriber на маке
    # не импортируется (app.py выбирает darwin-обёртку).
    excludes=["torch", "ctranslate2", "faster_whisper", "nvidia",
              "molvi.platform.win32", "pytest", "tkinter.test"],
)
pyz = PYZ(a.pure)

# Стабильная подпись (например, самоподписанный «Molvi Dev Signing»): TCC
# привязывает разрешения к подписи, ad-hoc меняется каждой сборкой — и
# «Мониторинг ввода»/«Универсальный доступ» слетали при каждом обновлении.
_SIGN_IDENTITY = os.environ.get("MOLVI_CODESIGN_IDENTITY") or None

exe = EXE(
    pyz,
    a.scripts,
    exclude_binaries=True,
    name="Molvi",
    console=False,
    codesign_identity=_SIGN_IDENTITY,
)
coll = COLLECT(exe, a.binaries, a.datas, name="Molvi")
app = BUNDLE(
    coll,
    name="Molvi.app",
    icon="molvi.icns",
    bundle_identifier="tech.molvi.app",
    version=os.environ.get("MOLVI_VERSION", "0.0.0").lstrip("v"),
    info_plist={
        # Приложение строки меню: без иконки в Dock и Cmd+Tab (дублирует
        # activationPolicy Accessory — Dock-иконка не мигает при старте).
        "LSUIElement": True,
        "NSMicrophoneUsageDescription":
            "Molvi записывает голос с микрофона и распознаёт его в текст "
            "локально, без отправки в интернет.",
        "LSMinimumSystemVersion": "13.5",  # требование mlx
        "NSHighResolutionCapable": True,
    },
)
