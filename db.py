import psycopg2
import psycopg2.extras
from psycopg2 import pool as pg_pool
import os
import secrets

_pool = None


def init_pool():
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
    if _pool is None:
        init_pool()
    return _PooledConnection(_pool.getconn())

def init_invite_codes_table():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS invite_codes (
            id SERIAL PRIMARY KEY,
            code TEXT UNIQUE NOT NULL,
            email TEXT NOT NULL,
            used_at TIMESTAMP,
            expires_at TIMESTAMP NOT NULL,
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)
    conn.commit()
    cur.close()
    conn.close()


def create_invite_code(email, days_valid=14):
    code = secrets.token_urlsafe(24)
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO invite_codes (code, email, expires_at)
        VALUES (%s, %s, NOW() + (%s || ' days')::interval)
        RETURNING code, email, expires_at
        """,
        (code, email.strip().lower(), days_valid)
    )
    row = cur.fetchone()
    conn.commit()
    cur.close()
    conn.close()
    return row


def get_invite_code(code):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT code, email, used_at, expires_at FROM invite_codes WHERE code = %s", (code,))
    row = cur.fetchone()
    cur.close()
    conn.close()
    return row


def mark_invite_used(code):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("UPDATE invite_codes SET used_at = NOW() WHERE code = %s", (code,))
    conn.commit()
    cur.close()
    conn.close()


def init_donators_table():
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
    cur.execute("ALTER TABLE donators ADD COLUMN IF NOT EXISTS is_admin BOOLEAN NOT NULL DEFAULT FALSE")
    conn.commit()
    cur.close()
    conn.close()


def get_donator_by_id(donator_id):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT id, name, email FROM donators WHERE id = %s", (donator_id,))
    row = cur.fetchone()
    cur.close()
    conn.close()
    return row


def get_donator_by_email(email):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT id, name, email, password_hash FROM donators WHERE email = %s", (email,))
    row = cur.fetchone()
    cur.close()
    conn.close()
    return row


def get_forum_messages_for_moderation(channel=None, limit=200):
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
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM forum_messages WHERE id = %s", (message_id,))
    deleted = cur.rowcount > 0
    conn.commit()
    cur.close()
    conn.close()
    return deleted


def clear_forum_messages_by_channel(channel):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM forum_messages WHERE channel = %s", (channel,))
    deleted = cur.rowcount
    conn.commit()
    cur.close()
    conn.close()
    return deleted



def list_all_donators():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT id, name, email, is_admin, created_at FROM donators ORDER BY created_at DESC")
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return rows

def delete_donator_by_id(donator_id):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT id FROM donators WHERE id = %s", (donator_id,))
    if not cur.fetchone():
        cur.close()
        conn.close()
        return False

    cur.execute("DELETE FROM forum_messages WHERE sender_id = %s", (str(donator_id),))
    cur.execute("DELETE FROM intro_replies WHERE donator_id = %s", (donator_id,))
    cur.execute("DELETE FROM intro_threads WHERE donator_id = %s", (donator_id,))
    cur.execute("DELETE FROM donators WHERE id = %s", (donator_id,))

    conn.commit()
    cur.close()
    conn.close()
    return True


def get_donator_by_id(donator_id):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT id, name, email, is_admin FROM donators WHERE id = %s", (donator_id,))
    row = cur.fetchone()
    cur.close()
    conn.close()
    return row


def get_donator_by_email(email):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT id, name, email, password_hash, is_admin FROM donators WHERE email = %s", (email,))
    row = cur.fetchone()
    cur.close()
    conn.close()
    return row


def set_donator_admin_status(email, is_admin):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(
        "UPDATE donators SET is_admin = %s WHERE email = %s RETURNING id, name, email, is_admin",
        (is_admin, email.strip().lower())
    )
    row = cur.fetchone()
    conn.commit()
    cur.close()
    conn.close()
    return row