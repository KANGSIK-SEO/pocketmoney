"""
Entrypoint when executed as `python -m budget_app`.
"""

import sys
from budget_app.cli import main

if __name__ == "__main__":
    sys.exit(main())
