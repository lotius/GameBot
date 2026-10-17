"""Short-lived MariaDB connections; callers run blocking work in a thread."""
import os
import pymysql


def connect():
    required = ['DB_HOST', 'DB_NAME', 'DB_USER', 'DB_PASSWORD']
    missing = [key for key in required if not os.getenv(key)]
    if missing:
        raise RuntimeError('Missing database settings: ' + ', '.join(missing))
    return pymysql.connect(
        host=os.environ['DB_HOST'], port=int(os.getenv('DB_PORT', '3306')),
        user=os.environ['DB_USER'], password=os.environ['DB_PASSWORD'],
        database=os.environ['DB_NAME'], charset='utf8mb4',
        init_command="SET time_zone = '+00:00'",
        connect_timeout=3, read_timeout=15, write_timeout=15,
    )
