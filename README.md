# OneUp

**One click, everything up to date.** A small, no-nonsense update dashboard for
openSUSE (Tumbleweed and Leap) that does the four things you actually need — in
the *right* way — from a single window.

![OneUp](screenshots/oneup.png)

---

## Why not just use Discover?

Because keeping openSUSE current means running several different commands, and the
graphical tools don't cover all of them:

- **Discover / PackageKit** handles packages and Flatpaks, but on Tumbleweed it
  regularly chokes on Packman codec **vendor changes** — the update stalls and you
  end up in a terminal anyway. It also doesn't touch firmware or clean up orphans.
- The **correct** Tumbleweed system-update command is `zypper dup --allow-vendor-change`.
  Plenty of people run plain `zypper up` instead and slowly break their system.
- Firmware (`fwupd`), Flatpak clean-up, and leftover-package removal are three more
  separate commands most people never run.

OneUp bundles all of that behind toggles and runs each step the way openSUSE's own
documentation recommends. It's the knowledge, not the GUI, that's the point.

## What it does

| Task | What runs |
|------|-----------|
| **System packages** | `zypper dup --allow-vendor-change` (Tumbleweed) or `zypper update` (Leap), after a repo refresh |
| **Flatpak apps** | `flatpak update` for both user and system scope, then prunes unused runtimes |
| **Firmware** | `fwupdmgr refresh` + `update` |
| **Leftover packages** | Safely autoremoves unneeded dependencies; *reports* (never auto-removes) hand-installed orphans |
| **Package cache** | `zypper clean --all` to reclaim disk space |

Each task is a toggle — turn off what you don't want. On top of running updates,
OneUp can:

- **Check for updates** read-only (see the count per task before installing).
- **Check weekly in the background** and notify you when updates are ready.
- **Sit quietly in the system tray** and turn amber when updates are waiting, so you
  notice without catching a popup — with a right-click Check / Update / Open / Quit
  menu. Optional (off by default), and can also start at login.
- **Update automatically every week** — optionally (off by default). An "Automatic
  updates" setting runs the whole update on a weekly schedule in the background,
  keeping the snapshot/rollback safety net. It needs the "Passwordless" setting, so
  an unattended run doesn't stop to ask for a password.
- **Restart just the affected services** instead of rebooting, when a full reboot
  isn't actually required.
- **Roll back** to the snapshot it took before the update, in one click.
- **Skip the password prompt** — optionally (off by default). A "Passwordless"
  toggle stops OneUp asking for your password on every update. It stores **no
  password**: the system just remembers the decision for OneUp's update commands,
  and switching it off revokes it instantly.
- **Explain failures** in plain English, warn about low disk space or duplicate
  repos before starting, and follow your desktop's **light/dark** theme.

There's a live log, a one-click **Restart** button when a reboot is genuinely
needed, and a run history.

## Design notes

- **OneUp never runs as root.** The GUI is a thin front-end; all privileged work
  happens in `update_system.sh`, which authenticates **once** through your desktop's
  standard password prompt and keeps the credential warm for the run.
- **It gets PackageKit out of the way.** The desktop's background updater grabs the
  package lock shortly after login; OneUp stops it first so `zypper` can work, and
  it restarts on its own afterwards.
- **A failed step never claims success.** The reboot advice only appears when
  something was actually installed, or when `zypper needs-rebooting` explicitly says
  so — not when a step merely errored out.
- **The engine is usable on its own.** `update_system.sh` runs fine in a plain
  terminal (`./update_system.sh --steps=system,cache`); the GUI just drives it.

## Install & run

### openSUSE repository — recommended (auto-updates)

On Tumbleweed, add the repo once and install — OneUp then updates along with the
rest of your system:

```bash
sudo zypper addrepo https://download.opensuse.org/repositories/home:/milnet/openSUSE_Tumbleweed/home:milnet.repo
sudo zypper refresh
sudo zypper install oneup
```

Built on the [openSUSE Build Service](https://build.opensuse.org/package/show/home:milnet/oneup)
and also searchable on [software.opensuse.org](https://software.opensuse.org/package/oneup).

### AppImage — one file, nothing to install

Grab `OneUp-x86_64.AppImage` from the
[latest release](https://github.com/milnet01/OneUp/releases/latest), make it
executable, and run it. Everything (Python + Qt) is bundled inside:

```bash
chmod +x OneUp-x86_64.AppImage
./OneUp-x86_64.AppImage
```

Needs `libfuse2` to run (`sudo zypper install libfuse2`), like any AppImage.

### RPM — for `zypper` users

```bash
sudo zypper install ./oneup-*.noarch.rpm     # pulls in python3-pyside6, zypper, sudo…
oneup
```

Prefer automatic updates? Use the **repository** method above instead.

### From source

```bash
sudo zypper install python3-pyside6
git clone https://github.com/milnet01/OneUp.git
cd OneUp
python3 updater.py
```

Build your own AppImage or RPM from `packaging/appimage/build-appimage.sh` and
`packaging/rpm/oneup.spec`.

## Requirements

- openSUSE Tumbleweed or Leap
- `zypper` (always present), and optionally `flatpak` and `fwupd` — steps for tools
  you don't have are skipped cleanly
- Python 3 + PySide6 (Qt 6) for the GUI
- A polkit/askpass agent for the password prompt (standard on KDE and GNOME)

## Licence

MIT — see [LICENSE](LICENSE). Icon uses the Material "refresh" glyph.
