"""Reading what the engine said, and saying it in English.

`docs/reference/marker-protocol.md` is the contract; this module holds the
splitting of a marker line into its name and fields, and the three formatters
that turn a payload into the words the window shows.
"""
from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QCoreApplication


def fallback_long(*codes: str) -> str:
    """What a site with room for a sentence shows when it cannot word what the engine
    sent (ONEUP-0108 §4.3): a code it has no entry for, a known code whose arguments
    do not fit, an unknown step key. Readable, never the bare token, never empty; it
    names what it could not word, for a bug report, and points at the log."""
    return (f"This version of OneUp has no wording for what the update reported "
            f"({', '.join(codes)}). The log has the details.")


# @@HINT@@'s codes (ONEUP-0072 §4.2): one per sentence, allocated with the engine
# branch that sends it, and its sentence carried across from the engine unchanged
# (§3.2). Each entry is the argument names, in the order they arrive, and the
# sentence. A shipped code is never reused for another meaning; a retired one is
# commented out here, not deleted — this table is the register.
_SIZE = "Couldn't work out the download size: "
_DOWNLOAD = ("openSUSE's servers are still catching up with this update. Nothing was "
             "installed and everything already downloaded has been kept; try again later.")
_BUSY = ("Something else is installing or removing software right now — {name} (process "
         "{pid}). That is often OneUp's own earlier run still finishing in the background; "
         "it clears on its own. Nothing was changed, so just run the update again in a "
         "minute.")
HINTS: dict[str, tuple[tuple[str, ...], str]] = {
    "downloads-kept": ((), "Kept the already-downloaded packages, so retrying the update "
                           "doesn't fetch them all over again."),
    "refresh-failed-cached": ((), "Couldn't refresh one or more repositories — upgraded from "
                                  "cached metadata. A future run should refresh cleanly."),
    "progress-unrecognised": ((), "Packages were installed, but OneUp couldn't follow the "
                                  "progress — zypper has probably renamed the lines it reports "
                                  "progress on. The update itself was fine; please report this "
                                  "so the progress display can be updated."),
    "repos-set-aside": (("aliases",), "Updated everything except: {aliases} — set aside this run "
                                      "(temporary problem); OneUp will retry next time."),
    "download-recovered": ((), "Recovered from a failed download — some packages were fetched "
                               "from openSUSE's content delivery network instead of the mirror "
                               "that failed."),
    "repos-failing-systemic": ((), "Several repositories are failing at once — likely a network "
                                   "or system problem, not a single bad source. Check your "
                                   "connection and retry."),
    "download-failed-package": (("package",), "Could not download {package} — " + _DOWNLOAD),
    "download-failed": ((), "A package could not be downloaded — " + _DOWNLOAD),
    "disk-full": ((), "Ran out of disk space — free some room (clear the package cache, delete "
                      "old snapshots) and retry."),
    "repo-key-still-rejected": ((), "A repository signing key is still rejected even after "
                                    "importing keys — check the log for the offending "
                                    "repository, or run: sudo zypper --gpg-auto-import-keys "
                                    "refresh, then retry."),
    "repo-key-expired": ((), 'A repository signing key is out of date. Use "Import signing key '
                             '& retry" to fix it, or run: sudo zypper --gpg-auto-import-keys '
                             "refresh, then retry."),
    "network-failed": ((), "A download failed — check your internet connection, then retry."),
    "package-conflict": ((), "A package conflict — often a third-party repo. Check the log; you "
                             "may need to disable a conflicting repository."),
    "go-ahead-unverified": ((), "OneUp could not verify the request to start the update, so "
                                "nothing was changed. Press Update again."),
    "package-manager-busy": (("pid", "name"), _BUSY),
    "package-manager-busy-unnamed": (("pid",), _BUSY.replace("{name}", "another program")),
    "oneup-already-running": (("pid",), "Another OneUp update is already running (process "
                                        "{pid}). Nothing was changed. Open OneUp to follow it, "
                                        "or run the update again once it has finished."),
    "passwordless-unsupported": ((), "Passwordless authorization can't be set up on this "
                                     "machine: zypper, timeout or du was not found, or the "
                                     "refresh budget is not a whole number of seconds."),
    "size-busy": ((), _SIZE + "another program is using the package manager (PackageKit, or a "
                              "zypper you have open elsewhere) — close it and try again."),
    "size-cancelled": ((), _SIZE + "OneUp wasn't allowed to run the check as administrator — "
                                   "the password prompt may have been cancelled."),
    "size-no-sources": ((), _SIZE + "no software sources are enabled, so there is nothing to "
                                    "weigh up."),
    "size-failed": (("code",), _SIZE + "the package manager reported an error (code {code}) — "
                                       "see the lines below."),
    "temp-file-failed": ((), "Could not create a temporary file."),
    "auth-rule-invalid": ((), "The generated authorization rule failed validation — nothing "
                              "was changed."),
    "guard-write-failed": (("path",), "Could not write the download helper ({path})."),
    "auth-write-failed": (("path",), "Could not write the authorization rule ({path})."),
    "auth-remove-failed": (("path",), "Could not remove the authorization rule ({path})."),
    "snapper-missing": ((), "Snapper isn't installed, so there are no snapshots to thin."),
    "snapshots-unreadable": ((), "Couldn't read the list of restore points, so OneUp can't "
                                 "tell whether any were removed."),
    "snapper-cleanup-failed": ((), "Snapper's cleanup failed, so no restore points were "
                                   "removed."),
    "stopped": ((), "Stopped at your request. Anything already installed stays installed — a "
                    "stop never interrupts an install half-way, because that can leave programs "
                    "broken. Run the update again whenever you like."),
    "repo-slow": (("alias",), "The '{alias}' source is serving updates too slowly to wait for, "
                              'so OneUp moved on. Use "Skip {alias} & update the rest" to leave '
                              "it out of the next run, or try again later."),
}


