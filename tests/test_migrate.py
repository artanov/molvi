from molvi import migrate


def test_migrate_data_dir_renames_old(monkeypatch, tmp_path):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    old = tmp_path / "VoiceFlow"
    old.mkdir()
    (old / "config.json").write_text("{}", encoding="utf-8")
    (old / "cuda").mkdir()

    assert migrate.migrate_data_dir() is True
    new = tmp_path / "Molvi"
    assert not old.exists()
    assert (new / "config.json").read_text(encoding="utf-8") == "{}"
    assert (new / "cuda").is_dir()


def test_migrate_data_dir_keeps_existing_new(monkeypatch, tmp_path):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    (tmp_path / "VoiceFlow").mkdir()
    new = tmp_path / "Molvi"
    new.mkdir()
    (new / "config.json").write_text("keep", encoding="utf-8")

    assert migrate.migrate_data_dir() is False
    # существующие данные Molvi не затёрты, старую папку не тронули
    assert (new / "config.json").read_text(encoding="utf-8") == "keep"
    assert (tmp_path / "VoiceFlow").exists()


def test_migrate_data_dir_noop_without_old(monkeypatch, tmp_path):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    assert migrate.migrate_data_dir() is False


def test_run_skips_in_dev(monkeypatch):
    monkeypatch.setattr(migrate.paths, "is_frozen", lambda: False)
    called = []
    monkeypatch.setattr(migrate, "migrate_data_dir", lambda: called.append("d"))
    monkeypatch.setattr(migrate, "migrate_autostart", lambda: called.append("a"))
    migrate.run()
    assert called == []
