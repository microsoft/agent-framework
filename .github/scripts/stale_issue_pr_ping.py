# Copyright (c) Microsoft. All rights reserved.

"""Warn and close stale external-authored pull requests.

After a CODEOWNER's latest conversation comment, warn and apply
'requested-info' after the warning threshold, then close after the closing
threshold without activity. CODEOWNER-authored and 'dont-close'-labeled pull
requests are exempt.
"""

from __future__ import annotations

import os
import sys
import time
from datetime import datetime, timezone

from github import Auth, Github
from github.PullRequest import PullRequest
from github.Repository import Repository


REQUESTED_INFO_LABEL = "requested-info"
DONT_CLOSE_LABEL = "dont-close"
WARNING_THRESHOLD_DAYS = 4
CLOSING_THRESHOLD_DAYS = 4
WARNING_COMMENT = (
    "@{author}, this pull request is waiting on your response. "
    "If there is no further activity within {closing_days} days, "
    "it will be closed automatically. (This is an automated message.)"
)
CLOSING_COMMENT = (
    "Closing this pull request because there was no further activity "
    "after the automated warning. (This is an automated message.)"
)


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


def should_warn(
    pull_request: PullRequest,
    maintainers: set[str],
    now: datetime,
    warning_threshold_days: int,
) -> bool:
    """Return whether an external pull request is ready for its warning."""
    if pull_request.user.login.lower() in maintainers:
        return False
    if any(label.name == DONT_CLOSE_LABEL for label in pull_request.labels):
        return False
    if any(label.name == REQUESTED_INFO_LABEL for label in pull_request.labels):
        return False
    days_inactive = (
        now - pull_request.updated_at.astimezone(timezone.utc)
    ).days
    if days_inactive < warning_threshold_days:
        return False

    comments = list(pull_request.get_issue_comments())
    if not comments:
        return False

    latest_comment = comments[-1]
    return bool(
        latest_comment.user
        and latest_comment.user.login.lower() in maintainers
    )


def should_close(
    pull_request: PullRequest,
    maintainers: set[str],
    now: datetime,
    closing_threshold_days: int,
) -> bool:
    """Return whether a warned external pull request is ready to close."""
    if pull_request.user.login.lower() in maintainers:
        return False
    if any(label.name == DONT_CLOSE_LABEL for label in pull_request.labels):
        return False
    if not any(
        label.name == REQUESTED_INFO_LABEL
        for label in pull_request.labels
    ):
        return False

    days_inactive = (
        now - pull_request.updated_at.astimezone(timezone.utc)
    ).days
    return days_inactive >= closing_threshold_days


def warn(
    pull_request: PullRequest,
    dry_run: bool,
    closing_threshold_days: int,
) -> bool:
    """Post the warning and add 'requested-info'. Returns True on success."""
    author = pull_request.user.login

    if dry_run:
        print(
            f"  [DRY RUN] Would warn PR #{pull_request.number} (@{author}) "
            f"and add '{REQUESTED_INFO_LABEL}'"
        )
        return True

    max_retries = 3
    commented = False
    labeled = False
    for attempt in range(1, max_retries + 1):
        try:
            if not commented:
                pull_request.create_issue_comment(
                    WARNING_COMMENT.format(
                        author=author,
                        closing_days=closing_threshold_days,
                    )
                )
                commented = True
            if not labeled:
                pull_request.add_to_labels(REQUESTED_INFO_LABEL)
                labeled = True
            print(f"  Warned PR #{pull_request.number} (@{author})")
            return True
        except Exception as exc:
            if attempt < max_retries:
                wait = 2 ** attempt  # 2s, 4s
                print(
                    f"  WARN: Warning attempt {attempt}/{max_retries} failed "
                    f"for PR #{pull_request.number}: {exc}. "
                    f"Retrying in {wait}s..."
                )
                time.sleep(wait)
            else:
                print(
                    f"  ERROR: Failed to warn PR #{pull_request.number} after "
                    f"{max_retries} attempts: {exc}"
                )
                return False


