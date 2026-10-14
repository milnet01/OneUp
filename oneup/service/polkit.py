"""Ask polkit whether a caller may: §4.4. Any error is a refusal.

The subject is the caller's unique bus name, never a pid: CVE-2013-4288 was a race in
the pid-based subject. A caller who left mid-check gets `denied`, never a yes
(CVE-2021-3560).
"""

from __future__ import annotations

from jeepney import DBusAddress, MessageType, new_method_call

SYSTEM_UPDATE = "org.freedesktop.packagekit.system-update"
TRUST_SIGNING_KEY = "org.freedesktop.packagekit.system-trust-signing-key"

_AUTHORITY = DBusAddress("/org/freedesktop/PolicyKit1/Authority",
                         bus_name="org.freedesktop.PolicyKit1",
                         interface="org.freedesktop.PolicyKit1.Authority")
_ALLOW_USER_INTERACTION = 0x1

# §4.4 step 6's reason codes. A yes is the one other answer.
YES = "yes"
DISMISSED = "dismissed"
CHALLENGE = "challenge"
DENIED = "denied"


def check(router, caller: str, action: str, *, interactive: bool) -> str:
    """`YES`, or the reason code for a refusal. Blocks while polkit asks the user."""
    subject = ("system-bus-name", {"name": ("s", caller)})
    flags = _ALLOW_USER_INTERACTION if interactive else 0
    msg = new_method_call(_AUTHORITY, "CheckAuthorization", "(sa{sv})sa{ss}us",
                          (subject, action, {}, flags, ""))
    try:
        reply = router.send_and_get_reply(msg)
        if reply.header.message_type != MessageType.method_return:
            return DENIED
        authorized, challenge, details = reply.body[0]
    except Exception:  # noqa: BLE001 — unreachable, unregistered, malformed: each refuses
        return DENIED
    if authorized is True:
        return YES
    if details.get("polkit.dismissed") == "true":
        return DISMISSED
    if challenge is True:
        return CHALLENGE
    return DENIED


def caller_uid(router, caller: str) -> int | None:
    """The caller's uid from the bus itself, or None when it cannot be resolved."""
    bus = DBusAddress("/org/freedesktop/DBus", bus_name="org.freedesktop.DBus",
                      interface="org.freedesktop.DBus")
    try:
        reply = router.send_and_get_reply(
            new_method_call(bus, "GetConnectionUnixUser", "s", (caller,)), timeout=10)
    except Exception:  # noqa: BLE001 — an unresolvable caller is refused
        return None
    if reply.header.message_type != MessageType.method_return:
        return None
    return int(reply.body[0])
