# Additional Usage Pointers

## Prompting Strategies

We found that it is often a good idea to spend some time conceptualizing and planning a task
before actually implementing it, especially for non-trivial tasks. 
For very complex tasks, you can make a detailed plan in one session, 
where Serena may read a lot of your code to build up the context,
and then continue with the implementation in another,
having persisted the plan in a memory or dedicated file.

## Serena and Git Worktrees

[git-worktree](https://git-scm.com/docs/git-worktree) can be an excellent way to parallelize your work. More on this in [Anthropic: Run parallel Claude Code sessions with Git worktrees](https://docs.claude.com/en/docs/claude-code/common-workflows#run-parallel-claude-code-sessions-with-git-worktrees).

Be sure to add the `.serena` folder to version control, such that your project-specific settings and memories are available across worktrees.

When you launch a CLI agent from inside a worktree using `--project-from-cwd`, Serena activates the worktree itself, even if the worktree lives under another Serena project (for example `<repo>/.claude/worktrees/<name>`, where Claude Code creates them natively). The nearest project boundary wins: the worktree's own `.git` pointer file takes precedence over an ancestor's `.serena/project.yml`, so file operations always resolve against the correct working tree.
