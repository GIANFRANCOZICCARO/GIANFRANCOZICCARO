import pytest

from file_classifier import shutdown_guard


class _FakeKernel32:
    def __init__(self, hwnd=123):
        self.hwnd = hwnd

    def GetConsoleWindow(self):
        return self.hwnd


class _FakeUser32:
    def __init__(self):
        self.created = []
        self.destroyed = []

    def ShutdownBlockReasonCreate(self, hwnd, reason):
        self.created.append((hwnd, reason))
        return True

    def ShutdownBlockReasonDestroy(self, hwnd):
        self.destroyed.append(hwnd)
        return True


def test_guard_is_noop_outside_windows(monkeypatch):
    monkeypatch.setattr(shutdown_guard, "IS_WINDOWS", False)
    with shutdown_guard.ShutdownGuard("motivo di test") as guard:
        assert guard._active is False


def test_guard_creates_and_destroys_block_reason_on_windows(monkeypatch):
    fake_kernel32 = _FakeKernel32()
    fake_user32 = _FakeUser32()
    monkeypatch.setattr(shutdown_guard, "IS_WINDOWS", True)
    monkeypatch.setattr(shutdown_guard, "_kernel32", fake_kernel32, raising=False)
    monkeypatch.setattr(shutdown_guard, "_user32", fake_user32, raising=False)

    with shutdown_guard.ShutdownGuard("sincronizzazione in corso") as guard:
        assert guard._active is True
        assert fake_user32.created == [(123, "sincronizzazione in corso")]

    assert fake_user32.destroyed == [123]


def test_guard_handles_missing_console_window(monkeypatch):
    fake_kernel32 = _FakeKernel32(hwnd=0)
    fake_user32 = _FakeUser32()
    monkeypatch.setattr(shutdown_guard, "IS_WINDOWS", True)
    monkeypatch.setattr(shutdown_guard, "_kernel32", fake_kernel32, raising=False)
    monkeypatch.setattr(shutdown_guard, "_user32", fake_user32, raising=False)

    with shutdown_guard.ShutdownGuard("motivo") as guard:
        assert guard._active is False

    assert fake_user32.created == []
    assert fake_user32.destroyed == []


def test_guard_releases_block_even_on_exception(monkeypatch):
    fake_kernel32 = _FakeKernel32()
    fake_user32 = _FakeUser32()
    monkeypatch.setattr(shutdown_guard, "IS_WINDOWS", True)
    monkeypatch.setattr(shutdown_guard, "_kernel32", fake_kernel32, raising=False)
    monkeypatch.setattr(shutdown_guard, "_user32", fake_user32, raising=False)

    with pytest.raises(ValueError):
        with shutdown_guard.ShutdownGuard("motivo"):
            raise ValueError("boom")

    assert fake_user32.destroyed == [123]


def test_guard_can_be_reused_after_exit(monkeypatch):
    fake_kernel32 = _FakeKernel32()
    fake_user32 = _FakeUser32()
    monkeypatch.setattr(shutdown_guard, "IS_WINDOWS", True)
    monkeypatch.setattr(shutdown_guard, "_kernel32", fake_kernel32, raising=False)
    monkeypatch.setattr(shutdown_guard, "_user32", fake_user32, raising=False)

    guard = shutdown_guard.ShutdownGuard("motivo")
    with guard:
        pass
    assert guard._active is False
    with guard:
        assert guard._active is True
    assert fake_user32.created == [(123, "motivo"), (123, "motivo")]
    assert fake_user32.destroyed == [123, 123]


def test_request_shutdown_windows(monkeypatch):
    monkeypatch.setattr(shutdown_guard.platform, "system", lambda: "Windows")
    calls = []
    monkeypatch.setattr(shutdown_guard.subprocess, "run", lambda cmd, **kw: calls.append(cmd))

    shutdown_guard.request_shutdown(delay_seconds=15)

    assert calls == [["shutdown", "/s", "/t", "15"]]


def test_request_shutdown_linux(monkeypatch):
    monkeypatch.setattr(shutdown_guard.platform, "system", lambda: "Linux")
    calls = []
    monkeypatch.setattr(shutdown_guard.subprocess, "run", lambda cmd, **kw: calls.append(cmd))

    shutdown_guard.request_shutdown(delay_seconds=90)

    assert calls == [["shutdown", "-h", "+2"]]


def test_request_shutdown_unsupported_platform(monkeypatch):
    monkeypatch.setattr(shutdown_guard.platform, "system", lambda: "Darwin")

    with pytest.raises(RuntimeError):
        shutdown_guard.request_shutdown()


def test_cancel_shutdown_windows(monkeypatch):
    monkeypatch.setattr(shutdown_guard.platform, "system", lambda: "Windows")
    calls = []
    monkeypatch.setattr(shutdown_guard.subprocess, "run", lambda cmd, **kw: calls.append(cmd))

    shutdown_guard.cancel_shutdown()

    assert calls == [["shutdown", "/a"]]


def test_cancel_shutdown_linux(monkeypatch):
    monkeypatch.setattr(shutdown_guard.platform, "system", lambda: "Linux")
    calls = []
    monkeypatch.setattr(shutdown_guard.subprocess, "run", lambda cmd, **kw: calls.append(cmd))

    shutdown_guard.cancel_shutdown()

    assert calls == [["shutdown", "-c"]]


def test_cancel_shutdown_unsupported_platform_is_noop(monkeypatch):
    monkeypatch.setattr(shutdown_guard.platform, "system", lambda: "Darwin")
    calls = []
    monkeypatch.setattr(shutdown_guard.subprocess, "run", lambda cmd, **kw: calls.append(cmd))

    shutdown_guard.cancel_shutdown()

    assert calls == []
