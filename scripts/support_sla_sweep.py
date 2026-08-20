"""Support ticket housekeeping — run periodically via an external OS-level scheduler (cron /
Windows Task Scheduler); this backend has no in-process job scheduler.

Usage:
    python scripts/support_sla_sweep.py

Auto-closes resolved tickets past the configured reopen window and notifies assignees of
tickets whose SLA has been breached while still open/in_progress.
"""
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

from app.core.database import SessionLocal
from app.services.support.support_service import SupportService


def main():
    db = SessionLocal()
    try:
        result = SupportService(db).run_sla_sweep()
        print(f"Auto-closed {result['auto_closed']} tickets; {result['sla_breached_open']} open tickets are SLA-breached.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
