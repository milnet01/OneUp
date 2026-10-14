#!/usr/bin/env python3
"""The system service's own suite: ONEUP-0249 §7.

Starts a private `dbus-daemon`, a fake polkit authority on it, and the service with
mock binaries first on its PATH, then talks to it as clients do. Nothing here needs
root: the mocks only log their argv. It locks INV-1, INV-2, INV-3, INV-5, INV-6,
INV-7, INV-9, INV-14 and INV-15 of `docs/specs/ONEUP-0249-system-service.md`.

Exits 0 on success, 1 on a failed check, and 77 (skipped) when `dbus-daemon` or
`jeepney` is missing, like `tests/gui-smoke.py` without PySide6.

Two helper modes, run as child processes of this file:
  --fake-polkit DIR   the polkit authority; answers per DIR/polkit.answers
  --client DIR        opens a session, starts a slow commit, then waits to be killed
And one for `tests/run-tests.sh`, whose engine scenarios need a service to talk to:
  --serve DIR         bus + fake polkit + service over the mocks in DIR; writes the
                      bus address to DIR/bus.address; stops on SIGTERM
"""

from __future__ import annotations

import contextlib
import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import traceback
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
BUS_NAME = "za.co.antsprojectshub.OneUp1"
OBJECT_PATH = "/za/co/antsprojectshub/OneUp1"
SYSTEM_UPDATE = "org.freedesktop.packagekit.system-update"
SIGNING_KEY = "org.freedesktop.packagekit.system-trust-signing-key"

try:
    from jeepney import (
        DBusAddress,
        HeaderFields,
        MessageType,
        new_error,
        new_method_call,
        new_method_return,
    )
    from jeepney.io.blocking import open_dbus_connection as open_blocking
    from jeepney.io.threading import DBusRouter, open_dbus_connection
except ImportError:
    DBusAddress = None

SERVICE = None if DBusAddress is None else DBusAddress(
    OBJECT_PATH, bus_name=BUS_NAME, interface=BUS_NAME)
BUS = None if DBusAddress is None else DBusAddress(
    "/org/freedesktop/DBus", bus_name="org.freedesktop.DBus",
    interface="org.freedesktop.DBus")

BUS_CONFIG = """<!DOCTYPE busconfig PUBLIC "-//freedesktop//DTD D-BUS Bus Configuration 1.0//EN"
 "http://www.freedesktop.org/standards/dbus/1.0/busconfig.dtd">
<busconfig>
  <type>session</type>
  <listen>unix:path={dir}/bus</listen>
  <auth>EXTERNAL</auth>
  <policy context="default">
    <allow send_destination="*" eavesdrop="true"/>
    <allow eavesdrop="true"/>
    <allow own="*"/>
    <allow user="*"/>
  </policy>
</busconfig>
"""

# The mock zypper. Logs "LC_ALL|argv" per call. `packages --unneeded` lists two
# packages; a transaction prints, sleeps for DIR/dup-sleep seconds, and then writes
# DIR/done; it turns SIGTERM into 105, as zypper does. `clean` prints to both streams;
# DIR/clean-dies makes it die of SIGKILL instead.
ZYPPER = r"""#!/usr/bin/env bash
d="$ONEUP_MOCK_DIR"
printf '%s|%s\n' "$LC_ALL" "$*" >> "$d/calls.log"
case " $* " in
  *" packages --unneeded "*)
    printf 'Loading repository data...\nS | Repository | Name | Version | Arch\n'
    printf '%s\n' '--+------------+------+---------+-------'
    printf 'i | @System    | alpha | 1.0 | x86_64\ni | @System    | beta  | 2.0 | x86_64\n' ;;
  *" dup "*|*" update "*)
    trap 'echo "Trying to exit gracefully..."; exit 105' TERM
    echo "Retrieving: alpha-1.0.x86_64 (Main) (1/1), 10.0 KiB"
    sleep "$(cat "$d/dup-sleep" 2>/dev/null || echo 0)" & wait $!
    echo "done"; touch "$d/done" ;;
  *" clean "*)
    [[ -e "$d/clean-dies" ]] && kill -KILL $$
    echo "out-line"; echo "err-line" >&2 ;;
esac
exit 0
"""


