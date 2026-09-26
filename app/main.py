import hashlib
import hmac
import os
import re
import secrets
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Literal
from urllib.parse import urlparse

from fastapi import (
    Depends,
    FastAPI,
    File,
    HTTPException,
    Query,
    Request,
    Response,
    UploadFile,
)
from fastapi.responses import (
    FileResponse,
    HTMLResponse,
    JSONResponse,
)
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field, field_validator


# =========================================================
# CONFIGURATION
# =========================================================

DATABASE = "campus.db"

UPLOAD_DIR = "uploads"

MAX_UPLOAD_SIZE = 10 * 1024 * 1024  # 10 MB

ALLOWED_FILE_EXTENSION = ".pdf"

ALLOWED_CONTENT_TYPE = "application/pdf"

SESSION_DAYS = 7

PASSWORD_ITERATIONS = 310_000

VALID_ROLES = {
    "student",
    "admin",
}


# =========================================================
# FASTAPI APP
# =========================================================

app = FastAPI(
    title="Campus Knowledge Hub",
    description="API for managing college learning resources",
    version="1.3.0",
)

templates = Jinja2Templates(
    directory="templates"
)


# =========================================================
# PYDANTIC MODELS
# =========================================================

class RegisterRequest(BaseModel):
    username: str = Field(
        min_length=3,
        max_length=30,
    )

    password: str = Field(
        min_length=8,
        max_length=128,
    )

    @field_validator("username")
    @classmethod
    def validate_username(
        cls,
        value: str,
    ) -> str:
        value = value.strip()

        if not re.fullmatch(
            r"[A-Za-z0-9_]{3,30}",
            value,
        ):
            raise ValueError(
                "Username must contain only letters, "
                "numbers, and underscores"
            )

        return value


class LoginRequest(BaseModel):
    username: str
    password: str


class Resource(BaseModel):
    subject: str = Field(
        min_length=1,
    )

    title: str = Field(
        min_length=1,
    )

    resource_type: str = Field(
        min_length=1,
    )

    link: str = Field(
        min_length=1,
    )

    description: str = Field(
        default="",
        max_length=500,
    )

    @field_validator(
        "subject",
        "title",
        "resource_type",
        "link",
    )
    @classmethod
    def validate_text(
        cls,
        value: str,
    ) -> str:
        value = value.strip()

        if not value:
            raise ValueError(
                "Field cannot be empty"
            )

        return value

    @field_validator("description")
    @classmethod
    def validate_description(
        cls,
        value: str,
    ) -> str:
        return value.strip()

    @field_validator("link")
    @classmethod
    def validate_link(
        cls,
        value: str,
    ) -> str:
        parsed_url = urlparse(value)

        if (
            parsed_url.scheme
            not in ("http", "https")
            or not parsed_url.netloc
        ):
            raise ValueError(
                "Link must be a valid HTTP or HTTPS URL"
            )

        return value


class RoleUpdateRequest(BaseModel):
    role: Literal[
        "student",
        "admin",
    ]


# =========================================================
# DATABASE
# =========================================================

def connect_database():
    connection = sqlite3.connect(
        DATABASE
    )

    connection.execute(
        "PRAGMA foreign_keys = ON"
    )

    return connection


# =========================================================
# PASSWORD SECURITY
# =========================================================

