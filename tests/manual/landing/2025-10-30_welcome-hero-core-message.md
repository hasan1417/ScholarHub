Purpose
- Validate the simplified hero section that focuses solely on the headline, supporting copy, CTAs, and promise cards.

Setup
- Ensure docker stack is running (`docker compose up -d postgres redis onlyoffice backend frontend`).
- Open http://localhost:3000 in a desktop browser at ≥1280px width.
- Optionally enable OS-level “Reduce Motion” to confirm animation behavior.

Test Data
- No authentication required; landing page is public.

Steps
- Navigate to http://localhost:3000 and view the top hero section.
- Confirm the pre-title pill (“Research-ready by design”), headline, paragraph, and both CTAs (“Get started free”, “Explore overview”) render with correct spacing.
- Verify the three promise cards appear underneath, each showing icon + copy without wrapping issues.
- Inspect the new proof block: three stat tiles on the left and a testimonial card on the right (stacks vertically on smaller screens).
- Resize to tablet width (~1024px) to ensure the promise cards and proof block collapse to a stacked layout without gaps.
- Toggle “Reduce Motion” (if available) and reload; confirm the hero fades into view smoothly.

Expected Results
- Typography hierarchy remains intact (pill < headline < supporting paragraph).
- CTAs align side-by-side on desktop and stack cleanly on narrow widths.
- Promise cards maintain consistent padding and border styles; icons stay emerald-colored.
- Proof block displays three stat tiles with indigo accents and a testimonial card with author/role attribution; layout stacks gracefully on smaller screens.
- No imagery loads in the hero; content stays text-forward.

Rollback
- Restore `frontend/src/pages/Landing.tsx` to a previous design if visual regressions occur.

Evidence
- Screenshot: `tests/manual/_evidence/2025-10-30_welcome-hero-core-message.png`.
