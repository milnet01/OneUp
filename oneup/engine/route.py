"""Which way the engine reaches root: through sudo, or through OneUp's system service.

ONEUP-0249 §4.7. The engine asks once per run, through `privilege`; the window asks too,
with the environment `_resolve_engine` gives the engine (§4.10), so both read the same
answer. That is why the answer depends only on the environment it is handed, this
computer's files and polkit's list of actions, and why this module imports only the
standard library at the top: the AppImage's window imports it, and `jeepney` is imported
only on the `auto` route, after the activation file is found (INV-12).
"""

from __future__ import annotations

import os
from collections.abc import Mapping

SUDO = "sudo"
SERVICE = "service"

# The D-Bus activation file the RPM installs (§4.8). Its presence is what says the service
# is installed; the AppImage never ships it. A module constant so a test can point it at
# a scratch file instead of depending on what this machine has installed.
ACTIVATION_FILE = "/usr/share/dbus-1/system-services/za.co.antsprojectshub.OneUp1.service"

# The polkit action the service checks (oneup/service/polkit.py, SYSTEM_UPDATE). Repeated
# here, not imported: the window imports this module, and the service package needs jeepney.
PACKAGEKIT_UPDATE = "org.freedesktop.packagekit.system-update"


def engine_route(environ: Mapping[str, str]) -> str:
    """`SUDO` or `SERVICE`, from §4.7's table.

    `ONEUP_BACKEND=sudo` or `=service` forces a route. Unset, empty or `auto` takes the
    service only where it is installed, `jeepney` imports and `packagekit_registered`
    holds. Any other value takes sudo,
    the table's last row: the route that works on every install.
    """
    backend = environ.get("ONEUP_BACKEND", "")
    if backend in (SUDO, SERVICE):
        return backend
    if backend not in ("", "auto"):
        return SUDO
    if not os.path.isfile(ACTIVATION_FILE):
        return SUDO
    try:
        import jeepney  # noqa: F401 — deferred: INV-12, the sudo route runs without it
    except ImportError:
        return SUDO
    return SERVICE if packagekit_registered(environ) else SUDO


def packagekit_registered(environ: Mapping[str, str]) -> bool:
    """False only when polkit answers and its list lacks PackageKit's update action.

    The service borrows that action (§4.4), so without PackageKit every session is refused,
    and the `auto` route takes sudo instead, as the AppImage does (ONEUP-0286). No answer,
    or an error of any kind, is True: the route stays the service, whose own fallbacks
    never put a password box in front of a run nobody started by hand (§4.7). Bounded by
    `jeepney`'s 1-second connection set-up and a 2-second reply.
    """
    try:
        from jeepney import DBusAddress, MessageType, new_method_call
        from jeepney.io.blocking import open_dbus_connection

        authority = DBusAddress("/org/freedesktop/PolicyKit1/Authority",
                                bus_name="org.freedesktop.PolicyKit1",
                                interface="org.freedesktop.PolicyKit1.Authority")
        # `ONEUP_SERVICE_BUS` is the engine client's test override (service_client._bus).
        with open_dbus_connection(bus=environ.get("ONEUP_SERVICE_BUS") or "SYSTEM") as conn:
            reply = conn.send_and_get_reply(
                new_method_call(authority, "EnumerateActions", "s", ("",)), timeout=2)
        if reply.header.message_type != MessageType.method_return:
            return True
        return any(action[0] == PACKAGEKIT_UPDATE for action in reply.body[0])
    except Exception:  # noqa: BLE001 — no answer is not an answer: keep the service route
        return True
