import app.main as main

from fastapi.testclient import TestClient


client = TestClient(main.app)


def setup_test_database(tmp_path, monkeypatch):
    database_path = tmp_path / "test.db"

    monkeypatch.setattr(main, "DATABASE", str(database_path))

    main.create_table()

    return database_path


def test_create_table(tmp_path, monkeypatch):
    setup_test_database(tmp_path, monkeypatch)

    connection = main.connect_database()
    cursor = connection.cursor()

    cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='resources'"
    )

    result = cursor.fetchone()

    connection.close()

    assert result is not None


def test_add_resource(tmp_path, monkeypatch):
    setup_test_database(tmp_path, monkeypatch)

    connection = main.connect_database()
    cursor = connection.cursor()

    cursor.execute(
        """
        INSERT INTO resources (subject, title, resource_type, link)
        VALUES (?, ?, ?, ?)
        """,
        (
            "Python",
            "Python Fundamentals",
            "Notes",
            "https://example.com",
        ),
    )

    connection.commit()

    cursor.execute("SELECT * FROM resources")

    resource = cursor.fetchone()

    connection.close()

    assert resource[1] == "Python"
    assert resource[2] == "Python Fundamentals"
    assert resource[3] == "Notes"
    assert resource[4] == "https://example.com"


def test_search_resource(tmp_path, monkeypatch):
    setup_test_database(tmp_path, monkeypatch)

    connection = main.connect_database()
    cursor = connection.cursor()

    cursor.execute(
        """
        INSERT INTO resources (subject, title, resource_type, link)
        VALUES (?, ?, ?, ?)
        """,
        (
            "Python",
            "FastAPI Basics",
            "Course",
            "https://example.com/fastapi",
        ),
    )

    connection.commit()

    search_term = "%FastAPI%"

    cursor.execute(
        """
        SELECT * FROM resources
        WHERE subject LIKE ?
           OR title LIKE ?
           OR resource_type LIKE ?
        """,
        (search_term, search_term, search_term),
    )

    results = cursor.fetchall()

    connection.close()

    assert len(results) == 1
    assert results[0][2] == "FastAPI Basics"


def test_update_resource(tmp_path, monkeypatch):
    setup_test_database(tmp_path, monkeypatch)

    connection = main.connect_database()
    cursor = connection.cursor()

    cursor.execute(
        """
        INSERT INTO resources (subject, title, resource_type, link)
        VALUES (?, ?, ?, ?)
        """,
        (
            "Python",
            "Python Basics",
            "Notes",
            "https://example.com",
        ),
    )

    connection.commit()

    cursor.execute(
        """
        UPDATE resources
        SET title = ?
        WHERE id = ?
        """,
        ("Python Fundamentals", 1),
    )

    connection.commit()

    cursor.execute(
        "SELECT title FROM resources WHERE id = ?",
        (1,),
    )

    result = cursor.fetchone()

    connection.close()

    assert result[0] == "Python Fundamentals"


def test_delete_resource(tmp_path, monkeypatch):
    setup_test_database(tmp_path, monkeypatch)

    connection = main.connect_database()
    cursor = connection.cursor()

    cursor.execute(
        """
        INSERT INTO resources (subject, title, resource_type, link)
        VALUES (?, ?, ?, ?)
        """,
        (
            "Java",
            "Java Basics",
            "Notes",
            "https://example.com/java",
        ),
    )

    connection.commit()

    cursor.execute(
        "DELETE FROM resources WHERE id = ?",
        (1,),
    )

    connection.commit()

    cursor.execute(
        "SELECT * FROM resources WHERE id = ?",
        (1,),
    )

    result = cursor.fetchone()

    connection.close()

    assert result is None


def test_homepage():
    response = client.get("/")

    assert response.status_code == 200
    assert "Campus Knowledge Hub" in response.text


def test_get_resources_api(tmp_path, monkeypatch):
    setup_test_database(tmp_path, monkeypatch)

    response = client.get("/resources")

    assert response.status_code == 200
    assert response.json() == []


