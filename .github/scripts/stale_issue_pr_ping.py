# Copyright (c) Microsoft. All rights reserved.

"""Scan open issues and PRs labeled 'waiting-for-author' for stale follow-ups.

Team members manually add the 'waiting-for-author' label when they need a
response from the external author.  If the author hasn't replied within
DAYS_THRESHOLD days of the last team comment, post a reminder and add the
'requested-info' label to prevent duplicate pings.
"""

from __future__ import annotations

import os
import sys
import time
from datetime import datetime, timezone

from github import Auth, Github, GithubException
from github.Issue import Issue
from github.IssueComment import IssueComment


PING_COMMENT = (
    "@{author}, friendly reminder — this issue is waiting on your response. "
    "Please share any updates when you get a chance. (This is an automated message.)"
)
TRIGGER_LABEL = "waiting-for-author"
PINGED_LABEL = "requested-info"


def get_team_members(g: Github, org: str, team_slug: str) -> set[str]:
    """Fetch active team member usernames."""
    try:
        org_obj = g.get_organization(org)
        team = org_obj.get_team_by_slug(team_slug)
        return {m.login for m in team.get_members()}
    except GithubException as exc:
        if exc.status in (403, 404):
            print(
                f"ERROR: Failed to fetch team members for {org}/{team_slug} "
                f"(HTTP {exc.status}). Check that the token has the 'read:org' "
                f"scope and that the team slug '{team_slug}' is correct."
            )
        else:
            print(f"ERROR: Failed to fetch team members for {org}/{team_slug}: {exc}")
        sys.exit(1)
    except Exception as exc:
        print(f"ERROR: Failed to fetch team members for {org}/{team_slug}: {exc}")
        sys.exit(1)


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

    # Skip if no comments at all
    if issue.comments == 0:
        return False

    # Fetch comments once for both lookups
    comments = list(issue.get_comments())

    # Find last team member comment
    last_team_comment = find_last_team_comment(comments, team_members)
    if last_team_comment is None:
        return False

    # Skip if author replied after the last team comment
    if author_replied_after(comments, author, last_team_comment.created_at):
        return False

    # Check if enough days have passed
    days_since = (now - last_team_comment.created_at.astimezone(timezone.utc)).days
    if days_since < days_threshold:
        return False

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

    team_slug = os.environ.get("TEAM_SLUG")
    if not team_slug:
        print("ERROR: TEAM_SLUG environment variable is required")
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

    print(f"Fetching team members for {org}/{team_slug}...")
    team_members = get_team_members(g, org, team_slug)
    print(f"Found {len(team_members)} team members.\n")

    now = datetime.now(timezone.utc)
    pinged = []
    failed = []
    scanned = 0

    print(f"Scanning open issues and PRs labeled '{TRIGGER_LABEL}' (threshold: {days_threshold} days)...\n")

    for issue in repo.get_issues(state="open", labels=[TRIGGER_LABEL]):
        scanned += 1

        if should_ping(issue, team_members, days_threshold, now):
            if ping(issue, dry_run):
                pinged.append(issue.number)
            else:
                failed.append(issue.number)

    print(f"\nDone. Scanned {scanned} items, pinged {len(pinged)}, failed {len(failed)}.")
    if pinged:
        print(f"Pinged: {', '.join(f'#{n}' for n in pinged)}")
    if failed:
        print(f"Failed: {', '.join(f'#{n}' for n in failed)}")
        sys.exit(1)


if __name__ == "__main__":
    main()
