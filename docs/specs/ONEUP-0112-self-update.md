# ONEUP-0112 — OneUp updates itself: what's new, a signed AppImage swap, and a restart

**Status:** Implemented
**Kind:** feature
**Roadmap:** ONEUP-0112
**Branch:** v2
**Verified at:** `fd1f527` — every symbol below was opened on 2026-11-07. Figures name the
command that produced them.

**Sections:** 1 goal · 2 background · 3 scope decisions · 4 design · 5 correctness
invariants · 6 failure modes · 7 tests · 8 docs & release · 9 alternatives · 10 out of
scope · 11 cold-eyes loop log

**In one sentence:** when a newer OneUp exists, the banner opens a window inside OneUp
listing what changed in every version since yours; an AppImage then downloads, proves the
download is genuine, swaps itself and reopens, an installed package tells you to run the
System update, and after that update a "Restart OneUp" button loads the new version.

## 1. Goal

After this ships, OneUp never sends the user to a web page to learn about or get a new
version of itself. The banner's button opens a pop-up with the release notes of every
version between the one running and the one on offer. On an AppImage the pop-up offers
**Update now**, which downloads the new AppImage, checks its Ed25519 signature against a
key built into OneUp, replaces the file and relaunches. On a package install the pop-up
says the System update will install it, and offers it only once the software source
carries it. After a run that updated the `oneup` package, a **Restart OneUp** button
replaces the open window, which still runs the old code, with the new version.

## 2. Background

**The check exists; everything after it is a dead end.** `oneup/gui/app_update.py`
`_check_app_update` asks `https://api.github.com/repos/{REPO_SLUG}/releases/latest`,
`_on_app_update_reply` compares the tag with `APP_VERSION` through `_version_tuple`, and a
newer tag shows `appupdate_banner`. Its button, built in `Updater.__init__`
(`oneup/gui/window.py`) and labelled "View release", calls `_open_release`, which opens the
GitHub release page in the browser. On the AppImage that opened nothing until ONEUP-0383
(`paths.restore_machine_library_path`), and the user decided on 2026-11-07 that it should
never open a browser at all (§3).

Consequences, numbered so §5 can trace to them:

1. **Only the newest release's notes are reachable**, and only on GitHub. A user two
   versions behind sees nothing about the version in between.
2. **The check ignores how OneUp was installed.** On a package install it announces a
   GitHub release the software source may not have built yet, so the System update the user
   runs next installs nothing.
3. **An AppImage cannot update itself.** The user must find, download and replace the file
   by hand.
4. **After the System update installs a new `oneup` package, the open window keeps running
   the old code**, and nothing says so. `grep -rn -i restart oneup/gui/*.py` on `fd1f527`
   finds only `banners.py`'s restarts of the computer and of system services, never of
   OneUp.
5. **`_version_tuple` accepts any digits.** It is `re.findall(r"\d+", v)`, so `2.1.0-rc1`
   compares as `[2, 1, 0, 1]`, newer than a final `2.1.0`. `/releases/latest` excludes
   prereleases, which hid this; §4.2's list endpoint does not.

**The reference implementation is finbreak's** (`/mnt/Games/Scripts/Linux/finbreak`),
which shipped this and paid for its failure modes. Its contract is
`tests/features/auto_update/spec.md` there; its code is `src/finbreak/services/update*.py`
and `src/finbreak/ui/update_dialog.py`. This spec takes its shape and cites each trap it
inherits. **Two of its traps transfer because OneUp freezes the same way**:
`packaging/appimage/build-appimage.sh` runs `pyinstaller --onefile`, as finbreak's onefile
build did.

**What the window already knows, and this design reuses:**

- **How it was launched.** `paths.HERE` is the bundle under `sys.frozen`, the repository
  root otherwise. `packaging/rpm/oneup.spec`'s `%install` puts the package under
  `%{_datadir}/oneup/`, and `oneup/gui/autostart.py` already treats a set `APPIMAGE`
  variable as "this is an AppImage".
- **What the software source offers.** After a check, `PackageModel` (`oneup/gui/packages.py`)
  holds one `Package` per `@@CHECK_ITEM@@` row — `key|name|from|to[|bytes|repo[|change]]`
  (`docs/reference/marker-protocol.md`). A row with key `system` and name `oneup` is the
  version zypper will install.
- **Whether a run is in flight.** `Updater._run_active`, set in `run._reset_for_run` and
  cleared in `run.on_finished` and `run.on_error`; `Updater._confirm_quit` reads it.
- **One instance per user.** `tray._arm_single_instance` holds a `QLocalServer`, and
  `app._raise_existing_instance` hands a second launch to the first and exits. A relaunch
  started before the old process has gone would be handed back to it and close.
- **How it quits.** `Updater._quit_requested` saves geometry, stops the details fetch and
  calls `QApplication.quit()`.

