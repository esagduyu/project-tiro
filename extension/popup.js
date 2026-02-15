const TIRO_URL = 'http://localhost:8000';

const els = {
  stateReady: document.getElementById('state-ready'),
  stateSaving: document.getElementById('state-saving'),
  stateSuccess: document.getElementById('state-success'),
  stateError: document.getElementById('state-error'),
  stateAlready: document.getElementById('state-already'),
  pageTitle: document.getElementById('page-title'),
  pageUrl: document.getElementById('page-url'),
  vipToggle: document.getElementById('vip-toggle'),
  saveBtn: document.getElementById('save-btn'),
  successTitle: document.getElementById('success-title'),
  successSource: document.getElementById('success-source'),
  openLink: document.getElementById('open-link'),
  errorText: document.getElementById('error-text'),
  retryBtn: document.getElementById('retry-btn'),
  alreadyTitle: document.getElementById('already-title'),
  alreadyTime: document.getElementById('already-time'),
  alreadyLink: document.getElementById('already-link'),
};

let currentUrl = '';

function showState(name) {
  ['stateReady', 'stateSaving', 'stateSuccess', 'stateError', 'stateAlready'].forEach(function (key) {
    els[key].classList.toggle('active', key === 'state' + name.charAt(0).toUpperCase() + name.slice(1));
  });
}

function formatTimeAgo(isoStr) {
  var date = new Date(isoStr);
  var now = new Date();
  var diffMs = now - date;
  var diffMin = Math.floor(diffMs / 60000);
  var diffHr = Math.floor(diffMin / 60);
  var diffDay = Math.floor(diffHr / 24);

  if (diffMin < 1) return 'just now';
  if (diffMin < 60) return diffMin + ' minute' + (diffMin === 1 ? '' : 's') + ' ago';
  if (diffHr < 24) return diffHr + ' hour' + (diffHr === 1 ? '' : 's') + ' ago';
  if (diffDay < 30) return diffDay + ' day' + (diffDay === 1 ? '' : 's') + ' ago';
  return date.toLocaleDateString();
}

// Get current tab info on popup open, then check if already saved
chrome.tabs.query({ active: true, currentWindow: true }, function (tabs) {
  if (tabs[0]) {
    currentUrl = tabs[0].url;
    els.pageTitle.textContent = tabs[0].title || 'Untitled page';
    els.pageUrl.textContent = currentUrl;
    checkIfSaved(currentUrl);
  }
});

async function checkIfSaved(url) {
  try {
    var res = await fetch(TIRO_URL + '/api/ingest/check?url=' + encodeURIComponent(url));
    var data = await res.json();
    if (data.success && data.saved) {
      els.alreadyTitle.textContent = data.data.title;
      els.alreadyTime.textContent = 'Saved ' + formatTimeAgo(data.data.ingested_at);
      els.alreadyLink.href = TIRO_URL + '/articles/' + data.data.id;
      showState('already');
    }
  } catch (_) {
    // Server might not be running — that's fine, user will see the error when they try to save
  }
}

// Save button click
els.saveBtn.addEventListener('click', saveArticle);
els.retryBtn.addEventListener('click', function () {
  showState('ready');
});

async function saveArticle() {
  if (!currentUrl) return;

  showState('saving');

  try {
    var res = await fetch(TIRO_URL + '/api/ingest/url', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ url: currentUrl }),
    });

    var data = await res.json();

    if (data.success) {
      var article = data.data;
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
    } else if (data.error === 'already_saved') {
      // 409 — already saved, show the already-saved state
      els.alreadyTitle.textContent = data.data.title;
      els.alreadyTime.textContent = 'Saved ' + formatTimeAgo(data.data.ingested_at);
      els.alreadyLink.href = TIRO_URL + '/articles/' + data.data.id;
      showState('already');
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
