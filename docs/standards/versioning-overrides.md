# Breaking surfaces — what makes a release MAJOR

**In one sentence:** this is the list of things a OneUp user or their machine relies on
across an update, so that a change which breaks one of them is released as a new major
version and not slipped out as a fix.

**Status:** Draft
**Kind:** doc
**Roadmap:** ONEUP-0339
**Branch:** v2
**Verified at:** `7f8519c` — every path, symbol and name below was read in this tree on
2026-10-26, not recalled.

## 1. What this file is

`~/.claude/standards/versioning.md` decides which number a release bumps. Its §3 asks each
project to name its own breaking surfaces in this file, and this is OneUp's answer.
`docs/standards/workflow.md` §5 applies the levels to OneUp's releases.

OneUp is past `1.0`, so `versioning.md` §4's exit condition does not apply.

## 2. The rule

**A change is breaking when something in §3 that worked before an update stops working
after it.** It is then a MAJOR release (`versioning.md` §2).

- **Removing, renaming or changing the meaning of a surface breaks it.**
- **A change that keeps the old form working does not.** A new option is compatible, and so
  is a renamed setting that the new version carries over.
- **A surface missing from this list is still a surface** (`versioning.md` §3). Add it here
  when you find it.

## 3. The surfaces

| Surface | Defined in | Who relies on it across an update |
| --- | --- | --- |
| The marker contract — every marker, its fields and their order | `docs/reference/marker-protocol.md` | Anything reading the engine's output. That reference's §5 says which added field breaks a reader |
| The step keys `system`, `flatpak`, `firmware`, `orphans`, `cache` | `ALL_STEPS` in `oneup/engine/__main__.py` | A user's own command or script; `--steps=` and `--size=` take them |
| The command-line options | the engine's `parse` in `oneup/engine/__main__.py`; the window's `--check`, `--update` and `--tray` in `main` in `oneup/gui/app.py` | A user's own command or script, and the timer units an older copy wrote, which run the window with `--check` or `--update` (`TIMERS` in `oneup/gui/autostart.py`) |
| The four state files `run.state`, `stop.request`, `hold.state`, `go.request` | `docs/reference/marker-protocol.md` §8 | A window following a run that another copy started |
| The saved settings — every key in `~/.config/OneUp/OneUp.conf` | each `QSettings("OneUp", "OneUp")` read in `oneup/gui/`; `git grep -n 'setValue("' -- oneup/gui` lists the keys | The user. A key renamed with no carry-over resets their choice to its default |
| The installed helper files | `~/.config/autostart/za.co.antsprojectshub.OneUp-tray.desktop` and the `oneup-check` and `oneup-update` user timers (`oneup/gui/autostart.py`); `/etc/sudoers.d/oneup` and the download guard (`AUTH_FILE` and `GUARD_FILE` in `oneup/engine/actions.py`) | The user's start-at-boot, weekly check, weekly update and *Passwordless* settings. A renamed file leaves the old one behind and the setting reads off. Changing the guard's text also ends every existing grant (`docs/standards/security.md` §5.7) |
| The system service's interface — its bus name, object path and methods, and the polkit actions it checks | `BUS_NAME`, `OBJECT_PATH` and the method table in `oneup/service/server.py`; `SYSTEM_UPDATE` and `TRUST_SIGNING_KEY` in `oneup/service/polkit.py` | The engine, which is a separate process from the service. An administrator's polkit rule written for those actions |
| The version's spelling at its six sites, and the release tag | `docs/standards/workflow.md` §5.1 | Every installed copy's update check, which compares the newest release tag's digits with `APP_VERSION` (`_version_tuple` in `oneup/gui/app_update.py`) |
| The app ID `za.co.antsprojectshub.OneUp` | the desktop file, icon and AppStream metainfo under `data/` | The desktop's menu entry, a pinned launcher and a software-centre listing, which treat a new ID as a different program |

## What checks this

| Rule | What catches a breach |
| --- | --- |
| §2 — a breaking change to a surface is released as MAJOR | **nothing.** `release.sh` takes the version as an argument and never questions it (`workflow.md`'s *What checks this*, its §5 row). A person reading the `[Unreleased]` entries decides it |
| §3 — a surface's change is noticed at all | **partly, and for some surfaces only.** The engine suite fails when a marker's field count leaves its pinned set (`LAYOUT` in `tests/run-tests.sh`), so a reorder passes. `local-CI.sh`'s version-lockstep gate fails when the six sites disagree, so a change made alike at all six passes. Neither says the release must be MAJOR. Nothing notices a change to the other surfaces |
| §3 — the list is complete | **nothing.** A missing surface is found when an update breaks it |

## Cold-eyes loop log

The rows are in [`docs/reviews/versioning-overrides-loop-log.md`](../reviews/versioning-overrides-loop-log.md).
