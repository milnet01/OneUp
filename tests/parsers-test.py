#!/usr/bin/env python3
"""Table-driven tests for oneup/engine/parsers.py — the pure half of the engine.

`docs/specs/ONEUP-0054-python-engine.md` §4.3.4: `to_bytes`, the zypper progress
wordings, the two download-size wordings, `lr` output and `lock_holder`'s text
are today reachable only through a full engine run. As pure functions they get a
table instead, which is the right shape for the stale-parser canary — the
scenario *"a transaction with no recognisable progress lines says so"* exists to
fire when zypper changes its wording under us, and it can only fire on wordings
somebody wrote down.

Every input here is real captured output, quoted from `update_system.sh`'s own
worked examples and from the mocks `tests/run-tests.sh` ships. A table invented
from the docstring tests the docstring.

Stdlib-only, exit 0 on success and 1 on any failure, so it runs wherever Python
does — `local-CI.sh` and the release workflow both name it by hand, because
nothing in this project discovers tests.
"""
import sys
from pathlib import Path

# The repo root, so `oneup.engine` imports without an install step.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from oneup.engine import parsers

PASS = 0
FAIL = 0


def check(name: str, got, want):
    global PASS, FAIL
    if got == want:
        print(f"  ok   - {name}")
        PASS += 1
    else:
        print(f"  FAIL - {name}: got {got!r}, want {want!r}")
        FAIL += 1


# --- to_bytes ----------------------------------------------------------------
# Integer arithmetic with ONE fractional digit and truncating division. Every
# expected value below was read back from the Bash `to_bytes` itself, not
# computed here: `1.3 GiB` is 1395864371 and not 1395864371.2 rounded up.
TO_BYTES = [
    # (number, unit, bytes, why this row is here)
    ("31.0", "KiB", 31744, "the worked example in progress_filter's comment"),
    ("1.3", "GiB", 1395864371, "the Leap download-size line; truncates, never rounds"),
    ("371.4", "MiB", 389441126, "the Tumbleweed download-size line"),
    ("86.4", "MiB", 90596966, "the ONEUP-0048 slow-mirror figure"),
    ("0", "B", 0, "a definite zero is a real answer"),
    ("31", "MiB", 32505856, "no decimal point at all"),
    ("08.0", "MiB", 8388608, "zero-padded: decimal, never an invalid octal literal"),
    ("1.25", "GiB", 1288490188, "a second fractional digit is dropped, not rounded"),
    ("12.5", "KB", 0, "KB passes progress_filter's regex and is NOT a unit we know"),
    ("1.9", "TiB", 0, "an unknown unit is 0, never a guess"),
    ("31.", "KiB", 0, "a trailing dot leaves no fractional digit"),
    (".5", "MiB", 0, "no whole part"),
    ("x", "MiB", 0, "not a number at all"),
]

# --- the two download-size wordings ------------------------------------------
# They disagree in BOTH directions, which is why parsers.py carries two
# functions. A single parser would change what @@SIZE@@ reports.
SIZE_TEXT = [
    ("Overall download size: 1.3 GiB. Already cached: 0 B.", "1.3 GiB"),
    ("Package download size:   371.4 MiB", "371.4 MiB"),
    ("Overall download size: 1.5 MiB. Already cached: 0 B.", "1.5 MiB"),
    ("Package download size:    86.4 MiB", "86.4 MiB"),
    ("Overall download size: 1.3 TiB. Already cached: 0 B.", "1.3 TiB"),
    ("Package download size:371.4MiB", None),
    ("Nothing to do.", None),
    ("Package install size change:", None),
]

SIZE_BYTES = [
    ("Overall download size: 1.3 GiB. Already cached: 0 B.", 1395864371),
    ("Package download size:   371.4 MiB", 389441126),
    ("Package download size:371.4MiB", 389441126),
    ("Overall download size: 1.3 TiB. Already cached: 0 B.", None),
    ("  Overall download size: 1.3 GiB.", None),
    ("Package install size change:", None),
]

# --- the progress wordings ---------------------------------------------------
RETRIEVING = [
    # (line, fraction, bytes)
    ("Retrieving: cpupower-lang-7.1.4-17.noarch (devel-tools) (1/77),  31.0 KiB",
     "1/77", 31744),
    ("Retrieving: kernel-default-6.9.1-1.x86_64 (repo-oss) (77/77),  86.4 MiB",
     "77/77", 90596966),
    ("Retrieving: something-1.0.noarch (12/34)", "12/34", 0),
]

INSTALLING = [
    ("( 1/77) Installing: cpupower-lang-7.1.4-17.noarch [...done]", " 1/77"),
    ("(77/77) Removing: obsolete-package-2.0.x86_64", "77/77"),
    ("( 3/10) Upgrading: libfoo-1.2.3.x86_64", " 3/10"),
]