def hash_password(
    password: str,
) -> str:
    salt = secrets.token_hex(16)

    password_hash = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        PASSWORD_ITERATIONS,
    )

    return (
        f"pbkdf2_sha256"
        f"${PASSWORD_ITERATIONS}"
        f"${salt}"
        f"${password_hash.hex()}"
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

    except (
        ValueError,
        TypeError,
    ):
        return False


# =========================================================
# FILE HELPERS
# =========================================================

def ensure_upload_directory():
    Path(
        UPLOAD_DIR
    ).mkdir(
        parents=True,
        exist_ok=True,
    )


def generate_stored_filename():
    return (
        f"{secrets.token_hex(20)}"
        f"{ALLOWED_FILE_EXTENSION}"
    )


def safe_uploaded_filename(
    filename: str | None,
) -> str:
    if not filename:
        return "resource.pdf"

    cleaned = Path(filename).name

    if not cleaned.lower().endswith(
        ALLOWED_FILE_EXTENSION
    ):
        cleaned += ALLOWED_FILE_EXTENSION

    return cleaned[:255]


def get_stored_file_path(
    stored_filename: str,
) -> Path:
    upload_root = Path(
        UPLOAD_DIR
    ).resolve()

    file_path = (
        upload_root
        / stored_filename
    ).resolve()

    if upload_root not in file_path.parents:
        raise HTTPException(
            status_code=500,
            detail="Invalid stored file path",
        )

    return file_path


def delete_physical_file(
    stored_filename: str | None,
):
    if not stored_filename:
        return

    try:
        file_path = get_stored_file_path(
            stored_filename
        )

        if file_path.exists():
            file_path.unlink()

    except OSError:
        pass


# =========================================================
# DATABASE INITIALIZATION / MIGRATION
# =========================================================

def create_table():
    ensure_upload_directory()

    connection = connect_database()
    cursor = connection.cursor()

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
            created_by INTEGER,
            file_name TEXT,
            file_path TEXT,
            file_size INTEGER,
            file_content_type TEXT,
            uploaded_at TEXT
        )
        """
    )

    cursor.execute(
        "PRAGMA table_info(resources)"
    )

    resource_columns = [
        column[1]
        for column in cursor.fetchall()
    ]

    if "description" not in resource_columns:
        cursor.execute(
            """
            ALTER TABLE resources
            ADD COLUMN description
            TEXT NOT NULL DEFAULT ''
            """
        )

    if "is_favorite" not in resource_columns:
        cursor.execute(
            """
            ALTER TABLE resources
            ADD COLUMN is_favorite
            INTEGER NOT NULL DEFAULT 0
            """
        )

    if "created_by" not in resource_columns:
        cursor.execute(
            """
            ALTER TABLE resources
            ADD COLUMN created_by INTEGER
            """
        )

    if "file_name" not in resource_columns:
        cursor.execute(
            """
            ALTER TABLE resources
            ADD COLUMN file_name TEXT
            """
        )

    if "file_path" not in resource_columns:
        cursor.execute(
            """
            ALTER TABLE resources
            ADD COLUMN file_path TEXT
            """
        )

    if "file_size" not in resource_columns:
        cursor.execute(
            """
            ALTER TABLE resources
            ADD COLUMN file_size INTEGER
            """
        )

    if "file_content_type" not in resource_columns:
        cursor.execute(
            """
            ALTER TABLE resources
            ADD COLUMN file_content_type TEXT
            """
        )

    if "uploaded_at" not in resource_columns:
        cursor.execute(
            """
            ALTER TABLE resources
            ADD COLUMN uploaded_at TEXT
            """
        )

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

    bootstrap_admin(
        connection
    )

    connection.close()


def bootstrap_admin(
    connection,
):
    admin_username = os.getenv(
        "ADMIN_USERNAME",
        "",
    ).strip()

    admin_password = os.getenv(
        "ADMIN_PASSWORD",
        "",
    )

    if (
        not admin_username
        or not admin_password
    ):
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
        """
        SELECT id
        FROM users
        WHERE username = ?
        """,
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
                hash_password(
                    admin_password
                ),
                "admin",
                datetime.now(
                    timezone.utc
                ).isoformat(),
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


# =========================================================
# SESSION / AUTHENTICATION
# =========================================================

def create_session(
    user_id: int,
) -> str:
    token = secrets.token_urlsafe(
        32
    )

    expires_at = (
        datetime.now(
            timezone.utc
        )
        + timedelta(
            days=SESSION_DAYS
        )
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


def get_current_user(
    request: Request,
):
    token = request.cookies.get(
        "session_token"
    )

    if not token:
        raise HTTPException(
            status_code=401,
            detail="Authentication required",
        )

    connection = connect_database()
    connection.row_factory = sqlite3.Row
    cursor = connection.cursor()

    now = datetime.now(
        timezone.utc
    ).isoformat()

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
    current_user=Depends(
        get_current_user
    ),
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
        max_age=(
            SESSION_DAYS
            * 24
            * 60
            * 60
        ),
        httponly=True,
        samesite="lax",
        secure=False,
    )


# =========================================================
# RESOURCE PERMISSIONS
# =========================================================

def check_resource_modify_permission(
    resource,
    current_user,
):
    if current_user["role"] == "admin":
        return

    if (
        resource["created_by"]
        != current_user["id"]
    ):
        raise HTTPException(
            status_code=403,
            detail=(
                "You can only modify "
                "resources you created"
            ),
        )


# =========================================================
# CLI HELPERS
# =========================================================

def get_required_input(
    prompt,
):
    while True:
        value = input(
            prompt
        ).strip()

        if value:
            return value

        print(
            "This field cannot be empty. "
            "Please try again."
        )


def get_optional_input(
    prompt,
):
    return input(
        prompt
    ).strip()


def add_resource():
    print(
        "\n--- Add Resource ---"
    )

    subject = get_required_input(
        "Subject: "
    )

    title = get_required_input(
        "Title: "
    )

    resource_type = get_required_input(
        "Type: "
    )

    link = get_required_input(
        "Link: "
    )

    description = get_optional_input(
        "Description: "
    )

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

    print(
        "Resource added successfully!"
    )


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
            created_by,
            file_name,
            file_size
        FROM resources
        ORDER BY id
        """
    )

    resources = cursor.fetchall()

    connection.close()

    print(
        "\n--- All Resources ---"
    )

    if not resources:
        print(
            "No resources available."
        )
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
            file_name,
            file_size,
        ) = resource

        print(
            f"\nResource #{resource_id}"
        )

        print(
            f"Subject: {subject}"
        )

        print(
            f"Title: {title}"
        )

        print(
            f"Type: {resource_type}"
        )

        print(
            f"Link: {link}"
        )

        print(
            "Description: "
            f"{description or 'No description provided.'}"
        )

        print(
            f"Favorite: "
            f"{'Yes' if is_favorite else 'No'}"
        )

        print(
            f"Created by user ID: "
            f"{created_by}"
        )

        print(
            "Attached PDF: "
            f"{file_name or 'None'}"
        )

        if file_size is not None:
            print(
                f"File size: {file_size} bytes"
            )


