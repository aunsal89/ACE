# Autonomous Career Engine (ACE) — Contributing & Git Workflow Guidelines

Welcome to the **Autonomous Career Engine (ACE)** repository! This document establishes the official development standards, branching strategies, Pull Request (PR) lifecycle, and conflict resolution protocols for both repository administrators and contributors.

---

## 1. Golden Rules & Architectural Invariants

1. **Strict `main` Branch Protection:**
   - Direct pushes to `main` are **strictly prohibited** by policy.
   - All code additions, bug fixes, refactors, and documentation updates must be developed on a dedicated feature or bugfix branch, pushed to GitHub, and merged exclusively via Pull Requests (PRs).
2. **Deterministic & Isolated Data Files:**
   - **Never commit secret `.env` files, local SQLite databases (`data/*.db`), user tenant profiles (`config/tenants/`), or generated application dossiers (`inbox/`)**.
   - Fonts in `data/fonts/` are dynamically downloaded on-demand by `src/utils/pdf.py` (`ensure_unicode_fonts()`) across Linux, macOS, and Windows. Do not commit binary font files to git.
3. **Mandatory Verification Prior to PR:**
   - Every branch must pass all unit and integration tests (`pytest`) before opening or merging a PR.
   - For Linux host `vsmlnx`, all CLI commands and test suites must run using the official environment interpreter: `/home/nsl/miniconda3/envs/lnxenv/bin/python`.

---

## 2. Branching Strategy & Naming Conventions

Always branch directly from an up-to-date `main`. Use descriptive, hyphen-separated or slash-separated branch names adhering to standard semantic prefixes:

| Prefix | Usage | Example |
| :--- | :--- | :--- |
| `feat/` or `feature-` | New functionality, scraper additions, LLM integrations | `feat/linkedin-apify-pagination` |
| `fix/` or `fix-` | Bug fixes, syntax corrections, runtime exception fixes | `fix/pdf-unicode-fonts` |
| `refactor/` | Structural code improvements without changing behavior | `refactor/unify-preferences` |
| `docs/` | Documentation, architectural references, guides | `docs/git-workflow-guidelines` |
| `test/` | Adding test suites, mock fixtures, CI enhancements | `test/scoring-engine-matrix` |

---

## 3. End-to-End Contributor Workflow

### Step 1: Synchronize Local `main`
Before starting any new task, ensure your local `main` matches `origin/main` exactly:
```bash
git checkout main
git pull origin main
```

### Step 2: Create a Feature Branch
```bash
git checkout -b feat/add-baykar-filter
```

### Step 3: Implement Changes & Run Smoke Tests
Make your code changes, then execute the full test suite and a dry-run pipeline smoke test:
```bash
# 1. Run full test suite (34+ unit and integration tests)
pytest

# Or on vsmlnx using the explicit Python binary:
/home/nsl/miniconda3/envs/lnxenv/bin/python -m pytest

# 2. Run pipeline smoke test in dry-run mode
python run.py pipeline --dry-run
```

### Step 4: Make Atomic, Semantic Commits
Group related changes into logical commits with conventional commit messages (`feat:`, `fix:`, `docs:`, `refactor:`, `test:`, `chore:`):
```bash
git status
git add src/sourcing/defense/baykar.py tests/test_sourcing.py
git commit -m "feat(sourcing): enhance Baykar scraper keyword filtering for powertrain roles"
```

### Step 5: Push Branch to Remote
```bash
git push -u origin feat/add-baykar-filter
```

### Step 6: Open a Pull Request (PR)
You can open a PR via the GitHub Web UI or directly from your terminal using GitHub CLI (`gh`):

```bash
gh pr create \
  --title "feat(sourcing): enhance Baykar scraper keyword filtering" \
  --body "## Summary
- Added powertrain and inverter keyword extraction to Baykar scraper.
- Updated mock test fixtures in tests/test_sourcing.py.
- Verified all unit tests pass with pytest in lnxenv." \
  --head feat/add-baykar-filter \
  --base main
```

---

## 4. Pull Request Review & Merge Protocols (For Admins & Authors)

### PR Review Checklist
Before approving and merging any PR, verify:
- [ ] Automated tests / CI checks pass with 0 failures.
- [ ] No git-ignored files or credentials (`.env`, `*.db`, `inbox/*`, `data/fonts/*`) are included in the diff.
- [ ] `GEMINI.md` or `README.md` are updated if configuration keys or architectural rules changed.

### Merge Strategy
- **Squash and Merge (Recommended):** Condenses all commits from the feature branch into a single clean commit on `main`, preserving a clear, linear history.
- **Rebase and Merge:** Retains individual atomic commits on top of `main` without creating merge commits.
- **Merge Commit:** Avoid creating non-fast-forward merge commits unless integrating major long-lived milestone branches.

---

## 5. Handling Merge Conflicts & Divergent Branches

### Scenario A: Your Branch Conflicts with `main`
If changes were merged into `main` while you were working on your branch:

```bash
# 1. Fetch latest changes from origin
git fetch origin

# 2. Rebase your feature branch on top of origin/main
git checkout feat/your-feature
git rebase origin/main

# 3. If conflicts occur, git will pause and mark conflicting files.
# Open each conflicted file, look for <<<<<<< HEAD, resolve the conflict, and save.

# 4. Stage resolved files:
git add src/scoring/scorer.py

# 5. Continue the rebase:
git rebase --continue

# 6. Force-push your updated branch to your remote PR branch:
git push --force-with-lease origin feat/your-feature
```

### Scenario B: Local `main` Diverged After Remote PR Merge
If you merged a PR on GitHub (e.g., using "Squash and merge"), your local `main` may report:
`Your branch and 'origin/main' have diverged, and have 1 and 3 different commits each`.

To cleanly synchronize local `main` with the exact state of GitHub `main`:
```bash
git checkout main
git fetch origin
git reset --hard origin/main
```

---

## 6. Post-Merge Housekeeping: Cleaning Up Branches

Once a PR is merged into `main` on GitHub:

```bash
# 1. Switch to local main and pull merged changes
git checkout main
git pull origin main

# 2. Delete the local merged branch
git branch -d feat/add-baykar-filter

# If git complains that the branch is not fully merged (common with squash-merges):
git branch -D feat/add-baykar-filter

# 3. Prune obsolete remote-tracking branches from your local list
git fetch -p
```

---

## 7. Helpful Git Command Cheat Sheet

| Intent | Command |
| :--- | :--- |
| **Check current status & modified files** | `git status` |
| **View branch list (local + remote)** | `git branch -a` |
| **Switch to existing branch** | `git checkout <branch-name>` |
| **Create and switch to new branch** | `git checkout -b <new-branch-name>` |
| **Discard unstaged changes in a file** | `git restore <file>` |
| **Unstage a file while keeping changes** | `git restore --staged <file>` |
| **View concise commit history** | `git log --oneline -n 10` |
| **View graphical commit history tree** | `git log --graph --oneline --decorate -n 15` |
| **Temporarily stash working changes** | `git stash` |
| **Re-apply stashed changes** | `git stash pop` |
| **Clean untracked files safely (dry-run first)** | `git clean -nd` (check) -> `git clean -fd` (remove) |
