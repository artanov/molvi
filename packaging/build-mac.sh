#!/bin/zsh
# Сборка Molvi.app + DMG (локально и в CI). Запуск из корня репозитория:
#   packaging/build-mac.sh [версия]
# Интерпретатор: $PYTHON или .venv/bin/python; нужны requirements-base.txt
# + pyinstaller==6.21.0.
set -euo pipefail
cd "$(dirname "$0")/.."

export MOLVI_VERSION="${1:-0.0.0}"
PY="${PYTHON:-.venv/bin/python}"

# Подпись: без стабильной identity TCC-разрешения слетают при каждой
# пересборке. Берём «Molvi Dev Signing» из keychain, если есть; иначе
# PyInstaller подпишет ad-hoc (как в CI без сертификата).
if [[ -z "${MOLVI_CODESIGN_IDENTITY:-}" ]] \
   && security find-identity -v -p codesigning 2>/dev/null | grep -q "Molvi Dev Signing"; then
  export MOLVI_CODESIGN_IDENTITY="Molvi Dev Signing"
fi
echo "Подпись: ${MOLVI_CODESIGN_IDENTITY:-ad-hoc}"

$PY packaging/make_icns.py
$PY -m PyInstaller packaging/molvi-mac.spec --noconfirm \
    --distpath packaging/dist --workpath packaging/build

# DMG: приложение + симлинк на /Applications, чтобы «перетащить и готово».
STAGE=packaging/dist/dmg
rm -rf "$STAGE"
mkdir -p "$STAGE"
cp -R packaging/dist/Molvi.app "$STAGE/"
ln -s /Applications "$STAGE/Applications"
DMG="packaging/dist/Molvi-${MOLVI_VERSION}.dmg"
rm -f "$DMG"
hdiutil create -volname "Molvi" -srcfolder "$STAGE" -ov -format UDZO "$DMG"
echo "Готово: $DMG"
