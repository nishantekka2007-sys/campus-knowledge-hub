import app.main as main

from fastapi.testclient import TestClient


client = TestClient(main.app)


def setup_test_database(tmp_path, monkeypatch):
    database_path = tmp_path / "test.db"

    monkeypatch.setattr(
        main,
        "DATABASE",
        str(database_path),
    )

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

    assert register_response.status_code in (
        200,
        201,
    )

    login_response = client_instance.post(
        "/login",
        json={
            "username": username,
            "password": password,
        },
    )

    assert login_response.status_code == 200

    return login_response


def make_admin(username):
    connection = main.connect_database()
    cursor = connection.cursor()

    cursor.execute(
        """
        UPDATE users
        SET role = 'admin'
        WHERE username = ?
        """,
        (username,),
    )

    connection.commit()
    connection.close()


def create_test_resource():
    response = client.post(
        "/resources",
        json={
            "subject": "Python",
            "title": "Python Basics",
            "resource_type": "Course",
            "link": "https://example.com/python",
            "description": "Python fundamentals.",
        },
    )

    assert response.status_code == 201

    return response.json()["id"]


def create_resource_with_title(
    title,
    resource_type="Course",
    subject="Python",
    description=None,
):
    response = client.post(
        "/resources",
        json={
            "subject": subject,
            "title": title,
            "resource_type": resource_type,
            "link": "https://example.com/resource",
            "description": (
                description
                if description is not None
                else f"Description for {title}."
            ),
        },
    )

    assert response.status_code == 201

    return response.json()["id"]


def valid_pdf_content():
    return (
        b"%PDF-1.4\n"
        b"1 0 obj\n"
        b"<< /Type /Catalog >>\n"
        b"endobj\n"
        b"%%EOF\n"
    )


# =========================================================
# DATABASE / BASIC TESTS
# =========================================================

