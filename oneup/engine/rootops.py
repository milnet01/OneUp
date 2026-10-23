"""Every command the engine runs as root, defined once.

`docs/specs/ONEUP-0249-system-service.md` §4.2. Each operation is a name, the
typed arguments it accepts, and a builder that returns the argv. Both routes to
root build from here: the sudo route prefixes `sudo`, and the system service
runs the argv itself. So the two cannot drift (INV-4).

One operation differs by route. On the sudo route, `system-download` keeps the
guard or stop-wrapper argv `steps._download_pass` builds, because there the
engine cannot signal a root child. Its row here is the service route's.

The validators here check SHAPE, and every one fails closed (`security.md`
§4.2). The checks that need state live in the service, which holds it: that an
alias names a repository in `/etc/zypp/repos.d`, that `repo-enable` undoes this
session's own disable, and that every name `orphans-remove` gets is one zypper
just called unneeded (§4.2, §4.5).

Standard library and engine siblings only, so the AppImage's copied-out engine
imports it on a machine without the service (INV-12).
"""

from __future__ import annotations

import os
import time
from collections.abc import Callable, Mapping
from typing import NamedTuple

from . import privilege, repos, steps


class Invalid(ValueError):
    """An operation or argument the table refuses. Nothing is run."""


# §4.5's limits. Anything larger is refused rather than truncated.
MAX_NAMES = 5000
MAX_STRING_BYTES = 255

_ALGORITHMS = ("number", "timeline")

# How long the check's dry run may take, refresh included, before `timeout` ends it
# (ONEUP-0329 §4.1). Read where the argv is built: on the service route, the service.
# `privilege.BUSY_WAIT_SECONDS` is this plus a margin; change the two together.
CHECK_DRY_RUN_SECONDS = int(os.environ.get("ONEUP_CHECK_DRY_RUN_SECONDS") or "180")


def _now() -> str:
    """The snapshot description's clock. The engine passes no text (§4.2)."""
    return time.strftime("%Y-%m-%d %H:%M")


def _txn(args: Mapping[str, object], cdn_dir: str) -> list[str]:
    """`env LC_ALL=C` + the system transaction, against the CDN copy when asked.

    The locale is an ARGV PREFIX because sudo resets the environment, and the
    drop-in grants the literal words `env LC_ALL=C zypper *`.
    """
    if args["cdn"] and not cdn_dir:
        raise Invalid("cdn asked for with no CDN directory")
    return ["env", "LC_ALL=C", *steps.system_txn_argv(cdn_dir if args["cdn"] else "")]


def _gpg(args: Mapping[str, object]) -> list[str]:
    return ["--gpg-auto-import-keys"] if args["import_keys"] else []


def _timeout() -> str:
    """The same `timeout` path the drop-in grants (ONEUP-0092 §4.2), and the bare
    name only where none was found, as the refresh call site did before this table."""
    granted = privilege.REFRESH_SUDO_ARGV
    return granted[0] if granted else "timeout"


def _refresh(args: Mapping[str, object], _cdn_dir: str) -> list[str]:
    return [_timeout(), str(args["budget"]), "zypper", "--non-interactive", *_gpg(args),
            "refresh", str(args["alias"])]


def _check_dry_run(_args: Mapping[str, object], _cdn_dir: str) -> list[str]:
    """The update's own transaction, solved but not run, as XML (ONEUP-0329 §4.1).

    `--xmlout` is a global option, so it goes straight after `zypper`. No
    `--no-refresh`: the check refreshes first, as the update does. Bounded by
    `timeout` rather than by the service, which never stops a job its caller left.
    """
    zypper, *rest = steps.system_txn_argv("")
    return [_timeout(), str(CHECK_DRY_RUN_SECONDS), "env", "LC_ALL=C", zypper, "--xmlout",
            *rest, "--dry-run"]


def _cache_size(_args: Mapping[str, object], _cdn_dir: str) -> list[str]:
    if privilege.CACHE_DU_ARGV is None:
        raise Invalid("du is not installed")
    return list(privilege.CACHE_DU_ARGV)


def _snapshot_list(args: Mapping[str, object], _cdn_dir: str) -> list[str]:
    if args["csv"]:
        return ["snapper", "--machine-readable", "csv", "list",
                "--columns", "number,date,description"]
    return ["snapper", "--no-headers", "list"]


def _fixed(*argv: str) -> Callable[[Mapping[str, object], str], list[str]]:
    return lambda _args, _cdn_dir: list(argv)


class Op(NamedTuple):
    args: dict[str, str]     # name -> D-Bus signature: b, s, u or as
    build: Callable[[Mapping[str, object], str], list[str]]


