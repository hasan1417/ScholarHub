const path = require('path')
const { chromium } = require('@playwright/test')

const APP_URL = 'http://localhost:3000'
const LOGIN_EMAIL = 'g202403940@kfupm.edu.sa'
const LOGIN_PASSWORD = 'testpass123'

const SCENES = [
  {
    name: 'hero-editor',
    url: `${APP_URL}/projects/7ce05847-1dc3-4ebb-b930-0b093ee63f3e/papers/6b6765ea-a3c3-4ce4-8ee9-52763c0a1564/editor`,
    waitFor: 'iframe',
    settle: 2500,
  },
  {
    name: 'hero-overview',
    url: `${APP_URL}/projects/7ce05847-1dc3-4ebb-b930-0b093ee63f3e`,
    waitFor: 'main',
    settle: 1200,
  },
  {
    name: 'hero-library',
    url: `${APP_URL}/projects/7ce05847-1dc3-4ebb-b930-0b093ee63f3e/library/discover`,
    waitFor: '[data-testid="discovery-search"], main',
    settle: 1200,
  },
]

async function captureScene(page, { name, url, waitFor, settle }) {
  const outputPath = path.join(__dirname, '..', 'frontend', 'src', 'assets', `${name}.png`)
  await page.goto(url, { waitUntil: 'domcontentloaded' })
  await page.waitForLoadState('networkidle', { timeout: 60000 }).catch(() => {})
  if (waitFor) {
    if (waitFor.includes(',')) {
      const selectors = waitFor.split(',').map(s => s.trim())
      for (const selector of selectors) {
        try {
          await page.waitForSelector(selector, { timeout: 15000 })
          break
        } catch (_) {}
      }
    } else {
      await page.waitForSelector(waitFor, { timeout: 15000 })
    }
  }
  if (settle) {
    await page.waitForTimeout(settle)
  }
  await page.screenshot({ path: outputPath, type: 'png', fullPage: false })
  console.log(`📸 Captured ${name} -> ${outputPath}`)
}

async function run() {
  const browser = await chromium.launch({ headless: true })
  const context = await browser.newContext({
    viewport: { width: 1440, height: 900 },
    deviceScaleFactor: 2,
  })

  const page = await context.newPage()

  await page.addInitScript(() => {
    try {
      window.localStorage.setItem('scholarhub.theme', 'light')
    } catch (_) {}
  })

  await page.goto(`${APP_URL}/login`, { waitUntil: 'domcontentloaded' })
  await page.fill('input[type="email"]', LOGIN_EMAIL, { timeout: 5000 })
  await page.fill('input[type="password"]', LOGIN_PASSWORD)
  await Promise.all([
    page.waitForNavigation({ waitUntil: 'networkidle' }),
    page.click('button[type="submit"]'),
  ])

  for (const scene of SCENES) {
    try {
      await captureScene(page, scene)
    } catch (error) {
      console.error(`❌ Failed to capture ${scene.name}:`, error)
    }
  }

  await browser.close()
}

run().catch((error) => {
  console.error('Failed to capture hero screenshots', error)
  process.exitCode = 1
})
