"""OneUp — who the application is, and the one place its version lives.

`APP_VERSION` is one of the six version sites `docs/standards/workflow.md` §5.1
documents; `./bump.py` writes it and `local-CI.sh`'s lockstep gate reads it.
Nothing here imports Qt, so the engine can read the app's identity without a
GUI toolkit installed (`docs/standards/files-and-naming.md` §4.1 rule 2).
"""

APP_ID = "za.co.antsprojectshub.OneUp"
APP_NAME = "OneUp"
APP_VERSION = "1.4.5"
REPO_SLUG = "milnet01/OneUp"
