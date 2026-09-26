import hashlib
import hmac
import os
import re
import secrets
import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Literal
from urllib.parse import urlparse

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field, field_validator


DATABASE = "campus.db"

SESSION_DAYS = 7
PASSWORD_ITERATIONS = 310_000

VALID_ROLES = {"student", "admin"}


app = FastAPI(
    title="Campus Knowledge Hub",
    description="API for managing college learning resources",
    version="1.1.0",
)


templates = Jinja2Templates(directory="templates")


# ---------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------

class RegisterRequest(BaseModel):
    username: str = Field(min_length=3, max_length=30)
    password: str = Field(min_length=8, max_length=128)

    @field_validator("username")
    @classmethod
    def validate_username(cls, value: str) -> str:
        value = value.strip()

        if not re.fullmatch(r"[A-Za-z0-9_]{3,30}", value):
            raise ValueError(
                "Username must contain only letters, numbers, and underscores"
            )

        return value


class LoginRequest(BaseModel):
    username: str
    password: str


class Resource(BaseModel):
    subject: str = Field(min_length=1)
    title: str = Field(min_length=1)
    resource_type: str = Field(min_length=1)
    link: str = Field(min_length=1)
    description: str = Field(default="", max_length=500)

    @field_validator(
        "subject",
        "title",
        "resource_type",
        "link",
    )
    @classmethod
    def validate_text(cls, value: str) -> str:
        value = value.strip()

        if not value:
            raise ValueError("Field cannot be empty")

        return value

    @field_validator("description")
    @classmethod
    def validate_description(cls, value: str) -> str:
        return value.strip()

    @field_validator("link")
    @classmethod
    def validate_link(cls, value: str) -> str:
        parsed_url = urlparse(value)

        if (
            parsed_url.scheme not in ("http", "https")
            or not parsed_url.netloc
        ):
            raise ValueError(
                "Link must be a valid HTTP or HTTPS URL"
            )

        return value


class RoleUpdateRequest(BaseModel):
    role: Literal["student", "admin"]


# ---------------------------------------------------------
# Database
# ---------------------------------------------------------

