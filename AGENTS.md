# Repository Guidelines

## Project Structure & Module Organization
- `src/`: core Python modules such as `gui.py`, `discord_client.py`, and `main.py`.
- `config/`: runtime configuration (`config.json`, `example_config.json`).
- `assets/`: UI assets; `logs/`: runtime logs and debug output.
- Top-level scripts: `run.py` (launch the app) and `build.py` plus `*.spec` (PyInstaller packaging).

## Build, Test, and Development Commands
- `pip install -r requirements.txt`: install Python dependencies.
- `python run.py`: start the desktop GUI locally.
- `python build.py --target windows` or `python build.py --target mac`: build platform packages with PyInstaller.

## Coding Style & Naming Conventions
Use Python 3 with 4-space indentation. Keep files, functions, and variables in `snake_case`, classes in `PascalCase`, and constants in `UPPER_SNAKE_CASE`. Keep GUI logic in `src/gui.py` or adjacent modules and avoid heavy work at import time. No formatter or linter is configured, so keep changes readable and consistent with surrounding code.

## Testing Guidelines
There is no automated test suite or coverage target in this repo. Validate changes manually by running `python run.py` and exercising Discord login and rule matching flows. If you add automated tests, place them in a new `tests/` directory and document the runner you choose.

## Commit & Pull Request Guidelines
Recent commits use short, lowercase messages like `update`, so there is no formal convention. For new work, use descriptive, imperative commit summaries (for example `add rule filter`). Pull requests should include a clear summary, steps to test, notes about config changes, and screenshots for GUI updates.

## Security & Configuration Tips
Treat Discord tokens as secrets; keep them in `config/config.json` and do not commit them. Use `config/example_config.json` for shareable defaults.
