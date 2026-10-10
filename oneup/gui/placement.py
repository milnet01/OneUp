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
import time
import uuid

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication


def _platform_name() -> str:
    return QApplication.platformName()


def _on_wayland() -> bool:
    # Qt's platform plugin, not XDG_SESSION_TYPE (ONEUP-0181): a Wayland session started
    # without that variable would otherwise take the X11 branch, where move() is accepted
    # and ignored.
    return _platform_name().startswith("wayland")


def run_kwin_script(js: str) -> bool:
    """Load, run and unload a one-shot KWin script (Plasma 5 & 6).

    On Wayland an application may not place its own windows — the compositor owns
    placement, so Qt's move() is accepted and silently ignored. Asking KWin is the only
    way to position anything, which is why both window recentring and dialog placement
    come through here.

    True means KWin accepted the script, never that it did anything: `dbus-send` exits
    non-zero only when the call did not land (no KWin on the bus), and says nothing
    about the script itself."""
    if not shutil.which("dbus-send"):
        return False
    script_path = None
    name = "oneup_place"
    try:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".js",
                                         prefix="oneup_place_", delete=False) as f:
            script_path = f.name   # capture before write so a write error still cleans up
            f.write(js)
        base = ["dbus-send", "--session", "--dest=org.kde.KWin",
                "--print-reply", "/Scripting"]
        loaded = subprocess.run([*base, "org.kde.kwin.Scripting.loadScript",  # noqa: S603 — fixed argv.
                                 f"string:{script_path}", f"string:{name}"],
                                capture_output=True, timeout=3)
        subprocess.run([*base, "org.kde.kwin.Scripting.start"],  # noqa: S603
                       capture_output=True, timeout=3)
        subprocess.run([*base, "org.kde.kwin.Scripting.unloadScript",  # noqa: S603
                        f"string:{name}"],
                       capture_output=True, timeout=3)
        return loaded.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False
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
            # Clamp to the screen, as the Wayland branch below does: a dialog taller
            # than its parent would otherwise hang off it (ONEUP-0181).
            screen = parent.screen() or QApplication.primaryScreen()
            if screen is not None:
                area = screen.availableGeometry()
                fg.moveLeft(max(area.left(), min(fg.left(), area.right() + 1 - fg.width())))
                fg.moveTop(max(area.top(), min(fg.top(), area.bottom() + 1 - fg.height())))
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


# How long to wait for KWin's answer to reach the journal. Measured on Plasma 6.7.5: about
# 10 ms, 600 ms on the first query of a session. Bounded because it runs as the window
# hides, on the GUI thread.
FRAME_ANSWER_TIMEOUT = 1.5


def _frame_from_journal(text: str, marker: str) -> tuple[int, int] | None:
    """The x, y KWin printed after `marker`, or None if no line carries two integers."""
    for line in text.splitlines():
        if marker in line:
            try:
                x, y = line.split(marker, 1)[1].split()[:2]
                return int(x), int(y)
            except ValueError:
                return None
    return None


def main_frame_position() -> tuple[int, int] | None:
    """Where KWin has the main window's frame, as x, y — or None if it cannot say.

    Wayland gives a client no global coordinates, so Qt reports 0,0 wherever the window
    is (ONEUP-0246). KWin knows, and a script's print() is the one channel back from it:
    the line lands in the user journal, tagged with a marker no other line carries. Only
    meaningful while the window is mapped — a hidden window is unknown to KWin."""
    if not shutil.which("journalctl"):
        return None
    marker = f"oneup_frame_{uuid.uuid4().hex}"
    since = f"@{int(time.time()) - 2}"
    if not run_kwin_script(f"""\
var wins = workspace.windowList();
for (var i = 0; i < wins.length; i++) {{
    var c = wins[i];
    if (c.pid !== {os.getpid()} || c.transientFor) continue;
    print("{marker}", c.frameGeometry.x, c.frameGeometry.y);
    break;
}}
"""):
        return None
    deadline = time.monotonic() + FRAME_ANSWER_TIMEOUT
    while True:
        try:
            out = subprocess.run(["journalctl", "--user", "-b", "--since", since,  # noqa: S603, S607
                                  "-o", "cat"],
                                 capture_output=True, text=True, timeout=2).stdout
        except (OSError, subprocess.SubprocessError):
            return None
        pos = _frame_from_journal(out, marker)
        if pos is not None or time.monotonic() >= deadline:
            return pos
        time.sleep(0.05)


def kwin_restore_position(x: int, y: int) -> None:
    """Ask KWin to put the main window's frame at x, y, keeping its current size.

    Clamped to the usable area of the screen holding that point, or of the window's own
    screen when that monitor is gone. The size is written too: KWin takes the whole
    rectangle as given. `KWin.PlacementArea`, not `workspace.PlacementArea`, which is
    undefined on Plasma 6 (measured 2026-10-10)."""
    run_kwin_script(f"""\
var x = {int(x)};
var y = {int(y)};
var wins = workspace.windowList();
for (var i = 0; i < wins.length; i++) {{
    var c = wins[i];
    if (c.pid !== {os.getpid()} || c.transientFor) continue;
    var g = c.frameGeometry, area = null;
    for (var j = 0; j < workspace.screens.length; j++) {{
        var s = workspace.screens[j].geometry;
        if (x >= s.x && x < s.x + s.width && y >= s.y && y < s.y + s.height)
            area = workspace.clientArea(KWin.PlacementArea, workspace.screens[j],
                                        workspace.currentDesktop);
    }}
    if (area === null) area = workspace.clientArea(KWin.PlacementArea, c);
    x = Math.max(area.x, Math.min(x, area.x + area.width - g.width));
    y = Math.max(area.y, Math.min(y, area.y + area.height - g.height));
    c.frameGeometry = {{ x: x, y: y, width: g.width, height: g.height }};
    break;
}}
""")