def write_mocks(d: Path) -> None:
    """The zypper mock and two repository files whose aliases the service may name."""
    (d / "zypper").write_text(ZYPPER)
    (d / "zypper").chmod(0o755)
    (d / "repos.d").mkdir(exist_ok=True)
    for alias in ("oss", "packman"):
        (d / "repos.d" / f"{alias}.repo").write_text(
            f"[{alias}]\nname={alias}\nenabled=1\nbaseurl=http://download.opensuse.org/x/\n")


# --- the fake polkit -------------------------------------------------------------

def fake_polkit(d: Path) -> int:
    """Owns org.freedesktop.PolicyKit1 on the private bus and answers from a file.

    DIR/polkit.answers maps an action id to yes, no, challenge, dismissed or error
    (anything unlisted is yes). Each call is logged to DIR/polkit.log as JSON.
    """
    conn = open_blocking(bus=os.environ["ONEUP_SERVICE_BUS"])
    conn.send_and_get_reply(new_method_call(
        BUS, "RequestName", "su", ("org.freedesktop.PolicyKit1", 0x4)))
    (d / "polkit.ready").touch()
    while True:
        msg = conn.receive()
        if msg.header.message_type != MessageType.method_call:
            continue
        if msg.header.fields.get(HeaderFields.member) != "CheckAuthorization":
            conn.send(new_error(msg, "org.freedesktop.DBus.Error.UnknownMethod"))
            continue
        subject, action, _details, flags, _cancel = msg.body
        try:
            answers = json.loads((d / "polkit.answers").read_text())
        except (OSError, ValueError):
            answers = {}
        answer = answers.get(action, "yes")
        with open(d / "polkit.log", "a") as log:
            log.write(json.dumps({"action": action, "flags": flags, "kind": subject[0],
                                  "name": subject[1].get("name", ("", ""))[1]}) + "\n")
        if answer == "error":
            conn.send(new_error(msg, "org.freedesktop.PolicyKit1.Error.Failed", "s",
                                ("fake failure",)))
            continue
        result = {"yes": (True, False, {}), "no": (False, False, {}),
                  "challenge": (False, True, {}),
                  "dismissed": (False, False, {"polkit.dismissed": "true"})}[answer]
        conn.send(new_method_return(msg, "(bba{ss})", (result,)))


# --- the rig: bus, polkit, service -----------------------------------------------

class Rig:
    """One private bus with a fake polkit and a running service, over mocks in `d`."""

    def __init__(self, d: Path, *, idle: str = "600") -> None:
        self.d = d
        self.procs: list[subprocess.Popen] = []
        (d / "bus.conf").write_text(BUS_CONFIG.format(dir=d))
        self.bus = subprocess.Popen(  # noqa: S603 — fixed argv
            [shutil.which("dbus-daemon") or "dbus-daemon", f"--config-file={d}/bus.conf",
             "--nofork", "--print-address"],
            stdout=subprocess.PIPE, text=True)
        self.address = self.bus.stdout.readline().strip()
        (d / "bus.address").write_text(self.address + "\n")
        self.env = {**os.environ, "ONEUP_SERVICE_BUS": self.address,
                    "ONEUP_MOCK_DIR": str(d), "PATH": f"{d}{os.pathsep}{os.environ['PATH']}",
                    "PYTHONPATH": str(REPO), "ONEUP_REPOS_DIR": str(d / "repos.d"),
                    "ONEUP_SERVICE_RUNTIME_DIR": str(d / "run"),
                    "ONEUP_SERVICE_IDLE_SECONDS": idle}
        self.procs.append(subprocess.Popen(  # noqa: S603 — this file, fixed argv
            [sys.executable, __file__, "--fake-polkit", str(d)], env=self.env))
        wait_for(lambda: (d / "polkit.ready").exists(), 10)
        self.service = None
        self.start_service()

    def start_service(self) -> None:
        self.log = open(self.d / "service.log", "a")
        self.service = subprocess.Popen(
            [sys.executable, "-m", "oneup.service"], env=self.env, cwd=self.d,
            stdout=self.log, stderr=subprocess.STDOUT)
        probe = self.client()
        try:
            wait_for(lambda: call(probe, BUS, "NameHasOwner", "s", (BUS_NAME,))
                     == ("ok", (True,)), 10)
        finally:
            close(probe)

    def client(self):
        return DBusRouter(open_dbus_connection(bus=self.address, enable_fds=True))

    def answers(self, **by_action: str) -> None:
        (self.d / "polkit.answers").write_text(json.dumps(by_action))

    def audit(self) -> str:
        self.log.flush()
        return (self.d / "service.log").read_text()

    def calls(self) -> list[str]:
        try:
            return (self.d / "calls.log").read_text().splitlines()
        except OSError:
            return []

    def stop(self) -> None:
        for p in [self.service, *self.procs, self.bus]:
            if p is not None and p.poll() is None:
                p.terminate()
                try:
                    p.wait(5)
                except subprocess.TimeoutExpired:
                    p.kill()
                    p.wait()


