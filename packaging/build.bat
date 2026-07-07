@echo off
cd /d "%~dp0"
if not exist voiceflow.ico ..\.venv\Scripts\python make_ico.py
cd ..
.venv\Scripts\python -m PyInstaller packaging\voiceflow.spec --noconfirm ^
  --distpath packaging\dist --workpath packaging\build
where iscc >nul 2>nul
if %errorlevel%==0 (
  cd packaging && iscc installer.iss && cd ..
) else (
  echo [!] iscc не найден - установщик не собран, только dist\VoiceFlow
)
