# Activity Feed Test Cases

## Test Plan

This document outlines all activity events that should be recorded and how to test them.

## Running the Automated Test Script

```bash
# From the backend directory or via docker

# Test with an existing project
python tests/test_activity_feed.py --project-id <YOUR_PROJECT_UUID>

# Create a new test project and run all tests
python tests/test_activity_feed.py --create-test-project

# Via Docker
docker-compose exec backend python tests/test_activity_feed.py --project-id <UUID>
```

**Environment Variables:**
- `API_BASE_URL` - API endpoint (default: http://localhost:8000/api/v1)
- `TEST_EMAIL` - Test user email
- `TEST_PASSWORD` - Test user password

---

## 1. Project Events

### 1.1 Project Created (`project.created`)
**Trigger:** Create a new project
**Expected Data:**
- actor: user who created
- project_title: title of project
- category: "project"
- action: "created"

### 1.2 Project Updated (`project.updated`)
**Trigger:** Update project title, description, keywords, or scope
**Expected Data:**
- actor: user who updated
- updated_fields: list of changed fields
- category: "project"
- action: "updated"

---

## 2. Member Events

### 2.1 Member Invited (`member.invited`)
**Trigger:** Invite a user to a project
**Expected Data:**
- actor: user who invited
- invited_user_id, invited_user_name, invited_user_email
- role: assigned role
- category: "member"
- action: "invited"

### 2.2 Member Joined (`member.joined`)
**Trigger:** Accept a project invitation
**Expected Data:**
- actor: user who joined
- role: their role
- category: "member"
- action: "joined"

### 2.3 Member Declined (`member.declined`)
**Trigger:** Decline a project invitation
**Expected Data:**
- actor: user who declined
- category: "member"
- action: "declined"

### 2.4 Member Removed (`member.removed`)
**Trigger:** Remove a member from project
**Expected Data:**
- actor: user who removed
- removed_user_id, removed_user_name, removed_user_email
- category: "member"
- action: "removed"

---

## 3. Paper Events

### 3.1 Paper Created (`paper.created`)
**Trigger:** Create a new paper in a project
**Expected Data:**
- actor: user who created
- paper_id, paper_title
- category: "paper"
- action: "created"

### 3.2 Paper Updated (`paper.updated`)
**Trigger:** Update paper title, content, etc.
**Expected Data:**
- actor: user who updated
- paper_id, paper_title
- updated_fields: list of changed fields
- category: "paper"
- action: "updated"

### 3.3 Reference Linked (`paper.reference-linked`)
**Trigger:** Link a reference to a paper
**Expected Data:**
- actor: user who linked
- paper_id, paper_title
- reference_id, reference_title
- category: "paper"
- action: "reference-linked"

### 3.4 Reference Unlinked (`paper.reference-unlinked`)
**Trigger:** Unlink a reference from a paper
**Expected Data:**
- actor: user who unlinked
- paper_id, paper_title
- reference_id, reference_title
- category: "paper"
- action: "reference-unlinked"

---

## 4. Reference Events (Discovery)

### 4.1 Reference Suggested (`project-reference.suggested`)
**Trigger:** Discovery suggests a reference
**Expected Data:**
- actor: system or user
- reference_title
- category: "project-reference"
- action: "suggested"

### 4.2 Reference Approved (`project-reference.approved`)
**Trigger:** Approve a suggested reference
**Expected Data:**
- actor: user who approved
- reference_title
- category: "project-reference"
- action: "approved"

### 4.3 Reference Rejected (`project-reference.rejected`)
**Trigger:** Reject a suggested reference
**Expected Data:**
- actor: user who rejected
- reference_title
- category: "project-reference"
- action: "rejected"

---

## 5. Sync Session (Call) Events

### 5.1 Call Started (`sync-session.started`)
**Trigger:** Start a video call
**Expected Data:**
- actor: user who started
- session_id
- provider: "daily"
- status: "live"
- category: "sync-session"
- action: "started"

### 5.2 Call Ended (`sync-session.ended`)
**Trigger:** End a video call
**Expected Data:**
- actor: user who ended
- session_id
- duration_seconds
- started_at, ended_at
- status: "ended"
- category: "sync-session"
- action: "ended"

### 5.3 Call Cancelled (`sync-session.cancelled`)
**Trigger:** Cancel a video call
**Expected Data:**
- actor: user who cancelled
- session_id
- status: "cancelled"
- category: "sync-session"
- action: "cancelled"

---

## Verification Checklist

| # | Event Type | Code Exists | Tested | Notes |
|---|------------|-------------|--------|-------|
| 1 | project.created | ✅ | ✅ | Verified with `--create-test-project` |
| 2 | project.updated | ✅ | ✅ | Verified |
| 3 | member.invited | ✅ | ✅ | Verified |
| 4 | member.joined | ✅ | ⏭️ | Requires second user to accept |
| 5 | member.declined | ✅ | ⏭️ | Requires second user to decline |
| 6 | member.removed | ✅ | ✅ | Verified |
| 7 | paper.created | ✅ | ✅ | Verified |
| 8 | paper.updated | ✅ | ✅ | Verified |
| 9 | paper.reference-linked | ✅ | ✅ | Verified (needs approved refs in project) |
| 10 | paper.reference-unlinked | ✅ | ✅ | Verified |
| 11 | project-reference.suggested | ✅ | ⏭️ | Auto-triggered by discovery service |
| 12 | project-reference.approved | ✅ | ⏭️ | Needs pending references |
| 13 | project-reference.rejected | ✅ | ⏭️ | Needs pending references |
| 14 | sync-session.started | ✅ | ✅ | Verified |
| 15 | sync-session.ended | ✅ | ✅ | Verified |
| 16 | sync-session.cancelled | ✅ | ✅ | Verified |

**Summary:** 16/16 have code, 10/16 automatically tested, 6/16 require manual setup.

All 16 activity events have recording code in the backend.
