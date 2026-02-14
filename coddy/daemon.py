"""
Thin wrapper for coddy daemon entry point.

Real implementation lives in coddy.observer.daemon.
Use: python -m coddy.daemon
"""

import sys

from coddy.observer.daemon import main

if __name__ == "__main__":
    sys.exit(main())
