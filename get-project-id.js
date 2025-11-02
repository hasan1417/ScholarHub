/**
 * Helper script to get your PROJECT_ID for demo recording
 *
 * Run this first to find your project ID:
 * node get-project-id.js
 */

const { chromium } = require('playwright');

async function getProjectId() {
  console.log('🔍 Finding your project ID...\n');

  const browser = await chromium.launch({ headless: false });
  const context = await browser.newContext();
  const page = await context.newPage();

  try {
    // Login
    await page.goto('http://localhost:3000/login');
    await page.fill('input[type="email"]', 'test@example.com');
    await page.fill('input[type="password"]', 'test12345');
    await page.click('button[type="submit"]');

    console.log('✅ Logged in');

    // Wait for navigation to projects page
    await page.waitForURL('**/projects', { timeout: 5000 });

    console.log('✅ On projects page\n');

    // Wait a bit for projects to load
    await page.waitForTimeout(2000);

    // Try to find project links
    const projectLinks = await page.locator('a[href*="/projects/"]').all();

    if (projectLinks.length === 0) {
      console.log('❌ No projects found. Please create a project first!\n');
      console.log('Steps:');
      console.log('1. Go to http://localhost:3000/projects');
      console.log('2. Click "New Project"');
      console.log('3. Create a project');
      console.log('4. Run this script again\n');
    } else {
      console.log(`✅ Found ${projectLinks.length} project(s):\n`);

      for (let i = 0; i < projectLinks.length; i++) {
        const href = await projectLinks[i].getAttribute('href');
        const text = await projectLinks[i].textContent();

        // Extract project ID from URL
        const match = href.match(/\/projects\/([^\/]+)/);
        if (match) {
          const projectId = match[1];
          console.log(`${i + 1}. Project: "${text.trim()}"`);
          console.log(`   ID: ${projectId}\n`);
        }
      }

      console.log('📝 Copy one of the IDs above and update record-demo.js:');
      console.log('   const PROJECT_ID = "paste-id-here"\n');
    }

    // Keep browser open for 5 seconds so you can see the page
    await page.waitForTimeout(5000);

  } catch (error) {
    console.error('❌ Error:', error.message);
    console.log('\nTroubleshooting:');
    console.log('- Make sure your app is running on http://localhost:3000');
    console.log('- Make sure you can login with test@example.com / testpass123');
    console.log('- Make sure you have at least one project created\n');
  } finally {
    await browser.close();
  }
}

getProjectId();
