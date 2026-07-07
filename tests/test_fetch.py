import zipfile

import voiceflow.fetch as fetch


def test_pick_wheel_url_latest_win64():
    pypi = {"releases": {
        "1.0.0": [{"filename": "pkg-1.0.0-py3-none-win_amd64.whl", "url": "http://old"}],
        "2.0.1": [
            {"filename": "pkg-2.0.1-py3-none-manylinux.whl", "url": "http://linux"},
            {"filename": "pkg-2.0.1-py3-none-win_amd64.whl", "url": "http://new"},
        ],
        "2.0.2": [{"filename": "pkg-2.0.2-py3-none-manylinux.whl", "url": "http://linux-only"}],
    }}
    assert fetch.pick_wheel_url(pypi) == "http://new"


def test_pick_wheel_url_skips_yanked_and_raises():
    pypi = {"releases": {"1.0": [
        {"filename": "p-1.0-win_amd64.whl", "url": "http://y", "yanked": True},
    ]}}
    import pytest
    with pytest.raises(LookupError):
        fetch.pick_wheel_url(pypi)


def test_extract_dlls(tmp_path):
    whl = tmp_path / "fake.whl"
    with zipfile.ZipFile(whl, "w") as z:
        z.writestr("nvidia/cublas/bin/cublas64_12.dll", b"DLL1")
        z.writestr("nvidia/cublas/bin/readme.txt", b"nope")
        z.writestr("nvidia/cublas/lib/other.dll", b"not-bin")
    out = tmp_path / "cuda"
    names = fetch.extract_dlls(whl, out)
    assert names == ["cublas64_12.dll"]
    assert (out / "cublas64_12.dll").read_bytes() == b"DLL1"
    assert not (out / "readme.txt").exists()


def test_extract_dlls_rejects_zip_slip(monkeypatch, tmp_path):
    # Настоящий zipfile на Windows нормализует "\" в "/" при чтении архива
    # (ZipInfo.__init__ заменяет os.sep), поэтому вредоносное имя с бэкслешами
    # подсовываем через фейковый ZipFile — так проверяется сама защита.
    class FakeInfo:
        filename = "nvidia/bin/..\\..\\evil.dll"

    class FakeZip:
        def __init__(self, path):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def infolist(self):
            return [FakeInfo()]

        def read(self, info):
            return b"BAD"

    monkeypatch.setattr(fetch.zipfile, "ZipFile", FakeZip)
    out = tmp_path / "deep" / "cuda"
    names = fetch.extract_dlls(tmp_path / "evil.whl", out)
    assert names == []
    assert list(out.iterdir()) == []
    assert not list(tmp_path.rglob("evil.dll"))


def test_download_reports_progress(monkeypatch, tmp_path):
    chunks = [b"aa", b"bb", b""]

    class FakeResp:
        headers = {"Content-Length": "4"}
        def read(self, n):
            return chunks.pop(0)
        def __enter__(self):
            return self
        def __exit__(self, *a):
            return False

    monkeypatch.setattr(fetch.urllib.request, "urlopen", lambda *a, **kw: FakeResp())
    progress = []
    dest = tmp_path / "f.bin"
    fetch.download("http://x", dest, lambda d, t: progress.append((d, t)))
    assert dest.read_bytes() == b"aabb"
    assert progress == [(2, 4), (4, 4)]


def test_model_constants():
    assert fetch.MODEL_REPOS["large-v3"] == "Systran/faster-whisper-large-v3"
    assert set(fetch.MODEL_REPOS) == set(fetch.MODEL_SIZES) == {"large-v3", "small", "base"}