def connect_database():
    connection = sqlite3.connect(DATABASE)
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def create_table():
    connection = connect_database()
    cursor = connection.cursor()

    # Resources table
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS resources (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            subject TEXT NOT NULL,
            title TEXT NOT NULL,
            resource_type TEXT NOT NULL,
            link TEXT NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            is_favorite INTEGER NOT NULL DEFAULT 0,
            created_by INTEGER
        )
        """
    )

    # Migrate older resource databases.
    cursor.execute("PRAGMA table_info(resources)")

    resource_columns = [
        column[1]
        for column in cursor.fetchall()
    ]

    if "description" not in resource_columns:
        cursor.execute(
            """
            ALTER TABLE resources
            ADD COLUMN description TEXT NOT NULL DEFAULT ''
            """
        )

    if "is_favorite" not in resource_columns:
        cursor.execute(
            """
            ALTER TABLE resources
            ADD COLUMN is_favorite INTEGER NOT NULL DEFAULT 0
            """
        )

    if "created_by" not in resource_columns:
        cursor.execute(
            """
            ALTER TABLE resources
            ADD COLUMN created_by INTEGER
            """
        )

    # Users table
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'student',
            created_at TEXT NOT NULL
        )
        """
    )

    # Sessions table
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS sessions (
            token TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL,
            expires_at TEXT NOT NULL
        )
        """
    )

    connection.commit()

    bootstrap_admin(connection)

    connection.close()


def bootstrap_admin(connection):
    """
    Optional admin bootstrap.

    Set these before starting the application:

        export ADMIN_USERNAME=admin
        export ADMIN_PASSWORD=your-password

    If the user does not exist, an admin account is created.
    If the user already exists, it is promoted to admin.
    """

    admin_username = os.getenv("ADMIN_USERNAME", "").strip()
    admin_password = os.getenv("ADMIN_PASSWORD", "")

    if not admin_username or not admin_password:
        return

    if not re.fullmatch(
        r"[A-Za-z0-9_]{3,30}",
        admin_username,
    ):
        return

    if len(admin_password) < 8:
        return

    cursor = connection.cursor()

    cursor.execute(
        "SELECT id FROM users WHERE username = ?",
        (admin_username,),
    )

    existing_user = cursor.fetchone()

    if existing_user is None:
        cursor.execute(
            """
            INSERT INTO users (
                username,
                password_hash,
                role,
                created_at
            )
            VALUES (?, ?, ?, ?)
            """,
            (
                admin_username,
                hash_password(admin_password),
                "admin",
                datetime.now(timezone.utc).isoformat(),
            ),
        )
    else:
        cursor.execute(
            """
            UPDATE users
            SET role = 'admin'
            WHERE username = ?
            """,
            (admin_username,),
        )

    connection.commit()


# ---------------------------------------------------------
# Password security
# ---------------------------------------------------------

def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)

    password_hash = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        PASSWORD_ITERATIONS,
    )

    return (
        f"pbkdf2_sha256${PASSWORD_ITERATIONS}"
        f"${salt}${password_hash.hex()}"
    )


def verify_password(
    password: str,
    stored_hash: str,
) -> bool:
    try:
        (
            algorithm,
            iterations,
            salt,
            expected_hash,
        ) = stored_hash.split("$")

        if algorithm != "pbkdf2_sha256":
            return False

        password_hash = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            salt.encode("utf-8"),
            int(iterations),
        )

        return hmac.compare_digest(
            password_hash.hex(),
            expected_hash,
        )

    except (ValueError, TypeError):
        return False


# ---------------------------------------------------------
# Sessions / authentication
# ---------------------------------------------------------

def create_session(user_id: int) -> str:
    token = secrets.token_urlsafe(32)

    expires_at = (
        datetime.now(timezone.utc)
        + timedelta(days=SESSION_DAYS)
    ).isoformat()

    connection = connect_database()
    cursor = connection.cursor()

    cursor.execute(
        """
        INSERT INTO sessions (
            token,
            user_id,
            expires_at
        )
        VALUES (?, ?, ?)
        """,
        (
            token,
            user_id,
            expires_at,
        ),
    )

    connection.commit()
    connection.close()

    return token


def get_current_user(request: Request):
    token = request.cookies.get("session_token")

    if not token:
        raise HTTPException(
            status_code=401,
            detail="Authentication required",
        )

    connection = connect_database()
    connection.row_factory = sqlite3.Row
    cursor = connection.cursor()

    now = datetime.now(timezone.utc).isoformat()

    # Remove expired sessions.
    cursor.execute(
        """
        DELETE FROM sessions
        WHERE expires_at <= ?
        """,
        (now,),
    )

    connection.commit()

    cursor.execute(
        """
        SELECT
            users.id,
            users.username,
            users.role,
            users.created_at
        FROM sessions
        JOIN users
            ON users.id = sessions.user_id
        WHERE sessions.token = ?
          AND sessions.expires_at > ?
        """,
        (
            token,
            now,
        ),
    )

    user = cursor.fetchone()

    connection.close()

    if user is None:
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired session",
        )

    if user["role"] not in VALID_ROLES:
        raise HTTPException(
            status_code=403,
            detail="Invalid user role",
        )

    return dict(user)


def get_admin_user(
    current_user=Depends(get_current_user),
):
    if current_user["role"] != "admin":
        raise HTTPException(
            status_code=403,
            detail="Administrator access required",
        )

    return current_user


def set_session_cookie(
    response,
    token: str,
):
    response.set_cookie(
        key="session_token",
        value=token,
        max_age=SESSION_DAYS * 24 * 60 * 60,
        httponly=True,
        samesite="lax",
        secure=False,
    )


# ---------------------------------------------------------
# CLI helpers
# ---------------------------------------------------------

def get_required_input(prompt):
    while True:
        value = input(prompt).strip()

        if value:
            return value

        print(
            "This field cannot be empty. Please try again."
        )


def get_optional_input(prompt):
    return input(prompt).strip()


def add_resource():
    print("\n--- Add Resource ---")

    subject = get_required_input("Subject: ")
    title = get_required_input("Title: ")
    resource_type = get_required_input("Type: ")
    link = get_required_input("Link: ")
    description = get_optional_input("Description: ")

    connection = connect_database()
    cursor = connection.cursor()

    cursor.execute(
        """
        INSERT INTO resources (
            subject,
            title,
            resource_type,
            link,
            description
        )
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            subject,
            title,
            resource_type,
            link,
            description,
        ),
    )

    connection.commit()
    connection.close()

    print("Resource added successfully!")


