#!/usr/bin/env python3
"""Table-driven tests for the pure half of the Python engine — oneup/engine/parsers.py
and the emitter predicates in oneup/engine/markers.py — and for the window's
Qt-free package-details parsers, oneup/gui/package_details.py (ONEUP-0260).

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
import contextlib
import io
import sys
import tempfile
from pathlib import Path

# The repo root, so `oneup.engine` imports without an install step.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from oneup.engine import markers, parsers
from oneup.gui import package_details as pd

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
# Integer arithmetic over every fractional digit, truncating only the final byte:
# `1.3 GiB` is 1395864371 and not 1395864371.2 rounded up. The Bash engine keeps one
# digit; the Python engine no longer matches it there (ONEUP-0335).
TO_BYTES = [
    # (number, unit, bytes, why this row is here)
    ("31.0", "KiB", 31744, "the worked example in progress_filter's comment"),
    ("1.3", "GiB", 1395864371, "the Leap download-size line; truncates, never rounds"),
    ("371.4", "MiB", 389441126, "the Tumbleweed download-size line"),
    ("86.4", "MiB", 90596966, "the ONEUP-0048 slow-mirror figure"),
    ("0", "B", 0, "a definite zero is a real answer"),
    ("31", "MiB", 32505856, "no decimal point at all"),
    ("08.0", "MiB", 8388608, "zero-padded: decimal, never an invalid octal literal"),
    ("1.25", "GiB", 1342177280, "a second fractional digit counts (ONEUP-0335)"),
    ("1.75", "GiB", 1879048192, "the 2026-10-23 run's total, which read as 1.7 GiB (ONEUP-0335)"),
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
    # With part of the transaction cached, the header has no number and the figure is
    # the "already in cache" row's first column (zypper src/Summary.cc, ONEUP-0223).
    ("Package download size:", None),
    ("                |     105.7 MiB  overall package size", None),
    ("      99.2 MiB  |  -    6.4 MiB  already in cache", "99.2 MiB"),
    ("Preloading: git-2.55.0-3.1.x86_64.rpm [already in cache]", None),
]

SIZE_BYTES = [
    ("Overall download size: 1.3 GiB. Already cached: 0 B.", 1395864371),
    ("Package download size:   371.4 MiB", 389441126),
    ("Package download size:371.4MiB", 389441126),
    ("Overall download size: 1.3 TiB. Already cached: 0 B.", None),
    ("  Overall download size: 1.3 GiB.", None),
    ("Package install size change:", None),
    ("Package download size:", None),
    ("                |     105.7 MiB  overall package size", None),
    ("      99.2 MiB  |  -    6.4 MiB  already in cache", 104018739),
    ("Preloading: git-2.55.0-3.1.x86_64.rpm [already in cache]", None),
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
    # A bare \r is NOT a line break to the Bash, which splits the transaction log
    # on \n alone. Python's splitlines() also breaks on \r, \v, \f and the Unicode
    # separators — and here that fabricates a reason: split in two, the vbox kmp no
    # longer has the nvidia name beside it to exclude it, so "kernel driver modules"
    # appears in a reason the Bash engine never gives (ONEUP-0152).
    ("nvidia-gfxG06-550.x86_64\rvbox-kmp-default-7.0",
     "your NVIDIA graphics driver was installed"),
    ("nvidia-gfxG06-550.x86_64\x0bvbox-kmp-default-7.0",
     "your NVIDIA graphics driver was installed"),
    ("Mesa-24.1.0-1.x86_64",
     "your graphics driver was installed"),
    ("kernel-default-6.9.1-1.x86_64\nMesa-24.1.0-1.x86_64\nvbox-kmp-default-7.0",
     "a new kernel, your graphics driver, and kernel driver modules were installed"),
    ("kernel-default-6.9.1-1.x86_64\nnvidia-compute-G06-550.x86_64",
     "a new kernel and your NVIDIA graphics driver were installed"),
    ("libfoo-1.2.3.x86_64\nbar-2.0.noarch", ""),
    ("", ""),
]


# --- one package at a time (ONEUP-0259) ---------------------------------------
# Real lines from a OneUp run log of 2026-10-12, except where a row says it was
# built to break the rule it tests.
NVRA = [
    ("cpupower-lang-7.1.4-17.noarch", ("cpupower-lang", "7.1.4-17", "noarch")),
    ("ImageMagick-config-7-SUSE-7.1.2.32-2.1.noarch",
     ("ImageMagick-config-7-SUSE", "7.1.2.32-2.1", "noarch")),
    ("libgstvideo-1_0-0-32bit-1.28.8-1.1.x86_64",
     ("libgstvideo-1_0-0-32bit", "1.28.8-1.1", "x86_64")),
    ("foo-1:2.0-3.1.x86_64", ("foo", "1:2.0-3.1", "x86_64")),   # an epoch stays in the version
    ("noarch-at-all", None),
    ("onlyname.x86_64", None),
    ("", None),
]

# (lines fed in order, the states that come out) — INV-6.
PACKAGE_LINES = [
    (["(  1/320) Installing: ImageMagick-config-7-SUSE-7.1.2.32-2.1.noarch [...done]"],
     [("installed", "ImageMagick-config-7-SUSE", "7.1.2.32-2.1", 0)]),
    (["(  3/320) Installing: akonadi-contacts-26.08.2-1.1.x86_64 [..done]"],
     [("installed", "akonadi-contacts", "26.08.2-1.1", 0)]),
    (["(1/6) Removing: mariadb-12.3.2-3.1.x86_64 [...done]"],
     [("removed", "mariadb", "12.3.2-3.1", 0)]),
    # Built to break it: an action that failed is never done.
    (["(1/6) Removing: mariadb-12.3.2-3.1.x86_64 [...error]"], []),
    # A package's script splits the line; a later `done]` completes it.
    (["(117/320) Installing: xorg-x11-server-21.1.24-2.1.x86_64 [...",
      "Updating /etc/sysconfig/displaymanager ...",
      "done]"],
     [("installed", "xorg-x11-server", "21.1.24-2.1", 0)]),
    (["(153/320) Installing: gstreamer-1.28.8-1.1.x86_64 [..",
      "/usr/libexec/gstreamer-1.0/gst-ptp-helper: setting to root:root 0755 "
      '"cap_net_bind_service=ep". (missing capabilities)',
      ".done]"],
     [("installed", "gstreamer", "1.28.8-1.1", 0)]),
    # Built to break it: a cut action followed by the NEXT action never completes.
    (["(3/6) Removing: x-1-2.noarch [..",
      "(4/6) Removing: y-1-2.noarch [..done]"],
     [("removed", "y", "1-2", 0)]),
    (["Preloading: libglfw3-3.4-67.34.x86_64.rpm [done]"],
     [("downloaded", "libglfw3", "3.4-67.34", 0)]),
    (["Preloading: libglfw3-3.4-67.34.x86_64.rpm [already in cache]"],
     [("downloaded", "libglfw3", "3.4-67.34", 0)]),
    (["Preloading: libglfw3-3.4-67.34.x86_64.rpm [error]"], []),
    # A fetch ends at the pass's end (ONEUP-0335, ONEUP-0239 §4.3.1).
    (["Retrieving: akonadi-calendar-26.08.2-1.1.x86_64 (Main Repository (OSS)) "
      "(2/320),  36.3 KiB    "],
     [("downloading", "akonadi-calendar", "26.08.2-1.1", 37171),
      ("downloaded", "akonadi-calendar", "26.08.2-1.1", 0)]),
    # ONEUP-0239 INV-21: a fetch also ends at the next package's `Retrieving:` line, and
    # at the pass's first action line, so a fetched package leaves "now".
    (["Retrieving: cpupower-lang-7.1.4-17.noarch (devel-tools) (1/2),  31.0 KiB",
      "Retrieving: libcapstone5-5.0.6-18.x86_64 (devel-tools) (2/2), 1.0 MiB",
      "(1/2) Installing: cpupower-lang-7.1.4-17.noarch [..done]"],
     [("downloading", "cpupower-lang", "7.1.4-17", 31744),
      ("downloaded", "cpupower-lang", "7.1.4-17", 0),
      ("downloading", "libcapstone5", "5.0.6-18", 1048576),
      ("downloaded", "libcapstone5", "5.0.6-18", 0),
      ("installed", "cpupower-lang", "7.1.4-17", 0)]),
]

# `zypper --xmlout list-updates`, shaped by /usr/share/zypper/xml/xmlout.rnc's
# `other-update`. A patch update is not a package and is left out.
UPDATE_XML = """<?xml version='1.0'?>
<stream>
<message type="info">Loading repository data...</message>
<message type="warning">Skipping repository &apos;Packman&apos; because of an error.</message>
<update-status version="0.6">
<update-list>
<update name="vlc" edition="3.0.24-1699.5.pm.3" arch="x86_64" kind="package"
 edition-old="3.0.24-1699.5.pm.1">
