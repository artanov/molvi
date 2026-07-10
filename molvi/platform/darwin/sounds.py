import subprocess


def play_wav(path):
    """Асинхронно: afplay играет в своём процессе, старт записи не ждёт."""
    subprocess.Popen(
        ["afplay", str(path)],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