def view_resources():
    connection = connect_database()
    cursor = connection.cursor()

    cursor.execute(
        """
        SELECT
            id,
            subject,
            title,
            resource_type,
            link,
            description,
            is_favorite,
            created_by
        FROM resources
        ORDER BY id
        """
    )

    resources = cursor.fetchall()

    connection.close()

    print("\n--- All Resources ---")

    if not resources:
        print("No resources available.")
        return

    for resource in resources:
        (
            resource_id,
            subject,
            title,
            resource_type,
            link,
            description,
            is_favorite,
            created_by,
        ) = resource

        print(f"\nResource #{resource_id}")
        print(f"Subject: {subject}")
        print(f"Title: {title}")
        print(f"Type: {resource_type}")
        print(f"Link: {link}")
        print(
            "Description: "
            f"{description or 'No description provided.'}"
        )
        print(
            f"Favorite: {'Yes' if is_favorite else 'No'}"
        )
        print(f"Created by user ID: {created_by}")


def search_resources():
    print("\n--- Search Resources ---")

    keyword = get_required_input("Search: ")

    connection = connect_database()
    cursor = connection.cursor()

    search_term = f"%{keyword}%"

    cursor.execute(
        """
        SELECT
            id,
            subject,
            title,
            resource_type,
            link,
            description,
            is_favorite,
            created_by
        FROM resources
        WHERE subject LIKE ?
           OR title LIKE ?
           OR resource_type LIKE ?
           OR description LIKE ?
        ORDER BY id
        """,
        (
            search_term,
            search_term,
            search_term,
            search_term,
        ),
    )

    resources = cursor.fetchall()

    connection.close()

    if not resources:
        print("No matching resources found.")
        return

    print(
        f"\nFound {len(resources)} resource(s):"
    )

    for resource in resources:
        (
            resource_id,
            subject,
            title,
            resource_type,
            link,
            description,
            is_favorite,
            created_by,
        ) = resource

        print(f"\nResource #{resource_id}")
        print(f"Subject: {subject}")
        print(f"Title: {title}")
        print(f"Type: {resource_type}")
        print(f"Link: {link}")
        print(
            "Description: "
            f"{description or 'No description provided.'}"
        )
        print(
            f"Favorite: {'Yes' if is_favorite else 'No'}"
        )
        print(f"Created by user ID: {created_by}")


def update_resource():
    print("\n--- Update Resource ---")

    resource_id = get_required_input(
        "Enter resource ID: "
    )

    connection = connect_database()
    cursor = connection.cursor()

    cursor.execute(
        """
        SELECT
            id,
            subject,
            title,
            resource_type,
            link,
            description
        FROM resources
        WHERE id = ?
        """,
        (resource_id,),
    )

    resource = cursor.fetchone()

    if resource is None:
        connection.close()
        print("Resource not found.")
        return

    print("\nCurrent resource:")
    print(f"Subject: {resource[1]}")
    print(f"Title: {resource[2]}")
    print(f"Type: {resource[3]}")
    print(f"Link: {resource[4]}")
    print(
        "Description: "
        f"{resource[5] or 'No description provided.'}"
    )

    print("\nEnter the new information.")

    new_subject = get_required_input(
        "New subject: "
    )
    new_title = get_required_input(
        "New title: "
    )
    new_type = get_required_input(
        "New type: "
    )
    new_link = get_required_input(
        "New link: "
    )
    new_description = get_optional_input(
        "New description: "
    )

    cursor.execute(
        """
        UPDATE resources
        SET subject = ?,
            title = ?,
            resource_type = ?,
            link = ?,
            description = ?
        WHERE id = ?
        """,
        (
            new_subject,
            new_title,
            new_type,
            new_link,
            new_description,
            resource_id,
        ),
    )

    connection.commit()
    connection.close()

    print("Resource updated successfully!")


