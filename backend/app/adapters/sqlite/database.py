import logging
from pathlib import Path

import aiosqlite

logger = logging.getLogger(__name__)

# Append-only: each entry upgrades the schema by one version (PRAGMA user_version).
MIGRATIONS: list[str] = [
    """
    CREATE TABLE conversations (
        id TEXT PRIMARY KEY,
        title TEXT NOT NULL,
        model TEXT NOT NULL,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    );
    CREATE INDEX idx_conversations_updated ON conversations (updated_at DESC);
    CREATE TABLE messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        conversation_id TEXT NOT NULL REFERENCES conversations (id) ON DELETE CASCADE,
        role TEXT NOT NULL CHECK (role IN ('system', 'user', 'assistant')),
        content TEXT NOT NULL,
        status TEXT NOT NULL CHECK (status IN ('done', 'stopped', 'error')),
        created_at TEXT NOT NULL
    );
    CREATE INDEX idx_messages_conversation ON messages (conversation_id, id);
    """,
]


def sqlite_path(database_url: str) -> str:
    """sqlite:///relative/path.db or sqlite:////absolute/path.db -> filesystem path."""
    prefix = "sqlite:///"
    if not database_url.startswith(prefix):
        raise ValueError("DATABASE_URL must start with sqlite:///")
    path = database_url.removeprefix(prefix)
    if not path:
        raise ValueError("DATABASE_URL has no file path")
    return path


async def connect(path: str) -> aiosqlite.Connection:
    if path != ":memory:":
        Path(path).parent.mkdir(parents=True, exist_ok=True)
    db = await aiosqlite.connect(path)
    db.row_factory = aiosqlite.Row
    await db.execute("PRAGMA foreign_keys = ON")
    await db.execute("PRAGMA journal_mode = WAL")
    await migrate(db)
    return db


async def migrate(db: aiosqlite.Connection) -> None:
    async with db.execute("PRAGMA user_version") as cursor:
        row = await cursor.fetchone()
    current = int(row[0]) if row else 0
    for version, sql in enumerate(MIGRATIONS[current:], start=current + 1):
        logger.info("Applying database migration %d", version)
        await db.executescript(f"BEGIN;\n{sql}\nPRAGMA user_version = {version};\nCOMMIT;")
