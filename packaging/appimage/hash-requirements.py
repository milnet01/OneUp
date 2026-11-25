#!/usr/bin/env python3
"""Write each pinned package's sha256 hashes into packaging/appimage/requirements.txt.

Usage:  packaging/appimage/hash-requirements.py

Run it after changing a pin. It keeps every comment and `name==version` line, drops any
`--hash` lines already there, and adds one for every file PyPI holds for that version: the
release workflow and a local build use different Pythons, so each may pick a different
wheel. With a hash present pip refuses any file not listed and any package the file does
not name, so a wheel added later under a pinned version, or a new dependency, stops the
build instead of riding into it (ONEUP-0430; docs/standards/security.md §13.6).
Needs the network; reads PyPI's public JSON API only.
"""
import json
import re
import sys
import urllib.request
from pathlib import Path

REQS = Path(__file__).resolve().parent / "requirements.txt"
PIN = re.compile(r"([A-Za-z0-9_.-]+)==(\S+)")


def hashes(name: str, version: str) -> list[str]:
    url = f"https://pypi.org/pypi/{name}/{version}/json"
    with urllib.request.urlopen(url, timeout=30) as reply:
        files = json.load(reply)["urls"]
    if not files:
        sys.exit(f"hash-requirements: PyPI lists no files for {name}=={version}")
    return sorted({f["digests"]["sha256"] for f in files})


def main() -> None:
    out = []
    for line in REQS.read_text().splitlines():
        stripped = line.strip()
        if stripped.startswith("--hash="):
            continue
        pin = PIN.match(stripped)
        if not pin:
            out.append(line)
            continue
        found = hashes(*pin.groups())
        out.append(f"{pin.group(1)}=={pin.group(2)} \\")
        out += [f"    --hash=sha256:{h}" + (" \\" if i < len(found) - 1 else "")
                for i, h in enumerate(found)]
    REQS.write_text("\n".join(out) + "\n")
    print(f"hash-requirements: {REQS} rewritten")


if __name__ == "__main__":
    main()
