"""Автозапуск на macOS: LaunchAgent plist в ~/Library/LaunchAgents.

Пока не реализовано — фаза 2 порта (см. docs/macos-port.md). Заглушки
безопасны для UI: настройки показывают выключенный чекбокс.
"""
import logging

log = logging.getLogger(__name__)

LABEL = "Запускать при входе в систему"


def is_enabled():
    return False


def enable(command):
    log.warning("Автозапуск на macOS ещё не реализован (фаза 2 порта)")


def disable():
    pass
