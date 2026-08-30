import psycopg2
import psycopg2.extras
from psycopg2 import pool as pg_pool
import os

_pool = None


def init_pool():
    """Create the connection pool once, on first use."""
    global _pool
    _pool = pg_pool.ThreadedConnectionPool(
        minconn=2,
        maxconn=20,
        host=os.environ.get('POSTGRES_HOST'),
        port=os.environ.get('POSTGRES_PORT', 5432),
        dbname=os.environ.get('POSTGRES_DB'),
        user=os.environ.get('POSTGRES_USER'),
        password=os.environ.get('POSTGRES_PASSWORD'),
        cursor_factory=psycopg2.extras.RealDictCursor
    )


class _PooledConnection:
    """Wraps a borrowed connection so every existing conn.close() call site
    across the app returns it to the pool instead of actually closing it.
    Everything else (cursor, commit, etc.) passes straight through unchanged."""
    def __init__(self, real_conn):
        self._real_conn = real_conn

    def cursor(self, *args, **kwargs):
        return self._real_conn.cursor(*args, **kwargs)

    def commit(self):
        self._real_conn.commit()

    def rollback(self):
        self._real_conn.rollback()

    def close(self):
        _pool.putconn(self._real_conn)


def get_db_connection():
    """Borrow a connection from the pool instead of opening a fresh one
    every call. Nothing else changes for callers -- conn.close() now
    returns the connection to the pool instead of tearing it down."""
    if _pool is None:
        init_pool()
    return _PooledConnection(_pool.getconn())


def init_donators_table():
    """Create the donators table if it doesn't already exist, and patch in any
    columns added after the table was first created. Safe to call every startup."""
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS donators (
            id SERIAL PRIMARY KEY,
            name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            profile_picture VARCHAR(255),
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)
    cur.execute("ALTER TABLE donators ADD COLUMN IF NOT EXISTS profile_picture VARCHAR(255)")
    conn.commit()
    cur.close()
    conn.close()


def get_donator_by_id(donator_id):
    """Fetch a donator by primary key — used by Flask-Login's user_loader."""
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT id, name, email FROM donators WHERE id = %s", (donator_id,))
    row = cur.fetchone()
    cur.close()
    conn.close()
    return row


def get_donator_by_email(email):
    """Fetch a donator (with password_hash) by email — used at login."""
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT id, name, email, password_hash FROM donators WHERE email = %s", (email,))
    row = cur.fetchone()
    cur.close()
    conn.close()
    return row


def init_forum_messages_table():
    """Create the forum_messages table if it doesn't already exist. Safe to call every startup."""
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS forum_messages (
            id SERIAL PRIMARY KEY,
            channel TEXT NOT NULL,
            sender_id TEXT NOT NULL,
            sender_name TEXT NOT NULL,
            message TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)
    conn.commit()
    cur.close()
    conn.close()


def get_channel_history(channel, limit=100):
    """Fetch the most recent messages for a channel, oldest first."""
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT id, channel, sender_id, sender_name, message, created_at
        FROM forum_messages
        WHERE channel = %s
        ORDER BY created_at DESC
        LIMIT %s
        """,
        (channel, limit)
    )
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return list(reversed(rows))


def save_channel_message(channel, sender_id, sender_name, message):
    """Insert a new chat message and return the saved row, including its real id/timestamp."""
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO forum_messages (channel, sender_id, sender_name, message)
        VALUES (%s, %s, %s, %s)
        RETURNING id, channel, sender_id, sender_name, message, created_at
        """,
        (channel, sender_id, sender_name, message)
    )
    row = cur.fetchone()
    conn.commit()
    cur.close()
    conn.close()
    return row


def get_forum_messages_for_moderation(channel=None, limit=200):
    """Fetch recent forum messages for admin review, optionally filtered to one channel."""
    conn = get_db_connection()
    cur = conn.cursor()
    if channel:
        cur.execute(
            """
            SELECT id, channel, sender_id, sender_name, message, created_at
            FROM forum_messages WHERE channel = %s
            ORDER BY created_at DESC LIMIT %s
            """,
            (channel, limit)
        )
    else:
        cur.execute(
            """
            SELECT id, channel, sender_id, sender_name, message, created_at
            FROM forum_messages ORDER BY created_at DESC LIMIT %s
            """,
            (limit,)
        )
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return rows