# --- zypper lr -u ------------------------------------------------------------
# Verbatim from the "the refresh names each source and says how far through the
# list it is" scenario's zypper mock.
LR_TABLE = """#  | Alias   | Name         | Enabled | GPG Check | Refresh
---+---------+--------------+---------+-----------+--------
 1 | oss     | Main OSS     | Yes     | (r ) Yes  | Yes
 2 | games   | Games        | Yes     | (r ) Yes  | Yes
 3 | offrepo | Disabled one | No      | ----      | ----
"""

# --- /run/zypp.pid -----------------------------------------------------------
LOCK_PID = [
    ("447150\n", 447150),
    ("447150 zypper\n", 447150),
    ("", None),
    ("\n", None),
    ("not-a-pid\n", None),
    ("-1\n", None),
]

# --- the reboot reason -------------------------------------------------------
REBOOT = [
    ("kernel-default-6.9.1-1.x86_64",
     "a new kernel was installed"),
    # An NVIDIA kmp is NOT also "kernel driver modules": the module filter is
    # `grep -vi nvidia`, so the driver it already named is excluded. Read back
    # from the Bash — this table's first draft got it the other way round.
    ("nvidia-gfxG06-kmp-default-550.x86_64",
     "your NVIDIA graphics driver was installed"),
    # A NON-NVIDIA kmp beside it IS, which is the case that separates the two
    # nvidia patterns parsers.py carries.
    ("nvidia-gfxG06-550.x86_64\nvbox-kmp-default-7.0",
     "your NVIDIA graphics driver and kernel driver modules were installed"),
    ("broadcom-wl-kmp-default-6.30.x86_64",
     "kernel driver modules was installed"),
    ("Mesa-24.1.0-1.x86_64",
     "your graphics driver was installed"),
    ("kernel-default-6.9.1-1.x86_64\nMesa-24.1.0-1.x86_64\nvbox-kmp-default-7.0",
     "a new kernel, your graphics driver, and kernel driver modules were installed"),
    ("kernel-default-6.9.1-1.x86_64\nnvidia-compute-G06-550.x86_64",
     "a new kernel and your NVIDIA graphics driver were installed"),
    ("libfoo-1.2.3.x86_64\nbar-2.0.noarch", ""),
    ("", ""),
]


def main() -> int:
    for number, unit, want, why in TO_BYTES:
        check(f"to_bytes({number!r}, {unit!r}) — {why}",
              parsers.to_bytes(number, unit), want)

    for line, want in SIZE_TEXT:
        check(f"download_size({line[:38]!r}…)", parsers.download_size(line), want)

    # The caller passes whole captured output, not one line: the first MATCHING
    # line wins, and lines before it must not stop the search.
    check("download_size skips non-matching lines and takes the first hit",
          parsers.download_size(
              "Loading repository data...\n"
              "Reading installed packages...\n"
              "Package download size:   371.4 MiB\n"
              "Package install size change:\n"),
          "371.4 MiB")
    check("download_size takes the LAST figure on a line, as the sed's greedy .* does",
          parsers.download_size("Overall download size: 1.3 GiB. Package download size: 2.0 MiB"),
          "2.0 MiB")

    for line, want in SIZE_BYTES:
        check(f"progress_total_bytes({line[:38]!r}…)", parsers.progress_total_bytes(line), want)

    for line, frac, want_bytes in RETRIEVING:
        check(f"retrieving_fraction({line[12:34]!r}…)", parsers.retrieving_fraction(line), frac)
        check(f"retrieving_bytes({line[12:34]!r}…)", parsers.retrieving_bytes(line), want_bytes)

    for line, frac in INSTALLING:
        check(f"install_fraction({line[:24]!r}…)", parsers.install_fraction(line), frac)

    check("enabled_aliases lists both enabled repositories, in table order",
          parsers.enabled_aliases(LR_TABLE), ["oss", "games"])
    check("enabled_aliases leaves out the disabled one",
          "offrepo" in parsers.enabled_aliases(LR_TABLE), False)
    check("enabled_aliases on an unexpected format is empty, never wrong",
          parsers.enabled_aliases("zypper: command not found\n"), [])
    check("enabled_aliases on no output at all is empty",
          parsers.enabled_aliases(""), [])

    for text, want in LOCK_PID:
        check(f"lock_pid({text!r})", parsers.lock_pid(text), want)

    for log, want in REBOOT:
        check(f"reboot_reason({log.splitlines()[0][:34] if log else ''!r}…)",
              parsers.reboot_reason(log), want)

    print(f"\n  Passed: {PASS}   Failed: {FAIL}")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
