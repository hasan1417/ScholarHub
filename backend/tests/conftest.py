"""
Pytest configuration and fixtures for integration tests.

Uses the actual PostgreSQL database via Docker for realistic testing.
"""

import os
import sys
import uuid
from typing import Generator

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.config import settings

# Use the actual PostgreSQL database URL from settings
DATABASE_URL = settings.DATABASE_URL

engine = create_engine(DATABASE_URL)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture(scope="function")
def db() -> Generator[Session, None, None]:
    """Create a database session for testing."""
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.rollback()  # Rollback any changes made during test
        db.close()


@pytest.fixture(scope="function")
def test_user(db: Session):
    """Create or get a test user."""
    from app.models.user import User

    # Check if test user already exists
    test_email = "ai_memory_test_user@example.com"
    user = db.query(User).filter(User.email == test_email).first()

    if not user:
        user = User(
            id=uuid.uuid4(),
            email=test_email,
            password_hash="test_hash_123",
            first_name="AI Memory",
            last_name="Test User",
            is_active=True,
            is_verified=True,
        )
        db.add(user)
        db.commit()
        db.refresh(user)

    return user


@pytest.fixture(scope="function")
def test_project(db: Session, test_user):
    """Create a test project for AI memory testing."""
    from app.models.project import Project
    from app.models.project_member import ProjectMember

    # Create a unique project for this test run
    project = Project(
        id=uuid.uuid4(),
        title=f"AI Memory Test Project {uuid.uuid4().hex[:8]}",
        idea="Test project for AI memory integration testing.",
        scope="Test objectives",
        keywords="test, ai, memory",
        created_by=test_user.id,
    )
    db.add(project)
    db.flush()

    # Add user as project owner
    member = ProjectMember(
        id=uuid.uuid4(),
        project_id=project.id,
        user_id=test_user.id,
        role="owner",
    )
    db.add(member)
    db.commit()
    db.refresh(project)

    yield project

    # Cleanup: Delete the project after test
    try:
        db.delete(project)
        db.commit()
    except Exception:
        db.rollback()


@pytest.fixture(scope="function")
def test_channel(db: Session, test_project, test_user):
    """Create a test discussion channel."""
    from app.models.project_discussion import ProjectDiscussionChannel

    channel = ProjectDiscussionChannel(
        id=uuid.uuid4(),
        project_id=test_project.id,
        name=f"AI Memory Test Channel {uuid.uuid4().hex[:8]}",
        slug=f"ai-memory-test-{uuid.uuid4().hex[:8]}",
        description="Test channel for AI memory integration testing",
        is_default=False,
        created_by=test_user.id,
    )
    db.add(channel)
    db.commit()
    db.refresh(channel)

    yield channel

    # Cleanup: Delete the channel after test
    try:
        db.delete(channel)
        db.commit()
    except Exception:
        db.rollback()


@pytest.fixture(scope="function")
def test_setup(db: Session, test_user, test_project, test_channel) -> dict:
    """Complete test setup with all dependencies."""
    return {
        "db": db,
        "user": test_user,
        "project": test_project,
        "channel": test_channel,
    }
