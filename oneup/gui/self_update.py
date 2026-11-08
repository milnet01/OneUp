"""OneUp updating itself: what is offered, proving a download genuine, the swap, the relaunch.

`docs/specs/ONEUP-0112-self-update.md` §4.2 to §4.8. No Qt and no network: the
requests are `app_update.py`'s alone (INV-15), and this module only judges and
acts on the bytes they bring back. Nothing here ever asks for root (INV-9).
"""
from __future__ import annotations

import binascii
import contextlib
import os
import re
import stat
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

from . import paths, update_key

ASSET = "OneUp-x86_64.AppImage"
SIG_ASSET = ASSET + ".sig"
SIG_BYTES = 64                          # a raw Ed25519 signature
PACKAGE_HOME = Path("/usr/share/oneup")  # packaging/rpm/oneup.spec's %install


class UpdateVerificationError(Exception):
    """The download could not be proved to come from OneUp's author."""


class UpdateInstallError(Exception):
    """The AppImage's folder is not writable; the argument is that folder."""


def parse_version(tag) -> tuple[int, int, int] | None:
    """'v2.1.0' / '2.1.0' -> (2, 1, 0). Anything else -> None: exactly three
    dot-separated parts, each ASCII digits, one leading v/V allowed (INV-2).
    `'¹'.isdigit()` is true, hence the isascii()."""
    if not isinstance(tag, str):
        return None
    if tag.startswith(("v", "V")):
        tag = tag[1:]
    parts = tag.split(".")
    if len(parts) != 3 or not all(p.isascii() and p.isdigit() for p in parts):
        return None
    return int(parts[0]), int(parts[1]), int(parts[2])


def version_text(version: tuple[int, int, int]) -> str:
    return ".".join(map(str, version))


@dataclass(frozen=True)
class Release:
    version: tuple[int, int, int]
    body: str                    # the CHANGELOG section, Markdown; may be ""
    appimage_url: str | None     # browser_download_url of OneUp-x86_64.AppImage
    sig_url: str | None          # browser_download_url of OneUp-x86_64.AppImage.sig
    appimage_size: int           # the asset's "size", 0 when absent


def _assets(entry: dict) -> tuple[str | None, str | None, int]:
    urls: dict[str, str] = {}
    size = 0
    assets = entry.get("assets")
    for asset in assets if isinstance(assets, list) else []:
        if not isinstance(asset, dict) or asset.get("name") not in (ASSET, SIG_ASSET):
            continue
        url = asset.get("browser_download_url")
        if not (isinstance(url, str) and url.startswith("https://")):
            continue                     # a non-HTTPS URL counts as absent
        urls[asset["name"]] = url
        if asset["name"] == ASSET:
            n = asset.get("size")
            size = n if type(n) is int and n > 0 else 0
    return urls.get(ASSET), urls.get(SIG_ASSET), size


def releases_from_json(data) -> list[Release] | None:
    """None when `data` is not a list: the caller reports an unreadable reply. Otherwise
    every entry that is a dict, not draft, not prerelease, whose tag_name parses, highest
    version first. A malformed entry is dropped, never raised (INV-3)."""
    if not isinstance(data, list):
        return None
    out = []
    for entry in data:
        if not isinstance(entry, dict) or entry.get("draft") or entry.get("prerelease"):
            continue
        version = parse_version(entry.get("tag_name"))
        if version is None:
            continue
        body = entry.get("body")
        out.append(Release(version, body if isinstance(body, str) else "", *_assets(entry)))
    out.sort(key=lambda r: r.version, reverse=True)
    return out


def changelog(releases, installed, offered) -> list[Release]:
    """installed < r.version <= offered, highest version first."""
    return sorted((r for r in releases if installed < r.version <= offered),
                  key=lambda r: r.version, reverse=True)


def install_kind() -> str:
    """'appimage' — frozen and $APPIMAGE names an existing file; 'package' — not frozen
    and paths.HERE resolves to /usr/share/oneup; 'checkout' — anything else (INV-1).
    $APPIMAGE alone is inherited by anything an AppImage starts, so it is not proof."""
    if getattr(sys, "frozen", False):
        appimage = os.environ.get("APPIMAGE", "")
        return "appimage" if appimage and os.path.isfile(appimage) else "checkout"
    return "package" if Path(os.path.realpath(paths.HERE)) == PACKAGE_HOME else "checkout"


def signed_message(data: bytes, version: str) -> bytes:
    """What the signature covers: the asset's name and the release's X.Y.Z, then its
    bytes. Binding the version means a genuine older AppImage and its .sig, re-attached
    to a newer tag, fail (§4.5). `packaging/sign-release.py` signs this same message."""
    return f"{ASSET} {version}\n".encode() + data


def verify(data: bytes, sig: bytes, version: str) -> None:
    """Return only when `sig` is the release key's signature of `data` for `version`;
    raise UpdateVerificationError otherwise, a missing key or library included (INV-6)."""
    if len(sig) != SIG_BYTES:
        raise UpdateVerificationError(f"the signature is {len(sig)} bytes, not {SIG_BYTES}")
    try:
        from cryptography.exceptions import InvalidSignature
        key = update_key.public_key()
    except (ImportError, ValueError, binascii.Error) as exc:
        raise UpdateVerificationError(str(exc)) from exc
    try:
        key.verify(sig, signed_message(data, version))
    except InvalidSignature as exc:
        raise UpdateVerificationError("the signature does not match") from exc


