// ScholarHub Browser Extension - Popup Script

const $ = (sel) => document.querySelector(sel);

// DOM elements
const statusDot = $('#statusDot');
const statusText = $('#statusText');
const loginView = $('#loginView');
const mainView = $('#mainView');
const paperDetected = $('#paperDetected');
const noPaper = $('#noPaper');
const loginBtn = $('#loginBtn');
const logoutBtn = $('#logoutBtn');
const saveBtn = $('#saveBtn');
const loginMsg = $('#loginMsg');
const saveMsg = $('#saveMsg');
const userNameEl = $('#userName');
const paperTitle = $('#paperTitle');
const paperAuthors = $('#paperAuthors');
const paperYear = $('#paperYear');
const paperSource = $('#paperSource');
const pdfStatus = $('#pdfStatus');
const pdfUpload = $('#pdfUpload');
const dropdownTrigger = $('#dropdownTrigger');
const dropdownText = $('#dropdownText');
const dropdownOptions = $('#dropdownOptions');

let currentPaperData = null;
let selectedPdfFile = null;
let projects = [];
let selectedProjectId = null; // null = Personal Library
let selectedProjectName = null;

// ── Initialization ──

document.addEventListener('DOMContentLoaded', async () => {
  const stored = await chrome.storage.local.get(['instanceUrl', 'accessToken', 'userEmail', 'userName']);

  if (stored.instanceUrl) {
    $('#instanceUrl').value = stored.instanceUrl;
  }

  if (stored.accessToken) {
    showMainView(stored.userName || stored.userEmail || 'User');
    // Fetch projects and detect paper in parallel
    await Promise.all([detectPaper(), fetchProjects()]);
  } else {
    showLoginView();
  }
});

// ── Login ──

loginBtn.addEventListener('click', async () => {
  const instanceUrl = $('#instanceUrl').value.replace(/\/+$/, '');
  const email = $('#email').value.trim();
  const password = $('#password').value;

  if (!instanceUrl || !email || !password) {
    showMessage(loginMsg, 'Please fill in all fields.', 'error');
    return;
  }

  loginBtn.disabled = true;
  loginBtn.textContent = '';
  const spinner = document.createElement('span');
  spinner.className = 'spinner';
  loginBtn.appendChild(spinner);
  loginBtn.appendChild(document.createTextNode(' Signing in...'));
  clearMessage(loginMsg);

  try {
    const resp = await fetch(`${instanceUrl}/api/v1/extension-token`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email, password }),
    });

    if (!resp.ok) {
      const err = await resp.json().catch(() => ({}));
      throw new Error(err.detail || `Login failed (${resp.status})`);
    }

    const data = await resp.json();

    await chrome.storage.local.set({
      instanceUrl,
      accessToken: data.access_token,
      userEmail: data.user_email,
      userName: data.user_name,
      tokenExpiresAt: Date.now() + data.expires_in * 1000,
    });

    showMainView(data.user_name || data.user_email);
    await Promise.all([detectPaper(), fetchProjects()]);
  } catch (err) {
    showMessage(loginMsg, err.message, 'error');
  } finally {
    loginBtn.disabled = false;
    loginBtn.textContent = 'Sign In';
  }
});

// ── Logout ──

logoutBtn.addEventListener('click', async () => {
  await chrome.storage.local.remove(['accessToken', 'userEmail', 'userName', 'tokenExpiresAt']);
  showLoginView();
});

// ── Save paper (direct API call from popup) ──

