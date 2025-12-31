---
description: "Check current git state to avoid branch/commit confusion"
---

Run these git commands and report the current state clearly:

1. **Current branch**: `git branch --show-current`
2. **Upstream tracking**: `git rev-parse --abbrev-ref @{u}` (if set)
3. **Uncommitted changes**: `git status --short`
4. **Recent commits**: `git log --oneline -5`
5. **Ahead/behind remote**: `git status -sb` (first line)

## Report Format

```
=== Git State ===
Branch:   <branch-name>
Tracking: <remote/branch> or (none)
Status:   <clean | X uncommitted changes>

Recent commits:
  <hash> <message>
  <hash> <message>
  ...

Remote sync: <ahead X, behind Y | up to date | not tracking>
```

If there are uncommitted changes, list them.

This helps me avoid confusion about what branch we're on and what's been committed.
