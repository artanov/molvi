import winreg

import voiceflow.autostart as autostart


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
    autostart.enable(r"F:\voiceflow\voiceflow.bat")
    assert store["VoiceFlow"] == r"F:\voiceflow\voiceflow.bat"
    assert autostart.is_enabled() is True
    autostart.disable()
    assert "VoiceFlow" not in store
    assert autostart.is_enabled() is False


def test_disable_when_absent_is_noop(monkeypatch):
    _patch_registry(monkeypatch, {})
    autostart.disable()  # не должно бросить
