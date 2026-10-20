"""SQLite connection, migrations and canonical encoding for the experiment store.

The store is `experiments.sqlite3` at the repository root (gitignored); schema
migrations live in `migrations/` and are applied in order, each once, inside a
transaction. Every connection uses WAL, foreign keys and a busy timeout so
several local processes can write safely.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import math
import sqlite3
from contextlib import contextmanager
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
DEFAULT_DB = REPO / "experiments.sqlite3"
MIGRATIONS = Path(__file__).resolve().parent / "migrations"
BUSY_TIMEOUT_MS = 30_000


def now() -> str:
    return dt.datetime.now().astimezone().isoformat(timespec="seconds")


def canonical(obj) -> str:
    """Deterministic JSON: sorted keys, no whitespace, floats as Python repr."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), allow_nan=False)


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def sha256_file(path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def value_type(v) -> str:
    if v is None:
        return "null"
    if isinstance(v, bool):
        return "bool"
    if isinstance(v, int):
        return "int"
    if isinstance(v, float):
        if not math.isfinite(v):
            raise ValueError(f"non-finite value {v!r} cannot be stored")
        return "float"
    if isinstance(v, str):
        return "str"
    if isinstance(v, (list, tuple)):
        return "list"
    if isinstance(v, dict):
        return "object"
    raise TypeError(f"unsupported parameter value {v!r}")


def stable_id(prefix: str, *parts: str) -> str:
    return f"{prefix}-{sha256_text(chr(31).join(parts))[:16]}"


def connect(path=None) -> sqlite3.Connection:
    """Open (and migrate) the store. Autocommit mode; use `transaction()`."""
    path = Path(path or DEFAULT_DB)
    con = sqlite3.connect(str(path), timeout=BUSY_TIMEOUT_MS / 1000, isolation_level=None)
    con.row_factory = sqlite3.Row
    con.execute(f"PRAGMA busy_timeout = {BUSY_TIMEOUT_MS}")
    con.execute("PRAGMA foreign_keys = ON")
    mode = con.execute("PRAGMA journal_mode = WAL").fetchone()[0]
    if mode.lower() != "wal":
        raise RuntimeError(f"could not enable WAL on {path} (got {mode})")
    migrate(con)
    return con


@contextmanager
def transaction(con: sqlite3.Connection):
    """BEGIN IMMEDIATE: takes the write lock up front, so concurrent writers
    queue on the busy timeout instead of failing mid-transaction."""
    con.execute("BEGIN IMMEDIATE")
    try:
        yield con
    except BaseException:
        con.execute("ROLLBACK")
        raise
    else:
        con.execute("COMMIT")


def migrate(con: sqlite3.Connection) -> list[str]:
    con.execute("CREATE TABLE IF NOT EXISTS schema_migrations (version INTEGER PRIMARY KEY, name TEXT NOT NULL, "
                "sha256 TEXT NOT NULL, applied_at TEXT NOT NULL)")
    applied = {r["version"]: r for r in con.execute("SELECT * FROM schema_migrations")}
    done = []
    for f in sorted(MIGRATIONS.glob("[0-9][0-9][0-9][0-9]_*.sql")):
        version = int(f.name[:4])
        text = f.read_text()
        digest = sha256_text(text)
        if version in applied:
            if applied[version]["sha256"] != digest:
                raise RuntimeError(f"migration {f.name} changed after it was applied; add a new migration instead")
            continue
        with transaction(con):
            if con.execute("SELECT 1 FROM schema_migrations WHERE version = ?", (version,)).fetchone():
                continue  # another process applied it while we waited for the lock
            for statement in _statements(text):
                con.execute(statement)
            con.execute("INSERT INTO schema_migrations VALUES (?, ?, ?, ?)", (version, f.name, digest, now()))
        done.append(f.name)
    return done


def _statements(sql: str) -> list[str]:
    """Split a migration into statements (triggers contain inner semicolons)."""
    out, buf = [], []
    for line in sql.splitlines():
        if line.strip().startswith("--") or not line.strip():
            continue
        buf.append(line)
        joined = "\n".join(buf)
        if sqlite3.complete_statement(joined):
            out.append(joined)
            buf = []
    if buf and "\n".join(buf).strip():
        raise ValueError("incomplete SQL statement at the end of a migration")
    return out
