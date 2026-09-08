"""
Cairn task runner — identical commands on Windows, macOS, and Linux.

Usage:
    uv run tasks.py <command>     (recommended — uses the project venv)
    python tasks.py <command>     (if your venv is already activated)

Run without arguments to list commands.
"""

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def sh(*cmd: str) -> None:
    print(f"$ {' '.join(cmd)}")
    subprocess.run(list(cmd), cwd=ROOT, check=True)


def py(*args: str) -> None:
    """Run a module with the *current* Python (venv-aware under `uv run`)."""
    sh(sys.executable, *args)


def cmd_install():
    sh("uv", "sync")


def cmd_db_up():
    sh("docker", "compose", "up", "-d")


def cmd_db_down():
    sh("docker", "compose", "down")


def cmd_init():
    py("-m", "scripts.reset_db")
    py("-m", "scripts.seed_dev")


def cmd_dev():
    py("-m", "uvicorn", "app.main:app", "--reload", "--port", "8000")


def cmd_test():
    py("-m", "pytest", "-q")


def cmd_fmt():
    if shutil.which("ruff"):
        sh("ruff", "format", ".")
    else:
        sh("uv", "run", "ruff", "format", ".")


def cmd_requirements():
    sh("uv", "export", "--all-groups", "--no-hashes", "-o", "requirements.txt")


def cmd_install_pip():
    py("-m", "pip", "install", "-r", "requirements.txt")


COMMANDS = {
    "install": (cmd_install, "uv sync — install dependencies"),
    "db-up": (cmd_db_up, "start Postgres + Adminer (Docker Desktop must be running)"),
    "db-down": (cmd_db_down, "stop containers"),
    "init": (cmd_init, "reset schema + seed placeholder data"),
    "dev": (cmd_dev, "run app with hot reload on http://localhost:8000"),
    "test": (cmd_test, "run smoke tests (needs db-up first)"),
    "fmt": (cmd_fmt, "ruff format"),
    "requirements": (cmd_requirements, "regenerate requirements.txt from uv.lock"),
    "install-pip": (cmd_install_pip, "pip install from requirements.txt"),
}


if __name__ == "__main__":
    if len(sys.argv) == 1:
        print(__doc__)
        print("Commands:")
        for name, (_, desc) in COMMANDS.items():
            print(f"  {name:15} {desc}")
        sys.exit(0)

    name = sys.argv[1]
    if name not in COMMANDS:
        print(f"Unknown command: {name}\n")
        print(__doc__)
        sys.exit(1)

    COMMANDS[name][0]()
