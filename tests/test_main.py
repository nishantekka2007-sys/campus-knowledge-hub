import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import app.main as main


def test_create_table(tmp_path):
    database = tmp_path / "test.db"

    main.DATABASE = str(database)

    main.create_table()

    connection = sqlite3.connect(database)
    cursor = connection.cursor()

    cursor.execute("""
        SELECT name
        FROM sqlite_master
        WHERE type = 'table' AND name = 'resources'
    """)

    result = cursor.fetchone()

    connection.close()

    assert result is not None
import sqlite3

import app.main as main


def test_create_table(tmp_path):
    database = tmp_path / "test.db"

    main.DATABASE = str(database)

    main.create_table()

    connection = sqlite3.connect(database)
    cursor = connection.cursor()

    cursor.execute("""
        SELECT name
        FROM sqlite_master
        WHERE type = 'table' AND name = 'resources'
    """)

    result = cursor.fetchone()

    connection.close()

    assert result is not None

