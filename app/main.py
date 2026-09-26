import sqlite3


DATABASE = "campus.db"


def connect_database():
    return sqlite3.connect(DATABASE)


def create_table():
    connection = connect_database()
    cursor = connection.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS resources (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            subject TEXT NOT NULL,
            title TEXT NOT NULL,
            resource_type TEXT NOT NULL,
            link TEXT NOT NULL
        )
    """)

    connection.commit()
    connection.close()


def get_required_input(prompt):
    while True:
        value = input(prompt).strip()

        if value:
            return value

        print("This field cannot be empty. Please try again.")


def add_resource():
    print("\n--- Add Resource ---")

    subject = get_required_input("Subject: ")
    title = get_required_input("Title: ")
    resource_type = get_required_input("Type: ")
    link = get_required_input("Link: ")

    connection = connect_database()
    cursor = connection.cursor()

    cursor.execute("""
        INSERT INTO resources (subject, title, resource_type, link)
        VALUES (?, ?, ?, ?)
    """, (subject, title, resource_type, link))

    connection.commit()
    connection.close()

    print("\nResource added successfully!")


def view_resources():
    print("\n--- All Resources ---")

    connection = connect_database()
    cursor = connection.cursor()

    cursor.execute("""
        SELECT id, subject, title, resource_type, link
        FROM resources
    """)

    resources = cursor.fetchall()

    connection.close()

    if not resources:
        print("No resources available.")
        return

    for resource in resources:
        resource_id, subject, title, resource_type, link = resource

        print(f"\nResource #{resource_id}")
        print(f"Subject: {subject}")
        print(f"Title: {title}")
        print(f"Type: {resource_type}")
        print(f"Link: {link}")


def search_resources():
    print("\n--- Search Resources ---")

    keyword = input("Search: ").strip()

    if not keyword:
        print("Search cannot be empty.")
        return

    connection = connect_database()
    cursor = connection.cursor()

    search_term = f"%{keyword}%"

    cursor.execute("""
        SELECT id, subject, title, resource_type, link
        FROM resources
        WHERE subject LIKE ?
           OR title LIKE ?
           OR resource_type LIKE ?
    """, (search_term, search_term, search_term))

    resources = cursor.fetchall()

    connection.close()

    if not resources:
        print("\nNo matching resources found.")
        return

    print(f"\nFound {len(resources)} resource(s):")

    for resource in resources:
        resource_id, subject, title, resource_type, link = resource

        print(f"\nResource #{resource_id}")
        print(f"Subject: {subject}")
        print(f"Title: {title}")
        print(f"Type: {resource_type}")
        print(f"Link: {link}")


def update_resource():
    print("\n--- Update Resource ---")

    resource_id = input("Enter resource ID: ").strip()

    if not resource_id.isdigit():
        print("Please enter a valid resource ID.")
        return

    connection = connect_database()
    cursor = connection.cursor()

    cursor.execute("""
        SELECT subject, title, resource_type, link
        FROM resources
        WHERE id = ?
    """, (resource_id,))

    resource = cursor.fetchone()

    if resource is None:
        print("Resource not found.")
        connection.close()
        return

    print("\nCurrent resource:")
    print(f"Subject: {resource[0]}")
    print(f"Title: {resource[1]}")
    print(f"Type: {resource[2]}")
    print(f"Link: {resource[3]}")

    print("\nEnter the new information.")

    subject = get_required_input("New subject: ")
    title = get_required_input("New title: ")
    resource_type = get_required_input("New type: ")
    link = get_required_input("New link: ")

    cursor.execute("""
        UPDATE resources
        SET subject = ?,
            title = ?,
            resource_type = ?,
            link = ?
        WHERE id = ?
    """, (subject, title, resource_type, link, resource_id))

    connection.commit()
    connection.close()

    print("\nResource updated successfully!")


def delete_resource():
    print("\n--- Delete Resource ---")

    resource_id = input("Enter resource ID: ").strip()

    if not resource_id.isdigit():
        print("Please enter a valid resource ID.")
        return

    connection = connect_database()
    cursor = connection.cursor()

    cursor.execute(
        "SELECT title FROM resources WHERE id = ?",
        (resource_id,)
    )

    resource = cursor.fetchone()

    if resource is None:
        print("Resource not found.")
        connection.close()
        return

    confirm = input(
        f'Delete "{resource[0]}"? (y/n): '
    ).strip().lower()

    if confirm == "y":
        cursor.execute(
            "DELETE FROM resources WHERE id = ?",
            (resource_id,)
        )

        connection.commit()
        print("Resource deleted successfully!")

    else:
        print("Deletion cancelled.")

    connection.close()


def main():
    create_table()

    while True:
        print("\n==============================")
        print("     CAMPUS KNOWLEDGE HUB")
        print("==============================")
        print()
        print("1. Add Resource")
        print("2. View Resources")
        print("3. Search Resources")
        print("4. Update Resource")
        print("5. Delete Resource")
        print("6. Exit")

        choice = input("\nEnter your choice: ").strip()

        if choice == "1":
            add_resource()

        elif choice == "2":
            view_resources()

        elif choice == "3":
            search_resources()

        elif choice == "4":
            update_resource()

        elif choice == "5":
            delete_resource()

        elif choice == "6":
            print("\nGoodbye!")
            break

        else:
            print("\nInvalid choice. Please try again.")


if __name__ == "__main__":
    main()