def wait_for(test, seconds: float) -> bool:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if test():
            return True
        time.sleep(0.05)
    return test()


def call(router, address, method: str, signature: str | None = None, body: tuple = (),
         timeout: float = 15):
    """("ok", body), or (the error's last word, its text)."""
    reply = router.send_and_get_reply(
        new_method_call(address, method, signature, body), timeout=timeout)
    if reply.header.message_type == MessageType.error:
        name = reply.header.fields.get(HeaderFields.error_name, "")
        return name.rsplit(".", 1)[-1], (reply.body[0] if reply.body else "")
    return "ok", reply.body


def close(router) -> None:
    with contextlib.suppress(Exception):
        router.close()
    with contextlib.suppress(Exception):
        router.conn.close()


def open_session(router, **options: bool):
    return call(router, SERVICE, "OpenSession", "a{sv}",
                ({k: ("b", v) for k, v in options.items()},), timeout=30)


def run(router, op: str, args: dict, merge: bool = False):
    """Run `op`; returns (code, text) on refusal, or ("ok", output, status)."""
    sigs = {bool: "b", int: "u", str: "s", list: "as"}
    result = call(router, SERVICE, "Run", "sa{sv}b",
                  (op, {k: (sigs[type(v)], v) for k, v in args.items()}, merge))
    if result[0] != "ok":
        return result
    out_fd, status_fd = result[1]
    with os.fdopen(out_fd.to_raw_fd(), "rb") as out:
        output = out.read().decode()
    with os.fdopen(status_fd.to_raw_fd(), "rb") as st:
        status = st.read().decode().strip()
    return "ok", output, status


def start(router, op: str, args: dict):
    """Run `op` and return its two descriptors without reading them."""
    sigs = {bool: "b", int: "u", str: "s", list: "as"}
    result = call(router, SERVICE, "Run", "sa{sv}b",
                  (op, {k: (sigs[type(v)], v) for k, v in args.items()}, True))
    if result[0] != "ok":
        raise RuntimeError(f"Run {op} was refused: {result}")
    return (os.fdopen(result[1][0].to_raw_fd(), "rb"), os.fdopen(result[1][1].to_raw_fd(), "rb"))


# --- the checks ------------------------------------------------------------------

PASS = 0
FAIL = 0


def check(name: str, cond: bool, detail: object = "") -> None:
    global PASS, FAIL
    if cond:
        print(f"  ok   - {name}")
        PASS += 1
    else:
        print(f"  FAIL - {name}" + (f"\n         got: {detail!r}" if detail != "" else ""))
        FAIL += 1


def scenario(title: str):
    print(f"\n--- {title}")


