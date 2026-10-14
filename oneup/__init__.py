"""OneUp — who the application is, and the one place its version lives.

`APP_VERSION` is one of the six version sites `docs/standards/workflow.md` §5.1
documents; `./bump.py` writes it and `local-CI.sh`'s lockstep gate reads it.
Nothing here imports Qt, so the engine can read the app's identity without a
GUI toolkit installed (`docs/standards/files-and-naming.md` §4.1 rule 2).
"""

APP_ID = "za.co.antsprojectshub.OneUp"
APP_NAME = "OneUp"
APP_VERSION = "1.4.10"
REPO_SLUG = "milnet01/OneUp"

# What the window shows as the version. While APP_VERSION still carries a 1.x
# number this checkout is the unfinished 2.0, so it says so rather than passing
# for the last 1.4.x release (ONEUP-0272). From 2.0.0 the two are the same, so
# nothing has to be retired by hand. APP_VERSION stays the number the lockstep
# gate and the in-app update check compare.
APP_VERSION_LABEL = "2.0 preview" if APP_VERSION.startswith("1.") else APP_VERSION
