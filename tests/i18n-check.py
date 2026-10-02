#!/usr/bin/env python3
"""Source checks for the translation groundwork — the rules no reader catches.

Each guards a way the window could stop being translatable, or stop mirroring
for right-to-left languages, without any test noticing:

  INV-1   nothing under oneup/engine/ touches translation machinery: the half
          that runs as root has no locale.
  INV-3   nothing sets the layout direction, and no widget reads its own. An
          explicit setLayoutDirection overrides `-reverse`, so the right-to-left
          pass would go green while running left to right. tests/ is read too:
          one in the suite defeats `-reverse` exactly as one in the window does.
  INV-6   no left- or right-handed stylesheet property and no AlignLeft or
          AlignRight anywhere under oneup/: Qt mirrors neither, so each is a
          control on the wrong side in Arabic and Hebrew only.
  INV-7   every string handed to a user in oneup/gui/ is wrapped for
          translation: no bare literal, f-string, `+`, `%` or `.join` at any
          call on the closed list below. It reads the argument at the call, so a
          sentence assembled into a variable first is invisible to it.
  INV-12  no wording is derived by a case change or joined with a literal
          separator under oneup/gui/: CJK has no case and its list separator is
          not ", ". Every such call is data — a search key, an argv, a log line —
          and is on the closed exemption list below with the reason.
  INV-8   the catalogue extracts and compiles, and a finished translation
          survives the round trip. pyside6-lupdate is given the .py files, never
          the directory, which extracts nothing. The one check that needs the Qt
          tools: it alone skips without them, and says so.
  INV-10  nothing sets QFont.NoFontMerging, so a glyph the chosen font lacks is
          always drawn from a font that has it — CJK text never draws as boxes.
  INV-11  no widget caps the size its text can grow to. Every fixed- or
          maximum-size call, and every width/height/max-width/max-height in the
          window's two stylesheets, is on the closed exemption list below, and
          each entry says why that site shows no text or scrolls it.

An AST walk, not a grep: a mention in a docstring or comment is prose and must
not fail the gate. The source checks are stdlib-only and always run; INV-8 alone
uses the Qt tools, in subprocesses. Exit 0 on success and 1 on any failure.
`local-CI.sh` and the release workflow both name it by hand, because nothing in
this project discovers tests.

Contract: `docs/specs/ONEUP-0032-i18n.md` §5.
"""
import ast
import os
import re
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PKG = REPO / "oneup"
GUI = PKG / "gui"
ENGINE = PKG / "engine"
TESTS = REPO / "tests"
THEME = GUI / "theme.py"

PASS = 0
FAIL = 0


def check(name: str, cond: bool):
    global PASS, FAIL
    if cond:
        print(f"  ok   - {name}")
        PASS += 1
    else:
        print(f"  FAIL - {name}")
        FAIL += 1


def _modules(root: Path, skip: tuple[Path, ...] = ()):
    """Every Python module under `root`, with its parsed tree."""
    for path in sorted(root.rglob("*.py")):
        if path.resolve() not in skip:
            yield path, ast.parse(path.read_text(), filename=str(path))


def _rel(path: Path) -> str:
    return str(path.relative_to(REPO))


def _found(offenders: list[str]) -> str:
    return "; ".join(offenders) or "none"


