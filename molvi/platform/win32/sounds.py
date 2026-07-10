import winsound


def play_wav(path):
    """Асинхронно: сигнал не должен задерживать старт записи."""
    winsound.PlaySound(str(path), winsound.SND_FILENAME | winsound.SND_ASYNC)
