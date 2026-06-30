"""Eval harness CI entrypoint (placeholder).

No-op until Phase 2 (matching) and Phase 6 (faithfulness) populate it. Exits 0
so the CI job is green in Phase 0.
"""

from __future__ import annotations

import sys


def main() -> int:
    print("evals: no eval suites registered yet (Phase 0). Skipping.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
