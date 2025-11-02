#!/usr/bin/env bash
# Simple helper to notify ScholarHub that an external recording is ready.
# Usage:
#   ./notify_scholarhub.sh \
#       --api "http://backend:8000" \
#       --token "$SYNC_CALLBACK_TOKEN" \
#       --project "$PROJECT_ID" \
#       --session "$SESSION_ID" \
#       --audio "http://jibri.example/recordings/<file>.wav"

set -euo pipefail

API_BASE=""
CALLBACK_TOKEN=""
PROJECT_ID=""
SESSION_ID=""
AUDIO_URL=""
SUMMARY=""
ACTION_ITEMS=""
TRANSCRIPT_PATH=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --api)
      API_BASE="$2"; shift 2 ;;
    --token)
      CALLBACK_TOKEN="$2"; shift 2 ;;
    --project)
      PROJECT_ID="$2"; shift 2 ;;
    --session)
      SESSION_ID="$2"; shift 2 ;;
    --audio)
      AUDIO_URL="$2"; shift 2 ;;
    --summary)
      SUMMARY="$2"; shift 2 ;;
    --action-items)
      ACTION_ITEMS="$2"; shift 2 ;;
    --transcript-json)
      TRANSCRIPT_PATH="$2"; shift 2 ;;
    *)
      echo "Unknown argument: $1" >&2
      exit 1 ;;
  esac
done

if [[ -z "$API_BASE" || -z "$CALLBACK_TOKEN" || -z "$PROJECT_ID" || -z "$SESSION_ID" || -z "$AUDIO_URL" ]]; then
  echo "Missing required arguments" >&2
  exit 1
fi

if [[ -n "$TRANSCRIPT_PATH" && ! -f "$TRANSCRIPT_PATH" ]]; then
  echo "Transcript file not found: $TRANSCRIPT_PATH" >&2
  exit 1
fi

if [[ -n "$ACTION_ITEMS" ]]; then
  ACTION_ITEMS_JSON="$ACTION_ITEMS"
else
  ACTION_ITEMS_JSON="null"
fi

if [[ -n "$TRANSCRIPT_PATH" ]]; then
  TRANSCRIPT_JSON="$(cat "$TRANSCRIPT_PATH")"
else
  TRANSCRIPT_JSON="null"
fi

payload=$(jq -n \
  --arg audio "$AUDIO_URL" \
  --arg summary "$SUMMARY" \
  --argjson items "$ACTION_ITEMS_JSON" \
  --argjson transcript "$TRANSCRIPT_JSON" \
  '{audio_url: $audio, summary: (if $summary == "" then null else $summary end), action_items: $items, transcript: $transcript}'
)

curl -sS \
  -H "Content-Type: application/json" \
  -H "X-Sync-Token: $CALLBACK_TOKEN" \
  -X POST "$API_BASE/api/v1/projects/$PROJECT_ID/sync-sessions/$SESSION_ID/recording/callback" \
  -d "$payload"