<summary>Graphical media player</summary><description>x</description><license/>
<source url="https://ftp.gwdg.de/pub/linux/misc/packman" alias="packman"/>
</update>
<update name="openSUSE-2026-1" edition="1" arch="noarch" kind="patch" status="needed"
 pkgmanager="false" restart="false">
<summary>p</summary><description>p</description><license/><source url="x" alias="oss"/>
</update>
<update name="bash" edition="5.3.9-1.1" arch="x86_64" kind="package">
<summary>s</summary><description>d</description><license/>
</update>
</update-list>
</update-status>
</stream>
"""


# --- the window's package details (oneup/gui/package_details.py) -----------
# ONEUP-0260 §4.1 and §4.3. Qt-free on purpose, so these run here. The rpm
# texts are built with the two separators the window's --qf formats use.
_E, _F = "\x1e", "\x1f"

INFO_TEXT = """Loading repository data...
Reading installed packages...


Information for package bash:
-----------------------------
Repository     : Main Repository (OSS)
Name           : bash
Version        : 5.3.20-9.1
Upstream URL   : https://www.gnu.org/software/bash/bash.html
Summary        : The GNU Bourne-Again Shell
Description    :~
    Bash is an sh-compatible command interpreter that executes commands
    read from standard input or from a file.


Information for package vlc:
----------------------------
Name           : vlc
Summary        :~
Description    :~

