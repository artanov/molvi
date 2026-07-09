import tkinter as tk

import pytest

from molvi.overlay import Overlay


def _throw(exc):
    raise exc


@pytest.fixture
def overlay():
    try:
        ov = Overlay(scale=0.5)
    except tk.TclError:
        pytest.skip("нет дисплея для tkinter")
    yield ov
    try:
        ov.root.destroy()
    except tk.TclError:
        pass  # уже разрушен самим тестом


def test_poll_survives_failing_settings_opener(overlay):
    """Исключение при открытии настроек не должно обрывать цикл очереди."""
    overlay.set_settings_opener(lambda: _throw(RuntimeError("boom")))
    overlay.open_settings()
    overlay._poll()  # не бросает, ошибка уходит в лог
    # Очередь жива: следующие состояния обрабатываются.
    overlay.show_recording()
    overlay._poll()
    assert overlay.root.state() == "normal"
    overlay.hide()
    overlay._poll()
    assert overlay.root.state() == "withdrawn"


def test_quit_processed_after_opener_failure(overlay):
    """Главный сценарий бага: после упавшего опенера «Выход» должен работать,
    иначе процесс висел бы навсегда без иконки в трее."""
    overlay.set_settings_opener(lambda: _throw(RuntimeError("boom")))
    overlay.open_settings()
    overlay.schedule_quit()
    overlay._poll()  # обработал и ошибку, и quit → root разрушен
    with pytest.raises(tk.TclError):
        overlay.root.winfo_exists()


def test_state_protocol(overlay):
    overlay.show_transcribing()
    overlay._poll()
    assert overlay.root.state() == "normal"
    overlay.hide()
    overlay._poll()
    assert overlay.root.state() == "withdrawn"