def install(data: bytes, appimage: str) -> Path:
    """Replace the AppImage `appimage` names with `data`, atomically, keeping its mode
    (§4.6, INV-8). The temp is made beside the real file, because `os.replace` across
    filesystems raises EXDEV; `realpath` because $APPIMAGE may be a symlink, which
    `os.replace` would replace instead of the file. An unwritable folder is refused
    before anything is written (INV-9). Any failure before the replace leaves the
    original untouched and no temp behind. Returns the real path."""
    target = Path(os.path.realpath(appimage))
    if not os.access(target.parent, os.W_OK):
        raise UpdateInstallError(str(target.parent))
    mode = stat.S_IMODE(target.stat().st_mode)
    fd, temp = tempfile.mkstemp(prefix=".OneUp-update-", dir=target.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            os.fchmod(handle.fileno(), mode)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp, target)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(temp)
        raise
    # The directory entry too. Best-effort: the swap has already happened.
    with contextlib.suppress(OSError):
        dir_fd = os.open(target.parent, os.O_RDONLY)
        try:
            os.fsync(dir_fd)
        finally:
            os.close(dir_fd)
    return target


# The waiter: its arguments are the pids to outlive, then "--", then the argv to exec.
# It polls every 0.1 s, for at most 60 s. A zombie counts as gone — `kill -0` succeeds
# on one, and whoever started the old process reaps it — and its state is the field
# after the LAST ')' of /proc/<pid>/stat, since the command name may hold any byte.
# The argv arrives as "$@", so no path is ever parsed by the shell.
WAITER = r"""
pids=
while [ "$#" -gt 0 ] && [ "$1" != -- ]; do pids="$pids $1"; shift; done
[ "$#" -gt 0 ] && shift
i=0
while [ "$i" -lt 600 ]; do
    alive=
    for p in $pids; do
        if kill -0 "$p" 2>/dev/null; then
            state=$(sed 's/.*) //' "/proc/$p/stat" 2>/dev/null | cut -c1)
            [ "$state" = Z ] || alive=1
        fi
    done
    [ -z "$alive" ] && break
    i=$((i + 1))
    sleep 0.1
done
exec "$@"
"""

# The AppImage runtime's markers of the image now running; the new one derives its own.
_STALE_APPIMAGE_ENV = ("APPDIR", "APPIMAGE", "ARGV0", "OWD")
_LOADER_ENV = ("LD_LIBRARY_PATH", "LD_PRELOAD")


def relaunch_env(environ=None) -> dict[str, str]:
    """The waiter's environment, which the relaunched OneUp inherits (§4.7, INV-10).

    PYINSTALLER_RESET_ENVIRONMENT=1 is PyInstaller's supported restart signal: the new
    bootloader starts fresh instead of taking itself for a worker of the old run. The
    loader variables go back to their pre-launch `<VAR>_ORIG` values, or are dropped,
    so the system /bin/sh never loads the bundle's libraries (finbreak 0.1.6→0.1.7)."""
    env = dict(os.environ if environ is None else environ)
    for name in _STALE_APPIMAGE_ENV:
        env.pop(name, None)
    env["PYINSTALLER_RESET_ENVIRONMENT"] = "1"
    for var in _LOADER_ENV:
        original = env.pop(f"{var}_ORIG", None)
        if original:
            env[var] = original
        else:
            env.pop(var, None)
    return env


def relaunch_pids() -> list[int]:
    """This process, and its parent when that runs the same executable: the onefile
    bootloader, whose exit unmounts the bundle (finbreak FIBR-0392)."""
    pids = [os.getpid()]
    with contextlib.suppress(OSError):
        ppid = os.getppid()
        if ppid > 1 and os.readlink(f"/proc/{ppid}/exe") == os.readlink("/proc/self/exe"):
            pids.append(ppid)
    return pids


def relaunch_command(argv: list[str]) -> list[str]:
    return ["/bin/sh", "-c", WAITER, "sh", *map(str, relaunch_pids()), "--", *argv]


def relaunch(argv: list[str]) -> None:
    """Start a detached waiter that runs `argv` once this process has gone. Never
    `os.execv`: it cannot replace a busy FUSE mount, and the onefile bootloader takes
    the result for a worker of the old run (finbreak 0.1.2→0.1.3). Waiting also lets
    the new copy own the single-instance socket. Raises OSError when it cannot start.
    The caller then quits."""
    subprocess.Popen(  # noqa: S603 — the fixed waiter; argv is ours, passed as "$@".
        relaunch_command(argv), start_new_session=True, env=relaunch_env(),
        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        close_fds=True)


def restart_argv() -> list[str]:
    """How a package install or a checkout starts again."""
    return [sys.executable, str(paths.HERE / "updater.py")]


def disk_version() -> tuple[int, int, int] | None:
    """APP_VERSION as written in paths.HERE / 'oneup' / '__init__.py' — what a restart
    would load. None when the file is unreadable or the line absent (§4.8)."""
    try:
        text = (paths.HERE / "oneup" / "__init__.py").read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None
    found = re.search(r'^APP_VERSION = "([^"]+)"$', text, re.MULTILINE)
    return parse_version(found.group(1)) if found else None
