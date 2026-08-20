"""Shared sequential display-code generator — every entity's human-readable ID (RFQ001,
PR001, WH001, ...) is `{prefix}{zero-padded number}`, based on the highest existing numeric
suffix rather than a row count, so a deleted row can never cause a duplicate code.
"""
from sqlalchemy import select
from sqlalchemy.orm import InstrumentedAttribute, Session


def next_sequential_code(session: Session, column: InstrumentedAttribute, prefix: str, width: int = 3) -> str:
    existing = session.scalars(select(column).where(column.op("~")(rf"^{prefix}[0-9]+$"))).all()
    next_num = max((int(c[len(prefix):]) for c in existing), default=0) + 1
    return f"{prefix}{next_num:0{width}d}"