**Signing does not exist yet.** `.github/workflows/release.yml` builds the AppImage and
attaches `OneUp-x86_64.AppImage` with `softprops/action-gh-release`; nothing signs it.
`gh release view v2.0.0 --json assets -q '.assets[].name'` on 2026-11-07 →
`OneUp-x86_64.AppImage`, alone. `packaging/appimage/requirements.txt` carries no Ed25519
library (`grep -c cryptography packaging/appimage/requirements.txt` → `0`). ONEUP-0060,
the pinned build set this item's trust rests on, shipped.

## 3. Scope decisions (agreed with the user)

Decided by the user on 2026-11-07 unless marked otherwise.

1. **No web page, ever.** The banner's button opens a pop-up inside OneUp. Nothing in this
   feature opens a browser.
2. **The pop-up shows every version's notes** between the installed one and the one
   offered, newest first — not the newest alone. Source: the GitHub releases list, whose
   bodies are each version's CHANGELOG section (`release.yml`'s "Release notes from
   CHANGELOG.md" step writes them; checked for v2.0.0).
3. **The AppImage self-updates**: download, verify, swap, relaunch, after finbreak.
4. **A package install never self-updates.** zypper owns those files, and OneUp is the
   tool that runs zypper properly. The pop-up shows the notes and says the System update
   installs it. **It offers only what the software source can deliver**, because GitHub
   can be ahead of OBS.
5. **A "Restart OneUp" button** appears when OneUp on disk is newer than the running
   window — only then, in the update banner (the user's choice over an always-present
   About button).
6. **Releases are signed on this PC**, after GitHub builds the AppImage. `release.sh`
   waits for the build, downloads the AppImage, signs it with a key kept only here, and
   uploads the signature (the user's choice over a GitHub secret or a local build).
7. **The download is never automatic** — decided here, not by the user, following
   finbreak's opt-in. The existing "check for OneUp updates" setting (`app_update_check`,
   default on) still governs the GitHub check. Nothing downloads until the user presses
   **Update now**.
8. **Update now and Restart OneUp wait for a run to finish** — decided here. Runs outlive
   the window (ONEUP-0042) and the AppImage's engine runs from a copy outside the bundle
   (`paths._engine_copy`), so a swap mid-run would likely be safe; disabling the two
   buttons removes the need to prove it.
9. **A developer checkout** — decided here — gets the pop-up and the notes, says to update
   with git, and gets the Restart button. It never downloads.
10. **ONEUP-0384** (Run repeats a fresh Check) stays a separate item — decided here. It
    changes the engine/window contract; this item changes neither.

## 4. Design

### 4.1 Modules

| File | Holds | Network |
| --- | --- | --- |
| `oneup/gui/app_update.py` (exists) | the check, the releases list, the asset download, the offer and restart decisions, the banner wiring | **the only module with network code** (INV-15) |
| `oneup/gui/self_update.py` (new) | install kind, version parsing, the changelog slice, signature verification, the swap, the relaunch | none |
| `oneup/gui/update_key.py` (new) | `RELEASE_PUBLIC_KEY_B64` and `public_key()` | none |
| `oneup/gui/update_dialog.py` (new) | the non-modal pop-up | none |
| `packaging/sign-release.py` (new) | sign and verify an asset; generate the key pair once | none |

`self_update` imports `cryptography` **inside** `verify()`, never at module level, so a
package install, which has no `python3-cryptography` requirement, never imports it (INV-17).
`app_update._open_release` is deleted.

### 4.2 The release list and the version grammar

One request replaces `/releases/latest`:

```
GET https://api.github.com/repos/{REPO_SLUG}/releases?per_page=30
Accept: application/vnd.github+json
```

One call keeps the unauthenticated budget (60 an hour, ONEUP-0089's
`_update_check_error`) at one request per check, as today. The reply is read whole and
capped at 1 MiB; a larger body is a failed check.

```python
# self_update.py
def parse_version(tag: str) -> tuple[int, int, int] | None:
    """'v2.1.0' / '2.1.0' -> (2, 1, 0). Anything else -> None: exactly three
    dot-separated parts, each str.isascii() and str.isdigit(), one leading v/V allowed."""

@dataclass(frozen=True)
class Release:
    version: tuple[int, int, int]
    body: str                    # the CHANGELOG section, Markdown; may be ""
    appimage_url: str | None     # browser_download_url of OneUp-x86_64.AppImage
    sig_url: str | None          # browser_download_url of OneUp-x86_64.AppImage.sig
    appimage_size: int           # the asset's "size", 0 when absent

def releases_from_json(data) -> list[Release] | None:
    """None when data is not a list: the caller reports an unreadable reply. Otherwise
    every entry that is a dict, not draft, not prerelease, whose tag_name parses.
    Sorted by version, highest first. A malformed entry is dropped, never raised. An asset URL that is not
    https:// counts as absent."""

def changelog(releases, installed, offered) -> list[Release]:
    """installed < r.version <= offered, highest version first."""
```

