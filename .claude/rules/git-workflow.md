# Git workflow (applies everywhere)

- **All work happens on `main`.** No feature branches, no PRs, no worktrees. Keep `main` deployable: run the full verification (tests, lint, format, evals if LLM behavior changed) before every commit.
- Conventional commits: `feat(rules): flag paystubs older than 30 days`. Small commits, one concern each.
- Only commit or push when the human asks.
- **Parallel agents:** run them one area at a time on `main` (e.g. backend/rules, then frontend), never two agents editing the same files at once. Re-run the full verification after each.
- Commit message body for non-trivial changes: the outcome it moves (O1–O6), what changed, and how it was verified.
- Record which agent did what in `docs/BUILD_LOG.md` (`/build-log`).