def test_polkit(rig: Rig) -> None:
    scenario("INV-2: a session opens only on polkit's yes, and each refusal says why")
    c = rig.client()
    check("Run with no session is NoSession", run(c, "cache-clean", {})[0] == "NoSession")
    close(c)
    for answer, expected in (("no", "denied"), ("challenge", "challenge"),
                             ("dismissed", "dismissed"), ("error", "denied")):
        rig.answers(**{SYSTEM_UPDATE: answer})
        c = rig.client()
        got = open_session(c)
        check(f"polkit '{answer}' refuses with NotAuthorized/{expected}",
              got == ("NotAuthorized", expected), got)
        close(c)
    rig.answers()
    (rig.d / "polkit.log").unlink(missing_ok=True)
    c = rig.client()
    check("polkit 'yes' opens the session", open_session(c) == ("ok", ()))
    asked = [json.loads(line) for line in (rig.d / "polkit.log").read_text().splitlines()]
    check("the subject is the caller's own unique bus name, as system-bus-name",
          asked and asked[0]["kind"] == "system-bus-name"
          and asked[0]["name"] == c.unique_name, asked)
    check("the action is Discover's system-update", asked and asked[0]["action"] == SYSTEM_UPDATE)
    check("an interactive session lets polkit ask (flags 1)", asked and asked[0]["flags"] == 1)
    close(c)
    (rig.d / "polkit.log").unlink(missing_ok=True)
    c = rig.client()
    open_session(c, interactive=False)
    asked = [json.loads(line) for line in (rig.d / "polkit.log").read_text().splitlines()]
    check("a non-interactive session never lets polkit ask (flags 0, INV-16)",
          asked and asked[0]["flags"] == 0, asked)
    close(c)
    rig.answers(**{SYSTEM_UPDATE: "no"})
    c = rig.client()
    check("CanUpdate answers no when polkit says no",
          call(c, SERVICE, "CanUpdate") == ("ok", ("no",)))
    rig.answers()
    check("CanUpdate answers yes when polkit says yes",
          call(c, SERVICE, "CanUpdate") == ("ok", ("yes",)))
    props = DBusAddress(OBJECT_PATH, bus_name=BUS_NAME,
                        interface="org.freedesktop.DBus.Properties")
    check("the Version property is 1",
          call(c, props, "Get", "ss", (BUS_NAME, "Version")) == ("ok", (("u", 1),)))
    close(c)


def test_import_keys(rig: Rig) -> None:
    scenario("INV-3: a session's authorisation cannot be widened after it opens")
    rig.answers(**{SIGNING_KEY: "no"})
    c = rig.client()
    got = open_session(c, import_keys=True)
    check("import_keys needs the signing-key action too", got[0] == "NotAuthorized", got)
    close(c)
    c = rig.client()
    check("a plain session opens", open_session(c) == ("ok", ()))
    before = len(rig.calls())
    got = run(c, "repo-refresh", {"alias": "oss", "import_keys": True, "budget": 5})
    check("a refresh with import_keys is refused in a session opened without it",
          got[0] == "NotAuthorized", got)
    got = run(c, "repo-refresh-all", {"import_keys": True})
    check("so is the bulk refresh", got[0] == "NotAuthorized", got)
    check("and neither ran anything", len(rig.calls()) == before, rig.calls()[before:])
    close(c)
    rig.answers()


def test_validation(rig: Rig) -> None:
    scenario("INV-1: nothing runs that the table did not build from valid arguments")
    c = rig.client()
    open_session(c)
    before = len(rig.calls())
    for label, op, args in (
            ("a bogus operation", "rm-rf", {}),
            ("an extra argument", "cache-clean", {"extra": True}),
            ("a missing argument", "repo-refresh", {"alias": "oss", "import_keys": False}),
            ("an alias with a space", "repo-disable", {"alias": "oss packman"}),
            ("a path-shaped alias", "repo-disable", {"alias": "../../etc/passwd"}),
            ("an alias no repository file defines", "repo-disable", {"alias": "nosuch"}),
            ("a budget of zero", "repo-refresh",
             {"alias": "oss", "import_keys": False, "budget": 0}),
            ("an unknown snapper algorithm", "snapshot-thin", {"algorithm": "all"}),
            ("an option-shaped package name", "orphans-remove", {"names": ["--force"]})):
        got = run(c, op, args)
        check(f"{label} is Invalid", got[0] == "Invalid", got)
    sigs_wrong = call(c, SERVICE, "Run", "sa{sv}b",
                      ("repo-disable", {"alias": ("as", ["oss"])}, False))
    check("an argument of the wrong D-Bus type is Invalid", sigs_wrong[0] == "Invalid", sigs_wrong)
    check("none of them started a child", len(rig.calls()) == before, rig.calls()[before:])
    close(c)


