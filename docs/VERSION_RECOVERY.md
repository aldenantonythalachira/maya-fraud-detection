# Version recovery

Validated stages use feature branches, ordinary commits, annotated `maya/*` tags
and pull requests. Main is never force-pushed. List versions:

```powershell
.\.venv\Scripts\python.exe scripts/versions.py list
```

Return to a checkpoint without deleting newer versions:

```powershell
.\.venv\Scripts\python.exe scripts/versions.py restore maya/01-payment-review
```

The command requires a clean working tree and creates a new `restore/*` branch.
It refuses dirty work rather than discarding it. If the branch already exists,
use `git switch` to select it. To return, switch to your original feature branch.
For published changes that must be undone on a shared branch, use a new branch
and `git revert <commit>` followed by a reviewed PR; do not rewrite history.

Create your own checkpoint after committing:

```powershell
.\.venv\Scripts\python.exe scripts/versions.py save my-working-version
git push origin maya/my-working-version
```

Checkpoints restore tracked source only. Datasets, trained model JSON, virtual
environments and SQLite databases are ignored. Stop the server before backing
up an existing database; copy the complete database and its WAL/SHM files if
present. Keep copies in a separately named local backup directory. Use a new
database filename when running older code; never run old code against a newer
schema without checking compatibility. Model rebuild commands are in README.md.
Reinstall the checkpoint's dependencies before starting an older version.

Release checkpoints are published alongside their feature branch. The running
logs record which tests passed and which features each checkpoint contains.