def delete_resource():
    print("\n--- Delete Resource ---")

    resource_id = get_required_input(
        "Enter resource ID: "
    )

    connection = connect_database()
    cursor = connection.cursor()

    cursor.execute(
        """
        SELECT title
        FROM resources
        WHERE id = ?
        """,
        (resource_id,),
    )

    resource = cursor.fetchone()

    if resource is None:
        connection.close()
        print("Resource not found.")
        return

    confirm = input(
        f'Delete "{resource[0]}"? (y/n): '
    ).strip().lower()

    if confirm != "y":
        connection.close()
        print("Deletion cancelled.")
        return

    cursor.execute(
        """
        DELETE FROM resources
        WHERE id = ?
        """,
        (resource_id,),
    )

    connection.commit()
    connection.close()

    print("Resource deleted successfully!")


# ---------------------------------------------------------
# Application startup
# ---------------------------------------------------------

create_table()


# ---------------------------------------------------------
# Basic endpoints
# ---------------------------------------------------------

@app.get(
    "/",
    response_class=HTMLResponse,
)
def home(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={},
    )


@app.get("/health")
def health_check():
    return {
        "status": "ok"
    }


# ---------------------------------------------------------
# Authentication
# ---------------------------------------------------------

@app.post(
    "/register",
    status_code=201,
)
def register_user(
    data: RegisterRequest,
):
    connection = connect_database()
    cursor = connection.cursor()

    cursor.execute(
        """
        SELECT id
        FROM users
        WHERE username = ?
        """,
        (data.username,),
    )

    existing_user = cursor.fetchone()

    if existing_user is not None:
        connection.close()

        raise HTTPException(
            status_code=409,
            detail="Username already exists",
        )

    created_at = (
        datetime.now(timezone.utc).isoformat()
    )

    cursor.execute(
        """
        INSERT INTO users (
            username,
            password_hash,
            role,
            created_at
        )
        VALUES (?, ?, ?, ?)
        """,
        (
            data.username,
            hash_password(data.password),
            "student",
            created_at,
        ),
    )

    user_id = cursor.lastrowid

    connection.commit()
    connection.close()

    return {
        "message": "Registration successful",
        "id": user_id,
        "username": data.username,
        "role": "student",
    }


@app.post("/login")
def login_user(
    data: LoginRequest,
):
    connection = connect_database()
    connection.row_factory = sqlite3.Row
    cursor = connection.cursor()

    cursor.execute(
        """
        SELECT
            id,
            username,
            password_hash,
            role
        FROM users
        WHERE username = ?
        """,
        (data.username.strip(),),
    )

    user = cursor.fetchone()

    connection.close()

    if user is None:
        raise HTTPException(
            status_code=401,
            detail="Invalid username or password",
        )

    if not verify_password(
        data.password,
        user["password_hash"],
    ):
        raise HTTPException(
            status_code=401,
            detail="Invalid username or password",
        )

    token = create_session(user["id"])

    response = JSONResponse(
        {
            "message": "Login successful",
            "username": user["username"],
            "role": user["role"],
        }
    )

    set_session_cookie(
        response,
        token,
    )

    return response


@app.post("/logout")
def logout_user(request: Request):
    token = request.cookies.get("session_token")

    if token:
        connection = connect_database()
        cursor = connection.cursor()

        cursor.execute(
            """
            DELETE FROM sessions
            WHERE token = ?
            """,
            (token,),
        )

        connection.commit()
        connection.close()

    response = JSONResponse(
        {
            "message": "Logged out successfully"
        }
    )

    response.delete_cookie(
        "session_token"
    )

    return response


@app.get("/me")
def get_me(
    current_user=Depends(get_current_user),
):
    return {
        "id": current_user["id"],
        "username": current_user["username"],
        "role": current_user["role"],
        "created_at": current_user["created_at"],
    }


# ---------------------------------------------------------
# Admin / user management
# ---------------------------------------------------------

