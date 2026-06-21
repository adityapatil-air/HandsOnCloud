import os
import sqlite3
import time
import threading

import psycopg2
import psycopg2.pool
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv

load_dotenv()

DB_ENGINE = os.getenv("DB_ENGINE", "sqlite").lower()
BASE_DIR = os.path.dirname(__file__)
SQLITE_DB_PATH = os.path.join(BASE_DIR, "cloudproof.db")
SQLITE_INITIALIZED = False

# PostgreSQL connection pool (created lazily)
_pg_pool = None
_pg_pool_lock = threading.Lock()
_sqlite_init_lock = threading.Lock()


SQLITE_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE,
    name TEXT NOT NULL,
    email TEXT UNIQUE NOT NULL,
    password_hash TEXT,
    email_verified INTEGER DEFAULT 0,
    oauth_provider TEXT,
    oauth_id TEXT,
    role_arn TEXT,
    s3_bucket TEXT,
    s3_prefix TEXT DEFAULT '',
    aws_region TEXT DEFAULT 'us-east-1',
    sync_pin_hash TEXT,
    aws_access_key_encrypted TEXT,
    aws_secret_key_encrypted TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS email_verification_tokens (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    token TEXT UNIQUE NOT NULL,
    expires_at TIMESTAMP NOT NULL,
    used INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS password_reset_tokens (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    token TEXT UNIQUE NOT NULL,
    expires_at TIMESTAMP NOT NULL,
    used INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS activity_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    date DATE NOT NULL,
    service TEXT NOT NULL,
    action TEXT NOT NULL,
    score INTEGER NOT NULL,
    event_id TEXT,
    timestamp TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
    UNIQUE(user_id, event_id)
);

CREATE TABLE IF NOT EXISTS daily_scores (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    date DATE NOT NULL,
    total_score INTEGER NOT NULL,
    UNIQUE(user_id, date),
    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS processing_state (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    last_processed_timestamp TIMESTAMP NOT NULL,
    UNIQUE(user_id),
    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS resource_state (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    resource_type TEXT NOT NULL,
    resource_id TEXT NOT NULL,
    parent_resource_id TEXT,
    state TEXT NOT NULL,
    metadata TEXT,
    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, resource_type, resource_id),
    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_activity_logs_user_date
    ON activity_logs(user_id, date);

CREATE INDEX IF NOT EXISTS idx_daily_scores_user_date
    ON daily_scores(user_id, date);

CREATE INDEX IF NOT EXISTS idx_resource_state_user
    ON resource_state(user_id, resource_type, state);
"""


def get_db_connection(retries=3):
    if DB_ENGINE == "sqlite":
        return _get_sqlite_connection()
    else:
        return _get_postgres_connection(retries=retries)


def _get_postgres_connection(retries=3):
    global _pg_pool
    if _pg_pool is None:
        with _pg_pool_lock:
            if _pg_pool is None:
                _pg_pool = psycopg2.pool.ThreadedConnectionPool(
                    minconn=1,
                    maxconn=5,
                    host=os.getenv("DB_HOST", "localhost"),
                    port=os.getenv("DB_PORT", "5432"),
                    database=os.getenv("DB_NAME", "cloudproof"),
                    user=os.getenv("DB_USER", "postgres"),
                    password=os.getenv("DB_PASSWORD", "postgres"),
                    connect_timeout=10,
                )
    for attempt in range(retries):
        try:
            return _pg_pool.getconn()
        except psycopg2.OperationalError as e:
            if attempt < retries - 1:
                time.sleep(2)
                continue
            raise Exception(f"Database connection failed after {retries} attempts: {str(e)}")


def _get_sqlite_connection():
    """Return a SQLite connection with WAL mode for better concurrent reads."""
    global SQLITE_INITIALIZED

    conn = sqlite3.connect(
        SQLITE_DB_PATH,
        detect_types=sqlite3.PARSE_DECLTYPES | sqlite3.PARSE_COLNAMES,
        check_same_thread=False,
    )
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA synchronous = NORMAL;")
    conn.execute("PRAGMA cache_size = -32000;")  # 32 MB cache

    if not SQLITE_INITIALIZED:
        with _sqlite_init_lock:
            if not SQLITE_INITIALIZED:
                _init_sqlite_schema(conn)
                SQLITE_INITIALIZED = True

    return conn


def _init_sqlite_schema(conn: sqlite3.Connection):
    """Create all required tables if they do not already exist, then migrate."""
    conn.executescript(SQLITE_SCHEMA)
    conn.commit()
    _migrate_sqlite(conn)


def _migrate_sqlite(conn: sqlite3.Connection):
    """Add columns introduced in later versions to existing SQLite databases."""
    new_columns = [
        "ALTER TABLE users ADD COLUMN username TEXT",
        "ALTER TABLE users ADD COLUMN password_hash TEXT",
        "ALTER TABLE users ADD COLUMN email_verified INTEGER DEFAULT 0",
        "ALTER TABLE users ADD COLUMN oauth_provider TEXT",
        "ALTER TABLE users ADD COLUMN oauth_id TEXT",
        "ALTER TABLE users ADD COLUMN s3_bucket TEXT",
        "ALTER TABLE users ADD COLUMN s3_prefix TEXT DEFAULT ''",
        "ALTER TABLE users ADD COLUMN aws_region TEXT DEFAULT 'us-east-1'",
        "ALTER TABLE users ADD COLUMN sync_pin_hash TEXT",
        "ALTER TABLE users ADD COLUMN aws_access_key_encrypted TEXT",
        "ALTER TABLE users ADD COLUMN aws_secret_key_encrypted TEXT",
        "ALTER TABLE users ADD COLUMN aws_account_id TEXT",
        "ALTER TABLE users ADD COLUMN aws_user_arn TEXT",
        "ALTER TABLE users ADD COLUMN last_auto_synced_at TIMESTAMP",
        "ALTER TABLE activity_logs ADD COLUMN event_id TEXT",
    ]
    for sql in new_columns:
        try:
            conn.execute(sql)
            conn.commit()
        except Exception:
            pass  # Column already exists — safe to ignore

    # Add unique index for event_id dedup (CREATE INDEX IF NOT EXISTS is safe to re-run)
    try:
        conn.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_activity_logs_event_id "
            "ON activity_logs(user_id, event_id) WHERE event_id IS NOT NULL"
        )
        conn.commit()
    except Exception:
        pass


def _convert_sqlite_placeholders(query, params):
    """
    Convert psycopg2-style %s placeholders to SQLite ? placeholders.
    """
    if params is None:
        return query, None

    if "%s" in query:
        query = query.replace("%s", "?")

    # Ensure params is a sequence type that SQLite understands
    if not isinstance(params, (list, tuple)):
        params = [params]

    return query, params


def execute_query(query, params=None, fetch=False):
    conn = None
    cursor = None
    is_pooled = DB_ENGINE != 'sqlite'
    try:
        conn = get_db_connection()

        if DB_ENGINE == "sqlite":
            query, params = _convert_sqlite_placeholders(query, params)
            cursor = conn.cursor()
            cursor.execute(query, params or [])
            if fetch:
                rows = cursor.fetchall()
                result = [dict(row) for row in rows]
            else:
                result = None
        else:
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            cursor.execute(query, params)
            result = cursor.fetchall() if fetch else None

        conn.commit()
        return result
    except Exception as e:
        if conn:
            conn.rollback()
        raise Exception(f"Query execution failed: {str(e)}")
    finally:
        if cursor:
            cursor.close()
        if conn:
            if is_pooled and _pg_pool:
                _pg_pool.putconn(conn)  # return to pool instead of closing
            else:
                conn.close()
