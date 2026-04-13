const STORAGE_KEY_EOD = "stock-watchlist-eodhd-key";
const cardList = document.getElementById("cardList");
const searchInput = document.getElementById("searchInput");
const filterButtons = document.querySelectorAll(".filter-btn");
const refreshBtn = document.getElementById("refreshBtn");
const refreshSpinner = document.getElementById("refreshSpinner");
const refreshBtnText = document.getElementById("refreshBtnText");
const saveApiKeyBtn = document.getElementById("saveApiKeyBtn");
const apiKeyInput = document.getElementById("apiKeyInput");
const statusBar = document.getElementById("statusBar");

const totalCount = document.getElementById("totalCount");
const ownedCount = document.getElementById("ownedCount");
const watchlistCount = document.getElementById("watchlistCount");
const upcomingCount = document.getElementById("upcomingCount");

let currentFilter = "all";
let liveData = {};

const FINNHUB_BASE = "https://finnhub.io/api/v1";
const STORAGE_KEY = "stock-watchlist-finnhub-key";

const marketSymbolMap = {
  "A2M": "A2M.AU",
  "CCR": "CCR.AU",
  "CSL": "CSL.AU",
  "HGH": "HGH.AU",
  "MQG": "MQG.AU",
  "SIG": "SIG.AU",
  "XRO": "XRO.AU",
  "EUAD": "LSE:EUAD"
};

function getApiKey() {
  return localStorage.getItem(STORAGE_KEY) || "";
}

function setStatus(message) {
  statusBar.textContent = message;
}

function saveApiKey() {
  const key = apiKeyInput.value.trim();
  if (!key) {
    setStatus("Please paste your Finnhub API key first.");
    return;
  }
  localStorage.setItem(STORAGE_KEY, key);
  setStatus("API key saved on this device.");
}

function resolveSymbol(item) {
  return marketSymbolMap[item.ticker] || item.ticker;
}
function getEodKey() {
  return localStorage.getItem(STORAGE_KEY_EOD) || "";
}

function saveEodKey() {
  const key = prompt("Paste your EODHD API key:");
  if (!key) return;
  localStorage.setItem(STORAGE_KEY_EOD, key.trim());
  setStatus("EODHD key saved.");
}
function formatCurrency(value) {
  if (value == null || Number.isNaN(value)) return "—";
  return new Intl.NumberFormat(undefined, {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: value < 10 ? 3 : 2
  }).format(value);
}

function formatPercent(value) {
  if (value == null || Number.isNaN(value)) return "—";
  const sign = value > 0 ? "+" : "";
  return `${sign}${value.toFixed(2)}%`;
}

function formatDate(dateStr) {
  if (!dateStr) return "—";
  const d = new Date(dateStr + "T00:00:00");
  if (Number.isNaN(d.getTime())) return dateStr;
  return d.toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" });
}

function daysUntil(dateStr) {
  if (!dateStr) return null;
  const today = new Date();
  const target = new Date(dateStr + "T00:00:00");
  const ms = target - new Date(today.getFullYear(), today.getMonth(), today.getDate());
  return Math.round(ms / 86400000);
}

function updateSummary(filteredForDisplay) {
  totalCount.textContent = stocks.length;
  ownedCount.textContent = stocks.filter(x => x.status === "owned").length;
  watchlistCount.textContent = stocks.filter(x => x.status === "watchlist").length;

  const upcoming = stocks.filter(item => {
    const earningDate = liveData[item.ticker]?.earningsDate;
    const d = daysUntil(earningDate);
    return d != null && d >= 0 && d <= 30;
  }).length;
  upcomingCount.textContent = upcoming;
}

function getMetricClass(value) {
  if (value > 0) return "pos";
  if (value < 0) return "neg";
  return "";
}

function buildCard(item) {
  const data = liveData[item.ticker] || {};
  const earningsDate = data.earningsDate || null;
  const dte = daysUntil(earningsDate);

  let earningsText = "—";
  if (earningsDate) {
    earningsText = formatDate(earningsDate);
    if (dte != null && dte >= 0) earningsText += ` (${dte}d)`;
  }

  const quote = data.quote || {};
  const current = quote.c;
  const pct = quote.dp;

  return `
    <article class="stock-card ${item.status}">
      <div class="card-head">
        <div>
          <h2 class="company">${item.company}</h2>
          <div class="ticker-line">${item.ticker} · ${item.market}</div>
        </div>
        <span class="badge ${item.status}">${item.status === "owned" ? "Owned" : "Watchlist"}</span>
      </div>

      <div class="metrics-grid">
        <div class="metric">
          <div class="metric-label">Price</div>
          <div class="metric-value">${formatCurrency(current)}</div>
        </div>
        <div class="metric">
          <div class="metric-label">Day %</div>
          <div class="metric-value ${getMetricClass(pct)}">${formatPercent(pct)}</div>
        </div>
        <div class="metric">
          <div class="metric-label">Next earnings</div>
          <div class="metric-value">${earningsText}</div>
        </div>
        <div class="metric">
          <div class="metric-label">Source symbol</div>
          <div class="metric-value">${resolveSymbol(item)}</div>
        </div>
      </div>

      <div class="notes">${item.notes}</div>
      ${item.irUrl ? `<div class="card-actions"><a class="secondary-btn" href="${item.irUrl}" target="_blank" rel="noopener">IR Page</a></div>` : ""}
      <div class="small-note">Some ETFs, OTC lines and non-US tickers may have patchy coverage depending on the data provider and exchange mapping.</div>


    </article>
  `;
}

