/**
 * Automated Demo Recording Script for ScholarHub
 *
 * This script automates navigation through ScholarHub features for video recording
 * Duration: ~30 seconds
 *
 * Setup:
 * 1. Install Playwright: npm install -D playwright
 * 2. Make sure your app is running on http://localhost:5173
 * 3. Make sure you're logged in (or update credentials below)
 * 4. Start your screen recording software
 * 5. Run: node record-demo.js
 */

const { chromium } = require('playwright');

// Configuration
const APP_URL = 'http://localhost:3000';
const LOGIN_EMAIL = 'test@example.com';
const LOGIN_PASSWORD = 'test12345';
const PROJECT_ID = '7ce05847-1dc3-4ebb-b930-0b093ee63f3e';
const PAPER_ID = '90389636-a2cc-4a8d-b7d4-95a52f0f5e1e';

async function sleep(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

async function recordDemo() {
  console.log('🎬 Starting ScholarHub demo recording...\n');

  // Launch browser in fullscreen mode
  const browser = await chromium.launch({
    headless: false,
    slowMo: 50, // Slightly slow down actions for smoother recording
    args: ['--start-maximized'] // Start in fullscreen
  });

  const context = await browser.newContext({
    viewport: null, // Use full window size (for fullscreen)
    recordVideo: {
      dir: './recordings/', // Save videos to recordings folder
      size: { width: 1920, height: 1080 }
    }
  });

  const page = await context.newPage();

  try {
    // ============================================
    // LOGIN (if needed)
    // ============================================
    console.log('Step 1: Logging in...');
    await page.goto(`${APP_URL}/login`);
    await sleep(500);

    // Check if already logged in
    const isLoggedIn = await page.url().includes('/projects');

    if (!isLoggedIn) {
      await page.fill('input[type="email"]', LOGIN_EMAIL);
      await page.fill('input[type="password"]', LOGIN_PASSWORD);
      await page.click('button[type="submit"]');
      await sleep(2000); // Wait for login
    }

    console.log('✅ Logged in\n');

    // ============================================
    // SECTION 1: Projects Page (0-3s)
    // ============================================
    console.log('🎬 Section 1: Projects Page');

    // Make sure we're on projects page
    await page.goto(`${APP_URL}/projects`);
    await sleep(2000);

    console.log('✅ On projects page\n');

    // ============================================
    // SECTION 2: Open "Agentic AI" Project (3-5s)
    // ============================================
    console.log('🎬 Section 2: Opening "Agentic AI" project');

    // Find and click "Agentic AI" project
    const agenticAIProject = page.locator('a:has-text("Agentic AI")').first();
    if (await agenticAIProject.isVisible().catch(() => false)) {
      await agenticAIProject.click();
      await sleep(2000);
      console.log('✅ Opened "Agentic AI" project\n');
    } else {
      console.log('⚠️ "Agentic AI" project not found, using PROJECT_ID instead');
      await page.goto(`${APP_URL}/projects/${PROJECT_ID}`);
      await sleep(2000);
    }

    // ============================================
    // SECTION 3: Navigate to Papers Tab (5-7s)
    // ============================================
    console.log('🎬 Section 3: Opening Papers tab');

    // Click on Papers tab
    const papersTab = page.locator('a:has-text("Papers"), [href*="/papers"]').first();
    if (await papersTab.isVisible().catch(() => false)) {
      await papersTab.click();
      await sleep(2000);
      console.log('✅ On Papers tab\n');
    } else {
      // Navigate directly if tab not found
      await page.goto(`${APP_URL}/projects/${PROJECT_ID}/papers`);
      await sleep(2000);
    }

    // ============================================
    // SECTION 4: Open "demo" Paper & Edit (7-20s)
    // ============================================
    console.log('🎬 Section 4: Opening and editing "demo" paper');

    // Find and click "demo" paper
    const demoPaper = page.locator('a:has-text("demo"), [class*="paper"]:has-text("demo")').first();
    if (await demoPaper.isVisible().catch(() => false)) {
      await demoPaper.click();
      await sleep(1500);
      console.log('✅ Opened "demo" paper\n');
    } else {
      console.log('⚠️ "demo" paper not found, using PAPER_ID instead');
      await page.goto(`${APP_URL}/projects/${PROJECT_ID}/papers/${PAPER_ID}`);
      await sleep(1500);
    }

    // Click Edit/Editor button
    const editButton = page.locator('a:has-text("Editor"), button:has-text("Edit"), a[href*="/editor"]').first();
    if (await editButton.isVisible().catch(() => false)) {
      await editButton.click();
      await sleep(2000);
    } else {
      // Navigate directly to editor
      await page.goto(`${APP_URL}/projects/${PROJECT_ID}/papers/${PAPER_ID}/editor`);
      await sleep(2000);
    }

    console.log('🎬 Typing LaTeX content...');

    // Type in the editor
    const editorVisible = await page.locator('.CodeMirror, .cm-editor, textarea').isVisible().catch(() => false);

    if (editorVisible) {
      // Click in the editor to focus it
      const editor = page.locator('.CodeMirror, .cm-editor, textarea').first();
      await editor.click();
      await sleep(500);

      // Navigate to the insertion point (after the comment line)
      // Press Ctrl+End (or Cmd+Down on Mac) to go to end, then up a bit
      await page.keyboard.press('End'); // Go to end of document
      await sleep(200);

      // Now type the ML content
      await page.keyboard.type('\n\\section{Machine Learning Architecture}\n\n', { delay: 80 });
      await sleep(300);
      await page.keyboard.type('The transformer model uses attention mechanisms:\n\n', { delay: 80 });
      await sleep(300);
      await page.keyboard.type('\\begin{equation}\n', { delay: 80 });
      await page.keyboard.type('  \\text{Attention}(Q, K, V) = \\text{softmax}\\left(\\frac{QK^T}{\\sqrt{d_k}}\\right)V\n', { delay: 60 });
      await page.keyboard.type('\\end{equation}\n', { delay: 80 });
      await sleep(2000);

      console.log('✅ LaTeX typed successfully\n');
    }

    // ============================================
    // SECTION 5: Browse Other Tabs (20-30s)
    // ============================================
    console.log('🎬 Section 5: Browsing other project features');

    // Go back to project overview
    await page.goto(`${APP_URL}/projects/${PROJECT_ID}`);
    await sleep(1500);

    // Navigate to Library/Discovery
    console.log('   → Discovery tab');
    await page.goto(`${APP_URL}/projects/${PROJECT_ID}/library/discover`);
    await sleep(2000);

    // Scroll through discoveries
    await page.evaluate(() => {
      window.scrollTo({ top: 400, behavior: 'smooth' });
    });
    await sleep(1500);

    // Navigate to Collaborate
    console.log('   → Collaborate tab');
    await page.goto(`${APP_URL}/projects/${PROJECT_ID}/collaborate/chat`);
    await sleep(2000);

    // Click on first channel if exists
    const channelExists = await page.locator('[class*="channel"]').first().isVisible().catch(() => false);
    if (channelExists) {
      await page.locator('[class*="channel"]').first().click();
      await sleep(1500);
    }

    console.log('✅ Browsing complete\n');

    // ============================================
    // SECTION 6: Return to Projects (30s+)
    // ============================================
    console.log('🎬 Section 6: Returning to projects page');

    await page.goto(`${APP_URL}/projects`);
    await sleep(2000);

    console.log('✅ Demo complete (30s)\n');
    console.log('🎬 Saving video recording...\n');

    // Keep browser open for 2 seconds to ensure smooth ending
    await sleep(2000);

  } catch (error) {
    console.error('❌ Error during demo recording:', error);
  } finally {
    // Close context to finalize video recording
    await context.close();
    await browser.close();

    console.log('✅ Recording saved!\n');
    console.log('📹 Video location: ./recordings/\n');
    console.log('The video file will be saved as a .webm file.');
    console.log('You can convert it to MP4 using:');
    console.log('  ffmpeg -i recordings/video.webm demo-video.mp4\n');
  }
}

// Run the demo
recordDemo();
