"""Clear all stored cases (tickets, agent logs, decisions, incidents) before a demo.
A timestamped backup of the database is made first.      py demo/reset_db.py"""
import shutil
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from backend import config  # noqa: E402

db = config.DB_PATH
if not db.exists():
    print("No database yet, nothing to clear.")
    raise SystemExit
backup = db.with_name(f"uniresolve_backup_{datetime.now():%H%M%S}.db")
shutil.copy2(db, backup)
c = sqlite3.connect(db)
tables = [r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
for t in tables:
    n = c.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
    c.execute(f"DELETE FROM {t}")
    print(f"cleared {t}: {n} rows")
c.commit()
c.execute("VACUUM")
c.close()
print(f"Done. Backup saved as {backup.name} (copy it back over uniresolve.db to restore).")
