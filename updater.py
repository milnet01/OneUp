#!/usr/bin/env python3
"""OneUp — the thing you launch.

The application itself lives in `oneup/`: `oneup/gui/` is the window, split into
modules that each do one job, and `docs/specs/ONEUP-0034-gui-modules.md` says
which module owns what.

This file stays at the repo root and stays a few lines, because the desktop
entry's `Exec=oneup`, the RPM's `/usr/bin/oneup` wrapper, the AppImage's
PyInstaller entry point and every hand-made launcher all name it by path
(`docs/standards/files-and-naming.md` §4.1 rule 1).

Run headless as `oneup --check` (or `updater.py --check`) to perform a read-only
"updates available?" check and a desktop notification, with no window — this is
what the optional weekly systemd-user timer calls.
"""

from oneup.gui.app import main

if __name__ == "__main__":
    main()
