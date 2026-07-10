"""Каталог mlx-моделей — единственный источник для transcriber, fetch и UI.

Без тяжёлых импортов: модуль читают и wizard (до загрузки движка),
и Windows-тесты. Имена ключей общие с Windows-версией — конфиг переносим.
"""

# имя из конфига → репозиторий mlx-community на HuggingFace
REPOS = {
    "large-v3-turbo": "mlx-community/whisper-large-v3-turbo",
    "large-v3": "mlx-community/whisper-large-v3-mlx",
    "medium": "mlx-community/whisper-medium-mlx",
    "small": "mlx-community/whisper-small-mlx",
    "base": "mlx-community/whisper-base-mlx",
}

# примерный полный размер, байты — для прогресса по росту HF-кэша
SIZES = {
    "large-v3-turbo": 1_620_000_000,
    "large-v3": 3_100_000_000,
    "medium": 1_530_000_000,
    "small": 500_000_000,
    "base": 150_000_000,
}