`_version_tuple` is replaced by `parse_version` everywhere it is called
(`grep -rn _version_tuple oneup` on `fd1f527` → `app_update.py` only).

### 4.3 What is offered, by install kind

```python
def install_kind() -> str:   # self_update.py
    """'appimage' — sys.frozen and $APPIMAGE names an existing file;
       'package'  — not frozen and paths.HERE resolves to /usr/share/oneup;
       'checkout' — anything else."""
```

| Kind | Offered version | Banner shows when | Pop-up's action |
| --- | --- | --- | --- |
| `appimage` | the newest `Release` with both `appimage_url` and `sig_url` | the GitHub check finds one newer than `APP_VERSION`, not skipped | **Update now** · Skip this version · Later |
| `package` | the version part (before the first `-`) of the `system`/`oneup` `PackageModel` row's `to` | a check produced that row, newer than `APP_VERSION`, not skipped | Skip this version · Close; the text says the System update installs it |
| `checkout` | the newest `Release` | as `appimage`, signature not required | Skip this version · Close; the text says to update with git |

**On a package install the GitHub check no longer drives the banner** (§3 item 4). The pop-up
fetches the releases list when it opens, for the notes alone, and only when
`app_update_check` is on. With it off, or the fetch failing, the pop-up says the notes
could not be fetched, and the offer stands: it came from the software source.

**The About dialog's "Check for updates"** keeps its manual form. On a package install it
reports one of: the software source offers X (and opens the pop-up); OneUp X is released
but the software source does not carry it yet, and the System update will offer it once it
does; you are on the latest.

**A release with no `.sig`** — every release before the one shipping this — is listed in
the notes but never offered to an AppImage. A 2.0.0 AppImage has no updater; its users
download the first self-updating version by hand, once.

### 4.4 The pop-up

`update_dialog.UpdateDialog(QDialog)`, opened with `show()`, never `exec()` (INV-18).

- Heading: "OneUp {offered} is available — you have {installed}."
- A read-only `QTextBrowser` holding each version's notes under a "Version {v}" heading,
  newest first, rendered with `setMarkdown`. `setOpenLinks(False)` and
  `setOpenExternalLinks(False)`: a link in the notes does nothing (§3 item 1).
  `QTextBrowser.loadResource` fetches no network resource, so an image in the notes shows
  as nothing.
  Where the list holds no entry at or below `installed`, a last line says earlier
  versions' notes are not shown.
- The action row from §4.3's table. During a download: a progress bar, determinate from
  the asset's `size`, and **Cancel** in place of the actions.
- Translatable through `QCoreApplication.translate("update_dialog", …)`; accessible names on
  every control; no fixed geometry (`docs/standards/ui-and-accessibility.md`).
- **Skip this version** stores the offered version as `app_update_skip` in the window's
  `QSettings` and hides the banner. **Later** closes the pop-up and stores nothing.

The banner button is relabelled "What's new" and opens the pop-up.

### 4.5 Download and verify (AppImage only)

1. `app_update` fetches the `.sig` first, on a `QNetworkAccessManager` of its own: the one
   `_check_app_update` creates sends every reply to the check's handler. The `.sig` must be
   exactly 64 bytes, read with a 1 KiB cap.
2. It fetches the AppImage into memory, aborting past 256 MiB
   (`gh release view v2.0.0 --json assets -q '.assets[].size'` → `85309944` on 2026-11-07,
   so the cap is three times the current size). Qt 6's default redirect policy follows
   GitHub's redirect to its download host; a non-HTTPS redirect is refused by that policy.
3. `self_update.verify(data: bytes, sig: bytes, version: str) -> None` raises
   `UpdateVerificationError` unless `update_key.public_key().verify(sig, message)` passes,
   where `message` is `b"OneUp-x86_64.AppImage " + version.encode() + b"\n" + data` and
   `version` is the offered release's `X.Y.Z`. Binding the version means a genuine older
   AppImage and its `.sig`, re-attached to a newer tag, fails (finbreak FIBR-0169).
4. Only then `self_update.install(data, target)`.

**Nothing downloaded touches the disk before it verifies.** The bytes verified are the
bytes written, so there is no file to swap between check and use (finbreak FIBR-0170).

### 4.6 The swap

```python
def install(data: bytes, appimage: str) -> Path:   # self_update.py
    """target = Path(os.path.realpath(appimage)). Refuse with UpdateInstallError, before
    writing anything, when os.access(target.parent, W_OK) is false. Write data to a
    tempfile.mkstemp(prefix=".OneUp-update-", dir=target.parent), fchmod to target's
    mode, fsync, os.replace(temp, target). Any exception before os.replace unlinks the
    temp and leaves target untouched. Returns target."""
```