def test_relay(rig: Rig) -> None:
    scenario("§4.3: output and status come back as the engine reads them")
    c = rig.client()
    open_session(c)
    got = run(c, "cache-clean", {}, merge=False)
    check("unmerged: stdout alone, then status 0", got == ("ok", "out-line\n", "0"), got)
    got = run(c, "cache-clean", {}, merge=True)
    check("merged: stderr joins the one stream", got[0] == "ok" and "err-line" in got[1], got)
    (rig.d / "clean-dies").touch()
    got = run(c, "cache-clean", {})
    (rig.d / "clean-dies").unlink()
    check("a child killed by SIGKILL reports 137 (128+N)",
          got[:1] == ("ok",) and got[2] == "137", got)
    got = run(c, "system-commit", {"cdn": False})
    check("the transaction runs under LC_ALL=C, as the table builds it",
          got[0] == "ok" and rig.calls()[-1].startswith("C|") and " dup " in f" {rig.calls()[-1]} ",
          rig.calls()[-1:])
    close(c)
    check("no job file is left behind", not list((rig.d / "run").glob("job-*")),
          list((rig.d / "run").glob("job-*")))


def test_orphans(rig: Rig) -> None:
    scenario("INV-7: orphans-remove takes only what zypper just called unneeded")
    c = rig.client()
    open_session(c)
    start_at = len(rig.calls())
    got = run(c, "orphans-remove", {"names": ["alpha", "gamma"]})
    check("a name zypper did not list is Invalid", got[0] == "Invalid", got)
    made = rig.calls()[start_at:]
    check("the service asked zypper for the list itself",
          any("packages --unneeded" in line for line in made), made)
    check("and nothing was removed", not any(" remove " in f" {line} " for line in made), made)
    got = run(c, "orphans-remove", {"names": ["alpha"]})
    check("a listed name is removed", got[0] == "ok" and got[2] == "0", got)
    check("with the table's argv",
          rig.calls()[-1].endswith("--non-interactive remove --clean-deps alpha"), rig.calls()[-1:])
    close(c)


def test_repo_restore(rig: Rig) -> None:
    scenario("INV-6: repo-enable undoes only this session's disable; leaving undoes the rest")
    c = rig.client()
    open_session(c)
    got = run(c, "repo-enable", {"alias": "packman"})
    check("enabling an alias this session never disabled is Invalid", got[0] == "Invalid", got)
    got = run(c, "repo-disable", {"alias": "oss"})
    check("disabling a real alias runs", got[0] == "ok" and got[2] == "0", got)
    close(c)     # the caller drops off the bus without CloseSession
    check("dropping the connection re-enables it",
          wait_for(lambda: any(line.endswith("modifyrepo --enable oss")
                               for line in rig.calls()), 10),
          rig.calls()[-3:])
    check("and the audit line names it",
          wait_for(lambda: "re-enabled=oss" in rig.audit(), 5), rig.audit()[-300:])
    c = rig.client()
    open_session(c)
    run(c, "repo-disable", {"alias": "packman"})
    got = run(c, "repo-enable", {"alias": "packman"})
    check("enabling its own disable runs", got[0] == "ok" and got[2] == "0", got)
    count = len(rig.calls())
    check("CloseSession is accepted", call(c, SERVICE, "CloseSession") == ("ok", ()))
    time.sleep(0.5)
    check("an alias already re-enabled is not enabled twice", len(rig.calls()) == count,
          rig.calls()[count:])
    close(c)


