import winreg

_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
_VALUE_NAME = "Molvi"


def _open(access):
    return winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY, 0, access)


def is_enabled():
    with _open(winreg.KEY_READ) as key:
        try:
            winreg.QueryValueEx(key, _VALUE_NAME)
            return True
        except FileNotFoundError:
            return False


def enable(command):
    with _open(winreg.KEY_SET_VALUE) as key:
        winreg.SetValueEx(key, _VALUE_NAME, 0, winreg.REG_SZ, command)


def disable():
    with _open(winreg.KEY_SET_VALUE) as key:
        try:
            winreg.DeleteValue(key, _VALUE_NAME)
        except FileNotFoundError:
            pass
