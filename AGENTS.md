# Repository Guidelines

## Project Structure & Module Organization

The application lives in `Contribution Graph/`. `contribution_engine.py` defines models, validation, and scoring; `contribution_store.py` handles SQLite persistence and the CLI. `dashboard_server.py` exposes the FastAPI service and serves `dashboard/` (`index.html`, `app.js`, `style.css`). `demo_workflow.py` and `seed_dashboard.py` create example data. Tests are adjacent `test_*.py` files. The repository root contains project notes and source documents.

## Build, Test, and Development Commands

Run these commands from `Contribution Graph/`. The browser code has no build step; the server needs the packages in `requirements.txt`.

```sh
python3 -m venv .venv                              # Create an isolated Python environment
.venv/bin/python -m pip install -r requirements.txt # Install server and test dependencies
.venv/bin/python -m unittest discover -s . -p 'test_*.py' # Run all tests
.venv/bin/python demo_workflow.py                   # Exercise the workflow with temporary data
.venv/bin/python dashboard_server.py                # Serve at http://127.0.0.1:8000
```

The server and CLI read the same `data.sqlite3` by default. The website uses port 8000. If the database is absent, run `python3 import_json.py data.json data.sqlite3`; after changing data, run `python3 export_json.py` to refresh the portable snapshot. Use temporary files for workflow examples.

## Coding Style & Naming Conventions

Follow the existing Python style: four-space indentation, `snake_case` for functions and files, `PascalCase` for classes, and uppercase enum values such as `PENDING`. Keep scoring in the engine, persistence and state changes in the store, and browser rendering in `dashboard/app.js`. JavaScript uses two-space indentation and `camelCase`. No formatter or linter is configured; match nearby code.

## Testing Guidelines

Tests use the standard-library `unittest` framework. Name new files `test_*.py` and methods `test_*`. Add focused cases for scoring, invalid input, persistence, and status transitions when changing those behaviors. Use temporary files for write tests, then run the full test command and `demo_workflow.py` before submitting.

## Commit & Pull Request Guidelines

The short Git history uses brief imperative subjects, such as `Add Contribution Graph project`; there is no documented prefix convention. Keep commits focused and describe the change in one line. Pull requests should explain the behavior changed, identify the tests run, and include a dashboard screenshot for visible UI changes. Link an issue when one exists. Avoid committing generated caches, local JSON experiments, or office lock files; `.gitignore` already excludes Python caches and `~$*` files.
