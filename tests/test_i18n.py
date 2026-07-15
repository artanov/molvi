import re

import pytest

from molvi import i18n


@pytest.fixture(autouse=True)
def _reset_language():
    # Каждый тест начинает с ru — как приложение до чтения конфига.
    i18n.set_language("ru")
    yield
    i18n.set_language("ru")


def test_ru_en_same_keys():
    assert set(i18n.RU) == set(i18n.EN)


# wizard.language.title намеренно двуязычный («Язык / Language»):
# шаг выбора языка виден ДО выбора — оба названия обязаны быть.
_BILINGUAL_KEYS = {"wizard.language.title"}


def test_en_has_no_cyrillic():
    for key, value in i18n.EN.items():
        if key in _BILINGUAL_KEYS:
            continue
        assert not re.search("[А-Яа-яЁё]", value), f"кириллица в EN[{key}]"


def test_tr_returns_russian_by_default():
    assert i18n.tr("tray.quit") == "Выход"


def test_tr_switches_to_english():
    i18n.set_language("en")
    assert i18n.tr("tray.quit") == "Quit"


def test_tr_formats_placeholders():
    i18n.set_language("en")
    assert "boom" in i18n.tr("controller.mic_unavailable", exc="boom")


def test_tr_unknown_key_returns_key():
    assert i18n.tr("no.such.key") == "no.such.key"


def test_tr_missing_format_arg_returns_raw():
    # Опечатка в имени параметра не должна ронять UI.
    raw = i18n.tr("controller.mic_unavailable")
    assert "{exc}" in raw


def test_set_language_auto_uses_system(monkeypatch):
    monkeypatch.setattr(i18n, "system_language", lambda: "en")
    i18n.set_language("auto")
    assert i18n.current_language() == "en"


def test_set_language_unknown_falls_back_to_en():
    i18n.set_language("de")
    assert i18n.current_language() == "en"
