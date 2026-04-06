import logging

from sensai.util.git import GitStatus

from ..constants import REPO_ROOT
from .shell import subprocess_check_output

log = logging.getLogger(__name__)


def get_git_status() -> GitStatus | None:
    try:
        cwd = REPO_ROOT
        commit_hash = subprocess_check_output(["git", "rev-parse", "HEAD"], cwd=cwd)
        unstaged = bool(subprocess_check_output(["git", "diff", "--name-only"], cwd=cwd))
        staged = bool(subprocess_check_output(["git", "diff", "--staged", "--name-only"], cwd=cwd))
        untracked = bool(subprocess_check_output(["git", "ls-files", "--others", "--exclude-standard"], cwd=cwd))
        return GitStatus(
            commit=commit_hash, has_unstaged_changes=unstaged, has_staged_uncommitted_changes=staged, has_untracked_files=untracked
        )
    except:
        return None
