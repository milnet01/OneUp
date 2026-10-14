"""OneUp's system service: runs the engine's root commands, and nothing else.

`docs/specs/ONEUP-0249-system-service.md` §4.3 to §4.9. It runs as root on the system
bus, started on demand by D-Bus through `oneup-service.service`, and exits when idle.
It takes an operation's NAME and typed arguments, never an argv, and builds the
command from `oneup/engine/rootops.py`, the same table the sudo route builds from.
Whether a caller may is polkit's answer to Discover's system-update action (§4.4).

Started by `/usr/libexec/oneup-service` under `python3 -I` (§4.8). It imports engine
modules and nothing from `oneup/gui/`.
"""
