# Branch Safety

## Core Rules

1. **Never switch branches in a worktree.** Your worktree is checked out on a specific branch. Switching would corrupt the isolation model.

2. **Never touch the main checkout.** Your worktree is a copy. The main checkout is the operator's working tree. Writing to it from a worker is a data-corruption risk.

3. **All commits go to YOUR branch.** The branch name is in the worktree directory name or the brief header. Commit there and nowhere else.

4. **Use absolute paths.** Workers resolve relative paths against the main checkout root, not the worktree CWD. Always use absolute paths or `$(pwd)/` in your commands.

## Multi-session Safety

Multiple workers may run concurrently in separate worktrees. Each has its own branch. Merge conflicts are resolved by the operator after workers complete, not by workers during execution.

## What To Do If You See Unfamiliar State

- Unfamiliar files in the worktree: investigate before modifying. They may be the operator's in-progress work.
- Lock files: check what process holds them rather than deleting.
- Merge conflicts: report them in your status output. Do not force-resolve.

## Commit Discipline

- Use Conventional Commits format: `feat:`, `fix:`, `docs:`, `refactor:`, `test:`, `chore:`
- One logical change per commit
- Never amend commits that may have been pushed
- Never force-push
