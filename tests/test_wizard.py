from molvi.wizard import resolve_device, vram_label


def test_resolve_device_large_always_tries_gpu():
    assert resolve_device("large-v3", "cpu") == "auto"
    assert resolve_device("large-v3", "auto") == "auto"


def test_resolve_device_small_follows_hardware_recommendation():
    assert resolve_device("small", "cpu") == "cpu"
    assert resolve_device("small", "auto") == "auto"
    assert resolve_device("base", "cpu") == "cpu"


def test_resolve_device_independent_of_click_order():
    # Слабый GPU (рекомендация cpu): «large-v3, потом small» и «сразу small»
    # должны давать одинаковый device — раньше результат зависел от порядка.
    via_detour = resolve_device("small", "cpu")   # после клика large-v3
    direct = resolve_device("small", "cpu")
    assert via_detour == direct == "cpu"


def test_vram_label():
    assert vram_label(8192) == "8 ГБ"
    assert vram_label(6000) == "5 ГБ"
    assert vram_label(512) == "512 МБ"  # не «0 ГБ»
