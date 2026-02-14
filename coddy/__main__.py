"""Allow running package as python -m coddy (observer | worker)."""

import sys

from coddy.main import main

if __name__ == "__main__":
    sys.exit(main())
