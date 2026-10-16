"""The D-Bus object: sessions, the one running job, and what each method may do.

§4.3 to §4.9. One thread owns every piece of state: the main loop below. The bus
receiver thread only queues messages; polkit checks run on worker threads, because a
check that asks the user can take minutes; the job's waiter runs on its own. Each of
those posts its result back to the main loop's queue rather than touching state.
"""

from __future__ import annotations

import contextlib
import os
import pwd
import queue
import shutil
import signal
import sys
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

from jeepney import (
    DBusAddress,
    HeaderFields,
    MatchRule,
    Message,
    MessageType,
    new_error,
    new_method_call,
    new_method_return,
)
from jeepney.io.threading import DBusRouter, open_dbus_connection

from oneup.engine import repos, rootops, steps

from . import jobs, polkit

BUS_NAME = "za.co.antsprojectshub.OneUp1"
OBJECT_PATH = "/za/co/antsprojectshub/OneUp1"
INTERFACE = BUS_NAME
VERSION = 1
_ERR = BUS_NAME + ".Error."

MAX_SESSIONS = 8                  # §4.5
READ_WAIT_SECONDS = 1.0           # the longest a `Read` with nothing to say waits (§4.3)

_DBUS = DBusAddress("/org/freedesktop/DBus", bus_name="org.freedesktop.DBus",
                    interface="org.freedesktop.DBus")

_INTROSPECTION = f"""<node>
 <interface name="{INTERFACE}">
  <method name="OpenSession"><arg direction="in" type="a{{sv}}"/></method>
  <method name="Run"><arg direction="in" type="s"/><arg direction="in" type="a{{sv}}"/>
   <arg direction="in" type="b"/></method>
  <method name="Read"><arg direction="in" type="t"/><arg direction="out" type="ay"/>
   <arg direction="out" type="i"/></method>
  <method name="Stop"/>
  <method name="CloseSession"/>
  <method name="CanUpdate"><arg direction="out" type="s"/></method>
  <property name="Version" type="u" access="read"/>
 </interface>
</node>
"""


class Refusal(Exception):
    """A method's answer is one of the service's errors (§4.3)."""

    def __init__(self, code: str, text: str) -> None:
        super().__init__(text)
        self.code = code
        self.text = text


@dataclass
class Session:
    owner: str                    # the caller's unique bus name, never reused
    uid: int
    user: str
    import_keys: bool
    disabled: list[str] = field(default_factory=list)   # aliases to re-enable at the end
    cdn_dir: str = ""
    why: str = ""                 # how it ended, for the audit line
    job: jobs.Job | None = None   # its last job, running or ended, until read (§4.3)
    told: bool = False            # that job's final status has been returned once


def _env_seconds(name: str, default: float) -> float:
    """A test override from the SERVICE's own environment (§4.8), never a client's."""
    try:
        value = float(os.environ.get(name) or default)
    except ValueError:
        return default
    return value if value > 0 else default


def _user(uid: int) -> str:
    try:
        return pwd.getpwuid(uid).pw_name
    except KeyError:
        return "?"


def audit(text: str) -> None:
    """One journal line (§4.9). Stdout is the journal under systemd."""
    print(f"oneup-service: {text}", flush=True)


def _repo_aliases() -> set[str]:
    """The aliases the repository files define, read as the service, now (§4.2)."""
    aliases = set()
    for path in sorted(repos.REPOS_DIR.glob("*.repo")):
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for line in text.splitlines():
            line = line.strip()
            if line.startswith("[") and line.endswith("]"):
                aliases.add(line[1:-1])
    return aliases