def test_create_resource_api(tmp_path, monkeypatch):
    setup_test_database(tmp_path, monkeypatch)

    response = client.post(
        "/resources",
        json={
            "subject": "Java",
            "title": "Java Basics",
            "resource_type": "Notes",
            "link": "https://example.com/java",
        },
    )

    assert response.status_code == 201
    assert response.json()["message"] == "Resource created successfully"

    resource_id = response.json()["id"]

    get_response = client.get(f"/resources/{resource_id}")

    assert get_response.status_code == 200
    assert get_response.json()["title"] == "Java Basics"


def test_update_resource_api(tmp_path, monkeypatch):
    setup_test_database(tmp_path, monkeypatch)

    create_response = client.post(
        "/resources",
        json={
            "subject": "Python",
            "title": "Python Basics",
            "resource_type": "Notes",
            "link": "https://example.com",
        },
    )

    resource_id = create_response.json()["id"]

    response = client.put(
        f"/resources/{resource_id}",
        json={
            "subject": "Python",
            "title": "Python Fundamentals",
            "resource_type": "Course",
            "link": "https://example.com/python",
        },
    )

    assert response.status_code == 200

    get_response = client.get(f"/resources/{resource_id}")

    assert get_response.status_code == 200
    assert get_response.json()["title"] == "Python Fundamentals"
    assert get_response.json()["resource_type"] == "Course"


def test_delete_resource_api(tmp_path, monkeypatch):
    setup_test_database(tmp_path, monkeypatch)

    create_response = client.post(
        "/resources",
        json={
            "subject": "Java",
            "title": "Java Basics",
            "resource_type": "Notes",
            "link": "https://example.com/java",
        },
    )

    resource_id = create_response.json()["id"]

    response = client.delete(
        f"/resources/{resource_id}"
    )

    assert response.status_code == 200

    get_response = client.get(
        f"/resources/{resource_id}"
    )

    assert get_response.status_code == 404


def test_search_resource_api(tmp_path, monkeypatch):
    setup_test_database(tmp_path, monkeypatch)

    client.post(
        "/resources",
        json={
            "subject": "Python",
            "title": "FastAPI Basics",
            "resource_type": "Course",
            "link": "https://example.com/fastapi",
        },
    )

    client.post(
        "/resources",
        json={
            "subject": "Java",
            "title": "Java Basics",
            "resource_type": "Notes",
            "link": "https://example.com/java",
        },
    )

    response = client.get(
        "/resources/search/FastAPI"
    )

    assert response.status_code == 200

    results = response.json()

    assert len(results) == 1
    assert results[0]["title"] == "FastAPI Basics"


def test_not_found_resource_api(tmp_path, monkeypatch):
    setup_test_database(tmp_path, monkeypatch)

    response = client.get("/resources/9999")

    assert response.status_code == 404
    assert response.json()["detail"] == "Resource not found"


def test_create_resource_api_rejects_empty_fields(tmp_path, monkeypatch):
    setup_test_database(tmp_path, monkeypatch)

    response = client.post(
        "/resources",
        json={
            "subject": "",
            "title": "Java Basics",
            "resource_type": "Notes",
            "link": "https://example.com/java",
        },
    )

    assert response.status_code == 422


def test_create_resource_api_rejects_whitespace_fields(tmp_path, monkeypatch):
    setup_test_database(tmp_path, monkeypatch)

    response = client.post(
        "/resources",
        json={
            "subject": "   ",
            "title": "Java Basics",
            "resource_type": "Notes",
            "link": "https://example.com/java",
        },
    )

    assert response.status_code == 422


def test_create_resource_api_rejects_invalid_url(tmp_path, monkeypatch):
    setup_test_database(tmp_path, monkeypatch)

    response = client.post(
        "/resources",
        json={
            "subject": "Java",
            "title": "Java Basics",
            "resource_type": "Notes",
            "link": "not-a-valid-url",
        },
    )

    assert response.status_code == 422


def test_create_resource_api_accepts_https_url(tmp_path, monkeypatch):
    setup_test_database(tmp_path, monkeypatch)

    response = client.post(
        "/resources",
        json={
            "subject": "FastAPI",
            "title": "FastAPI Documentation",
            "resource_type": "Documentation",
            "link": "https://fastapi.tiangolo.com/",
        },
    )

    assert response.status_code == 201