def render_hint(fields: list[str]) -> str:
    """The sentence for a @@HINT@@'s fields — the code, then its arguments. A code
    the table does not know, or whose arguments do not fit, gets the long fallback
    (ONEUP-0108 §4.3) rather than a bare token or an exception in the read slot."""
    code, args = (fields[0] if fields else ""), fields[1:]
    entry = HINTS.get(code)
    if entry is None or len(args) != len(entry[0]):
        return fallback_long(code or "an empty hint")
    return entry[1].format(**dict(zip(entry[0], args, strict=True)))


def fallback_remedy(code: str) -> str:
    """What the banner says beside the run's hint when the engine offers a fix this
    window does not know: no button is armed, since there is no action it can
    perform (ONEUP-0072 §4.1, ONEUP-0108 INV-1)."""
    return (f"This version of OneUp has no fix for what the update reported ({code}). "
            "The log has the details.")


# @@CHECK_UNKNOWN@@'s codes (ONEUP-0072 §4.1): why a --check could not read a source.
# Each entry is its fixed argument count — None for a variable tail of names, where
# any count is valid data (ONEUP-0108 §4.1) — and the function that words it. The
# two lists join with ", " and keep their tails, as the engine wrote them (§4.2);
# zero names is an engine defect and renders the sentence with an empty list (§4.3).
_INCOMPLETE = " — this list may be incomplete."
_REFRESH = " Running an update refreshes them."
CHECK_UNKNOWN: dict[str, tuple[int | None, Callable[[list[str]], str]]] = {
    "sources-unreadable": (None, lambda names: "OneUp couldn't read these software "
                           "sources: " + ", ".join(names) + _INCOMPLETE + _REFRESH),
    "sources-unknown-error": (1, lambda a: "OneUp couldn't read the software sources "
                              f"(zypper exited {a[0]})" + _INCOMPLETE + _REFRESH),
    "flatpak-remotes-unreachable": (None, lambda names: "OneUp couldn't reach these "
                                    "Flatpak sources: " + ", ".join(names) + _INCOMPLETE),
    "fwupd-unreachable": (0, lambda _a: "OneUp couldn't ask fwupd"),
}


def render_check_unknown(fields: list[str]) -> str:
    """The sentence for a @@CHECK_UNKNOWN@@'s fields after the step key — the code,
    then its arguments. An unknown code, or a fixed-arity one whose arguments do not
    fit, gets the long fallback (ONEUP-0108 §4.3)."""
    code, args = (fields[0] if fields else ""), fields[1:]
    entry = CHECK_UNKNOWN.get(code)
    if entry is None or (entry[0] is not None and len(args) != entry[0]):
        return fallback_long(code or "an empty reason")
    return entry[1](args)


# @@REBOOT@@'s reason (ONEUP-0072 §4.1): component codes joined into one sentence, or
# one standalone code with a sentence of its own. The two sets are disjoint. Each
# component is a fragment joined into "… was/were installed" — the one carve-out from
# wording-and-translation.md §6.2 — and its English is the engine's, unchanged.
REBOOT_COMPONENTS = {
    "kernel-new": "a new kernel",
    "graphics-driver-nvidia": "your NVIDIA graphics driver",
    "graphics-driver-generic": "your graphics driver",
    "kernel-modules": "kernel driver modules",
}
REBOOT_STANDALONE = {
    "core-packages-updated": "core system packages were updated",
    "firmware-updated": "firmware was updated",
}
_INSTALLED = "{items} were installed"


def _join_items(items: list[str]) -> str:
    """The engine's English join (ONEUP-0108 §4.2): one bare, two with " and ",
    three or more as "a, b, and c" with the serial comma."""
    if len(items) <= 2:
        return " and ".join(items)
    return ", ".join(items[:-1]) + ", and " + items[-1]