OPS: dict[str, Op] = {
    "size-dry-run": Op({"cdn": "b"}, lambda a, d: [*_txn(a, d), "--dry-run"]),
    "check-dry-run": Op({}, _check_dry_run),
    "system-download": Op({"cdn": "b"}, lambda a, d: [*_txn(a, d), "--download-only"]),
    "system-commit": Op({"cdn": "b"}, _txn),
    "repo-refresh": Op({"alias": "s", "import_keys": "b", "budget": "u"}, _refresh),
    "repo-refresh-all": Op(
        {"import_keys": "b"},
        lambda a, _d: ["zypper", "--non-interactive", *_gpg(a), "refresh"]),
    "repo-disable": Op(
        {"alias": "s"},
        lambda a, _d: ["zypper", "--non-interactive", "modifyrepo", "--disable", a["alias"]]),
    "repo-enable": Op(
        {"alias": "s"},
        lambda a, _d: ["zypper", "--non-interactive", "modifyrepo", "--enable", a["alias"]]),
    "release-lock": Op({}, _fixed("systemctl", "stop", "packagekit")),
    "snapshot-create": Op(
        {},
        lambda _a, _d: ["snapper", "create", "--description", "OneUp pre-update " + _now(),
                        "--cleanup-algorithm", "number", "--print-number"]),
    "snapshot-list": Op({"csv": "b"}, _snapshot_list),
    "snapshot-thin": Op({"algorithm": "s"},
                        lambda a, _d: ["snapper", "cleanup", a["algorithm"]]),
    "restart-list": Op({}, _fixed("zypper", "ps", "-sss")),
    "flatpak-system-update": Op({}, _fixed("flatpak", "update", "--system", "-y")),
    "flatpak-system-unused": Op({}, _fixed("flatpak", "uninstall", "--system", "--unused",
                                           "-y")),
    "orphans-unneeded": Op({}, _fixed("zypper", "--non-interactive", "--no-refresh",
                                      "packages", "--unneeded")),
    "orphans-orphaned": Op({}, _fixed("zypper", "--non-interactive", "--no-refresh",
                                      "packages", "--orphaned")),
    "orphans-remove": Op(
        {"names": "as"},
        lambda a, _d: ["zypper", "--non-interactive", "remove", "--clean-deps", *a["names"]]),
    "cache-clean": Op({}, _fixed("zypper", "--non-interactive", "clean")),
    "cache-size": Op({}, _cache_size),
}


def _short(text: str) -> bool:
    return len(text.encode("utf-8", "surrogateescape")) <= MAX_STRING_BYTES


def _check_type(name: str, sig: str, value: object) -> None:
    """The D-Bus signature, checked exactly: a bool is not a `u`, and vice versa."""
    if sig == "b":
        ok = type(value) is bool
    elif sig == "s":
        ok = type(value) is str and _short(value)
    elif sig == "u":
        ok = type(value) is int and 0 <= value <= 0xFFFFFFFF
    else:   # "as"
        ok = (type(value) is list and len(value) <= MAX_NAMES
              and all(type(v) is str and _short(v) for v in value))
    if not ok:
        raise Invalid(f"argument {name} is not a valid {sig}")


def _check_value(name: str, value: object) -> None:
    """Each argument's own validator (§4.2). Shape only; see the module docstring."""
    if name == "alias" and not repos.valid_alias(value):
        raise Invalid("unsafe repository alias")
    if name == "budget" and value <= 0:
        raise Invalid("budget must be a positive number of seconds")
    if name == "algorithm" and value not in _ALGORITHMS:
        raise Invalid("unknown snapper cleanup algorithm")
    if name == "names" and (not value or not all(steps.valid_package(n) for n in value)):
        raise Invalid("names must be a non-empty list of package names")


def build(op: str, args: Mapping[str, object] | None = None, *, cdn_dir: str = "") -> list[str]:
    """The argv for `op`, before any `sudo`, or `Invalid` and nothing to run.

    `cdn_dir` is where the caller's own CDN copy of the repository files lives.
    It is never a client's argument: the service passes the directory it built
    for the session, and the sudo route the one the engine built (§4.2, `cdn`).
    """
    spec = OPS.get(op)
    if spec is None:
        raise Invalid(f"unknown operation {op!r}")
    args = dict(args or {})
    if set(args) != set(spec.args):
        raise Invalid(f"{op} takes {sorted(spec.args)}, got {sorted(args)}")
    for name, sig in spec.args.items():
        _check_type(name, sig, args[name])
        _check_value(name, args[name])
    return spec.build(args, cdn_dir)