# INV-11's closed exemption list. A size cap on a widget that shows a translatable
# string clips a longer or wider translation, so every cap must be here, with the
# reason it shows no text or scrolls it. Keyed by (file, method, the receiver as
# written) for a call, and by (selector, property) for a stylesheet declaration.
SIZE_CAP_EXEMPT = {
    ("oneup/gui/toggle_switch.py", "setFixedSize", "self"):
        "ToggleSwitch is painted geometry with no label of its own",
    ("oneup/gui/task_row.py", "setMaximumHeight", "scroll"):
        "the package list is a scroll area: its content scrolls rather than clips",
}
QSS_CAP_EXEMPT = {
    ("QComboBox#ThemeCombo::drop-down", "width"):
        "the combo box's arrow sub-control, which shows no text",
}
# INV-7's closed list: every call that hands a sentence to a user, with the
# positions of the arguments that carry one. Adding a text-setting call to the
# window means adding it here in the same commit, or it is silently exempt.
_SETTERS = {name: (0,) for name in (
    "setText", "setToolTip", "setWindowTitle", "setAccessibleName",
    "setAccessibleDescription", "setPlaceholderText", "addItem", "setInformativeText",
    "setStatusTip", "setWhatsThis", "setTitle", "addAction", "addMenu",
    "_announce",                        # the screen-reader announcement, a window method
    "setFormat",                        # the progress bar's caption
    "set_badge", "set_size_result",     # TaskRow helpers that set a label's text
    "_heading", "_row", "_settings_status")}   # the Settings dialog's own helpers
_SETTERS.update({"showMessage": (0, 1),  # QSystemTrayIcon: title, message
                 "addButton": (0,)})
_MESSAGE_BOX = {"warning", "critical", "information", "question"}   # (parent, title, text)
_HELPERS = {                             # project helpers whose parameter reaches a user
    "_show_warning": (1,), "_confirm_reboot": (1, 2), "_set_activity": (1,),
    "_notify_when_away": (1,), "_notify": (0, 1),
    "_make_banner": (3,)}                # (win, frame name, button name, button text, …)
_WIDGETS = {"QLabel", "QPushButton", "QCheckBox", "QAction", "QGroupBox",
            "QToolButton", "QRadioButton", "QMenu"}                  # text as argument 0


def _translated(node: ast.AST) -> bool:
    return (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
            and node.func.attr in ("translate", "tr"))


