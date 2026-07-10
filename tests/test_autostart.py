import pytest

winreg = pytest.importorskip("winreg", reason="реестр — только Windows")
autostart = pytest.importorskip("molvi.platform.win32.autostart")


class FakeKey:
    def __init__(self, store):
        self.store = store
    def __enter__(self):
        return self
    def __exit__(self, *a):
        return False


def _patch_registry(monkeypatch, store):
    key = FakeKey(store)
    monkeypatch.setattr(autostart.winreg, "OpenKey", lambda *a, **kw: key)
    monkeypatch.setattr(
        autostart.winreg, "SetValueEx",
        lambda k, name, res, typ, val: store.__setitem__(name, val),
    )
    def query(k, name):
        if name not in store:
            raise FileNotFoundError
        return store[name], winreg.REG_SZ
    monkeypatch.setattr(autostart.winreg, "QueryValueEx", query)
    def delete(k, name):
        if name not in store:
            raise FileNotFoundError
        del store[name]
    monkeypatch.setattr(autostart.winreg, "DeleteValue", delete)


def test_enable_disable_cycle(monkeypatch):
    store = {}
    _patch_registry(monkeypatch, store)
    assert autostart.is_enabled() is False
    autostart.enable(r"F:\molvi\molvi.bat")
    assert store["Molvi"] == r"F:\molvi\molvi.bat"
    assert autostart.is_enabled() is True
    autostart.disable()
    assert "Molvi" not in store
    assert autostart.is_enabled() is False


def test_disable_when_absent_is_noop(monkeypatch):
    _patch_registry(monkeypatch, {})
    autostart.disable()  # не должно бросить
