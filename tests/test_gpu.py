import subprocess
from types import SimpleNamespace

import molvi.gpu as gpu


def _fake_run(stdout, returncode=0):
    def run(*a, **kw):
        return SimpleNamespace(stdout=stdout, returncode=returncode)
    return run


def test_detect_parses_nvidia_smi(monkeypatch):
    monkeypatch.setattr(gpu.subprocess, "run",
                        _fake_run("NVIDIA GeForce RTX 4080, 16376\n"))
    assert gpu.detect_nvidia() == {"name": "NVIDIA GeForce RTX 4080", "vram_mb": 16376}


def test_detect_no_nvidia_smi(monkeypatch):
    def raise_oserror(*a, **kw):
        raise OSError("not found")
    monkeypatch.setattr(gpu.subprocess, "run", raise_oserror)
    assert gpu.detect_nvidia() is None


def test_detect_bad_output(monkeypatch):
    monkeypatch.setattr(gpu.subprocess, "run", _fake_run("garbage"))
    assert gpu.detect_nvidia() is None
    monkeypatch.setattr(gpu.subprocess, "run", _fake_run("", returncode=1))
    assert gpu.detect_nvidia() is None


def test_recommend():
    assert gpu.recommend({"name": "RTX 4080", "vram_mb": 16376}) == ("large-v3", "auto")
    assert gpu.recommend({"name": "GT 1030", "vram_mb": 2048}) == ("base", "cpu")
    assert gpu.recommend(None) == ("base", "cpu")