@app.get("/users")
def get_users(
    current_user=Depends(get_admin_user),
):
    connection = connect_database()
    connection.row_factory = sqlite3.Row
    cursor = connection.cursor()

    cursor.execute(
        """
        SELECT
            id,
            username,
            role,
            created_at
        FROM users
        ORDER BY id
        """
    )

    users = [
        dict(row)
        for row in cursor.fetchall()
    ]

    connection.close()

    return users


@app.patch("/users/{user_id}/role")
def update_user_role(
    user_id: int,
    data: RoleUpdateRequest,
    current_user=Depends(get_admin_user),
):
    if data.role not in VALID_ROLES:
        raise HTTPException(
            status_code=422,
            detail="Invalid role",
        )

    if user_id == current_user["id"]:
        raise HTTPException(
            status_code=400,
            detail="You cannot change your own role",
        )

    connection = connect_database()
    connection.row_factory = sqlite3.Row
    cursor = connection.cursor()

    cursor.execute(
        """
        SELECT
            id,
            username,
            role
        FROM users
        WHERE id = ?
        """,
        (user_id,),
    )

    user = cursor.fetchone()

    if user is None:
        connection.close()

        raise HTTPException(
            status_code=404,
            detail="User not found",
        )

    cursor.execute(
        """
        UPDATE users
        SET role = ?
        WHERE id = ?
        """,
        (
            data.role,
            user_id,
        ),
    )

    connection.commit()

    cursor.execute(
        """
        SELECT
            id,
            username,
            role,
            created_at
        FROM users
        WHERE id = ?
        """,
        (user_id,),
    )

    updated_user = cursor.fetchone()

    connection.close()

    return {
        "message": "User role updated successfully",
        "user": dict(updated_user),
    }


# ---------------------------------------------------------
# Resources
# ---------------------------------------------------------

@app.get("/resources")
def get_resources(
    favorite: bool = False,
    resource_type: str | None = Query(
        default=None,
        alias="type",
    ),
):
    connection = connect_database()
    connection.row_factory = sqlite3.Row
    cursor = connection.cursor()

    query = """
        SELECT
            resources.id,
            resources.subject,
            resources.title,
            resources.resource_type,
            resources.link,
            resources.description,
            resources.is_favorite,
            resources.created_by
        FROM resources
    """

    conditions = []
    parameters = []

    if favorite:
        conditions.append(
            "resources.is_favorite = 1"
        )

    if resource_type:
        conditions.append(
            """
            LOWER(resources.resource_type)
            = LOWER(?)
            """
        )

        parameters.append(
            resource_type.strip()
        )

    if conditions:
        query += (
            " WHERE "
            + " AND ".join(conditions)
        )

    query += " ORDER BY resources.id"

    cursor.execute(
        query,
        parameters,
    )

    resources = []

    for row in cursor.fetchall():
        resource = dict(row)

        resource["is_favorite"] = bool(
            resource["is_favorite"]
        )

        resources.append(resource)

    connection.close()

    return resources


@app.get("/resources/{resource_id}")
def get_resource(
    resource_id: int,
):
    connection = connect_database()
    connection.row_factory = sqlite3.Row
    cursor = connection.cursor()

    cursor.execute(
        """
        SELECT
            id,
            subject,
            title,
            resource_type,
            link,
            description,
            is_favorite,
            created_by
        FROM resources
        WHERE id = ?
        """,
        (resource_id,),
    )

    resource = cursor.fetchone()

    connection.close()

    if resource is None:
        raise HTTPException(
            status_code=404,
            detail="Resource not found",
        )

    result = dict(resource)

    result["is_favorite"] = bool(
        result["is_favorite"]
    )

    return result


