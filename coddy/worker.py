"""
Thin wrapper for coddy worker entry point.

Real implementation lives in coddy.worker.run.
Use: python -m coddy.worker
"""

import sys

from coddy.worker.run import main

if __name__ == "__main__":
    sys.exit(main())
