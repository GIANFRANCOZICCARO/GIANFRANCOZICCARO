from collections import namedtuple

from file_classifier import drives

_Partition = namedtuple("sdiskpart", ["device", "mountpoint", "fstype", "opts"])


def test_list_drives_filters_virtual_filesystems(monkeypatch):
    fake_partitions = [
        _Partition("/dev/sda1", "/", "ext4", "rw"),
        _Partition("/dev/sdb1", "/mnt/dati", "ntfs", "rw"),
        _Partition("proc", "/proc", "proc", "rw"),
        _Partition("tmpfs", "/run", "tmpfs", "rw"),
    ]
    monkeypatch.setattr(drives.psutil, "disk_partitions", lambda all=False: fake_partitions)

    assert drives.list_drives() == ["/", "/mnt/dati"]


def test_list_drives_windows_style(monkeypatch):
    fake_partitions = [
        _Partition("C:\\", "C:\\", "NTFS", "rw"),
        _Partition("D:\\", "D:\\", "NTFS", "rw"),
    ]
    monkeypatch.setattr(drives.psutil, "disk_partitions", lambda all=False: fake_partitions)

    assert drives.list_drives() == ["C:\\", "D:\\"]


def test_list_drives_empty(monkeypatch):
    monkeypatch.setattr(drives.psutil, "disk_partitions", lambda all=False: [])
    assert drives.list_drives() == []
