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

let currentPaperData = null;

// ── Initialization ──

document.addEventListener('DOMContentLoaded', async () => {
  const stored = await chrome.storage.local.get(['instanceUrl', 'accessToken', 'userEmail', 'userName']);

  if (stored.instanceUrl) {
    $('#instanceUrl').value = stored.instanceUrl;
  }

  if (stored.accessToken) {
    showMainView(stored.userName || stored.userEmail || 'User');
    await detectPaper();
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
    await detectPaper();
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

// ── Save paper ──

saveBtn.addEventListener('click', async () => {
  if (!currentPaperData) return;

  saveBtn.disabled = true;
  saveBtn.textContent = '';
  const spinner = document.createElement('span');
  spinner.className = 'spinner';
  saveBtn.appendChild(spinner);
  saveBtn.appendChild(document.createTextNode(' Saving...'));
  clearMessage(saveMsg);

  try {
    const resp = await chrome.runtime.sendMessage({
      type: 'SAVE_REFERENCE',
      data: currentPaperData,
    });

    if (resp && resp.success) {
      showMessage(saveMsg, 'Saved to your library!', 'success');
      saveBtn.textContent = 'Saved';
    } else {
      throw new Error(resp?.error || 'Failed to save');
    }
  } catch (err) {
    showMessage(saveMsg, err.message, 'error');
    saveBtn.disabled = false;
    setSaveBtnDefault();
  }
});

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
