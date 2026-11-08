"""The public key every downloaded OneUp AppImage must be signed by.

`docs/specs/ONEUP-0112-self-update.md` §4.5 and §4.9. The private half is made once,
by the maintainer, with `python3 packaging/sign-release.py --generate`, and lives only
on the machine that signs releases; it never enters the repository. That command
prints the value for `RELEASE_PUBLIC_KEY_B64`.

`cryptography` is imported inside `public_key()`, never at module level: a package
install has no `python3-cryptography` requirement and never verifies anything
(INV-17).
"""
from __future__ import annotations

import base64

# The raw 32-byte Ed25519 public key, base64. Empty until the signing key exists:
# then `public_key()` raises, so no download verifies and nothing is ever installed.
RELEASE_PUBLIC_KEY_B64 = ""


def public_key():
    """The release key as an `Ed25519PublicKey`. Raises ValueError when no key is set
    or the constant is not a 32-byte key."""
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

    raw = base64.b64decode(RELEASE_PUBLIC_KEY_B64, validate=True)
    if len(raw) != 32:
        raise ValueError("no release signing key is built into this OneUp")
    return Ed25519PublicKey.from_public_bytes(raw)