@app.post(
    "/resources",
    status_code=201,
)
def create_resource(
    resource: Resource,
    current_user=Depends(get_current_user),
):
    connection = connect_database()
    cursor = connection.cursor()

    cursor.execute(
        """
        INSERT INTO resources (
            subject,
            title,
            resource_type,
            link,
            description,
            created_by
        )
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            resource.subject,
            resource.title,
            resource.resource_type,
            resource.link,
            resource.description,
            current_user["id"],
        ),
    )

    resource_id = cursor.lastrowid

    connection.commit()
    connection.close()

    return {
        "message": "Resource created successfully",
        "id": resource_id,
        "created_by": current_user["id"],
    }


@app.put("/resources/{resource_id}")
def update_resource_api(
    resource_id: int,
    resource: Resource,
    current_user=Depends(get_current_user),
):
    connection = connect_database()
    connection.row_factory = sqlite3.Row
    cursor = connection.cursor()

    cursor.execute(
        """
        SELECT
            id,
            created_by
        FROM resources
        WHERE id = ?
        """,
        (resource_id,),
    )

    existing_resource = cursor.fetchone()

    if existing_resource is None:
        connection.close()

        raise HTTPException(
            status_code=404,
            detail="Resource not found",
        )

    # Students may edit only resources they created.
    if (
        current_user["role"] != "admin"
        and existing_resource["created_by"]
        != current_user["id"]
    ):
        connection.close()

        raise HTTPException(
            status_code=403,
            detail=(
                "You can only edit resources "
                "you created"
            ),
        )

    cursor.execute(
        """
        UPDATE resources
        SET subject = ?,
            title = ?,
            resource_type = ?,
            link = ?,
            description = ?
        WHERE id = ?
        """,
        (
            resource.subject,
            resource.title,
            resource.resource_type,
            resource.link,
            resource.description,
            resource_id,
        ),
    )

    connection.commit()
    connection.close()

    return {
        "message": "Resource updated successfully",
        "id": resource_id,
    }


@app.patch(
    "/resources/{resource_id}/favorite"
)
def toggle_favorite(
    resource_id: int,
    current_user=Depends(get_current_user),
):
    connection = connect_database()
    connection.row_factory = sqlite3.Row
    cursor = connection.cursor()

    cursor.execute(
        """
        SELECT
            id,
            is_favorite
        FROM resources
        WHERE id = ?
        """,
        (resource_id,),
    )

    resource = cursor.fetchone()

    if resource is None:
        connection.close()

        raise HTTPException(
            status_code=404,
            detail="Resource not found",
        )

    new_status = (
        0
        if resource["is_favorite"]
        else 1
    )

    cursor.execute(
        """
        UPDATE resources
        SET is_favorite = ?
        WHERE id = ?
        """,
        (
            new_status,
            resource_id,
        ),
    )

    connection.commit()
    connection.close()

    return {
        "message": "Favorite status updated",
        "id": resource_id,
        "is_favorite": bool(new_status),
    }


@app.delete("/resources/{resource_id}")
def delete_resource_api(
    resource_id: int,
    current_user=Depends(get_admin_user),
):
    connection = connect_database()
    cursor = connection.cursor()

    cursor.execute(
        """
        SELECT id
        FROM resources
        WHERE id = ?
        """,
        (resource_id,),
    )

    existing_resource = cursor.fetchone()

    if existing_resource is None:
        connection.close()

        raise HTTPException(
            status_code=404,
            detail="Resource not found",
        )

    cursor.execute(
        """
        DELETE FROM resources
        WHERE id = ?
        """,
        (resource_id,),
    )

    connection.commit()
    connection.close()

    return {
        "message": "Resource deleted successfully",
        "id": resource_id,
    }


@app.get(
    "/resources/search/{keyword}"
)
def search_resources_api(
    keyword: str,
):
    connection = connect_database()
    connection.row_factory = sqlite3.Row
    cursor = connection.cursor()

    search_term = f"%{keyword}%"

    cursor.execute(
        """
        SELECT
            id,
            subject,
            title,
            resource_type,
            link,
            description,
            is_favorite,
            created_by
        FROM resources
        WHERE subject LIKE ?
           OR title LIKE ?
           OR resource_type LIKE ?
           OR description LIKE ?
        ORDER BY id
        """,
        (
            search_term,
            search_term,
            search_term,
            search_term,
        ),
    )

    resources = []

    for row in cursor.fetchall():
        resource = dict(row)

        resource["is_favorite"] = bool(
            resource["is_favorite"]
        )

        resources.append(resource)

    connection.close()

    return resources


# ---------------------------------------------------------
# Main
# ---------------------------------------------------------

def main():
    print("Campus Knowledge Hub")
    print("Use FastAPI to run the web application.")


if __name__ == "__main__":
    main()