function renderCards() {
  const searchText = searchInput.value.trim().toLowerCase();

  const filtered = stocks.filter(item => {
    const matchesFilter = currentFilter === "all" ? true : item.status === currentFilter;
    const searchable = `${item.company} ${item.ticker} ${item.market} ${item.notes}`.toLowerCase();
    return matchesFilter && searchable.includes(searchText);
  });

  updateSummary(filtered);

  if (!filtered.length) {
    cardList.innerHTML = `<div class="empty">No matching stocks found.</div>`;
    return;
  }

  cardList.innerHTML = filtered.map(buildCard).join("");
}

async function fetchQuote(symbol, apiKey) {
  const url = `${FINNHUB_BASE}/quote?symbol=${encodeURIComponent(symbol)}&token=${encodeURIComponent(apiKey)}`;
  const res = await fetch(url);
  if (!res.ok) throw new Error(`Quote failed for ${symbol}`);
  return await res.json();
}
async function fetchEodQuote(symbol, apiKey) {
  const url = `https://eodhd.com/api/eod/${symbol}?filter=last_close&api_token=${apiKey}&fmt=json`;
  const res = await fetch(url);

  if (!res.ok) throw new Error(`EODHD failed for ${symbol}`);

  const price = await res.json();

  return {
    c: price,
    dp: null
  };
}
async function fetchEarnings(symbol, apiKey) {
  const today = new Date();
  const from = today.toISOString().slice(0, 10);
  const toObj = new Date(today.getTime() + 180 * 86400000);
  const to = toObj.toISOString().slice(0, 10);
  const url = `${FINNHUB_BASE}/calendar/earnings?symbol=${encodeURIComponent(symbol)}&from=${from}&to=${to}&token=${encodeURIComponent(apiKey)}`;
  const res = await fetch(url);
  if (!res.ok) throw new Error(`Earnings failed for ${symbol}`);
  const json = await res.json();
  const earningsCalendar = json.earningsCalendar || [];
  const nextItem = earningsCalendar
    .filter(x => x.date)
    .sort((a, b) => a.date.localeCompare(b.date))[0];
  return nextItem ? nextItem.date : null;
}

async function refreshLiveData() {
  const apiKey = getApiKey();
  if (!apiKey) {
    setStatus("Add your Finnhub API key and tap Save key.");
    return;
  }

  setStatus("Refreshing live prices and earnings dates...");
  refreshBtn.disabled = true;
  refreshSpinner.classList.remove("hidden");
  refreshBtnText.textContent = "Refreshing...";

  const nextLiveData = {};

  for (let i = 0; i < stocks.length; i++) {
    const item = stocks[i];
    const symbol = resolveSymbol(item);

    let quote = {};
let earningsDate = null;
let error = null;

try {
  if (symbol.endsWith(".AU")) {
    const eodKey = getEodKey();
    if (!eodKey) throw new Error("No EODHD key saved");
    quote = await fetchEodQuote(symbol, eodKey);
  } else {
    quote = await fetchQuote(symbol, apiKey);
  }
} catch (err) {
  error = err.message;
  console.error("Quote error for", symbol, err);
}

    try {
      earningsDate = await fetchEarnings(symbol, apiKey);
    } catch (err) {
      error = error
        ? error + ` | Earnings failed: ${err.message}`
        : `Earnings failed: ${err.message}`;
      console.error("Earnings error for", symbol, err);
    }

    nextLiveData[item.ticker] = {
      quote,
      earningsDate,
      sourceSymbol: symbol,
      error
    };

    liveData = nextLiveData;
    renderCards();

    setStatus(`Loaded ${i + 1} of ${stocks.length}: ${item.ticker}`);

    await new Promise(r => setTimeout(r, 1200));
  }

 refreshBtn.disabled = false;
refreshSpinner.classList.add("hidden");
refreshBtnText.textContent = "Refresh";
setStatus("Refresh finished.");
}
 
searchInput.addEventListener("input", renderCards);

filterButtons.forEach(button => {
  button.addEventListener("click", () => {
    filterButtons.forEach(btn => btn.classList.remove("active"));
    button.classList.add("active");
    currentFilter = button.dataset.filter;
    renderCards();
  });
});

saveApiKeyBtn.addEventListener("click", saveApiKey);
refreshBtn.addEventListener("click", refreshLiveData);

// if ("serviceWorker" in navigator) {
//  window.addEventListener("load", () => {
//    navigator.serviceWorker.register("./service-worker.js").catch(() => {});
//  });
// }

apiKeyInput.value = getApiKey();
renderCards();

