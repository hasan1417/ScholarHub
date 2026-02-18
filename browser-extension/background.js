// ScholarHub Browser Extension - Background Service Worker

// Listen for messages from popup and content scripts
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message.type === 'SAVE_REFERENCE') {
    // Attach the sender tab ID so we can delegate PDF fetching back to the content script
    const data = { ...message.data };
    if (sender.tab?.id) {
      data._tabId = sender.tab.id;
    }
    handleSaveReference(data, message.projectId).then(sendResponse);
    return true; // keep message channel open for async response
  }

  if (message.type === 'FETCH_AND_UPLOAD_PDF') {
    fetchAndUploadPdf(message.pdfUrl, message.referenceId).then(sendResponse);
    return true;
  }
});

/**
 * Save a reference to a ScholarHub project via the API.
 * If no projectId is given (badge click), fetches the user's first project.
 * If a PDF URL is detected, downloads and uploads it to backend.
 */
async function handleSaveReference(paperData, projectId) {
  try {
    const stored = await chrome.storage.local.get(['instanceUrl', 'accessToken', 'tokenExpiresAt']);

    if (!stored.accessToken || !stored.instanceUrl) {
      return { success: false, error: 'Not signed in. Please open the extension and sign in.' };
    }

    if (stored.tokenExpiresAt && Date.now() >= stored.tokenExpiresAt) {
      await chrome.storage.local.remove(['accessToken', 'userEmail', 'userName', 'tokenExpiresAt']);
      return { success: false, error: 'Session expired. Please sign in again.' };
    }

    const baseUrl = stored.instanceUrl.replace(/\/+$/, '');
    const headers = {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${stored.accessToken}`,
    };

    // If no project specified (badge click), find the user's first project
    if (!projectId) {
      try {
        const projResp = await fetch(`${baseUrl}/api/v1/projects/?limit=1`, { headers });
        if (projResp.ok) {
          const projData = await projResp.json();
          const projects = projData.projects || [];
          if (projects.length > 0) {
            projectId = projects[0].id;
          }
        }
      } catch {
        // Non-fatal
      }
    }

    // Build the reference payload
    const payload = {
      title: paperData.title,
      authors: paperData.authors || [],
      year: paperData.year ? parseInt(paperData.year, 10) || null : null,
      doi: paperData.doi || null,
      url: paperData.url || null,
      source: paperData.source || 'browser-extension',
      journal: paperData.journal || null,
      abstract: paperData.abstract || null,
      pdf_url: paperData.pdfUrl || null,
    };

    const resp = await fetch(`${baseUrl}/api/v1/references/`, {
      method: 'POST',
      headers,
      body: JSON.stringify(payload),
    });

    if (resp.status === 401) {
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

    // Quick-add to project
    if (projectId) {
      try {
        await fetch(`${baseUrl}/api/v1/projects/${projectId}/references/quick-add`, {
          method: 'POST',
          headers,
          body: JSON.stringify({ reference_id: reference.id }),
        });
      } catch {
        // Non-fatal
      }
    }

    // If PDF URL detected and reference doesn't already have a document,
    // fetch the PDF directly from the background service worker and upload.
    if (paperData.pdfUrl && !reference.document_id) {
      try {
        const pdfResult = await fetchAndUploadPdf(paperData.pdfUrl, reference.id);
        if (pdfResult?.error) {
          console.warn('PDF fetch/upload failed:', pdfResult.error);
        }
      } catch (e) {
        console.warn('PDF fetch/upload failed (non-fatal):', e);
      }
    }

    return { success: true, reference };
  } catch (err) {
    return { success: false, error: err.message || 'Network error' };
  }
}

/**
 * Fetch a PDF from a URL and upload it to the ScholarHub backend.
 * Runs in the service worker which has host_permissions CORS bypass.
 */
async function fetchAndUploadPdf(pdfUrl, referenceId) {
  try {
    const blob = await fetchPdfBlob(pdfUrl);
    if (!blob) {
      return { error: 'Could not download PDF from publisher' };
    }

    const stored = await chrome.storage.local.get(['instanceUrl', 'accessToken']);
    if (!stored.accessToken || !stored.instanceUrl) {
      return { error: 'Not signed in' };
    }

    const baseUrl = stored.instanceUrl.replace(/\/+$/, '');
    const formData = new FormData();
    formData.append('file', blob, 'paper.pdf');

    const uploadResp = await fetch(`${baseUrl}/api/v1/references/${referenceId}/upload-pdf`, {
      method: 'POST',
      headers: { 'Authorization': `Bearer ${stored.accessToken}` },
      body: formData,
    });

    if (uploadResp.ok) {
      return { success: true };
    }
    return { error: `Upload failed: HTTP ${uploadResp.status}` };
  } catch (e) {
    return { error: e.message || 'PDF fetch/upload error' };
  }
}

/**
 * Fetch a PDF blob from the given URL.
 * If the URL returns HTML (e.g. IEEE stamp viewer), tries to extract
 * the actual PDF URL from the HTML and retry.
 */
async function fetchPdfBlob(pdfUrl) {
  const resp = await fetch(pdfUrl);
  if (!resp.ok) return null;

  const ct = resp.headers.get('content-type') || '';

  // Happy path: got a PDF directly
  if (ct.includes('pdf') || ct.includes('octet-stream')) {
    const rawBlob = await resp.blob();
    if (rawBlob.size > 50 * 1024 * 1024) return null;
    return new Blob([rawBlob], { type: 'application/pdf' });
  }

  // Got HTML — likely a viewer/stamp page. Try to extract the real PDF URL.
  if (ct.includes('html')) {
    try {
      const html = await resp.text();
      const realPdfUrl = extractPdfUrlFromHtml(html, pdfUrl);
      if (realPdfUrl) {
        const retry = await fetch(realPdfUrl);
        if (!retry.ok) return null;
        const retryCt = retry.headers.get('content-type') || '';
        if (retryCt.includes('pdf') || retryCt.includes('octet-stream')) {
          const rawBlob = await retry.blob();
          if (rawBlob.size > 50 * 1024 * 1024) return null;
          return new Blob([rawBlob], { type: 'application/pdf' });
        }
      }
    } catch {
      // Couldn't extract PDF URL from HTML
    }
  }

  return null;
}

/**
 * Given an HTML response (e.g. IEEE stamp viewer), try to extract
 * the actual PDF URL from iframe/embed/object/link tags.
 */
function extractPdfUrlFromHtml(html, baseUrl) {
  const patterns = [
    /src=["']([^"']*\.pdf[^"']*)/i,
    /src=["']([^"']*\/pdf\/[^"']*)/i,
    /data=["']([^"']*\.pdf[^"']*)/i,
    /href=["']([^"']*\.pdf[^"']*)/i,
    /(https?:\/\/ieeexplore\.ieee\.org\/ielx[^"'\s]+\.pdf[^"'\s]*)/i,
  ];

  for (const pat of patterns) {
    const match = html.match(pat);
    if (match && match[1]) {
      let url = match[1];
      if (url.startsWith('/')) {
        try {
          const base = new URL(baseUrl);
          url = `${base.origin}${url}`;
        } catch { /* ignore */ }
      }
      return url;
    }
  }

  return null;
}
