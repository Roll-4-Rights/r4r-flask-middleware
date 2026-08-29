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