def _unwrapped(node: ast.AST) -> str | None:
    """Why this argument is an unwrapped sentence, or None if it is not one. A
    translate/tr call passes — and so does `.format` on one, which is
    `wording-and-translation.md` §6.2's own form, and a `.join` whose separator is
    not a literal, which is how ONEUP-0032 §4.5 joins a list. A literal with no
    letter in it (an empty string, a lone symbol) is not a sentence."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return "a bare literal" if any(c.isalpha() for c in node.value) else None
    if isinstance(node, ast.JoinedStr):
        return "an f-string"
    if isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Add, ast.Mod)):
        return "a + or % concatenation"
    if isinstance(node, ast.IfExp):
        return _unwrapped(node.body) or _unwrapped(node.orelse)
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
        if node.func.attr == "join" and isinstance(node.func.value, ast.Constant):
            return "a .join on a literal separator"   # a translated separator passes
        if node.func.attr == "format" and not _translated(node.func.value):
            return "a .format on something not translated"
    return None


def _sentence_args(call: ast.Call) -> tuple[int, ...]:
    func = call.func
    name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
    if (isinstance(func, ast.Attribute) and name in _MESSAGE_BOX
            and isinstance(func.value, ast.Name) and func.value.id == "QMessageBox"):
        return (1, 2)
    if name in _HELPERS:
        return _HELPERS[name]
    if name in _WIDGETS and isinstance(func, ast.Name):
        return (0,)
    return _SETTERS.get(name, ()) if isinstance(func, ast.Attribute) else ()


# INV-12's closed exemption list, keyed by (file, enclosing function, call). Every
# entry is data no user reads as wording.
WORD_LOGIC_EXEMPT = {
    ("oneup/gui/autostart.py", "_arg", "join ''"):
        "quotes one argument for a systemd unit's or .desktop file's command line",
    ("oneup/gui/contrast.py", "bad_exceptions", "lower"):
        "a search key: looks for deferral words in a contrast exemption's reason",
    ("oneup/gui/contrast.py", "report", "join '\\n'"):
        "a developer's contrast report, printed for a palette author",
    ("oneup/gui/diagnostics.py", "build_diagnostics", "join '  '"):
        "the bug-report payload, read by a developer (ONEUP-0032 §10)",
    ("oneup/gui/diagnostics.py", "build_diagnostics", "join '\\n'"):
        "the bug-report payload's lines, read by a developer",
    ("oneup/gui/paths.py", "_resolve_engine", "join '; '"):
        "the stderr line naming the paths the resolver tried",
    ("oneup/gui/paths.py", "engine_argv", "join '; '"):
        "an exception message, for a developer",
    ("oneup/gui/paths.py", "engine_tried", "join '\\n'"):
        "one path or tool name per line — data, not a sentence",
    ("oneup/gui/repos.py", "_parse_repos", "lower"):
        "reads zypper's Yes/No column as a flag",
    ("oneup/gui/repos.py", "_repo_purpose", "lower"):
        "a search key over the alias, name and URL",
    ("oneup/gui/repos.py", "_build_apply_command", "join ' '"):
        "builds a zypper command line",
    ("oneup/gui/repos.py", "_build_apply_command", "join ' && '"):
        "chains shell commands for pkexec",
    ("oneup/gui/run.py", "_engine_args", "join ','"):
        "the engine's --steps= argument",
    ("oneup/gui/run.py", "_adopt_held_engine", "join ','"):
        "the go-ahead file's step list, read by the engine",
    ("oneup/gui/theme.py", "derive_focus", "join ', '"):
        "an exception message naming colours, for a palette author",
}
_CASE_CALLS = {"lower", "upper", "capitalize", "title", "swapcase", "casefold"}


def _enclosing(tree: ast.AST) -> dict[int, str]:
    """id(node) -> the name of the function it sits in."""
    where: dict[int, str] = {}

    def walk(node, name):
        for child in ast.iter_child_nodes(node):
            inner = child.name if isinstance(child, (ast.FunctionDef,
                                                     ast.AsyncFunctionDef)) else name
            where[id(child)] = inner
            walk(child, inner)
    walk(tree, "<module>")
    return where


_CAP_CALLS = {"setFixedWidth", "setFixedHeight", "setFixedSize",
              "setMaximumWidth", "setMaximumHeight", "setMaximumSize"}
_HANDED_QSS = re.compile(
    r"\b(?:margin|padding|border)-(?:left|right)\s*:|\btext-align\s*:\s*(?:left|right)\b"
    r"|\bqproperty-alignment\b")
_QSS_RULE = re.compile(r"([^{}]+)\{([^{}]*)\}")
_QSS_CAP = re.compile(r"(?:^|;)\s*(max-width|max-height|width|height)\s*:")


def _stylesheets() -> dict[str, str]:
    """The window's two stylesheet templates, `_QSS` and `_HC_QSS`, by name."""
    sheets = {}
    for node in ast.parse(THEME.read_text()).body:
        if (isinstance(node, ast.Assign) and len(node.targets) == 1
                and isinstance(node.targets[0], ast.Name)
                and node.targets[0].id in ("_QSS", "_HC_QSS")):
            value = node.value       # `Template(r"""…""")`: the template is its argument
            if isinstance(value, ast.Call) and value.args:
                value = value.args[0]
            sheets[node.targets[0].id] = ast.literal_eval(value)
    return sheets


_ROUND_TRIP = """
import sys
from PySide6.QtCore import QCoreApplication, QTranslator
app = QCoreApplication([])
t = QTranslator()
ok = t.load(sys.argv[1]) and app.installTranslator(t)
print("TRANSLATED" if ok and QCoreApplication.translate(sys.argv[2], sys.argv[3])
      == sys.argv[4] else "ENGLISH")
"""


