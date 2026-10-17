"""Run with python init_database.py to create GameBot tables safely."""
from pathlib import Path
from dotenv import load_dotenv

from database import connect

ROOT = Path(__file__).resolve().parent


def initialize_database():
    load_dotenv(ROOT / '.env')
    statements = [statement.strip() for statement in (ROOT / 'schema.sql').read_text().split(';') if statement.strip()]
    with connect() as connection:
        with connection.cursor() as cursor:
            for statement in statements:
                cursor.execute(statement)
            # Older startup code may already have created the settings table.
            cursor.execute('SHOW COLUMNS FROM gamebot_guild_settings')
            present = {row[0] for row in cursor.fetchall()}
            additions = {
                'bot_admin_role_id': 'BIGINT UNSIGNED NULL',
                'roll_logging_enabled': 'BOOLEAN NOT NULL DEFAULT TRUE',
                'spam_enabled': 'BOOLEAN NOT NULL DEFAULT TRUE',
                'spam_limit': 'INT UNSIGNED NOT NULL DEFAULT 5',
                'spam_window_seconds': 'INT UNSIGNED NOT NULL DEFAULT 10',
                'retention_enabled': 'BOOLEAN NOT NULL DEFAULT FALSE',
                'retention_days': 'INT UNSIGNED NOT NULL DEFAULT 90',
            }
            for name, definition in additions.items():
                if name not in present:
                    cursor.execute(f'ALTER TABLE gamebot_guild_settings ADD COLUMN {name} {definition}')
            cursor.execute('SHOW COLUMNS FROM gamebot_instruction_deliveries')
            if 'delivery_state' not in {row[0] for row in cursor.fetchall()}:
                cursor.execute("ALTER TABLE gamebot_instruction_deliveries ADD COLUMN delivery_state VARCHAR(16) NOT NULL DEFAULT 'sent'")
            cursor.execute('SHOW COLUMNS FROM found_instructions')
            columns = {row[0] for row in cursor.fetchall()}
            if not {'instruction_id', 'title', 'page_url'} <= columns:
                raise RuntimeError('Existing found_instructions table is incompatible; it was preserved. '
                                   'Inspect SHOW CREATE TABLE found_instructions before migrating it. '
                                   'Other GameBot tables have been created.')
            cursor.execute('SHOW TABLES')
            print('Database tables:', ', '.join(row[0] for row in cursor.fetchall()))
        connection.commit()


if __name__ == '__main__':
    initialize_database()