saveBtn.addEventListener('click', async () => {
  if (!currentPaperData) return;

  if (!selectedProjectId) {
    showMessage(saveMsg, 'Please select a project first.', 'error');
    return;
  }

  saveBtn.disabled = true;
  saveBtn.textContent = '';
  const spinner = document.createElement('span');
  spinner.className = 'spinner';
  saveBtn.appendChild(spinner);
  saveBtn.appendChild(document.createTextNode(' Saving...'));
  clearMessage(saveMsg);

  try {
    const stored = await chrome.storage.local.get(['instanceUrl', 'accessToken', 'tokenExpiresAt']);

    if (!stored.accessToken || !stored.instanceUrl) {
      throw new Error('Not signed in. Please sign in again.');
    }

    if (stored.tokenExpiresAt && Date.now() >= stored.tokenExpiresAt) {
      await chrome.storage.local.remove(['accessToken', 'userEmail', 'userName', 'tokenExpiresAt']);
      throw new Error('Session expired. Please sign in again.');
    }

    const baseUrl = stored.instanceUrl.replace(/\/+$/, '');
    const headers = {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${stored.accessToken}`,
    };

    // Step 1: Create reference
    const payload = {
      title: currentPaperData.title,
      authors: currentPaperData.authors || [],
      year: currentPaperData.year ? parseInt(currentPaperData.year, 10) || null : null,
      doi: currentPaperData.doi || null,
      url: currentPaperData.url || null,
      source: currentPaperData.source || 'browser-extension',
      journal: currentPaperData.journal || null,
      abstract: currentPaperData.abstract || null,
      pdf_url: currentPaperData.pdfUrl || null,
    };

    const refResp = await fetch(`${baseUrl}/api/v1/references/`, {
      method: 'POST',
      headers,
      body: JSON.stringify(payload),
    });

    if (refResp.status === 401) {
      await chrome.storage.local.remove(['accessToken', 'userEmail', 'userName', 'tokenExpiresAt']);
      throw new Error('Session expired. Please sign in again.');
    }

    if (!refResp.ok) {
      const err = await refResp.json().catch(() => ({}));
      const d = err.detail;
      if (typeof d === 'string') throw new Error(d);
      if (d?.error === 'limit_exceeded') throw new Error(`Library limit reached (${d.current}/${d.limit}). Upgrade to add more references.`);
      if (d?.message) throw new Error(d.message);
      throw new Error(err.message || `Request failed (${refResp.status})`);
    }

    const reference = await refResp.json();
    const referenceId = reference.id;

    // Step 2: If project selected, quick-add to project
    if (selectedProjectId) {
      const addResp = await fetch(`${baseUrl}/api/v1/projects/${selectedProjectId}/references/quick-add`, {
        method: 'POST',
        headers,
        body: JSON.stringify({ reference_id: referenceId }),
      });

      if (!addResp.ok) {
        const err = await addResp.json().catch(() => ({}));
        console.warn('Failed to add to project:', err);
        // Non-fatal: reference was still saved to personal library
      }
    }

    // Step 3: Upload PDF — either manual file pick (uploaded from popup)
    // or auto-detected URL (fetched by content script using the page's cookies).
    let pdfUploaded = false;
    const pdfFile = selectedPdfFile;
    const detectedPdfUrl = !pdfFile && currentPaperData.pdfUrl && !reference.document_id
      ? currentPaperData.pdfUrl : null;

    if (pdfFile) {
      // Manual file pick — upload directly from the popup
      try {
        if (pdfFile.size <= 50 * 1024 * 1024) {
          const formData = new FormData();
          formData.append('file', pdfFile, pdfFile.name);

          const pdfResp = await fetch(`${baseUrl}/api/v1/references/${referenceId}/upload-pdf`, {
            method: 'POST',
            headers: { 'Authorization': `Bearer ${stored.accessToken}` },
            body: formData,
          });

          if (pdfResp.ok) {
            pdfUploaded = true;
          }
        }
      } catch (e) {
        console.warn('PDF upload failed (non-fatal):', e);
      }
    } else if (detectedPdfUrl) {
      // Auto-detected PDF — ask the background service worker to fetch + upload.
      // Background has host_permissions CORS bypass for reliable cross-origin fetches.
      try {
        const result = await chrome.runtime.sendMessage({
          type: 'FETCH_AND_UPLOAD_PDF',
          pdfUrl: detectedPdfUrl,
          referenceId,
        });
        if (result?.success) {
          pdfUploaded = true;
        } else if (result?.error) {
          console.warn('PDF fetch/upload failed:', result.error);
        }
      } catch (e) {
        console.warn('PDF fetch/upload failed (non-fatal):', e);
      }
    }

    // Build success message
    let msg = `Saved to ${selectedProjectName}!`;
    if (pdfUploaded) msg += ' with PDF';

    showMessage(saveMsg, msg, 'success');
    saveBtn.textContent = 'Saved';
  } catch (err) {
    showMessage(saveMsg, err.message, 'error');
    saveBtn.disabled = false;
    setSaveBtnDefault();
  }
});

// ── PDF file picker ──

pdfUpload.addEventListener('change', (e) => {
  const file = e.target.files[0];
  if (!file) {
    selectedPdfFile = null;
    updatePdfStatus(currentPaperData);
    return;
  }

  // 50MB limit
  if (file.size > 50 * 1024 * 1024) {
    selectedPdfFile = null;
    pdfUpload.value = '';
    showMessage(saveMsg, 'PDF file must be under 50MB.', 'error');
    return;
  }

  selectedPdfFile = file;
  updatePdfStatus(currentPaperData);
});

// ── Project dropdown ──

dropdownTrigger.addEventListener('click', () => {
  const isOpen = !dropdownOptions.classList.contains('hidden');
  if (isOpen) {
    closeDropdown();
  } else {
    openDropdown();
  }
});

// Close on click outside
document.addEventListener('click', (e) => {
  if (!e.target.closest('#projectDropdown')) {
    closeDropdown();
  }
});

function openDropdown() {
  dropdownOptions.classList.remove('hidden');
  dropdownTrigger.classList.add('open');
}

function closeDropdown() {
  dropdownOptions.classList.add('hidden');
  dropdownTrigger.classList.remove('open');
}

function selectProject(id, name) {
  selectedProjectId = id;
  selectedProjectName = name;
  dropdownText.textContent = name;
  closeDropdown();

  // Update selected state
  dropdownOptions.querySelectorAll('.dropdown-option').forEach((opt) => {
    opt.classList.toggle('selected', opt.dataset.id === (id || ''));
  });
}

function populateDropdown(projectList) {
  dropdownOptions.innerHTML = '';

  if (projectList.length === 0) {
    const emptyOpt = document.createElement('div');
    emptyOpt.className = 'dropdown-option';
    emptyOpt.textContent = 'No projects found';
    emptyOpt.style.color = 'var(--slate-400)';
    emptyOpt.style.cursor = 'default';
    dropdownOptions.appendChild(emptyOpt);
    return;
  }

  // Auto-select the first project
  const first = projectList[0];
  selectProject(String(first.id), first.title);

  // Project options
  for (const project of projectList) {
    const opt = document.createElement('div');
    opt.className = 'dropdown-option';
    if (String(project.id) === selectedProjectId) opt.classList.add('selected');
    opt.textContent = project.title;
    opt.dataset.id = String(project.id);
    opt.setAttribute('role', 'option');
    opt.addEventListener('click', () => selectProject(String(project.id), project.title));
    dropdownOptions.appendChild(opt);
  }
}

async function fetchProjects() {
  try {
    const stored = await chrome.storage.local.get(['instanceUrl', 'accessToken']);
    if (!stored.accessToken || !stored.instanceUrl) return;

    const baseUrl = stored.instanceUrl.replace(/\/+$/, '');
    const resp = await fetch(`${baseUrl}/api/v1/projects/?limit=50`, {
      headers: { 'Authorization': `Bearer ${stored.accessToken}` },
    });

    if (!resp.ok) return;

    const data = await resp.json();
    projects = data.projects || [];
    populateDropdown(projects);
  } catch (err) {
    console.warn('Failed to fetch projects:', err);
  }
}

// ── Paper detection ──

async function detectPaper() {
  try {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    if (!tab?.id) {
      showNoPaper();
      return;
    }

    // Try to get paper data from the content script
    const response = await chrome.tabs.sendMessage(tab.id, { type: 'GET_PAPER_DATA' }).catch(() => null);

    if (response && response.paper) {
      currentPaperData = response.paper;
      showPaperInfo(currentPaperData);
    } else {
      showNoPaper();
    }
  } catch {
    showNoPaper();
  }
}

// ── UI helpers ──

function showLoginView() {
  loginView.classList.remove('hidden');
  mainView.classList.add('hidden');
  setStatus('disconnected', 'Not connected');
}

function showMainView(name) {
  loginView.classList.add('hidden');
  mainView.classList.remove('hidden');
  userNameEl.textContent = name;
  setStatus('connected', 'Connected');
}

function showPaperInfo(paper) {
  paperDetected.classList.remove('hidden');
  noPaper.classList.add('hidden');

  paperTitle.textContent = paper.title || 'Untitled';

  if (paper.authors && paper.authors.length > 0) {
    const authorStr = paper.authors.length > 3
      ? paper.authors.slice(0, 3).join(', ') + ' et al.'
      : paper.authors.join(', ');
    paperAuthors.textContent = authorStr;
  } else {
    paperAuthors.textContent = '';
  }

  paperYear.textContent = paper.year || '';
  paperSource.textContent = paper.source || '';

  updatePdfStatus(paper);
}

function updatePdfStatus(paper) {
  if (!paper) {
    pdfStatus.classList.add('hidden');
    return;
  }

  pdfStatus.classList.remove('hidden');

  if (selectedPdfFile) {
    // User has selected a file manually
    pdfStatus.className = 'pdf-status detected';
    pdfStatus.innerHTML = `
      <span>PDF selected</span>
      <span class="pdf-file-name" style="margin-left:auto">${escapeHtml(selectedPdfFile.name)}</span>
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>
    `;
  } else if (paper.pdfUrl) {
    pdfStatus.className = 'pdf-status detected';
    pdfStatus.innerHTML = `
      <span>PDF available</span>
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>
    `;
  } else {
    pdfStatus.className = 'pdf-status not-detected';
    pdfStatus.innerHTML = `
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>
      <span>No PDF found</span>
      <div class="pdf-upload-row">
        <label class="pdf-upload-label" for="pdfUpload">Upload</label>
      </div>
    `;
  }
}

function showNoPaper() {
  paperDetected.classList.add('hidden');
  noPaper.classList.remove('hidden');
}

function setStatus(state, text) {
  statusDot.className = 'status-dot';
  if (state === 'connected') statusDot.classList.add('connected');
  if (state === 'error') statusDot.classList.add('error');
  statusText.textContent = text;
}

function showMessage(el, text, type) {
  el.className = `msg msg-${type}`;
  el.textContent = text;
}

function clearMessage(el) {
  el.className = '';
  el.textContent = '';
}

function setSaveBtnDefault() {
  saveBtn.textContent = 'Save to Library';
}

function escapeHtml(str) {
  const div = document.createElement('div');
  div.textContent = str;
  return div.innerHTML;
}