class Service:
    def __init__(self, router: DBusRouter) -> None:
        self.router = router
        self.events: queue.Queue = queue.Queue()
        self.sessions: dict[str, Session] = {}
        self.checking: set[str] = set()             # callers whose OpenSession is with polkit
        self.job: jobs.Job | None = None
        self.ending: list[Session] = []             # sessions whose clean-up is still owed
        self.waiting: list[tuple[Message, Session, int, float]] = []   # parked Reads
        self.stopping = False
        self.idle_seconds = _env_seconds("ONEUP_SERVICE_IDLE_SECONDS", 60)
        self.runtime_dir = Path(os.environ.get("ONEUP_SERVICE_RUNTIME_DIR")
                                or os.environ.get("RUNTIME_DIRECTORY") or "/run/oneup")
        jobs.clear_stale(self.runtime_dir)
        self.last_busy = time.monotonic()

    # --- the loop ---------------------------------------------------------------

    def serve(self) -> int:
        while True:
            try:
                # A parked Read is answered as soon as its job writes or ends, so the
                # loop looks often while one waits.
                item = self.events.get(timeout=0.02 if self.waiting else 0.25)
            except queue.Empty:
                item = None
            if isinstance(item, Message):
                self._message(item)
            elif item is not None:
                item()                                 # a worker's result, run here
            self._answer_waiting()
            if self.stopping:
                # §4.8: a session keeps its job readable until the final status has
                # gone out once; every other session ends now.
                for session in list(self.sessions.values()):
                    if session.job is None or session.told:
                        self._end_session(session, "service stopping")
            self._clean_up()
            if self.sessions or self.checking or self.job or self.ending:
                self.last_busy = time.monotonic()
                continue
            if self.stopping:
                audit("stopping on SIGTERM")
                return 0
            if time.monotonic() - self.last_busy >= self.idle_seconds:
                audit("idle; exiting")
                return 0

    def _message(self, msg: Message) -> None:
        hdr = msg.header
        if hdr.message_type == MessageType.signal:
            self._signal(msg)
            return
        if hdr.message_type != MessageType.method_call:
            return
        iface = hdr.fields.get(HeaderFields.interface, "")
        member = hdr.fields.get(HeaderFields.member, "")
        if hdr.fields.get(HeaderFields.path) != OBJECT_PATH:
            self._error(msg, "org.freedesktop.DBus.Error.UnknownObject", "no such object")
            return
        handler = {
            (INTERFACE, "OpenSession"): self._open_session,
            (INTERFACE, "Run"): self._run,
            (INTERFACE, "Read"): self._read,
            (INTERFACE, "Stop"): self._stop,
            (INTERFACE, "CloseSession"): self._close_session,
            (INTERFACE, "CanUpdate"): self._can_update,
            ("org.freedesktop.DBus.Properties", "Get"): self._get_property,
            ("org.freedesktop.DBus.Properties", "GetAll"): self._get_all,
            ("org.freedesktop.DBus.Introspectable", "Introspect"): self._introspect,
        }.get((iface, member))
        if handler is None and not iface:
            handler = {"OpenSession": self._open_session, "Run": self._run,
                       "Read": self._read, "Stop": self._stop, "CloseSession": self._close_session,
                       "CanUpdate": self._can_update}.get(member)
        if handler is None:
            self._error(msg, "org.freedesktop.DBus.Error.UnknownMethod", f"no method {member}")
            return
        try:
            handler(msg)
        except Refusal as exc:
            self._error(msg, _ERR + exc.code, exc.text)
        except Exception as exc:  # noqa: BLE001 — a bug answers one caller, never kills the rest
            audit(f"error in {member}: {exc!r}")
            self._error(msg, "org.freedesktop.DBus.Error.Failed", "internal error")

    def _signal(self, msg: Message) -> None:
        """A caller left the bus: its session ends (§4.3), its job does not (§4.6)."""
        fields = msg.header.fields
        if (fields.get(HeaderFields.sender) != "org.freedesktop.DBus"
                or fields.get(HeaderFields.member) != "NameOwnerChanged"):
            return
        name, _old, new = msg.body
        if new == "" and name in self.sessions:
            self._end_session(self.sessions[name], "caller left")

    # --- replies ------------------------------------------------------------------

    def _reply(self, msg: Message, signature: str | None = None, body: tuple = ()) -> None:
        with contextlib.suppress(OSError):
            self.router.send(new_method_return(msg, signature, body))

    def _error(self, msg: Message, name: str, text: str) -> None:
        with contextlib.suppress(OSError):
            self.router.send(new_error(msg, name, "s", (text,)))

    @staticmethod
    def _sender(msg: Message) -> str:
        return msg.header.fields.get(HeaderFields.sender, "")

    def _post(self, fn) -> None:
        self.events.put(fn)

    # --- OpenSession (§4.4) ---------------------------------------------------------

    def _open_session(self, msg: Message) -> None:
        caller = self._sender(msg)
        options = self._options(msg, "a{sv}", {"interactive": "b", "import_keys": "b"})
        interactive = options.get("interactive", True)
        import_keys = options.get("import_keys", False)
        if self.stopping:
            raise Refusal("Busy", "the service is stopping")
        if caller in self.sessions or caller in self.checking:
            raise Refusal("Busy", "this caller already has a session")
        if len(self.sessions) + len(self.checking) >= MAX_SESSIONS:
            raise Refusal("Busy", "too many sessions")
        self.checking.add(caller)

        def check() -> None:
            uid = polkit.caller_uid(self.router, caller)
            answer = polkit.DENIED
            if uid is not None:
                answer = polkit.check(self.router, caller, polkit.SYSTEM_UPDATE,
                                      interactive=interactive)
                if answer == polkit.YES and import_keys:
                    answer = polkit.check(self.router, caller, polkit.TRUST_SIGNING_KEY,
                                          interactive=interactive)
            self._post(lambda: self._opened(msg, caller, uid, import_keys, answer))

        threading.Thread(target=check, daemon=True).start()

    def _opened(self, msg: Message, caller: str, uid: int | None, import_keys: bool,
                answer: str) -> None:
        self.checking.discard(caller)
        if answer == polkit.YES and not self._has_owner(caller):
            answer = polkit.DENIED            # left mid-check: never a yes (CVE-2021-3560)
        who = f"uid={uid} user={_user(uid) if uid is not None else '?'} caller={caller}"
        if answer != polkit.YES:
            audit(f"session refused {who} reason={answer}")
            self._error(msg, _ERR + "NotAuthorized", answer)
            return
        if self.stopping:
            audit(f"session refused {who} reason=stopping")
            self._error(msg, _ERR + "Busy", "the service is stopping")
            return
        self.sessions[caller] = Session(caller, uid, _user(uid), import_keys)
        audit(f"session opened {who} import_keys={str(import_keys).lower()}")
        self._reply(msg)

    def _has_owner(self, name: str) -> bool:
        try:
            reply = self.router.send_and_get_reply(
                new_method_call(_DBUS, "NameHasOwner", "s", (name,)), timeout=10)
        except Exception:  # noqa: BLE001 — an unanswerable question is a no
            return False
        return reply.header.message_type == MessageType.method_return and reply.body[0] is True

    # --- Run (§4.2, §4.5) -----------------------------------------------------------

    def _run(self, msg: Message) -> None:
        session = self._session(msg)
        if self.stopping:
            raise Refusal("Busy", "the service is stopping")
        if self.job is not None:
            raise Refusal("Busy", "a job is running")
        op, raw_args, merge_stderr = self._body(msg, "sa{sv}b")
        spec = rootops.OPS.get(op)
        if spec is None:
            raise Refusal("Invalid", f"unknown operation {op!r}")
        args = self._variants(raw_args, spec.args)
        self._validate(op, args)
        if args.get("import_keys") is True and not session.import_keys:
            raise Refusal("NotAuthorized", polkit.DENIED)
        if op == "repo-enable" and args["alias"] not in session.disabled:
            raise Refusal("Invalid", "repo-enable undoes only this session's own disable")
        if op == "orphans-remove":
            self._check_unneeded(args["names"])
        if args.get("cdn") is True and not session.cdn_dir:
            session.cdn_dir = repos.make_cdn_reposd()
            if not session.cdn_dir:
                raise Refusal("Invalid", "the CDN repository copy could not be staged")
        argv = rootops.build(op, args, cdn_dir=session.cdn_dir)
        if session.job is not None:      # its last job has ended; its output goes now
            session.job.discard()
            session.job = None
        try:
            job = jobs.Job(op=op, args=args, argv=argv, merge_stderr=merge_stderr,
                           runtime_dir=self.runtime_dir, session=session,
                           on_end=lambda j: self._post(lambda: self._job_ended(j)))
        except OSError as exc:
            raise Refusal("Invalid", f"could not start {op}: {exc.strerror}") from exc
        self.job = job
        session.job = job
        session.told = False
        audit(f"job started uid={session.uid} op={op} args={_args_text(args)}")
        self._reply(msg)

    # --- Read (§4.3) ----------------------------------------------------------------

    def _read(self, msg: Message) -> None:
        session = self._session(msg)
        (offset,) = self._body(msg, "t")
        job = session.job
        if job is None:
            raise Refusal("Invalid", "this session has no job to read")
        if offset > job.size():
            raise Refusal("Invalid", "offset is past the end of the output")
        if not self._answer(msg, session, offset):
            self.waiting.append((msg, session, offset, time.monotonic() + READ_WAIT_SECONDS))

    def _answer(self, msg: Message, session: Session, offset: int) -> bool:
        """Reply if there is something to say: bytes past `offset`, or the job's end."""
        job = session.job
        status = job.status          # first: once set, everything is in the file
        data = job.read(offset)
        if data:
            self._reply(msg, "ayi", (data, -1))
            return True
        if status is not None:
            self._reply(msg, "ayi", (b"", status))
            session.told = True
            return True
        return False

    def _answer_waiting(self) -> None:
        now = time.monotonic()
        parked, self.waiting = self.waiting, []
        for msg, session, offset, deadline in parked:
            if self.sessions.get(session.owner) is not session:
                self._error(msg, _ERR + "NoSession", "this caller has no session")
            elif not self._answer(msg, session, offset):
                if now < deadline:
                    self.waiting.append((msg, session, offset, deadline))
                else:
                    self._reply(msg, "ayi", (b"", -1))

    @staticmethod
    def _validate(op: str, args: dict) -> None:
        """The table's shape checks, then the alias's existence, which needs state.

        The shape check builds with `cdn` false, because the CDN copy is staged only
        once everything else has passed.
        """
        try:
            rootops.build(op, {**args, **({"cdn": False} if "cdn" in args else {})})
        except rootops.Invalid as exc:
            raise Refusal("Invalid", str(exc)) from exc
        if "alias" in args and args["alias"] not in _repo_aliases():
            raise Refusal("Invalid", "no repository has that alias")

    def _check_unneeded(self, names: list[str]) -> None:
        """INV-7: every name must be one zypper calls unneeded, asked just now."""
        rc, out = jobs.run_captured(rootops.build("orphans-unneeded"))
        unneeded = steps._package_column(out) if rc == 0 else None
        if unneeded is None or not set(names) <= set(unneeded):
            raise Refusal("Invalid", "a name is not in zypper's list of unneeded packages")

    def _job_ended(self, job: jobs.Job) -> None:
        session = job.session
        alias = job.args.get("alias")
        if job.status == 0 and job.op == "repo-disable" and alias not in session.disabled:
            session.disabled.append(alias)
        if job.status == 0 and job.op == "repo-enable" and alias in session.disabled:
            session.disabled.remove(alias)
        audit(f"job ended uid={session.uid} op={job.op} status={job.status}")
        if self.job is job:
            self.job = None

    # --- Stop, CloseSession, CanUpdate (§4.6, §4.4) ---------------------------------

    def _stop(self, msg: Message) -> None:
        session = self._session(msg)
        job = self.job
        if job is None:
            raise Refusal("NotStoppable", "nothing is running")
        if job.session is not session:
            raise Refusal("NoSession", "this session did not start the running job")
        if job.op != "system-download":
            raise Refusal("NotStoppable", f"{job.op} is never stopped")
        job.stop()
        audit(f"job stop asked uid={session.uid} op={job.op}")
        self._reply(msg)

    def _close_session(self, msg: Message) -> None:
        self._end_session(self._session(msg), "closed")
        self._reply(msg)

    def _can_update(self, msg: Message) -> None:
        caller = self._sender(msg)

        def check() -> None:
            answer = polkit.check(self.router, caller, polkit.SYSTEM_UPDATE,
                                  interactive=False)
            self._reply(msg, "s", ("yes" if answer == polkit.YES else "no",))

        threading.Thread(target=check, daemon=True).start()

    # --- sessions end ---------------------------------------------------------------

    def _session(self, msg: Message) -> Session:
        session = self.sessions.get(self._sender(msg))
        if session is None:
            raise Refusal("NoSession", "this caller has no session")
        return session

    def _end_session(self, session: Session, why: str) -> None:
        self.sessions.pop(session.owner, None)
        session.why = why
        self.ending.append(session)

    def _clean_up(self) -> None:
        """§4.5: re-enable what a session disabled, drop its CDN copy — once no job runs.

        A re-enable cannot take zypp's lock while a job holds it, and a running
        commit may still be reading the CDN directory.
        """
        if self.job is not None:
            return
        while self.ending:
            session = self.ending.pop(0)
            enabled = []
            for alias in list(session.disabled):
                rc, _ = jobs.run_captured(rootops.build("repo-enable", {"alias": alias}))
                if rc == 0:
                    enabled.append(alias)
                else:
                    audit(f"re-enable failed uid={session.uid} alias={alias} status={rc}")
            if session.cdn_dir:
                shutil.rmtree(session.cdn_dir, ignore_errors=True)
            if session.job is not None:      # ended: no job runs here
                session.job.discard()
            audit(f"session ended uid={session.uid} caller={session.owner} "
                  f"why={session.why} re-enabled={','.join(enabled) or '-'}")

    # --- properties -----------------------------------------------------------------

    def _get_property(self, msg: Message) -> None:
        iface, name = self._body(msg, "ss")
        if iface != INTERFACE or name != "Version":
            self._error(msg, "org.freedesktop.DBus.Error.UnknownProperty", name)
            return
        self._reply(msg, "v", (("u", VERSION),))

    def _get_all(self, msg: Message) -> None:
        (iface,) = self._body(msg, "s")
        self._reply(msg, "a{sv}", ({"Version": ("u", VERSION)} if iface == INTERFACE else {},))

    def _introspect(self, msg: Message) -> None:
        self._reply(msg, "s", (_INTROSPECTION,))

    # --- argument checks: fail closed (§4.2) ----------------------------------------

    @staticmethod
    def _body(msg: Message, signature: str) -> tuple:
        if msg.header.fields.get(HeaderFields.signature, "") != signature:
            raise Refusal("Invalid", f"expected arguments {signature}")
        return msg.body

    def _options(self, msg: Message, signature: str, allowed: dict[str, str]) -> dict:
        (raw,) = self._body(msg, signature)
        return self._variants(raw, allowed, required=False)

    @staticmethod
    def _variants(raw: dict, allowed: dict[str, str], *, required: bool = True) -> dict:
        """Unwrap a{sv}, refusing an unknown key, a wrong type or a missing argument."""
        out = {}
        for name, (sig, value) in raw.items():
            if name not in allowed:
                raise Refusal("Invalid", f"unknown argument {name!r}")
            if sig != allowed[name]:
                raise Refusal("Invalid", f"argument {name} must be {allowed[name]}")
            out[name] = value
        if required and set(out) != set(allowed):
            raise Refusal("Invalid", f"arguments must be {sorted(allowed)}")
        return out