`realpath` because `$APPIMAGE` may be a symlink, and `os.replace` on the link would replace
the link, not the AppImage. **No root, ever** (INV-9): an AppImage in a folder the user
cannot write is reported — "OneUp can't replace itself in {folder}" — and left alone.

### 4.7 The relaunch

Both traps finbreak paid for transfer (§2):

```python
def relaunch(argv: list[str]) -> None:   # self_update.py
    """subprocess.Popen(['/bin/sh', '-c', WAITER, 'sh', *map(str, pids), '--', *argv],
    start_new_session=True, env=relaunch_env(), stdin/stdout/stderr=DEVNULL).
    The caller then quits through Updater._quit_requested's path."""
```

- **Never `os.execv`.** It cannot replace the running image's busy FUSE mount, and the
  onefile bootloader mistakes the result for a worker of the old run (finbreak 0.1.2→0.1.3).
- **`WAITER` waits until every pid has gone**, with a pid in zombie state counting as gone,
  polling every 0.1 s for at most 60 s, then `exec`s the argv. The pids are `os.getpid()`,
  plus the parent when `/proc/<ppid>/exe` resolves to the same file as `/proc/self/exe` —
  the onefile bootloader, whose exit unmounts the bundle (finbreak FIBR-0392). Waiting is
  also what lets the new process own the single-instance socket (§2).
- **`relaunch_env()`** copies `os.environ`, drops `APPDIR`, `APPIMAGE`, `ARGV0` and `OWD`,
  sets `PYINSTALLER_RESET_ENVIRONMENT=1`, and for each of `LD_LIBRARY_PATH` and
  `LD_PRELOAD` restores `<VAR>_ORIG` or drops the variable where there was none — so the
  system `/bin/sh` never loads the bundle's libraries (finbreak 0.1.6→0.1.7).
- **argv**: the AppImage path from §4.6 after a swap; `[sys.executable, HERE/updater.py]`
  for a restart on a package or a checkout. `--tray` is appended when the window is hidden
  in the tray, so a resident OneUp comes back resident.

The relaunch itself runs only in a real AppImage on a real desktop; the suites test the
command and environment it builds, and §7 says so.

### 4.8 Restart OneUp (package and checkout)

```python
def disk_version() -> tuple[int, int, int] | None:   # self_update.py
    """APP_VERSION as written in paths.HERE / 'oneup' / '__init__.py', read with
    re.search(r'^APP_VERSION = "([^"]+)"$', text, re.M) and parse_version.
    None when the file is unreadable or the line absent."""
```

Asked when a run ends (`run.on_finished`) and when the window is shown from the tray.
`disk_version()` strictly newer than `APP_VERSION` puts the update banner in its restart
form — "OneUp was updated to {v}. Restart OneUp to use it." with a **Restart OneUp**
button calling §4.7 — which takes precedence over an offer. Never asked on an AppImage:
its own swap relaunches it.

### 4.9 Signing the release (`release.sh`)

- **Once, by the user**: `python3 packaging/sign-release.py --generate` writes the private
  key to `~/.config/oneup-release/signing.key` (mode 600, refusing to overwrite) and prints
  the public key's base64, which goes into `update_key.RELEASE_PUBLIC_KEY_B64`. The private
  key never enters the repository or a Claude session. **Back it up**: a lost key means
  every installed AppImage refuses all later updates until its user downloads one by hand.
