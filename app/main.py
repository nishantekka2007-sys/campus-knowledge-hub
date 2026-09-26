import sqlite3
from urllib.parse import urlparse

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field, field_validator


DATABASE = "campus.db"


app = FastAPI(
    title="Campus Knowledge Hub",
    description="API for managing college learning resources",
    version="1.0.0",
)


templates = Jinja2Templates(directory="templates")


class Resource(BaseModel):
    subject: str = Field(min_length=1)
    title: str = Field(min_length=1)
    resource_type: str = Field(min_length=1)
    link: str = Field(min_length=1)
    description: str = Field(default="", max_length=500)

    @field_validator("subject", "title", "resource_type", "link")
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

        if parsed_url.scheme not in ("http", "https") or not parsed_url.netloc:
            raise ValueError("Link must be a valid HTTP or HTTPS URL")

        return value


def connect_database():
    return sqlite3.connect(DATABASE)


def create_table():
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
            is_favorite INTEGER NOT NULL DEFAULT 0
        )
        """
    )

    cursor.execute("PRAGMA table_info(resources)")
    columns = [column[1] for column in cursor.fetchall()]

    if "description" not in columns:
        cursor.execute(
            """
            ALTER TABLE resources
            ADD COLUMN description TEXT NOT NULL DEFAULT ''
            """
        )

    if "is_favorite" not in columns:
        cursor.execute(
            """
            ALTER TABLE resources
            ADD COLUMN is_favorite INTEGER NOT NULL DEFAULT 0
            """
        )

    connection.commit()
    connection.close()


def get_required_input(prompt):
    while True:
        value = input(prompt).strip()

        if value:
            return value

        print("This field cannot be empty. Please try again.")


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
            is_favorite
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
        ) = resource

        print(f"\nResource #{resource_id}")
        print(f"Subject: {subject}")
        print(f"Title: {title}")
        print(f"Type: {resource_type}")
        print(f"Link: {link}")
        print(
            f"Description: {description or 'No description provided.'}"
        )
        print(
            f"Favorite: {'Yes' if is_favorite else 'No'}"
        )


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
            is_favorite
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

    print(f"\nFound {len(resources)} resource(s):")

    for resource in resources:
        (
            resource_id,
            subject,
            title,
            resource_type,
            link,
            description,
            is_favorite,
        ) = resource

        print(f"\nResource #{resource_id}")
        print(f"Subject: {subject}")
        print(f"Title: {title}")
        print(f"Type: {resource_type}")
        print(f"Link: {link}")
        print(
            f"Description: {description or 'No description provided.'}"
        )
        print(
            f"Favorite: {'Yes' if is_favorite else 'No'}"
        )


def update_resource():
    print("\n--- Update Resource ---")

    resource_id = get_required_input("Enter resource ID: ")

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
        f"Description: {resource[5] or 'No description provided.'}"
    )

    print("\nEnter the new information.")

    new_subject = get_required_input("New subject: ")
    new_title = get_required_input("New title: ")
    new_type = get_required_input("New type: ")
    new_link = get_required_input("New link: ")
    new_description = get_optional_input("New description: ")

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

    resource_id = get_required_input("Enter resource ID: ")

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


create_table()


@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={},
    )


@app.get("/resources")
def get_resources(favorite: bool = False):
    connection = connect_database()
    connection.row_factory = sqlite3.Row
    cursor = connection.cursor()

    if favorite:
        cursor.execute(
            """
            SELECT
                id,
                subject,
                title,
                resource_type,
                link,
                description,
                is_favorite
            FROM resources
            WHERE is_favorite = 1
            ORDER BY id
            """
        )
    else:
        cursor.execute(
            """
            SELECT
                id,
                subject,
                title,
                resource_type,
                link,
                description,
                is_favorite
            FROM resources
            ORDER BY id
            """
        )

    resources = []

    for row in cursor.fetchall():
        resource = dict(row)
        resource["is_favorite"] = bool(resource["is_favorite"])
        resources.append(resource)

    connection.close()

    return resources


@app.get("/resources/{resource_id}")
def get_resource(resource_id: int):
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
            is_favorite
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
    result["is_favorite"] = bool(result["is_favorite"])

    return result


@app.post("/resources", status_code=201)
def create_resource(resource: Resource):
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
            resource.subject,
            resource.title,
            resource.resource_type,
            resource.link,
            resource.description,
        ),
    )

    resource_id = cursor.lastrowid

    connection.commit()
    connection.close()

    return {
        "message": "Resource created successfully",
        "id": resource_id,
    }


@app.put("/resources/{resource_id}")
def update_resource_api(
    resource_id: int,
    resource: Resource,
):
    connection = connect_database()
    cursor = connection.cursor()

    cursor.execute(
        "SELECT id FROM resources WHERE id = ?",
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


@app.patch("/resources/{resource_id}/favorite")
def toggle_favorite(resource_id: int):
    connection = connect_database()
    connection.row_factory = sqlite3.Row
    cursor = connection.cursor()

    cursor.execute(
        """
        SELECT id, is_favorite
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

    new_status = 0 if resource["is_favorite"] else 1

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
def delete_resource_api(resource_id: int):
    connection = connect_database()
    cursor = connection.cursor()

    cursor.execute(
        "SELECT id FROM resources WHERE id = ?",
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


@app.get("/resources/search/{keyword}")
def search_resources_api(keyword: str):
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
            is_favorite
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
        resource["is_favorite"] = bool(resource["is_favorite"])
        resources.append(resource)

    connection.close()

    return resources


def main():
    print("Campus Knowledge Hub")
    print("Use FastAPI to run the web application.")


if __name__ == "__main__":
    main()