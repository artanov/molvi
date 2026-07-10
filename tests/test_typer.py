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
