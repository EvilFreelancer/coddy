"""Convert issue YAML (IssueFile) to markdown for the coddy agent to read."""

from coddy.observer.issues.issue_file import IssueFile


def issue_to_markdown(issue: IssueFile, issue_number: int | None = None) -> str:
    """Convert an IssueFile to a single markdown document.

    Output: title, description, then a thread of messages (user comments and bot replies).
    The agent can use this as context when working on the task.
    """
    lines = []
    if issue_number is not None:
        lines.append(f"# Issue {issue_number}")
        lines.append("")
    lines.append("## Title")
    lines.append(issue.title or "(no title)")
    lines.append("")
    lines.append("## Description")
    lines.append(issue.description or "(no description)")
    lines.append("")
    if issue.messages:
        lines.append("## Messages")
        lines.append("")
        for msg in issue.messages:
            lines.append(f"### {msg.name}")
            lines.append("")
            lines.append(msg.content)
            lines.append("")
            lines.append(f"*timestamp: {msg.timestamp}*")
            lines.append("")
    return "\n".join(lines).strip() + "\n"
