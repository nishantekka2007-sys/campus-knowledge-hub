# Campus Knowledge Hub

A centralized platform for finding and managing college learning resources.

## Overview

Campus Knowledge Hub helps students organize learning resources in one place. Resources can be added, searched, viewed, edited, deleted, and bookmarked through a responsive web interface backed by a REST API and SQLite database.

Each resource can include a subject, title, resource type, link, and an optional description.

## Features

- Add learning resources
- View all resources
- Search by subject, title, resource type, or description
- Filter resources by type
- Bookmark resources as favorites
- Filter to show favorites only
- Edit existing resources
- Delete resources
- Optional resource descriptions
- Input validation for required fields
- HTTP/HTTPS URL validation
- REST API built with FastAPI
- SQLite database for persistent storage
- Automatic database migration for new fields
- Jinja2-powered web interface
- Responsive frontend design
- Automated API and database tests with pytest

## Tech Stack

- **Python**
- **FastAPI**
- **SQLite**
- **Jinja2**
- **HTML & CSS**
- **JavaScript**
- **Pytest**
- **Uvicorn**
- **Pydantic**

## API Endpoints

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/` | Web interface |
| GET | `/resources` | Get all resources |
| POST | `/resources` | Create a resource |
| GET | `/resources/{resource_id}` | Get one resource |
| PUT | `/resources/{resource_id}` | Update a resource |
| PATCH | `/resources/{resource_id}/favorite` | Toggle favorite status |
| DELETE | `/resources/{resource_id}` | Delete a resource |
| GET | `/resources/search/{keyword}` | Search resources |

## Project Structure

```text
campus-knowledge-hub/
│
├── app/
│   ├── __init__.py
│   └── main.py
│
├── templates/
│   └── index.html
│
├── tests/
│   └── test_main.py
│
├── docs/
├── .gitignore
├── README.md
└── requirements.txt