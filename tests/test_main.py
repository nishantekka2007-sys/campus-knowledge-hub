import app.main as main

from fastapi.testclient import TestClient


client = TestClient(main.app)


def setup_test_database(tmp_path, monkeypatch):
    database_path = tmp_path / "test.db"
    monkeypatch.setattr(main, "DATABASE", str(database_path))
    main.create_table()
    return database_path


def register_and_login(
    client_instance,
    username="testuser",
    password="testpassword123",
):
    register_response = client_instance.post(
        "/register",
        json={
            "username": username,
            "password": password,
        },
    )

    assert register_response.status_code in (200, 201)

    login_response = client_instance.post(
        "/login",
        json={
            "username": username,
            "password": password,
        },
    )

    assert login_response.status_code == 200

    return login_response


def test_create_table(tmp_path, monkeypatch):
    setup_test_database(tmp_path, monkeypatch)

    connection = main.connect_database()
    cursor = connection.cursor()

    cursor.execute(
        """
        SELECT name
        FROM sqlite_master
        WHERE type = 'table' AND name = 'resources'
        """
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
        INSERT INTO resources
        (subject, title, resource_type, link)
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
        INSERT INTO resources
        (subject, title, resource_type, link)
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
        SELECT *
        FROM resources
        WHERE subject LIKE ?
           OR title LIKE ?
           OR resource_type LIKE ?
        """,
        (
            search_term,
            search_term,
            search_term,
        ),
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
        INSERT INTO resources
        (subject, title, resource_type, link)
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
        (
            "Python Fundamentals",
            1,
        ),
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
        INSERT INTO resources
        (subject, title, resource_type, link)
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


def test_health_check():
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_get_resources_api(tmp_path, monkeypatch):
    setup_test_database(tmp_path, monkeypatch)

    response = client.get("/resources")

    assert response.status_code == 200
    assert response.json() == []


def test_create_resource_api(tmp_path, monkeypatch):
    setup_test_database(tmp_path, monkeypatch)

    register_and_login(client)

    response = client.post(
        "/resources",
        json={
            "subject": "Java",
            "title": "Java Basics",
            "resource_type": "Notes",
            "link": "https://example.com/java",
            "description": "Introduction to Java programming.",
        },
    )

    assert response.status_code == 201
    assert response.json()["message"] == "Resource created successfully"

    resource_id = response.json()["id"]

    get_response = client.get(
        f"/resources/{resource_id}"
    )

    assert get_response.status_code == 200
    assert get_response.json()["title"] == "Java Basics"


def test_update_resource_api(tmp_path, monkeypatch):
    setup_test_database(tmp_path, monkeypatch)

    register_and_login(client)

    create_response = client.post(
        "/resources",
        json={
            "subject": "Python",
            "title": "Python Basics",
            "resource_type": "Notes",
            "link": "https://example.com",
            "description": "Basic Python concepts.",
        },
    )

    assert create_response.status_code == 201

    resource_id = create_response.json()["id"]

    response = client.put(
        f"/resources/{resource_id}",
        json={
            "subject": "Python",
            "title": "Python Fundamentals",
            "resource_type": "Course",
            "link": "https://example.com/python",
            "description": "Updated Python course.",
        },
    )

    assert response.status_code == 200

    get_response = client.get(
        f"/resources/{resource_id}"
    )

    assert get_response.status_code == 200
    assert get_response.json()["title"] == "Python Fundamentals"
    assert get_response.json()["resource_type"] == "Course"


def test_update_resource_api_rejects_invalid_url(
    tmp_path,
    monkeypatch,
):
    setup_test_database(tmp_path, monkeypatch)

    register_and_login(client)

    create_response = client.post(
        "/resources",
        json={
            "subject": "Python",
            "title": "Python Basics",
            "resource_type": "Notes",
            "link": "https://example.com",
            "description": "Basic Python concepts.",
        },
    )

    assert create_response.status_code == 201

    resource_id = create_response.json()["id"]

    response = client.put(
        f"/resources/{resource_id}",
        json={
            "subject": "Python",
            "title": "Updated Python",
            "resource_type": "Course",
            "link": "not-a-valid-url",
            "description": "Updated description.",
        },
    )

    assert response.status_code == 422


def test_toggle_favorite_api(tmp_path, monkeypatch):
    setup_test_database(tmp_path, monkeypatch)

    register_and_login(client)

    create_response = client.post(
        "/resources",
        json={
            "subject": "Java",
            "title": "Java Basics",
            "resource_type": "Course",
            "link": "https://example.com/java",
            "description": "Java programming notes.",
        },
    )

    assert create_response.status_code == 201

    resource_id = create_response.json()["id"]

    response = client.patch(
        f"/resources/{resource_id}/favorite"
    )

    assert response.status_code == 200

    body = response.json()

    assert body["is_favorite"] is True


def test_get_favorite_resources_api(tmp_path, monkeypatch):
    setup_test_database(tmp_path, monkeypatch)

    register_and_login(client)

    first_response = client.post(
        "/resources",
        json={
            "subject": "Java",
            "title": "Java Basics",
            "resource_type": "Course",
            "link": "https://example.com/java",
            "description": "Java programming.",
        },
    )

    second_response = client.post(
        "/resources",
        json={
            "subject": "Python",
            "title": "Python Basics",
            "resource_type": "Notes",
            "link": "https://example.com/python",
            "description": "Python programming.",
        },
    )

    assert first_response.status_code == 201
    assert second_response.status_code == 201

    first_id = first_response.json()["id"]

    favorite_response = client.patch(
        f"/resources/{first_id}/favorite"
    )

    assert favorite_response.status_code == 200

    response = client.get(
        "/resources?favorite=true"
    )

    assert response.status_code == 200

    results = response.json()

    assert len(results) == 1
    assert results[0]["title"] == "Java Basics"
    assert results[0]["is_favorite"] is True


def test_get_resources_by_type_api(tmp_path, monkeypatch):
    setup_test_database(tmp_path, monkeypatch)

    register_and_login(client)

    course_response = client.post(
        "/resources",
        json={
            "subject": "FastAPI",
            "title": "FastAPI Basics",
            "resource_type": "Course",
            "link": "https://example.com/fastapi",
            "description": "Learn FastAPI.",
        },
    )

    notes_response = client.post(
        "/resources",
        json={
            "subject": "Python",
            "title": "Python Fundamentals",
            "resource_type": "Notes",
            "link": "https://example.com/python",
            "description": "Learn Python.",
        },
    )

    assert course_response.status_code == 201
    assert notes_response.status_code == 201

    response = client.get(
        "/resources?type=Course"
    )

    assert response.status_code == 200

    results = response.json()

    assert len(results) == 1
    assert results[0]["title"] == "FastAPI Basics"
    assert results[0]["resource_type"] == "Course"


def test_delete_resource_api(tmp_path, monkeypatch):
    setup_test_database(tmp_path, monkeypatch)

    register_and_login(client)

    create_response = client.post(
        "/resources",
        json={
            "subject": "Java",
            "title": "Java Basics",
            "resource_type": "Notes",
            "link": "https://example.com/java",
            "description": "Java programming notes.",
        },
    )

    assert create_response.status_code == 201

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

    register_and_login(client)

    first_response = client.post(
        "/resources",
        json={
            "subject": "Python",
            "title": "FastAPI Basics",
            "resource_type": "Course",
            "link": "https://example.com/fastapi",
            "description": "Learn FastAPI fundamentals.",
        },
    )

    second_response = client.post(
        "/resources",
        json={
            "subject": "Java",
            "title": "Java Basics",
            "resource_type": "Notes",
            "link": "https://example.com/java",
            "description": "Java programming notes.",
        },
    )

    assert first_response.status_code == 201
    assert second_response.status_code == 201

    response = client.get(
        "/resources/search/FastAPI"
    )

    assert response.status_code == 200

    results = response.json()

    assert len(results) == 1
    assert results[0]["title"] == "FastAPI Basics"


def test_search_resource_api_by_description(
    tmp_path,
    monkeypatch,
):
    setup_test_database(tmp_path, monkeypatch)

    register_and_login(client)

    first_response = client.post(
        "/resources",
        json={
            "subject": "Java",
            "title": "Java Basics",
            "resource_type": "Course",
            "link": "https://example.com/java",
            "description": (
                "Introduction to object-oriented programming."
            ),
        },
    )

    second_response = client.post(
        "/resources",
        json={
            "subject": "Python",
            "title": "Python Basics",
            "resource_type": "Notes",
            "link": "https://example.com/python",
            "description": "Python syntax and fundamentals.",
        },
    )

    assert first_response.status_code == 201
    assert second_response.status_code == 201

    response = client.get(
        "/resources/search/object-oriented"
    )

    assert response.status_code == 200

    results = response.json()

    assert len(results) == 1
    assert results[0]["title"] == "Java Basics"


def test_not_found_resource_api(tmp_path, monkeypatch):
    setup_test_database(tmp_path, monkeypatch)

    response = client.get(
        "/resources/9999"
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Resource not found"


def test_create_resource_api_rejects_empty_fields(
    tmp_path,
    monkeypatch,
):
    setup_test_database(tmp_path, monkeypatch)

    register_and_login(client)

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


def test_create_resource_api_rejects_whitespace_fields(
    tmp_path,
    monkeypatch,
):
    setup_test_database(tmp_path, monkeypatch)

    register_and_login(client)

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


def test_create_resource_api_rejects_invalid_url(
    tmp_path,
    monkeypatch,
):
    setup_test_database(tmp_path, monkeypatch)

    register_and_login(client)

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


def test_create_resource_api_accepts_https_url(
    tmp_path,
    monkeypatch,
):
    setup_test_database(tmp_path, monkeypatch)

    register_and_login(client)

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


def test_register_api(tmp_path, monkeypatch):
    setup_test_database(tmp_path, monkeypatch)

    response = client.post(
        "/register",
        json={
            "username": "newuser",
            "password": "password123",
        },
    )

    assert response.status_code in (200, 201)

    body = response.json()

    assert "message" in body


def test_register_duplicate_username(
    tmp_path,
    monkeypatch,
):
    setup_test_database(tmp_path, monkeypatch)

    first_response = client.post(
        "/register",
        json={
            "username": "duplicateuser",
            "password": "password123",
        },
    )

    assert first_response.status_code in (200, 201)

    second_response = client.post(
        "/register",
        json={
            "username": "duplicateuser",
            "password": "password123",
        },
    )

    assert second_response.status_code in (400, 409)


def test_login_api(tmp_path, monkeypatch):
    setup_test_database(tmp_path, monkeypatch)

    register_response = client.post(
        "/register",
        json={
            "username": "loginuser",
            "password": "password123",
        },
    )

    assert register_response.status_code in (200, 201)

    login_response = client.post(
        "/login",
        json={
            "username": "loginuser",
            "password": "password123",
        },
    )

    assert login_response.status_code == 200

    body = login_response.json()

    assert "message" in body


def test_login_rejects_invalid_password(
    tmp_path,
    monkeypatch,
):
    setup_test_database(tmp_path, monkeypatch)

    register_response = client.post(
        "/register",
        json={
            "username": "wrongpassuser",
            "password": "password123",
        },
    )

    assert register_response.status_code in (200, 201)

    login_response = client.post(
        "/login",
        json={
            "username": "wrongpassuser",
            "password": "wrongpassword",
        },
    )

    assert login_response.status_code == 401


def test_me_requires_authentication(
    tmp_path,
    monkeypatch,
):
    setup_test_database(tmp_path, monkeypatch)

    unauthenticated_client = TestClient(main.app)

    response = unauthenticated_client.get("/me")

    assert response.status_code == 401


def test_me_returns_current_user(
    tmp_path,
    monkeypatch,
):
    setup_test_database(tmp_path, monkeypatch)

    authenticated_client = TestClient(main.app)

    register_and_login(
        authenticated_client,
        username="meuser",
        password="password123",
    )

    response = authenticated_client.get("/me")

    assert response.status_code == 200

    body = response.json()

    assert body["username"] == "meuser"
    assert body["role"] == "student"


def test_logout_api(tmp_path, monkeypatch):
    setup_test_database(tmp_path, monkeypatch)

    authenticated_client = TestClient(main.app)

    register_and_login(
        authenticated_client,
        username="logoutuser",
        password="password123",
    )

    me_response = authenticated_client.get("/me")

    assert me_response.status_code == 200

    logout_response = authenticated_client.post("/logout")

    assert logout_response.status_code == 200

    me_after_logout = authenticated_client.get("/me")

    assert me_after_logout.status_code == 401


def test_protected_create_requires_login(
    tmp_path,
    monkeypatch,
):
    setup_test_database(tmp_path, monkeypatch)

    unauthenticated_client = TestClient(main.app)

    response = unauthenticated_client.post(
        "/resources",
        json={
            "subject": "Python",
            "title": "Python Basics",
            "resource_type": "Course",
            "link": "https://example.com/python",
        },
    )

    assert response.status_code == 401