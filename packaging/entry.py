import multiprocessing

from molvi.app import main

if __name__ == "__main__":
    # Обязательно до main(): без этого на маке multiprocessing
    # (resource_tracker/spawn из зависимостей) перезапускал весь
    # frozen-бандл, и приложение плодило собственные копии.
    multiprocessing.freeze_support()
    main()
