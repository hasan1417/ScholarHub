# Multi-channel discussion backend + API regression

## Purpose
Validate that the multi-channel discussion data model and API routes behave as expected: channel CRUD, channel-scoped messages and stats, resource tagging, task lifecycle, and generic AI artifact generation.

## Setup
- Container stack running (`docker compose up -d postgres redis onlyoffice backend frontend`).
- Ensure migrations applied: `docker compose exec backend alembic upgrade head`.
- Authenticate as a project member with editor privileges via the frontend or API and note the bearer token.

## Test Data
- Existing project with at least one member besides the requester.
- Sample research paper ID and meeting ID linked to the project to exercise resource tagging.
- AI orchestration enabled in environment (toggle `PROJECT_AI_ORCHESTRATION_ENABLED=true`).

## Steps
1. **Channel lifecycle**
   - `POST /api/v1/projects/{project_id}/discussion/channels` with body `{ "name": "Brainstorm", "description": "Ideas" }`.<br>
     Expect 201 with slug auto-generated.
   - `GET /api/v1/projects/{project_id}/discussion/channels` and confirm new channel present, default channel still marked `is_default=true`.
   - `PUT /api/v1/projects/{project_id}/discussion/channels/{channel_id}` to update name/description and archive flag (set to `true`), then confirm archive flag reflects in list response.
2. **Channel-scoped messaging + stats**
   - `POST /api/v1/projects/{project_id}/discussion/messages` with `{ "content": "First brainstorm note", "channel_id": <brainstorm_channel> }`.
   - `GET /api/v1/projects/{project_id}/discussion/messages?channel_id=<brainstorm>` returns message with `channel_id` and empty attachments.
   - `GET /api/v1/projects/{project_id}/discussion/stats?channel_id=<brainstorm>` shows `total_messages=1`, `total_threads=1`.
   - Repeat `POST` for default channel (omit `channel_id`) and confirm stats remain isolated.
3. **Resource tagging**
   - `POST /api/v1/projects/{project_id}/discussion/channels/{channel_id}/resources` add paper, meeting, tag, and external link (separate requests).
   - `GET /api/v1/projects/{project_id}/discussion/channels/{channel_id}/resources` contains each resource with correct type metadata.
   - Attempt duplicate insert and confirm 409 conflict.
4. **Task tracker**
   - `POST /api/v1/projects/{project_id}/discussion/channels/{channel_id}/tasks` create task referencing the brainstorm message (`message_id`).
   - `GET /api/v1/projects/{project_id}/discussion/tasks?channel_id=<brainstorm>` lists task with `status=open`.
   - `PUT /api/v1/projects/{project_id}/discussion/tasks/{task_id}` set `status":"completed"` and confirm `completed_at` populated; revert to `in_progress` and confirm timestamp cleared.
5. **AI artifact generation (project scoped)**
   - `POST /api/v1/projects/{project_id}/ai/artifacts/generate` with `{ "type": "summary", "focus": "brainstorm recap" }`.
   - `GET /api/v1/projects/{project_id}/ai/artifacts` returns the new artifact in descending order of creation.
   - `POST /api/v1/projects/{project_id}/ai/artifacts/{artifact_id}/status` can update the artifact payload/status as before.

## Expected Results
- All responses return 2xx except the intentional duplicate resource test (409).
- Channel-specific stats/messages never bleed across default channel.
- Resource and task payloads persist and respect delete endpoints.
- Project-level AI artifacts generate successfully without channel linkage.

## Rollback
- Use archive endpoint to hide temporary channel or delete via database if needed.
- Remove created resources/tasks via corresponding DELETE endpoints.
- Optionally delete generated AI artifacts through the status update endpoint.

## Evidence
- Capture cURL outputs or Postman screenshots showing each success response and the 409 duplicate resource attempt.
- Store artifacts under `tests/manual/_evidence/2025-10-05_multi-channel-backend/`.
