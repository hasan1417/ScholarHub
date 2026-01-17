#!/usr/bin/env python3
"""
Activity Feed Test Script

Tests that all activity events are properly recorded in the notifications system.

Usage:
    # Test with existing project (recommended)
    python test_activity_feed.py --project-id <UUID>

    # Test with auto-created project (will create test data)
    python test_activity_feed.py --create-test-project

    # Cleanup test data after running
    python test_activity_feed.py --project-id <UUID> --cleanup
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, asdict
from uuid import uuid4
import requests

# Configuration
API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000/api/v1")

# Test user credentials (primary tester)
TEST_EMAIL = os.getenv("TEST_EMAIL", "g20240390@kfupm.edu.sa")
TEST_PASSWORD = os.getenv("TEST_PASSWORD", "test123")

# Secondary user for member events (optional)
TEST_EMAIL_2 = os.getenv("TEST_EMAIL_2", "")
TEST_PASSWORD_2 = os.getenv("TEST_PASSWORD_2", "")


@dataclass
class EventTestResult:
    event_type: str
    status: str  # "pass", "fail", "skip", "error"
    message: str
    notification_found: bool
    notification_id: Optional[str] = None
    payload_sample: Optional[Dict] = None
    timestamp: str = ""

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now().isoformat()


class ActivityFeedTester:
    def __init__(self, api_base_url: str):
        self.api_base_url = api_base_url
        self.session = requests.Session()
        self.token: Optional[str] = None
        self.user_id: Optional[str] = None
        self.project_id: Optional[str] = None
        self.results: List[EventTestResult] = []
        self.created_resources: Dict[str, List[str]] = {
            "projects": [],
            "papers": [],
            "members": [],
            "references": [],
        }

    def authenticate(self, email: str, password: str) -> bool:
        """Login and get auth token."""
        try:
            response = self.session.post(
                f"{self.api_base_url}/login",
                json={"email": email, "password": password}
            )
            if response.status_code == 200:
                data = response.json()
                self.token = data.get("access_token")
                self.user_id = data.get("user", {}).get("id")
                self.session.headers["Authorization"] = f"Bearer {self.token}"
                print(f"✓ Authenticated as {email}")
                return True
            else:
                print(f"✗ Authentication failed: {response.status_code} - {response.text}")
                return False
        except Exception as e:
            print(f"✗ Authentication error: {e}")
            return False

    def get_notifications(self, since: Optional[datetime] = None) -> List[Dict]:
        """Fetch notifications for the current project."""
        url = f"{self.api_base_url}/projects/{self.project_id}/notifications"
        try:
            response = self.session.get(url)
            if response.status_code == 200:
                notifications = response.json().get("notifications", [])
                if since:
                    notifications = [
                        n for n in notifications
                        if n.get("created_at") and n["created_at"] > since.isoformat()
                    ]
                return notifications
            else:
                print(f"  Warning: Failed to fetch notifications: {response.status_code}")
                return []
        except Exception as e:
            print(f"  Warning: Error fetching notifications: {e}")
            return []

    def find_notification_by_type(
        self, event_type: str, notifications: List[Dict], since: Optional[datetime] = None
    ) -> Optional[Dict]:
        """Find a notification matching the event type."""
        for n in notifications:
            if n.get("type") == event_type:
                if since:
                    created = n.get("created_at", "")
                    if created and created > since.isoformat():
                        return n
                else:
                    return n
        return None

    def record_result(self, result: EventTestResult):
        """Record a test result."""
        self.results.append(result)
        status_icon = {"pass": "✓", "fail": "✗", "skip": "○", "error": "!"}
        print(f"  {status_icon.get(result.status, '?')} {result.event_type}: {result.message}")

    # =========================================================================
    # Test Methods for Each Event Type
    # =========================================================================

    def test_project_created(self) -> EventTestResult:
        """Test project.created event."""
        print("\n[1/16] Testing project.created...")

        before = datetime.utcnow()
        time.sleep(0.5)

        # Create a new project
        response = self.session.post(
            f"{self.api_base_url}/projects/",
            json={
                "title": f"Activity Test Project {uuid4().hex[:8]}",
                "idea": "Test project for activity feed testing",
                "keywords": ["test", "activity"],
                "scope": "Testing activity events",
            }
        )

        if response.status_code != 201:
            return EventTestResult(
                event_type="project.created",
                status="error",
                message=f"Failed to create project: {response.status_code} - {response.text}",
                notification_found=False,
            )

        project = response.json()
        self.project_id = project.get("id")
        self.created_resources["projects"].append(self.project_id)

        time.sleep(1)  # Wait for notification to be created

        # Check for notification
        notifications = self.get_notifications(since=before)
        notification = self.find_notification_by_type("project.created", notifications, since=before)

        if notification:
            return EventTestResult(
                event_type="project.created",
                status="pass",
                message="Event recorded successfully",
                notification_found=True,
                notification_id=notification.get("id"),
                payload_sample=notification.get("payload"),
            )
        else:
            return EventTestResult(
                event_type="project.created",
                status="fail",
                message="Notification not found after project creation",
                notification_found=False,
            )

    def test_project_updated(self) -> EventTestResult:
        """Test project.updated event."""
        print("\n[2/16] Testing project.updated...")

        if not self.project_id:
            return EventTestResult(
                event_type="project.updated",
                status="skip",
                message="No project available",
                notification_found=False,
            )

        before = datetime.utcnow()
        time.sleep(0.5)

        # Update the project
        response = self.session.put(
            f"{self.api_base_url}/projects/{self.project_id}",
            json={"title": f"Updated Activity Test Project {uuid4().hex[:8]}"}
        )

        if response.status_code != 200:
            return EventTestResult(
                event_type="project.updated",
                status="error",
                message=f"Failed to update project: {response.status_code}",
                notification_found=False,
            )

        time.sleep(1)

        notifications = self.get_notifications(since=before)
        notification = self.find_notification_by_type("project.updated", notifications, since=before)

        if notification:
            return EventTestResult(
                event_type="project.updated",
                status="pass",
                message="Event recorded successfully",
                notification_found=True,
                notification_id=notification.get("id"),
                payload_sample=notification.get("payload"),
            )
        else:
            return EventTestResult(
                event_type="project.updated",
                status="fail",
                message="Notification not found after project update",
                notification_found=False,
            )

    def test_member_invited(self) -> EventTestResult:
        """Test member.invited event."""
        print("\n[3/16] Testing member.invited...")

        if not self.project_id:
            return EventTestResult(
                event_type="member.invited",
                status="skip",
                message="No project available",
                notification_found=False,
            )

        # First, we need to find a user to invite
        # For testing, we'll try to get a list of users or use a known user
        response = self.session.get(f"{self.api_base_url}/users")

        if response.status_code != 200:
            return EventTestResult(
                event_type="member.invited",
                status="skip",
                message="Cannot search for users to invite",
                notification_found=False,
            )

        data = response.json()
        users = data if isinstance(data, list) else data.get("users", [])
        invite_user = None
        for user in users:
            if user.get("id") != self.user_id:
                invite_user = user
                break

        if not invite_user:
            return EventTestResult(
                event_type="member.invited",
                status="skip",
                message="No other user found to invite",
                notification_found=False,
            )

        before = datetime.utcnow()
        time.sleep(0.5)

        # Invite the user
        response = self.session.post(
            f"{self.api_base_url}/projects/{self.project_id}/members",
            json={"user_id": invite_user["id"], "role": "viewer"}
        )

        if response.status_code == 400 and "already exists" in response.text.lower():
            return EventTestResult(
                event_type="member.invited",
                status="skip",
                message="Member already exists in project",
                notification_found=False,
            )

        if response.status_code != 201:
            return EventTestResult(
                event_type="member.invited",
                status="error",
                message=f"Failed to invite member: {response.status_code}",
                notification_found=False,
            )

        member = response.json()
        self.created_resources["members"].append(member.get("id"))

        time.sleep(1)

        notifications = self.get_notifications(since=before)
        notification = self.find_notification_by_type("member.invited", notifications, since=before)

        if notification:
            return EventTestResult(
                event_type="member.invited",
                status="pass",
                message=f"Event recorded - invited {invite_user.get('email')}",
                notification_found=True,
                notification_id=notification.get("id"),
                payload_sample=notification.get("payload"),
            )
        else:
            return EventTestResult(
                event_type="member.invited",
                status="fail",
                message="Notification not found after member invite",
                notification_found=False,
            )

    def test_member_joined(self) -> EventTestResult:
        """Test member.joined event (requires second user)."""
        print("\n[4/16] Testing member.joined...")
        return EventTestResult(
            event_type="member.joined",
            status="skip",
            message="Requires second user to accept invitation - manual test needed",
            notification_found=False,
        )

    def test_member_declined(self) -> EventTestResult:
        """Test member.declined event (requires second user)."""
        print("\n[5/16] Testing member.declined...")
        return EventTestResult(
            event_type="member.declined",
            status="skip",
            message="Requires second user to decline invitation - manual test needed",
            notification_found=False,
        )

    def test_member_removed(self) -> EventTestResult:
        """Test member.removed event."""
        print("\n[6/16] Testing member.removed...")

        if not self.project_id or not self.created_resources["members"]:
            return EventTestResult(
                event_type="member.removed",
                status="skip",
                message="No invited member to remove",
                notification_found=False,
            )

        member_id = self.created_resources["members"][-1]
        before = datetime.utcnow()
        time.sleep(0.5)

        response = self.session.delete(
            f"{self.api_base_url}/projects/{self.project_id}/members/{member_id}"
        )

        if response.status_code != 204:
            return EventTestResult(
                event_type="member.removed",
                status="error",
                message=f"Failed to remove member: {response.status_code}",
                notification_found=False,
            )

        self.created_resources["members"].remove(member_id)
        time.sleep(1)

        notifications = self.get_notifications(since=before)
        notification = self.find_notification_by_type("member.removed", notifications, since=before)

        if notification:
            return EventTestResult(
                event_type="member.removed",
                status="pass",
                message="Event recorded successfully",
                notification_found=True,
                notification_id=notification.get("id"),
                payload_sample=notification.get("payload"),
            )
        else:
            return EventTestResult(
                event_type="member.removed",
                status="fail",
                message="Notification not found after member removal",
                notification_found=False,
            )

    def test_paper_created(self) -> EventTestResult:
        """Test paper.created event."""
        print("\n[7/16] Testing paper.created...")

        if not self.project_id:
            return EventTestResult(
                event_type="paper.created",
                status="skip",
                message="No project available",
                notification_found=False,
            )

        before = datetime.utcnow()
        time.sleep(0.5)

        response = self.session.post(
            f"{self.api_base_url}/research-papers/",
            json={
                "title": f"Test Paper {uuid4().hex[:8]}",
                "content": "\\section{Introduction}\nThis is a test paper.",
                "project_id": self.project_id,
                "objectives": ["Testing activity feed"],
            }
        )

        if response.status_code != 201:
            return EventTestResult(
                event_type="paper.created",
                status="error",
                message=f"Failed to create paper: {response.status_code} - {response.text}",
                notification_found=False,
            )

        paper = response.json()
        self.created_resources["papers"].append(paper.get("id"))

        time.sleep(1)

        notifications = self.get_notifications(since=before)
        notification = self.find_notification_by_type("paper.created", notifications, since=before)

        if notification:
            return EventTestResult(
                event_type="paper.created",
                status="pass",
                message="Event recorded successfully",
                notification_found=True,
                notification_id=notification.get("id"),
                payload_sample=notification.get("payload"),
            )
        else:
            return EventTestResult(
                event_type="paper.created",
                status="fail",
                message="Notification not found after paper creation",
                notification_found=False,
            )

    def test_paper_updated(self) -> EventTestResult:
        """Test paper.updated event."""
        print("\n[8/16] Testing paper.updated...")

        if not self.project_id or not self.created_resources["papers"]:
            return EventTestResult(
                event_type="paper.updated",
                status="skip",
                message="No paper available to update",
                notification_found=False,
            )

        paper_id = self.created_resources["papers"][-1]
        before = datetime.utcnow()
        time.sleep(0.5)

        response = self.session.put(
            f"{self.api_base_url}/research-papers/{paper_id}",
            json={"title": f"Updated Test Paper {uuid4().hex[:8]}"}
        )

        if response.status_code != 200:
            return EventTestResult(
                event_type="paper.updated",
                status="error",
                message=f"Failed to update paper: {response.status_code}",
                notification_found=False,
            )

        time.sleep(1)

        notifications = self.get_notifications(since=before)
        notification = self.find_notification_by_type("paper.updated", notifications, since=before)

        if notification:
            return EventTestResult(
                event_type="paper.updated",
                status="pass",
                message="Event recorded successfully",
                notification_found=True,
                notification_id=notification.get("id"),
                payload_sample=notification.get("payload"),
            )
        else:
            return EventTestResult(
                event_type="paper.updated",
                status="fail",
                message="Notification not found after paper update",
                notification_found=False,
            )

    def test_paper_reference_linked(self) -> EventTestResult:
        """Test paper.reference-linked event."""
        print("\n[9/16] Testing paper.reference-linked...")

        if not self.project_id or not self.created_resources["papers"]:
            return EventTestResult(
                event_type="paper.reference-linked",
                status="skip",
                message="No paper available",
                notification_found=False,
            )

        # Check for approved references in the project
        response = self.session.get(
            f"{self.api_base_url}/projects/{self.project_id}/references?status=approved"
        )

        if response.status_code != 200:
            return EventTestResult(
                event_type="paper.reference-linked",
                status="skip",
                message="Cannot fetch project references",
                notification_found=False,
            )

        references = response.json().get("references", [])
        if not references:
            return EventTestResult(
                event_type="paper.reference-linked",
                status="skip",
                message="No approved references in project to link",
                notification_found=False,
            )

        paper_id = self.created_resources["papers"][-1]
        reference = references[0]
        reference_id = reference.get("id")

        before = datetime.utcnow()
        time.sleep(0.5)

        # Use the attach endpoint with paper_id in body
        response = self.session.post(
            f"{self.api_base_url}/projects/{self.project_id}/references/{reference_id}/attach",
            json={"paper_id": paper_id}
        )

        if response.status_code not in [200, 201]:
            return EventTestResult(
                event_type="paper.reference-linked",
                status="error",
                message=f"Failed to link reference: {response.status_code}",
                notification_found=False,
            )

        time.sleep(1)

        notifications = self.get_notifications(since=before)
        notification = self.find_notification_by_type("paper.reference-linked", notifications, since=before)

        if notification:
            # Store linked reference info for unlink test
            self.created_resources["linked_reference"] = {
                "project_reference_id": reference_id,
                "paper_id": paper_id,
            }
            return EventTestResult(
                event_type="paper.reference-linked",
                status="pass",
                message="Event recorded successfully",
                notification_found=True,
                notification_id=notification.get("id"),
                payload_sample=notification.get("payload"),
            )
        else:
            return EventTestResult(
                event_type="paper.reference-linked",
                status="fail",
                message="Notification not found after reference link",
                notification_found=False,
            )

    def test_paper_reference_unlinked(self) -> EventTestResult:
        """Test paper.reference-unlinked event."""
        print("\n[10/16] Testing paper.reference-unlinked...")

        linked_ref = self.created_resources.get("linked_reference")
        if not linked_ref:
            return EventTestResult(
                event_type="paper.reference-unlinked",
                status="skip",
                message="No linked reference to unlink - run reference-linked test first",
                notification_found=False,
            )

        before = datetime.utcnow()
        time.sleep(0.5)

        # DELETE /projects/{project_id}/references/{project_reference_id}/papers/{paper_id}
        response = self.session.delete(
            f"{self.api_base_url}/projects/{self.project_id}/references/{linked_ref['project_reference_id']}/papers/{linked_ref['paper_id']}"
        )

        if response.status_code != 204:
            return EventTestResult(
                event_type="paper.reference-unlinked",
                status="error",
                message=f"Failed to unlink reference: {response.status_code}",
                notification_found=False,
            )

        time.sleep(1)

        notifications = self.get_notifications(since=before)
        notification = self.find_notification_by_type("paper.reference-unlinked", notifications, since=before)

        if notification:
            return EventTestResult(
                event_type="paper.reference-unlinked",
                status="pass",
                message="Event recorded successfully",
                notification_found=True,
                notification_id=notification.get("id"),
                payload_sample=notification.get("payload"),
            )
        else:
            return EventTestResult(
                event_type="paper.reference-unlinked",
                status="fail",
                message="Notification not found after reference unlink",
                notification_found=False,
            )

    def test_project_reference_suggested(self) -> EventTestResult:
        """Test project-reference.suggested event."""
        print("\n[11/16] Testing project-reference.suggested...")
        return EventTestResult(
            event_type="project-reference.suggested",
            status="skip",
            message="Triggered by discovery service - requires paper search with discovery enabled",
            notification_found=False,
        )

    def test_project_reference_approved(self) -> EventTestResult:
        """Test project-reference.approved event."""
        print("\n[12/16] Testing project-reference.approved...")

        if not self.project_id:
            return EventTestResult(
                event_type="project-reference.approved",
                status="skip",
                message="No project available",
                notification_found=False,
            )

        # Check for pending references
        response = self.session.get(
            f"{self.api_base_url}/projects/{self.project_id}/references?status=pending"
        )

        if response.status_code != 200:
            return EventTestResult(
                event_type="project-reference.approved",
                status="skip",
                message="Cannot fetch pending references",
                notification_found=False,
            )

        references = response.json().get("references", [])
        if not references:
            return EventTestResult(
                event_type="project-reference.approved",
                status="skip",
                message="No pending references to approve",
                notification_found=False,
            )

        reference = references[0]
        reference_id = reference.get("id")

        before = datetime.utcnow()
        time.sleep(0.5)

        response = self.session.patch(
            f"{self.api_base_url}/projects/{self.project_id}/references/{reference_id}",
            json={"status": "approved"}
        )

        if response.status_code != 200:
            return EventTestResult(
                event_type="project-reference.approved",
                status="error",
                message=f"Failed to approve reference: {response.status_code}",
                notification_found=False,
            )

        time.sleep(1)

        notifications = self.get_notifications(since=before)
        notification = self.find_notification_by_type("project-reference.approved", notifications, since=before)

        if notification:
            return EventTestResult(
                event_type="project-reference.approved",
                status="pass",
                message="Event recorded successfully",
                notification_found=True,
                notification_id=notification.get("id"),
                payload_sample=notification.get("payload"),
            )
        else:
            return EventTestResult(
                event_type="project-reference.approved",
                status="fail",
                message="Notification not found after reference approval",
                notification_found=False,
            )

    def test_project_reference_rejected(self) -> EventTestResult:
        """Test project-reference.rejected event."""
        print("\n[13/16] Testing project-reference.rejected...")

        if not self.project_id:
            return EventTestResult(
                event_type="project-reference.rejected",
                status="skip",
                message="No project available",
                notification_found=False,
            )

        # Check for pending references
        response = self.session.get(
            f"{self.api_base_url}/projects/{self.project_id}/references?status=pending"
        )

        if response.status_code != 200:
            return EventTestResult(
                event_type="project-reference.rejected",
                status="skip",
                message="Cannot fetch pending references",
                notification_found=False,
            )

        references = response.json().get("references", [])
        if not references:
            return EventTestResult(
                event_type="project-reference.rejected",
                status="skip",
                message="No pending references to reject",
                notification_found=False,
            )

        reference = references[0]
        reference_id = reference.get("id")

        before = datetime.utcnow()
        time.sleep(0.5)

        response = self.session.patch(
            f"{self.api_base_url}/projects/{self.project_id}/references/{reference_id}",
            json={"status": "rejected"}
        )

        if response.status_code != 200:
            return EventTestResult(
                event_type="project-reference.rejected",
                status="error",
                message=f"Failed to reject reference: {response.status_code}",
                notification_found=False,
            )

        time.sleep(1)

        notifications = self.get_notifications(since=before)
        notification = self.find_notification_by_type("project-reference.rejected", notifications, since=before)

        if notification:
            return EventTestResult(
                event_type="project-reference.rejected",
                status="pass",
                message="Event recorded successfully",
                notification_found=True,
                notification_id=notification.get("id"),
                payload_sample=notification.get("payload"),
            )
        else:
            return EventTestResult(
                event_type="project-reference.rejected",
                status="fail",
                message="Notification not found after reference rejection",
                notification_found=False,
            )

    def test_sync_session_started(self) -> EventTestResult:
        """Test sync-session.started event."""
        print("\n[14/16] Testing sync-session.started...")

        if not self.project_id:
            return EventTestResult(
                event_type="sync-session.started",
                status="skip",
                message="No project available",
                notification_found=False,
            )

        before = datetime.utcnow()
        time.sleep(0.5)

        response = self.session.post(
            f"{self.api_base_url}/projects/{self.project_id}/sync-sessions",
            json={"status": "live"}
        )

        if response.status_code not in [200, 201]:
            return EventTestResult(
                event_type="sync-session.started",
                status="error",
                message=f"Failed to start sync session: {response.status_code}",
                notification_found=False,
            )

        session_data = response.json()
        session_id = session_data.get("id")

        time.sleep(1)

        notifications = self.get_notifications(since=before)
        notification = self.find_notification_by_type("sync-session.started", notifications, since=before)

        # Store session ID for later tests
        self.created_resources["sync_session"] = session_id

        if notification:
            return EventTestResult(
                event_type="sync-session.started",
                status="pass",
                message="Event recorded successfully",
                notification_found=True,
                notification_id=notification.get("id"),
                payload_sample=notification.get("payload"),
            )
        else:
            return EventTestResult(
                event_type="sync-session.started",
                status="fail",
                message="Notification not found after session start",
                notification_found=False,
            )

    def test_sync_session_ended(self) -> EventTestResult:
        """Test sync-session.ended event."""
        print("\n[15/16] Testing sync-session.ended...")

        if not self.project_id:
            return EventTestResult(
                event_type="sync-session.ended",
                status="skip",
                message="No project available",
                notification_found=False,
            )

        session_id = self.created_resources.get("sync_session")
        if not session_id:
            return EventTestResult(
                event_type="sync-session.ended",
                status="skip",
                message="No active sync session to end",
                notification_found=False,
            )

        before = datetime.utcnow()
        time.sleep(0.5)

        response = self.session.post(
            f"{self.api_base_url}/projects/{self.project_id}/sync-sessions/{session_id}/end",
            json={"status": "ended"}
        )

        if response.status_code != 200:
            return EventTestResult(
                event_type="sync-session.ended",
                status="error",
                message=f"Failed to end sync session: {response.status_code}",
                notification_found=False,
            )

        time.sleep(1)

        notifications = self.get_notifications(since=before)
        notification = self.find_notification_by_type("sync-session.ended", notifications, since=before)

        if notification:
            return EventTestResult(
                event_type="sync-session.ended",
                status="pass",
                message="Event recorded successfully",
                notification_found=True,
                notification_id=notification.get("id"),
                payload_sample=notification.get("payload"),
            )
        else:
            return EventTestResult(
                event_type="sync-session.ended",
                status="fail",
                message="Notification not found after session end",
                notification_found=False,
            )

    def test_sync_session_cancelled(self) -> EventTestResult:
        """Test sync-session.cancelled event."""
        print("\n[16/16] Testing sync-session.cancelled...")

        if not self.project_id:
            return EventTestResult(
                event_type="sync-session.cancelled",
                status="skip",
                message="No project available",
                notification_found=False,
            )

        # Create a new session to cancel
        response = self.session.post(
            f"{self.api_base_url}/projects/{self.project_id}/sync-sessions",
            json={"status": "live"}
        )

        if response.status_code not in [200, 201]:
            return EventTestResult(
                event_type="sync-session.cancelled",
                status="skip",
                message="Cannot create session to cancel",
                notification_found=False,
            )

        session_data = response.json()
        session_id = session_data.get("id")

        before = datetime.utcnow()
        time.sleep(0.5)

        response = self.session.post(
            f"{self.api_base_url}/projects/{self.project_id}/sync-sessions/{session_id}/end",
            json={"status": "cancelled"}
        )

        if response.status_code != 200:
            return EventTestResult(
                event_type="sync-session.cancelled",
                status="error",
                message=f"Failed to cancel sync session: {response.status_code}",
                notification_found=False,
            )

        time.sleep(1)

        notifications = self.get_notifications(since=before)
        notification = self.find_notification_by_type("sync-session.cancelled", notifications, since=before)

        if notification:
            return EventTestResult(
                event_type="sync-session.cancelled",
                status="pass",
                message="Event recorded successfully",
                notification_found=True,
                notification_id=notification.get("id"),
                payload_sample=notification.get("payload"),
            )
        else:
            return EventTestResult(
                event_type="sync-session.cancelled",
                status="fail",
                message="Notification not found after session cancel",
                notification_found=False,
            )

    def run_all_tests(self, project_id: Optional[str] = None) -> List[EventTestResult]:
        """Run all activity feed tests."""
        if project_id:
            self.project_id = project_id
            print(f"\nUsing existing project: {project_id}")
            # Run tests that don't create a project
            results = [
                self.test_project_updated(),
                self.test_member_invited(),
                self.test_member_joined(),
                self.test_member_declined(),
                self.test_member_removed(),
                self.test_paper_created(),
                self.test_paper_updated(),
                self.test_paper_reference_linked(),
                self.test_paper_reference_unlinked(),
                self.test_project_reference_suggested(),
                self.test_project_reference_approved(),
                self.test_project_reference_rejected(),
                self.test_sync_session_started(),
                self.test_sync_session_ended(),
                self.test_sync_session_cancelled(),
            ]
            # Add skip for project.created since we're using existing
            results.insert(0, EventTestResult(
                event_type="project.created",
                status="skip",
                message="Using existing project",
                notification_found=False,
            ))
        else:
            # Create a new project and run all tests
            results = [
                self.test_project_created(),
                self.test_project_updated(),
                self.test_member_invited(),
                self.test_member_joined(),
                self.test_member_declined(),
                self.test_member_removed(),
                self.test_paper_created(),
                self.test_paper_updated(),
                self.test_paper_reference_linked(),
                self.test_paper_reference_unlinked(),
                self.test_project_reference_suggested(),
                self.test_project_reference_approved(),
                self.test_project_reference_rejected(),
                self.test_sync_session_started(),
                self.test_sync_session_ended(),
                self.test_sync_session_cancelled(),
            ]

        for result in results:
            self.record_result(result)

        return results

    def print_summary(self):
        """Print test summary."""
        passed = len([r for r in self.results if r.status == "pass"])
        failed = len([r for r in self.results if r.status == "fail"])
        skipped = len([r for r in self.results if r.status == "skip"])
        errors = len([r for r in self.results if r.status == "error"])
        total = len(self.results)

        print(f"\n{'='*60}")
        print("ACTIVITY FEED TEST SUMMARY")
        print(f"{'='*60}")
        print(f"Total:   {total}")
        print(f"Passed:  {passed} ✓")
        print(f"Failed:  {failed} ✗")
        print(f"Skipped: {skipped} ○")
        print(f"Errors:  {errors} !")

        if failed > 0:
            print(f"\n{'='*60}")
            print("FAILED TESTS:")
            print(f"{'='*60}")
            for r in self.results:
                if r.status == "fail":
                    print(f"  ✗ {r.event_type}: {r.message}")

        if skipped > 0:
            print(f"\n{'='*60}")
            print("SKIPPED TESTS (require manual testing or setup):")
            print(f"{'='*60}")
            for r in self.results:
                if r.status == "skip":
                    print(f"  ○ {r.event_type}: {r.message}")

    def save_results(self, filename: str = "activity_feed_test_results.json"):
        """Save results to JSON file."""
        output = {
            "run_timestamp": datetime.now().isoformat(),
            "project_id": self.project_id,
            "total_tests": len(self.results),
            "passed": len([r for r in self.results if r.status == "pass"]),
            "failed": len([r for r in self.results if r.status == "fail"]),
            "skipped": len([r for r in self.results if r.status == "skip"]),
            "errors": len([r for r in self.results if r.status == "error"]),
            "results": [asdict(r) for r in self.results],
        }

        with open(filename, "w") as f:
            json.dump(output, f, indent=2)

        print(f"\n✓ Results saved to {filename}")


def main():
    parser = argparse.ArgumentParser(description="Activity Feed Test Script")
    parser.add_argument("--project-id", type=str, help="Use existing project ID")
    parser.add_argument("--create-test-project", action="store_true", help="Create a new test project")
    parser.add_argument("--output", type=str, default="activity_feed_test_results.json", help="Output file")

    args = parser.parse_args()

    tester = ActivityFeedTester(API_BASE_URL)

    # Authenticate
    if not tester.authenticate(TEST_EMAIL, TEST_PASSWORD):
        print("Failed to authenticate. Exiting.")
        sys.exit(1)

    # Run tests
    print(f"\n{'#'*60}")
    print("ACTIVITY FEED EVENT TESTS")
    print(f"{'#'*60}")

    if args.project_id:
        tester.run_all_tests(project_id=args.project_id)
    elif args.create_test_project:
        tester.run_all_tests()
    else:
        print("\nUsage:")
        print("  --project-id <UUID>      Test with existing project")
        print("  --create-test-project    Create new project for testing")
        sys.exit(0)

    # Save and summarize
    tester.save_results(args.output)
    tester.print_summary()


if __name__ == "__main__":
    main()