def _args_text(args: dict) -> str:
    return " ".join(f"{k}={','.join(v) if isinstance(v, list) else v}"
                    for k, v in sorted(args.items())) or "-"


def main() -> int:
    bus = os.environ.get("ONEUP_SERVICE_BUS") or "SYSTEM"   # a test's private bus
    try:
        # No descriptor passing: SELinux stops the system bus taking one from this
        # service, and the bus then drops the connection (ONEUP-0282, INV-17).
        conn = open_dbus_connection(bus=bus)
    except OSError as exc:
        print(f"oneup-service: cannot reach the bus: {exc}", file=sys.stderr, flush=True)
        return 1
    router = DBusRouter(conn)
    service = Service(router)
    # Every message reaches the loop through one queue, in arrival order.
    # The handles are kept: a filter lives as long as its handle.
    handles = [router.filter(MatchRule(type="method_call"), queue=service.events)]
    handles.append(router.filter(MatchRule(type="signal", sender="org.freedesktop.DBus",
                            interface="org.freedesktop.DBus", member="NameOwnerChanged"),
                  queue=service.events))
    router.send_and_get_reply(new_method_call(
        _DBUS, "AddMatch", "s",
        ("type='signal',sender='org.freedesktop.DBus',interface='org.freedesktop.DBus',"
         "member='NameOwnerChanged'",)), timeout=10)
    reply = router.send_and_get_reply(
        new_method_call(_DBUS, "RequestName", "su", (BUS_NAME, 0x4)), timeout=10)
    if reply.header.message_type != MessageType.method_return or reply.body[0] != 1:
        print("oneup-service: could not own the bus name", file=sys.stderr, flush=True)
        return 1

    def on_term(_signum, _frame) -> None:
        # §4.8: refuse new sessions, and exit once the running job has ended. A flag
        # only: the loop ends the sessions, because it owns them.
        service.stopping = True

    signal.signal(signal.SIGTERM, on_term)
    audit(f"started version={VERSION}")
    try:
        return service.serve()
    finally:
        with contextlib.suppress(Exception):
            router.send_and_get_reply(
                new_method_call(_DBUS, "ReleaseName", "s", (BUS_NAME,)), timeout=5)
        with contextlib.suppress(Exception):
            router.close()
        with contextlib.suppress(Exception):
            conn.close()
