import os
from pathlib import Path

import psycopg2
from dotenv import load_dotenv


def main() -> None:
    load_dotenv()
    db_url = os.getenv("SUPABASE_DB_URL")
    if not db_url:
        print("Missing SUPABASE_DB_URL in .env")
        return

    migration_path = Path("supabase/migrations/039_source_state_on_publish.sql")
    if not migration_path.exists():
        print(f"Migration file not found: {migration_path}")
        return

    sql = migration_path.read_text(encoding="utf-8")
    print(f"Applying migration {migration_path.name} to {db_url.split('@')[-1]}...")

    try:
        conn = psycopg2.connect(db_url)
        conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute(sql)
        print("Success! Migration applied.")
        conn.close()
    except Exception as e:
        print(f"Error applying migration: {e}")


if __name__ == "__main__":
    main()
