#!/usr/bin/env python3
"""Structural checks on the oneup/ package — the rules no reader catches.

Every one of these passes review by looking correct and fails only later, in a
place that looks unrelated:

  INV-2  a path constant bound by name (`from .paths import RUN_STATE`) keeps
         its own copy, so the suite's redirect lands somewhere nobody reads: the
         suite stays green while the window deletes the real run's `run.state`.
  INV-3  an engine module importing a Qt-free helper out of `oneup/gui/` passes
         the design's G5 gate — which only proves the engine imports no Qt — and
         still inverts the dependency the split exists to keep one-way.
  INV-4  a module that builds a path from its own `__file__` gets `oneup/gui/`
         rather than the repo root, so the engine is looked for in the wrong
         directory and the Run button fails; and a systemd unit written from one
         runs a package module that does nothing at all. The existing
         assertions pass either way.
  INV-12 the entry point runs as `__main__`, so importing it by name from inside
         the package would execute the whole file a second time under a second
         name — two QApplication set-ups, two of everything.
  engine a launch site that names its own program cannot reach the Python engine,
         and reads as correct because the Bash one still runs. The tell is
         `paths.ENGINE` at a call site: naming your own program means naming the
         script too, so the constant escaping paths.py IS the hardcoded launch.

An AST walk, not a grep: a mention inside a docstring or a comment is prose and
must not fail the gate, and `# noqa`-style evasion is not available.
Stdlib-only, exit 0 on success and 1 on any failure, so it runs wherever Python
does — `local-CI.sh` and the release workflow both name it by hand, because
nothing in this project discovers tests.

Contracts: `docs/specs/ONEUP-0034-gui-modules.md` §5 for the INV-numbered rules
above; `docs/specs/ONEUP-0054-python-engine.md` §4.7 for the engine-launch rule,
which carries no INV number because it is a build-step guarantee rather than one
of that spec's invariants.
"""
import ast
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PKG = REPO / "oneup"
GUI = PKG / "gui"
ENGINE = PKG / "engine"
PATHS_MODULE = GUI / "paths.py"

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


def _modules(root: Path):
    """Every Python module under `root`, with its parsed tree."""
    for path in sorted(root.rglob("*.py")):
        yield path, ast.parse(path.read_text(), filename=str(path))


def _rel(path: Path) -> str:
    return str(path.relative_to(REPO))


def _imported_names(tree: ast.AST):
    """(module, imported-name-or-None, node) for every import in the tree.

    A relative `from . import paths` reports as ".paths"; a plain
    `from .paths import RUN_STATE` as ".paths" with the name. The leading dots
    are kept so a relative import is distinguishable from an absolute one.
    """
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield alias.name, None, node
        elif isinstance(node, ast.ImportFrom):
            mod = "." * (node.level or 0) + (node.module or "")
            for alias in node.names:
                yield mod, alias.name, node


def main() -> int:
    check("the oneup/ package exists", PKG.is_dir())
    check("oneup/gui/paths.py is where paths live", PATHS_MODULE.is_file())
    if not PKG.is_dir():
        print(f"\n  Passed: {PASS}   Failed: {FAIL}")
        return 1

    # --- INV-2: a path constant is read THROUGH its module, never bound by name.
    offenders = []
    for path, tree in _modules(PKG):
        if path == PATHS_MODULE:
            continue
        for mod, name, node in _imported_names(tree):
            if name is not None and mod.endswith("paths"):
                offenders.append(f"{_rel(path)}:{node.lineno} from {mod} import {name}")
    check("INV-2: no module binds a name out of paths.py "
          f"({'; '.join(offenders) or 'none'})", not offenders)

    # --- INV-3: no engine module imports from oneup.gui.
    # Vacuously true until oneup/engine/ exists — which is the point of writing
    # it now, so it is already in place when ONEUP-0054 starts.
    offenders = []
    if ENGINE.is_dir():
        for path, tree in _modules(ENGINE):
            for mod, _name, node in _imported_names(tree):
                if "oneup.gui" in mod or mod.lstrip(".").startswith("gui"):
                    offenders.append(f"{_rel(path)}:{node.lineno} imports {mod}")
    _none = "none" if ENGINE.is_dir() else "none — the directory does not exist yet"
    check("INV-3: no module under oneup/engine/ imports oneup.gui "
          f"({'; '.join(offenders) or _none})", not offenders)

    # --- INV-4: HERE is computed in exactly one place.
    offenders = []
    for path, tree in _modules(PKG):
        if path == PATHS_MODULE:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Name) and node.id == "__file__":
                offenders.append(f"{_rel(path)}:{node.lineno}")
    check(f"INV-4: __file__ is used only in oneup/gui/paths.py ({'; '.join(offenders) or 'none'})",
          not offenders)
    check("INV-4: paths.py defines HERE",
          any(isinstance(n, ast.Assign)
              and any(isinstance(t, ast.Name) and t.id == "HERE" for t in n.targets)
              for n in ast.walk(ast.parse(PATHS_MODULE.read_text()))))

    # --- ONEUP-0054 stage 7: every engine launch goes through paths.engine_argv.
    # The tell is `paths.ENGINE` read at a call site: a launch that names its own
    # program has to name the script too, so the constant escaping paths.py IS the
    # hardcoded `bash` this stage removed. Checking for the `bash` literal instead
    # would be unrunnable — engine_argv's own v1 arm is one, so the honest count
    # there is one and not zero.
    offenders = []
    for path, tree in _modules(GUI):
        if path == PATHS_MODULE:
            continue
        for node in ast.walk(tree):
            if (isinstance(node, ast.Attribute) and node.attr == "ENGINE"
                    and isinstance(node.value, ast.Name) and node.value.id == "paths"):
                offenders.append(f"{_rel(path)}:{node.lineno}")
    check("engine launches go through paths.engine_argv, not paths.ENGINE "
          f"({'; '.join(offenders) or 'none'})", not offenders)

    # --- INV-12: nothing under oneup/ imports the entry point.
    offenders = []
    for path, tree in _modules(PKG):
        for mod, _name, node in _imported_names(tree):
            if mod == "updater" or mod.startswith("updater."):
                offenders.append(f"{_rel(path)}:{node.lineno} imports {mod}")
    check(f"INV-12: nothing under oneup/ imports updater ({'; '.join(offenders) or 'none'})",
          not offenders)

    print(f"\n  Passed: {PASS}   Failed: {FAIL}")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
