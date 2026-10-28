# Copyright (c) Microsoft. All rights reserved.

"""Classify open issues and PRs waiting for external authors and ping stale items.

When a maintainer leaves the latest conversation comment on an external item,
the automation adds 'waiting-for-author'. On later runs, inactive items receive
a reminder and the 'requested-info' label to prevent duplicate pings.
"""

from __future__ import annotations

import os
import sys
import time
from datetime import datetime, timezone

from github import Auth, Github, GithubException
from github.Issue import Issue
from github.IssueComment import IssueComment
from github.Repository import Repository


PING_COMMENT = (
    "@{author}, friendly reminder — this issue is waiting on your response. "
    "Please share any updates when you get a chance. (This is an automated message.)"
)
TRIGGER_LABEL = "waiting-for-author"
PINGED_LABEL = "requested-info"


def get_maintainers(repo: Repository) -> set[str]:
    """Fetch maintainer usernames from CODEOWNERS on the default branch."""
    codeowners = repo.get_contents(
        ".github/CODEOWNERS",
        ref=repo.default_branch,
    )

    if isinstance(codeowners, list):
        raise RuntimeError("Expected CODEOWNERS to be a file")

    content = codeowners.decoded_content.decode("utf-8")
    owners = set()

    for line in content.splitlines():
        parts = line.split()
        if not parts or parts[0] not in {"/python/", "/dotnet/"}:
            continue

        owners.update(
            owner.removeprefix("@").lower()
            for owner in parts[1:]
            if owner.startswith("@")
        )

    if not owners:
        raise RuntimeError("No maintainers found in CODEOWNERS")

    return owners


def find_last_team_comment(
    comments: list[IssueComment], team_members: set[str]
) -> IssueComment | None:
    """Return the most recent comment from a team member, or None."""
    for comment in reversed(comments):
        if comment.user and comment.user.login in team_members:
            return comment
    return None


def author_replied_after(
    comments: list[IssueComment], author: str, after: datetime
) -> bool:
    """Check if the issue author commented after the given timestamp."""
    for comment in comments:
        if (
            comment.user
            and comment.user.login == author
            and comment.created_at > after
        ):
            return True
    return False


def should_mark_waiting(issue: Issue, team_members: set[str]) -> bool:
    """Return whether an external item should gain 'waiting-for-author'.

    Policy: a CODEOWNER's latest conversation comment marks the item, and newly
    marked items are not pinged until a later scheduled run.
    """
    if issue.user.login in team_members:
        return False
    if any(label.name == TRIGGER_LABEL for label in issue.labels):
        return False
    if issue.comments == 0:
        return False

    comments = list(issue.get_comments())
    if not comments:
        return False

    latest_comment = comments[-1]
    return bool(
        latest_comment.user
        and latest_comment.user.login in team_members
    )


def should_ping(
    issue: Issue,
    team_members: set[str],
    days_threshold: int,
    now: datetime,
) -> bool:
    """Determine whether this issue/PR should be pinged.

    Only issues/PRs carrying the 'waiting-for-author' label are candidates.
    """
    author = issue.user.login

    # Skip if the trigger label is not present
    if not any(label.name == TRIGGER_LABEL for label in issue.labels):
        return False
    # Skip if author is a team member
    if author in team_members:
        return False

    # Skip if already pinged
    if any(label.name == PINGED_LABEL for label in issue.labels):
        return False

    # Check if the issue has been inactive long enough
    days_since = (now - issue.updated_at.astimezone(timezone.utc)).days
    return days_since >= days_threshold


def mark_waiting(issue: Issue, dry_run: bool) -> bool:
    """Add the 'waiting-for-author' label. Returns True on success."""
    author = issue.user.login
    kind = "PR" if issue.pull_request else "Issue"

    if dry_run:
        print(
            f"  [DRY RUN] Would mark {kind} #{issue.number} "
            f"as waiting for @{author}"
        )
        return True

    try:
        issue.add_to_labels(TRIGGER_LABEL)
    except Exception as exc:
        print(
            f"  ERROR: Failed to mark {kind} #{issue.number} "
            f"as waiting for @{author}: {exc}"
        )
        return False

    print(f"  Marked {kind} #{issue.number} as waiting for @{author}")
    return True


def ping(issue: Issue, dry_run: bool) -> bool:
    """Post a reminder comment and add the 'requested-info' label. Returns True on success."""
    author = issue.user.login
    kind = "PR" if issue.pull_request else "Issue"

    if dry_run:
        print(f"  [DRY RUN] Would ping {kind} #{issue.number} (@{author})")
        return True

    max_retries = 3
    commented = False
    labeled = False
    for attempt in range(1, max_retries + 1):
        try:
            if not commented:
                issue.create_comment(PING_COMMENT.format(author=author))
                commented = True
            if not labeled:
                issue.add_to_labels(PINGED_LABEL)
                labeled = True
            print(f"  Pinged {kind} #{issue.number} (@{author})")
            return True
        except Exception as exc:
            if attempt < max_retries:
                wait = 2 ** attempt  # 2s, 4s
                print(f"  WARN: Attempt {attempt}/{max_retries} failed for {kind} #{issue.number}: {exc}. Retrying in {wait}s...")
                time.sleep(wait)
            else:
                print(f"  ERROR: Failed to ping {kind} #{issue.number} after {max_retries} attempts: {exc}")
                return False


def main() -> None:
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        print("ERROR: GITHUB_TOKEN environment variable is required")
        sys.exit(1)

    repository = os.environ.get("GITHUB_REPOSITORY")
    if not repository:
        print("ERROR: GITHUB_REPOSITORY environment variable is required")
        sys.exit(1)

    days_threshold_raw = os.environ.get("DAYS_THRESHOLD", "4")
    try:
        days_threshold = int(days_threshold_raw)
    except ValueError:
        print(f"ERROR: DAYS_THRESHOLD must be a numeric value, got '{days_threshold_raw}'")
        sys.exit(1)
    dry_run = os.environ.get("DRY_RUN", "false").lower() == "true"

    org = repository.split("/")[0]

    if dry_run:
        print("Running in DRY RUN mode — no comments or labels will be applied.\n")

    g = Github(auth=Auth.Token(token))
    repo = g.get_repo(repository)

    print("Fetching maintainers...")
    team_members = get_maintainers(repo)
    print(f"Found {len(team_members)} team members.\n")
    for maintainer in sorted(team_members):
        print(f"  @{maintainer}")

    now = datetime.now(timezone.utc)
    marked = []
    pinged = []
    failed = []
    scanned = 0

    print(
        "Scanning open issues and PRs "
        f"(stale threshold: {days_threshold} days)...\n"
    )

    for issue in repo.get_issues(state="open"):
        scanned += 1

        if should_mark_waiting(issue, team_members):
            if mark_waiting(issue, dry_run):
                marked.append(issue.number)
            else:
                failed.append(issue.number)
            continue

        if should_ping(issue, team_members, days_threshold, now):
            if ping(issue, dry_run):
                pinged.append(issue.number)
            else:
                failed.append(issue.number)

    print(
        f"\nDone. Scanned {scanned} items, marked {len(marked)}, "
        f"pinged {len(pinged)}, failed {len(failed)}."
    )
    if marked:
        print(f"Marked waiting: {', '.join(f'#{n}' for n in marked)}")
    if pinged:
        print(f"Pinged: {', '.join(f'#{n}' for n in pinged)}")
    if failed:
        print(f"Failed: {', '.join(f'#{n}' for n in failed)}")
        sys.exit(1)


if __name__ == "__main__":
    main()
