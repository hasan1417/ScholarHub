# ScholarHub Demo Video Recording Guide

## ✅ UPDATED: Now with Built-in Screen Recording!

The script now automatically records the browser screen - no need for external recording software!

## What the Script Does (~35 seconds)

1. **Login & Projects Page (0-3s)**
   - Logs in automatically
   - Shows projects page

2. **Open "Agentic AI" Project (3-5s)**
   - Finds and clicks on "Agentic AI" project
   - Opens project overview

3. **Navigate to Papers (5-7s)**
   - Clicks on Papers tab
   - Shows list of papers

4. **Edit "demo" Paper (7-20s)**
   - Finds and clicks "demo" LaTeX paper
   - Opens editor (pre-populated with LaTeX template)
   - Adds impressive LaTeX content about ML transformers
   - Shows live LaTeX rendering

5. **Browse Other Features (20-30s)**
   - Returns to project overview
   - Visits Discovery tab → scrolls through papers
   - Visits Collaborate tab → shows team chat

6. **Clean Close (30-35s)**
   - Returns to projects page
   - Smooth ending

---

## Setup Instructions

### Step 1: Install Playwright
```bash
cd /Users/hassan/Desktop/Coding/MX/Final\ Project/ScholarHub
npm install -D playwright
```

### Step 2: Update Configuration
Open `record-demo.js` and update these values:

```javascript
const LOGIN_EMAIL = 'your-email@example.com';     // Your login email
const LOGIN_PASSWORD = 'your-password';           // Your password
const PROJECT_ID = 'your-project-id';             // An existing project ID
```

**How to get PROJECT_ID:**
1. Log into ScholarHub
2. Open a project
3. Look at the URL: `http://localhost:5173/app/projects/abc-123-xyz`
4. Copy the ID: `abc-123-xyz`

### Step 3: Prepare Your Environment
Before recording, make sure:
- ✅ Your app is running: `docker compose up`
- ✅ You have at least one project created
- ✅ That project has at least one paper named "demo" (pre-populated with LaTeX content)
- ✅ That project has at least one chat channel
- ✅ Close unnecessary applications (for best performance)

**Note:** The "demo" paper has been pre-populated with a LaTeX template so the editor shows content from the start.

### Step 4: Run the Recording
```bash
node record-demo.js
```

That's it! The script will:
- ✅ Launch the browser automatically
- ✅ Record everything to video
- ✅ Save the recording to `./recordings/` folder
- ✅ Close and finalize the video when done

**No need for external screen recording software!**

---

## Recording Tips

### Best Practices:
- ✅ The script records at 1920x1080 automatically
- ✅ Browser opens in a clean profile (no extensions/bookmarks)
- ✅ Turn off system notifications before running
- ✅ Close other applications to avoid distractions
- ✅ Make sure your system isn't under heavy load (for smooth recording)

### If Something Goes Wrong:
- **Script errors?** Check that PROJECT_ID is correct
- **No papers?** Create a paper with LaTeX content first
- **Too fast/slow?** Edit the `sleep()` values in the script
- **Want longer sections?** Increase sleep times for specific sections

### Customization:
Edit `record-demo.js` to adjust:
- `slowMo: 50` - Makes actions slower (increase for smoother video)
- `sleep(1500)` - Pauses between actions (increase for longer sections)
- Navigation URLs - Change which pages to visit

---

## After Recording

### Step 1: Find Your Video
The recording will be saved in the `recordings/` folder as a `.webm` file.

### Step 2: Convert to MP4 (Recommended)
WebM works in most browsers, but MP4 is more universal:

**Using ffmpeg (install with: `brew install ffmpeg`)**
```bash
# Find your video file
ls recordings/

# Convert to MP4
ffmpeg -i recordings/your-video-file.webm demo-video.mp4
```

**Or use an online converter:**
- CloudConvert.com
- Online-convert.com

### Step 3: Place Video in Project
```bash
# Move to frontend public folder
mv demo-video.mp4 frontend/public/
```

### Optional: Video Editing
If you want to enhance the video:
1. **Trim** any extra seconds at start/end
2. **Add background music** (optional, keep subtle)
3. **Add captions** for key features
4. Use tools like: iMovie, DaVinci Resolve (free), or online editors

### Final Video Specs:
- Format: MP4 (H.264)
- Resolution: 1920x1080
- Duration: ~30 seconds
- File size: 5-15 MB (aim for under 10 MB)

---

## Alternative: Manual Recording

If the script doesn't work perfectly, follow this manual checklist:

**0-12s: Editor**
- [ ] Open project papers page
- [ ] Click first paper → Editor
- [ ] Type: `\section{Introduction}`
- [ ] Type: `Consider the equation: $E = mc^2$`
- [ ] Type a LaTeX equation block
- [ ] Pause to show rendering

**12-20s: Discovery**
- [ ] Click Library tab → Discover
- [ ] Scroll slowly through papers
- [ ] Hover over 2-3 papers

**20-28s: Collaborate**
- [ ] Click Collaborate tab → Chat
- [ ] Click a channel
- [ ] Show messages scrolling

**28-30s: Close**
- [ ] Return to Projects page

---

## Troubleshooting

### "Cannot find PROJECT_ID"
Create a project first:
1. Go to http://localhost:5173/app/projects
2. Click "New Project"
3. Create it
4. Copy the ID from the URL

### "Login failed"
- Check credentials in script
- Try logging in manually first
- Check if backend is running

### "Script runs too fast"
Increase `slowMo` value:
```javascript
const browser = await chromium.launch({
  headless: false,
  slowMo: 100 // Increase this (was 50)
});
```

### "Need more time on a section"
Increase `sleep()` times for that section:
```javascript
await sleep(3000); // 3 seconds instead of 1.5
```

---

## Questions?

If you need help:
1. Check the console output for errors
2. Verify all prerequisites are met
3. Try manual recording if automation fails
4. Adjust timing values as needed

Good luck with your recording! 🎬
