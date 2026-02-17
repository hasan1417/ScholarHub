// ScholarHub Browser Extension - Background Service Worker

// Listen for messages from popup and content scripts
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message.type === 'SAVE_REFERENCE') {
    handleSaveReference(message.data).then(sendResponse);
    return true; // keep message channel open for async response
  }
});

/**
 * Save a reference to the ScholarHub library via the API.
 */
async function handleSaveReference(paperData) {
  try {
    const stored = await chrome.storage.local.get(['instanceUrl', 'accessToken', 'tokenExpiresAt']);

    if (!stored.accessToken || !stored.instanceUrl) {
      return { success: false, error: 'Not signed in. Please open the extension and sign in.' };
    }

    // Check if token has expired before making the API call
    if (stored.tokenExpiresAt && Date.now() >= stored.tokenExpiresAt) {
      await chrome.storage.local.remove(['accessToken', 'userEmail', 'userName', 'tokenExpiresAt']);
      return { success: false, error: 'Session expired. Please sign in again.' };
    }

    const baseUrl = stored.instanceUrl.replace(/\/+$/, '');

    // Build the reference payload matching the backend ReferenceCreateRequest schema
    const payload = {
      title: paperData.title,
      authors: paperData.authors || [],
      year: paperData.year ? parseInt(paperData.year, 10) || null : null,
      doi: paperData.doi || null,
      url: paperData.url || null,
      source: paperData.source || 'browser-extension',
      journal: paperData.journal || null,
      abstract: paperData.abstract || null,
    };

    const resp = await fetch(`${baseUrl}/api/v1/references/`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${stored.accessToken}`,
      },
      body: JSON.stringify(payload),
    });

    if (resp.status === 401) {
      // Token expired - clear credentials
      await chrome.storage.local.remove(['accessToken', 'userEmail', 'userName', 'tokenExpiresAt']);
      return { success: false, error: 'Session expired. Please sign in again.' };
    }

    if (!resp.ok) {
      const err = await resp.json().catch(() => ({}));
      let detail;
      const d = err.detail;
      if (typeof d === 'string') {
        detail = d;
      } else if (d?.error === 'limit_exceeded') {
        detail = `Library limit reached (${d.current}/${d.limit}). Upgrade to add more references.`;
      } else if (d?.message) {
        detail = d.message;
      } else if (err.message) {
        detail = err.message;
      } else {
        detail = `Request failed (${resp.status})`;
      }
      return { success: false, error: detail };
    }

    const reference = await resp.json();
    return { success: true, reference };
  } catch (err) {
    return { success: false, error: err.message || 'Network error' };
  }
}