def test_caps(rig: Rig) -> None:
    scenario("INV-9: one session per caller, eight in all, one job in the service")
    first = rig.client()
    check("the first session opens", open_session(first) == ("ok", ()))
    got = open_session(first)
    check("a second from the same caller is Busy", got[0] == "Busy", got)
    others = [rig.client() for _ in range(8)]
    results = [open_session(c)[0] for c in others]
    check("seven more open, and the ninth is Busy", results == ["ok"] * 7 + ["Busy"], results)
    (rig.d / "dup-sleep").write_text("2")
    (rig.d / "done").unlink(missing_ok=True)
    out, status = start(first, "system-commit", {"cdn": False})
    got = run(first, "cache-clean", {})
    check("a second Run from the same session is Busy", got[0] == "Busy", got)
    got = run(others[0], "cache-clean", {})
    check("a Run from another session is Busy", got[0] == "Busy", got)
    got = call(others[0], SERVICE, "Stop")
    check("Stop from another session is NoSession", got[0] == "NoSession", got)
    got = call(first, SERVICE, "Stop")
    check("Stop on a commit is NotStoppable (INV-5)", got[0] == "NotStoppable", got)
    out.read()
    check("the commit finishes with status 0", status.read().decode().strip() == "0")
    out.close()
    status.close()
    for c in [first, *others]:
        close(c)
    (rig.d / "dup-sleep").unlink()


def test_stop_download(rig: Rig) -> None:
    scenario("§4.6: Stop reaches a download, as SIGTERM, which zypper makes 105")
    c = rig.client()
    open_session(c)
    (rig.d / "dup-sleep").write_text("30")
    out, status = start(c, "system-download", {"cdn": False})
    time.sleep(0.5)
    began = time.monotonic()
    check("Stop is accepted", call(c, SERVICE, "Stop") == ("ok", ()))
    text = out.read().decode()
    code = status.read().decode().strip()
    check("the download ends 105, promptly", code == "105" and time.monotonic() - began < 10,
          (code, round(time.monotonic() - began, 1)))
    check("with zypper's own words relayed", "Trying to exit gracefully" in text, text)
    out.close()
    status.close()
    close(c)
    (rig.d / "dup-sleep").unlink()


def test_client_killed(rig: Rig) -> None:
    scenario("INV-5: a commit outlives its caller")
    (rig.d / "dup-sleep").write_text("2")
    (rig.d / "done").unlink(missing_ok=True)
    ended = rig.audit().count("op=system-commit status=0")
    client = subprocess.Popen(  # noqa: S603 — this file, fixed argv
        [sys.executable, __file__, "--client", str(rig.d)], env=rig.env,
        stdout=subprocess.PIPE, text=True)
    line = client.stdout.readline().strip()
    check("the client started a commit", line == "started", line)
    client.kill()
    client.wait()
    check("the commit still finishes after its caller is killed",
          wait_for(lambda: (rig.d / "done").exists(), 15))
    check("and the service records its end",
          wait_for(lambda: rig.audit().count("op=system-commit status=0") > ended, 5),
          rig.audit()[-300:])
    (rig.d / "dup-sleep").unlink()


def test_service_killed(rig: Rig) -> None:
    scenario("INV-5: a commit outlives the service")
    (rig.d / "dup-sleep").write_text("2")
    (rig.d / "done").unlink(missing_ok=True)
    c = rig.client()
    open_session(c)
    out, status = start(c, "system-commit", {"cdn": False})
    time.sleep(0.3)
    rig.service.kill()
    rig.service.wait()
    out.read()
    check("the client sees the status close with no line", status.read() == b"")
    check("the commit still finishes after the service is killed",
          wait_for(lambda: (rig.d / "done").exists(), 15))
    out.close()
    status.close()
    close(c)
    (rig.d / "dup-sleep").unlink()
    rig.start_service()


def test_audit(rig: Rig) -> None:
    scenario("INV-14: every session and job leaves one audit line")
    text = rig.audit()
    for needle in ("session opened uid=", "session refused uid=", "reason=dismissed",
                   "job started uid=", "op=repo-disable args=alias=oss", "job ended uid=",
                   "session ended uid="):
        check(f"the journal has '{needle}'", needle in text)


