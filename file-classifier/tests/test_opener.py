import subprocess

import pytest

from file_classifier import opener


def test_reveal_raises_if_missing(tmp_path):
    with pytest.raises(opener.OpenError):
        opener.reveal_in_file_manager(tmp_path / "ghost.txt")


def test_open_file_raises_if_missing(tmp_path):
    with pytest.raises(opener.OpenError):
        opener.open_file(tmp_path / "ghost.txt")


def test_reveal_windows_uses_explorer_select(tmp_path, monkeypatch):
    target = tmp_path / "a.txt"
    target.write_text("x")
    monkeypatch.setattr(opener.platform, "system", lambda: "Windows")
    calls = []
    monkeypatch.setattr(opener.subprocess, "run", lambda cmd, **kw: calls.append(cmd))

    opener.reveal_in_file_manager(target)

    assert calls == [["explorer", f"/select,{target}"]]


def test_reveal_macos_uses_open_dash_r(tmp_path, monkeypatch):
    target = tmp_path / "a.txt"
    target.write_text("x")
    monkeypatch.setattr(opener.platform, "system", lambda: "Darwin")
    calls = []
    monkeypatch.setattr(opener.subprocess, "run", lambda cmd, **kw: calls.append(cmd))

    opener.reveal_in_file_manager(target)

    assert calls == [["open", "-R", str(target)]]


def test_reveal_linux_opens_parent_directory(tmp_path, monkeypatch):
    target = tmp_path / "a.txt"
    target.write_text("x")
    monkeypatch.setattr(opener.platform, "system", lambda: "Linux")
    calls = []
    monkeypatch.setattr(opener.subprocess, "run", lambda cmd, **kw: calls.append(cmd))

    opener.reveal_in_file_manager(target)

    assert calls == [["xdg-open", str(target.parent)]]


def test_open_file_with_specific_program(tmp_path, monkeypatch):
    target = tmp_path / "a.txt"
    target.write_text("x")
    calls = []
    monkeypatch.setattr(opener.subprocess, "Popen", lambda cmd, **kw: calls.append(cmd))

    opener.open_file(target, program="notepad.exe")

    assert calls == [["notepad.exe", str(target)]]


def test_open_file_default_app_windows(tmp_path, monkeypatch):
    target = tmp_path / "a.txt"
    target.write_text("x")
    monkeypatch.setattr(opener.platform, "system", lambda: "Windows")
    calls = []
    monkeypatch.setattr(opener.os, "startfile", lambda p: calls.append(p), raising=False)

    opener.open_file(target)

    assert calls == [str(target)]


def test_open_file_default_app_linux(tmp_path, monkeypatch):
    target = tmp_path / "a.txt"
    target.write_text("x")
    monkeypatch.setattr(opener.platform, "system", lambda: "Linux")
    calls = []
    monkeypatch.setattr(opener.subprocess, "run", lambda cmd, **kw: calls.append(cmd))

    opener.open_file(target)

    assert calls == [["xdg-open", str(target)]]


def test_open_file_missing_program_raises(tmp_path, monkeypatch):
    target = tmp_path / "a.txt"
    target.write_text("x")

    def fake_popen(cmd, **kw):
        raise FileNotFoundError(cmd[0])

    monkeypatch.setattr(opener.subprocess, "Popen", fake_popen)

    with pytest.raises(opener.OpenError):
        opener.open_file(target, program="programma-inesistente")


def test_reveal_failure_raises_open_error(tmp_path, monkeypatch):
    target = tmp_path / "a.txt"
    target.write_text("x")
    monkeypatch.setattr(opener.platform, "system", lambda: "Linux")

    def fake_run(cmd, **kw):
        raise subprocess.CalledProcessError(1, cmd)

    monkeypatch.setattr(opener.subprocess, "run", fake_run)

    with pytest.raises(opener.OpenError):
        opener.reveal_in_file_manager(target)
