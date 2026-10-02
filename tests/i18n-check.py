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
  INV-10  nothing sets QFont.NoFontMerging, so a glyph the chosen font lacks is
          always drawn from a font that has it — CJK text never draws as boxes.
  INV-11  no widget caps the size its text can grow to. Every fixed- or
          maximum-size call, and every width/height/max-width/max-height in the
          window's two stylesheets, is on the closed exemption list below, and
          each entry says why that site shows no text or scrolls it.

An AST walk, not a grep: a mention in a docstring or comment is prose and must
not fail the gate. Stdlib-only, exit 0 on success and 1 on any failure.
`local-CI.sh` and the release workflow both name it by hand, because nothing in
this project discovers tests.

Contract: `docs/specs/ONEUP-0032-i18n.md` §5.
"""
import ast
import re
import sys
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
_CAP_CALLS = {"setFixedWidth", "setFixedHeight", "setFixedSize",
              "setMaximumWidth", "setMaximumHeight", "setMaximumSize"}
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

    print(f"\n  Passed: {PASS}   Failed: {FAIL}")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
