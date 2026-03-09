# Rule: Python Virtual Environment

Any Python code in this repository MUST use a virtual environment at `.venv/`.

## Gate Check

Before running or modifying Python code, verify:

1. `.venv/` exists at the repo root
2. `.venv/` is in `.gitignore`
3. `.vscode/settings.json` has `python.defaultInterpreterPath` pointing to `.venv/bin/python3` (absolute path — `${workspaceFolder}` is not supported)

## If `.venv/` Does Not Exist

Create it immediately:

```bash
python3 -m venv .venv
```

Install dependencies from whichever exists:
```bash
.venv/bin/pip install -e ".[dev]"          # if pyproject.toml
.venv/bin/pip install -r requirements.txt  # if requirements.txt
```

## Never

- Install packages into the system Python
- Use `${workspaceFolder}` in `python.defaultInterpreterPath` (VS Code doesn't resolve it)
- Use Windows paths (`Scripts/python.exe`) on WSL/Linux
- Commit `.venv/` to git

## VS Code Integration

`python.defaultInterpreterPath` must be an absolute path:
```json
"python.defaultInterpreterPath": "/root/projects/REPO_NAME/.venv/bin/python3"
```
