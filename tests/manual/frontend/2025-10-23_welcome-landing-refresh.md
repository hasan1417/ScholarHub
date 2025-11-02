## Purpose
Validate the signed-out landing page updates for researcher-focused messaging, motion accessibility, and new CTAs.

## Setup
- Frontend running locally (dev or preview build).
- Browser with and without `prefers-reduced-motion` enabled for comparison.

## Test Data
- No account needed; use signed-out session.

## Steps
1. Open the ScholarHub root URL in a private window.
2. Confirm the hero headline and subtext reference researcher workflows, the CTA pair “Get started free” / “Take the tour,” and the illustration depicting the LaTeX workspace.
3. Resize the browser below 1024px width to ensure the hero illustration stacks below the copy with consistent spacing.
4. Sign in, then immediately sign out from the settings menu.
5. Confirm the app redirects to the landing page (not the login page) and the hero renders as in step 2.
6. Scroll to the trust strip and feature cards; read each card for outcome-driven messaging.
7. Scroll further to the “How it works” steps and testimonial, ensuring layout renders correctly on desktop width.
8. Enable “Reduce motion” in OS accessibility settings, reload the page, and confirm the hero section loads without entrance animation while still rendering the static illustration.

## Expected Results
- Hero clearly targets research teams, shows both primary and secondary CTAs, and displays the illustration without layout overlap.
- Signing out returns the user to the landing page rather than the login view.
- Trust strip highlights coordination, versioning, and literature benefits with balanced typography.
- Feature cards use outcome-oriented descriptions and consistent spacing.
- “How it works” sequence displays numbered steps with supporting text.
- With “Reduce motion” enabled, hero content immediately appears without transition and the illustration remains visible.

## Rollback
- Revert OS “Reduce motion” setting if changed for testing.

## Evidence
- Not captured for this run.
