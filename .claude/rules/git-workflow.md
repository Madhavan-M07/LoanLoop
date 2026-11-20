# Git & parallel-agent workflow (applies everywhere)

- `main` is always deployable. Work on `feat/<short-name>`, `fix/<short-name>`, `chore/<short-name>` branches and merge via PR with CI green.
- Conventional commits: `feat(rules): flag paystubs older than 30 days`. Small commits, one concern each.
- Only commit or push when the human asks.
- **Parallel agents:** each concurrent agent gets its own git worktree (`git worktree add ../loanloop-<task> -b feat/<task>`) and owns a non-overlapping area (e.g. backend/rules vs frontend). The integrator merges and runs the full verification.
- PR description: the outcome it moves (O1–O6), what changed, how it was verified (paste test/eval output), and risks.
- Record which agent did what in `docs/BUILD_LOG.md` (`/build-log`).