def test_sigterm(rig: Rig) -> None:
    scenario("§4.8: on SIGTERM the service refuses new sessions and waits for its job")
    c = rig.client()
    open_session(c)
    (rig.d / "dup-sleep").write_text("2")
    (rig.d / "done").unlink(missing_ok=True)
    out, status = start(c, "system-commit", {"cdn": False})
    rig.service.send_signal(signal.SIGTERM)
    time.sleep(0.5)
    late = rig.client()
    got = open_session(late)
    check("a new session is Busy", got[0] == "Busy", got)
    check("the service is still running while the job runs", rig.service.poll() is None)
    out.read()
    check("the job finishes", status.read().decode().strip() == "0")
    check("and then the service exits", wait_for(lambda: rig.service.poll() is not None, 10))
    for f in (out, status):
        f.close()
    close(c)
    close(late)
    (rig.d / "dup-sleep").unlink()
    rig.start_service()


def test_idle(base: Path) -> None:
    scenario("INV-15: with no session and no job, the service exits")
    d = base / "idle"
    d.mkdir()
    write_mocks(d)
    rig = Rig(d, idle="2")
    try:
        c = rig.client()
        open_session(c)
        time.sleep(3)
        check("a session keeps it running past the idle period", rig.service.poll() is None)
        call(c, SERVICE, "CloseSession")
        close(c)
        check("it exits once idle", wait_for(lambda: rig.service.poll() is not None, 8))
        check("and says so", "idle; exiting" in rig.audit())
    finally:
        rig.stop()


def client_mode(d: Path) -> int:
    """The INV-5 caller: open a session, start a commit, then wait to be killed."""
    router = DBusRouter(open_dbus_connection(bus=os.environ["ONEUP_SERVICE_BUS"],
                                             enable_fds=True))
    open_session(router)
    _held = start(router, "system-commit", {"cdn": False})   # kept open until killed
    print("started", flush=True)
    time.sleep(600)
    return 0


def serve_mode(d: Path) -> int:
    """For tests/run-tests.sh: serve until SIGTERM, then tear everything down."""
    rig = Rig(d)
    stopping = []
    signal.signal(signal.SIGTERM, lambda *_: stopping.append(1))
    (d / "serve.ready").touch()
    try:
        while not stopping:
            time.sleep(0.1)
    finally:
        rig.stop()
    return 0


def main() -> int:
    base = Path(tempfile.mkdtemp(prefix="oneup-servicetest-"))
    try:
        d = base / "main"
        d.mkdir()
        write_mocks(d)
        rig = Rig(d)
        try:
            for test in (test_polkit, test_import_keys, test_validation, test_relay,
                         test_orphans, test_repo_restore, test_caps, test_stop_download,
                         test_client_killed, test_service_killed, test_sigterm, test_audit):
                test(rig)
        finally:
            rig.stop()
        test_idle(base)
    finally:
        shutil.rmtree(base, ignore_errors=True)
    print()
    print("======================================")
    print(f"  Passed: {PASS}   Failed: {FAIL}")
    print("======================================")
    return 1 if FAIL else 0


if __name__ == "__main__":
    if DBusAddress is None or shutil.which("dbus-daemon") is None:
        print("SKIP: service-test needs dbus-daemon and the jeepney module")
        sys.exit(77)
    if len(sys.argv) == 3 and sys.argv[1] in ("--fake-polkit", "--client", "--serve"):
        mode = {"--fake-polkit": fake_polkit, "--client": client_mode,
                "--serve": serve_mode}[sys.argv[1]]
        sys.exit(mode(Path(sys.argv[2])))
    code = 1
    try:
        code = main()
    except Exception:  # noqa: BLE001 — any crash; reported, then exits 1
        traceback.print_exc()
        print(f"  ABORTED after {PASS + FAIL} checks — Passed: {PASS}   Failed: {FAIL}")
    sys.exit(code)