def render_reboot_reason(field: str) -> str:
    """The sentence for @@REBOOT@@'s reason field, by ONEUP-0108 §4.4's rows in
    order. "" when the field is absent: nothing was reported, so there is nothing
    the window failed to word."""
    elems = field.split()
    if not elems:
        return ""
    if len(elems) == 1 and elems[0] in REBOOT_STANDALONE:
        return REBOOT_STANDALONE[elems[0]]
    unknown = [e for e in elems if e not in REBOOT_COMPONENTS and e not in REBOOT_STANDALONE]
    if any(e in REBOOT_STANDALONE for e in elems) or len(unknown) == len(elems):
        # Both vocabularies, or neither: never the join (§4.4). Name what it could
        # not recognise, or every element when it recognised them all (§4.3).
        return fallback_long(*(unknown or elems))
    rendered = [REBOOT_COMPONENTS.get(e, e) for e in elems]   # unknowns as bare codes
    n = len(rendered)
    sentence = QCoreApplication.translate(
        "markers", _INSTALLED,
        "reboot reason; {items} is a joined list of things like 'a new kernel'", n)
    if sentence == _INSTALLED and n == 1:
        # No catalogue answered, and a verb has no "(s)" idiom: English agrees with
        # what the sentence lists, unknown codes included (ONEUP-0108 §4.2, INV-2).
        sentence = "{items} was installed"
    return sentence.format(items=_join_items(rendered))


def split_marker(line: str) -> tuple[str, list[str], str] | None:
    """Split an `@@TAG@@|payload` line into (tag, fields, raw payload).

    None for a line that starts with `@@` but is not a marker: a diff hunk
    header ("@@ -1,4 +1,4 @@") is ordinary output and must be logged rather
    than dropped.
    """
    try:
        tag, rest = line[2:].split("@@|", 1)
    except ValueError:
        return None
    return tag, rest.split("|"), rest


# @@STEP_END@@'s codes and the badge each one shows (ONEUP-0072 §4.1's closed set;
# ONEUP-0108 §4.1). The second value is how many arguments the code carries — a
# step with no number sends a different code, never the same one without it — and
# the badge's {count} is filled from that argument. A shipped code is never reused
# for another meaning; a retired one is commented out here, not deleted, because
# this table is the register (ONEUP-0072 §4.2).
STEP_BADGES: dict[str, tuple[int, str]] = {
    "up-to-date": (0, "Up to date"),
    "installed": (1, "{count} installed"),
    "removed": (1, "{count} removed"),
    "updated": (0, "Updated"),
    "done": (0, "Done"),
    "not-installed": (0, "Not installed"),
    "skipped": (0, "Skipped"),
    "failed": (0, "Failed"),
}


def _step_badge(status: str, code: str, args: list[str]) -> str:
    """A short per-row badge for a finished step, from its @@STEP_END@@ status,
    code and arguments — e.g. '3 installed', 'Up to date', 'Failed', 'Skipped'.

    `status` decides a failure before the code is read, as it always has: a
    failed step badges "Failed" whatever its code (ONEUP-0072 §4.1). A code the
    table does not know, or whose arguments do not fit it, shows the bare code —
    the short fallback, since a badge has no room for a sentence (ONEUP-0108
    §4.3) — and never raises out of the read slot.
    """
    if status == "fail":
        return "Failed"
    # ONEUP-0190: the status field is exactly one of ok / skip / fail. Anything
    # else earned no success badge, so say we cannot tell rather than "Done".
    if status not in ("ok", "skip"):
        return "Result unknown"
    entry = STEP_BADGES.get(code)
    if entry is None or len(args) != entry[0] or not all(a.isdecimal() for a in args):
        # An empty code has no token to show — the frozen Bash fallback sends one
        # for the cache step's success (ONEUP-0072 §6) — so it reads like any
        # other outcome the window cannot tell.
        return code or "Result unknown"
    return entry[1].format(count=args[0]) if args else entry[1]


def _format_duration(secs: int) -> str:
    """A compact human duration: '<1s', '42s', '1m 5s'."""
    if secs < 1:
        return "<1s"
    if secs < 60:
        return f"{secs}s"
    return f"{secs // 60}m {secs % 60}s"

def _format_size(n: int) -> str:
    """A compact human size: '900 B', '512 KiB', '41 MiB', '1.4 GiB'.

    Binary units, labelled as such (ONEUP-0190) — the same MiB zypper prints in
    the log pane, so the two figures agree.
    """
    if n >= 1 << 30:
        return f"{n / (1 << 30):.1f} GiB"
    if n >= 1 << 20:
        return f"{n / (1 << 20):.0f} MiB"
    if n >= 1 << 10:
        return f"{n / (1 << 10):.0f} KiB"
    return f"{n} B"
