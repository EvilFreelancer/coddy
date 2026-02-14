"""CLI: load issue from .coddy/issues/{N}.yaml and print markdown for the agent."""

import argparse
import sys
from pathlib import Path

from coddy.observer.issues import load_issue


def main() -> int:
    parser = argparse.ArgumentParser(description="Convert issue YAML to markdown for coddy agent")
    parser.add_argument("issue_number", type=int, help="Issue number")
    parser.add_argument(
        "repo_dir",
        type=Path,
        nargs="?",
        default=Path.cwd(),
        help="Repository root (default: current directory)",
    )
    args = parser.parse_args()

    issue = load_issue(args.repo_dir, args.issue_number)
    if not issue:
        print(f"Issue #{args.issue_number} not found in {args.repo_dir / '.coddy' / 'issues'}", file=sys.stderr)
        return 1
    print(issue.to_markdown())
    return 0


if __name__ == "__main__":
    sys.exit(main())