def _catalogue_round_trip() -> None:
    """INV-8: extract, finish one message, compile, and read it back through Qt."""
    lupdate, lrelease = shutil.which("pyside6-lupdate"), shutil.which("pyside6-lrelease")
    if not (lupdate and lrelease):
        print("  SKIP - INV-8 needs pyside6-lupdate and pyside6-lrelease, not installed")
        return
    with tempfile.TemporaryDirectory() as tmp:
        ts, qm = os.path.join(tmp, "oneup_xx.ts"), os.path.join(tmp, "oneup_xx.qm")
        files = [str(p) for p in sorted(PKG.rglob("*.py"))]
        subprocess.run([lupdate, *files, "-ts", ts],  # noqa: S603 — fixed argv, no shell.
                       capture_output=True, check=True)
        tree = ET.parse(ts)   # noqa: S314 — the file lupdate wrote a moment ago
        contexts = {c.findtext("name"): c for c in tree.getroot().iter("context")}
        wanted = {"markers", "steps", "run", "window", "_Counted"}
        check(f"INV-8: extraction reaches the window and its tables (missing: "
              f"{_found(sorted(wanted - set(contexts)))})", wanted <= set(contexts))
        check("INV-8: the counted sentences extract as plurals",
              any(m.get("numerus") == "yes" for m in contexts.get("_Counted", ET.Element("x"))
                  .iter("message")))
        if "markers" not in contexts:
            return              # reported above; there is nothing to round-trip
        target = next(m for m in contexts["markers"].iter("message")
                      if m.get("numerus") != "yes")
        source = target.findtext("source")
        translation = target.find("translation")
        translation.attrib.pop("type", None)
        translation.text = "INV-8 round trip"
        tree.write(ts, encoding="utf-8", xml_declaration=True)
        subprocess.run([lrelease, ts, "-qm", qm],  # noqa: S603 — fixed argv, no shell.
                       capture_output=True, check=True)
        out = subprocess.run(  # noqa: S603 — this interpreter, a fixed script.
            [sys.executable, "-c", _ROUND_TRIP, qm, "markers", source, "INV-8 round trip"],
            capture_output=True, text=True, env={**os.environ, "QT_QPA_PLATFORM": "offscreen"})
        check("INV-8: a finished translation survives extract, compile and load",
              out.stdout.strip() == "TRANSLATED")


