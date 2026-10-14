"""`python3 -m oneup.service` — the launcher's entry, and the test suite's."""

import sys

from .server import main

sys.exit(main())
