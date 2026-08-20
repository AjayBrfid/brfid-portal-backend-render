"""Run Alembic commands via `python scripts/run_alembic.py <args>` instead of a bare `alembic`
command, e.g.:

    python scripts\\run_alembic.py upgrade head
    python scripts\\run_alembic.py revision --autogenerate -m "add some_table"
    python scripts\\run_alembic.py downgrade -1

Two unrelated problems this works around (carried over from Backend-WH-Retail, one of the three
source projects, which hit both on this same machine):
1. This alembic version has no __main__.py, so `python -m alembic` doesn't work at all.
2. The project's own top-level "alembic/" folder (the migrations directory) shadows the real
   installed alembic package if the project root ends up at sys.path[0] - which happens for
   any script run *from* the project root. Running this file from scripts/ instead means
   sys.path[0] is scripts/, which has no alembic/ subfolder of its own, so the import below
   resolves to the real package. The project root is added back afterwards (not prepended)
   so `app.*` imports inside alembic/env.py still work.

This machine additionally has a Windows Application Control policy blocking standalone .exe
files (including alembic.exe/pip.exe) — always invoke via `python scripts\\run_alembic.py ...`,
never a bare `alembic` command.
"""

import sys
from pathlib import Path

import alembic.config  # must be imported before the project root is added to sys.path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.append(str(PROJECT_ROOT))

if __name__ == "__main__":
    alembic.config.main(argv=sys.argv[1:])
