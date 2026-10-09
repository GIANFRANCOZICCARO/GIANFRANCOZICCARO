import subprocess
from pathlib import Path

from file_classifier import volume_id


def test_get_volume_root_windows(monkeypatch):
    monkeypatch.setattr(volume_id, "IS_WINDOWS", True)

    root = volume_id.get_volume_root(Path("D:/Documenti/foto"))

    assert str(root) == "D:\\"


def test_get_volume_id_windows_reads_serial(monkeypatch):
    monkeypatch.setattr(volume_id, "IS_WINDOWS", True)

    class FakeKernel32:
        def GetVolumeInformationW(self, root_str, vol_buf, vol_len, serial_ref,
                                   max_len_ref, flags_ref, fs_buf, fs_len):
            serial_ref._obj.value = 0x1A2B3C4D
            return 1

    monkeypatch.setattr(volume_id, "_kernel32", FakeKernel32(), raising=False)

    vol_id = volume_id.get_volume_id(Path("D:/Documenti"))

    assert vol_id == "1A2B3C4D"


def test_get_volume_id_windows_returns_none_on_failure(monkeypatch):
    monkeypatch.setattr(volume_id, "IS_WINDOWS", True)

    class FakeKernel32:
        def GetVolumeInformationW(self, *args):
            return 0

    monkeypatch.setattr(volume_id, "_kernel32", FakeKernel32(), raising=False)

    assert volume_id.get_volume_id(Path("D:/Documenti")) is None


def test_get_volume_root_linux_uses_findmnt(monkeypatch):
    monkeypatch.setattr(volume_id, "IS_WINDOWS", False)

    def fake_run(cmd, **kwargs):
        assert cmd[:2] == ["findmnt", "-no"]
        return subprocess.CompletedProcess(cmd, 0, stdout="/mnt/dati\n", stderr="")

    monkeypatch.setattr(volume_id.subprocess, "run", fake_run)

    root = volume_id.get_volume_root(Path("/mnt/dati/foto"))

    assert root == Path("/mnt/dati")


def test_get_volume_id_linux_uses_findmnt_uuid(monkeypatch):
    monkeypatch.setattr(volume_id, "IS_WINDOWS", False)

    def fake_run(cmd, **kwargs):
        return subprocess.CompletedProcess(cmd, 0, stdout="1234-5678-ABCD\n", stderr="")

    monkeypatch.setattr(volume_id.subprocess, "run", fake_run)

    assert volume_id.get_volume_id(Path("/mnt/dati")) == "1234-5678-ABCD"


def test_get_volume_id_linux_returns_none_when_findmnt_missing(monkeypatch):
    monkeypatch.setattr(volume_id, "IS_WINDOWS", False)

    def fake_run(cmd, **kwargs):
        raise FileNotFoundError("findmnt")

    monkeypatch.setattr(volume_id.subprocess, "run", fake_run)

    assert volume_id.get_volume_id(Path("/mnt/dati")) is None
    assert volume_id.get_volume_root(Path("/mnt/dati")) is None


def test_get_volume_id_linux_returns_none_on_empty_uuid(monkeypatch):
    monkeypatch.setattr(volume_id, "IS_WINDOWS", False)

    def fake_run(cmd, **kwargs):
        return subprocess.CompletedProcess(cmd, 0, stdout="\n", stderr="")

    monkeypatch.setattr(volume_id.subprocess, "run", fake_run)

    assert volume_id.get_volume_id(Path("/mnt/dati")) is None
