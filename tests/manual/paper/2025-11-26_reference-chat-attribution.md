Purpose:
- Validate that the paper reference AI chat omits citations when answers rely on a single reference and only adds brief source tags when multiple references are used.

Setup:
- Backend running with latest container build.
- One paper with exactly one analyzed reference (PDF processed) and another paper with at least two analyzed references.
- Logged in as a user who can open both papers.

Test Data:
- Paper A: single analyzed reference with PDF.
- Paper B: two analyzed references with PDFs.

Steps:
1) Open Paper A → References → AI Assistant. Ask “Summarize the reference.” then observe the streamed reply.
2) Open Paper B → References → AI Assistant. Ask “Compare the main contributions.” then observe the streamed reply.
3) For Paper B, ask “List any evaluation results.” and watch the streamed output formatting.

Expected Results:
- Step 1: Reply is plain text, no source tags/citations since only one reference is used.
- Step 2: Reply is concise; when statements come from different references, brief source tags like “(Title, Year)” appear only where attribution is needed, not after every sentence.
- Step 3: Streaming stays incremental; no chunk numbers or citation list is appended; no markdown headings are emitted.

Rollback:
- None required.

Evidence:
- Capture screenshots of the Paper B replies showing minimal source tags (tests/manual/_evidence/2025-11-26_reference-chat-attribution.png).
