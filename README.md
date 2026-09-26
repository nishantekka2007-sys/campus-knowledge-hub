# Campus Knowledge Hub

A centralized platform for finding and managing college learning resources.

## Overview

Campus Knowledge Hub helps students organize learning resources in one place. Resources can be added, searched, viewed, edited, and deleted through a simple web interface backed by a REST API and SQLite database.

## Features

- Add learning resources
- View all resources
- Search by subject, title, or resource type
- Edit existing resources
- Delete resources
- REST API built with FastAPI
- SQLite database for persistent storage
- Jinja2-powered web interface
- Automated tests with pytest
- Responsive frontend design

## Tech Stack

- **Python**
- **FastAPI**
- **SQLite**
- **Jinja2**
- **HTML & CSS**
- **JavaScript**
- **Pytest**
- **Uvicorn**

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