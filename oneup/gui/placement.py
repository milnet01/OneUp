"""Putting a window where the user expects to find it.

On Wayland an application may not place its own windows — the compositor owns
placement, so Qt's `move()` is accepted and silently ignored. Asking KWin is the
only way to position anything, which is why both window recentring and dialog
placement come through `run_kwin_script`.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile

from PySide6.QtCore import QTimer


def _on_wayland() -> bool:
    return os.environ.get("XDG_SESSION_TYPE", "").lower() == "wayland"


def run_kwin_script(js: str) -> None:
    """Load, run and unload a one-shot KWin script (Plasma 5 & 6).

    On Wayland an application may not place its own windows — the compositor owns
    placement, so Qt's move() is accepted and silently ignored. Asking KWin is the only
    way to position anything, which is why both window recentring and dialog placement
    come through here."""
    if not shutil.which("dbus-send"):
        return
    script_path = None
    name = "oneup_place"
    try:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".js",
                                         prefix="oneup_place_", delete=False) as f:
            script_path = f.name   # capture before write so a write error still cleans up
            f.write(js)
        base = ["dbus-send", "--session", "--dest=org.kde.KWin",
                "--print-reply", "/Scripting"]
        subprocess.run([*base, "org.kde.kwin.Scripting.loadScript",  # noqa: S603 — fixed argv.
                        f"string:{script_path}", f"string:{name}"],
                       capture_output=True, timeout=3)
        subprocess.run([*base, "org.kde.kwin.Scripting.start"],  # noqa: S603
                       capture_output=True, timeout=3)
        subprocess.run([*base, "org.kde.kwin.Scripting.unloadScript",  # noqa: S603
                        f"string:{name}"],
                       capture_output=True, timeout=3)
    except (OSError, subprocess.SubprocessError):
        pass
    finally:
        if script_path:
            try:
                os.unlink(script_path)
            except OSError:
                pass


def center_on_parent(widget) -> None:
    """Put a dialog in the middle of the window that opened it.

    On X11 the direct move works. On Wayland it does nothing whatsoever, which is why
    OneUp's dialogs kept opening away from the window (ONEUP-0049) — there we ask KWin to
    centre each of our transient windows over its own parent. Matching on `transientFor`
    rather than on a window title means every dialog is covered, including the message
    boxes that have no title of their own."""
    if not _on_wayland():
        parent = widget.parent()
        if parent is not None:
            fg = widget.frameGeometry()
            fg.moveCenter(parent.frameGeometry().center())
            widget.move(fg.topLeft())
        return
    js = f"""\
var wins = workspace.windowList();
for (var i = 0; i < wins.length; i++) {{
    var c = wins[i];
    if (c.pid !== {os.getpid()} || !c.transientFor) continue;
    var g = c.frameGeometry, pg = c.transientFor.frameGeometry;
    var area = workspace.clientArea(workspace.PlacementArea, c);
    var x = pg.x + Math.round((pg.width - g.width) / 2);
    var y = pg.y + Math.round((pg.height - g.height) / 2);
    // Clamp to the screen: a dialog taller than its parent would otherwise hang off it.
    x = Math.max(area.x, Math.min(x, area.x + area.width - g.width));
    y = Math.max(area.y, Math.min(y, area.y + area.height - g.height));
    c.frameGeometry = {{ x: x, y: y, width: g.width, height: g.height }};
}}
"""
    # Deferred by a tick: KWin can only move a window it already knows about, and on
    # Wayland the surface isn't committed yet while showEvent is still running.
    QTimer.singleShot(0, lambda: run_kwin_script(js))



def kwin_recenter() -> None:
    # Center via KWin scripting (Plasma 5 & 6). We match our own window by PID and use
    # workspace.PlacementArea for the usable screen rectangle — the approach proven to
    # work on this machine's KDE Wayland session. Transients are skipped so this
    # always finds the main window, never a dialog that happens to come first;
    # centring a dialog is center_on_parent's job.
    run_kwin_script(f"""\
var wins = workspace.windowList();
for (var i = 0; i < wins.length; i++) {{
    var c = wins[i];
    if (c.pid !== {os.getpid()} || c.transientFor) continue;
    var area = workspace.clientArea(workspace.PlacementArea, c);
    c.frameGeometry = {{
        x: area.x + Math.round((area.width - c.frameGeometry.width) / 2),
        y: area.y + Math.round((area.height - c.frameGeometry.height) / 2),
        width: c.frameGeometry.width,
        height: c.frameGeometry.height
    }};
    break;
}}
""")
