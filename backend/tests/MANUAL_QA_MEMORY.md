# Manual QA: Memory Reliability + Research Quality

**Date:** 2026-02-07
**Tester:** _______________
**Channel IDs used:** _______________

## Execution Rules (Deterministic)

1. Use prompts exactly as written (no paraphrasing).
2. Wait for the full AI response before checking DB state.
3. Run the SQL check immediately after each test prompt.
4. If a test says "New channel", do not reuse an old channel.
5. Record the channel ID and message index for each test in Notes.
6. Mark `Pass?` only when expected conditions are met exactly.

## How to Check Results

```sql
SELECT
  id,
  updated_at,
  ai_memory->'facts'->>'research_question' as rq,
  ai_memory->'facts'->>'research_topic' as topic,
  ai_memory->'facts'->'unanswered_questions' as unanswered,
  ai_memory->'facts'->'decisions_made' as decisions,
  ai_memory->'summary' as summary,
  ai_memory->'key_quotes' as quotes,
  ai_memory->'long_term'->'user_preferences' as prefs,
  ai_memory->'long_term'->'rejected_approaches' as rejections,
  ai_memory->'research_state'->>'stage' as stage
FROM project_discussion_channels
WHERE id = '<YOUR_CHANNEL_ID>'
ORDER BY updated_at DESC LIMIT 1;
```

---

## Test 1: Explicit Research Question (Fix 1 — direct regex)

**Prompt:**
> My research question is: How does social media usage affect academic performance among university students?

| Field | Expected | Actual | Pass? |
|---|---|---|---|
| `research_question` | Contains "social media" and "academic performance" | | [ ] |
| `research_topic` | Populated (LLM-generated, about social media/academics) | | [ ] |
| `stage` | `"exploring"` | | [ ] |
| `key_quotes` | Contains entry mentioning social media | | [ ] |

---

## Test 2: RQ Preservation After Casual Follow-up (Fix 1)

**Prompt (send right after Test 1, same channel):**
> Can you find me some recent papers on this topic?

| Field | Expected | Actual | Pass? |
|---|---|---|---|
| `research_question` | **Unchanged** from Test 1 — must NOT be null | | [ ] |
| `stage` | Exactly `"finding_papers"` | | [ ] |

---

## Test 3: Urgency Bypass — Early Decision (Fix 2)

**Setup:** New channel. Send this as the 1st or 2nd message.

**Prompt:**
> I've decided to focus on the impact of sleep deprivation on cognitive function in medical residents.

| Field | Expected | Actual | Pass? |
|---|---|---|---|
| `research_topic` | Populated (sleep deprivation / cognitive function) even at exchange #1 | | [ ] |
| `decisions_made` | Contains entry about this decision | | [ ] |

**Why this matters:** Without Fix 2, the rate limiter would skip fact extraction on exchanges #1-2 and `research_topic` would stay null.

---

## Test 4: Implied RQ via Investigation Pattern (Fix 1)

**Prompt:**
> I'm investigating how renewable energy subsidies influence adoption rates in developing countries.

| Field | Expected | Actual | Pass? |
|---|---|---|---|
| `research_question` | Contains "renewable energy subsidies" and "adoption rates" | | [ ] |
| `key_quotes` | Should capture a related statement | | [ ] |

---

## Test 5: Standalone Research Question (Fix 1)

**Setup:** New channel. Send only this message.

**Prompt:**
> What is the relationship between childhood trauma and substance abuse disorders in adulthood?

| Field | Expected | Actual | Pass? |
|---|---|---|---|
| `research_question` | The full question text (standalone ?, >30 chars) | | [ ] |

---

## Test 6: Unanswered Question — False Positive Filter (Fix 4)

**Prompt:**
> I know how transformers work. What I want is to compare BERT and GPT for my use case, right?

| Field | Expected | Actual | Pass? |
|---|---|---|---|
| `unanswered_questions` | **Empty** — "I know" is declarative, should be filtered | | [ ] |

---

## Test 7: Real Unanswered Question — Should Track (Fix 4)

**Prompt:**
> I still have an unanswered question for later: What evaluation metrics are most appropriate for measuring bias in large language models?

| Field | Expected | Actual | Pass? |
|---|---|---|---|
| `unanswered_questions` | Contains this question text (or a close paraphrase including "evaluation metrics" + "bias" + "large language models") | | [ ] |

