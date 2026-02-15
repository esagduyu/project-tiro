const TIRO_URL = 'http://localhost:8000';

const els = {
  stateReady: document.getElementById('state-ready'),
  stateSaving: document.getElementById('state-saving'),
  stateSuccess: document.getElementById('state-success'),
  stateError: document.getElementById('state-error'),
  pageTitle: document.getElementById('page-title'),
  pageUrl: document.getElementById('page-url'),
  vipToggle: document.getElementById('vip-toggle'),
  saveBtn: document.getElementById('save-btn'),
  successTitle: document.getElementById('success-title'),
  successSource: document.getElementById('success-source'),
  openLink: document.getElementById('open-link'),
  errorText: document.getElementById('error-text'),
  retryBtn: document.getElementById('retry-btn'),
};

let currentUrl = '';

function showState(name) {
  ['stateReady', 'stateSaving', 'stateSuccess', 'stateError'].forEach(function (key) {
    els[key].classList.toggle('active', key === 'state' + name.charAt(0).toUpperCase() + name.slice(1));
  });
}

// Get current tab info on popup open
chrome.tabs.query({ active: true, currentWindow: true }, function (tabs) {
  if (tabs[0]) {
    currentUrl = tabs[0].url;
    els.pageTitle.textContent = tabs[0].title || 'Untitled page';
    els.pageUrl.textContent = currentUrl;
  }
});

// Save button click
els.saveBtn.addEventListener('click', saveArticle);
els.retryBtn.addEventListener('click', function () {
  showState('ready');
});

async function saveArticle() {
  if (!currentUrl) return;

  showState('saving');

  try {
    const res = await fetch(TIRO_URL + '/api/ingest/url', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ url: currentUrl }),
    });

    const data = await res.json();

    if (data.success) {
      const article = data.data;
      els.successTitle.textContent = article.title || 'Saved';
      els.successSource.textContent = article.source || '';
      els.openLink.href = TIRO_URL + '/articles/' + article.id;

      // Toggle VIP if checked
      if (els.vipToggle.checked && article.source_id) {
        try {
          await fetch(TIRO_URL + '/api/sources/' + article.source_id + '/vip', {
            method: 'PATCH',
          });
        } catch (_) {
          // VIP toggle is best-effort
        }
      }

      showState('success');
    } else {
      els.errorText.textContent = data.error || 'Could not save this page.';
      showState('error');
    }
  } catch (err) {
    if (err.message && err.message.includes('Failed to fetch')) {
      els.errorText.textContent = 'Tiro server not running. Start it with: uv run python run.py';
    } else {
      els.errorText.textContent = err.message || 'Could not save this page.';
    }
    showState('error');
  }
}
