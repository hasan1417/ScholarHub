#!/bin/bash

# Helper script to set DATABASE_URL environment variable for ScholarHub backend
# This ensures consistent database connection configuration across different environments

export DATABASE_URL=postgresql://scholarhub:scholarhub@localhost:5432/scholarhub

# Source the virtual environment if it exists
if [ -d "scholarenv/bin" ]; then
    source scholarenv/bin/activate
fi

# Execute any command passed as arguments with the DATABASE_URL set
if [ $# -gt 0 ]; then
    exec "$@"
else
    echo "DATABASE_URL set to: $DATABASE_URL"
    echo "Virtual environment activated (if available)"
    echo "Usage: ./set_database_url.sh [command...]"
    echo "Example: ./set_database_url.sh alembic upgrade head"
    echo "Example: ./set_database_url.sh uvicorn app.main:app --reload"
fi