---

## Test 8: Preferences and Rejections (Long-term Memory)

**Prompt 1:**
> I prefer using quantitative methods and papers from the last 3 years.

**Prompt 2:**
> I don't want to use survey-based studies, they're not suitable for my research.

| Field | Expected | Actual | Pass? |
|---|---|---|---|
| `user_preferences` | Contains entry with "prefer using quantitative" | | [ ] |
| `rejected_approaches` | Contains entry with "don't want to use survey" | | [ ] |

---

## Test 9: Incremental Summary for Short Sessions (Fix 5)

**Setup:** New channel. Send 6+ back-and-forth messages on any topic.

**Check after message 4:**

| Field | Expected | Actual | Pass? |
|---|---|---|---|
| `summary` | `null` (not enough messages yet) | | [ ] |

**Check after message 6+:**

| Field | Expected | Actual | Pass? |
|---|---|---|---|
| `summary` | **Not null** — bullet-point summary generated | | [ ] |

---

## Test 10: Context Carryover — RQ Survives Across Messages (Fix 3)

**Setup:** New channel. Send these 3 messages in order.

**Prompt 1:**
> My research question is: How does air pollution exposure during pregnancy affect neonatal health outcomes?

**Prompt 2:**
> What databases should I search for this kind of epidemiological research?

**Prompt 3:**
> Can you also suggest some keywords for my search strategy?

**Check after Prompt 3:**

| Field | Expected | Actual | Pass? |
|---|---|---|---|
| `research_question` | **Still populated** from Prompt 1 (contains "air pollution") | | [ ] |
| `research_topic` | About air pollution / neonatal health | | [ ] |

**Why this matters:** Fix 3 passes recent messages as context to the LLM, so it doesn't forget the RQ stated 2 messages ago.

---

## Test 11: Search Query Quality — No Year Spam

**Setup:** New channel.

**Prompt:**
> Find recent papers about social media usage and academic performance among university students.

**How to inspect query:** Capture the actual `search_papers` query from tool payload/logs.

| Field | Expected | Actual | Pass? |
|---|---|---|---|
| `search_papers.query` | Does **not** include raw year lists like `2020 2021 2022 2023` | | [ ] |
| `search_papers.query` | Uses concise academic phrasing (not keyword dump) | | [ ] |

---

## Test 12: Search Query Quality — High-Signal Coverage

**Setup:** New channel.

**Prompt:**
> I've decided to focus on the impact of sleep deprivation on cognitive function in medical residents. Find papers.

**How to inspect query:** Capture the actual `search_papers` query from tool payload/logs.

| Field | Expected | Actual | Pass? |
|---|---|---|---|
| `search_papers.query` | Includes at least 2 core concepts from prompt (`sleep deprivation`, `cognitive function`, `medical residents`) | | [ ] |
| `search_papers.query` | Reasonably concise (roughly 4-10 terms) | | [ ] |

---

## Summary Scorecard

| # | Test | Description | Result |
|---|---|---|---|
| 1 | Explicit RQ | `research_question` populated after "My RQ is: ..." | [ ] |
| 2 | RQ preservation | `research_question` unchanged after casual follow-up | [ ] |
| 3 | Urgency bypass | `research_topic` populated on exchange #1-2 | [ ] |
| 4 | Investigation RQ | `research_question` extracted from "I'm investigating..." | [ ] |
| 5 | Standalone question | `research_question` extracted from plain "?" message | [ ] |
| 6 | False positive filter | `unanswered_questions` empty for declarations | [ ] |
| 7 | Real question tracked | `unanswered_questions` captures explicit "unanswered question for later" | [ ] |
| 8 | Prefs & rejections | Both `user_preferences` and `rejected_approaches` populated | [ ] |
| 9 | Incremental summary | `summary` not null after 6 exchanges | [ ] |
| 10 | Context carryover | RQ survives across 3 messages | [ ] |
| 11 | No year spam | Search query avoids raw year-list stuffing | [ ] |
| 12 | High-signal query | Search query captures core concepts concisely | [ ] |

**Overall: ___ / 12 passed**

---

## Notes / Issues Found

```
(Write any issues, unexpected behavior, or observations here)
```
