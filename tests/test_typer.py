import ctypes

import pytest

typer = pytest.importorskip(
    "molvi.platform.win32.typer",
    reason="вставка текста через WinAPI — только Windows",
)


@pytest.fixture
def fake_env(monkeypatch):
    """Подменяет работу с реальным буфером и клавиатурой; пишет журнал вызовов."""
    calls = []
    clipboard = {"text": "старое содержимое"}

    monkeypatch.setattr(typer, "_get_clipboard_text", lambda: clipboard["text"])
    monkeypatch.setattr(
        typer, "_set_clipboard_text",
        lambda t: (clipboard.__setitem__("text", t), calls.append(("set", t))),
    )
    monkeypatch.setattr(typer, "_press_ctrl_v", lambda: calls.append(("ctrl_v",)))
    monkeypatch.setattr(typer.time, "sleep", lambda s: calls.append(("sleep", s)))
    return calls, clipboard


def test_paste_sets_pastes_then_restores(fake_env):
    calls, clipboard = fake_env
    typer.paste_text("новый текст", restore_delay=0.3)
    assert calls == [
        ("set", "новый текст"),
        ("ctrl_v",),
        ("sleep", 0.3),
        ("set", "старое содержимое"),
    ]
    assert clipboard["text"] == "старое содержимое"


def test_paste_without_prior_text_skips_restore(fake_env, monkeypatch):
    calls, clipboard = fake_env
    monkeypatch.setattr(typer, "_get_clipboard_text", lambda: None)  # в буфере картинка
    typer.paste_text("текст", restore_delay=0.1)
    assert ("set", "текст") in calls
    assert calls[-1] != ("set", None)
    assert clipboard["text"] == "текст"


def test_paste_failure_keeps_text_in_clipboard(fake_env, monkeypatch):
    calls, clipboard = fake_env
    monkeypatch.setattr(
        typer, "_press_ctrl_v",
        lambda: (_ for _ in ()).throw(OSError("SendInput failed")),
    )
    with pytest.raises(OSError):
        typer.paste_text("важный текст")
    assert clipboard["text"] == "важный текст"  # буфер НЕ восстановлен — текст не потерян


def test_input_struct_size_matches_win32():
    # Win32 требует cbSize == sizeof(INPUT) == 40 на x64; SendInput с другим размером возвращает 0/ERROR_INVALID_PARAMETER
    assert ctypes.sizeof(typer._INPUT) == 40


def test_insert_text_dispatch(fake_env, monkeypatch):
    called = {}
    monkeypatch.setattr(typer, "paste_text", lambda t: called.setdefault("paste", t))
    monkeypatch.setattr(typer, "type_text_direct", lambda t: called.setdefault("type", t))
    typer.insert_text("a", "clipboard")
    typer.insert_text("b", "type")
    assert called == {"paste": "a", "type": "b"}


def test_type_text_direct_sends_utf16_pairs(monkeypatch):
    """Символы вне BMP (эмодзи) шлются суррогатной парой, а не обрезаются."""
    sent = []
    monkeypatch.setattr(
        typer, "_send_key",
        lambda vk=0, scan=0, flags=0: sent.append((vk, scan, flags)),
    )
    monkeypatch.setattr(typer.time, "sleep", lambda s: None)
    typer.type_text_direct("a\U0001F600")  # 😀 = U+1F600 → D83D DE00
    U, UP = typer.KEYEVENTF_UNICODE, typer.KEYEVENTF_KEYUP
    assert sent == [
        (0, ord("a"), U), (0, ord("a"), U | UP),
        (0, 0xD83D, U), (0, 0xD83D, U | UP),
        (0, 0xDE00, U), (0, 0xDE00, U | UP),
    ]


def test_insert_text_type_failure_puts_text_in_clipboard(fake_env, monkeypatch):
    calls, clipboard = fake_env
    monkeypatch.setattr(
        typer, "type_text_direct",
        lambda t: (_ for _ in ()).throw(OSError("SendInput failed")),
    )
    with pytest.raises(OSError):
        typer.insert_text("важный текст", "type")
    assert clipboard["text"] == "важный текст"  # текст не потерян


def test_insert_text_auto_mode(monkeypatch):
    called = {}
    monkeypatch.setattr(typer, "paste_text", lambda t: called.setdefault("paste", t))
    monkeypatch.setattr(typer, "type_text_direct", lambda t: called.setdefault("type", t))
    monkeypatch.setattr(typer, "_foreground_is_console", lambda: True)
    typer.insert_text("a", "auto")
    monkeypatch.setattr(typer, "_foreground_is_console", lambda: False)
    typer.insert_text("b", "auto")
    assert called == {"type": "a", "paste": "b"}


def test_copy_to_clipboard_sets_without_paste_or_restore(fake_env):
    calls, clipboard = fake_env
    typer.copy_to_clipboard("спасённый текст")
    assert clipboard["text"] == "спасённый текст"
    assert calls == [("set", "спасённый текст")]  # ни ctrl_v, ни восстановления


class FakeUser32:
    """WinAPI-заглушка для функций цели: журнал вызовов + управляемый фокус."""
    def __init__(self, foreground=100, valid=True, activate_switches=True):
        self.foreground = foreground
        self.valid = valid
        self.activate_switches = activate_switches
        self.calls = []

    def GetForegroundWindow(self):
        return self.foreground

    def IsWindow(self, hwnd):
        return 1 if self.valid else 0

    def GetWindowThreadProcessId(self, hwnd, ref):
        return 42  # чужой поток — ветка AttachThreadInput

    def AttachThreadInput(self, a, b, attach):
        self.calls.append(("attach", bool(attach)))
        return 1

    def SetForegroundWindow(self, hwnd):
        self.calls.append(("set_fg", hwnd))
        if self.activate_switches:
            self.foreground = hwnd
        return 1


@pytest.fixture
def fake_user32(monkeypatch):
    fake = FakeUser32()
    monkeypatch.setattr(typer, "_user32", fake)
    monkeypatch.setattr(typer.time, "sleep", lambda s: None)
    return fake


def test_get_target_returns_foreground_or_none(fake_user32):
    assert typer.get_target() == 100
    fake_user32.foreground = 0
    assert typer.get_target() is None


def test_target_is_foreground(fake_user32):
    assert typer.target_is_foreground(100) is True
    assert typer.target_is_foreground(200) is False
    assert typer.target_is_foreground(None) is False


def test_activate_target_invalid_window_false(fake_user32):
    fake_user32.valid = False
    assert typer.activate_target(200) is False
    assert fake_user32.calls == []  # до SetForegroundWindow не дошли


def test_activate_target_already_foreground_true(fake_user32):
    assert typer.activate_target(100) is True
    assert fake_user32.calls == []


def test_activate_target_switches_and_verifies(fake_user32):
    assert typer.activate_target(200) is True
    assert ("set_fg", 200) in fake_user32.calls
    # AttachThreadInput отцеплен после активации
    assert fake_user32.calls.count(("attach", True)) == 1
    assert fake_user32.calls.count(("attach", False)) == 1


def test_activate_target_verifies_result_not_call(fake_user32):
    # SetForegroundWindow «сработал», но фокус не сменился (foreground lock)
    fake_user32.activate_switches = False
    assert typer.activate_target(200) is False