def test_create_table(tmp_path, monkeypatch):
    setup_test_database(tmp_path, monkeypatch)

    connection = main.connect_database()
    cursor = connection.cursor()

    cursor.execute(
        """
        SELECT name
        FROM sqlite_master
        WHERE type = 'table'
          AND name = 'resources'
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
        (
            subject,
            title,
            resource_type,
            link
        )
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

    cursor.execute(
        "SELECT * FROM resources"
    )

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
        (
            subject,
            title,
            resource_type,
            link
        )
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
        (
            subject,
            title,
            resource_type,
            link
        )
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
        """
        SELECT title
        FROM resources
        WHERE id = ?
        """,
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
        (
            subject,
            title,
            resource_type,
            link
        )
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
        """
        DELETE FROM resources
        WHERE id = ?
        """,
        (1,),
    )

    connection.commit()

    cursor.execute(
        """
        SELECT *
        FROM resources
        WHERE id = ?
        """,
        (1,),
    )

    result = cursor.fetchone()

    connection.close()

    assert result is None


# =========================================================
# BASIC API TESTS
# =========================================================

def test_homepage():
    response = client.get("/")

    assert response.status_code == 200
    assert "Campus Knowledge Hub" in response.text


def test_health_check():
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_get_resources_api(
    tmp_path,
    monkeypatch,
):
    setup_test_database(
        tmp_path,
        monkeypatch,
    )

    response = client.get("/resources")

    assert response.status_code == 200
    assert response.json() == []


def test_create_resource_api(
    tmp_path,
    monkeypatch,
):
    setup_test_database(
        tmp_path,
        monkeypatch,
    )

    register_and_login(client)

    response = client.post(
        "/resources",
        json={
            "subject": "Java",
            "title": "Java Basics",
            "resource_type": "Notes",
            "link": "https://example.com/java",
            "description": (
                "Introduction to Java programming."
            ),
        },
    )

    assert response.status_code == 201

    assert (
        response.json()["message"]
        == "Resource created successfully"
    )

    resource_id = response.json()["id"]

    get_response = client.get(
        f"/resources/{resource_id}"
    )

    assert get_response.status_code == 200

    assert (
        get_response.json()["title"]
        == "Java Basics"
    )


def test_update_resource_api(
    tmp_path,
    monkeypatch,
):
    setup_test_database(
        tmp_path,
        monkeypatch,
    )

    register_and_login(client)

    create_response = client.post(
        "/resources",
        json={
            "subject": "Python",
            "title": "Python Basics",
            "resource_type": "Notes",
            "link": "https://example.com",
            "description": (
                "Basic Python concepts."
            ),
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
            "link": (
                "https://example.com/python"
            ),
            "description": (
                "Updated Python course."
            ),
        },
    )

    assert response.status_code == 200

    get_response = client.get(
        f"/resources/{resource_id}"
    )

    assert get_response.status_code == 200

    assert (
        get_response.json()["title"]
        == "Python Fundamentals"
    )

    assert (
        get_response.json()["resource_type"]
        == "Course"
    )


def test_update_resource_api_rejects_invalid_url(
    tmp_path,
    monkeypatch,
):
    setup_test_database(
        tmp_path,
        monkeypatch,
    )

    register_and_login(client)

    create_response = client.post(
        "/resources",
        json={
            "subject": "Python",
            "title": "Python Basics",
            "resource_type": "Notes",
            "link": "https://example.com",
            "description": (
                "Basic Python concepts."
            ),
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
            "description": (
                "Updated description."
            ),
        },
    )

    assert response.status_code == 422


def test_toggle_favorite_api(
    tmp_path,
    monkeypatch,
):
    setup_test_database(
        tmp_path,
        monkeypatch,
    )

    register_and_login(client)

    create_response = client.post(
        "/resources",
        json={
            "subject": "Java",
            "title": "Java Basics",
            "resource_type": "Course",
            "link": "https://example.com/java",
            "description": (
                "Java programming notes."
            ),
        },
    )

    assert create_response.status_code == 201

    resource_id = create_response.json()["id"]

    response = client.patch(
        f"/resources/{resource_id}/favorite"
    )

    assert response.status_code == 200

    assert (
        response.json()["is_favorite"]
        is True
    )


def test_get_favorite_resources_api(
    tmp_path,
    monkeypatch,
):
    setup_test_database(
        tmp_path,
        monkeypatch,
    )

    register_and_login(client)

    first_response = client.post(
        "/resources",
        json={
            "subject": "Java",
            "title": "Java Basics",
            "resource_type": "Course",
            "link": (
                "https://example.com/java"
            ),
            "description": (
                "Java programming."
            ),
        },
    )

    second_response = client.post(
        "/resources",
        json={
            "subject": "Python",
            "title": "Python Basics",
            "resource_type": "Notes",
            "link": (
                "https://example.com/python"
            ),
            "description": (
                "Python programming."
            ),
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

    assert (
        results[0]["title"]
        == "Java Basics"
    )

    assert (
        results[0]["is_favorite"]
        is True
    )


def test_get_resources_by_type_api(
    tmp_path,
    monkeypatch,
):
    setup_test_database(
        tmp_path,
        monkeypatch,
    )

    register_and_login(client)

    course_response = client.post(
        "/resources",
        json={
            "subject": "FastAPI",
            "title": "FastAPI Basics",
            "resource_type": "Course",
            "link": (
                "https://example.com/fastapi"
            ),
            "description": (
                "Learn FastAPI."
            ),
        },
    )

    notes_response = client.post(
        "/resources",
        json={
            "subject": "Python",
            "title": "Python Fundamentals",
            "resource_type": "Notes",
            "link": (
                "https://example.com/python"
            ),
            "description": (
                "Learn Python."
            ),
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

    assert (
        results[0]["title"]
        == "FastAPI Basics"
    )

    assert (
        results[0]["resource_type"]
        == "Course"
    )


def test_delete_resource_api(
    tmp_path,
    monkeypatch,
):
    setup_test_database(
        tmp_path,
        monkeypatch,
    )

    username = "admin_delete_test"

    register_and_login(
        client,
        username=username,
        password="password123",
    )

    make_admin(username)

    create_response = client.post(
        "/resources",
        json={
            "subject": "Java",
            "title": "Java Basics",
            "resource_type": "Notes",
            "link": (
                "https://example.com/java"
            ),
            "description": (
                "Java programming notes."
            ),
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


def test_search_resource_api(
    tmp_path,
    monkeypatch,
):
    setup_test_database(
        tmp_path,
        monkeypatch,
    )

    register_and_login(client)

    first_response = client.post(
        "/resources",
        json={
            "subject": "Python",
            "title": "FastAPI Basics",
            "resource_type": "Course",
            "link": (
                "https://example.com/fastapi"
            ),
            "description": (
                "Learn FastAPI fundamentals."
            ),
        },
    )

    second_response = client.post(
        "/resources",
        json={
            "subject": "Java",
            "title": "Java Basics",
            "resource_type": "Notes",
            "link": (
                "https://example.com/java"
            ),
            "description": (
                "Java programming notes."
            ),
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

    assert (
        results[0]["title"]
        == "FastAPI Basics"
    )


def test_search_resource_api_by_description(
    tmp_path,
    monkeypatch,
):
    setup_test_database(
        tmp_path,
        monkeypatch,
    )

    register_and_login(client)

    first_response = client.post(
        "/resources",
        json={
            "subject": "Java",
            "title": "Java Basics",
            "resource_type": "Course",
            "link": (
                "https://example.com/java"
            ),
            "description": (
                "Introduction to "
                "object-oriented programming."
            ),
        },
    )

    second_response = client.post(
        "/resources",
        json={
            "subject": "Python",
            "title": "Python Basics",
            "resource_type": "Notes",
            "link": (
                "https://example.com/python"
            ),
            "description": (
                "Python syntax and fundamentals."
            ),
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

    assert (
        results[0]["title"]
        == "Java Basics"
    )


def test_not_found_resource_api(
    tmp_path,
    monkeypatch,
):
    setup_test_database(tmp_path, monkeypatch)

    response = client.get(
        "/resources/9999"
    )

    assert response.status_code == 404

    assert (
        response.json()["detail"]
        == "Resource not found"
    )


# =========================================================
# VALIDATION TESTS
# =========================================================

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
            "link": (
                "https://example.com/java"
            ),
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
            "link": (
                "https://example.com/java"
            ),
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
            "link": (
                "https://fastapi.tiangolo.com/"
            ),
        },
    )

    assert response.status_code == 201


# =========================================================
# AUTHENTICATION TESTS
# =========================================================

def test_register_api(
    tmp_path,
    monkeypatch,
):
    setup_test_database(tmp_path, monkeypatch)

    response = client.post(
        "/register",
        json={
            "username": "newuser",
            "password": "password123",
        },
    )

    assert response.status_code in (
        200,
        201,
    )

    assert "message" in response.json()


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

    assert first_response.status_code in (
        200,
        201,
    )

    second_response = client.post(
        "/register",
        json={
            "username": "duplicateuser",
            "password": "password123",
        },
    )

    assert second_response.status_code in (
        400,
        409,
    )


def test_login_api(
    tmp_path,
    monkeypatch,
):
    setup_test_database(tmp_path, monkeypatch)

    register_response = client.post(
        "/register",
        json={
            "username": "loginuser",
            "password": "password123",
        },
    )

    assert register_response.status_code in (
        200,
        201,
    )

    login_response = client.post(
        "/login",
        json={
            "username": "loginuser",
            "password": "password123",
        },
    )

    assert login_response.status_code == 200

    assert "message" in login_response.json()


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

    assert register_response.status_code in (
        200,
        201,
    )

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

    unauthenticated_client = TestClient(
        main.app
    )

    response = (
        unauthenticated_client.get(
            "/me"
        )
    )

    assert response.status_code == 401


def test_me_returns_current_user(
    tmp_path,
    monkeypatch,
):
    setup_test_database(tmp_path, monkeypatch)

    authenticated_client = TestClient(
        main.app
    )

    register_and_login(
        authenticated_client,
        username="meuser",
        password="password123",
    )

    response = authenticated_client.get(
        "/me"
    )

    assert response.status_code == 200

    body = response.json()

    assert body["username"] == "meuser"
    assert body["role"] == "student"


def test_logout_api(
    tmp_path,
    monkeypatch,
):
    setup_test_database(tmp_path, monkeypatch)

    authenticated_client = TestClient(
        main.app
    )

    register_and_login(
        authenticated_client,
        username="logoutuser",
        password="password123",
    )

    me_response = authenticated_client.get(
        "/me"
    )

    assert me_response.status_code == 200

    logout_response = (
        authenticated_client.post(
            "/logout"
        )
    )

    assert logout_response.status_code == 200

    me_after_logout = (
        authenticated_client.get(
            "/me"
        )
    )

    assert me_after_logout.status_code == 401


def test_protected_create_requires_login(
    tmp_path,
    monkeypatch,
):
    setup_test_database(tmp_path, monkeypatch)

    unauthenticated_client = TestClient(
        main.app
    )

    response = unauthenticated_client.post(
        "/resources",
        json={
            "subject": "Python",
            "title": "Python Basics",
            "resource_type": "Course",
            "link": (
                "https://example.com/python"
            ),
        },
    )

    assert response.status_code == 401


# =========================================================
# FILE / PDF TESTS
# =========================================================

def test_upload_pdf_api(
    tmp_path,
    monkeypatch,
):
    setup_test_database(tmp_path, monkeypatch)

    register_and_login(client)

    resource_id = create_test_resource()

    response = client.post(
        f"/resources/{resource_id}/file",
        files={
            "file": (
                "python-notes.pdf",
                valid_pdf_content(),
                "application/pdf",
            )
        },
    )

    assert response.status_code == 201

    body = response.json()

    assert (
        body["message"]
        == "PDF uploaded successfully"
    )

    assert (
        body["resource_id"]
        == resource_id
    )

    assert (
        body["file_name"]
        == "python-notes.pdf"
    )

    assert (
        body["content_type"]
        == "application/pdf"
    )

    assert body["file_size"] > 0


def test_resource_shows_attached_file(
    tmp_path,
    monkeypatch,
):
    setup_test_database(tmp_path, monkeypatch)

    register_and_login(client)

    resource_id = create_test_resource()

    upload_response = client.post(
        f"/resources/{resource_id}/file",
        files={
            "file": (
                "notes.pdf",
                valid_pdf_content(),
                "application/pdf",
            )
        },
    )

    assert upload_response.status_code == 201

    response = client.get(
        f"/resources/{resource_id}"
    )

    assert response.status_code == 200

    body = response.json()

    assert body["has_file"] is True
    assert body["file_name"] == "notes.pdf"
    assert body["file_size"] > 0
    assert (
        body["file_content_type"]
        == "application/pdf"
    )


def test_download_pdf_api(
    tmp_path,
    monkeypatch,
):
    setup_test_database(tmp_path, monkeypatch)

    register_and_login(client)

    resource_id = create_test_resource()

    pdf_data = valid_pdf_content()

    upload_response = client.post(
        f"/resources/{resource_id}/file",
        files={
            "file": (
                "download-test.pdf",
                pdf_data,
                "application/pdf",
            )
        },
    )

    assert upload_response.status_code == 201

    response = client.get(
        f"/resources/{resource_id}/file"
    )

    assert response.status_code == 200

    assert (
        response.headers["content-type"]
        == "application/pdf"
    )

    assert response.content == pdf_data


def test_upload_rejects_non_pdf(
    tmp_path,
    monkeypatch,
):
    setup_test_database(tmp_path, monkeypatch)

    register_and_login(client)

    resource_id = create_test_resource()

    response = client.post(
        f"/resources/{resource_id}/file",
        files={
            "file": (
                "notes.txt",
                b"plain text file",
                "text/plain",
            )
        },
    )

    assert response.status_code == 415

    assert (
        response.json()["detail"]
        == "Only PDF files are allowed"
    )


def test_upload_rejects_fake_pdf(
    tmp_path,
    monkeypatch,
):
    setup_test_database(tmp_path, monkeypatch)

    register_and_login(client)

    resource_id = create_test_resource()

    response = client.post(
        f"/resources/{resource_id}/file",
        files={
            "file": (
                "fake.pdf",
                b"this is not really a PDF",
                "application/pdf",
            )
        },
    )

    assert response.status_code == 415

    assert (
        "valid PDF signature"
        in response.json()["detail"]
    )


def test_student_cannot_upload_to_others_resource(
    tmp_path,
    monkeypatch,
):
    setup_test_database(tmp_path, monkeypatch)

    register_and_login(
        client,
        username="owneruser",
        password="password123",
    )

    resource_id = create_test_resource()

    client.post("/logout")

    register_and_login(
        client,
        username="otheruser",
        password="password123",
    )

    response = client.post(
        f"/resources/{resource_id}/file",
        files={
            "file": (
                "other.pdf",
                valid_pdf_content(),
                "application/pdf",
            )
        },
    )

    assert response.status_code == 403


def test_delete_pdf_api(
    tmp_path,
    monkeypatch,
):
    setup_test_database(tmp_path, monkeypatch)

    register_and_login(client)

    resource_id = create_test_resource()

    upload_response = client.post(
        f"/resources/{resource_id}/file",
        files={
            "file": (
                "delete-test.pdf",
                valid_pdf_content(),
                "application/pdf",
            )
        },
    )

    assert upload_response.status_code == 201

    delete_response = client.delete(
        f"/resources/{resource_id}/file"
    )

    assert delete_response.status_code == 200

    body = delete_response.json()

    assert (
        body["message"]
        == "PDF deleted successfully"
    )

    resource_response = client.get(
        f"/resources/{resource_id}"
    )

    assert resource_response.status_code == 200

    resource_body = resource_response.json()

    assert resource_body["has_file"] is False
    assert resource_body["file_name"] is None
    assert resource_body["file_size"] is None


def test_download_missing_file_returns_404(
    tmp_path,
    monkeypatch,
):
    setup_test_database(tmp_path, monkeypatch)

    register_and_login(client)

    resource_id = create_test_resource()

    response = client.get(
        f"/resources/{resource_id}/file"
    )

    assert response.status_code == 404

    assert (
        response.json()["detail"]
        == "No file is attached "
        "to this resource"
    )


# =========================================================
# PAGINATION TESTS
# =========================================================

def test_resources_pagination_headers(
    tmp_path,
    monkeypatch,
):
    setup_test_database(tmp_path, monkeypatch)

    register_and_login(client)

    for number in range(12):
        create_resource_with_title(
            f"Resource {number:02d}"
        )

    response = client.get(
        "/resources?page=2&limit=5"
    )

    assert response.status_code == 200

    results = response.json()

    assert len(results) == 5

    assert response.headers["X-Page"] == "2"
    assert response.headers["X-Limit"] == "5"
    assert response.headers["X-Total"] == "12"
    assert response.headers["X-Pages"] == "3"
    assert response.headers["X-Sort-By"] == "id"
    assert response.headers["X-Order"] == "asc"


def test_resources_pagination_page_three(
    tmp_path,
    monkeypatch,
):
    setup_test_database(tmp_path, monkeypatch)

    register_and_login(client)

    for number in range(12):
        create_resource_with_title(
            f"Resource {number:02d}"
        )

    response = client.get(
        "/resources?page=3&limit=5"
    )

    assert response.status_code == 200

    results = response.json()

    assert len(results) == 2

    assert response.headers["X-Page"] == "3"
    assert response.headers["X-Limit"] == "5"
    assert response.headers["X-Total"] == "12"
    assert response.headers["X-Pages"] == "3"


def test_resources_sort_title_ascending(
    tmp_path,
    monkeypatch,
):
    setup_test_database(tmp_path, monkeypatch)

    register_and_login(client)

    create_resource_with_title("Zebra")
    create_resource_with_title("Alpha")
    create_resource_with_title("Middle")

    response = client.get(
        "/resources?sort_by=title&order=asc"
    )

    assert response.status_code == 200

    titles = [
        resource["title"]
        for resource in response.json()
    ]

    assert titles == [
        "Alpha",
        "Middle",
        "Zebra",
    ]

    assert (
        response.headers["X-Sort-By"]
        == "title"
    )

    assert (
        response.headers["X-Order"]
        == "asc"
    )


def test_resources_sort_title_descending(
    tmp_path,
    monkeypatch,
):
    setup_test_database(tmp_path, monkeypatch)

    register_and_login(client)

    create_resource_with_title("Zebra")
    create_resource_with_title("Alpha")
    create_resource_with_title("Middle")

    response = client.get(
        "/resources?sort_by=title&order=desc"
    )

    assert response.status_code == 200

    titles = [
        resource["title"]
        for resource in response.json()
    ]

    assert titles == [
        "Zebra",
        "Middle",
        "Alpha",
    ]

    assert (
        response.headers["X-Sort-By"]
        == "title"
    )

    assert (
        response.headers["X-Order"]
        == "desc"
    )


def test_resources_invalid_page(
    tmp_path,
    monkeypatch,
):
    setup_test_database(tmp_path, monkeypatch)

    response = client.get(
        "/resources?page=0"
    )

    assert response.status_code == 422


def test_resources_invalid_limit(
    tmp_path,
    monkeypatch,
):
    setup_test_database(tmp_path, monkeypatch)

    response = client.get(
        "/resources?limit=101"
    )

    assert response.status_code == 422


def test_resources_invalid_sort_by(
    tmp_path,
    monkeypatch,
):
    setup_test_database(tmp_path, monkeypatch)

    response = client.get(
        "/resources?sort_by=subject"
    )

    assert response.status_code == 422


def test_resources_invalid_order(
    tmp_path,
    monkeypatch,
):
    setup_test_database(tmp_path, monkeypatch)

    response = client.get(
        "/resources?order=random"
    )

    assert response.status_code == 422


# =========================================================
# SEARCH PAGINATION / SORTING TESTS
# =========================================================

def test_search_pagination_headers(
    tmp_path,
    monkeypatch,
):
    setup_test_database(tmp_path, monkeypatch)

    register_and_login(client)

    for number in range(12):
        create_resource_with_title(
            f"Python Resource {number:02d}",
            description=(
                f"Python learning resource {number}"
            ),
        )

    response = client.get(
        "/resources/search/Python"
        "?page=2&limit=5"
    )

    assert response.status_code == 200

    results = response.json()

    assert len(results) == 5

    assert response.headers["X-Page"] == "2"
    assert response.headers["X-Limit"] == "5"
    assert response.headers["X-Total"] == "12"
    assert response.headers["X-Pages"] == "3"
    assert response.headers["X-Sort-By"] == "id"
    assert response.headers["X-Order"] == "asc"


def test_search_pagination_last_page(
    tmp_path,
    monkeypatch,
):
    setup_test_database(tmp_path, monkeypatch)

    register_and_login(client)

    for number in range(12):
        create_resource_with_title(
            f"Python Resource {number:02d}",
            description=(
                f"Python learning resource {number}"
            ),
        )

    response = client.get(
        "/resources/search/Python"
        "?page=3&limit=5"
    )

    assert response.status_code == 200

    results = response.json()

    assert len(results) == 2

    assert response.headers["X-Page"] == "3"
    assert response.headers["X-Limit"] == "5"
    assert response.headers["X-Total"] == "12"
    assert response.headers["X-Pages"] == "3"


def test_search_sort_title_ascending(
    tmp_path,
    monkeypatch,
):
    setup_test_database(tmp_path, monkeypatch)

    register_and_login(client)

    create_resource_with_title(
        "Python Zebra"
    )

    create_resource_with_title(
        "Python Alpha"
    )

    create_resource_with_title(
        "Python Middle"
    )

    response = client.get(
        "/resources/search/Python"
        "?sort_by=title&order=asc"
    )

    assert response.status_code == 200

    titles = [
        resource["title"]
        for resource in response.json()
    ]

    assert titles == [
        "Python Alpha",
        "Python Middle",
        "Python Zebra",
    ]

    assert (
        response.headers["X-Sort-By"]
        == "title"
    )

    assert (
        response.headers["X-Order"]
        == "asc"
    )


def test_search_sort_title_descending(
    tmp_path,
    monkeypatch,
):
    setup_test_database(tmp_path, monkeypatch)

    register_and_login(client)

    create_resource_with_title(
        "Python Zebra"
    )

    create_resource_with_title(
        "Python Alpha"
    )

    create_resource_with_title(
        "Python Middle"
    )

    response = client.get(
        "/resources/search/Python"
        "?sort_by=title&order=desc"
    )

    assert response.status_code == 200

    titles = [
        resource["title"]
        for resource in response.json()
    ]

    assert titles == [
        "Python Zebra",
        "Python Middle",
        "Python Alpha",
    ]

    assert (
        response.headers["X-Sort-By"]
        == "title"
    )

    assert (
        response.headers["X-Order"]
        == "desc"
    )


def test_search_invalid_page(
    tmp_path,
    monkeypatch,
):
    setup_test_database(tmp_path, monkeypatch)

    response = client.get(
        "/resources/search/Python?page=0"
    )

    assert response.status_code == 422


def test_search_invalid_limit(
    tmp_path,
    monkeypatch,
):
    setup_test_database(tmp_path, monkeypatch)

    response = client.get(
        "/resources/search/Python?limit=101"
    )

    assert response.status_code == 422


def test_search_invalid_sort_by(
    tmp_path,
    monkeypatch,
):
    setup_test_database(tmp_path, monkeypatch)

    response = client.get(
        "/resources/search/Python?sort_by=subject"
    )

    assert response.status_code == 422


def test_search_invalid_order(
    tmp_path,
    monkeypatch,
):
    setup_test_database(tmp_path, monkeypatch)

    response = client.get(
        "/resources/search/Python?order=random"
    )

    assert response.status_code == 422