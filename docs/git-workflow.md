# Git Workflow Guide

This project intentionally keeps the workflow lightweight so that changes stay traceable and easy to roll back.  
Use the steps below whenever you’re making updates.

---

## 1. Sync and Inspect

```bash
git pull            # update local repo
git status -sb      # check current changes / branch
git log --oneline   # optional: quick history glance
```

Staying on `main` is fine for small fixes. For larger work, create a short-lived feature branch:

```bash
git checkout -b fix/<topic>
```

---

## 2. Edit & Test

- Make the code changes.
- Run the relevant checks before committing:

  ```bash
  docker compose exec frontend npm run build
  docker compose exec backend alembic upgrade head  # when schema changes
  docker compose exec backend pytest                # if you add backend tests
  ```

  (Run only the checks that apply to your work.)

---

## 3. Review Changes

```bash
git status -sb
git diff           # review unstaged changes
git add <paths>    # stage files
git diff --cached  # review staged content
```

---

## 4. Commit

Use short commits that explain *what* changed:

```bash
git commit -m "Fix LaTeX collaboration seeding duplication"
```

If you’re working on a branch, keep pushing updates as you go:

```bash
git push -u origin <branch>   # first push for a branch
git push                      # subsequent pushes
```

---

## 5. Merge to Main

Once ready:

```bash
git checkout main
git pull --ff-only
git merge --ff-only <branch>
git push
```

*(If Git cannot fast-forward, rebase first: `git checkout <branch> && git rebase main`.)*

---

## 6. Reverting / Debugging

- Quick undo of last local commit (keep changes):

  ```bash
  git reset --soft HEAD~1
  ```

- Hard reset to a known commit (discard changes):

  ```bash
  git reset --hard <sha>
  git push --force-with-lease   # only if already pushed
  ```

- Revert a pushed commit (makes a new inverse commit):

  ```bash
  git revert <sha>
  git push
  ```

---

## 7. Common Troubleshooting

| Issue                                  | Fix                                                                 |
|---------------------------------------|---------------------------------------------------------------------|
| “Your branch is behind ‘origin/main’” | `git pull --ff-only`                                                |
| Merge conflict                        | Resolve files → `git add` → `git commit`                           |
| Force push needed                     | `git push --force-with-lease` (double-check before using)          |
| Want to compare two commits           | `git diff <sha1>..<sha2>`                                           |

---

## 8. Tips

- Avoid large “kitchen sink” commits; keep them focused so rollbacks stay simple.
- Document any breaking or notable changes in commit messages (and optionally in `CHANGELOG.md` if you’re maintaining one).
- If a feature needs collaboration or review, open a draft PR even if the team primarily merges via `main`. This keeps discussion tied to code.

---

This guide lives in `docs/git-workflow.md`. Update it whenever the team changes its conventions.  
Happy hacking! 🎯
