#!/usr/bin/env python3
"""
ScholarHub Screenshot Automation Script
Captures screenshots of all main features for the project report.
"""

import asyncio
from playwright.async_api import async_playwright
import os

# Configuration
BASE_URL = "http://localhost:3000"
EMAIL = "g202403940@kfupm.edu.sa"
PASSWORD = "testpass123"
SCREENSHOTS_DIR = os.path.join(os.path.dirname(__file__), "screenshots")

# Ensure screenshots directory exists
os.makedirs(SCREENSHOTS_DIR, exist_ok=True)


async def safe_screenshot(page, name, wait_time=2):
    """Take a screenshot with error handling."""
    try:
        await asyncio.sleep(wait_time)
        await page.screenshot(path=f"{SCREENSHOTS_DIR}/{name}.png", full_page=False)
        print(f"   Saved: {name}.png")
        return True
    except Exception as e:
        print(f"   Failed to save {name}: {e}")
        return False


async def capture_screenshots():
    async with async_playwright() as p:
        # Launch browser
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={"width": 1920, "height": 1080},
            device_scale_factor=2  # Retina quality
        )
        page = await context.new_page()

        print("=" * 60)
        print("ScholarHub Screenshot Capture")
        print("=" * 60)

        # 1. Login Page
        print("\n[1/12] Login Page...")
        await page.goto(f"{BASE_URL}/login")
        await page.wait_for_load_state("networkidle")
        await safe_screenshot(page, "01_login_page", 1)

        # 2. Perform Login
        print("\n[2/12] Logging in...")
        try:
            await page.fill('input[type="email"]', EMAIL)
            await page.fill('input[type="password"]', PASSWORD)
            await page.click('button[type="submit"]')
            await page.wait_for_load_state("networkidle")
            await asyncio.sleep(3)
            print("   Login successful")
        except Exception as e:
            print(f"   Login error: {e}")

        # 3. Projects Dashboard
        print("\n[3/12] Projects Dashboard...")
        await page.goto(f"{BASE_URL}/projects")
        await page.wait_for_load_state("networkidle")
        await safe_screenshot(page, "02_projects_dashboard", 2)

        # Find first project ID from the URL or page content
        project_id = None
        try:
            # Click first project
            project_link = await page.query_selector('a[href*="/projects/"]')
            if project_link:
                href = await project_link.get_attribute('href')
                if href and '/projects/' in href:
                    parts = href.split('/projects/')
                    if len(parts) > 1:
                        project_id = parts[1].split('/')[0]
                        print(f"   Found project: {project_id}")
        except Exception as e:
            print(f"   Error finding project: {e}")

        if project_id:
            # 4. Project Overview
            print("\n[4/12] Project Overview...")
            await page.goto(f"{BASE_URL}/projects/{project_id}")
            await page.wait_for_load_state("networkidle")
            await safe_screenshot(page, "03_project_overview", 2)

            # 5. Papers List
            print("\n[5/12] Papers List...")
            await page.goto(f"{BASE_URL}/projects/{project_id}/papers")
            await page.wait_for_load_state("networkidle")
            await safe_screenshot(page, "04_papers_list", 2)

            # Get paper ID for editor
            paper_id = None
            try:
                paper_link = await page.query_selector('a[href*="/papers/"]')
                if paper_link:
                    href = await paper_link.get_attribute('href')
                    if href and '/papers/' in href:
                        paper_id = href.split('/papers/')[-1].split('/')[0].split('?')[0]
                        print(f"   Found paper: {paper_id}")
            except Exception as e:
                print(f"   Error finding paper: {e}")

            # 6. Paper Editor
            if paper_id:
                print("\n[6/12] Paper Editor...")
                await page.goto(f"{BASE_URL}/projects/{project_id}/papers/{paper_id}")
                await page.wait_for_load_state("networkidle")
                await asyncio.sleep(3)  # Wait for editor to load
                await safe_screenshot(page, "05_paper_editor", 2)

                # 7. AI Chat Panel
                print("\n[7/12] AI Chat Panel...")
                try:
                    # Try to find and click AI chat button
                    ai_selectors = [
                        'button[aria-label*="AI"]',
                        'button:has-text("AI")',
                        '[data-testid="ai-chat"]',
                        '.ai-toggle',
                        'button[title*="AI"]',
                    ]
                    for selector in ai_selectors:
                        try:
                            btn = await page.query_selector(selector)
                            if btn:
                                await btn.click()
                                await asyncio.sleep(2)
                                await safe_screenshot(page, "06_ai_chat", 1)
                                break
                        except:
                            continue
                except Exception as e:
                    print(f"   AI Chat: {e}")
            else:
                print("\n[6/12] Paper Editor... (skipped - no papers found)")
                print("\n[7/12] AI Chat Panel... (skipped)")

            # 8. Library / References
            print("\n[8/12] Library...")
            await page.goto(f"{BASE_URL}/projects/{project_id}/library")
            await page.wait_for_load_state("networkidle")
            await safe_screenshot(page, "07_library", 2)

            # 9. Discovery (inside library or separate)
            print("\n[9/12] Discovery...")
            try:
                # Try discovery sub-route first
                await page.goto(f"{BASE_URL}/projects/{project_id}/library/discover")
                await page.wait_for_load_state("networkidle")
                await safe_screenshot(page, "08_discovery", 2)
            except:
                # Try related-papers route
                try:
                    await page.goto(f"{BASE_URL}/projects/{project_id}/related-papers")
                    await page.wait_for_load_state("networkidle")
                    await safe_screenshot(page, "08_discovery", 2)
                except Exception as e:
                    print(f"   Discovery: {e}")

            # 10. Discussion
            print("\n[10/12] Discussion...")
            await page.goto(f"{BASE_URL}/projects/{project_id}/discussion")
            await page.wait_for_load_state("networkidle")
            await safe_screenshot(page, "09_discussion", 2)

            # 11. Collaborate / Sync Space
            print("\n[11/12] Collaboration / Sync Space...")
            try:
                await page.goto(f"{BASE_URL}/projects/{project_id}/collaborate")
                await page.wait_for_load_state("networkidle")
                await safe_screenshot(page, "10_collaborate", 2)
            except:
                try:
                    await page.goto(f"{BASE_URL}/projects/{project_id}/sync-space")
                    await page.wait_for_load_state("networkidle")
                    await safe_screenshot(page, "10_sync_space", 2)
                except Exception as e:
                    print(f"   Collaborate: {e}")

            # 12. References management
            print("\n[12/12] References...")
            try:
                await page.goto(f"{BASE_URL}/projects/{project_id}/library/references")
                await page.wait_for_load_state("networkidle")
                await safe_screenshot(page, "11_references", 2)
            except Exception as e:
                print(f"   References: {e}")

        else:
            print("\n   No project found - skipping project-specific screenshots")

        # Close browser
        await browser.close()

        print("\n" + "=" * 60)
        print("Screenshot capture complete!")
        print("=" * 60)

        # List captured screenshots
        screenshots = sorted([f for f in os.listdir(SCREENSHOTS_DIR) if f.endswith('.png')])
        print(f"\nCaptured {len(screenshots)} screenshots:")
        for s in screenshots:
            size = os.path.getsize(f"{SCREENSHOTS_DIR}/{s}") / 1024
            print(f"  - {s} ({size:.1f} KB)")


if __name__ == "__main__":
    asyncio.run(capture_screenshots())