def delete_forum_message_by_id(message_id):
    """Delete a single forum message by id. Returns True if a row was actually removed."""
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM forum_messages WHERE id = %s", (message_id,))
    deleted = cur.rowcount > 0
    conn.commit()
    cur.close()
    conn.close()
    return deleted


def init_intro_threads_tables():
    """Create the intro thread/reply tables if they don't already exist. Safe to call every startup."""
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS intro_threads (
            id SERIAL PRIMARY KEY,
            donator_id INTEGER NOT NULL UNIQUE,
            author_name TEXT NOT NULL,
            title TEXT NOT NULL,
            body TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS intro_replies (
            id SERIAL PRIMARY KEY,
            thread_id INTEGER NOT NULL REFERENCES intro_threads(id) ON DELETE CASCADE,
            donator_id INTEGER NOT NULL,
            author_name TEXT NOT NULL,
            message TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)
    conn.commit()
    cur.close()
    conn.close()


def get_intro_threads(page=1, per_page=10):
    """Paginated list of intro threads, newest first, each with its reply count."""
    offset = (page - 1) * per_page
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) AS total FROM intro_threads")
    total = cur.fetchone()['total']
    cur.execute(
        """
        SELECT t.id, t.donator_id, t.author_name, t.title, t.body, t.created_at,
               COUNT(r.id) AS reply_count
        FROM intro_threads t
        LEFT JOIN intro_replies r ON r.thread_id = t.id
        GROUP BY t.id
        ORDER BY t.created_at DESC
        LIMIT %s OFFSET %s
        """,
        (per_page, offset)
    )
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return rows, total


def get_intro_thread_by_donator(donator_id):
    """Fetch the current donator's own intro thread, if they have one."""
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT id, donator_id, author_name, title, body, created_at FROM intro_threads WHERE donator_id = %s",
        (donator_id,)
    )
    row = cur.fetchone()
    cur.close()
    conn.close()
    return row


def upsert_intro_thread(donator_id, author_name, title, body):
    """Create the donator's intro thread, or overwrite it if they already have one."""
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO intro_threads (donator_id, author_name, title, body)
        VALUES (%s, %s, %s, %s)
        ON CONFLICT (donator_id)
        DO UPDATE SET author_name = EXCLUDED.author_name, title = EXCLUDED.title, body = EXCLUDED.body
        RETURNING id, donator_id, author_name, title, body, created_at
        """,
        (donator_id, author_name, title, body)
    )
    row = cur.fetchone()
    conn.commit()
    cur.close()
    conn.close()
    return row


def get_intro_thread_owner(thread_id):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT donator_id FROM intro_threads WHERE id = %s", (thread_id,))
    row = cur.fetchone()
    cur.close()
    conn.close()
    return row['donator_id'] if row else None


def delete_intro_thread_by_id(thread_id):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM intro_threads WHERE id = %s", (thread_id,))
    deleted = cur.rowcount > 0
    conn.commit()
    cur.close()
    conn.close()
    return deleted


def get_intro_replies(thread_id, page=1, per_page=10):
    """Paginated replies for one thread, oldest first (natural reading order)."""
    offset = (page - 1) * per_page
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) AS total FROM intro_replies WHERE thread_id = %s", (thread_id,))
    total = cur.fetchone()['total']
    cur.execute(
        """
        SELECT id, thread_id, donator_id, author_name, message, created_at
        FROM intro_replies WHERE thread_id = %s
        ORDER BY created_at ASC LIMIT %s OFFSET %s
        """,
        (thread_id, per_page, offset)
    )
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return rows, total


def add_intro_reply(thread_id, donator_id, author_name, message):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO intro_replies (thread_id, donator_id, author_name, message)
        VALUES (%s, %s, %s, %s)
        RETURNING id, thread_id, donator_id, author_name, message, created_at
        """,
        (thread_id, donator_id, author_name, message)
    )
    row = cur.fetchone()
    conn.commit()
    cur.close()
    conn.close()
    return row


def get_intro_reply_owner(reply_id):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT donator_id FROM intro_replies WHERE id = %s", (reply_id,))
    row = cur.fetchone()
    cur.close()
    conn.close()
    return row['donator_id'] if row else None


def delete_intro_reply_by_id(reply_id):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM intro_replies WHERE id = %s", (reply_id,))
    deleted = cur.rowcount > 0
    conn.commit()
    cur.close()
    conn.close()
    return deleted