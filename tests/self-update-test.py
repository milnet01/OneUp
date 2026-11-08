#!/usr/bin/env python3
"""The self-update's Qt-free half: versions, the release list, the signature, the swap,
the relaunch, and the signing script (`docs/specs/ONEUP-0112-self-update.md` §7).

Stdlib plus `cryptography`, a throwaway key, synthetic bytes, and no network
(`docs/standards/testing.md` §2). Exits 0 on success, 1 on any failure, and 77 when
`cryptography` is absent — which `release.yml` treats as a failure, since the
AppImage build installs it.
"""
from __future__ import annotations

import ast
import base64
import importlib.util
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

try:
    import cryptography  # noqa: F401 — only its presence is asked
except ImportError:
    print("cryptography is not installed — skipping (exit 77)")
    sys.exit(77)

from oneup.gui import paths, self_update, update_key  # noqa: E402 — after sys.path

PASS = 0
FAIL = 0


def check(name: str, cond: bool):
    global PASS, FAIL
    if cond:
        print(f"  ok   - {name}")
        PASS += 1
    else:
        print(f"  FAIL - {name}")
        FAIL += 1


def _raises(fn, exc) -> bool:
    try:
        fn()
    except exc:
        return True
    return False


def _load_signer():
    spec = importlib.util.spec_from_file_location("sign_release",
                                                  REPO / "packaging" / "sign-release.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_install_kind(work: Path):
    """INV-1."""
    real = work / "OneUp.AppImage"
    real.write_bytes(b"x")
    saved = (getattr(sys, "frozen", None), os.environ.get("APPIMAGE"), paths.HERE)

    def kind(frozen, appimage, here=REPO):
        if frozen:
            sys.frozen = True
        elif hasattr(sys, "frozen"):
            del sys.frozen
        if appimage is None:
            os.environ.pop("APPIMAGE", None)
        else:
            os.environ["APPIMAGE"] = appimage
        paths.HERE = Path(here)
        return self_update.install_kind()

    try:
        check("INV-1 frozen with $APPIMAGE naming a file is an AppImage",
              kind(True, str(real)) == "appimage")
        check("INV-1 an unfrozen /usr/share/oneup is a package install",
              kind(False, None, "/usr/share/oneup") == "package")
        check("INV-1 an unfrozen repository is a checkout", kind(False, None) == "checkout")
        check("INV-1 frozen with $APPIMAGE unset is a checkout", kind(True, None) == "checkout")
        check("INV-1 frozen with $APPIMAGE naming a missing file is a checkout",
              kind(True, str(work / "gone.AppImage")) == "checkout")
        check("INV-1 $APPIMAGE without sys.frozen is not an AppImage",
              kind(False, str(real)) == "checkout")
    finally:
        frozen, appimage, paths.HERE = saved
        if frozen is None:
            if hasattr(sys, "frozen"):
                del sys.frozen
        else:
            sys.frozen = frozen
        if appimage is None:
            os.environ.pop("APPIMAGE", None)
        else:
            os.environ["APPIMAGE"] = appimage


def test_parse_version():
    """INV-2."""
    p = self_update.parse_version
    check("INV-2 2.1.0 and v2.1.0 parse", p("2.1.0") == (2, 1, 0) and p("v2.1.0") == (2, 1, 0))
    check("INV-2 a prerelease, a short, a long, a word, a superscript and empty are refused",
          all(p(t) is None for t in ("2.1.0-rc1", "2.1", "2.1.0.1", "latest", "2.¹.0", "")))
    check("INV-2 a non-string is refused", p(None) is None and p(210) is None)


def _entry(tag, *, draft=False, prerelease=False, assets=None, body="notes"):
    return {"tag_name": tag, "draft": draft, "prerelease": prerelease, "body": body,
            "assets": assets or []}


def _asset(name, url, size=0):
    return {"name": name, "browser_download_url": url, "size": size}


def test_release_list():
    """INV-3."""
    base = "https://github.com/milnet01/OneUp/releases/download"
    data = [
        "not a dict",
        _entry("v2.4.0", draft=True),
        _entry("v2.5.0", prerelease=True),
        _entry("nightly"),
        _entry("v2.0.0"),
        _entry("v2.3.0", assets=[_asset(self_update.ASSET, "http://example.com/a"),
                                 _asset(self_update.SIG_ASSET, f"{base}/v2.3.0/a.sig")]),
        _entry("1.4.13"),
        _entry("v2.1.0", body=None),
        _entry("v2.2.0", assets=[_asset(self_update.ASSET, f"{base}/v2.2.0/a", 85309944),
                                 _asset(self_update.SIG_ASSET, f"{base}/v2.2.0/a.sig"),
                                 "junk"]),
    ]
    got = self_update.releases_from_json(data)
    check("INV-3 a JSON object is not a list of releases",
          self_update.releases_from_json({"message": "Not Found"}) is None)
    check("INV-3 drafts, prereleases, non-dicts and unparseable tags are dropped, sorted",
          [r.version for r in got] == [(2, 3, 0), (2, 2, 0), (2, 1, 0), (2, 0, 0), (1, 4, 13)])
    r230, r220 = got[0], got[1]
    check("INV-3 a non-HTTPS asset URL counts as absent",
          r230.appimage_url is None and r230.sig_url is not None)
    check("INV-3 both assets and the size are read",
          r220.appimage_url and r220.sig_url and r220.appimage_size == 85309944)
    check("INV-3 a null body reads as empty", got[2].body == "")
    picked = self_update.changelog(got, (2, 0, 0), (2, 2, 0))
    check("INV-3 the changelog is installed < v <= offered, highest first",
          [r.version for r in picked] == [(2, 2, 0), (2, 1, 0)])


def _keypair():
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    key = Ed25519PrivateKey.generate()
    raw = key.public_key().public_bytes(serialization.Encoding.Raw,
                                        serialization.PublicFormat.Raw)
    return key, base64.b64encode(raw).decode()


def test_verify():
    """INV-6."""
    saved = update_key.RELEASE_PUBLIC_KEY_B64
    key, public = _keypair()
    other, _ = _keypair()
    data = os.urandom(4096)
    sig = key.sign(self_update.signed_message(data, "2.1.0"))
    bad = self_update.UpdateVerificationError
    try:
        update_key.RELEASE_PUBLIC_KEY_B64 = ""
        check("INV-6 with no key built in, nothing verifies",
              _raises(lambda: self_update.verify(data, sig, "2.1.0"), bad))
        update_key.RELEASE_PUBLIC_KEY_B64 = public
        self_update.verify(data, sig, "2.1.0")
        check("INV-6 good bytes and signature verify", True)
        flipped = bytes([data[0] ^ 1]) + data[1:]
        sig_flipped = bytes([sig[0] ^ 1]) + sig[1:]
        check("INV-6 one flipped byte in the data fails",
              _raises(lambda: self_update.verify(flipped, sig, "2.1.0"), bad))
        check("INV-6 one flipped byte in the signature fails",
              _raises(lambda: self_update.verify(data, sig_flipped, "2.1.0"), bad))
        check("INV-6 a 63-byte signature fails",
              _raises(lambda: self_update.verify(data, sig[:63], "2.1.0"), bad))
        check("INV-6 a signature made for another version fails",
              _raises(lambda: self_update.verify(data, sig, "2.2.0"), bad))
        other_sig = other.sign(self_update.signed_message(data, "2.1.0"))
        check("INV-6 a signature from a second key fails",
              _raises(lambda: self_update.verify(data, other_sig, "2.1.0"), bad))
    finally:
        update_key.RELEASE_PUBLIC_KEY_B64 = saved


def test_install(work: Path):
    """INV-8 and INV-9."""
    real_dir = work / "apps"
    real_dir.mkdir()
    target = real_dir / "OneUp-x86_64.AppImage"
    target.write_bytes(b"old")
    target.chmod(0o755)
    link = work / "OneUp.AppImage"
    link.symlink_to(target)
    got = self_update.install(b"new", str(link))
    check("INV-8 through a symlink the real file is replaced, at its mode",
          got == target and target.read_bytes() == b"new"
          and (target.stat().st_mode & 0o777) == 0o755)
    check("INV-8 the symlink is still a symlink", link.is_symlink())
    check("INV-8 no temporary file is left", sorted(os.listdir(real_dir)) == [target.name])

    real_replace = os.replace

    def _fail(*_args):
        raise OSError("disk full")

    os.replace = _fail
    try:
        raised = _raises(lambda: self_update.install(b"newer", str(link)), OSError)
    finally:
        os.replace = real_replace
    check("INV-8 a failed replace raises, leaves the original and no temp",
          raised and target.read_bytes() == b"new"
          and sorted(os.listdir(real_dir)) == [target.name])

    locked = work / "locked"
    locked.mkdir()
    (locked / "OneUp.AppImage").write_bytes(b"old")
    locked.chmod(0o555)
    try:
        if os.geteuid() == 0:
            check("INV-9 an unwritable folder is refused (skipped: running as root)", True)
        else:
            refused = _raises(lambda: self_update.install(b"new", str(locked / "OneUp.AppImage")),
                              self_update.UpdateInstallError)
            check("INV-9 an unwritable folder is refused and nothing is written",
                  refused and (locked / "OneUp.AppImage").read_bytes() == b"old"
                  and os.listdir(locked) == ["OneUp.AppImage"])
    finally:
        locked.chmod(0o755)
    source = (REPO / "oneup" / "gui" / "self_update.py").read_text()
    check("INV-9 self_update.py names no privileged route",
          not re.search(r"sudo|pkexec|service_client|rootops", source))


def test_relaunch():
    """INV-10."""
    recorded = []

    class _Popen:
        def __init__(self, argv, **kwargs):
            recorded.append((argv, kwargs))

    loader = {"LD_LIBRARY_PATH": "/bundle/_MEIx", "LD_LIBRARY_PATH_ORIG": "/usr/lib64",
              "LD_PRELOAD": "/bundle/_MEIx/a.so", "APPDIR": "/bundle/.mount_x",
              "APPIMAGE": "/home/u/OneUp.AppImage", "ARGV0": "OneUp", "OWD": "/home/u"}
    saved_env = {k: os.environ.get(k) for k in (*loader, "LD_PRELOAD_ORIG")}
    os.environ.update(loader)
    os.environ.pop("LD_PRELOAD_ORIG", None)
    real_popen = subprocess.Popen
    subprocess.Popen = _Popen
    try:
        self_update.relaunch(["/home/u/OneUp.AppImage", "--tray"])
    finally:
        subprocess.Popen = real_popen
        for k, v in saved_env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
    argv, kwargs = recorded[0] if recorded else ([], {})
    env = kwargs.get("env", {})
    check("INV-10 the waiter is /bin/sh, detached, with its pids and the argv",
          argv[:3] == ["/bin/sh", "-c", self_update.WAITER] and argv[3] == "sh"
          and str(os.getpid()) in argv and argv[-3:] == ["--", "/home/u/OneUp.AppImage",
                                                         "--tray"]
          and kwargs.get("start_new_session") is True)
    check("INV-10 the environment resets PyInstaller and drops the AppImage markers",
          env.get("PYINSTALLER_RESET_ENVIRONMENT") == "1"
          and not any(k in env for k in ("APPDIR", "APPIMAGE", "ARGV0", "OWD")))
    check("INV-10 the loader path is restored from _ORIG, LD_PRELOAD with none is dropped",
          env.get("LD_LIBRARY_PATH") == "/usr/lib64" and "LD_PRELOAD" not in env)

    tree = ast.parse((REPO / "oneup" / "gui" / "self_update.py").read_text())
    execs = [n.lineno for n in ast.walk(tree) if isinstance(n, ast.Attribute)
             and n.attr.startswith(("exec", "spawn")) and isinstance(n.value, ast.Name)
             and n.value.id == "os"]
    check(f"INV-10 self_update never calls os.exec* ({execs or 'none'})", not execs)

    # The waiter for real, against a child that lives half a second.
    child = subprocess.Popen(["sleep", "0.5"])  # noqa: S607 — a fixed test argv.
    started = time.monotonic()
    out = subprocess.run(  # noqa: S603 — the waiter under test, fixed argv.
        ["/bin/sh", "-c", self_update.WAITER, "sh", str(child.pid), "--",
         "sh", "-c", "echo launched"], capture_output=True, text=True, timeout=30)
    waited = time.monotonic() - started
    child.wait()
    check(f"INV-10 the waiter execs only after the pid has gone ({waited:.2f}s)",
          out.stdout.strip() == "launched" and waited >= 0.45)


def test_signer(work: Path):
    """INV-16."""
    tracked = subprocess.run(["git", "ls-files"], cwd=REPO, capture_output=True,  # noqa: S607
                             text=True, check=True).stdout.split()
    check("INV-16 no *.key file is tracked", not [f for f in tracked if f.endswith(".key")])
    pem = subprocess.run(
        ["git", "grep", "-l", "-I", "-E",  # noqa: S607 — fixed argv.
         "-----BEGIN [A-Z ]*PRIVATE KEY-----"],
        cwd=REPO, capture_output=True, text=True).stdout.split()
    check(f"INV-16 no tracked file holds a private key ({pem or 'none'})", not pem)

    signer = _load_signer()
    public = signer.generate(work / "keys" / "signing.key")
    check("INV-16 the generated key is mode 600",
          ((work / "keys" / "signing.key").stat().st_mode & 0o777) == 0o600)
    check("INV-16 --generate refuses to overwrite",
          _raises(lambda: signer.generate(work / "keys" / "signing.key"), FileExistsError))
    artifact = work / "OneUp-x86_64.AppImage"
    artifact.write_bytes(os.urandom(2048))
    sig = signer.sign(work / "keys" / "signing.key", artifact, "2.1.0").read_bytes()
    saved = update_key.RELEASE_PUBLIC_KEY_B64
    try:
        update_key.RELEASE_PUBLIC_KEY_B64 = public
        self_update.verify(artifact.read_bytes(), sig, "2.1.0")
        check("INV-16 a signature the signer makes verifies through self_update.verify", True)
        update_key.RELEASE_PUBLIC_KEY_B64 = _keypair()[1]
        check("INV-16 and fails against a second key",
              _raises(lambda: self_update.verify(artifact.read_bytes(), sig, "2.1.0"),
                      self_update.UpdateVerificationError))
    finally:
        update_key.RELEASE_PUBLIC_KEY_B64 = saved


def test_disk_version(work: Path):
    """§4.8's reader (INV-13's comparison is gui-smoke's)."""
    saved = paths.HERE
    (work / "oneup").mkdir()
    init = work / "oneup" / "__init__.py"
    try:
        paths.HERE = work
        init.write_text('"""x"""\nAPP_VERSION = "2.3.4"\n')
        check("disk_version reads APP_VERSION", self_update.disk_version() == (2, 3, 4))
        init.write_text('APP_ID = "x"\n')
        check("disk_version is None with the line absent", self_update.disk_version() is None)
        init.unlink()
        check("disk_version is None with the file gone", self_update.disk_version() is None)
    finally:
        paths.HERE = saved


def main() -> int:
    work = Path(tempfile.mkdtemp(prefix="oneup-selfupdate-"))
    try:
        for name in ("kind", "install", "sign", "disk"):
            (work / name).mkdir()
        test_install_kind(work / "kind")
        test_parse_version()
        test_release_list()
        test_verify()
        test_install(work / "install")
        test_relaunch()
        test_signer(work / "sign")
        test_disk_version(work / "disk")
    finally:
        shutil.rmtree(work, ignore_errors=True)
    print()
    print(f"  Passed: {PASS}   Failed: {FAIL}")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
