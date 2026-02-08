# Manual QA - Policy + Memory Routing

This checklist validates deterministic routing, context carry-over, and tool argument normalization.

## Test Sequence (Single Channel)

1. `My research question is: How does sleep deprivation affect cognitive function in medical residents?`
2. `Can you find me 5 recent papers on this topic?`
3. `Can you find another 3 papers?`
4. `Find 4 open access papers from the last 3 years on this topic.`
5. `Please update project keywords to sleep deprivation, cognition, medical residents.`
6. `Can you find papers on climate adaptation policy from 2021 to 2024?`

## Expected Behavior

### Step 2
- Tool called: `search_papers`
- Effective query reflects sleep/cognition topic (not filler text)
- `count=5`, `limit=5`
- Recency filter applied (`year_from=current_year-4`, `year_to=current_year`)

### Step 3
- Tool called: `search_papers`
- Query reuses previous effective topic (must not be literal `another 3 papers`)
- `count=3`, `limit=3`

### Step 4
- Tool called: `search_papers`
- `count=4`, `limit=4`
- `open_access_only=true`
- Last-3-years filter applied (`year_from=current_year-2`, `year_to=current_year`)

### Step 5
- Tool called: `update_project_info`
- Search tools are not executed in the same turn
- If mode fields are omitted by model, update mode is inferred from user intent (`add` => `append`)

### Step 6
- Tool called: `search_papers`
- Query contains climate adaptation policy topic
- Exact year bounds: `year_from=2021`, `year_to=2024`

## Logs and SQL Checks

### Policy + Args Logs
- Check `[PolicyDecision]` includes:
  - `intent`
  - `action_plan.primary_tool`
  - `action_plan.blocked_tools`
  - `search.query`, `count`, `year_from`, `year_to`
- Check `[SearchArgs]` includes normalized final args (not raw model args)

### SQL / Memory State
Confirm `search_state.last_effective_topic` updates after successful searches:

```sql
SELECT
  id,
  ai_memory->'search_state'->>'last_effective_topic' AS last_effective_topic,
  ai_memory->'search_state'->>'last_count' AS last_count,
  ai_memory->'search_state'->>'last_updated_at' AS last_updated_at
FROM project_discussion_channels
WHERE id = '<channel_id>'
ORDER BY updated_at DESC
LIMIT 1;
```
