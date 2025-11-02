# Manual Test - Paper Discovery Modal Content Rendering

**Purpose**
Ensure the Paper Discovery modal loads content preview states correctly without React render errors.

**Setup**
1. Frontend dev server running (`npm run dev`).
2. Backend running with authenticated session.
3. Access token stored in localStorage so discovery endpoints succeed.

**Test Data**
- Use any paper in discovery results that supports content preview or PDF metadata.

**Steps**
1. Open the discovery hub and run a search that returns at least one paper.
2. Click "Attach to Paper" or otherwise trigger the modal so that `selectedPaper` is set.
3. From the results list, click the action that opens the modal content preview.
4. Observe the modal with different server responses:
   - Initial `loading` state.
   - Error response (trigger by re-opening after clearing cache if needed).
   - PDF response (paper with `pdf_url` or `content_type === 'pdf'`).
   - Full text response with `chunks` array when available.
5. Close the modal using the “×” button.

**Expected Results**
- Step 2-3: Modal renders without blank screen or console errors.
- Loading state shows spinner; error state renders retry button.
- Chunk results display scrollable preview; PDF state shows action buttons and guidance.
- Default fallback shows content preview text and link to original paper.
- Closing the modal resets state without warnings.

**Rollback**
No rollback required.

**Evidence**
- None captured (verified interactively).
