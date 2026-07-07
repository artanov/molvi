# -*- mode: python -*-
# Сборка: packaging/build.bat (или см. .github/workflows/release.yml)
import os

from PyInstaller.utils.hooks import collect_all, collect_data_files

# Абсолютный путь к корню репозитория: относительный pathex („..“) находил пакет
# voiceflow только при запуске через `python -m PyInstaller` (CWD в sys.path);
# голый `pyinstaller` собирал exe без него → ModuleNotFoundError у пользователей.
REPO_ROOT = os.path.abspath(os.path.join(SPECPATH, ".."))

ct2_datas, ct2_binaries, ct2_hidden = collect_all("ctranslate2")

a = Analysis(
    ["entry.py"],
    pathex=[REPO_ROOT],
    binaries=ct2_binaries,
    datas=[("../voiceflow/assets", "voiceflow/assets")]
          + collect_data_files("faster_whisper")
          + ct2_datas,
    hiddenimports=["pystray._win32", "PIL.ImageTk", "sounddevice"] + ct2_hidden,
    excludes=["nvidia", "torch", "pytest", "tkinter.test"],
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    exclude_binaries=True,
    name="VoiceFlow",
    console=False,
    icon="voiceflow.ico",
)
coll = COLLECT(exe, a.binaries, a.datas, name="VoiceFlow")
