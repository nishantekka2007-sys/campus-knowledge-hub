import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import app.main as main


def setup_database(tmp_path):
    database = tmp_path / "test.db"
    main.DATABASE = str(database)
    main.create_table()
    return database


def get_all_resources(database):
    connection = sqlite3.connect(database)
    cursor = connection.cursor()

    cursor.execute("""
        SELECT id, subject, title, resource_type, link
        FROM resources
    """)

    resources = cursor.fetchall()

    connection.close()

    return resources


def test_create_table(tmp_path):
    database = setup_database(tmp_path)

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


def test_add_resource(tmp_path, monkeypatch):
    database = setup_database(tmp_path)

    inputs = iter([
        "Python",
        "Python Fundamentals",
        "Notes",
        "https://example.com/python"
    ])

    monkeypatch.setattr("builtins.input", lambda _: next(inputs))

    main.add_resource()

    resources = get_all_resources(database)

    assert len(resources) == 1
    assert resources[0][1] == "Python"
    assert resources[0][2] == "Python Fundamentals"
    assert resources[0][3] == "Notes"
    assert resources[0][4] == "https://example.com/python"


def test_search_resources(tmp_path, monkeypatch, capsys):
    database = setup_database(tmp_path)

    connection = sqlite3.connect(database)
    cursor = connection.cursor()

    cursor.execute("""
        INSERT INTO resources (subject, title, resource_type, link)
        VALUES (?, ?, ?, ?)
    """, (
        "Python",
        "Python Fundamentals",
        "Notes",
        "https://example.com/python"
    ))

    cursor.execute("""
        INSERT INTO resources (subject, title, resource_type, link)
        VALUES (?, ?, ?, ?)
    """, (
        "Physics",
        "Electromagnetic Induction",
        "Notes",
        "https://example.com/physics"
    ))

    connection.commit()
    connection.close()

    monkeypatch.setattr("builtins.input", lambda _: "Python")

    main.search_resources()

    output = capsys.readouterr().out

    assert "Python Fundamentals" in output
    assert "Electromagnetic Induction" not in output


def test_update_resource(tmp_path, monkeypatch):
    database = setup_database(tmp_path)

    connection = sqlite3.connect(database)
    cursor = connection.cursor()

    cursor.execute("""
        INSERT INTO resources (subject, title, resource_type, link)
        VALUES (?, ?, ?, ?)
    """, (
        "Python",
        "Python Basics",
        "Notes",
        "https://example.com/python"
    ))

    connection.commit()
    connection.close()

    inputs = iter([
        "1",
        "Python",
        "Python Advanced",
        "Course",
        "https://example.com/advanced"
    ])

    monkeypatch.setattr("builtins.input", lambda _: next(inputs))

    main.update_resource()

    resources = get_all_resources(database)

    assert resources[0][2] == "Python Advanced"
    assert resources[0][3] == "Course"
    assert resources[0][4] == "https://example.com/advanced"


def test_delete_resource(tmp_path, monkeypatch):
    database = setup_database(tmp_path)

    connection = sqlite3.connect(database)
    cursor = connection.cursor()

    cursor.execute("""
        INSERT INTO resources (subject, title, resource_type, link)
        VALUES (?, ?, ?, ?)
    """, (
        "Python",
        "Python Basics",
        "Notes",
        "https://example.com/python"
    ))

    connection.commit()
    connection.close()

    inputs = iter([
        "1",
        "y"
    ])

    monkeypatch.setattr("builtins.input", lambda _: next(inputs))

    main.delete_resource()

    resources = get_all_resources(database)

    assert resources == []

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

