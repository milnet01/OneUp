#!/usr/bin/env python3
"""Sign, or verify, a OneUp AppImage for the self-update; or make the signing key once.

`docs/specs/ONEUP-0112-self-update.md` §4.9. Run from anywhere; it finds the repository
from its own path.

    python3 packaging/sign-release.py --generate                  # once, by the maintainer
    python3 packaging/sign-release.py --version X.Y.Z FILE        # writes FILE.sig
    python3 packaging/sign-release.py --verify --version X.Y.Z FILE
    python3 packaging/sign-release.py --check-key                 # before a release

`--check-key` asks whether the private key is the committed public key's other half,
and prints only the answer, never key material. `release.sh` runs it before it changes
anything, so a mismatched key stops the release instead of shipping an AppImage that
every installed copy refuses.

`--generate` writes the private key (mode 600, never over an existing one) and prints
the public key for `oneup/gui/update_key.py`. **Back the private key up**: without it
no later release can be signed, and every installed AppImage refuses every update.

The signature is the raw 64-byte Ed25519 signature of `self_update.signed_message`,
and `--verify` checks it through `self_update.verify` against the COMMITTED public key —
the very check the app makes, so a release that verifies here verifies there.
"""
from __future__ import annotations

import argparse
import base64
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from oneup.gui import self_update, update_key  # noqa: E402 — needs the repository on sys.path.

DEFAULT_KEY = Path.home() / ".config" / "oneup-release" / "signing.key"


def generate(dest: Path) -> str:
    """Write a new private key to `dest` (mode 600, refusing to overwrite) and return
    the public key as base64 of its raw 32 bytes."""
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    key = Ed25519PrivateKey.generate()
    pem = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                            serialization.NoEncryption())
    dest.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    # O_EXCL refuses an existing key; 0600 from the start leaves no readable moment.
    fd = os.open(dest, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as handle:
        handle.write(pem)
    raw = key.public_key().public_bytes(serialization.Encoding.Raw,
                                        serialization.PublicFormat.Raw)
    return base64.b64encode(raw).decode("ascii")


def _load_private(key_path: Path):
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    key = serialization.load_pem_private_key(key_path.read_bytes(), password=None)
    if not isinstance(key, Ed25519PrivateKey):
        raise TypeError(f"{key_path} is not an Ed25519 private key")
    return key


def key_matches(key_path: Path) -> bool:
    """True when the private key at `key_path` is the other half of the committed
    `update_key.RELEASE_PUBLIC_KEY_B64`. Raises as `public_key()` does when no
    public key is committed, and as `_load_private` does for an unreadable key."""
    from cryptography.hazmat.primitives import serialization

    raw = serialization.Encoding.Raw, serialization.PublicFormat.Raw
    return (_load_private(key_path).public_key().public_bytes(*raw)
            == update_key.public_key().public_bytes(*raw))


def sign(key_path: Path, artifact: Path, version: str) -> Path:
    """Write `<artifact>.sig` for `version` with the private key at `key_path`."""
    key = _load_private(key_path)
    sig_path = artifact.with_name(artifact.name + ".sig")
    sig_path.write_bytes(key.sign(self_update.signed_message(artifact.read_bytes(), version)))
    return sig_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Sign or verify a OneUp AppImage.")
    parser.add_argument("artifact", type=Path, nargs="?", help="the AppImage")
    parser.add_argument("--generate", action="store_true", help="make the signing key once")
    parser.add_argument("--verify", action="store_true",
                        help="check ARTIFACT.sig against the committed public key")
    parser.add_argument("--check-key", action="store_true",
                        help="check the private key matches the committed public key")
    parser.add_argument("--version", help="the release's X.Y.Z")
    parser.add_argument("--key", type=Path, default=DEFAULT_KEY,
                        help=f"the private key (default {DEFAULT_KEY})")
    args = parser.parse_args(argv)

    if args.generate:
        try:
            public = generate(args.key)
        except FileExistsError:
            print(f"error: {args.key} already exists — refusing to replace a signing key",
                  file=sys.stderr)
            return 1
        print(f"Private key written to {args.key} (mode 600). Back it up somewhere safe.")
        print("Put this line in oneup/gui/update_key.py:")
        print(f'RELEASE_PUBLIC_KEY_B64 = "{public}"')
        return 0

    if args.check_key:
        if not args.key.is_file():
            print(f"error: signing key not found: {args.key}", file=sys.stderr)
            return 1
        try:
            match = key_matches(args.key)
        except (OSError, ValueError, TypeError) as exc:
            print(f"error: could not compare the keys: {exc}", file=sys.stderr)
            return 1
        if not match:
            print(f"error: {args.key} is not the private half of the public key in "
                  "oneup/gui/update_key.py — every installed AppImage would refuse "
                  "a release it signs", file=sys.stderr)
            return 1
        print(f"{args.key} matches the committed public key.")
        return 0

    if args.artifact is None or self_update.parse_version(args.version or "") is None:
        parser.error("an ARTIFACT and --version X.Y.Z are required")
    if not args.artifact.is_file():
        print(f"error: {args.artifact} not found", file=sys.stderr)
        return 1
    if args.verify:
        sig_path = args.artifact.with_name(args.artifact.name + ".sig")
        try:
            self_update.verify(args.artifact.read_bytes(), sig_path.read_bytes(), args.version)
        except (OSError, self_update.UpdateVerificationError) as exc:
            print(f"error: {sig_path} does not verify: {exc}", file=sys.stderr)
            return 1
        print(f"{sig_path} verifies against the committed public key for {args.version}.")
        return 0
    if not args.key.is_file():
        print(f"error: signing key not found: {args.key}", file=sys.stderr)
        return 1
    print(f"Wrote {sign(args.key, args.artifact, args.version)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