- **Each release**, after the OBS step and before the OBS report, `--no-obs` included, so
  neither failure skips the other: `release.sh` waits for that tag's Release
  workflow (`gh run watch`), downloads `OneUp-x86_64.AppImage`
  (`gh release download v$ver`, into a temporary directory: the `.sig` is not git-ignored,
  and an untracked file stops the next release's clean-tree check), signs it for `$ver` with `sign-release.py --version "$ver" --key "${ONEUP_SIGNING_KEY:-$HOME/.config/oneup-release/signing.key}"`,
  verifies the signature against the **committed** public key through
  `self_update.verify`, and uploads `OneUp-x86_64.AppImage.sig` (`gh release upload`).
  With no key, or a failed verify, it says so in red and exits 4, which wins over OBS's 3;
  the release then carries no `.sig` and no AppImage is offered it.
- **A moved tag** rebuilds the AppImage, so the old `.sig` no longer matches it.
  `release.sh --sign-only X.Y.Z` runs the signing step alone and replaces the `.sig`
  (`gh release upload --clobber`); `workflow.md` §8's move-the-tag recovery ends with it.
- `.gitignore` gains `*.key`.

### 4.10 Dependency

`cryptography` and its resolved dependencies (`cffi`, `pycparser`) join
`packaging/appimage/requirements.txt`, pinned at the latest release on the day of
implementation, resolved with that file's header command. The RPM spec gains nothing.
The new suite (§7) needs it; this machine has it (`python3 -c 'import cryptography;
print(cryptography.__version__)'` → `47.0.0` on 2026-11-07).

## 5. Correctness invariants

- **INV-1** `install_kind()` is `appimage` only when frozen with `$APPIMAGE` naming an
  existing file, `package` only for an unfrozen `paths.HERE` of `/usr/share/oneup`, and
  `checkout` otherwise. (§2 consequence 2.)
  *Test:* `tests/self-update-test.py` — each of the three, plus frozen with `$APPIMAGE`
  unset and `$APPIMAGE` naming a missing file → `checkout`.
  *Breaks when:* `$APPIMAGE` alone, without `sys.frozen`, is read as an AppImage.

- **INV-2** `parse_version` accepts exactly `[vV]?D.D.D` with ASCII digits; anything else
  is `None`. (§2 consequence 5.)
  *Test:* `tests/self-update-test.py` — `2.1.0`, `v2.1.0` accepted; `2.1.0-rc1`, `2.1`,
  `2.1.0.1`, `latest`, `2.¹.0`, `` rejected.
  *Breaks when:* the digit test uses `isdigit()` without `isascii()` (`'¹'.isdigit()` is
  true), or a fourth part is allowed.

- **INV-3** `releases_from_json` drops drafts, prereleases, non-dict entries, unparseable
  tags and non-HTTPS asset URLs, and never raises; `changelog` returns exactly the releases
  with `installed < v <= offered`, highest version first. (§2 consequence 1, §3 item 2.)
  *Test:* `tests/self-update-test.py` — a fixture list holding one of each bad kind, and
  installed `2.0.0` / offered `2.2.0` over `2.0.0, 2.3.0, 1.4.13, 2.1.0, 2.2.0` → `[2.2.0, 2.1.0]`.
  *Breaks when:* the bound is `<` on `offered` or `<=` on `installed`.

- **INV-4** On a package install the banner's offer comes only from a `system`/`oneup`
  `PackageModel` row; a newer GitHub release with no such row shows no banner. (§3 item 4.)
  *Test:* `tests/gui-smoke.py` — `install_kind` forced to `package`; a stubbed list
  advertising `9.0.0` and no check row → banner hidden; then a `CHECK_ITEM` row
  `system|oneup|2.0.0-1.1|2.1.0-1.1` → banner shown offering `2.1.0`.
  *Breaks when:* the package path still reads the GitHub reply's newest tag.

- **INV-5** Nothing in this feature opens a browser or fetches a remote resource for the
  notes: `_open_release` is gone, and the notes browser has both link-opening properties
  off. (§3 item 1.)
  *Test:* `tests/gui-smoke.py` — `QDesktopServices.openUrl` patched to record; the pop-up
  shown with notes holding a link and an image; the link activated → nothing recorded,
  `openLinks()` and `openExternalLinks()` both false. `grep -n openUrl
  oneup/gui/app_update.py oneup/gui/update_dialog.py` → no lines.
  *Breaks when:* the text widget is a `QLabel` with `setOpenExternalLinks(True)`, as the
  About box's is.

- **INV-6** Nothing is written unless the signature verifies against
  `update_key.public_key()`. (§2 consequence 3; the trust boundary.)
  *Test:* `tests/self-update-test.py` — a throwaway key patched into `update_key`; good
  bytes and signature → `verify` returns; one flipped byte in the data, one in the
  signature, a 63-byte signature, a signature made for another version, and a signature
  from a second key → each raises `UpdateVerificationError`. That nothing is written after
  a failed verify is INV-7's test.
  *Breaks when:* `verify` is skipped on a fetched `.sig` of the wrong length, or the
  verify result is caught and ignored.

- **INV-7** The downloaded bytes reach the disk only through `install`, after `verify`.
  *Test:* `tests/gui-smoke.py` — the download path driven with a fake reply; the
  target's folder and `tempfile.gettempdir()` listed before `verify` returns → no file
  from this download; a `.sig` that fails `verify` → `install` never called, the target
  byte-identical.
  *Breaks when:* the download streams to a temporary file that is verified and then
  re-read (finbreak's pre-FIBR-0170 shape).

- **INV-8** `install` writes beside the real file, keeps its mode and replaces it
  atomically; any failure before the replace leaves the original byte-identical and no
  temporary file behind.
  *Test:* `tests/self-update-test.py` — a 0755 target reached through a symlink → the
  symlink still a symlink, the real file holding the new bytes at 0755; `os.replace`
  patched to raise → original unchanged, folder listing unchanged.
  *Breaks when:* the temp is made in `/tmp` (a cross-filesystem `os.replace` raises
  `EXDEV`), or `$APPIMAGE` is not resolved.

- **INV-9** The self-update never asks for root: an unwritable folder is refused before
  anything is written, and `self_update.py` names no privileged route.
  *Test:* `tests/self-update-test.py` — a target in a 0555 folder → `UpdateInstallError`,
  nothing written; `grep -nE 'sudo|pkexec|service_client|rootops' oneup/gui/self_update.py`
  → no lines.
  *Breaks when:* an unwritable folder falls back to a root copy.

- **INV-10** `relaunch` spawns `/bin/sh` detached (`start_new_session=True`) with the
  waiter, its pids and the argv, and an environment holding
  `PYINSTALLER_RESET_ENVIRONMENT=1`, none of `APPDIR`/`APPIMAGE`/`ARGV0`/`OWD`, and each
  loader variable restored from `<VAR>_ORIG` or absent; it never calls `os.exec*`.
  *Test:* `tests/self-update-test.py` — `subprocess.Popen` patched to record; an
  environment with `LD_LIBRARY_PATH=/tmp/_MEIx`, `LD_LIBRARY_PATH_ORIG=/usr/lib64` and
  `LD_PRELOAD=/tmp/_MEIx/a.so` with no `_ORIG` → recorded env has
  `LD_LIBRARY_PATH=/usr/lib64` and no `LD_PRELOAD`; the waiter run for real against a
  child `sleep 0.5` pid exits after that child, not before. The relaunch inside a real
  AppImage is the §7 manual recipe.
  *Breaks when:* the waiter inherits the bundle's `LD_LIBRARY_PATH` (finbreak 0.1.6), or the
  relaunch is an `execv` (finbreak 0.1.2).

- **INV-11** Every read is capped: the list at 1 MiB, the `.sig` at 1 KiB and exactly 64
  bytes, the AppImage at 256 MiB; an over-cap read aborts and stores nothing.
  *Test:* `tests/gui-smoke.py` — the reply handlers fed one byte over each cap →
  aborted, nothing written.
  *Breaks when:* a cap is checked on `Content-Length` only, which a server may omit.

- **INV-12** Update now and Restart OneUp are disabled while `Updater._run_active` is true,
  with a tooltip saying why, and enabled when it clears. (§3 item 8.)
  *Test:* `tests/gui-smoke.py` — `_run_active` set → both disabled; `run.on_finished`
  driven → both enabled.
  *Breaks when:* the buttons read the state once, when the pop-up opens.

- **INV-13** The restart banner shows exactly when `disk_version()` is strictly newer than
  `APP_VERSION`, never on an AppImage. (§2 consequence 4, §3 item 5.)
  *Test:* `tests/gui-smoke.py` — `paths.HERE` redirected to a sandbox holding an
  `oneup/__init__.py` with a newer, equal, older and absent `APP_VERSION` line; a run's end
  driven each time → banner in restart form only for the newer one.
  *Breaks when:* the comparison is `!=`, so a downgrade asks for a restart.

- **INV-14** Skip this version persists the offered version and hides that version's
  banner across windows; a newer version is offered again; Later persists nothing.
  *Test:* `tests/gui-smoke.py` — Skip on `2.1.0`, a new window and a reply offering
  `2.1.0` → no banner; offering `2.2.0` → banner; Later → `app_update_skip` unchanged.
  *Breaks when:* the skip is compared with `<=` instead of `==`, which would silence every
  later version too.

- **INV-15** `app_update.py` is the only module under `oneup/` that makes network requests.
  *Test:* `tests/imports-test.py`, an AST walk like its other checks — no module under
  `oneup/` but `app_update.py` imports `QNetworkAccessManager`, `urllib` or `http.client`,
  or names `socket.create_connection`; a planted `import urllib.request` in a scratch copy
  of another module → flagged.
  *Breaks when:* the download moves to `self_update.py`.

- **INV-16** No private key material is tracked, and `sign-release.py` round-trips: a
  signature it makes verifies through `self_update.verify` with the matching public key.
  *Test:* `tests/self-update-test.py` — `git ls-files` holds no `*.key` and no file
  matching `-----BEGIN [A-Z ]*PRIVATE KEY-----`; a throwaway key pair generated, a file signed, verified → passes;
  verified against a second key → `UpdateVerificationError`.
  *Breaks when:* the signer signs a hash of the file while the verifier checks the file.

- **INV-17** A package install never imports `cryptography`.
  *Test:* `tests/imports-test.py`, an AST walk like its other checks — no module under
  `oneup/` imports `cryptography` outside a function body.
  *Breaks when:* `update_key` or `self_update` imports it at module level.

- **INV-18** The pop-up is non-modal and every control in it is named.
  *Test:* `grep -n '\.exec(' oneup/gui/update_dialog.py` → no lines; `tests/gui-smoke.py`'s
  accessible-name walk covers the shown pop-up.
  *Breaks when:* the pop-up is opened with `exec()`, which blocks the run's output.

- **INV-19** A failed check stays silent at startup and is reported on the manual check
  as today; it never raises out of the network slot.
  *Test:* `tests/gui-smoke.py` — a stubbed reply with HTTP 403, a non-JSON body and a JSON
  object → no box when automatic; when manual, the ONEUP-0089 wording for the 403 and
  "Couldn't read GitHub's reply" for the other two.
  *Breaks when:* a non-list body is read as an empty list, or raises out of the slot.

## 6. Failure modes

| What goes wrong | What the user sees | Why it is safe |
| --- | --- | --- |
| GitHub unreachable or rate-limited | nothing at startup; the ONEUP-0089 message on a manual check | no offer is made |
| Package install, GitHub fails | the pop-up says the notes could not be fetched; the offer stands | the offer came from the software source |
| The newest release has no `.sig` | AppImage: no offer for it; its notes still appear under a signed later version | INV-6 |
| Download interrupted or cancelled | "The download didn't finish" and the actions return | nothing was written (INV-7) |
| Signature fails | "This download couldn't be proved to come from OneUp's author, so it was not installed." | INV-6 |
| AppImage folder not writable | "OneUp can't replace itself in {folder}" | no root (INV-9) |
| Disk full during the write | the write's `OSError` reported; the old AppImage runs on | INV-8 |
| The waiter times out (old process stuck) | the new copy starts, finds the old one and hands over to it; the user has the old window | the swap already happened; the next start runs the new file |
| The relaunch never starts (sh missing) | OneUp closes and does not reopen; the new AppImage is in place | the next launch runs the new version |
| `disk_version()` unreadable | no restart banner | the old window still works |
| The signing key is lost | releases ship unsigned; AppImages are offered nothing | users download one by hand; see §4.9 |
| A GitHub account compromise swaps the AppImage after signing, or re-attaches an older signed AppImage to a newer tag | the asset fails verification | the key is not on GitHub (§3 item 6); the signature covers the version (§4.5) |
| A compromise of the CI build itself, before signing | **not defended**: this PC signs what CI built | residual risk of §3 item 6; the build set is pinned (ONEUP-0060) |

## 7. Tests

| Invariant | Where |
| --- | --- |
| INV-1, INV-2, INV-3, INV-6, INV-8, INV-9, INV-10, INV-16 | `tests/self-update-test.py` (new) — stdlib plus `cryptography`; a throwaway key; synthetic bytes; no network (`docs/standards/testing.md` §2). Exits 77 when `cryptography` is absent. Added to `local-CI.sh`, and to `release.yml` after the requirements install, where exit 77 fails the step |
| INV-4, INV-5, INV-7, INV-11, INV-12, INV-13, INV-14, INV-18, INV-19 | `tests/gui-smoke.py`, with each network entry point in `app_update` — the check, the pop-up's list fetch, the download — stubbed as `_check_app_update` is today, under the ONEUP-0098 gate that refuses any real request, and replies injected |
| INV-15, INV-17 | `tests/imports-test.py` |

Each test is seen failing against a tree without its rule before it is called green.

**What no suite covers:** the relaunch inside a real AppImage on a real desktop — the FUSE
mount, the onefile bootloader and the single-instance handover. **Manual recipe**, run on
the first signed release and on the clean test VM: install AppImage N, publish N+1
signed, press What's new → Update now; OneUp closes and reopens on N+1 within a few
seconds, in the same tray state, with one tray icon. Repeat with OneUp hidden in the tray.
Then the package path: install the RPM at N, let OBS build N+1, run the System update;
the restart banner appears; Restart OneUp reopens on N+1.

## 8. Docs & release

- `CHANGELOG.md` `[Unreleased]`: Added — the What's new pop-up; AppImage self-update;
  Restart OneUp.
- `README.md`: the AppImage section says it updates itself from this version on, and that
  2.0.0 users download once by hand.
- `docs/standards/security.md`: a section on the self-update — the trust boundary (§4.5),
  the signing key's home and backup (§4.9), never root (INV-9), the residual risk (§6) —
  and its **What checks this** rows.
- `docs/standards/workflow.md` §8: the release's signing step, `--sign-only` after a moved
  tag, and the one-time key setup.
- `docs/standards/dependencies.md`: `cryptography`, `cffi`, `pycparser` in the AppImage set.
- `docs/standards/testing.md` §1 and `CLAUDE.md` §2: the new suite.
- `docs/standards/files-and-naming.md` and `docs/specs/ONEUP-0034-gui-modules.md`'s module
  table: the three new modules; `app_update.py`'s row loses "opening the release page".
- `docs/specs/ONEUP-0028-accessibility.md`'s name table: the pop-up's controls; the
  banner button's new label.
- `docs/reference/marker-protocol.md`: unchanged — no marker is added.
- No version site changes.

## 9. Alternatives considered (and rejected)

- **Sign in CI with a GitHub secret** — rejected by the user: whoever gets into the GitHub
  account could sign a fake update.
- **Build and sign on this PC** — rejected by the user: every release would need a long
  local build on a good connection.
- **Link to the GitHub release page** — rejected by the user (§3 item 1).
- **Self-update a package install** — rejected: it writes behind zypper's back and corrupts
  the package database (§3 item 4).
- **AppImage's own GPG signature with AppImageUpdate/zsync** — rejected: it needs `gpg`
  and an extra updater tool on the user's machine, and has no reference implementation
  here; Ed25519 with a committed key has finbreak's.
- **Verify with the machine's `openssl`** — rejected: its version varies by machine, and a
  program started from the bundle meets the `LD_LIBRARY_PATH` trap ONEUP-0383 just fixed.
- **Sign a `SHA256SUMS` file instead of the AppImage** — rejected: there is one asset, and
  signing the version with the bytes (§4.5) gives the binding finbreak's manifest gives
  (FIBR-0169) without a second file.
- **Two requests, `/releases/latest` then the list** — rejected: it doubles the use of a
  60-an-hour budget for no information the list lacks.
- **Download to a temporary file, then verify** — rejected: finbreak's FIBR-0170 closed
  that check-then-use gap; 256 MiB in memory is affordable for a one-off.
- **`os.execv` for the relaunch** — rejected: finbreak's 0.1.2→0.1.3 bug (§4.7).

## 10. Out of scope

- Rotating the signing key — deferred; not yet queued.
- Delta or background downloads, or installing without a click (§3 item 7) — deferred; not
  yet queued.
- Updating a developer checkout — git's job (§3 item 9).
- A test that verifies a real signed release against the committed key (finbreak INV-15)
  — it needs a signed release to exist; deferred; not yet queued.
- Run repeating a fresh Check — ONEUP-0384.

## 11. Cold-eyes loop log

| Loop | Date | Findings | Outcome |
| --- | --- | --- | --- |
| 1 | 2026-11-07 | Q1 4 · Q2 4 · Q3 4 · Q4 2 — 14 verified, 1 dismissed | all 14 fixed. Two lanes, each holding every question. Four came from building the packet, fixed before dispatch: a genuine older AppImage and its `.sig` re-attached to a newer tag passed the signature (finbreak FIBR-0169), so the signature now covers the version; a quoted `~` in the key path that bash leaves literal; the signing step pointed at `workflow.md` §5, not §8; and INV-17 importing Qt in the stdlib-only `tests/imports-test.py`. Both lanes found the download routed through `win._nam`, whose `finished` feeds the check's handler, and INV-19 treating a JSON list, the new endpoint's success shape, as a failure. One lane each found INV-15's grep against `imports-test.py`'s AST rule, INV-16's `PRIVATE KEY` match failing on this spec, `installed + 1` on a version triple, INV-7 and INV-11 placed in a suite that has no Qt, the signing step's order and exit code against OBS's, the releases list's sort order, and the suite's exit 77 skipping in `release.yml`. One Q3 came from settling a lane's open question: the pop-up's list fetch and the download met the ONEUP-0098 network gate with no stub named. Dismissed: §2's restart grep also hits `rollback.py`, `run.py` and `layout_host.py`, all about the computer or services, so no code changes. Seven open questions resolved clean. Unrunnable here: the relaunch inside a real AppImage (§7's manual recipe). |
| 2 | 2026-11-07 | Q2 2 · Q3 1 · Q4 1 — 4 verified, 0 dismissed | all 4 fixed; the cap for a spec, so these fixes are read by no lane, and implementation reads them. Two lanes, each holding every question. Both found `releases_from_json` turning a JSON object into an empty list, which a manual check would report as up to date; INV-6's "`install` called" in a suite where nothing calls `install`; and signing "after the OBS step" left open against `release.sh`'s exit-3 report. One lane found `workflow.md` §8's move-the-tag recovery leaving a `.sig` that no longer matches the rebuilt AppImage, so `release.sh --sign-only` now re-signs. Calm cap: 1 of 4 findings landed on text this run wrote (the signing order). The second share is unreadable, since the armed change was the whole document. Six open questions resolved clean, one by a PyInstaller build showing a function-level `cryptography` import is bundled. |
| impl | 2026-11-08 | none: an implementation record, no reviewer dispatched | **Built as specified; five points the spec left open, settled in the build.** Each request runs on a `QNetworkAccessManager` of its own and connects only its own reply, so no reply reaches another request's handler. A manual check that finds a newer AppImage or checkout release opens the pop-up instead of a message box, as §4.3 already says for a package. `relaunch_env()` also drops the `<VAR>_ORIG` copies after restoring from them, as finbreak does. A run started while the AppImage downloads stops the swap, so §3 item 8 holds for the whole download, not only the press. `update_key.RELEASE_PUBLIC_KEY_B64` is empty until the user makes the key (§4.9); until then nothing verifies and `release.sh` exits 4. Every suite's new test was seen failing against a mutated rule first. Not yet run: §7's manual recipe, which needs a signed release. Rule 14: an implementation record; no gate. |
