import psycopg2
import psycopg2.extras
import os

def get_db_connection():
    """Open a direct connection to Postgres (separate from NocoDB's REST API)."""
    return psycopg2.connect(
        host=os.environ.get('POSTGRES_HOST'),
        port=os.environ.get('POSTGRES_PORT', 5432),
        dbname=os.environ.get('POSTGRES_DB'),
        user=os.environ.get('POSTGRES_USER'),
        password=os.environ.get('POSTGRES_PASSWORD'),
        cursor_factory=psycopg2.extras.RealDictCursor
    )

def init_donators_table():
    """Create the donators table if it doesn't already exist. Safe to call every startup."""
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS donators (
            id SERIAL PRIMARY KEY,
            name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)
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


'''forum message handling functions'''


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