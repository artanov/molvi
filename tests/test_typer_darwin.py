import pytest

typer = pytest.importorskip(
    "molvi.platform.darwin.typer",
    reason="вставка текста через Quartz/AppKit — только macOS",
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
    monkeypatch.setattr(typer, "_press_cmd_v", lambda: calls.append(("cmd_v",)))
    monkeypatch.setattr(typer.time, "sleep", lambda s: calls.append(("sleep", s)))
    return calls, clipboard


def test_paste_sets_pastes_then_restores(fake_env):
    calls, clipboard = fake_env
    typer.paste_text("новый текст", restore_delay=0.3)
    assert calls == [
        ("set", "новый текст"),
        ("cmd_v",),
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
        typer, "_press_cmd_v",
        lambda: (_ for _ in ()).throw(OSError("CGEventPost failed")),
    )
    with pytest.raises(OSError):
        typer.paste_text("важный текст")
    assert clipboard["text"] == "важный текст"  # буфер НЕ восстановлен — текст не потерян


def test_insert_text_dispatch(fake_env, monkeypatch):
    called = {}
    monkeypatch.setattr(typer, "paste_text", lambda t: called.setdefault("paste", t))
    monkeypatch.setattr(typer, "type_text_direct", lambda t: called.setdefault("type", t))
    typer.insert_text("a", "clipboard")
    typer.insert_text("b", "type")
    assert called == {"paste": "a", "type": "b"}


def test_insert_text_auto_is_paste(fake_env, monkeypatch):
    # На маке auto — всегда вставка: терминалы понимают Cmd+V сами.
    called = {}
    monkeypatch.setattr(typer, "paste_text", lambda t: called.setdefault("paste", t))
    typer.insert_text("a", "auto")
    assert called == {"paste": "a"}


def test_insert_text_type_failure_puts_text_in_clipboard(fake_env, monkeypatch):
    calls, clipboard = fake_env
    monkeypatch.setattr(
        typer, "type_text_direct",
        lambda t: (_ for _ in ()).throw(OSError("CGEventPost failed")),
    )
    with pytest.raises(OSError):
        typer.insert_text("важный текст", "type")
    assert clipboard["text"] == "важный текст"  # текст не потерян


def test_type_text_direct_posts_unicode_events(monkeypatch):
    """Каждый символ (включая эмодзи вне BMP) — пара keyDown/keyUp с юникодом."""
    posted = []
    monkeypatch.setattr(typer.Quartz, "CGEventCreateKeyboardEvent",
                        lambda src, vk, down: {"vk": vk, "down": down})
    monkeypatch.setattr(
        typer.Quartz, "CGEventKeyboardSetUnicodeString",
        lambda ev, n, s: ev.update(units=n, s=s))
    monkeypatch.setattr(typer, "_post", lambda ev: posted.append(ev))
    monkeypatch.setattr(typer.time, "sleep", lambda s: None)
    typer.type_text_direct("a\U0001F600\n")  # 😀 = 2 UTF-16 юнита
    assert posted[0] == {"vk": 0, "down": True, "units": 1, "s": "a"}
    assert posted[1] == {"vk": 0, "down": False, "units": 1, "s": "a"}
    assert posted[2]["units"] == 2 and posted[2]["s"] == "\U0001F600"
    assert posted[4] == {"vk": typer.VK_RETURN, "down": True}
    assert posted[5] == {"vk": typer.VK_RETURN, "down": False}


def test_post_marks_events_as_injected(monkeypatch):
    """Без метки INJECT_MAGIC собственный Cmd+V дёргал бы PTT с Cmd."""
    marked = []
    monkeypatch.setattr(
        typer.Quartz, "CGEventSetIntegerValueField",
        lambda ev, field, value: marked.append((field, value)))
    monkeypatch.setattr(typer.Quartz, "CGEventPost", lambda tap, ev: None)
    typer._post(object())
    from molvi.platform.darwin.hotkey import INJECT_MAGIC
    assert marked == [(typer.Quartz.kCGEventSourceUserData, INJECT_MAGIC)]
