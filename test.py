from dotenv import load_dotenv
load_dotenv()

from db import get_db_connection

try:
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT version();")
    result = cur.fetchone()
    print("Connected successfully!")
    print(result)
    cur.close()
    conn.close()
except Exception as e:
    print("Connection failed:")
    print(e)