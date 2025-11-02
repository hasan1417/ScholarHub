/**
 * Clear localStorage cache for demo paper
 * Run this to clear any cached drafts that might override the seeded content
 */

const { chromium } = require('playwright');

async function clearCache() {
  console.log('🧹 Clearing demo paper cache...\n');

  const browser = await chromium.launch({ headless: false });
  const context = await browser.newContext();
  const page = await context.newPage();

  try {
    // Navigate to the app
    await page.goto('http://localhost:3000/login');

    // Login
    await page.fill('input[type="email"]', 'test@example.com');
    await page.fill('input[type="password"]', 'test12345');
    await page.click('button[type="submit"]');
    await page.waitForTimeout(2000);

    // Clear the localStorage draft for the demo paper
    await page.evaluate(() => {
      const paperId = '90389636-a2cc-4a8d-b7d4-95a52f0f5e1e';
      localStorage.removeItem(`paper:${paperId}:draft`);
      console.log('Cleared draft cache for paper:', paperId);
    });

    console.log('✅ Cache cleared!\n');
    console.log('You can now close the browser and reload your demo paper.\n');

    // Keep browser open for 3 seconds
    await page.waitForTimeout(3000);

  } catch (error) {
    console.error('❌ Error:', error.message);
  } finally {
    await browser.close();
  }
}

clearCache();