package 'nosuchpkg-xyz' not found.
""".replace("~", " ")   # zypper ends an empty value with a space


def details_checks() -> None:
    about = pd.parse_info(INFO_TEXT)
    check("parse_info: bash's summary", about.get("bash") and about["bash"].summary,
          "The GNU Bourne-Again Shell")
    check("parse_info: the description's continuation lines, joined",
          about.get("bash") and about["bash"].description,
          "Bash is an sh-compatible command interpreter that executes commands\n"
          "read from standard input or from a file.")
    check("parse_info: the upstream address", about.get("bash") and about["bash"].url,
          "https://www.gnu.org/software/bash/bash.html")
    check("parse_info: a block with no summary and no description has no About",
          "vlc" in about, False)
    check("parse_info: a name zypper did not find has no About", "nosuchpkg-xyz" in about, False)

    # INV-2. The leading "-" is the case only the name pattern rejects.
    check("build_info_argv keeps only valid names, after fixed options",
          pd.build_info_argv(["bash", "-rf", "a*b"]),
          ["zypper", "--no-refresh", "--non-interactive", "info", "bash"])
    check("build_info_argv with nothing valid is None", pd.build_info_argv(["-x"]), None)
    check("strip_epoch drops a leading N:", pd.strip_epoch("1:2.3-4"), "2.3-4")
    check("strip_epoch leaves an edition with none", pd.strip_epoch("5.3.20-9.1"), "5.3.20-9.1")

    with tempfile.TemporaryDirectory() as root:
        d = Path(root) / "repo-oss" / "x86_64"
        d.mkdir(parents=True)
        (d / "foo-2.3-4.x86_64.rpm").write_bytes(b"")
        check("find_download: an epoched edition finds the file named without it",
              pd.find_download("foo", "1:2.3-4", root), str(d / "foo-2.3-4.x86_64.rpm"))
        check("find_download: an edition holding a glob character finds nothing",
              pd.find_download("foo", "2.*", root), None)
        check("find_download: no file is None", pd.find_download("bar", "1-1", root), None)

    calls = []

    def run(argv, **_kw):
        calls.append(argv)
        raise AssertionError("rpm must not be called")

    got = pd.changelog("foo", "2.*", "installed", None, run=run)
    check("changelog: an edition with '*' gives no entries and calls nothing",
          (got.entries, calls), ([], []))

    base = (_F.join(("bash", "5.3.20-9.1", "100", "A <a@x>", "old text")) + _E
            + "package nosuch is not installed\n"
            + _F.join(("kernel-default", "7.2.8-1.1", "50", "K <k@x>", "k old")) + _E
            + _F.join(("kernel-default", "7.2.9-1.1", "60", "K <k@x>", "k new")) + _E
            + _F.join(("libavcodec62", "1.0-1", "(none)", "(none)", "(none)")) + _E)
    olds = {"bash": "5.3.20-9.1", "kernel-default": "7.2.8-1.1", "libavcodec62": "1.0-1"}
    bl = pd.parse_baseline(base, olds)
    check("parse_baseline: time, author and text", bl.get("bash"),
          pd.Entry(100, "A <a@x>", "old text"))
    check("parse_baseline: a multiversion name takes the line matching its old version",
          bl.get("kernel-default"), pd.Entry(50, "K <k@x>", "k old"))
    check("parse_baseline: (none) gives no entry", "libavcodec62" in bl, False)

    # INV-3. Both new entries share the baseline's date AND author; only the text
    # tells the baseline entry from the new one below it.
    new = pd.parse_entries(_F.join(("200", "A <a@x>", "newest")) + _E
                           + _F.join(("100", "A <a@x>", "same day, same author")) + _E
                           + _F.join(("100", "A <a@x>", "old text")) + _E
                           + _F.join(("90", "B <b@x>", "older")) + _E)
    entries, known = pd.new_entries(new, pd.Entry(100, "A <a@x>", "old text"))
    check("new_entries: matched on time, author and text",
          ([e.text for e in entries], known), (["newest", "same day, same author"], True))
    entries, known = pd.new_entries(new, None)
    check("new_entries: no baseline shows the newest, flagged unknown",
          (len(entries), known), (4, False))
    entries, known = pd.new_entries(new, pd.Entry(5, "Z", "never"))
    check("new_entries: a baseline never met is the same fallback", known, False)
    many = pd.parse_entries(_E.join(_F.join((str(n), "A", f"t{n}")) for n in range(30, 0, -1)) + _E)
    check("new_entries: the fallback stops at 20", len(pd.new_entries(many, None)[0]), 20)


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
    check("download_size reads the cached-split table, header and all (ONEUP-0223)",
          parsers.download_size(
              "12 packages to upgrade.\n"
              "\n"
              "Package download size:\n"
              "                |     105.7 MiB  overall package size\n"
              "      99.2 MiB  |  -    6.4 MiB  already in cache\n"),
          "99.2 MiB")
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
        check(f"reboot_phrase(reboot_components({log.splitlines()[0][:34] if log else ''!r}…))",
              parsers.reboot_phrase(parsers.reboot_components(log)), want)
    # The marker carries the codes, not the phrase (ONEUP-0072 §4.1).
    check("reboot_components names a kernel and the NVIDIA driver as codes",
          parsers.reboot_components("kernel-default-6.9.1-1.x86_64\n"
                                    "nvidia-compute-G06-550.x86_64"),
          ["kernel-new", "graphics-driver-nvidia"])
    check("reboot_components: all three, in the reason's order",
          parsers.reboot_components("kernel-default-6.9.1-1.x86_64\nMesa-24.1.0-1.x86_64\n"
                                    "vbox-kmp-default-7.0"),
          ["kernel-new", "graphics-driver-generic", "kernel-modules"])
    check("reboot_components: nothing qualifying is empty",
          parsers.reboot_components("libfoo-1.2.3.x86_64"), [])

    for nvra, want in NVRA:
        check(f"split_nvra({nvra!r})", parsers.split_nvra(nvra), want)

    for lines, want in PACKAGE_LINES:
        reader = parsers.PackageLines()
        got = [r for line in lines for r in reader.feed(line)] + reader.finish()
        check(f"PackageLines({lines[0][:44]!r}… x{len(lines)})", got, want)

    listed = parsers.update_list(UPDATE_XML)
    check("update_list: packages only, in zypper's order",
          [u.name for u in listed[0]] if listed else None, ["vlc", "bash"])
    check("update_list: edition, old edition, arch and alias",
          listed[0][0] if listed else None,
          parsers.Update("vlc", "3.0.24-1699.5.pm.3", "3.0.24-1699.5.pm.1", "x86_64", "packman"))
    check("update_list: no edition-old and no source read as empty",
          (listed[0][1].old, listed[0][1].alias) if listed else None, ("", ""))
    check("update_list: a message comes back unescaped, so its quotes can be matched",
          any("Skipping repository 'Packman'" in m for m in listed[1]) if listed else None, True)
    check("repo_names maps each alias to its display name",
          parsers.repo_names('<stream><repo-list>'
                             '<repo alias="download.opensuse.org-non-oss" '
                             'name="Main Repository (NON-OSS)"/>'
                             '<repo alias="devel-tools" name="devel-tools"/></repo-list></stream>'),
          {"download.opensuse.org-non-oss": "Main Repository (NON-OSS)",
           "devel-tools": "devel-tools"})
    check("repo_names on output that is not XML is empty",
          parsers.repo_names("zypper: command not found"), {})
    check("update_list: output that is not well-formed is None, never a partial list",
          parsers.update_list(UPDATE_XML[:300]), None)

    # --- the emitter (oneup/engine/markers.py) ------------------------------
    # `emit_progress` returns False when there was no counter to parse, and that
    # distinction is the whole input to the ONEUP-0046 stale-parser canary: a
    # transaction that installed packages while nothing was recognised. A pattern
    # that accepts more than the Bash does blinds the canary.
    for frac, want in (("1/77", True),
                       ("  12 / 141 ", True),
                       # `$` matches before a trailing newline; the Bash `case` does
                       # not. `\Z` is the anchor that means end-of-string.
                       ("1/77\n", False),
                       ("( 1/77", False),
                       ("x/77", False),
                       ("", False)):
        with contextlib.redirect_stdout(io.StringIO()):
            got = markers.emit_progress("system", frac, "download")
        check(f"emit_progress(frac={frac!r})", got, want)

    # The two byte fields travel together, and "0" is a REAL reading ("nothing has
    # come down yet"), not an absent one. Only the empty string means absent. The
    # emitter tests the argument for emptiness rather than truth, so a caller that
    # ever passes a falsy non-string cannot silently drop both fields.
    for got_arg, want_fields in (("0", 7), ("41943040", 7), ("", 5)):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            markers.emit_progress("system", "1/77", "download", got_arg, "397410304")
        line = buf.getvalue().strip()
        check(f"emit_progress(got={got_arg!r}) field count",
              len(line.split("|")), want_fields)

    # One marker call must produce exactly one line. The payload is interpolated
    # straight into the output, so a newline reaching it fabricates a whole second
    # marker — and the window parses whatever comes out.
    for payload in ("plain", "two\nlines", "carriage\rreturn", "vertical\x0btab"):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            markers.marker("HINT", payload)
        body = buf.getvalue().rstrip("\n")
        check(f"marker(HINT, {payload!r}) emits one line",
              not any(c in body for c in "\n\r\x0b\x0c"), True)

    details_checks()

    print(f"\n  Passed: {PASS}   Failed: {FAIL}")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