def close(pull_request: PullRequest, dry_run: bool) -> bool:
    """Post the closing message and close the PR. Returns True on success."""
    author = pull_request.user.login

    if dry_run:
        print(
            f"  [DRY RUN] Would comment on and close "
            f"PR #{pull_request.number} (@{author})"
        )
        return True

    max_retries = 3
    commented = False
    for attempt in range(1, max_retries + 1):
        try:
            if not commented:
                pull_request.create_issue_comment(CLOSING_COMMENT)
                commented = True
            pull_request.edit(state="closed")
            print(f"  Closed PR #{pull_request.number} (@{author})")
            return True
        except Exception as exc:
            if attempt < max_retries:
                wait = 2 ** attempt  # 2s, 4s
                print(
                    f"  WARN: Closing attempt {attempt}/{max_retries} failed "
                    f"for PR #{pull_request.number}: {exc}. "
                    f"Retrying in {wait}s..."
                )
                time.sleep(wait)
            else:
                print(
                    f"  ERROR: Failed to close PR #{pull_request.number} after "
                    f"{max_retries} attempts: {exc}"
                )
                return False


def get_runtime_thresholds() -> tuple[int, int]:
    """Return warning and closing thresholds, applying DAYS_THRESHOLD to both."""
    override = os.environ.get("DAYS_THRESHOLD")
    if override is None:
        return WARNING_THRESHOLD_DAYS, CLOSING_THRESHOLD_DAYS

    try:
        threshold = int(override)
    except ValueError:
        print(
            "ERROR: DAYS_THRESHOLD must be a non-negative integer, "
            f"got '{override}'"
        )
        sys.exit(1)

    if threshold < 0:
        print(
            "ERROR: DAYS_THRESHOLD must be a non-negative integer, "
            f"got '{override}'"
        )
        sys.exit(1)

    return threshold, threshold


def main() -> None:
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        print("ERROR: GITHUB_TOKEN environment variable is required")
        sys.exit(1)

    repository = os.environ.get("GITHUB_REPOSITORY")
    if not repository:
        print("ERROR: GITHUB_REPOSITORY environment variable is required")
        sys.exit(1)

    warning_threshold_days, closing_threshold_days = get_runtime_thresholds()
    dry_run = os.environ.get("DRY_RUN", "false").lower() == "true"

    if dry_run:
        print("Running in DRY RUN mode — no comments, labels, or closures will be applied.\n")

    g = Github(auth=Auth.Token(token))
    repo = g.get_repo(repository)

    print("Fetching maintainers...")
    maintainers = get_maintainers(repo)
    print(f"Found {len(maintainers)} maintainers.\n")
    for maintainer in sorted(maintainers):
        print(f"  @{maintainer}")

    now = datetime.now(timezone.utc)
    warned = []
    closed = []
    failed = []
    scanned = 0

    print(
        "Scanning open pull requests "
        f"(warning: {warning_threshold_days} days, "
        f"closing: {closing_threshold_days} days)...\n"
    )

    for pull_request in repo.get_pulls(state="open"):
        scanned += 1

        if should_close(
            pull_request,
            maintainers,
            now,
            closing_threshold_days,
        ):
            if close(pull_request, dry_run):
                closed.append(pull_request.number)
            else:
                failed.append(pull_request.number)
            continue

        if should_warn(
            pull_request,
            maintainers,
            now,
            warning_threshold_days,
        ):
            if warn(
                pull_request,
                dry_run,
                closing_threshold_days,
            ):
                warned.append(pull_request.number)
            else:
                failed.append(pull_request.number)
            continue

    print(
        f"\nDone. Scanned {scanned} PRs, warned {len(warned)}, "
        f"closed {len(closed)}, failed {len(failed)}."
    )
    if warned:
        print(f"Warned: {', '.join(f'#{n}' for n in warned)}")
    if closed:
        print(f"Closed: {', '.join(f'#{n}' for n in closed)}")
    if failed:
        print(f"Failed: {', '.join(f'#{n}' for n in failed)}")
        sys.exit(1)


if __name__ == "__main__":
    main()