def search_resources():
    print(
        "\n--- Search Resources ---"
    )

    keyword = get_required_input(
        "Search: "
    )

    connection = connect_database()
    cursor = connection.cursor()

    search_term = (
        f"%{keyword}%"
    )

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
            created_by,
            file_name,
            file_size
        FROM resources
        WHERE subject LIKE ?
           OR title LIKE ?
           OR resource_type LIKE ?
           OR description LIKE ?
           OR file_name LIKE ?
        ORDER BY id
        """,
        (
            search_term,
            search_term,
            search_term,
            search_term,
            search_term,
        ),
    )

    resources = cursor.fetchall()

    connection.close()

    if not resources:
        print(
            "No matching resources found."
        )
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
            file_name,
            file_size,
        ) = resource

        print(
            f"\nResource #{resource_id}"
        )

        print(
            f"Subject: {subject}"
        )

        print(
            f"Title: {title}"
        )

        print(
            f"Type: {resource_type}"
        )

        print(
            f"Link: {link}"
        )

        print(
            "Description: "
            f"{description or 'No description provided.'}"
        )

        print(
            "Attached PDF: "
            f"{file_name or 'None'}"
        )

        if file_size is not None:
            print(
                f"File size: {file_size} bytes"
            )


def update_resource():
    print(
        "\n--- Update Resource ---"
    )

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

        print(
            "Resource not found."
        )

        return

    print(
        "\nCurrent resource:"
    )

    print(
        f"Subject: {resource[1]}"
    )

    print(
        f"Title: {resource[2]}"
    )

    print(
        f"Type: {resource[3]}"
    )

    print(
        f"Link: {resource[4]}"
    )

    print(
        "Description: "
        f"{resource[5] or 'No description provided.'}"
    )

    print(
        "\nEnter the new information."
    )

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

    print(
        "Resource updated successfully!"
    )


def delete_resource():
    print(
        "\n--- Delete Resource ---"
    )

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

        print(
            "Resource not found."
        )

        return

    confirm = input(
        f'Delete "{resource[0]}"? (y/n): '
    ).strip().lower()

    if confirm != "y":
        connection.close()

        print(
            "Deletion cancelled."
        )

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

    print(
        "Resource deleted successfully!"
    )


# =========================================================
# STARTUP
# =========================================================

create_table()


# =========================================================
# BASIC ENDPOINTS
# =========================================================

@app.get(
    "/",
    response_class=HTMLResponse,
)
def home(
    request: Request,
):
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


# =========================================================
# AUTHENTICATION
# =========================================================

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

    existing_user = (
        cursor.fetchone()
    )

    if existing_user is not None:
        connection.close()

        raise HTTPException(
            status_code=409,
            detail="Username already exists",
        )

    created_at = (
        datetime.now(
            timezone.utc
        ).isoformat()
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
            hash_password(
                data.password
            ),
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

    token = create_session(
        user["id"]
    )

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
def logout_user(
    request: Request,
):
    token = request.cookies.get(
        "session_token"
    )

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
            "message": (
                "Logged out successfully"
            )
        }
    )

    response.delete_cookie(
        "session_token"
    )

    return response


@app.get("/me")
def get_me(
    current_user=Depends(
        get_current_user
    ),
):
    return {
        "id": current_user["id"],
        "username": current_user["username"],
        "role": current_user["role"],
        "created_at": current_user["created_at"],
    }


# =========================================================
# ADMIN USER MANAGEMENT
# =========================================================

@app.get("/users")
def get_users(
    current_user=Depends(
        get_admin_user
    ),
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


@app.patch(
    "/users/{user_id}/role"
)
def update_user_role(
    user_id: int,
    data: RoleUpdateRequest,
    current_user=Depends(
        get_admin_user
    ),
):
    if data.role not in VALID_ROLES:
        raise HTTPException(
            status_code=422,
            detail="Invalid role",
        )

    if user_id == current_user["id"]:
        raise HTTPException(
            status_code=400,
            detail=(
                "You cannot change "
                "your own role"
            ),
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

    updated_user = (
        cursor.fetchone()
    )

    connection.close()

    return {
        "message": (
            "User role updated successfully"
        ),
        "user": dict(
            updated_user
        ),
    }


# =========================================================
# RESOURCE LIST
# =========================================================

@app.get("/resources")
def get_resources(
    response: Response,
    favorite: bool = False,
    resource_type: str | None = Query(
        default=None,
        alias="type",
    ),
    page: int = Query(
        default=1,
        ge=1,
    ),
    limit: int = Query(
        default=10,
        ge=1,
        le=100,
    ),
    sort_by: Literal[
        "id",
        "title",
    ] = Query(
        default="id",
    ),
    order: Literal[
        "asc",
        "desc",
    ] = Query(
        default="asc",
    ),
):
    connection = connect_database()
    connection.row_factory = sqlite3.Row
    cursor = connection.cursor()

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

    where_clause = ""

    if conditions:
        where_clause = (
            " WHERE "
            + " AND ".join(
                conditions
            )
        )

    cursor.execute(
        f"""
        SELECT COUNT(*)
        FROM resources
        {where_clause}
        """,
        parameters,
    )

    total = cursor.fetchone()[0]

    sort_column = {
        "id": "resources.id",
        "title": "resources.title",
    }[sort_by]

    sort_order = (
        "DESC"
        if order == "desc"
        else "ASC"
    )

    offset = (
        (page - 1)
        * limit
    )

    cursor.execute(
        f"""
        SELECT
            resources.id,
            resources.subject,
            resources.title,
            resources.resource_type,
            resources.link,
            resources.description,
            resources.is_favorite,
            resources.created_by,
            resources.file_name,
            resources.file_size,
            resources.file_content_type,
            resources.uploaded_at
        FROM resources
        {where_clause}
        ORDER BY
            {sort_column}
            {sort_order},
            resources.id
            {sort_order}
        LIMIT ?
        OFFSET ?
        """,
        parameters + [
            limit,
            offset,
        ],
    )

    resources = []

    for row in cursor.fetchall():
        resource = dict(row)

        resource["is_favorite"] = bool(
            resource["is_favorite"]
        )

        resource["has_file"] = bool(
            resource.get("file_name")
        )

        resources.append(
            resource
        )

    connection.close()

    pages = (
        (total + limit - 1) // limit
        if total > 0
        else 0
    )

    response.headers["X-Page"] = str(page)
    response.headers["X-Limit"] = str(limit)
    response.headers["X-Total"] = str(total)
    response.headers["X-Pages"] = str(pages)
    response.headers["X-Sort-By"] = sort_by
    response.headers["X-Order"] = order

    return resources


# =========================================================
# SINGLE RESOURCE
# =========================================================

@app.get(
    "/resources/{resource_id}"
)
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
            created_by,
            file_name,
            file_size,
            file_content_type,
            uploaded_at,
            file_path
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

    result["has_file"] = bool(
        result.get("file_name")
    )

    result.pop(
        "file_path",
        None,
    )

    return result


# =========================================================
# CREATE RESOURCE
# =========================================================

@app.post(
    "/resources",
    status_code=201,
)
def create_resource(
    resource: Resource,
    current_user=Depends(
        get_current_user
    ),
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
        "message": (
            "Resource created successfully"
        ),
        "id": resource_id,
        "created_by": current_user["id"],
    }


# =========================================================
# UPDATE RESOURCE
# =========================================================

@app.put(
    "/resources/{resource_id}"
)
def update_resource_api(
    resource_id: int,
    resource: Resource,
    current_user=Depends(
        get_current_user
    ),
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

    existing_resource = (
        cursor.fetchone()
    )

    if existing_resource is None:
        connection.close()

        raise HTTPException(
            status_code=404,
            detail="Resource not found",
        )

    try:
        check_resource_modify_permission(
            existing_resource,
            current_user,
        )
    except HTTPException:
        connection.close()
        raise

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
        "message": (
            "Resource updated successfully"
        ),
        "id": resource_id,
    }


# =========================================================
# FAVORITE
# =========================================================

@app.patch(
    "/resources/{resource_id}/favorite"
)
def toggle_favorite(
    resource_id: int,
    current_user=Depends(
        get_current_user
    ),
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
        "message": (
            "Favorite status updated"
        ),
        "id": resource_id,
        "is_favorite": bool(
            new_status
        ),
    }


# =========================================================
# DELETE RESOURCE
# ADMIN ONLY
# =========================================================

@app.delete(
    "/resources/{resource_id}"
)
def delete_resource_api(
    resource_id: int,
    current_user=Depends(
        get_admin_user
    ),
):
    connection = connect_database()
    connection.row_factory = sqlite3.Row
    cursor = connection.cursor()

    cursor.execute(
        """
        SELECT
            id,
            file_path
        FROM resources
        WHERE id = ?
        """,
        (resource_id,),
    )

    existing_resource = (
        cursor.fetchone()
    )

    if existing_resource is None:
        connection.close()

        raise HTTPException(
            status_code=404,
            detail="Resource not found",
        )

    old_file_path = (
        existing_resource["file_path"]
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

    delete_physical_file(
        old_file_path
    )

    return {
        "message": (
            "Resource deleted successfully"
        ),
        "id": resource_id,
    }


# =========================================================
# SEARCH
# =========================================================

@app.get(
    "/resources/search/{keyword}"
)
def search_resources_api(
    keyword: str,
):
    connection = connect_database()
    connection.row_factory = sqlite3.Row
    cursor = connection.cursor()

    search_term = (
        f"%{keyword}%"
    )

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
            created_by,
            file_name,
            file_size,
            file_content_type,
            uploaded_at
        FROM resources
        WHERE subject LIKE ?
           OR title LIKE ?
           OR resource_type LIKE ?
           OR description LIKE ?
           OR file_name LIKE ?
        ORDER BY id
        """,
        (
            search_term,
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

        resource["has_file"] = bool(
            resource.get("file_name")
        )

        resources.append(
            resource
        )

    connection.close()

    return resources


# =========================================================
# PDF UPLOAD
# =========================================================

@app.post(
    "/resources/{resource_id}/file",
    status_code=201,
)
async def upload_resource_file(
    resource_id: int,
    file: UploadFile = File(...),
    current_user=Depends(
        get_current_user
    ),
):
    if (
        file.content_type
        != ALLOWED_CONTENT_TYPE
    ):
        await file.close()

        raise HTTPException(
            status_code=415,
            detail="Only PDF files are allowed",
        )

    original_filename = (
        safe_uploaded_filename(
            file.filename
        )
    )

    if not original_filename.lower().endswith(
        ALLOWED_FILE_EXTENSION
    ):
        await file.close()

        raise HTTPException(
            status_code=415,
            detail="Only .pdf files are allowed",
        )

    connection = connect_database()
    connection.row_factory = sqlite3.Row
    cursor = connection.cursor()

    cursor.execute(
        """
        SELECT
            id,
            created_by,
            file_path,
            file_name
        FROM resources
        WHERE id = ?
        """,
        (resource_id,),
    )

    resource = cursor.fetchone()

    if resource is None:
        connection.close()
        await file.close()

        raise HTTPException(
            status_code=404,
            detail="Resource not found",
        )

    try:
        check_resource_modify_permission(
            resource,
            current_user,
        )
    except HTTPException:
        connection.close()
        await file.close()
        raise

    ensure_upload_directory()

    stored_filename = (
        generate_stored_filename()
    )

    destination = (
        get_stored_file_path(
            stored_filename
        )
    )

    total_size = 0
    first_chunk = b""

    try:
        with destination.open(
            "wb"
        ) as output_file:

            while True:
                chunk = await file.read(
                    1024 * 1024
                )

                if not chunk:
                    break

                if not first_chunk:
                    first_chunk = chunk[:5]

                total_size += len(chunk)

                if (
                    total_size
                    > MAX_UPLOAD_SIZE
                ):
                    raise HTTPException(
                        status_code=413,
                        detail=(
                            "File size exceeds "
                            "the 10 MB limit"
                        ),
                    )

                output_file.write(
                    chunk
                )

    except HTTPException:
        if destination.exists():
            destination.unlink()

        connection.close()
        await file.close()

        raise

    except OSError as exc:
        if destination.exists():
            destination.unlink()

        connection.close()
        await file.close()

        raise HTTPException(
            status_code=500,
            detail=(
                "Unable to save uploaded file"
            ),
        ) from exc

    finally:
        await file.close()

    if first_chunk != b"%PDF-":
        if destination.exists():
            destination.unlink()

        connection.close()

        raise HTTPException(
            status_code=415,
            detail=(
                "Uploaded file does not "
                "contain a valid PDF signature"
            ),
        )

    old_file_path = (
        resource["file_path"]
    )

    uploaded_at = (
        datetime.now(
            timezone.utc
        ).isoformat()
    )

    cursor.execute(
        """
        UPDATE resources
        SET file_name = ?,
            file_path = ?,
            file_size = ?,
            file_content_type = ?,
            uploaded_at = ?
        WHERE id = ?
        """,
        (
            original_filename,
            stored_filename,
            total_size,
            ALLOWED_CONTENT_TYPE,
            uploaded_at,
            resource_id,
        ),
    )

    connection.commit()
    connection.close()

    if (
        old_file_path
        and old_file_path
        != stored_filename
    ):
        delete_physical_file(
            old_file_path
        )

    return {
        "message": (
            "PDF uploaded successfully"
        ),
        "resource_id": resource_id,
        "file_name": original_filename,
        "file_size": total_size,
        "content_type": ALLOWED_CONTENT_TYPE,
        "uploaded_at": uploaded_at,
    }


# =========================================================
# PDF DOWNLOAD
# =========================================================

@app.get(
    "/resources/{resource_id}/file"
)
def download_resource_file(
    resource_id: int,
):
    connection = connect_database()
    connection.row_factory = sqlite3.Row
    cursor = connection.cursor()

    cursor.execute(
        """
        SELECT
            id,
            title,
            file_name,
            file_path,
            file_content_type
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

    stored_file = (
        resource["file_path"]
    )

    if not stored_file:
        raise HTTPException(
            status_code=404,
            detail=(
                "No file is attached "
                "to this resource"
            ),
        )

    file_path = get_stored_file_path(
        stored_file
    )

    if not file_path.is_file():
        raise HTTPException(
            status_code=404,
            detail="Attached file is missing",
        )

    return FileResponse(
        path=file_path,
        media_type=(
            resource["file_content_type"]
            or ALLOWED_CONTENT_TYPE
        ),
        filename=(
            resource["file_name"]
            or "resource.pdf"
        ),
    )


# =========================================================
# PDF DELETE
# =========================================================

@app.delete(
    "/resources/{resource_id}/file"
)
def delete_resource_file(
    resource_id: int,
    current_user=Depends(
        get_current_user
    ),
):
    connection = connect_database()
    connection.row_factory = sqlite3.Row
    cursor = connection.cursor()

    cursor.execute(
        """
        SELECT
            id,
            created_by,
            file_path,
            file_name
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

    try:
        check_resource_modify_permission(
            resource,
            current_user,
        )
    except HTTPException:
        connection.close()
        raise

    if not resource["file_path"]:
        connection.close()

        raise HTTPException(
            status_code=404,
            detail=(
                "No file is attached "
                "to this resource"
            ),
        )

    old_file_path = (
        resource["file_path"]
    )

    cursor.execute(
        """
        UPDATE resources
        SET file_name = NULL,
            file_path = NULL,
            file_size = NULL,
            file_content_type = NULL,
            uploaded_at = NULL
        WHERE id = ?
        """,
        (resource_id,),
    )

    connection.commit()
    connection.close()

    delete_physical_file(
        old_file_path
    )

    return {
        "message": (
            "PDF deleted successfully"
        ),
        "resource_id": resource_id,
    }


# =========================================================
# MAIN
# =========================================================

def main():
    print(
        "Campus Knowledge Hub"
    )

    print(
        "Use FastAPI to run "
        "the web application."
    )


if __name__ == "__main__":
    main()