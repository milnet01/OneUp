# Dialog & Popup Standard

**Standing rule for OneUp.** Every popup window — modal dialogs and message boxes alike —
must (1) match the app's light/dark theme and (2) open **centered over the main window**.
Reuse the two helpers below; do not invent a third centering path or set a per-dialog
palette.

## The two properties

### 1. Theme-matched — free, don't fight it

The whole app is themed once, application-wide, in `main()`:

```python
def apply_theme():
    app.setStyleSheet(build_theme(current_is_dark(app)))
```

and re-applied live when the desktop switches light/dark (`colorSchemeChanged`). Because the
stylesheet lives on the `QApplication`, **every child widget — including `QDialog`
subclasses and `QMessageBox` instances — inherits it automatically.** A new popup is
theme-matched by construction.

- **Do:** let dialogs inherit. Use the shared object names the QSS already styles
  (`#Card`, `#RowBorder`, `#GhostBtn`, `QLabel#Tagline`, …) so a new dialog looks native.
- **Don't:** call `setStyleSheet`/`setPalette` on an individual dialog — a per-dialog
  override desyncs it from the live light/dark switch and is the one way to break this
  property.

### 2. Centered over the main window — use the matching helper

Positioning has two idioms depending on what kind of popup it is. On Wayland the compositor
places top-levels by default; these helpers re-center explicitly so a popup never drifts to
a corner.

**A `QDialog` subclass** (e.g. `RepoManagerDialog`, `SettingsDialog`) centers itself by
overriding `showEvent` — size is restored from `QSettings`, position is re-centered every
time it opens:

```python
def showEvent(self, event):
    super().showEvent(event)
    parent = self.parent()
    if parent:
        fg = self.frameGeometry()
        fg.moveCenter(parent.frameGeometry().center())
        self.move(fg.topLeft())
```

**A `QMessageBox` we build and `exec()` ourselves** (About, passwordless consent,
signing-key import) can't use `showEvent` cleanly because the box sizes to its content only
when shown. Center it via `Updater._center_child` deferred one event-loop tick, exactly as
`show_about` does:

```python
box = QMessageBox(self)
...                                    # setText / buttons / etc.
QTimer.singleShot(0, lambda: self._center_child(box))
box.exec()
```

## When each rule applies

| Popup kind | Theme | Center |
| --- | --- | --- |
| `QDialog` subclass (`RepoManagerDialog`, `SettingsDialog`) | inherited app QSS | `showEvent` override (above) |
| Hand-built `QMessageBox` we `exec()` (`show_about`, `_confirm_passwordless`, `_confirm_key_import`) | inherited app QSS | `QTimer.singleShot(0, _center_child)` before `exec()` |
| Static convenience `QMessageBox.warning/information/question/critical(self, …)` | inherited app QSS | Qt's parent-relative default — acceptable for transient one-line notices; do **not** rewrite these into hand-built boxes just to center them |

**Rule of thumb:** if you construct the box yourself and hold a reference to it, center it.
If it's a one-line `QMessageBox.warning(self, …)` convenience call, leave it — parenting to
`self` gives Qt enough to place it, and the extra machinery isn't worth it for a transient
prompt.

## Adding a new dialog — checklist

1. Parent it to the `Updater` window (`QDialog(parent)` / `QMessageBox(self)`) — never a
   parentless popup.
2. Don't set a per-dialog stylesheet; reuse the existing QSS object names.
3. Center it: `showEvent` override for a `QDialog` subclass, or
   `QTimer.singleShot(0, lambda: self._center_child(box))` before `exec()` for a hand-built
   `QMessageBox`.
4. `gui-smoke.py` opens dialogs headless — if the new one blocks on `exec()`, schedule a
   close in the smoke test the way `_dismiss_about` does.