def main() -> int:
    # --- INV-1: the engine has no translation machinery at all.
    offenders = []
    for path, tree in _modules(ENGINE):
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                mods = ([a.name for a in node.names] if isinstance(node, ast.Import)
                        else [node.module or ""])
                offenders += [f"{_rel(path)}:{node.lineno} imports {m}" for m in mods
                              if m.split(".")[0] in ("gettext", "PySide6")]
            elif isinstance(node, ast.Name) and node.id in (
                    "QTranslator", "QCoreApplication", "QT_TRANSLATE_NOOP"):
                offenders.append(f"{_rel(path)}:{node.lineno} names {node.id}")
            elif (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                  and node.func.attr == "tr"):
                offenders.append(f"{_rel(path)}:{node.lineno} calls .tr()")
    check(f"INV-1: nothing under oneup/engine/ touches translation ({_found(offenders)})",
          not offenders)

    # --- INV-3: the direction is Qt's to derive — never set, never read per widget.
    offenders = []
    this = Path(__file__).resolve()
    for root in (PKG, TESTS):
        for path, tree in _modules(root, skip=(this,)):
            for node in ast.walk(tree):
                if (isinstance(node, ast.Attribute)
                        and node.attr in ("setLayoutDirection", "layoutDirection")):
                    offenders.append(f"{_rel(path)}:{node.lineno} {node.attr}")
    check(f"INV-3: nothing sets the layout direction or reads a widget's own "
          f"({_found(offenders)})", not offenders)

    # --- INV-6: nothing handed — not in any string under oneup/ (every stylesheet
    # the window applies is one), and no fixed-side alignment flag. Docstrings are
    # prose and are skipped; `text-align: center` has no hand and is not matched.
    offenders = []
    for path, tree in _modules(PKG):
        docs = {id(n.body[0].value) for n in ast.walk(tree)
                if isinstance(n, (ast.Module, ast.ClassDef, ast.FunctionDef,
                                  ast.AsyncFunctionDef))
                and n.body and isinstance(n.body[0], ast.Expr)
                and isinstance(n.body[0].value, ast.Constant)}
        for node in ast.walk(tree):
            if (isinstance(node, ast.Constant) and isinstance(node.value, str)
                    and id(node) not in docs):
                offenders += [f"{_rel(path)}:{node.lineno} {m.group(0).strip()}"
                              for m in _HANDED_QSS.finditer(node.value)]
            elif isinstance(node, ast.Attribute) and node.attr in ("AlignLeft", "AlignRight"):
                offenders.append(f"{_rel(path)}:{node.lineno} {node.attr}")
    check(f"INV-6: nothing under oneup/ is left- or right-handed ({_found(offenders)})",
          not offenders)

    # --- INV-7: every sentence a user is handed is wrapped.
    offenders = []
    for path, tree in _modules(GUI):
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                for i in _sentence_args(node):
                    if i < len(node.args) and (why := _unwrapped(node.args[i])):
                        offenders.append(f"{_rel(path)}:{node.lineno} {why}")
    check(f"INV-7: every sentence handed to a user is wrapped ({len(offenders)} not: "
          f"{_found(offenders)})", not offenders)

    # --- INV-12: no wording by case change or literal-separator join.
    offenders, seen = [], set()
    for path, tree in _modules(GUI):
        where = _enclosing(tree)
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)):
                continue
            if node.func.attr in _CASE_CALLS and not node.args:
                call = node.func.attr
            elif node.func.attr == "join" and isinstance(node.func.value, ast.Constant):
                call = f"join {node.func.value.value!r}"
            else:
                continue
            key = (_rel(path), where.get(id(node), "<module>"), call)
            seen.add(key)
            if key not in WORD_LOGIC_EXEMPT:
                offenders.append(f"{key[0]}:{node.lineno} {key[2]} in {key[1]}")
    check(f"INV-12: no wording by a case change or a literal separator ({_found(offenders)})",
          not offenders)
    stale = [str(k) for k in WORD_LOGIC_EXEMPT if k not in seen]
    check(f"INV-12: every exemption still names a real site ({_found(stale)})", not stale)

    # --- INV-10: font fallback is never switched off.
    offenders = [f"{_rel(path)}:{node.lineno}"
                 for path, tree in _modules(PKG) for node in ast.walk(tree)
                 if (isinstance(node, ast.Attribute) and node.attr == "NoFontMerging")
                 or (isinstance(node, ast.Name) and node.id == "NoFontMerging")]
    check(f"INV-10: nothing sets QFont.NoFontMerging ({_found(offenders)})", not offenders)

    # --- INV-11: no size cap a translation could outgrow.
    offenders, seen = [], set()
    for path, tree in _modules(GUI):
        for node in ast.walk(tree):
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                    and node.func.attr in _CAP_CALLS):
                key = (_rel(path), node.func.attr, ast.unparse(node.func.value))
                seen.add(key)
                if key not in SIZE_CAP_EXEMPT:
                    offenders.append(f"{key[0]}:{node.lineno} {key[2]}.{key[1]}")
    sheets = _stylesheets()
    check("INV-11: both stylesheet templates were found and read",
          set(sheets) == {"_QSS", "_HC_QSS"})
    for name, qss in sheets.items():
        for selector, body in _QSS_RULE.findall(qss):
            for prop in _QSS_CAP.findall(body):
                key = (" ".join(selector.split()), prop)
                seen.add(key)
                if key not in QSS_CAP_EXEMPT:
                    offenders.append(f"{name}: {key[0]} {{ {prop} }}")
    check(f"INV-11: every size cap is on the exemption list ({_found(offenders)})",
          not offenders)
    stale = [str(k) for k in (*SIZE_CAP_EXEMPT, *QSS_CAP_EXEMPT) if k not in seen]
    check(f"INV-11: every exemption still names a real site ({_found(stale)})", not stale)

    _catalogue_round_trip()

    print(f"\n  Passed: {PASS}   Failed: {FAIL}")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
