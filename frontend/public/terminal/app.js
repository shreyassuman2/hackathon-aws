// Purchase emulator: "swipe" a company card and send the charge to the Runway API.
// Open index.html in a browser. Configure via query string, e.g.
//   index.html?api=https://xxxx.execute-api.us-east-1.amazonaws.com&token=...
const params = new URLSearchParams(location.search);
const API_URL = (params.get('api') || 'http://localhost:8000').replace(/\/$/, '');
const API_TOKEN = params.get('token') || '';

const swipeBtn = document.getElementById('swipe-button');
const statusTray = document.getElementById('status-tray');
const statusMsg = document.getElementById('status-message');
const swipesList = document.getElementById('swipes-list');

let recentSwipes = [];
try { recentSwipes = JSON.parse(localStorage.getItem('recent_swipes') || '[]'); } catch { recentSwipes = []; }

const clearBtn = document.getElementById('clear-swipes');
clearBtn.addEventListener('click', () => {
    recentSwipes = [];
    try { localStorage.removeItem('recent_swipes'); } catch { /* private mode */ }
    updateSwipesList();
});

function updateSwipesList() {
    clearBtn.hidden = recentSwipes.length === 0;
    swipesList.replaceChildren(...recentSwipes.map(s => {
        const pill = document.createElement('div');
        pill.className = 'swipe-pill';
        const m = document.createElement('span');
        m.className = 'merchant';
        m.textContent = s.merchant;
        const a = document.createElement('span');
        a.className = 'amount';
        a.textContent = `$${Number(s.amount).toFixed(2)}`;
        pill.append(m, a);
        return pill;
    }));
}

updateSwipesList();

swipeBtn.addEventListener('click', async () => {
    const merchant = document.getElementById('merchant').value.trim();
    const amount = parseFloat(document.getElementById('amount').value);
    const pillar = document.getElementById('pillar').value;
    const empSelect = document.getElementById('employee_id');
    const employee_id = empSelect.value || null;
    const submitted_by = empSelect.options[empSelect.selectedIndex].text.split('(')[0].trim();
    const memo = document.getElementById('memo').value.trim() || null;

    if (!merchant || !amount) {
        showStatus('Please fill in Merchant and Amount.', 'error');
        return;
    }

    swipeBtn.classList.add('loading');
    swipeBtn.innerText = 'Processing…';

    try {
        const res = await fetch(`${API_URL}/transactions`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', ...(API_TOKEN && { 'X-Runway-Token': API_TOKEN }) },
            // "auto" lets Runway's router decide the pillar.
            body: JSON.stringify({ merchant, amount, employee_id, submitted_by, memo,
                                   category: pillar === 'auto' ? null : pillar }),
        });
        if (!res.ok) throw new Error(`API returned ${res.status}`);
        const { alert } = await res.json();
        const flagged = alert.requires_action;
        showStatus(flagged ? `Flagged (${alert.tier}): ${alert.message}` : `Logged: ${alert.message}`,
                   flagged ? 'warning' : 'success');

        recentSwipes = [{ merchant, amount }, ...recentSwipes].slice(0, 5);
        try { localStorage.setItem('recent_swipes', JSON.stringify(recentSwipes)); } catch { /* private mode */ }
        updateSwipesList();
    } catch (error) {
        console.error('Swipe failed:', error);
        showStatus(`Error: ${error.message}. Is the API running at ${API_URL}?`, 'error');
    } finally {
        swipeBtn.classList.remove('loading');
        swipeBtn.innerText = 'Swipe card';
    }
});

function showStatus(text, type) {
    statusTray.className = `status-tray ${type}`;
    statusMsg.innerText = text;
    statusTray.style.display = 'block';
    setTimeout(() => {
        statusTray.style.display = 'none';
        statusTray.className = 'status-tray';
    }, 7000);
}
