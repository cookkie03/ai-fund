"""SQLite database backup utility with online backup API and rotation."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from storage.office_db import OfficeDB


def create_db_backup(db: OfficeDB, backup_dir: Path | str = "data/backups", max_backups: int = 10) -> dict[str, Any]:
    bdir = Path(backup_dir)
    bdir.mkdir(parents=True, exist_ok=True)

    from datetime import UTC, datetime
    ts_str = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    name = f"backup_{ts_str}.db"
    dest = bdir / name

    # Online backup using sqlite3 backup API if file backed
    if db.path != Path(":memory:"):
        import sqlite3
        src_conn = sqlite3.connect(str(db.path))
        dest_conn = sqlite3.connect(str(dest))
        with dest_conn:
            src_conn.backup(dest_conn)
        src_conn.close()
        dest_conn.close()
    else:
        # fallback copy
        pass

    size_bytes = dest.stat().st_size if dest.is_file() else 0
    db.insert_backup_record(name, size_bytes)

    # Rotation: keep latest max_backups
    records = db.list_backup_records(limit=100)
    if len(records) > max_backups:
        to_delete = records[max_backups:]
        for rec in to_delete:
            old_file = bdir / rec["name"]
            try:
                old_file.unlink(missing_ok=True)
            except Exception:
                pass
            # Also clean record or let it be / delete from db if desired

    return {"name": name, "size_bytes": size_bytes}
