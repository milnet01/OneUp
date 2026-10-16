"""The engine's half of OneUp's system service: open a session, run an operation.

`docs/specs/ONEUP-0249-system-service.md` §4.3. The engine stays the user's; only its
root commands travel. It names an operation from `rootops`' table and its arguments,
never an argv, and the service builds the command itself. The engine pulls the output
with `Read`, as raw bytes, then the exit status, so its own readers see what they
would see from a sudo child. No descriptor is passed: SELinux stops the system bus
taking one from the service (ONEUP-0282, INV-17).

`jeepney` is imported inside functions only. The AppImage's copied-out engine runs
on a machine without it, and its route is sudo, which never reaches this module
(INV-12). `privilege` is the only caller.
"""

from __future__ import annotations

import contextlib
import io
import os
from collections.abc import Iterator, Mapping

BUS_NAME = "za.co.antsprojectshub.OneUp1"
OBJECT_PATH = "/za/co/antsprojectshub/OneUp1"
INTERFACE = BUS_NAME
_ERROR_PREFIX = BUS_NAME + ".Error."


class Unreachable(Exception):
    """The bus, or the service on it, did not answer: a transport failure (§4.7)."""


class Refused(Exception):
    """The service answered with one of its own errors.

    `code` is the error's last word (`NotAuthorized`, `Busy`, `Invalid`, `NoSession`,
    `NotStoppable`); `reason` is its message, which for `NotAuthorized` is the reason
    code §4.4 step 6 names.
    """

    def __init__(self, code: str, reason: str) -> None:
        super().__init__(f"{code}: {reason}")
        self.code = code
        self.reason = reason


# This engine's one connection. A session belongs to the connection's unique bus name,
# so every call of the run goes through the same one (§4.3).
_CONN = None
_ROUTER = None
_SESSION = False


def _bus() -> str:
    """The system bus, or a test's private one.

    `ONEUP_SERVICE_BUS` is a test override: it points the engine at the private bus
    `tests/service-test.py` starts. It can only send the user's own engine somewhere
    else; it widens nothing on the service's side.
    """
    return os.environ.get("ONEUP_SERVICE_BUS") or "SYSTEM"


def _router():
    global _CONN, _ROUTER
    if _ROUTER is None:
        from jeepney.io.threading import DBusRouter, open_dbus_connection
        try:
            _CONN = open_dbus_connection(bus=_bus())
        except (OSError, ValueError, KeyError, TimeoutError) as exc:
            raise Unreachable(f"no bus: {exc}") from exc
        _ROUTER = DBusRouter(_CONN)
    return _ROUTER


def _call(method: str, signature: str | None = None, body: tuple = (),
          timeout: float | None = None) -> tuple:
    """One method call. Raises `Refused` for the service's errors, `Unreachable` else."""
    from jeepney import DBusAddress, HeaderFields, MessageType, new_method_call
    address = DBusAddress(OBJECT_PATH, bus_name=BUS_NAME, interface=INTERFACE)
    try:
        reply = _router().send_and_get_reply(
            new_method_call(address, method, signature, body), timeout=timeout)
    except Unreachable:
        raise
    except Exception as exc:   # jeepney raises several types; each is a transport failure
        raise Unreachable(f"{method}: {exc}") from exc
    if reply.header.message_type == MessageType.error:
        name = reply.header.fields.get(HeaderFields.error_name, "")
        text = reply.body[0] if reply.body and isinstance(reply.body[0], str) else ""
        if name.startswith(_ERROR_PREFIX):
            raise Refused(name[len(_ERROR_PREFIX):], text)
        raise Unreachable(f"{method}: {name} {text}".strip())
    return reply.body


def _variant(value: object) -> tuple[str, object]:
    """A Python value as the variant the table's signature letter names."""
    if type(value) is bool:
        return ("b", value)
    if type(value) is int:
        return ("u", value)
    if type(value) is str:
        return ("s", value)
    if type(value) is list:
        return ("as", value)
    raise Refused("Invalid", f"argument of type {type(value).__name__}")


def has_session() -> bool:
    return _SESSION


def open_session(*, interactive: bool, import_keys: bool) -> None:
    """`OpenSession`, once per run. Polkit may ask the user here, so there is no timeout."""
    global _SESSION
    _call("OpenSession", "a{sv}",
          ({"interactive": ("b", interactive), "import_keys": ("b", import_keys)},))
    _SESSION = True


class _Pull(io.RawIOBase):
    """The job's output as a byte stream, pulled with `Read` (§4.3).

    End of stream is the reply carrying the final status. A failed `Read` ends it too,
    with status 1: the client treats it as a failed job (§4.3, §6).
    """

    def __init__(self) -> None:
        super().__init__()
        self.offset = 0
        self.status: int | None = None
        self._pending = b""            # what the caller's buffer had no room for

    def readable(self) -> bool:
        return True

    def readinto(self, buffer) -> int:
        while not self._pending and self.status is None:
            try:
                data, status = _call("Read", "t", (self.offset,))
            except (Unreachable, Refused):
                self.status = 1
                break
            self._pending = bytes(data)
            self.offset += len(data)
            if not data and status != -1:
                self.status = status
        count = min(len(buffer), len(self._pending))
        buffer[:count] = self._pending[:count]
        self._pending = self._pending[count:]
        return count


class Job:
    """One running operation: its output, then its status."""

    def __init__(self) -> None:
        self._pull = _Pull()

    def lines(self) -> Iterator[str]:
        """The output decoded as `proc` decodes a child's: UTF-8, replace, any newline."""
        # The decoder reads with `read1`, one `Read` at a time, so a line goes on as
        # soon as the reply bringing its end arrives.
        yield from io.TextIOWrapper(io.BufferedReader(self._pull),
                                    encoding="utf-8", errors="replace")

    def read(self) -> str:
        return "".join(self.lines())

    def wait(self) -> int:
        """The job's status, pulling any output nobody read. A failed `Read` is 1 (§6)."""
        while self._pull.readinto(bytearray(65536)):
            pass
        return self._pull.status if self._pull.status is not None else 1


def run(op: str, args: Mapping[str, object], *, merge_stderr: bool) -> Job:
    """`Run`: start one operation; its output and status are pulled from the `Job`."""
    _call("Run", "sa{sv}b",
          (op, {name: _variant(value) for name, value in args.items()}, merge_stderr))
    return Job()


def stop() -> None:
    """`Stop`: the user's Stop, forwarded to the one stoppable operation (§4.6)."""
    _call("Stop", timeout=30)


def can_update() -> str:
    """`CanUpdate`: "yes" or "no", never a prompt (§4.4)."""
    return str(_call("CanUpdate", timeout=30)[0])


def close() -> None:
    """End the session, then the connection. Quiet: this runs on the way out."""
    global _CONN, _ROUTER, _SESSION
    if _SESSION:
        with contextlib.suppress(Unreachable, Refused):
            _call("CloseSession", timeout=30)
        _SESSION = False
    if _ROUTER is not None:
        with contextlib.suppress(Exception):
            _ROUTER.close()
        with contextlib.suppress(Exception):
            _CONN.close()
    _CONN = _ROUTER = None
