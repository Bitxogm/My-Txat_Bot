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
    # v2: personalities (ADR-013). Conversations keep a snapshot of the personality they were
    # created with; old conversations get NULL/'' (base layer only, model defaults).
    """
    CREATE TABLE personalities (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        icon TEXT NOT NULL,
        description TEXT NOT NULL DEFAULT '',
        system_prompt TEXT NOT NULL,
        temperature REAL,
        top_p REAL,
        num_ctx INTEGER,
        default_model TEXT,
        builtin INTEGER NOT NULL DEFAULT 0 CHECK (builtin IN (0, 1)),
        position INTEGER NOT NULL DEFAULT 1000,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    );
    ALTER TABLE conversations ADD COLUMN personality_id TEXT
        REFERENCES personalities (id) ON DELETE SET NULL;
    ALTER TABLE conversations ADD COLUMN personality_name TEXT;
    ALTER TABLE conversations ADD COLUMN personality_icon TEXT;
    ALTER TABLE conversations ADD COLUMN system_prompt TEXT NOT NULL DEFAULT '';
    ALTER TABLE conversations ADD COLUMN temperature REAL;
    ALTER TABLE conversations ADD COLUMN top_p REAL;
    ALTER TABLE conversations ADD COLUMN num_ctx INTEGER;
    """,
    # v3: OSINT source catalog (ADR-014). The category is validated in code (domain/osint.py)
    # so adding one doesn't need a migration.
    """
    CREATE TABLE osint_sources (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        url TEXT NOT NULL,
        category TEXT NOT NULL,
        description TEXT NOT NULL DEFAULT '',
        requires_api_key INTEGER NOT NULL DEFAULT 0 CHECK (requires_api_key IN (0, 1)),
        requires_payment INTEGER NOT NULL DEFAULT 0 CHECK (requires_payment IN (0, 1)),
        builtin INTEGER NOT NULL DEFAULT 0 CHECK (builtin IN (0, 1)),
        is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),
        position INTEGER NOT NULL DEFAULT 1000,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    );
    CREATE INDEX idx_osint_sources_category ON osint_sources (category);
    """,
    # v4: file attachments (ADR-015). The bytes live in data/uploads under storage_key; the
    # extracted text is kept here. message_id is NULL until the file is sent with a message.
    """
    CREATE TABLE attachments (
        id TEXT PRIMARY KEY,
        conversation_id TEXT NOT NULL REFERENCES conversations (id) ON DELETE CASCADE,
        message_id INTEGER REFERENCES messages (id) ON DELETE CASCADE,
        filename TEXT NOT NULL,
        mime TEXT NOT NULL,
        kind TEXT NOT NULL,
        size_bytes INTEGER NOT NULL,
        sha256 TEXT NOT NULL,
        storage_key TEXT NOT NULL UNIQUE,
        text TEXT NOT NULL DEFAULT '',
        truncated INTEGER NOT NULL DEFAULT 0 CHECK (truncated IN (0, 1)),
        created_at TEXT NOT NULL
    );
    CREATE INDEX idx_attachments_conversation ON attachments (conversation_id);
    CREATE INDEX idx_attachments_message ON attachments (message_id);
    """,
    # v5: ratings of the assistant's replies (ADR-024). Each reply now records the model, its
    # provider and the base layer fingerprint it was generated with (NULL on older replies and
    # on user messages). A rating keeps a copy of the turn as it was when rated.
    """
    ALTER TABLE messages ADD COLUMN model TEXT;
    ALTER TABLE messages ADD COLUMN provider TEXT;
    ALTER TABLE messages ADD COLUMN base_prompt_version TEXT;
    CREATE TABLE message_feedback (
        id TEXT PRIMARY KEY,
        message_id INTEGER NOT NULL UNIQUE REFERENCES messages (id) ON DELETE CASCADE,
        conversation_id TEXT NOT NULL REFERENCES conversations (id) ON DELETE CASCADE,
        rating INTEGER NOT NULL CHECK (rating IN (-1, 1)),
        reasons TEXT NOT NULL DEFAULT '[]' CHECK (json_valid(reasons)),
        correction TEXT,
        question TEXT NOT NULL,
        question_files TEXT NOT NULL DEFAULT '[]' CHECK (json_valid(question_files)),
        answer TEXT NOT NULL,
        model TEXT NOT NULL,
        model_approximate INTEGER NOT NULL DEFAULT 0 CHECK (model_approximate IN (0, 1)),
        provider TEXT,
        personality_id TEXT,
        personality_name TEXT,
        base_prompt_version TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    );
    CREATE INDEX idx_feedback_conversation ON message_feedback (conversation_id);
    CREATE INDEX idx_feedback_created ON message_feedback (created_at DESC);
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
